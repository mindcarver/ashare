#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""通用证据与来源契约断言（从 validate.py 抽出）。

把与具体章节无关的「证据—来源」断言下沉到本模块，`validate.py` 与
`validate_analysis.py` 共用同一套实现，既避免循环导入，也避免两处各写一份
导致校验口径漂移。导入无副作用。
"""

import math

from datetime import date
from typing import Any
from urllib.parse import urlparse

from schema import ReviewError, VERIFICATION_OPERATORS, VERIFICATION_UNITS_BY_SCOPE, parse_date, parse_datetime, require_text


def validate_source(source: Any, field: str) -> None:
    if not isinstance(source, dict):
        raise ReviewError(f"{field}.source 必须是object")
    for key in ("id", "name"):
        if not isinstance(source.get(key), str) or not source[key].strip():
            raise ReviewError(f"{field}.source.{key} 必须是非空字符串")
    kind = source.get("kind", "external")
    if kind == "derived":
        refs = source.get("evidence_refs")
        if not isinstance(refs, list) or not refs or not all(
            isinstance(item, str) and item.strip() for item in refs
        ):
            raise ReviewError(f"{field}.source.evidence_refs 必须是非空字符串数组")
        if source.get("url"):
            raise ReviewError(f"{field}.source.kind=derived 时不能伪造url")
        return
    if kind != "external":
        raise ReviewError(f"{field}.source.kind 不受支持")
    if not isinstance(source.get("url"), str) or not source["url"].strip():
        raise ReviewError(f"{field}.source.url 必须是非空字符串")
    parsed = urlparse(source["url"])
    is_web = parsed.scheme in {"http", "https"} and parsed.netloc
    is_file = parsed.scheme == "file" and parsed.path.startswith("/")
    if not (is_web or is_file):
        raise ReviewError(f"{field}.source.url 必须是http(s)或绝对file URL")

def validate_evidence(
    evidence: Any,
    field: str,
    as_of: date,
    expected_unit: str | None = None,
    value_constraint: str = "any",
) -> None:
    if not isinstance(evidence, dict):
        raise ReviewError(f"{field} 必须是object")
    raw_value = evidence.get("value")
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise ReviewError(f"{field}.value 必须是数值")
    number = float(raw_value)
    if not math.isfinite(number):
        raise ReviewError(f"{field}.value 必须是有限数值")
    if expected_unit == "count" and not number.is_integer():
        raise ReviewError(f"{field}.value 使用count时必须是整数")
    if value_constraint == "positive" and number <= 0:
        raise ReviewError(f"{field}.value 必须是正的有限数值")
    if value_constraint == "nonnegative" and number < 0:
        raise ReviewError(f"{field}.value 必须是非负的有限数值")
    unit = require_text(evidence, "unit", field)
    if expected_unit and unit != expected_unit:
        raise ReviewError(f"{field}.unit 必须是{expected_unit}")
    observed_at = parse_date(evidence.get("observed_at"), f"{field}.observed_at")
    published_at = parse_date(evidence.get("published_at"), f"{field}.published_at")
    if observed_at > as_of:
        raise ReviewError(f"{field}.observed_at 晚于 as-of")
    if published_at > as_of:
        raise ReviewError(f"{field}.published_at 晚于 as-of")
    parse_datetime(evidence.get("fetched_at"), f"{field}.fetched_at")
    validate_source(evidence.get("source"), field)

def validate_event(item: Any, field: str, as_of: date, allow_future_event: bool) -> None:
    if not isinstance(item, dict):
        raise ReviewError(f"{field} 必须是object")
    require_text(item, "title", field)
    event_date = parse_date(item.get("event_date"), f"{field}.event_date")
    published_at = parse_date(item.get("published_at"), f"{field}.published_at")
    if not allow_future_event and event_date > as_of:
        raise ReviewError(f"{field}.event_date 晚于 as-of")
    if published_at > as_of:
        raise ReviewError(f"{field}.published_at 晚于 as-of")
    parse_datetime(item.get("fetched_at"), f"{field}.fetched_at")
    validate_source(item.get("source"), field)

def validate_universe(universe: Any, field: str) -> None:
    if not isinstance(universe, dict):
        raise ReviewError(f"{field} 必须是object")
    for key in ("id", "label", "population_rule"):
        require_text(universe, key, field)
    for key in ("includes_st", "includes_bse"):
        if not isinstance(universe.get(key), bool):
            raise ReviewError(f"{field}.{key} 必须是boolean")
    exclusions = universe.get("exclusions")
    if not isinstance(exclusions, list) or not all(
        isinstance(item, str) and item.strip() for item in exclusions
    ):
        raise ReviewError(f"{field}.exclusions 必须是字符串数组")

def validate_window(window: Any, field: str, market_date: date) -> None:
    if not isinstance(window, dict):
        raise ReviewError(f"{field}.window 必须是object")
    trading_days = window.get("trading_days")
    if isinstance(trading_days, bool) or not isinstance(trading_days, int) or trading_days < 1:
        raise ReviewError(f"{field}.window.trading_days 必须是正整数")
    if parse_date(window.get("end_at"), f"{field}.window.end_at") != market_date:
        raise ReviewError(f"{field}.window.end_at 必须等于market_date")

def validate_verification_point(item: Any, field: str, as_of: date) -> None:
    validate_event(item, field, as_of, True)
    require_text(item, "id", field)
    subject = item.get("subject")
    if not isinstance(subject, dict):
        raise ReviewError(f"{field}.subject 必须是object")
    scope = subject.get("scope")
    if scope not in VERIFICATION_UNITS_BY_SCOPE:
        raise ReviewError(f"{field}.subject.scope 不受支持")
    require_text(subject, "id", f"{field}.subject")
    require_text(subject, "label", f"{field}.subject")
    condition = item.get("condition")
    if not isinstance(condition, dict):
        raise ReviewError(f"{field}.condition 必须是object")
    metric = condition.get("metric")
    if metric not in VERIFICATION_UNITS_BY_SCOPE[scope]:
        raise ReviewError(f"{field}.condition.metric 不受支持")
    if condition.get("operator") not in VERIFICATION_OPERATORS:
        raise ReviewError(f"{field}.condition.operator 不受支持")
    target = condition.get("value")
    if isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target):
        raise ReviewError(f"{field}.condition.value 必须是有限数值")
    unit = require_text(condition, "unit", f"{field}.condition")
    if unit != VERIFICATION_UNITS_BY_SCOPE[scope][metric]:
        raise ReviewError(f"{field}.condition.unit 与scope/metric不匹配")

def require_market_date(evidence: dict[str, Any], field: str, market_date: date) -> None:
    observed_at = parse_date(evidence.get("observed_at"), f"{field}.observed_at")
    if observed_at != market_date:
        raise ReviewError(f"{field} 标记available时observed_at必须等于market_date")
