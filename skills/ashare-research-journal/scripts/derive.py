#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 SQLite 存储与派生：落库、复核计算、查看、到期、统计、导出。

拆分自 research_journal.py（沿用 P2-5 纪律）。
"""

import json
import sqlite3

from datetime import date
from pathlib import Path
from typing import Any

from schema import JournalError, SCHEMA_VERSION, canonical_json, digest, now_iso
from validate import (
    validate_market_outcome,
    validate_market_snapshot,
    validate_outcome,
    validate_snapshot,
)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS research_records (
            research_id TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            name TEXT NOT NULL,
            market TEXT NOT NULL,
            as_of TEXT NOT NULL,
            evaluation_date TEXT NOT NULL,
            probability REAL,
            criterion_metric TEXT NOT NULL,
            criterion_operator TEXT NOT NULL,
            criterion_value REAL NOT NULL,
            snapshot_json TEXT NOT NULL,
            snapshot_sha256 TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS outcomes (
            research_id TEXT PRIMARY KEY REFERENCES research_records(research_id),
            outcome_json TEXT NOT NULL,
            outcome_sha256 TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            stock_return_pct REAL NOT NULL,
            benchmark_return_pct REAL,
            excess_return_pct REAL,
            max_drawdown_pct REAL NOT NULL,
            max_favorable_excursion_pct REAL NOT NULL,
            max_adverse_excursion_pct REAL NOT NULL,
            criterion_passed INTEGER NOT NULL,
            falsifier_triggered INTEGER NOT NULL,
            passed INTEGER NOT NULL
        );
        -- 市场级记录：与价格路径记录平行，独立成表，因此不需要迁移既有列（无 ALTER）。
        -- 价值在于同一份 SQLite 里既能复盘个股判断，也能复盘盘面条件，命中率可合并统计。
        CREATE TABLE IF NOT EXISTS market_records (
            research_id TEXT PRIMARY KEY,
            subject TEXT NOT NULL,
            market TEXT NOT NULL,
            as_of TEXT NOT NULL,
            evaluation_date TEXT NOT NULL,
            probability REAL,
            criterion_metric TEXT NOT NULL,
            criterion_operator TEXT NOT NULL,
            criterion_value REAL NOT NULL,
            snapshot_json TEXT NOT NULL,
            snapshot_sha256 TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS market_outcomes (
            research_id TEXT PRIMARY KEY REFERENCES market_records(research_id),
            outcome_json TEXT NOT NULL,
            outcome_sha256 TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            observed_value REAL NOT NULL,
            observed_unit TEXT NOT NULL,
            criterion_passed INTEGER NOT NULL,
            falsifier_triggered INTEGER NOT NULL,
            passed INTEGER NOT NULL
        );
        """
    )
    return db


