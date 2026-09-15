#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原型分类与象限划分。

两条纪律：
  1. 规则按 ARCHETYPE_ORDER 顺序求值，**首个命中即归类**，顺序是口径的一部分。
  2. 所有切点来自输入显式声明的 thresholds["archetype"]，本模块没有任何隐藏默认。
     缺证据（维度为 None）时不猜测，落到普通型——普通型是「未获足够证据归类」，
     不是「质量一般」。
"""

from typing import Any

from schema import ARCHETYPE_LABELS, PersonalityError


RULE_ORDER = (
    "wire_legend",
    "hot_volatile",
    "emotional_active",
    "bury_trap",
    "trend_slow_bull",
    "weight_steady",
)


def _number(row: dict[str, Any], key: str):
    value = row.get(key)
    return None if value is None else float(value)


def classify(row: dict[str, Any], thresholds: dict[str, Any]) -> tuple[str, str]:
    """返回 (原型键, 归类依据)。依据是给人看的、可复核的一行说明。"""
    cuts = thresholds["archetype"]
    high = float(cuts["high"])
    mid = float(cuts["mid"])
    low = float(cuts["low"])
    legend_streak = int(cuts["legend_streak"])
    capacity_high = float(cuts["capacity_high"])
    elastic_high = float(cuts["elastic_high"])
    trend_high = float(cuts["trend_high"])

    d1, d2, d3, d4 = _number(row, "d1"), _number(row, "d2"), _number(row, "d3"), _number(row, "d4")
    elasticity, trend = _number(row, "_elasticity"), _number(row, "_trend")
    streak = int(row.get("max_streak") or 0)
    ret_60d = _number(row, "ret_60d_pct")

    if streak >= legend_streak:
        return "wire_legend", f"窗口内最高连板 {streak} 板，达到连板阈值 {legend_streak}"

    if d1 is not None and elasticity is not None and d2 is not None:
        if d1 >= high and elasticity >= elastic_high and d2 < mid:
            return (
                "hot_volatile",
                f"异动基因 {d1:.1f}（≥{high:g}）且弹性 {elasticity:.1f}"
                f"（≥{elastic_high:g}），但溢价质量 {d2:.1f} 低于中位切点 {mid:g}",
            )

    if d1 is not None and d2 is not None and d1 >= high and d2 >= mid:
        if d3 is None or d3 < high:
            return (
                "emotional_active",
                f"异动基因 {d1:.1f}（≥{high:g}）且溢价质量 {d2:.1f}（≥{mid:g}），"
                f"埋人风险未达高位",
            )

    if d3 is not None and d2 is not None and d3 >= high and d2 < low:
        return (
            "bury_trap",
            f"埋人风险 {d3:.1f}（≥{high:g}）且溢价质量 {d2:.1f}（<{low:g}）："
            f"被选中后回撤深度在全池前列",
        )

    if trend is not None and trend >= trend_high and (ret_60d or 0) > 0:
        if d1 is None or d1 < mid:
            return (
                "trend_slow_bull",
                f"趋势分位 {trend:.1f}（≥{trend_high:g}）、60日区间 {ret_60d:+.2f}%，"
                f"异动频率未达中位切点",
            )

    if d4 is not None and elasticity is not None:
        if d4 >= capacity_high and elasticity < low and (d1 is None or d1 < mid):
            return (
                "weight_steady",
                f"流动性容量 {d4:.1f}（≥{capacity_high:g}）但弹性 {elasticity:.1f}"
                f"（<{low:g}）且异动频率低",
            )

    return "ordinary", "未命中任何原型规则（证据不足或落在各项切点之间）"


def quadrant(row: dict[str, Any], d1_median: float | None, d2_median: float | None) -> str | None:
    """股性地图象限：以全样本 d1/d2 中位数切分。任一分缺失即不给象限。"""
    d1, d2 = _number(row, "d1"), _number(row, "d2")
    if d1 is None or d2 is None or d1_median is None or d2_median is None:
        return None
    horizontal = "h" if d1 >= d1_median else "l"
    vertical = "h" if d2 >= d2_median else "l"
    return horizontal + vertical


def label(archetype: str) -> str:
    if archetype not in ARCHETYPE_LABELS:
        raise PersonalityError(f"未知原型：{archetype}")
    return ARCHETYPE_LABELS[archetype]
