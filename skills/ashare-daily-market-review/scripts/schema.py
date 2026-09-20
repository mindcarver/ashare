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


SCHEMA_VERSION = "1.5"


# 兼容可读的旧版本：升级链只前进不后退。
#   1.0 → 1.1  结构性归一化（旧文本口径 → 结构化 universe/窗口/资金类别）
#   1.1 → 1.2  纯版本升级（1.2 全部新增字段均为可选，旧输入语义不变）
#   1.2 → 1.3  验证点增加 subject 语义；深度分析层全部可选
#   1.3 → 1.4  增加分析模式、独立深度覆盖和四轴交汇；旧输入默认 core
#   1.4 → 1.5  深度层增加四条日常纪律：催化必须分类且宏观催化不绑主题、
#              个股窗口必须做口径交叉校验、集中度必须有样本口径、口径说明可披露。
#              这四项对「新写的 1.5 输入」是必填；由 1.4 升级进来的输入豁免且不回填，
#              因此历史 deep 输入仍可逐字节重放。core 输入不受影响。
SUPPORTED_LEGACY_VERSIONS = {"1.0", "1.1", "1.2", "1.3", "1.4"}


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


# 催化链的分类维度（1.5）。分类本身不是判断，而是为了让「今天只有政策新闻」这种
# 覆盖缺口在报告里可见；`transmission` 强制写出事件→主题的传导路径，用来拦住
# 「因为契约要求绑定主题，所以把宏观事件硬挂到某个板块」的写法。
CATALYST_TYPES = {
    "policy",
    "price_hike",
    "order",
    "capacity",
    "earnings",
    "shareholder",
    "supply",
    "macro",
}


# 产业级催化：能落到「这个板块为什么今天涨」的类型。政策与宏观属于背景，
# 不计入产业级覆盖。
INDUSTRIAL_CATALYST_TYPES = {
    "price_hike",
    "order",
    "capacity",
    "earnings",
    "shareholder",
    "supply",
}


CATALYST_TYPE_LABELS = {
    "policy": "政策",
    "price_hike": "提价",
    "order": "订单",
    "capacity": "产能",
    "earnings": "业绩",
    "shareholder": "股东行为",
    "supply": "供给与管制",
    "macro": "宏观",
}


# `theme` 必须绑定已声明主题并写出传导链；`macro_backdrop` 明确不绑主题。
CATALYST_SCOPES = {"theme", "macro_backdrop"}


CATALYST_SCOPE_LABELS = {
    "theme": "主题催化",
    "macro_backdrop": "宏观背景（不绑定主题）",
}


# 量价条件码的公开中文标签：渲染层统一取用；未列出的码保留原文，不静默丢弃。
# 码集与 deep_analysis.derive_liquidity_regime 声明的阈值键一一对应。
LIQUIDITY_CHECK_LABELS = {
    "volume_ratio_min": "量比(5日)",
    "consecutive_days_min": "连续放量天数",
    "ma20_distance_min_pct": "距20日均线",
    "daily_change_min_pct": "当日涨跌幅",
    "advancer_share_min_pct": "上涨家数占比",
    "limit_up_min": "涨停家数",
    "limit_down_max": "跌停家数",
    "promotion_rate_min_pct": "晋级率",
}


CONCENTRATION_SCOPES = {"complete", "sample"}


# ─── 公开报告中文标签层（2026-09-17 用户反馈：公开报告绝不出现英文字段码）───
# 渲染层一律从这里取标签；映射缺失时保留原文会被公开语言门禁拦下，逼着补齐。

OPERATOR_SYMBOLS = {"<=": "≤", ">=": "≥", "==": "="}


AVAILABILITY_LABELS = {
    "available": "可得",
    "partial": "部分",
    "unknown": "未知",
}


SENTIMENT_STATE_LABELS = {
    "ice": "冰点",
    "euphoria": "亢奋",
    "divergence": "分歧",
    "repair": "修复",
    "neutral": "中性",
    "unknown": "未知",
}

SNAPSHOT_TYPE_LABELS = {
    "close": "收盘",
    "post_close": "盘后",
    "weekend_update": "周末补充",
}

ANALYSIS_MODE_LABELS = {
    "deep": "深度交付",
    "core": "基础交付",
}

