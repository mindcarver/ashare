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
