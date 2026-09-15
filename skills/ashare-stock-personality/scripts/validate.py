#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输入契约校验与派生结果自洽校验。

两条硬线：
  1. 阈值必须由输入显式声明。缺任何一个切点都直接拒收，不允许回退到隐藏默认。
  2. 缺证据一律 None，不许用 0 顶替。任何「没有证据却给出了数值」都会在这里被拦下。
"""

import hashlib
import json

from pathlib import Path
from typing import Any

from schema import (
    ARCHETYPE_ORDER,
    ARCHETYPE_THRESHOLD_KEYS,
    BOARD_KEYS,
    CAPACITY_METRICS,
    DIMENSIONS,
    PersonalityError,
    QUADRANT_LABELS,
    SCHEMA_VERSION,
    THRESHOLD_KEYS,
    parse_date,
    require_number,
    require_text,
)

CODE_RE_LENGTH = 6


def load_input(path: Path) -> tuple[dict[str, Any], str]:
    raw = Path(path).read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise PersonalityError(f"输入不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise PersonalityError("输入顶层必须是对象")
    return data, hashlib.sha256(raw).hexdigest()


def _require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PersonalityError(f"{field} 必须是对象")
    return value


def _require_list(value: Any, field: str) -> list:
    if not isinstance(value, list):
        raise PersonalityError(f"{field} 必须是数组")
    return value


def validate_thresholds(raw: Any) -> dict[str, Any]:
    thresholds = _require_object(raw, "thresholds")
    missing = [key for key in THRESHOLD_KEYS if key not in thresholds]
    if missing:
        raise PersonalityError(
            f"thresholds 缺少必填键：{', '.join(missing)}。阈值必须由输入显式声明，不回退默认值。"
        )

    limits = _require_object(thresholds["limit_up_pct"], "thresholds.limit_up_pct")
    absent = [board for board in BOARD_KEYS if board not in limits]
    if absent:
        raise PersonalityError(f"thresholds.limit_up_pct 缺少板块：{', '.join(absent)}")
    clean_limits = {
        board: require_number(limits[board], f"thresholds.limit_up_pct.{board}", 0.5, 30.0)
        for board in BOARD_KEYS
    }

    weights = _require_object(thresholds["score_weights"], "thresholds.score_weights")
    absent_weights = [dim for dim in DIMENSIONS if dim not in weights]
    if absent_weights:
        raise PersonalityError(f"thresholds.score_weights 缺少维度：{', '.join(absent_weights)}")
    clean_weights = {
        dim: require_number(weights[dim], f"thresholds.score_weights.{dim}", 0.0, 1.0)
        for dim in DIMENSIONS
    }
    if sum(clean_weights.values()) <= 0:
        raise PersonalityError("thresholds.score_weights 合计必须为正")

    cuts = _require_object(thresholds["archetype"], "thresholds.archetype")
    absent_cuts = [key for key in ARCHETYPE_THRESHOLD_KEYS if key not in cuts]
    if absent_cuts:
        raise PersonalityError(f"thresholds.archetype 缺少切点：{', '.join(absent_cuts)}")
    clean_cuts: dict[str, Any] = {}
    for key in ARCHETYPE_THRESHOLD_KEYS:
        if key == "legend_streak":
            streak = require_number(cuts[key], "thresholds.archetype.legend_streak", 2, 20)
            if streak != int(streak):
                raise PersonalityError("thresholds.archetype.legend_streak 必须是整数")
            clean_cuts[key] = int(streak)
        else:
            clean_cuts[key] = require_number(cuts[key], f"thresholds.archetype.{key}", 0.0, 100.0)
    if not clean_cuts["low"] <= clean_cuts["mid"] <= clean_cuts["high"]:
        raise PersonalityError(
            "thresholds.archetype 必须满足 low ≤ mid ≤ high，否则原型规则互相矛盾"
        )

    return {
        "limit_up_pct": clean_limits,
        "spike_pct": require_number(thresholds["spike_pct"], "thresholds.spike_pct", 0.5, 30.0),
        "dump_drawdown_pct": require_number(
            thresholds["dump_drawdown_pct"], "thresholds.dump_drawdown_pct", -50.0, -1.0
        ),
        "dump_window_days": int(
            require_number(thresholds["dump_window_days"], "thresholds.dump_window_days", 1, 20)
        ),
        "lhb_net_min_cny": require_number(
            thresholds["lhb_net_min_cny"], "thresholds.lhb_net_min_cny"
        ),
        "score_weights": clean_weights,
        "archetype": clean_cuts,
    }


def _validate_spike(item: Any, code: str, index: int, threshold: float) -> dict[str, Any]:
    field = f"stocks[{code}].spikes[{index}]"
    spike = _require_object(item, field)
    clean: dict[str, Any] = {
        "date": parse_date(spike.get("date"), f"{field}.date").isoformat(),
        "change_pct": require_number(spike.get("change_pct"), f"{field}.change_pct", -35.0, 45.0),
        "limit_up": bool(spike.get("limit_up")),
        "streak": int(require_number(spike.get("streak", 0), f"{field}.streak", 0, 30)),
    }
    for key in ("next_day_pct", "drawdown_nd_pct"):
        if spike.get(key) is not None:
            clean[key] = require_number(spike[key], f"{field}.{key}", -100.0, 200.0)
    if clean["limit_up"] and clean["change_pct"] < threshold - 3.0:
        raise PersonalityError(
            f"{field} 标为涨停但涨跌幅 {clean['change_pct']} 明显低于该板块阈值 {threshold}"
        )
    return clean


def validate_stocks(raw: Any, window: dict[str, Any], thresholds: dict[str, Any], capacity_metric: str):
    rows = _require_list(raw, "stocks")
    if not rows:
        raise PersonalityError("stocks 不能为空")
    seen: set[str] = set()
    cleaned: list[dict[str, Any]] = []
    for item in rows:
        stock = _require_object(item, "stocks[]")
        code = require_text(stock.get("code"), "stocks[].code")
        if len(code) != CODE_RE_LENGTH or not code.isdigit():
            raise PersonalityError(f"stocks[].code 必须是 6 位数字：{code}")
        if code in seen:
            raise PersonalityError(f"stocks[].code 重复：{code}")
        seen.add(code)
        board = require_text(stock.get("board"), f"stocks[{code}].board")
        if board not in BOARD_KEYS:
            raise PersonalityError(
                f"stocks[{code}].board 必须是 {BOARD_KEYS} 之一，实际为 {board}"
            )
        entry: dict[str, Any] = {
            "code": code,
            "name": require_text(stock.get("name"), f"stocks[{code}].name"),
            "board": board,
            "sector": stock.get("sector"),
            "bars": int(require_number(stock.get("bars"), f"stocks[{code}].bars", 1)),
            "first_bar": stock.get("first_bar"),
            "last_bar": stock.get("last_bar"),
            "spikes": [
                _validate_spike(item, code, index, thresholds["limit_up_pct"][board])
                for index, item in enumerate(_require_list(stock.get("spikes"), f"stocks[{code}].spikes"))
            ],
            "lhb": [],
        }
        for index, item in enumerate(_require_list(stock.get("lhb"), f"stocks[{code}].lhb")):
            record = _require_object(item, f"stocks[{code}].lhb[{index}]")
            clean_record = {"date": parse_date(record.get("date"), "lhb.date").isoformat()}
            if record.get("net_amt_cny") is not None:
                clean_record["net_amt_cny"] = require_number(
                    record["net_amt_cny"], "lhb.net_amt_cny"
                )
            for horizon in (1, 2, 5, 10):
                key = f"d{horizon}_pct"
                if record.get(key) is not None:
                    clean_record[key] = require_number(record[key], f"lhb.{key}", -100.0, 500.0)
            entry["lhb"].append(clean_record)

        capacity = stock.get(capacity_metric)
        entry["capacity"] = None if capacity is None else require_number(
            capacity, f"stocks[{code}].{capacity_metric}", 0.0
        )
        for key in ("volatility_ann_pct", "ret_60d_pct", "ret_20d_pct", "ret_5d_pct", "float_cap_cny"):
            if stock.get(key) is not None:
                entry[key] = require_number(stock[key], f"stocks[{code}].{key}")
        for spike in entry["spikes"]:
            if not (window["start"] <= spike["date"] <= window["end"]):
                raise PersonalityError(
                    f"stocks[{code}] 的异动日 {spike['date']} 落在窗口 "
                    f"{window['start']} ~ {window['end']} 之外"
                )
        cleaned.append(entry)
    if not any(row["capacity"] is not None for row in cleaned):
        raise PersonalityError(f"流动性口径 {capacity_metric} 在全部股票上都缺失，无法给出容量维度")
    return cleaned


def validate_input(data: dict[str, Any]) -> dict[str, Any]:
    version = require_text(data.get("schema_version"), "schema_version")
    if version != SCHEMA_VERSION:
        raise PersonalityError(
            f"schema_version 必须是 {SCHEMA_VERSION}，实际为 {version}（本技能不做版本升级）"
        )
    as_of = parse_date(data.get("as_of"), "as_of")
    raw_window = _require_object(data.get("window"), "window")
    window = {
        "start": parse_date(raw_window.get("start"), "window.start").isoformat(),
        "end": parse_date(raw_window.get("end"), "window.end").isoformat(),
        "trading_days": int(require_number(raw_window.get("trading_days"), "window.trading_days", 5)),
    }
    if not (window["start"] <= window["end"] <= as_of.isoformat()):
        raise PersonalityError("window 必须满足 start ≤ end ≤ as_of")
    capacity_metric = require_text(data.get("capacity_metric"), "capacity_metric")
    if capacity_metric not in CAPACITY_METRICS:
        raise PersonalityError(
            f"capacity_metric 必须是 {CAPACITY_METRICS} 之一，实际为 {capacity_metric}"
        )
    thresholds = validate_thresholds(data.get("thresholds"))
    stocks = validate_stocks(data.get("stocks"), window, thresholds, capacity_metric)

    universe = _require_object(data.get("universe"), "universe")
    declared = int(require_number(universe.get("count"), "universe.count", 1))
    if declared != len(stocks):
        raise PersonalityError(
            f"universe.count 声明 {declared}，但 stocks 有 {len(stocks)} 条，两者必须一致"
        )
    return {
        "as_of": as_of.isoformat(),
        "window": window,
        "capacity_metric": capacity_metric,
        "thresholds": thresholds,
        "stocks": stocks,
        "universe": {
            "name": require_text(universe.get("name"), "universe.name"),
            "description": str(universe.get("description") or ""),
            "count": declared,
            "selection_rule": str(universe.get("selection_rule") or ""),
            "excluded_count": int(universe.get("excluded_count") or 0),
        },
        "sources": _require_list(data.get("sources") or [], "sources"),
    }


# --- 派生结果自洽 -----------------------------------------------------------


def validate_derived(derived: dict[str, Any], thresholds: dict[str, Any]) -> None:
    """校验派生层：维度区间、原型合法性、矩阵与象限的计数守恒。"""
    records = derived["stocks"]
    if not records:
        raise PersonalityError("派生结果为空")

    for row in records:
        for dim in DIMENSIONS:
            value = row.get(dim)
            if value is None:
                continue
            if not 0.0 <= float(value) <= 100.0:
                raise PersonalityError(f"{row['code']} 的 {dim} 越界：{value}")
            if abs(float(value) - round(float(value), 4)) > 1e-9:
                raise PersonalityError(f"{row['code']} 的 {dim} 小数位超过 4 位")
        has_all = all(row.get(dim) is not None for dim in DIMENSIONS)
        composite = row.get("composite")
        if has_all and composite is None:
            raise PersonalityError(f"{row['code']} 六维齐全却没给综合分")
        if not has_all and composite is not None:
            raise PersonalityError(
                f"{row['code']} 有维度缺失却给出了综合分——缺证据不得当 0 用"
            )
        if row["archetype"] not in ARCHETYPE_ORDER:
            raise PersonalityError(f"{row['code']} 原型非法：{row['archetype']}")
        if not row.get("archetype_reason"):
            raise PersonalityError(f"{row['code']} 缺少归类依据")
        if row.get("quadrant") is not None and row["quadrant"] not in QUADRANT_LABELS:
            raise PersonalityError(f"{row['code']} 象限非法：{row['quadrant']}")

    matrix = derived["archetype_sector_matrix"]
    cell_total = sum(cell["count"] for row in matrix["cells"] for cell in row["cells"])
    if cell_total != len(records):
        raise PersonalityError(
            f"板块×原型矩阵合计 {cell_total} 与股票池 {len(records)} 不一致"
        )
    for row in matrix["cells"]:
        for cell in row["cells"]:
            # 单元格可能「有样本但样本全都缺证据」——此时均值必须为 None。
            # 只有在至少有样本能算出综合分时，均值才必须给出。
            if cell["count"] == 0 and cell.get("scored_count", 0):
                raise PersonalityError(
                    f"{row['archetype']}×{cell['sector']} 无样本却有可计分样本数"
                )
            if cell.get("scored_count", 0) == 0 and cell["mean_composite"] is not None:
                raise PersonalityError("无可计分样本的均值必须为 None，不能用 0 占位")
            if cell.get("scored_count", 0) > 0 and cell["mean_composite"] is None:
                raise PersonalityError(f"{row['archetype']}×{cell['sector']} 有可计分样本却无均值")

    sectors = derived["sector_table"]
    if sum(item["count"] for item in sectors) != len(records):
        raise PersonalityError("板块表的只数合计与股票池不一致")

    quadrants = derived["map"]["quadrant_counts"]
    if sum(quadrants.values()) != sum(1 for row in records if row.get("quadrant")):
        raise PersonalityError("象限计数与有象限的个股数不一致")

    capacity_metric = derived["capacity_metric"]
    if capacity_metric not in CAPACITY_METRICS:
        raise PersonalityError(f"派生层容量口径非法：{capacity_metric}")
    if thresholds["archetype"]["low"] > thresholds["archetype"]["high"]:
        raise PersonalityError("原型切点自相矛盾")