METHOD_CATEGORY_LABELS = {
    "exchange_fact": "交易所事实",
    "provider_model": "供应商模型",
    "activity_proxy": "活跃度代理",
    "derived": "派生值",
}

SECURITY_ROLE_LABELS = {
    "high_board": "高标",
    "sector_leader": "板块重点股",
    "theme_leader": "主题领涨股",
}

CAPITAL_ROLE_LABELS = {
    "inflow": "流入",
    "outflow": "流出",
}

PSEUDO_STATUS_LABELS = {
    "clear": "未标记",
    "flagged": "伪板块",
    "unknown": "未知",
}

SCOPE_LABELS = {
    "market": "全市场",
    "stock": "个股",
    "sector": "板块",
    "theme": "主题",
    "benchmark": "基准",
}

LIQUIDITY_RESULT_LABELS = {
    "all_declared_conditions_met": "全部声明条件成立",
    "conditions_not_met": "条件未全部成立",
    "unknown": "未知",
}

CAUSAL_STATUS_LABELS = {
    "hypothesis": "机制假设",
    "correlation_only": "仅相关（不作因果解读）",
    "evidence_backed": "证据支撑",
}

SECTION_KEY_LABELS = {
    "indices": "主要指数",
    "breadth": "市场宽度",
    "short_term_sentiment": "短线情绪",
    "turnover": "成交与流动性",
    "sectors": "板块表现",
    "funds": "资金证据",
    "style": "风格结构",
    "events": "事件",
    "mainline_matrix": "双确认主线矩阵",
    "prev_pool_performance": "延续性检验",
}

# 验证点/阈值体检的全部指标（与 VERIFICATION_UNITS_BY_SCOPE 闭集对齐）+ 体检键。
PUBLIC_METRIC_LABELS = {
    "primary_index_change_pct": "主要指数涨跌幅",
    "advancer_share_pct": "上涨家数占比",
    "turnover_amount": "两市成交额",
    "turnover_vs_previous_pct": "成交额较前值变化",
    "open_board_rate_pct": "炸板率",
    "limit_balance": "涨停净差（涨停-跌停）",
    "promotion_rate_pct": "晋级率",
    "streak": "连板数",
    "change_pct": "涨跌幅",
    "fund_flow_1d_cny": "当日主力净额",
    "sealed_order_amount_cny": "封单金额",
    "break_count": "开板次数",
    "fund_flow_cny": "板块资金净流入",
    "top1_positive_share_pct": "Top1正流入占比",
    "first_board_count": "首板家数",
    "limit_up_count": "涨停家数",
    "board_fund_flow_cny": "板块资金净流入",
    "volume_ratio_5d": "量比(5日)",
    "ma20_distance_pct": "距20日均线",
    "ma60_distance_pct": "距60日均线",
    "return_percentile_120d": "收益120日分位",
    "volume_percentile_120d": "成交120日分位",
    "limit_up": "涨停家数",
    "limit_down": "跌停家数",
    "highest_streak": "最高连板",
    "limit_up_min": "涨停家数下限",
    "limit_down_max": "跌停家数上限",
    "open_board_rate_max_pct": "炸板率上限",
    "promotion_rate_min_pct": "晋级率下限",
    "highest_streak_min": "最高连板下限",
    "volume_ratio_min": "量比(5日)下限",
    "consecutive_days_min": "连续放量天数下限",
    "ma20_distance_min_pct": "距20日均线下限",
    "daily_change_min_pct": "当日涨跌幅下限",
}

# 象限码同时并入指标标签：信号规则文本（如 `quadrant == dual_confirmed`）共用这套映射。
PUBLIC_METRIC_LABELS.update({
    "dual_confirmed": "双确认",
    "capital_led": "资金先行",
    "sentiment_only": "情绪脉冲",
    "sentiment_bleeding": "情绪失血",
    "bleeding": "失血",
    "quadrant": "主线象限",
})

# 象限短名（区别于 QUADRANTS 的完整读法，用于表格单元格）。
QUADRANT_SHORT_LABELS = {
    "dual_confirmed": "双确认",
    "capital_led": "资金先行",
    "sentiment_only": "情绪脉冲",
    "sentiment_bleeding": "情绪失血",
    "bleeding": "失血",
    "unknown": "未知",
}


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
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ReviewError(f"{field} 必须是YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ReviewError(f"{field} 必须是YYYY-MM-DD")
    return parsed


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
