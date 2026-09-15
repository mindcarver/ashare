#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""股性派生层：六维 → 综合分 → 原型 → 象限 → 板块×原型矩阵 → 股性地图 → 信号。

编排纪律：
  - 只读 validate.py 归一化后的输入与显式阈值，不引入任何新默认值。
  - 板块×原型矩阵与板块表的只数必须与股票池守恒（validate.validate_derived 会复核）。
  - 信号只描述结构，不给方向、不给动作、不给价位。
"""

from typing import Any

from archetypes import classify, quadrant
from metrics import composite_score, raw_features, score_dimensions
from schema import (
    ARCHETYPE_LABELS,
    ARCHETYPE_ORDER,
    DIMENSIONS,
    QUADRANT_LABELS,
)

MATRIX_SECTOR_LIMIT = 12
OTHER_SECTOR = "其他行业"
UNKNOWN_SECTOR = "未知行业"
# 东财快照里停牌/异常股会把行业字段返回成占位符，这些都不是行业名。
SECTOR_PLACEHOLDERS = {"", "-", "--", "—", "n", "N", "null", "None"}
# 板块排序信号只在样本量够时才报，避免 1 只股票撑起的「板块第一」被当成结论。
SECTOR_RANK_MIN_COUNT = 3


def _sector_name(raw: Any) -> str:
    text = str(raw).strip() if raw is not None else ""
    if text in SECTOR_PLACEHOLDERS:
        return UNKNOWN_SECTOR
    return text


def _mean(values: list[float]) -> float | None:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 4)


def _median(values: list[float]) -> float | None:
    numbers = sorted(float(value) for value in values if value is not None)
    if not numbers:
        return None
    middle = len(numbers) // 2
    if len(numbers) % 2:
        return round(numbers[middle], 4)
    return round((numbers[middle - 1] + numbers[middle]) / 2, 4)


def derive(sections: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    stocks = sections["stocks"]
    window = sections["window"]
    thresholds = sections["thresholds"]
    capacity_metric = sections["capacity_metric"]

    features = []
    for stock in stocks:
        row = raw_features(stock, window["trading_days"], thresholds)
        row.update(
            {
                "code": stock["code"],
                "name": stock["name"],
                "board": stock["board"],
                "sector": _sector_name(stock.get("sector")),
                "bars": stock["bars"],
                "last_bar": stock.get("last_bar"),
            }
        )
        features.append(row)
    score_dimensions(features)

    weights = thresholds["score_weights"]
    for row in features:
        row["composite"] = composite_score(row, weights)
        archetype, reason = classify(row, thresholds)
        row["archetype"] = archetype
        row["archetype_reason"] = reason

    d1_median = _median([row.get("d1") for row in features])
    d2_median = _median([row.get("d2") for row in features])
    for row in features:
        row["quadrant"] = quadrant(row, d1_median, d2_median)
        row["selected_per_year"] = row["selected_days_per_year"]

    records = sorted(
        features,
        key=lambda row: (-(row["composite"] if row["composite"] is not None else -1), row["code"]),
    )

    derived: dict[str, Any] = {
        "capacity_metric": capacity_metric,
        "window": dict(window),
        "universe": sections["universe"],
        "thresholds": thresholds,
        "stocks": records,
        "overview": _overview(records, window, capacity_metric),
        "archetype_table": _archetype_table(records),
        "archetype_sector_matrix": _matrix(records),
        "sector_table": _sector_table(records),
        "map": _map(records, d1_median, d2_median, capacity_metric),
        "caveats": _caveats(capacity_metric),
    }
    return derived, _signals(derived)


def _overview(records: list[dict[str, Any]], window: dict[str, Any], capacity_metric: str) -> dict[str, Any]:
    scored = [row for row in records if row["composite"] is not None]
    return {
        "total": len(records),
        "scored": len(scored),
        "unscored": len(records) - len(scored),
        "mean_composite": _mean([row["composite"] for row in scored]),
        "mean_next_day_pct": _mean([row.get("avg_next_day_pct") for row in records]),
        "mean_bury_rate_pct": _mean([row.get("bury_rate_pct") for row in records]),
        "mean_selected_per_year": _mean([row.get("selected_per_year") for row in records]),
        "scored_share_pct": round(len(scored) / len(records) * 100, 2) if records else None,
        "window_start": window["start"],
        "window_end": window["end"],
        "trading_days": window["trading_days"],
        "capacity_metric": capacity_metric,
    }


def _archetype_table(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    table = []
    for archetype in ARCHETYPE_ORDER:
        rows = [row for row in records if row["archetype"] == archetype]
        table.append(
            {
                "archetype": archetype,
                "label": ARCHETYPE_LABELS[archetype],
                "count": len(rows),
                "share_pct": round(len(rows) / len(records) * 100, 2) if records else None,
                "mean_composite": _mean([row["composite"] for row in rows]),
                "mean_next_day_pct": _mean([row.get("avg_next_day_pct") for row in rows]),
                "mean_bury_rate_pct": _mean([row.get("bury_rate_pct") for row in rows]),
                "mean_selected_per_year": _mean([row.get("selected_per_year") for row in rows]),
            }
        )
    return table


def _matrix(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for row in records:
        counts[row["sector"]] = counts.get(row["sector"], 0) + 1
    top = [name for name, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
    kept = top[:MATRIX_SECTOR_LIMIT]
    columns = kept + ([OTHER_SECTOR] if len(top) > len(kept) else [])
    grouped = {name: name if name in kept else OTHER_SECTOR for name in counts}

    rows = []
    for archetype in ARCHETYPE_ORDER:
        cells = []
        for column in columns:
            members = [
                row
                for row in records
                if row["archetype"] == archetype and grouped[row["sector"]] == column
            ]
            cells.append(
                {
                    "sector": column,
                    "count": len(members),
                    "scored_count": sum(1 for row in members if row["composite"] is not None),
                    "mean_composite": _mean([row["composite"] for row in members]),
                }
            )
        rows.append({"archetype": archetype, "label": ARCHETYPE_LABELS[archetype], "cells": cells})
    return {
        "sectors": columns,
        "collapsed_sector_count": max(0, len(top) - len(kept)),
        "cells": rows,
    }


def _sector_table(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        grouped.setdefault(row["sector"], []).append(row)
    table = []
    for sector, rows in grouped.items():
        table.append(
            {
                "sector": sector,
                "count": len(rows),
                "scored_count": sum(1 for row in rows if row["composite"] is not None),
                "mean_composite": _mean([row["composite"] for row in rows]),
                "mean_next_day_pct": _mean([row.get("avg_next_day_pct") for row in rows]),
                "mean_bury_rate_pct": _mean([row.get("bury_rate_pct") for row in rows]),
                "mean_selected_per_year": _mean([row.get("selected_per_year") for row in rows]),
                "legend_count": sum(1 for row in rows if row["archetype"] == "wire_legend"),
                "trap_count": sum(1 for row in rows if row["archetype"] == "bury_trap"),
            }
        )
    return sorted(
        table,
        key=lambda item: (-(item["mean_composite"] if item["mean_composite"] is not None else -1),
                          -item["count"], item["sector"]),
    )


def _map(records, d1_median, d2_median, capacity_metric) -> dict[str, Any]:
    points = []
    for row in records:
        if row.get("d1") is None or row.get("d2") is None:
            continue
        points.append(
            {
                "code": row["code"],
                "name": row["name"],
                "x": row["d1"],
                "y": row["d2"],
                "size": row.get("capacity"),
                "danger": row.get("d3"),
                "archetype": row["archetype"],
                "quadrant": row.get("quadrant"),
            }
        )
    counts = {key: 0 for key in QUADRANT_LABELS}
    for point in points:
        if point["quadrant"]:
            counts[point["quadrant"]] += 1
    capacities = [point["size"] for point in points if point["size"] is not None]
    return {
        "points": points,
        "quadrant_counts": counts,
        "x_median": d1_median,
        "y_median": d2_median,
        "x_label": f"D1 异动基因（中位切点 {d1_median}）",
        "y_label": f"D2 溢价质量（中位切点 {d2_median}）",
        "size_metric": capacity_metric,
        "size_min": min(capacities) if capacities else None,
        "size_max": max(capacities) if capacities else None,
        "danger_label": "D3 埋人风险（越深越危险）",
        "plotted": len(points),
        "skipped": len(records) - len(points),
    }


def _caveats(capacity_metric: str) -> list[str]:
    notes = [
        "维度分是**池内百分位**，只表示在这批股票里的相对位置，不是绝对好坏，换池子必须重算。",
        "涨跌幅由前复权序列的相邻收盘价算出：除权日的涨跌幅会失真，该日若真实涨停可能被低估。",
        "最高连板按相邻交易日判定，遇到停牌即断板；连板门槛与板块无关，ST 与北交所涨跌幅只有 5%、更易连板，因此高连板样本会偏向 ST，解释时必须说明。",
        "龙虎榜的 D1/D2/D5/D10 是上榜后的事后涨跌幅，只用于统计已发生的历史事件，不用于当下判断。",
        "「被选中次数/年」按全部龙虎榜上榜日与异动日去重计算；龙虎榜净额门槛只作用于资金关注度维度，不改变被选中次数。",
        "原型规则按固定优先级首个命中即归类；普通型代表「未获足够证据归类」，不代表质地普通。",
        "埋人率与溢价质量只在有异动事件的样本上计算，事件数少的个股统计噪声大。",
        "板块归属取快照日的东财行业，历史上行业分类可能变动；同一只股票在不同时期可能属不同板块。",
    ]
    if capacity_metric == "turnover_avg_pct":
        notes.append(
            "流动性容量用的是**日均换手率**口径：成交量÷流通股本，流通股本取快照日，"
            "属透明计算，与交易所披露的成交额不是同一证据等级；换手率高代表流通盘被频繁交易，"
            "并不等于体量大。"
        )
    elif capacity_metric == "float_cap_cny":
        notes.append(
            "流动性容量用的是**流通市值**口径（东财快照直接披露），代理「装得下多少成交」；"
            "这是体量代理，不是实际成交额。"
        )
    else:
        notes.append("流动性容量用的是日均成交额口径（交易所级证据）。")
    return notes


def _signals(derived: dict[str, Any]) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    records = derived["stocks"]
    counts = derived["map"]["quadrant_counts"]
    total = derived["overview"]["total"]

    hh = counts.get("hh", 0)
    hl = counts.get("hl", 0)
    signals.append(
        {
            "kind": "quadrant_structure",
            "text": (
                f"股性地图分布：高异动·高溢价 {hh} 只、高异动·低溢价 {hl} 只，"
                f"高异动样本共 {hh + hl} 只（占 {round((hh + hl) / total * 100, 2)}%）。"
                "低溢价一侧代表被选中频繁但次日承接偏弱的结构。"
            ),
            "evidence": "map.points + 全样本 d1/d2 中位切点",
        }
    )

    traps = [row for row in records if row["archetype"] == "bury_trap"]
    if traps:
        sectors = {}
        for row in traps:
            sectors[row["sector"]] = sectors.get(row["sector"], 0) + 1
        top = sorted(sectors.items(), key=lambda item: (-item[1], item[0]))[:3]
        detail = "、".join(f"{name} {count} 只" for name, count in top)
        signals.append(
            {
                "kind": "bury_concentration",
                "text": (
                    f"高埋人风险型 {len(traps)} 只，集中在：{detail}。"
                    f"该原型要求埋人风险进入池内前段且溢价质量低于 {derived['thresholds']['archetype']['low']:g} 分位。"
                ),
                "evidence": "archetype == bury_trap",
            }
        )

    weakest = [
        row
        for row in records
        if row["archetype"] == "bury_trap" and (row.get("avg_next_day_pct") or 0) < 0
    ]
    if weakest:
        signals.append(
            {
                "kind": "negative_premium",
                "text": (
                    f"高埋人风险型中有 {len(weakest)} 只异动后次日平均涨跌幅为负"
                    f"（最低 {min(row['avg_next_day_pct'] for row in weakest):+.2f}%），"
                    "属结构描述，不构成任何操作判断。"
                ),
                "evidence": "bury_trap ∩ avg_next_day_pct < 0",
            }
        )

    legends = [row for row in records if row["archetype"] == "wire_legend"]
    if legends:
        best = max(legends, key=lambda row: row.get("max_streak") or 0)
        signals.append(
            {
                "kind": "legend_streak",
                "text": (
                    f"连板妖股型 {len(legends)} 只，窗口内最高连板为 {best['name']}"
                    f"（{best['code']}）的 {best['max_streak']} 板。"
                ),
                "evidence": "max_streak ≥ 连板阈值",
            }
        )

    unscored = [row for row in records if row["composite"] is None]
    if unscored:
        signals.append(
            {
                "kind": "coverage",
                "text": (
                    f"{len(unscored)} 只因维度缺证据未给综合分（多为异动事件样本不足），"
                    "已在明细表标为空缺，未用 0 顶替。"
                ),
                "evidence": "composite is None",
            }
        )

    ordered = [
        row
        for row in derived["sector_table"]
        if row["mean_composite"] is not None and row["count"] >= SECTOR_RANK_MIN_COUNT
    ]
    if ordered:
        best = ordered[0]
        signals.append(
            {
                "kind": "sector_ranking",
                "text": (
                    f"板块平均股性分最高为 {best['sector']}（{best['mean_composite']} 分，"
                    f"{best['count']} 只）；仅统计样本 ≥ {SECTOR_RANK_MIN_COUNT} 只的板块，"
                    "这是池内相对排序，不是板块评级。"
                ),
                "evidence": f"sector_table 排序首行 ∩ count ≥ {SECTOR_RANK_MIN_COUNT}",
            }
        )
    return signals
