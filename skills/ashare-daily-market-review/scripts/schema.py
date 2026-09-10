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


SCHEMA_VERSION = "1.1"


SECTION_NAMES = (
    "indices",
    "breadth",
    "short_term_sentiment",
    "turnover",
    "sectors",
    "funds",
    "style",
    "events",
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


VERIFICATION_METRICS = {
    "primary_index_change_pct",
    "advancer_share_pct",
    "turnover_amount",
    "turnover_vs_previous_pct",
    "open_board_rate_pct",
    "limit_balance",
}


VERIFICATION_UNITS = {
    "primary_index_change_pct": "percent",
    "advancer_share_pct": "percent",
    "turnover_amount": "CNY",
    "turnover_vs_previous_pct": "percent",
    "open_board_rate_pct": "percent",
    "limit_balance": "count",
}


VERIFICATION_OPERATORS = {">", ">=", "<", "<=", "=="}


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
