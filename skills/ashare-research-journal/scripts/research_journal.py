#!/usr/bin/env python3
"""Local, immutable A-share research snapshots and outcome reviews."""

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "1.0"
CRITERION_METRICS = {
    "stock_return_pct",
    "benchmark_return_pct",
    "excess_return_pct",
    "max_drawdown_pct",
    "max_favorable_excursion_pct",
    "max_adverse_excursion_pct",
}
OPERATORS = {"lt", "lte", "gt", "gte", "eq", "ne"}
DEFAULT_DB = Path.home() / ".ashare" / "research-journal.sqlite3"


class JournalError(ValueError):
    """Raised when journal input violates the immutable data contract."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise JournalError(f"无法读取输入：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise JournalError(f"输入不是有效JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise JournalError("输入顶层必须是object")
    return value


def parse_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise JournalError(f"{field} 必须是YYYY-MM-DD") from exc


def require_text(value: dict[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise JournalError(f"{field} 必须是非空字符串")
    return result


def validate_source(source: Any, field: str) -> None:
    if not isinstance(source, dict):
        raise JournalError(f"{field}.source 必须是object")
    for key in ("id", "name", "url"):
        if not isinstance(source.get(key), str) or not source[key].strip():
            raise JournalError(f"{field}.source.{key} 必须是非空字符串")
    parsed = urlparse(source["url"])
    is_web = parsed.scheme in {"http", "https"} and parsed.netloc
    is_file = parsed.scheme == "file" and parsed.path.startswith("/")
    if not (is_web or is_file):
        raise JournalError(f"{field}.source.url 必须是http(s)或绝对file URL")


def validate_evidence(
    evidence: Any,
    field: str,
    cutoff: date,
    require_value: bool = True,
) -> None:
    if not isinstance(evidence, dict):
        raise JournalError(f"{field} 必须是object")
    if require_value:
        raw_value = evidence.get("value")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise JournalError(f"{field}.value 必须是数值")
        if not math.isfinite(float(raw_value)) or float(raw_value) <= 0:
            raise JournalError(f"{field}.value 必须是正的有限数值")
        require_text(evidence, "unit")
    observed_at = parse_date(evidence.get("observed_at"), f"{field}.observed_at")
    published_at = parse_date(evidence.get("published_at"), f"{field}.published_at")
    if observed_at > cutoff:
        raise JournalError(f"{field}.observed_at 晚于截止日期")
    if published_at > cutoff:
        raise JournalError(f"{field}.published_at 晚于 as_of")
    try:
        datetime.fromisoformat(evidence.get("fetched_at"))
    except (TypeError, ValueError) as exc:
        raise JournalError(f"{field}.fetched_at 必须是ISO-8601 datetime") from exc
    validate_source(evidence.get("source"), field)


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise JournalError(f"schema_version 必须是{SCHEMA_VERSION}")
    for field in (
        "research_id",
        "code",
        "name",
        "market",
        "horizon_label",
        "thesis",
    ):
        require_text(snapshot, field)
    as_of = parse_date(snapshot.get("as_of"), "as_of")
    evaluation_date = parse_date(snapshot.get("evaluation_date"), "evaluation_date")
    if evaluation_date < as_of:
        raise JournalError("evaluation_date 不能早于 as_of")

    probability = snapshot.get("probability")
    if probability is not None:
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise JournalError("probability 必须是0到1数值")
        if not 0 <= float(probability) <= 1:
            raise JournalError("probability 必须在0到1之间")

    criterion = snapshot.get("criterion")
    if not isinstance(criterion, dict):
        raise JournalError("criterion 必须是object")
    if criterion.get("metric") not in CRITERION_METRICS:
        raise JournalError("criterion.metric 不受支持")
    if criterion.get("operator") not in OPERATORS:
        raise JournalError("criterion.operator 不受支持")
    raw_target = criterion.get("value")
    if isinstance(raw_target, bool) or not isinstance(raw_target, (int, float)):
        raise JournalError("criterion.value 必须是有限数值")
    if not math.isfinite(float(raw_target)):
        raise JournalError("criterion.value 必须是有限数值")

    baseline = snapshot.get("baseline")
    if not isinstance(baseline, dict) or "stock" not in baseline:
        raise JournalError("baseline.stock 必填")
    validate_evidence(baseline["stock"], "baseline.stock", as_of)
    if criterion["metric"] in {"benchmark_return_pct", "excess_return_pct"}:
        if "benchmark" not in baseline:
            raise JournalError("该criterion要求baseline.benchmark")
    if "benchmark" in baseline:
        require_text(snapshot, "benchmark_code")
        validate_evidence(baseline["benchmark"], "baseline.benchmark", as_of)

    for field in ("catalysts", "falsifiers"):
        items = snapshot.get(field)
        if not isinstance(items, list) or not all(
            isinstance(item, str) and item.strip() for item in items
        ):
            raise JournalError(f"{field} 必须是非空字符串数组")
    evidence_items = snapshot.get("evidence")
    if not isinstance(evidence_items, list):
        raise JournalError("evidence 必须是数组")
    for index, item in enumerate(evidence_items):
        if not isinstance(item, dict):
            raise JournalError(f"evidence[{index}] 必须是object")
        require_text(item, "claim")
        validate_evidence(item, f"evidence[{index}]", as_of, require_value=False)


def validate_path(
    path: Any,
    field: str,
    evaluation_date: date,
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(path, list) or len(path) < 2:
        raise JournalError(f"{field} 至少需要两个价格点")
    dates = []
    for index, point in enumerate(path):
        point_date = parse_date(
            point.get("observed_at") if isinstance(point, dict) else None,
            f"{field}[{index}].observed_at",
        )
        if point_date > evaluation_date:
            raise JournalError("价格路径超出 evaluation_date")
        validate_evidence(point, f"{field}[{index}]", evaluation_date)
        dates.append(point_date)
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise JournalError(f"{field} 日期必须严格递增")
    baseline_date = parse_date(baseline["observed_at"], "baseline.observed_at")
    if dates[0] != baseline_date:
        raise JournalError(f"{field} 首个日期必须等于基线观察日")
    if not math.isclose(float(path[0]["value"]), float(baseline["value"])):
        raise JournalError(f"{field} 首个价格必须等于基线价格")
    if path[0]["unit"] != baseline["unit"]:
        raise JournalError(f"{field} 单位必须与基线一致")
    return path


def validate_outcome(
    outcome: dict[str, Any],
    snapshot: dict[str, Any],
    review_as_of: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    if outcome.get("schema_version") != SCHEMA_VERSION:
        raise JournalError(f"schema_version 必须是{SCHEMA_VERSION}")
    if outcome.get("research_id") != snapshot["research_id"]:
        raise JournalError("outcome.research_id 与快照不一致")
    if outcome.get("evaluation_date") != snapshot["evaluation_date"]:
        raise JournalError("outcome.evaluation_date 与快照不一致")
    evaluation_date = parse_date(snapshot["evaluation_date"], "evaluation_date")
    if review_as_of < evaluation_date:
        raise JournalError("尚未到 evaluation_date，不能提前评分")
    baseline = snapshot["baseline"]
    stock_path = validate_path(
        outcome.get("stock_path"), "stock_path", evaluation_date, baseline["stock"]
    )
    benchmark_path = None
    if "benchmark" in baseline:
        benchmark_path = validate_path(
            outcome.get("benchmark_path"),
            "benchmark_path",
            evaluation_date,
            baseline["benchmark"],
        )
    falsifiers = outcome.get("falsifiers_triggered", [])
    if not isinstance(falsifiers, list) or not all(isinstance(item, str) for item in falsifiers):
        raise JournalError("falsifiers_triggered 必须是字符串数组")
    unknown_falsifiers = sorted(set(falsifiers) - set(snapshot["falsifiers"]))
    if unknown_falsifiers:
        raise JournalError(
            "falsifiers_triggered 包含快照未定义项：" + ", ".join(unknown_falsifiers)
        )
    return stock_path, benchmark_path


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


def show(db: sqlite3.Connection, research_id: str) -> dict[str, Any]:
    row = get_record(db, research_id)
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
    return result


def due(db: sqlite3.Connection, as_of: date) -> list[dict[str, Any]]:
    rows = db.execute(
        """
        SELECT r.research_id, r.code, r.name, r.evaluation_date
        FROM research_records r
        LEFT JOIN outcomes o ON o.research_id = r.research_id
        WHERE r.evaluation_date <= ? AND o.research_id IS NULL
        ORDER BY r.evaluation_date, r.research_id
        """,
        (as_of.isoformat(),),
    ).fetchall()
    return [dict(row) for row in rows]


def stats(db: sqlite3.Connection, as_of: date, code: str | None) -> dict[str, Any]:
    params: list[Any] = [as_of.isoformat()]
    where = "WHERE r.evaluation_date <= ?"
    if code:
        where += " AND r.code = ?"
        params.append(code)
    rows = db.execute(
        f"""
        SELECT r.probability, o.*
        FROM outcomes o JOIN research_records r ON r.research_id = o.research_id
        {where}
        ORDER BY r.research_id
        """,
        params,
    ).fetchall()
    if not rows:
        return {
            "as_of": as_of.isoformat(),
            "matured_count": 0,
            "passed_count": 0,
            "hit_rate_pct": None,
            "brier_score": None,
        }
    passed_count = sum(int(row["passed"]) for row in rows)
    probabilities = [
        (float(row["probability"]), int(row["passed"]))
        for row in rows
        if row["probability"] is not None
    ]
    brier = None
    if probabilities:
        brier = sum((probability - actual) ** 2 for probability, actual in probabilities) / len(probabilities)

    def average(field: str) -> float | None:
        values = [float(row[field]) for row in rows if row[field] is not None]
        return round(sum(values) / len(values), 6) if values else None

    return {
        "as_of": as_of.isoformat(),
        "matured_count": len(rows),
        "passed_count": passed_count,
        "hit_rate_pct": round(passed_count / len(rows) * 100, 6),
        "brier_score": round(brier, 6) if brier is not None else None,
        "calibrated_count": len(probabilities),
        "avg_stock_return_pct": average("stock_return_pct"),
        "avg_excess_return_pct": average("excess_return_pct"),
        "avg_max_drawdown_pct": average("max_drawdown_pct"),
    }


def export_all(db: sqlite3.Connection) -> dict[str, Any]:
    records = db.execute(
        "SELECT snapshot_json, snapshot_sha256, recorded_at FROM research_records ORDER BY research_id"
    ).fetchall()
    outcomes = db.execute("SELECT * FROM outcomes ORDER BY research_id").fetchall()
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
    }


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A股研究结论事后复盘")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="本地SQLite路径")
    sub = parser.add_subparsers(dest="command", required=True)
    record_parser = sub.add_parser("record", help="冻结研究快照")
    record_parser.add_argument("--input", type=Path, required=True)
    show_parser = sub.add_parser("show", help="查看快照和结果")
    show_parser.add_argument("--id", required=True)
    due_parser = sub.add_parser("due", help="列出到期未复核记录")
    due_parser.add_argument("--as-of", required=True)
    observe_parser = sub.add_parser("observe", help="追加到期结果")
    observe_parser.add_argument("--id", required=True)
    observe_parser.add_argument("--input", type=Path, required=True)
    observe_parser.add_argument("--as-of", required=True)
    stats_parser = sub.add_parser("stats", help="统计成熟记录")
    stats_parser.add_argument("--as-of", required=True)
    stats_parser.add_argument("--code")
    sub.add_parser("export", help="导出全部可复核JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        with connect(args.db) as db:
            if args.command == "record":
                result = record(db, load_json(args.input))
            elif args.command == "show":
                result = show(db, args.id)
            elif args.command == "due":
                result = due(db, parse_date(args.as_of, "as-of"))
            elif args.command == "observe":
                result = observe(
                    db,
                    args.id,
                    load_json(args.input),
                    parse_date(args.as_of, "as-of"),
                )
            elif args.command == "stats":
                result = stats(db, parse_date(args.as_of, "as-of"), args.code)
            else:
                result = export_all(db)
        print_json(result)
        return 0
    except JournalError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"错误：SQLite失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
