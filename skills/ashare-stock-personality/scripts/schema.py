#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""股性分析的契约常量与断言工具。

本模块只放「口径」：维度定义、原型名称与优先级、象限名称、阈值必填键、
以及最小断言工具。所有计算在 metrics.py / archetypes.py，编排在 derive.py。
"""

import re

from datetime import date, datetime

import _paths  # noqa: F401  确保 skills/_shared 在 sys.path 上


SCHEMA_VERSION = "1.0"

# 六维：全部归一化到 0-100，方向统一为「该属性越强分越高」。
# d3 是风险维度，分越高代表「埋人风险越大」，进入综合分时取 (100 - d3)。
DIMENSIONS = ("d1", "d2", "d3", "d4", "d5", "d6")

DIMENSION_LABELS = {
    "d1": "D1 异动基因",
    "d2": "D2 溢价质量",
    "d3": "D3 埋人风险",
    "d4": "D4 流动性容量",
    "d5": "D5 资金关注度",
    "d6": "D6 弹性与趋势",
}

DIMENSION_QUESTIONS = {
    "d1": "多久被拉一次、连得上吗",
    "d2": "拉完次日给不给溢价",
    "d3": "追进去后回撤有多深",
    "d4": "装得下多少成交",
    "d5": "常被资金选中吗",
    "d6": "涨得多猛、守不守得住",
}

# 风险维度的进入方向：综合分里用 100 - d3。
RISK_DIMENSIONS = ("d3",)

# 原型：按元组顺序做「首个命中即归类」，顺序本身是口径的一部分，不得重排。
ARCHETYPE_ORDER = (
    "wire_legend",
    "hot_volatile",
    "emotional_active",
    "bury_trap",
    "trend_slow_bull",
    "weight_steady",
    "ordinary",
)

ARCHETYPE_LABELS = {
    "wire_legend": "连板妖股型",
    "hot_volatile": "高波动题材型",
    "emotional_active": "情绪活跃型",
    "bury_trap": "高埋人风险型",
    "trend_slow_bull": "趋势慢牛型",
    "weight_steady": "权重稳重型",
    "ordinary": "普通型",
}

# 股性地图象限：由全样本 d1/d2 的中位数切分，象限只做结构分类，不是评价。
QUADRANT_LABELS = {
    "hh": "高异动·高溢价",
    "hl": "高异动·低溢价",
    "lh": "低异动·高溢价",
    "ll": "低异动·低溢价",
}

THRESHOLD_KEYS = (
    "limit_up_pct",
    "spike_pct",
    "dump_drawdown_pct",
    "dump_window_days",
    "lhb_net_min_cny",
    "score_weights",
    "archetype",
)

ARCHETYPE_THRESHOLD_KEYS = (
    "high",
    "mid",
    "low",
    "legend_streak",
    "capacity_high",
    "elastic_high",
    "trend_high",
)

BOARD_KEYS = ("main", "gem", "star", "bse", "st")

# 流动性容量口径，按证据等级从高到低：
#   amount_avg_cny   日均成交额（交易所级一手证据，最优）
#   float_cap_cny    流通市值（东财快照直接披露，代理「装得下多少成交」）
#   turnover_avg_pct 日均换手率（透明计算：成交量÷流通股本，证据等级最低）
CAPACITY_METRICS = ("amount_avg_cny", "float_cap_cny", "turnover_avg_pct")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class PersonalityError(ValueError):
    """契约或口径错误。生成器把它转成非零退出码，绝不静默降级。"""


def require_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise PersonalityError(f"{field} 必须是非空字符串")
    return value.strip()


def require_number(value, field, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PersonalityError(f"{field} 必须是数值，实际为 {type(value).__name__}")
    number = float(value)
    if minimum is not None and number < minimum:
        raise PersonalityError(f"{field} 不得小于 {minimum}，实际为 {number}")
    if maximum is not None and number > maximum:
        raise PersonalityError(f"{field} 不得大于 {maximum}，实际为 {number}")
    return number


def parse_date(value, field):
    text = require_text(value, field)
    if not DATE_RE.match(text):
        raise PersonalityError(f"{field} 必须是 YYYY-MM-DD 格式的日期字符串")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError as exc:
        raise PersonalityError(f"{field} 不是合法日期：{text}") from exc


def percentile_rank(values, target):
    """返回 target 在同批数值中的百分位（0-100，并列取平均秩）。

    样本只有 1 个时返回 50.0：单点无法定序，不假装它在两端。
    """
    if not values:
        raise PersonalityError("百分位计算需要非空样本")
    if len(values) == 1:
        return 50.0
    below = sum(1 for item in values if item < target)
    equal = sum(1 for item in values if item == target)
    average_rank = below + (equal - 1) / 2
    return round(average_rank / (len(values) - 1) * 100, 4)


def blend(*parts):
    """把若干 (分数, 权重) 合成为一个 0-100 分；权重不足 1 时按已给权重归一。"""
    total_weight = sum(weight for _, weight in parts)
    if total_weight <= 0:
        raise PersonalityError("合成分数需要正的权重合计")
    value = sum(score * weight for score, weight in parts) / total_weight
    return round(min(100.0, max(0.0, value)), 4)


def today() -> date:
    return datetime.now().date()
