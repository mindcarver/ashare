#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""契约层：Schema 常量、错误类型、规范化/摘要/日期与文本断言。

拆分自 research_journal.py（沿用 P2-5 纪律）。导入无副作用。
"""

import hashlib
import json

from datetime import date
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"


CRITERION_METRICS = {
    "stock_return_pct",
    "benchmark_return_pct",
    "excess_return_pct",
    "max_drawdown_pct",
    "max_favorable_excursion_pct",
    "max_adverse_excursion_pct",
}


# 市场级指标：衡量的是「整个盘面」的条件，不挂在单只股票上，因此没有价格路径。
# 用 record-market / observe-market 记录，存进独立的 market_records / market_outcomes 两张表，
# 不触碰价格路径那条链路（`record` / `observe` / research_records 语义完全不变）。
# 值 → 单位 的对应关系是契约的一部分，记录与结算时都要校验一致。
MARKET_METRICS = {
    "turnover_amount": "CNY",
    "advancer_share_pct": "percent",
    "open_board_rate_pct": "percent",
    "promotion_rate_pct": "percent",
    "primary_index_change_pct": "percent",
    "limit_balance": "count",
    "limit_up_count": "count",
    "limit_down_count": "count",
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
