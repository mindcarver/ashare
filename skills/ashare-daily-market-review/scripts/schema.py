#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日复盘的契约层：错误类型、Schema 常量、日期/文本断言与通用取值器。

拆分自 generate_daily_review.py（审计 P2-5）。导入无副作用。
"""

from datetime import date
from datetime import datetime
from typing import Any

import _paths  # noqa: F401  确保 skills/_shared 在 sys.path 上
from ashare_shared import forbidden_terms


SCHEMA_VERSION = "1.4"


# 兼容可读的旧版本：升级链只前进不后退。
#   1.0 → 1.1  结构性归一化（旧文本口径 → 结构化 universe/窗口/资金类别）
#   1.1 → 1.2  纯版本升级（1.2 全部新增字段均为可选，旧输入语义不变）
#   1.2 → 1.3  验证点增加 subject 语义；深度分析层全部可选
#   1.3 → 1.4  增加分析模式、独立深度覆盖和四轴交汇；旧输入默认 core
SUPPORTED_LEGACY_VERSIONS = {"1.0", "1.1", "1.2", "1.3"}


ANALYSIS_MODES = {"core", "deep"}


SECTION_NAMES = (
    "indices",
    "breadth",
    "short_term_sentiment",
    "turnover",
    "sectors",
    "funds",
    "style",
    "events",
    # 1.2 新增：两个可选的分析语义章节。缺省时按 unknown 处理，不影响旧报告。
    "mainline_matrix",
    "prev_pool_performance",
)


AVAILABILITY = {"available", "partial", "unknown"}


SNAPSHOT_TYPES = {"close", "post_close", "weekend_update"}


FUND_METHODS = {
    "exchange_fact",
    "transparent_calculation",
    "provider_model",
    "activity_proxy",
}


HIGH_TRUST_FUND_METHODS = {"exchange_fact", "transparent_calculation"}


# 可前瞻结算的量化指标。`promotion_rate_pct` 来自 prev_pool_performance：
# 它在交易日 D 衡量「D-1 涨停池于 D 的晋级率」，因此以 D 为 event_date 的验证点
# 会在 D 当天用同一口径结算，不需要额外的观察滞后。缺少该章节时取值为 None，
# 验证点自动落回 unknown，绝不用 0 或上期值顶替。
VERIFICATION_METRICS = {
    "primary_index_change_pct",
    "advancer_share_pct",
    "turnover_amount",
    "turnover_vs_previous_pct",
    "open_board_rate_pct",
    "limit_balance",
    "promotion_rate_pct",
}


VERIFICATION_UNITS = {
    "primary_index_change_pct": "percent",
    "advancer_share_pct": "percent",
    "turnover_amount": "CNY",
    "turnover_vs_previous_pct": "percent",
    "open_board_rate_pct": "percent",
    "limit_balance": "count",
    "promotion_rate_pct": "percent",
}


VERIFICATION_OPERATORS = {">", ">=", "<", "<=", "=="}


VERIFICATION_UNITS_BY_SCOPE = {
    "market": VERIFICATION_UNITS,
    "stock": {
        "streak": "count",
        "change_pct": "percent",
        "fund_flow_1d_cny": "CNY",
        "sealed_order_amount_cny": "CNY",
        "break_count": "count",
    },
    "sector": {
        "change_pct": "percent",
        "fund_flow_cny": "CNY",
        "top1_positive_share_pct": "percent",
        "first_board_count": "count",
    },
    "theme": {
        "limit_up_count": "count",
        "board_fund_flow_cny": "CNY",
        "top1_positive_share_pct": "percent",
    },
    "benchmark": {
        "change_pct": "percent",
        "volume_ratio_5d": "ratio",
        "ma20_distance_pct": "percent",
        "ma60_distance_pct": "percent",
        "return_percentile_120d": "percent",
        "volume_percentile_120d": "percent",
    },
}


DEEP_COMPONENTS = (
    "security_details",
    "liquidity_regime",
    "sentiment_cycle",
    "capital_co_movement",
    "catalyst_chains",
    "lhb_structure",
)


DEEP_SECURITY_ROLES = {"high_board", "sector_leader", "theme_leader"}
FUND_FLOW_WINDOWS = {1, 3, 5, 10}
SENTIMENT_STATES = {"ice", "euphoria", "divergence", "repair", "neutral", "unknown"}


# 双确认主线矩阵：象限是「游资情绪面（涨停家数）× 机构资金面（板块主力净流入）」
# 的二维结构观察，不是评分、不是买卖信号。阈值必须由输入显式声明，禁止隐式默认。
QUADRANTS = {
    "dual_confirmed": "双确认：涨停家数达标且板块资金净流入",
    "capital_led": "资金先行：板块资金净流入但涨停家数未达标",
    "sentiment_only": "情绪脉冲：涨停家数达标但板块资金未净流入",
    "sentiment_bleeding": "情绪失血：涨停家数达标但板块资金大额净流出",
    "bleeding": "失血：涨停家数未达标且板块资金未净流入",
    "unknown": "象限未知：板块资金流或涨停家数缺失",
}


# 输出（图例、计数、信号）顺序。`sentiment_bleeding` 只在输入声明了
# `bleeding_threshold_cny` 时出现，否则整条链路的输出与 1.2 原样一致。
QUADRANT_ORDER = (
    "dual_confirmed",
    "capital_led",
    "sentiment_only",
    "sentiment_bleeding",
    "bleeding",
    "unknown",
)


def active_quadrant_order(has_bleeding_line: bool) -> tuple[str, ...]:
    """实际参与计数与图例的象限顺序，是派生层与渲染层共用的唯一真源。

    未声明 `bleeding_threshold_cny` 时省略「情绪失血」格：既不计数也不展示，
    保证既有 1.2 输入的摘要与报告逐字节不变。声明后才多出这一格。
    """
    if has_bleeding_line:
        return QUADRANT_ORDER
    return tuple(name for name in QUADRANT_ORDER if name != "sentiment_bleeding")


MAINLINE_QUADRANT_RULES = ("limit_up_threshold", "capital_threshold_cny")


# 可选规则键：声明后把「情绪脉冲」按资金流出深度再拆一档，用于区分
# 「家数达标 + 资金弱正」（真实脉冲）与「家数达标 + 大额净流出」（失血中继）。
OPTIONAL_MAINLINE_QUADRANT_RULES = ("bleeding_threshold_cny",)


# 短线情绪健康体检的可声明阈值键。缺省即为「不体检」，绝不回退到隐藏默认值。
HEALTH_THRESHOLD_KEYS = (
    "limit_up_min",
    "limit_down_max",
    "open_board_rate_max_pct",
    "promotion_rate_min_pct",
    "highest_streak_min",
)


# 资金方法类别在 sectors 板块资金流上复用同一套证据分级。
SECTOR_FUND_FLOW_REQUIRES_METHOD = True


FORBIDDEN = forbidden_terms("no_price")


class ReviewError(ValueError):
    """Raised when market evidence violates the daily review contract."""


def parse_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ReviewError(f"{field} 必须是YYYY-MM-DD") from exc


def parse_datetime(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ReviewError(f"{field} 必须是带时区的ISO-8601 datetime") from exc
    if parsed.tzinfo is None:
        raise ReviewError(f"{field} 必须包含时区")
    return parsed


def require_text(value: dict[str, Any], field: str, prefix: str = "") -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        name = f"{prefix}.{field}" if prefix else field
        raise ReviewError(f"{name} 必须是非空字符串")
    return result


def value(section: dict[str, Any], metric: str) -> float | None:
    evidence = section.get("metrics", {}).get(metric)
    return float(evidence["value"]) if evidence else None