def record(db: sqlite3.Connection, snapshot: dict[str, Any]) -> dict[str, Any]:
    validate_snapshot(snapshot)
    sha = digest(snapshot)
    criterion = snapshot["criterion"]
    try:
        db.execute(
            """
            INSERT INTO research_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot["research_id"],
                snapshot["code"],
                snapshot["name"],
                snapshot["market"],
                snapshot["as_of"],
                snapshot["evaluation_date"],
                snapshot.get("probability"),
                criterion["metric"],
                criterion["operator"],
                float(criterion["value"]),
                canonical_json(snapshot),
                sha,
                now_iso(),
            ),
        )
        db.commit()
    except sqlite3.IntegrityError as exc:
        raise JournalError(f"research_id 已存在：{snapshot['research_id']}") from exc
    return {"research_id": snapshot["research_id"], "snapshot_sha256": sha}


def get_record(db: sqlite3.Connection, research_id: str) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM research_records WHERE research_id = ?", (research_id,)
    ).fetchone()
    if row is None:
        raise JournalError(f"未找到research_id：{research_id}")
    return row


def path_metrics(path: list[dict[str, Any]]) -> dict[str, float]:
    values = [float(point["value"]) for point in path]
    baseline = values[0]
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        peak = max(peak, value)
        max_drawdown = min(max_drawdown, (value / peak - 1) * 100)
    return {
        "return_pct": (values[-1] / baseline - 1) * 100,
        "max_drawdown_pct": max_drawdown,
        "max_favorable_excursion_pct": (max(values) / baseline - 1) * 100,
        "max_adverse_excursion_pct": (min(values) / baseline - 1) * 100,
    }


def criterion_passed(metric_value: float, operator: str, target: float) -> bool:
    if operator == "lt":
        return metric_value < target
    if operator == "lte":
        return metric_value <= target
    if operator == "gt":
        return metric_value > target
    if operator == "gte":
        return metric_value >= target
    if operator == "eq":
        return metric_value == target
    return metric_value != target


def observe(
    db: sqlite3.Connection,
    research_id: str,
    outcome: dict[str, Any],
    review_as_of: date,
) -> dict[str, Any]:
    row = get_record(db, research_id)
    if db.execute(
        "SELECT 1 FROM outcomes WHERE research_id = ?", (research_id,)
    ).fetchone():
        raise JournalError(f"结果已存在：{research_id}")
    snapshot = json.loads(row["snapshot_json"])
    stock_path, benchmark_path = validate_outcome(outcome, snapshot, review_as_of)
    stock = path_metrics(stock_path)
    benchmark_return = None
    if benchmark_path:
        benchmark_return = path_metrics(benchmark_path)["return_pct"]
    excess_return = (
        stock["return_pct"] - benchmark_return
        if benchmark_return is not None
        else None
    )
    metric_values = {
        "stock_return_pct": stock["return_pct"],
        "benchmark_return_pct": benchmark_return,
        "excess_return_pct": excess_return,
        "max_drawdown_pct": stock["max_drawdown_pct"],
        "max_favorable_excursion_pct": stock["max_favorable_excursion_pct"],
        "max_adverse_excursion_pct": stock["max_adverse_excursion_pct"],
    }
    metric_value = metric_values[row["criterion_metric"]]
    if metric_value is None:
        raise JournalError("评价指标缺少必要基准数据")
    criterion_result = criterion_passed(
        metric_value, row["criterion_operator"], row["criterion_value"]
    )
    falsifier_triggered = bool(outcome.get("falsifiers_triggered"))
    passed = criterion_result and not falsifier_triggered
    result = {
        "research_id": research_id,
        "stock_return_pct": round(stock["return_pct"], 6),
        "benchmark_return_pct": (
            round(benchmark_return, 6) if benchmark_return is not None else None
        ),
        "excess_return_pct": (
            round(excess_return, 6) if excess_return is not None else None
        ),
        "max_drawdown_pct": round(stock["max_drawdown_pct"], 6),
        "max_favorable_excursion_pct": round(
            stock["max_favorable_excursion_pct"], 6
        ),
        "max_adverse_excursion_pct": round(
            stock["max_adverse_excursion_pct"], 6
        ),
        "criterion_passed": criterion_result,
        "falsifier_triggered": falsifier_triggered,
        "passed": passed,
    }
    outcome_sha = digest(outcome)
    try:
        db.execute(
            """
            INSERT INTO outcomes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                research_id,
                canonical_json(outcome),
                outcome_sha,
                now_iso(),
                result["stock_return_pct"],
                result["benchmark_return_pct"],
                result["excess_return_pct"],
                result["max_drawdown_pct"],
                result["max_favorable_excursion_pct"],
                result["max_adverse_excursion_pct"],
                int(criterion_result),
                int(falsifier_triggered),
                int(passed),
            ),
        )
        db.commit()
    except sqlite3.IntegrityError as exc:
        raise JournalError(f"结果已存在：{research_id}") from exc
    return {**result, "outcome_sha256": outcome_sha}


# ============ 市场级记录（与价格路径记录平行） ============

def record_market(db: sqlite3.Connection, snapshot: dict[str, Any]) -> dict[str, Any]:
    validate_market_snapshot(snapshot)
    sha = digest(snapshot)
    criterion = snapshot["criterion"]
    try:
        db.execute(
            "INSERT INTO market_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                snapshot["research_id"],
                snapshot["subject"],
                snapshot["market"],
                snapshot["as_of"],
                snapshot["evaluation_date"],
                snapshot.get("probability"),
                criterion["metric"],
                criterion["operator"],
                float(criterion["value"]),
                canonical_json(snapshot),
                sha,
                now_iso(),
            ),
        )
        db.commit()
    except sqlite3.IntegrityError as exc:
        raise JournalError(f"research_id 已存在：{snapshot['research_id']}") from exc
    return {
        "research_id": snapshot["research_id"],
        "snapshot_sha256": sha,
        "kind": "market",
    }


def get_market_record(db: sqlite3.Connection, research_id: str) -> sqlite3.Row:
    row = db.execute(
        "SELECT * FROM market_records WHERE research_id = ?", (research_id,)
    ).fetchone()
    if row is None:
        raise JournalError(f"未找到research_id：{research_id}")
    return row


