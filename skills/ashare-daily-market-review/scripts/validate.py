#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输入读取、Schema 1.0 归一化与全部契约校验。

拆分自 generate_daily_review.py（审计 P2-5）。只做校验，不派生、不渲染。
"""

import copy
import hashlib
import json
import math
import re

from datetime import date
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from schema import AVAILABILITY, FUND_METHODS, HIGH_TRUST_FUND_METHODS, ReviewError, SCHEMA_VERSION, SECTION_NAMES, SNAPSHOT_TYPES, VERIFICATION_METRICS, VERIFICATION_OPERATORS, VERIFICATION_UNITS, parse_date, parse_datetime, require_text, value


def load_input(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReviewError(f"无法读取输入：{exc}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReviewError(f"输入不是有效JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise ReviewError("输入顶层必须是object")
    input_sha256 = hashlib.sha256(raw).hexdigest()
    return upgrade_legacy_input(value, input_sha256), input_sha256


def collect_fetched_at(value: Any) -> list[datetime]:
    found: list[datetime] = []
    if isinstance(value, dict):
        if "fetched_at" in value:
            found.append(parse_datetime(value["fetched_at"], "legacy.fetched_at"))
        for child in value.values():
            found.extend(collect_fetched_at(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(collect_fetched_at(child))
    return found


def legacy_universe(label: str, status_reason: str) -> dict[str, Any]:
    combined = f"{label} {status_reason}"
    return {
        "id": "legacy-" + hashlib.sha256(combined.encode("utf-8")).hexdigest()[:12],
        "label": label,
        "population_rule": f"由Schema 1.0文本保守迁移：{combined}",
        "includes_st": "含ST" in combined and "不含ST" not in combined,
        "includes_bse": "北交" in combined,
        "exclusions": [],
    }


def infer_legacy_window(item: dict[str, Any]) -> int:
    text = f"{item.get('name', '')} {item.get('interpretation', '')}"
    if re.search(r"(?:近)?20日|二十日", text):
        return 20
    if re.search(r"(?:近)?5日|五日", text):
        return 5
    return 1


def infer_legacy_fund_method(item: dict[str, Any]) -> str:
    text = f"{item.get('name', '')} {item.get('methodology', '')}"
    if "交易所" in text and any(word in text for word in ("事实", "公布", "披露")):
        return "exchange_fact"
    if any(word in text for word in ("成交额", "活跃度代理", "非净买入")):
        return "activity_proxy"
    return "provider_model"


def upgrade_legacy_input(data: dict[str, Any], input_sha256: str) -> dict[str, Any]:
    if data.get("schema_version") != "1.0":
        return data
    migrated = copy.deepcopy(data)
    market_date = require_text(migrated, "market_date")
    fetched = collect_fetched_at(migrated)
    if not fetched:
        raise ReviewError("Schema 1.0输入缺少fetched_at，无法确定快照截止时间")
    cutoff = max(fetched)
    migrated["schema_version"] = SCHEMA_VERSION
    migrated["snapshot"] = {
        "type": "close" if cutoff.date().isoformat() == market_date else "post_close",
        "cutoff_at": cutoff.isoformat(),
        "revision": 1,
        "supersedes_sha256": None,
        "raw_evidence_sha256": input_sha256,
    }
    warnings = ["输入由Schema 1.0保守归一化为1.1；未伪造缺失字段"]
    sections = migrated.get("sections", {})
    breadth = sections.get("breadth", {})
    sentiment = sections.get("short_term_sentiment", {})
    if breadth.get("availability") != "unknown":
        label = breadth.get("universe")
        if not isinstance(label, str) or not label.strip():
            label = breadth.get("status_reason", "Schema 1.0股票池未命名")
        breadth["universe"] = legacy_universe(label, breadth.get("status_reason", ""))
    if sentiment.get("availability") != "unknown":
        label = sentiment.get("universe")
        if not isinstance(label, str) or not label.strip():
            label = sentiment.get("status_reason", "Schema 1.0短线股票池未命名")
        methodology = sentiment.get("methodology", "")
        mismatch_markers = ("口径差", "不含ST", "统计时点", "股票池定义不同")
        if any(marker in methodology for marker in mismatch_markers):
            sentiment["availability"] = "partial"
            sentiment["status_reason"] = (
                f"{sentiment.get('status_reason', '')}；Schema 1.0方法文本显示股票池不一致，不能计算状态"
            ).strip("；")
            sentiment["universe"] = legacy_universe(label, methodology)
            warnings.append("短线情绪因旧输入披露股票池差异而降为partial")
        elif breadth.get("universe"):
            sentiment["universe"] = copy.deepcopy(breadth["universe"])

    turnover_metrics = sections.get("turnover", {}).get("metrics", {})
    for name, days in (("avg_5d_amount", 5), ("avg_20d_amount", 20)):
        if name in turnover_metrics:
            turnover_metrics[name]["window"] = {
                "trading_days": days,
                "end_at": market_date,
            }
    for item in sections.get("style", {}).get("items", []):
        item["window"] = {
            "trading_days": infer_legacy_window(item),
            "end_at": market_date,
        }
    funds = sections.get("funds", {})
    if funds.get("availability") != "unknown":
        for item in funds.get("items", []):
            item["method_category"] = infer_legacy_fund_method(item)
        if funds.get("availability") == "available" and not any(
            item["method_category"] in HIGH_TRUST_FUND_METHODS
            for item in funds.get("items", [])
        ):
            funds["availability"] = "partial"
            funds["status_reason"] = (
                f"{funds.get('status_reason', '')}；Schema 1.0资金证据仅含模型或活跃度代理"
            ).strip("；")
            warnings.append("资金章节因旧输入仅含模型或代理数据而降为partial")

    qualitative = migrated.get("verification_points", [])
    for point in qualitative:
        source = point.get("source", {})
        if source.get("id") == "self-derived" or source.get("url", "").startswith(
            "https://example.com"
        ):
            point["source"] = {
                "id": source.get("id", "legacy-derived"),
                "name": source.get("name", "旧版派生观察点"),
                "kind": "derived",
                "evidence_refs": ["legacy.qualitative_verification_points"],
            }
    migrated["qualitative_verification_points"] = qualitative
    migrated["verification_points"] = []
    if qualitative:
        warnings.append("旧版定性验证点保留展示，但不冒充机器可结算条件")
    migrated["legacy_migration"] = {"from": "1.0", "warnings": warnings}
    return migrated


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


def validate_snapshot(data: dict[str, Any], market_date: date, as_of: date) -> None:
    snapshot = data.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ReviewError("snapshot 必须是object")
    snapshot_type = snapshot.get("type")
    if snapshot_type not in SNAPSHOT_TYPES:
        raise ReviewError("snapshot.type 不受支持")
    cutoff = parse_datetime(snapshot.get("cutoff_at"), "snapshot.cutoff_at")
    if cutoff.date() > as_of:
        raise ReviewError("snapshot.cutoff_at 不能晚于as_of")
    if snapshot_type == "close" and cutoff.date() != market_date:
        raise ReviewError("close快照的cutoff_at必须与market_date同日")
    if cutoff.date() < market_date:
        raise ReviewError("snapshot.cutoff_at 不能早于market_date")
    revision = snapshot.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise ReviewError("snapshot.revision 必须是正整数")
    supersedes = snapshot.get("supersedes_sha256")
    if supersedes is not None and (
        not isinstance(supersedes, str)
        or len(supersedes) != 64
        or any(char not in "0123456789abcdef" for char in supersedes)
    ):
        raise ReviewError("snapshot.supersedes_sha256 必须是SHA-256或null")
    if revision == 1 and supersedes is not None:
        raise ReviewError("首个修订不能设置supersedes_sha256")
    if revision > 1 and supersedes is None:
        raise ReviewError("后续修订必须设置supersedes_sha256")
    raw_hash = snapshot.get("raw_evidence_sha256")
    if not isinstance(raw_hash, str) or len(raw_hash) != 64 or any(
        char not in "0123456789abcdef" for char in raw_hash
    ):
        raise ReviewError("snapshot.raw_evidence_sha256 必须是SHA-256")


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
    condition = item.get("condition")
    if not isinstance(condition, dict):
        raise ReviewError(f"{field}.condition 必须是object")
    if condition.get("metric") not in VERIFICATION_METRICS:
        raise ReviewError(f"{field}.condition.metric 不受支持")
    if condition.get("operator") not in VERIFICATION_OPERATORS:
        raise ReviewError(f"{field}.condition.operator 不受支持")
    target = condition.get("value")
    if isinstance(target, bool) or not isinstance(target, (int, float)) or not math.isfinite(target):
        raise ReviewError(f"{field}.condition.value 必须是有限数值")
    unit = require_text(condition, "unit", f"{field}.condition")
    if unit != VERIFICATION_UNITS[condition["metric"]]:
        raise ReviewError(f"{field}.condition.unit 与metric不匹配")


def validate_cutoff(value: Any, cutoff: datetime, field: str = "input") -> None:
    if isinstance(value, dict):
        if "fetched_at" in value:
            fetched_at = parse_datetime(value["fetched_at"], f"{field}.fetched_at")
            if fetched_at > cutoff:
                raise ReviewError(f"{field}.fetched_at 晚于snapshot.cutoff_at")
        if "published_at" in value:
            published_at = parse_date(value["published_at"], f"{field}.published_at")
            if published_at > cutoff.date():
                raise ReviewError(f"{field}.published_at 晚于snapshot.cutoff_at")
        for key, child in value.items():
            validate_cutoff(child, cutoff, f"{field}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            validate_cutoff(child, cutoff, f"{field}[{index}]")


def normalized_sections(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_sections = data.get("sections")
    if not isinstance(raw_sections, dict):
        raise ReviewError("sections 必须是object")
    sections = {}
    for name in SECTION_NAMES:
        section = raw_sections.get(name)
        if section is None:
            section = {"availability": "unknown", "status_reason": "输入未提供该章节"}
        if not isinstance(section, dict):
            raise ReviewError(f"sections.{name} 必须是object")
        availability = section.get("availability")
        if availability not in AVAILABILITY:
            raise ReviewError(f"sections.{name}.availability 不受支持")
        require_text(section, "status_reason", f"sections.{name}")
        if availability == "unknown" and any(
            section.get(name) for name in ("items", "metrics", "previous_metrics")
        ):
            raise ReviewError(f"sections.{name} 标记unknown时不能携带数值数据")
        sections[name] = section
    return sections


def require_market_date(evidence: dict[str, Any], field: str, market_date: date) -> None:
    observed_at = parse_date(evidence.get("observed_at"), f"{field}.observed_at")
    if observed_at != market_date:
        raise ReviewError(f"{field} 标记available时observed_at必须等于market_date")


def validate_sections(
    sections: dict[str, dict[str, Any]], as_of: date, market_date: date
) -> None:
    indices = sections["indices"]
    if indices["availability"] != "unknown":
        items = indices.get("items")
        if not isinstance(items, list) or not items:
            raise ReviewError("sections.indices.items 必须是非空数组")
        primary_count = 0
        for index, item in enumerate(items):
            field = f"sections.indices.items[{index}]"
            if not isinstance(item, dict):
                raise ReviewError(f"{field} 必须是object")
            require_text(item, "id", field)
            require_text(item, "name", field)
            if not isinstance(item.get("primary"), bool):
                raise ReviewError(f"{field}.primary 必须是boolean")
            primary_count += int(item["primary"])
            validate_evidence(
                item.get("close"),
                f"{field}.close",
                as_of,
                "index_points",
                "positive",
            )
            validate_evidence(item.get("change_pct"), f"{field}.change_pct", as_of, "percent")
            if indices["availability"] == "available":
                require_market_date(item["close"], f"{field}.close", market_date)
                require_market_date(
                    item["change_pct"], f"{field}.change_pct", market_date
                )
        if primary_count != 1:
            raise ReviewError("indices 必须且只能有一个primary指数")

    breadth = sections["breadth"]
    if breadth["availability"] != "unknown":
        validate_universe(breadth.get("universe"), "sections.breadth.universe")
        metrics = breadth.get("metrics")
        if not isinstance(metrics, dict):
            raise ReviewError("sections.breadth.metrics 必须是object")
        required = ("advancers", "decliners", "unchanged", "limit_up", "limit_down")
        if breadth["availability"] == "available" and any(name not in metrics for name in required):
            raise ReviewError("available breadth 缺少必需指标")
        for name, evidence in metrics.items():
            validate_evidence(
                evidence,
                f"sections.breadth.metrics.{name}",
                as_of,
                "count",
                "nonnegative",
            )
            if breadth["availability"] == "available":
                require_market_date(
                    evidence, f"sections.breadth.metrics.{name}", market_date
                )

    sentiment = sections["short_term_sentiment"]
    if sentiment["availability"] != "unknown":
        metrics = sentiment.get("metrics")
        if not isinstance(metrics, dict):
            raise ReviewError("sections.short_term_sentiment.metrics 必须是object")
        required = ("open_board_failed", "limit_attempts", "highest_streak")
        if sentiment["availability"] == "available" and any(
            name not in metrics for name in required
        ):
            raise ReviewError("available short_term_sentiment 缺少必需指标")
        if sentiment["availability"] == "available":
            if breadth["availability"] != "available":
                raise ReviewError("available short_term_sentiment 要求breadth为available")
            validate_universe(
                sentiment.get("universe"), "sections.short_term_sentiment.universe"
            )
            if sentiment["universe"] != breadth["universe"]:
                raise ReviewError("short_term_sentiment.universe 必须与breadth.universe一致")
            require_text(sentiment, "methodology", "sections.short_term_sentiment")
        for name, evidence in metrics.items():
            constraint = "positive" if name == "limit_attempts" else "nonnegative"
            validate_evidence(
                evidence,
                f"sections.short_term_sentiment.metrics.{name}",
                as_of,
                "count",
                constraint,
            )
            if sentiment["availability"] == "available":
                require_market_date(
                    evidence,
                    f"sections.short_term_sentiment.metrics.{name}",
                    market_date,
                )
        attempts = value(sentiment, "limit_attempts")
        failed = value(sentiment, "open_board_failed")
        if attempts is not None and failed is not None and failed > attempts:
            raise ReviewError("open_board_failed 不能大于limit_attempts")
        previous = sentiment.get("previous_metrics")
        if previous is not None:
            if not isinstance(previous, dict):
                raise ReviewError("sections.short_term_sentiment.previous_metrics 必须是object")
            required_previous = (
                "limit_up",
                "limit_down",
                "open_board_failed",
                "limit_attempts",
                "highest_streak",
            )
            if any(name not in previous for name in required_previous):
                raise ReviewError("previous_metrics 缺少修复判断必需指标")
            for name in required_previous:
                constraint = "positive" if name == "limit_attempts" else "nonnegative"
                evidence = previous[name]
                validate_evidence(
                    evidence,
                    f"sections.short_term_sentiment.previous_metrics.{name}",
                    as_of,
                    "count",
                    constraint,
                )
                if parse_date(
                    evidence["observed_at"],
                    f"sections.short_term_sentiment.previous_metrics.{name}.observed_at",
                ) >= market_date:
                    raise ReviewError("previous_metrics.observed_at 必须早于market_date")
            if value({"metrics": previous}, "open_board_failed") > value(
                {"metrics": previous}, "limit_attempts"
            ):
                raise ReviewError("previous_metrics.open_board_failed 不能大于limit_attempts")

    turnover = sections["turnover"]
    if turnover["availability"] != "unknown":
        metrics = turnover.get("metrics")
        if not isinstance(metrics, dict):
            raise ReviewError("sections.turnover.metrics 必须是object")
        if turnover["availability"] == "available" and any(
            name not in metrics for name in ("amount", "previous_amount")
        ):
            raise ReviewError("available turnover 缺少amount或previous_amount")
        for name, evidence in metrics.items():
            validate_evidence(
                evidence,
                f"sections.turnover.metrics.{name}",
                as_of,
                "CNY",
                "positive",
            )
        if turnover["availability"] == "available":
            require_market_date(
                metrics["amount"], "sections.turnover.metrics.amount", market_date
            )
        for name, expected_days in (("avg_5d_amount", 5), ("avg_20d_amount", 20)):
            if name in metrics:
                validate_window(
                    metrics[name].get("window"),
                    f"sections.turnover.metrics.{name}",
                    market_date,
                )
                if metrics[name]["window"]["trading_days"] != expected_days:
                    raise ReviewError(f"{name}.window.trading_days 必须是{expected_days}")

    sectors = sections["sectors"]
    if sectors["availability"] != "unknown":
        require_text(sectors, "classification", "sections.sectors")
        items = sectors.get("items")
        if not isinstance(items, list) or not items:
            raise ReviewError("sections.sectors.items 必须是非空数组")
        for index, item in enumerate(items):
            field = f"sections.sectors.items[{index}]"
            if not isinstance(item, dict):
                raise ReviewError(f"{field} 必须是object")
            require_text(item, "id", field)
            require_text(item, "name", field)
            validate_evidence(item.get("change_pct"), f"{field}.change_pct", as_of, "percent")
            if sectors["availability"] == "available":
                require_market_date(item["change_pct"], f"{field}.change_pct", market_date)

    for section_name in ("funds", "style"):
        section = sections[section_name]
        if section["availability"] == "unknown":
            continue
        items = section.get("items")
        if not isinstance(items, list) or not items:
            raise ReviewError(f"sections.{section_name}.items 必须是非空数组")
        for index, item in enumerate(items):
            field = f"sections.{section_name}.items[{index}]"
            if not isinstance(item, dict):
                raise ReviewError(f"{field} 必须是object")
            require_text(item, "name", field)
            explanation_field = "methodology" if section_name == "funds" else "interpretation"
            require_text(item, explanation_field, field)
            validate_evidence(item.get("metric"), f"{field}.metric", as_of)
            if section_name == "funds":
                method = item.get("method_category")
                if method not in FUND_METHODS:
                    raise ReviewError(f"{field}.method_category 不受支持")
                if method == "transparent_calculation":
                    calculation = item.get("calculation")
                    if not isinstance(calculation, dict):
                        raise ReviewError(f"{field}.calculation 必须是object")
                    require_text(calculation, "formula", f"{field}.calculation")
                    refs = calculation.get("input_refs")
                    if not isinstance(refs, list) or not refs or not all(
                        isinstance(ref, str) and ref.strip() for ref in refs
                    ):
                        raise ReviewError(f"{field}.calculation.input_refs 必须是非空字符串数组")
            else:
                validate_window(item.get("window"), field, market_date)
            if section_name == "style" and section["availability"] == "available":
                require_market_date(item["metric"], f"{field}.metric", market_date)

    funds = sections["funds"]
    if funds["availability"] == "available" and not any(
        item["method_category"] in HIGH_TRUST_FUND_METHODS
        for item in funds.get("items", [])
    ):
        raise ReviewError("funds仅含供应商模型或活跃度代理时不能标记available")

    events = sections["events"]
    if events["availability"] != "unknown":
        items = events.get("items")
        if not isinstance(items, list) or not items:
            raise ReviewError("sections.events.items 必须是非空数组")
        for index, item in enumerate(items):
            validate_event(item, f"sections.events.items[{index}]", as_of, False)


def validate_input(
    data: dict[str, Any], requested_as_of: date
) -> dict[str, dict[str, Any]]:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ReviewError(f"schema_version 必须是{SCHEMA_VERSION}")
    market_date = parse_date(data.get("market_date"), "market_date")
    input_as_of = parse_date(data.get("as_of"), "as_of")
    if input_as_of != requested_as_of:
        raise ReviewError("输入as_of与命令行as-of不一致")
    if market_date > requested_as_of:
        raise ReviewError("market_date 不能晚于 as-of")
    validate_snapshot(data, market_date, requested_as_of)
    validate_cutoff(
        data,
        parse_datetime(data["snapshot"]["cutoff_at"], "snapshot.cutoff_at"),
    )
    sections = normalized_sections(data)
    validate_sections(sections, requested_as_of, market_date)
    verification_points = data.get("verification_points", [])
    if not isinstance(verification_points, list):
        raise ReviewError("verification_points 必须是数组")
    point_ids: set[str] = set()
    for index, item in enumerate(verification_points):
        field = f"verification_points[{index}]"
        validate_verification_point(item, field, requested_as_of)
        if item["id"] in point_ids:
            raise ReviewError("verification_points.id 不能重复")
        point_ids.add(item["id"])
    qualitative_points = data.get("qualitative_verification_points", [])
    if not isinstance(qualitative_points, list):
        raise ReviewError("qualitative_verification_points 必须是数组")
    for index, item in enumerate(qualitative_points):
        validate_event(
            item,
            f"qualitative_verification_points[{index}]",
            requested_as_of,
            True,
        )
    return sections