def metric_by_name(metrics: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for item in metrics:
        if item.get("metric") == name:
            return item
    raise JournalError(f"market_metrics 缺少 {name}")


def observe_market(
    db: sqlite3.Connection,
    research_id: str,
    outcome: dict[str, Any],
    review_as_of: date,
) -> dict[str, Any]:
    row = get_market_record(db, research_id)
    if db.execute(
        "SELECT 1 FROM market_outcomes WHERE research_id = ?", (research_id,)
    ).fetchone():
        raise JournalError(f"结果已存在：{research_id}")
    snapshot = json.loads(row["snapshot_json"])
    metrics = validate_market_outcome(outcome, snapshot, review_as_of)
    criterion = snapshot["criterion"]
    observed = metric_by_name(metrics, criterion["metric"])
    value = float(observed["value"])
    criterion_result = criterion_passed(
        value, criterion["operator"], float(criterion["value"])
    )
    falsifier_triggered = bool(outcome.get("falsifiers_triggered"))
    passed = criterion_result and not falsifier_triggered
    result = {
        "research_id": research_id,
        "kind": "market",
        "criterion_metric": criterion["metric"],
        "criterion_operator": criterion["operator"],
        "criterion_value": float(criterion["value"]),
        "observed_value": value,
        "observed_unit": observed["unit"],
        "criterion_passed": criterion_result,
        "falsifier_triggered": falsifier_triggered,
        "passed": passed,
    }
    outcome_sha = digest(outcome)
    try:
        db.execute(
            "INSERT INTO market_outcomes VALUES (?,?,?,?,?,?,?,?,?)",
            (
                research_id,
                canonical_json(outcome),
                outcome_sha,
                now_iso(),
                result["observed_value"],
                result["observed_unit"],
                int(criterion_result),
                int(falsifier_triggered),
                int(passed),
            ),
        )
        db.commit()
    except sqlite3.IntegrityError as exc:
        raise JournalError(f"结果已存在：{research_id}") from exc
    return {**result, "outcome_sha256": outcome_sha}


def show(db: sqlite3.Connection, research_id: str) -> dict[str, Any]:
    """单条复盘。先在价格路径记录里找，找不到再找市场级记录。"""
    price = db.execute(
        "SELECT * FROM research_records WHERE research_id = ?", (research_id,)
    ).fetchone()
    if price is None:
        return show_market(db, research_id)
    row = price
    outcome = db.execute(
        "SELECT * FROM outcomes WHERE research_id = ?", (research_id,)
    ).fetchone()
    result = {
        "snapshot": json.loads(row["snapshot_json"]),
        "snapshot_sha256": row["snapshot_sha256"],
        "recorded_at": row["recorded_at"],
        "outcome": None,
    }
    if outcome:
        result["outcome"] = {
            "input": json.loads(outcome["outcome_json"]),
            "outcome_sha256": outcome["outcome_sha256"],
            "metrics": {
                key: outcome[key]
                for key in (
                    "stock_return_pct",
                    "benchmark_return_pct",
                    "excess_return_pct",
                    "max_drawdown_pct",
                    "max_favorable_excursion_pct",
                    "max_adverse_excursion_pct",
                    "criterion_passed",
                    "falsifier_triggered",
                    "passed",
                )
            },
        }
        for field in ("criterion_passed", "falsifier_triggered", "passed"):
            result["outcome"]["metrics"][field] = bool(
                result["outcome"]["metrics"][field]
            )
    result["kind"] = "price"
    return result


def show_market(db: sqlite3.Connection, research_id: str) -> dict[str, Any]:
    """市场级单条复盘。没有价格路径，结果只有「观察值 vs 阈值」的判定。"""
    row = get_market_record(db, research_id)
    outcome = db.execute(
        "SELECT * FROM market_outcomes WHERE research_id = ?", (research_id,)
    ).fetchone()
    result: dict[str, Any] = {
        "kind": "market",
        "snapshot": json.loads(row["snapshot_json"]),
        "snapshot_sha256": row["snapshot_sha256"],
        "recorded_at": row["recorded_at"],
        "outcome": None,
    }
    if outcome:
        metrics = {
            "observed_value": outcome["observed_value"],
            "observed_unit": outcome["observed_unit"],
            "criterion_passed": bool(outcome["criterion_passed"]),
            "falsifier_triggered": bool(outcome["falsifier_triggered"]),
            "passed": bool(outcome["passed"]),
        }
        result["outcome"] = {
            "input": json.loads(outcome["outcome_json"]),
            "outcome_sha256": outcome["outcome_sha256"],
            "metrics": metrics,
        }
    return result


def due(db: sqlite3.Connection, as_of: date) -> list[dict[str, Any]]:
    """到期未复核记录，价格路径与市场级合并返回，各带 kind 便于区分。"""
    rows = db.execute(
        """
        SELECT r.research_id, r.code, r.name, r.evaluation_date
        FROM research_records r
        LEFT JOIN outcomes o ON o.research_id = r.research_id
        WHERE r.evaluation_date <= ? AND o.research_id IS NULL
        """,
        (as_of.isoformat(),),
    ).fetchall()
    items = [{**dict(row), "kind": "price"} for row in rows]
    market_rows = db.execute(
        """
        SELECT m.research_id, m.subject, m.evaluation_date
        FROM market_records m
        LEFT JOIN market_outcomes o ON o.research_id = m.research_id
        WHERE m.evaluation_date <= ? AND o.research_id IS NULL
        """,
        (as_of.isoformat(),),
    ).fetchall()
    items += [
        {
            "research_id": row["research_id"],
            "code": row["subject"],
            "name": row["subject"],
            "evaluation_date": row["evaluation_date"],
            "kind": "market",
        }
        for row in market_rows
    ]
    items.sort(key=lambda item: (item["evaluation_date"], item["research_id"]))
    return items


def stats(db: sqlite3.Connection, as_of: date, code: str | None) -> dict[str, Any]:
    """成熟样本的聚合统计 + 逐条明细。

    价格路径记录与市场级记录**合并**计算命中率与 Brier（两者都是「条件是否兑现」）；
    但平均股票收益/超额/回撤只在价格路径记录上计算——市场级记录没有价格，不能摊进来。
    逐条明细带 kind 字段区分两类；价格路径记录的字段与改造前完全一致。
    """
    params: list[Any] = [as_of.isoformat()]
    where = "WHERE r.evaluation_date <= ?"
    if code:
        where += " AND r.code = ?"
        params.append(code)
    rows = db.execute(
        f"""
        SELECT r.research_id, r.code, r.name, r.evaluation_date, r.probability,
               o.stock_return_pct, o.benchmark_return_pct, o.excess_return_pct,
               o.max_drawdown_pct, o.max_favorable_excursion_pct,
               o.max_adverse_excursion_pct, o.criterion_passed,
               o.falsifier_triggered, o.passed
        FROM outcomes o JOIN research_records r ON r.research_id = o.research_id
        {where}
        ORDER BY r.research_id
        """,
        params,
    ).fetchall()
    records = [
        {
            "research_id": row["research_id"],
            "code": row["code"],
            "name": row["name"],
            "evaluation_date": row["evaluation_date"],
            "probability": row["probability"],
            "stock_return_pct": row["stock_return_pct"],
            "benchmark_return_pct": row["benchmark_return_pct"],
            "excess_return_pct": row["excess_return_pct"],
            "max_drawdown_pct": row["max_drawdown_pct"],
            "max_favorable_excursion_pct": row["max_favorable_excursion_pct"],
            "max_adverse_excursion_pct": row["max_adverse_excursion_pct"],
            "criterion_passed": bool(row["criterion_passed"]),
            "falsifier_triggered": bool(row["falsifier_triggered"]),
            "passed": bool(row["passed"]),
        }
        for row in rows
    ]
    market_params: list[Any] = [as_of.isoformat()]
    market_where = "WHERE m.evaluation_date <= ?"
    if code:
        market_where += " AND m.subject = ?"
        market_params.append(code)
    market_rows = db.execute(
        f"""
        SELECT m.research_id, m.subject, m.evaluation_date, m.probability,
               m.criterion_metric, m.criterion_operator, m.criterion_value,
               o.observed_value, o.observed_unit, o.criterion_passed,
               o.falsifier_triggered, o.passed
        FROM market_outcomes o JOIN market_records m ON m.research_id = o.research_id
        {market_where}
        ORDER BY m.research_id
        """,
        market_params,
    ).fetchall()
    total = len(rows) + len(market_rows)
    if not total:
        return {
            "as_of": as_of.isoformat(),
            "matured_count": 0,
            "passed_count": 0,
            "hit_rate_pct": None,
            "brier_score": None,
            "records": [],
        }

    market_records = [
        {
            "research_id": row["research_id"],
            "kind": "market",
            "code": row["subject"],
            "name": row["subject"],
            "evaluation_date": row["evaluation_date"],
            "probability": row["probability"],
            "stock_return_pct": None,
            "benchmark_return_pct": None,
            "excess_return_pct": None,
            "max_drawdown_pct": None,
            "max_favorable_excursion_pct": None,
            "max_adverse_excursion_pct": None,
            "criterion_metric": row["criterion_metric"],
            "criterion_operator": row["criterion_operator"],
            "criterion_value": row["criterion_value"],
            "observed_value": row["observed_value"],
            "observed_unit": row["observed_unit"],
            "criterion_passed": bool(row["criterion_passed"]),
            "falsifier_triggered": bool(row["falsifier_triggered"]),
            "passed": bool(row["passed"]),
        }
        for row in market_rows
    ]
    records = sorted(records + market_records, key=lambda item: item["research_id"])

    definitives = [
        (row["probability"], bool(row["passed"]))
        for row in list(rows) + list(market_rows)
    ]
    passed_count = sum(int(actual) for _, actual in definitives)
    probabilities = [
        (float(probability), int(actual))
        for probability, actual in definitives
        if probability is not None
    ]
    brier = None
    if probabilities:
        brier = sum((probability - actual) ** 2 for probability, actual in probabilities) / len(probabilities)

    def average(field: str) -> float | None:
        values = [float(row[field]) for row in rows if row[field] is not None]
        return round(sum(values) / len(values), 6) if values else None

    return {
        "as_of": as_of.isoformat(),
        "matured_count": total,
        "passed_count": passed_count,
        "hit_rate_pct": round(passed_count / total * 100, 6),
        "brier_score": round(brier, 6) if brier is not None else None,
        "calibrated_count": len(probabilities),
        "price_matured_count": len(rows),
        "market_matured_count": len(market_rows),
        "avg_stock_return_pct": average("stock_return_pct"),
        "avg_excess_return_pct": average("excess_return_pct"),
        "avg_max_drawdown_pct": average("max_drawdown_pct"),
        "records": records,
    }


def export_all(db: sqlite3.Connection) -> dict[str, Any]:
    records = db.execute(
        "SELECT snapshot_json, snapshot_sha256, recorded_at FROM research_records ORDER BY research_id"
    ).fetchall()
    outcomes = db.execute("SELECT * FROM outcomes ORDER BY research_id").fetchall()
    market_records = db.execute(
        "SELECT snapshot_json, snapshot_sha256, recorded_at FROM market_records ORDER BY research_id"
    ).fetchall()
    market_outcomes = db.execute(
        "SELECT * FROM market_outcomes ORDER BY research_id"
    ).fetchall()
    return {
        "schema_version": SCHEMA_VERSION,
        "records": [
            {
                "snapshot": json.loads(row["snapshot_json"]),
                "snapshot_sha256": row["snapshot_sha256"],
                "recorded_at": row["recorded_at"],
            }
            for row in records
        ],
        "outcomes": [
            {
                "research_id": row["research_id"],
                "outcome": json.loads(row["outcome_json"]),
                "outcome_sha256": row["outcome_sha256"],
                "recorded_at": row["recorded_at"],
                "metrics": {
                    "stock_return_pct": row["stock_return_pct"],
                    "benchmark_return_pct": row["benchmark_return_pct"],
                    "excess_return_pct": row["excess_return_pct"],
                    "max_drawdown_pct": row["max_drawdown_pct"],
                    "max_favorable_excursion_pct": row[
                        "max_favorable_excursion_pct"
                    ],
                    "max_adverse_excursion_pct": row[
                        "max_adverse_excursion_pct"
                    ],
                    "criterion_passed": bool(row["criterion_passed"]),
                    "falsifier_triggered": bool(row["falsifier_triggered"]),
                    "passed": bool(row["passed"]),
                },
            }
            for row in outcomes
        ],
        # 市场级记录单独成键，避免改动既有 records / outcomes 的语义与长度。
        "market_records": [
            {
                "snapshot": json.loads(row["snapshot_json"]),
                "snapshot_sha256": row["snapshot_sha256"],
                "recorded_at": row["recorded_at"],
            }
            for row in market_records
        ],
        "market_outcomes": [
            {
                "research_id": row["research_id"],
                "outcome": json.loads(row["outcome_json"]),
                "outcome_sha256": row["outcome_sha256"],
                "recorded_at": row["recorded_at"],
                "metrics": {
                    "observed_value": row["observed_value"],
                    "observed_unit": row["observed_unit"],
                    "criterion_passed": bool(row["criterion_passed"]),
                    "falsifier_triggered": bool(row["falsifier_triggered"]),
                    "passed": bool(row["passed"]),
                },
            }
            for row in market_outcomes
        ],
    }
