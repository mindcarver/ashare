#!/usr/bin/env python3
"""Generate an auditable A-share daily market review from normalized evidence."""

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from datetime import date, datetime
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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
FORBIDDEN = (
    "建议买入",
    "建议卖出",
    "目标价",
    "目标仓位",
    "建议轻仓",
    "建议半仓",
    "建议重仓",
    "建议空仓",
    "建议加仓",
    "建议减仓",
    "确定牛市",
    "确定熊市",
    "必然上涨",
    "必然下跌",
)


class ReviewError(ValueError):
    """Raised when market evidence violates the daily review contract."""


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


def value(section: dict[str, Any], metric: str) -> float | None:
    evidence = section.get("metrics", {}).get(metric)
    return float(evidence["value"]) if evidence else None


def derive_short_term_sentiment(
    sections: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    sentiment = sections["short_term_sentiment"]
    breadth = sections["breadth"]
    if sentiment["availability"] != "available":
        return {
            "state": "unknown",
            "reason": sentiment["status_reason"],
        }
    if breadth["availability"] != "available":
        return {
            "state": "unknown",
            "reason": "涨跌停宽度数据不可得，不能分类短线情绪",
        }

    limit_up = value(breadth, "limit_up")
    limit_down = value(breadth, "limit_down")
    failed = value(sentiment, "open_board_failed")
    attempts = value(sentiment, "limit_attempts")
    highest_streak = value(sentiment, "highest_streak")
    if None in (limit_up, limit_down, failed, attempts, highest_streak):
        return {
            "state": "unknown",
            "reason": "短线情绪必需指标不完整",
        }

    open_board_rate = round(failed / attempts * 100, 6)
    result: dict[str, Any] = {
        "open_board_rate_pct": open_board_rate,
        "repair_evaluated": False,
    }
    if limit_up < 20 and limit_down > 10 and highest_streak < 3:
        result.update(
            {
                "state": "ice",
                "rule": "limit_up < 20 and limit_down > 10 and highest_streak < 3",
                "evidence": f"涨停 {limit_up:.0f}，跌停 {limit_down:.0f}，最高连板 {highest_streak:.0f}",
            }
        )
        return result
    if limit_up > 80 and open_board_rate < 15 and highest_streak > 5:
        result.update(
            {
                "state": "euphoria",
                "rule": "limit_up > 80 and open_board_rate_pct < 15 and highest_streak > 5",
                "evidence": f"涨停 {limit_up:.0f}，炸板率 {open_board_rate:.2f}%，最高连板 {highest_streak:.0f}",
            }
        )
        return result
    if open_board_rate > 25:
        result.update(
            {
                "state": "divergence",
                "rule": "open_board_rate_pct > 25 and not (ice or euphoria)",
                "evidence": f"炸板率 {open_board_rate:.2f}%",
            }
        )
        return result

    previous = sentiment.get("previous_metrics")
    if previous is not None:
        previous_failed = float(previous["open_board_failed"]["value"])
        previous_attempts = float(previous["limit_attempts"]["value"])
        previous_rate = round(previous_failed / previous_attempts * 100, 6)
        previous_limit_up = float(previous["limit_up"]["value"])
        previous_limit_down = float(previous["limit_down"]["value"])
        previous_streak = float(previous["highest_streak"]["value"])
        result["repair_evaluated"] = True
        result["previous_open_board_rate_pct"] = previous_rate
        if (
            limit_up > previous_limit_up
            and limit_down < previous_limit_down
            and open_board_rate < previous_rate
            and highest_streak >= previous_streak
        ):
            result.update(
                {
                    "state": "repair",
                    "rule": "limit_up > previous_limit_up and limit_down < previous_limit_down and open_board_rate_pct < previous_open_board_rate_pct and highest_streak >= previous_highest_streak",
                    "evidence": (
                        f"涨停 {previous_limit_up:.0f}→{limit_up:.0f}，"
                        f"跌停 {previous_limit_down:.0f}→{limit_down:.0f}，"
                        f"炸板率 {previous_rate:.2f}%→{open_board_rate:.2f}%，"
                        f"最高连板 {previous_streak:.0f}→{highest_streak:.0f}"
                    ),
                }
            )
            return result

    result.update(
        {
            "state": "neutral",
            "rule": "no_predefined_state_triggered",
            "evidence": "当前数据完整但未触发预定义状态",
        }
    )
    return result


def derive(
    sections: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    derived: dict[str, Any] = {}
    signals: list[dict[str, str]] = []
    breadth = sections["breadth"]
    advances = value(breadth, "advancers")
    declines = value(breadth, "decliners")
    unchanged = value(breadth, "unchanged")
    if advances is not None and declines is not None and unchanged is not None:
        total = advances + declines + unchanged
        if total <= 0:
            raise ReviewError("上涨/下跌/平盘家数分母必须大于0")
        derived["advancer_share_pct"] = round(advances / total * 100, 6)
        derived["advance_decline_ratio"] = (
            round(advances / declines, 6) if declines > 0 else None
        )
    limit_up = value(breadth, "limit_up")
    limit_down = value(breadth, "limit_down")
    if limit_up is not None and limit_down is not None:
        derived["limit_balance"] = limit_up - limit_down
    derived["short_term_sentiment"] = derive_short_term_sentiment(sections)

    turnover = sections["turnover"]
    amount = value(turnover, "amount")
    previous = value(turnover, "previous_amount")
    average_5d = value(turnover, "avg_5d_amount")
    if amount is not None:
        derived["turnover_amount"] = amount
    if amount is not None and previous:
        derived["turnover_vs_previous_pct"] = round((amount / previous - 1) * 100, 6)
    if amount is not None and average_5d:
        derived["turnover_vs_5d_avg_pct"] = round((amount / average_5d - 1) * 100, 6)

    indices = sections["indices"].get("items", [])
    if indices:
        primary = next(item for item in indices if item["primary"])
        primary_change = float(primary["change_pct"]["value"])
        derived["primary_index"] = primary["name"]
        derived["primary_index_change_pct"] = primary_change
        if primary_change > 0 and derived.get("advancer_share_pct", 100) < 40:
            signals.append(
                {
                    "code": "index_up_breadth_narrow",
                    "label": "指数上涨但宽度偏窄",
                    "rule": "primary_index_change_pct > 0 and advancer_share_pct < 40",
                    "evidence": f"{primary['name']} {primary_change:+.2f}%，上涨家数占比 {derived['advancer_share_pct']:.2f}%",
                }
            )
        if primary_change < 0 and derived.get("advancer_share_pct", 0) > 60:
            signals.append(
                {
                    "code": "index_down_breadth_resilient",
                    "label": "指数下跌但宽度仍有韧性",
                    "rule": "primary_index_change_pct < 0 and advancer_share_pct > 60",
                    "evidence": f"{primary['name']} {primary_change:+.2f}%，上涨家数占比 {derived['advancer_share_pct']:.2f}%",
                }
            )

    sector_items = sections["sectors"].get("items", [])
    if sector_items:
        ordered = sorted(
            sector_items,
            key=lambda item: (-float(item["change_pct"]["value"]), item["id"]),
        )
        derived["leading_sector"] = ordered[0]["name"]
        derived["lagging_sector"] = ordered[-1]["name"]
    return derived, signals


def load_history_entries(history_dir: Path) -> list[dict[str, Any]]:
    if not history_dir.exists():
        return []
    entries = []
    for path in sorted(history_dir.glob("*/*.json")):
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReviewError(f"历史快照不可读：{path}: {exc}") from exc
        if not isinstance(envelope, dict) or not isinstance(envelope.get("snapshot"), dict):
            raise ReviewError(f"历史快照格式无效：{path}")
        input_sha = envelope.get("input_sha256")
        if not isinstance(input_sha, str) or len(input_sha) != 64:
            raise ReviewError(f"历史快照缺少input_sha256：{path}")
        expected_content_sha = envelope.get("snapshot_content_sha256")
        actual_content_sha = hashlib.sha256(
            json.dumps(
                envelope["snapshot"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if expected_content_sha != actual_content_sha:
            raise ReviewError(f"历史快照内容SHA不匹配：{path}")
        snapshot_as_of = parse_date(envelope["snapshot"].get("as_of"), "history.as_of")
        validate_input(envelope["snapshot"], snapshot_as_of)
        entries.append(
            {"path": path, "input_sha256": input_sha, "data": envelope["snapshot"]}
        )
    return entries


def latest_daily_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        data = entry["data"]
        market_date = require_text(data, "market_date")
        revision = data.get("snapshot", {}).get("revision")
        if not isinstance(revision, int):
            raise ReviewError(f"历史快照revision无效：{entry['path']}")
        current = latest.get(market_date)
        if current is None or revision > current["data"]["snapshot"]["revision"]:
            latest[market_date] = entry
    return [latest[key] for key in sorted(latest)]


def persist_snapshot(
    history_dir: Path,
    data: dict[str, Any],
    input_sha256: str,
    entries: list[dict[str, Any]],
) -> tuple[Path, bool]:
    duplicate = next(
        (entry for entry in entries if entry["input_sha256"] == input_sha256), None
    )
    if duplicate:
        return duplicate["path"], False

    market_date = data["market_date"]
    same_day = sorted(
        (entry for entry in entries if entry["data"]["market_date"] == market_date),
        key=lambda entry: entry["data"]["snapshot"]["revision"],
    )
    revision = data["snapshot"]["revision"]
    if same_day:
        latest = same_day[-1]
        expected_revision = latest["data"]["snapshot"]["revision"] + 1
        if revision != expected_revision:
            raise ReviewError(f"同日新修订revision必须是{expected_revision}")
        if data["snapshot"]["supersedes_sha256"] != latest["input_sha256"]:
            raise ReviewError("supersedes_sha256 必须指向同日上一修订")
    elif revision != 1:
        raise ReviewError("历史中没有同日旧快照时revision必须是1")

    target = history_dir / market_date / f"r{revision:03d}-{input_sha256[:12]}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    content_sha = hashlib.sha256(
        json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    envelope = {
        "input_sha256": input_sha256,
        "snapshot_content_sha256": content_sha,
        "snapshot": data,
    }
    target.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target, True


def percentile_rank(numbers: list[float], current: float) -> float:
    return round(sum(number <= current for number in numbers) / len(numbers) * 100, 6)


def history_metric_values(
    sections: dict[str, dict[str, Any]], derived: dict[str, Any]
) -> dict[str, float | None]:
    sentiment = derived.get("short_term_sentiment", {})
    return {
        "primary_index_change_pct": derived.get("primary_index_change_pct"),
        "advancer_share_pct": derived.get("advancer_share_pct"),
        "turnover_amount": derived.get("turnover_amount"),
        "turnover_vs_previous_pct": derived.get("turnover_vs_previous_pct"),
        "open_board_rate_pct": sentiment.get("open_board_rate_pct"),
        "limit_balance": derived.get("limit_balance"),
    }


def derive_history(
    entries: list[dict[str, Any]],
    data: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    derived: dict[str, Any],
) -> dict[str, Any]:
    prior_daily = [
        entry
        for entry in latest_daily_entries(entries)
        if entry["data"]["market_date"] < data["market_date"]
    ]
    series: list[dict[str, Any]] = []
    states: list[str] = []
    for entry in prior_daily:
        prior_sections = normalized_sections(entry["data"])
        prior_derived, _ = derive(prior_sections)
        series.append(
            {
                "market_date": entry["data"]["market_date"],
                "metrics": history_metric_values(prior_sections, prior_derived),
            }
        )
        states.append(prior_derived["short_term_sentiment"]["state"])
    current_metrics = history_metric_values(sections, derived)
    series.append({"market_date": data["market_date"], "metrics": current_metrics})

    previous = series[-2] if len(series) > 1 else None
    metric_summary: dict[str, Any] = {}
    for name, current in current_metrics.items():
        prior = previous["metrics"].get(name) if previous else None
        item = {
            "unit": VERIFICATION_UNITS[name],
            "current": current,
            "previous": prior,
            "change": round(current - prior, 6)
            if current is not None and prior is not None
            else None,
            "percentile_20d": None,
            "percentile_60d": None,
        }
        for window in (20, 60):
            values = [
                float(row["metrics"][name])
                for row in series[-window:]
                if row["metrics"].get(name) is not None
            ]
            if current is not None and len(values) >= window:
                item[f"percentile_{window}d"] = percentile_rank(values, float(current))
        metric_summary[name] = item

    current_state = derived["short_term_sentiment"]["state"]
    streak = None
    if current_state != "unknown":
        streak = 0
        for state in reversed(states + [current_state]):
            if state != current_state:
                break
            streak += 1
    return {
        "sample_size": len(series),
        "previous_market_date": previous["market_date"] if previous else None,
        "metrics": metric_summary,
        "sentiment_state_streak": streak,
    }


def verification_metric_value(
    metric: str, sections: dict[str, dict[str, Any]], derived: dict[str, Any]
) -> float | None:
    return history_metric_values(sections, derived).get(metric)


def resolve_verification_points(
    entries: list[dict[str, Any]],
    data: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    derived: dict[str, Any],
) -> list[dict[str, Any]]:
    prior = [
        entry
        for entry in latest_daily_entries(entries)
        if entry["data"]["market_date"] < data["market_date"]
    ]
    if not prior:
        return []
    previous_market_date = prior[-1]["data"]["market_date"]
    points: dict[str, dict[str, Any]] = {}
    for entry in prior:
        for point in entry["data"].get("verification_points", []):
            points[point["id"]] = point
    results = []
    operations = {
        ">": lambda observed, target: observed > target,
        ">=": lambda observed, target: observed >= target,
        "<": lambda observed, target: observed < target,
        "<=": lambda observed, target: observed <= target,
        "==": lambda observed, target: observed == target,
    }
    for point in points.values():
        if not (previous_market_date < point["event_date"] <= data["market_date"]):
            continue
        condition = point["condition"]
        observed = verification_metric_value(condition["metric"], sections, derived)
        status = "unknown"
        if observed is not None:
            status = (
                "passed"
                if operations[condition["operator"]](observed, float(condition["value"]))
                else "failed"
            )
        results.append(
            {
                "id": point["id"],
                "title": point["title"],
                "due_date": point["event_date"],
                "status": status,
                "condition": condition,
                "observed_value": observed,
                "observed_market_date": data["market_date"],
            }
        )
    return results


def coverage(sections: dict[str, dict[str, Any]]) -> dict[str, int]:
    return {
        status: sum(section["availability"] == status for section in sections.values())
        for status in ("available", "partial", "unknown")
    }


def iter_sources(data: Any):
    if isinstance(data, dict):
        if {"id", "name"} <= set(data) and (
            data.get("kind") == "derived" or "url" in data
        ):
            yield data
        for child in data.values():
            yield from iter_sources(child)
    elif isinstance(data, list):
        for child in data:
            yield from iter_sources(child)


def source_summary(data: dict[str, Any]) -> list[dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for source in iter_sources(data):
        current = sources.setdefault(
            source["id"],
            {
                "id": source["id"],
                "name": source["name"],
                "url": source.get("url"),
                "kind": source.get("kind", "external"),
                "count": 0,
            },
        )
        if (current["name"], current["url"], current["kind"]) != (
            source["name"],
            source.get("url"),
            source.get("kind", "external"),
        ):
            raise ReviewError(f"source.id存在冲突：{source['id']}")
        current["count"] += 1
    return [sources[key] for key in sorted(sources)]


def fmt_evidence(evidence: dict[str, Any]) -> str:
    number = float(evidence["value"])
    unit = evidence["unit"]
    if unit == "percent":
        return f"{number:+.2f}%"
    if unit == "CNY":
        return f"{number / 1e8:,.2f}亿元"
    if unit == "count":
        return f"{number:,.0f}"
    if unit == "index_points":
        return f"{number:,.2f}"
    return f"{number:g} {unit}"


def fmt_history_value(number: float | None, unit: str) -> str:
    if number is None:
        return "unknown"
    return fmt_evidence({"value": number, "unit": unit})


def unknown_line(section: dict[str, Any]) -> str:
    return f"> {section['availability'].upper()}：{section['status_reason']}"


def html_text(value: Any) -> str:
    return escape(str(value), quote=True)


def availability_badge(section: dict[str, Any]) -> str:
    status = section["availability"]
    labels = {"available": "可得", "partial": "部分", "unknown": "未知"}
    return f'<span class="badge badge-{status}">{labels[status]}</span>'


def value_tone(number: float | None) -> str:
    if number is None:
        return "neutral"
    return "rise" if number > 0 else "fall" if number < 0 else "neutral"


def html_evidence(evidence: dict[str, Any]) -> str:
    source = evidence["source"]
    return (
        f'{html_text(source["name"])} · 观测 {html_text(evidence["observed_at"])} · '
        f'发布 {html_text(evidence["published_at"])}'
    )


def html_metric_card(label: str, display: str, detail: str, tone: str = "neutral") -> str:
    return f'''<article class="metric-card tone-{tone}">
  <p>{html_text(label)}</p><strong>{html_text(display)}</strong><small>{html_text(detail)}</small>
</article>'''


def build_html(
    data: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    input_sha256: str,
    derived: dict[str, Any],
    signals: list[dict[str, str]],
    coverage_counts: dict[str, int],
    sources: list[dict[str, Any]],
    history: dict[str, Any],
    resolved_verifications: list[dict[str, Any]],
) -> str:
    """Build a self-contained visual report from the same validated evidence."""
    indices = sections["indices"]
    breadth = sections["breadth"]
    turnover = sections["turnover"]
    sectors = sections["sectors"]
    sentiment_section = sections["short_term_sentiment"]
    sentiment = derived["short_term_sentiment"]

    primary = None
    if indices["availability"] != "unknown":
        primary = next(item for item in indices["items"] if item["primary"])
    primary_change = float(primary["change_pct"]["value"]) if primary else None
    amount = turnover.get("metrics", {}).get("amount")
    metrics = breadth.get("metrics", {})
    advance_share = derived.get("advancer_share_pct")

    hero_cards = []
    if primary:
        hero_cards.append(html_metric_card(
            primary["name"], fmt_evidence(primary["close"]), fmt_evidence(primary["change_pct"]), value_tone(primary_change)
        ))
    if amount:
        hero_cards.append(html_metric_card(
            "全市场成交额", fmt_evidence(amount),
            f"较前值 {derived['turnover_vs_previous_pct']:+.2f}%" if "turnover_vs_previous_pct" in derived else turnover["status_reason"],
            value_tone(derived.get("turnover_vs_previous_pct")),
        ))
    if advance_share is not None:
        hero_cards.append(html_metric_card("上涨参与度", f"{advance_share:.2f}%", "上涨家数占总样本", value_tone(advance_share - 50)))
    if "limit_balance" in derived:
        hero_cards.append(html_metric_card("涨停净差", f"{derived['limit_balance']:+.0f}", "涨停家数减跌停家数", value_tone(derived["limit_balance"])))
    if not hero_cards:
        hero_cards.append(html_metric_card("市场脉搏", "未知", "缺少可得的盘面核心数据"))

    index_rows = ""
    if indices["availability"] == "unknown":
        index_rows = f'<p class="empty">{html_text(indices["status_reason"])}</p>'
    else:
        index_rows = "".join(
            f'''<div class="index-row"><span>{html_text(item["name"])}</span>
<strong>{html_text(fmt_evidence(item["close"]))}</strong>
<b class="value-{value_tone(float(item["change_pct"]["value"]))}">{html_text(fmt_evidence(item["change_pct"]))}</b>
<small>{html_evidence(item["change_pct"])}</small></div>'''
            for item in indices["items"]
        )

    breadth_chart = '<p class="empty">宽度数据不可得</p>'
    if advance_share is not None:
        breadth_chart = f'''<div class="breadth-wrap">
  <div class="donut" style="--advance:{advance_share:.4f}%"><span>{advance_share:.1f}%<small>上涨</small></span></div>
  <div class="breadth-list">
    <p><span>上涨</span><strong>{metrics["advancers"]["value"]:,}</strong></p>
    <p><span>下跌</span><strong>{metrics["decliners"]["value"]:,}</strong></p>
    <p><span>平盘</span><strong>{metrics["unchanged"]["value"]:,}</strong></p>
    <p><span>涨停 / 跌停</span><strong>{metrics["limit_up"]["value"]:,} / {metrics["limit_down"]["value"]:,}</strong></p>
  </div>
</div>'''

    state_labels = {"ice": "冰点", "euphoria": "亢奋", "divergence": "分歧", "repair": "修复", "neutral": "中性", "unknown": "未知"}
    if sentiment["state"] == "unknown":
        sentiment_html = f'<p class="empty">短线情绪未知：{html_text(sentiment["reason"])}</p>'
    else:
        sentiment_cards = [
            ("炸板率", f"{sentiment['open_board_rate_pct']:.2f}%"),
            ("最高连板", fmt_evidence(sentiment_section["metrics"]["highest_streak"])),
        ]
        if "limit_balance" in derived:
            sentiment_cards.append(("涨停净差", f"{derived['limit_balance']:+.0f}"))
        cards = "".join(
            f'<div><span>{html_text(label)}</span><strong>{html_text(number)}</strong></div>'
            for label, number in sentiment_cards
        )
        sentiment_html = f'''<div class="sentiment-state state-{html_text(sentiment["state"])}">
  <span>市场状态</span><strong>{state_labels[sentiment["state"]]}</strong>
</div><p class="rule">{html_text(sentiment["evidence"])}</p>
<div class="sentiment-kpis">{cards}</div>
<details class="method-details"><summary>查看股票池、口径与规则</summary><p class="evidence">股票池：{html_text(sentiment_section["universe"]["label"])}（{html_text(sentiment_section["universe"]["id"])}）<br />{html_text(sentiment_section["methodology"])}<br />规则：<code>{html_text(sentiment["rule"])}</code></p></details>'''

    sector_html = f'<p class="empty">{html_text(sectors["status_reason"])}</p>'
    if sectors["availability"] != "unknown":
        ordered = sorted(sectors["items"], key=lambda item: (-float(item["change_pct"]["value"]), item["id"]))
        max_change = max(abs(float(item["change_pct"]["value"])) for item in ordered) or 1
        winners = ordered[:10]
        losers = sorted(ordered, key=lambda item: (float(item["change_pct"]["value"]), item["id"]))[:10]

        def sector_rows(items: list[dict[str, Any]]) -> str:
            rows = []
            for item in items:
                change = float(item["change_pct"]["value"])
                width = abs(change) / max_change * 100
                side = "positive" if change >= 0 else "negative"
                rows.append(f'''<div class="sector-row"><span>{html_text(item["name"])}</span><div class="bar-track {side}"><i style="width:{width:.2f}%"></i></div><b class="value-{value_tone(change)}">{html_text(fmt_evidence(item["change_pct"]))}</b></div>''')
            return "".join(rows)

        up_count = sum(float(item["change_pct"]["value"]) > 0 for item in ordered)
        down_count = sum(float(item["change_pct"]["value"]) < 0 for item in ordered)
        flat_count = len(ordered) - up_count - down_count
        full_rows = sector_rows(ordered)
        featured_rows = sector_rows(winners)
        if any(item["id"] not in {winner["id"] for winner in winners} for item in losers):
            featured_rows += '<p class="sector-divider">跌幅靠前</p>' + sector_rows(losers)
        sector_html = f'''<p class="section-note">{html_text(sectors["classification"])} · {html_text(sectors["status_reason"])}</p>
<div class="sector-summary"><span>覆盖 {len(ordered)} 个行业</span><span class="value-rise">上涨 {up_count}</span><span class="value-fall">下跌 {down_count}</span><span>平盘 {flat_count}</span></div>
<p class="sector-divider">涨幅靠前</p>{featured_rows}
<details class="full-list"><summary>展开完整 {len(ordered)} 个行业榜单</summary>{full_rows}</details>'''

    def evidence_rows(section_name: str, description_key: str) -> str:
        section = sections[section_name]
        if section["availability"] == "unknown":
            return f'<p class="empty">{html_text(section["status_reason"])}</p>'
        rows = []
        for item in section["items"]:
            evidence = item["metric"]
            method = f' · {html_text(item["method_category"])}' if section_name == "funds" else ""
            rows.append(f'''<li><strong>{html_text(item["name"])} · {html_text(fmt_evidence(evidence))}</strong><span>{html_text(item[description_key])}</span><small>{html_evidence(evidence)}{method}</small></li>''')
        return '<ul class="evidence-list">' + "".join(rows) + "</ul>"

    event_items = []
    status_labels = {"passed": "已验证", "failed": "未成立", "unknown": "待补证"}
    event_items.extend(
        f'<li class="resolved {html_text(item["status"])}"><time>{html_text(item["observed_market_date"])}</time>{html_text(item["title"])}<small>上期验证 · {status_labels[item["status"]]} · 观察值 {html_text(fmt_history_value(item["observed_value"], item["condition"]["unit"]))}</small></li>'
        for item in resolved_verifications
    )
    if sections["events"]["availability"] != "unknown":
        event_items.extend(f'<li><time>{html_text(item["event_date"])}</time>{html_text(item["title"])}<small>{html_text(item["source"]["name"])}</small></li>' for item in sections["events"]["items"])
    event_items.extend(
        f'<li class="future"><time>{html_text(item["event_date"])}</time>{html_text(item["title"])}<small>后续验证 · {html_text(item["condition"]["metric"])} {html_text(item["condition"]["operator"])} {html_text(item["condition"]["value"])} {html_text(item["condition"]["unit"])} · {html_text(item["source"]["name"])}</small></li>'
        for item in data.get("verification_points", [])
    )
    event_items.extend(
        f'<li class="future qualitative"><time>{html_text(item["event_date"])}</time>{html_text(item["title"])}<small>定性观察点 · 不自动结算 · {html_text(item["source"]["name"])}</small></li>'
        for item in data.get("qualitative_verification_points", [])
    )
    events_html = '<ul class="timeline">' + "".join(event_items) + "</ul>" if event_items else '<p class="empty">暂无可得事件或验证点</p>'

    signal_html = "".join(f'<li><strong>{html_text(signal["label"])}：</strong>{html_text(signal["evidence"])}<small>{html_text(signal["rule"])}</small></li>' for signal in signals)
    if not signal_html:
        signal_html = '<li>当前输入未触发预定义的指数—宽度背离规则。</li>'
    limits = "".join(f'<li>{html_text(name)}：{html_text(section["availability"])}，{html_text(section["status_reason"])}</li>' for name, section in sections.items() if section["availability"] != "available")

    source_row_parts = []
    for source in sources:
        location = "派生证据"
        if source["url"]:
            url = html_text(source["url"])
            location = f'<a href="{url}" rel="noreferrer" target="_blank">{url}</a>'
        source_row_parts.append(
            f'<tr><td>{html_text(source["name"])}</td><td>{location}</td><td>{source["count"]}</td></tr>'
        )
    source_rows = "".join(source_row_parts)
    all_unknown = coverage_counts["unknown"] == len(SECTION_NAMES)
    content = '<div class="no-data">该日期没有可得的盘面数据；未绘制任何零值替代图表。</div>' if all_unknown else f'''<section class="dashboard-grid" aria-label="盘面核心数据"><article class="panel wide"><div class="panel-head"><h2>主要指数</h2>{availability_badge(indices)}</div>{index_rows}</article><article class="panel"><div class="panel-head"><h2>市场宽度</h2>{availability_badge(breadth)}</div>{breadth_chart}</article><article class="panel"><div class="panel-head"><h2>短线情绪</h2>{availability_badge(sentiment_section)}</div>{sentiment_html}</article><article class="panel wide"><div class="panel-head"><h2>板块温度</h2>{availability_badge(sectors)}</div>{sector_html}</article><article class="panel"><div class="panel-head"><h2>资金证据</h2>{availability_badge(sections["funds"])}</div>{evidence_rows("funds", "methodology")}</article><article class="panel"><div class="panel-head"><h2>风格结构</h2>{availability_badge(sections["style"])}</div>{evidence_rows("style", "interpretation")}</article><article class="panel wide"><div class="panel-head"><h2>事件与验证点</h2>{availability_badge(sections["events"])}</div>{events_html}</article></section>'''
    if not all_unknown and data.get("verification_points"):
        next_point = min(data["verification_points"], key=lambda item: item["event_date"])
        remaining = len(data["verification_points"]) - 1
        suffix = f"；另有 {remaining} 项" if remaining else ""
        content = f'''<aside class="verify-strip" aria-label="下一交易日验证"><span>下一交易日验证</span><strong>{html_text(next_point["event_date"])} · {html_text(next_point["title"])}{suffix}</strong><small>{html_text(next_point["source"]["name"])} · 已在信息截止日前公开</small></aside>''' + content

    breadth_history = history["metrics"]["advancer_share_pct"]
    turnover_history = history["metrics"]["turnover_amount"]
    history_strip = f'''<aside class="history-strip" aria-label="连续历史"><span>连续历史</span><strong>{history["sample_size"]} 个交易日 · 前值 {html_text(history["previous_market_date"] or "unknown")}</strong><small>上涨参与度20日分位 {html_text(breadth_history["percentile_20d"] if breadth_history["percentile_20d"] is not None else "样本不足")} · 成交额20日分位 {html_text(turnover_history["percentile_20d"] if turnover_history["percentile_20d"] is not None else "样本不足")}</small></aside>'''
    content = history_strip + content

    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1" /><meta name="robots" content="noindex,nofollow" /><title>A股每日盘面复盘 · {html_text(data["market_date"])}</title><style>
:root{{--ink:#13211f;--paper:#f6f1e7;--paper-2:#eee6d7;--line:#d8cdbb;--red:#bf332d;--green:#19724b;--gold:#ba8a35;--muted:#756f66}}*{{box-sizing:border-box}}body{{margin:0;background:#18221f;color:var(--ink);font-family:"Noto Serif SC","Songti SC",STSong,serif;overflow-x:hidden}}body:before{{content:"";position:fixed;inset:0;pointer-events:none;opacity:.15;background-image:linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.04) 1px,transparent 1px);background-size:24px 24px}}main{{max-width:1180px;margin:auto;padding:32px 20px 56px}}.masthead{{color:#f8f2e6;border-bottom:1px solid rgba(248,242,230,.25);padding:0 0 24px;display:flex;justify-content:space-between;gap:24px;align-items:end}}.eyebrow{{font:700 11px/1 "SFMono-Regular",Consolas,monospace;letter-spacing:.18em;color:#e3bc70;margin:0 0 12px}}h1,h2,p{{margin:0}}h1{{font-size:clamp(34px,6vw,68px);line-height:.95;letter-spacing:-.06em}}.asof{{font-size:14px;color:#cfc5b4;line-height:1.65;text-align:right}}.coverage{{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}}.badge{{font:700 11px/1 "SFMono-Regular",Consolas,monospace;padding:6px 8px;border-radius:999px;letter-spacing:.04em}}.badge-available{{background:#d8eedf;color:#155836}}.badge-partial{{background:#efe4c7;color:#725210}}.badge-unknown{{background:#edd8d2;color:#8a2c27}}.hero-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:10px}}.metric-card,.panel{{background:var(--paper);border:1px solid var(--line);box-shadow:5px 5px 0 rgba(12,18,16,.25)}}.metric-card{{min-width:0;min-height:132px;padding:18px;display:flex;flex-direction:column;justify-content:space-between;border-top:4px solid var(--gold);overflow:hidden}}.metric-card p,.section-note,.evidence,small{{color:var(--muted);font-size:12px;line-height:1.5}}.metric-card strong{{font-family:"SFMono-Regular",Consolas,monospace;font-size:27px;letter-spacing:-.06em;overflow-wrap:anywhere}}.tone-rise{{border-top-color:var(--red)}}.tone-fall{{border-top-color:var(--green)}}.dashboard-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.panel{{padding:20px;min-width:0}}.wide{{grid-column:span 2}}.panel-head{{display:flex;justify-content:space-between;gap:12px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:14px}}h2{{font-size:19px;letter-spacing:-.03em}}.index-row{{display:grid;grid-template-columns:1.2fr .8fr .55fr 1.75fr;gap:10px;padding:11px 0;border-bottom:1px solid rgba(216,205,187,.55);align-items:baseline}}.index-row strong,.index-row b,.sector-row b{{font-family:"SFMono-Regular",Consolas,monospace}}.value-rise{{color:var(--red)}}.value-fall{{color:var(--green)}}.value-neutral{{color:var(--muted)}}.breadth-wrap{{display:flex;gap:22px;align-items:center}}.donut{{width:142px;aspect-ratio:1;border-radius:50%;background:conic-gradient(var(--red) 0 var(--advance),var(--green) var(--advance) 100%);position:relative;display:grid;place-items:center;flex:none}}.donut:before{{content:"";position:absolute;width:72%;aspect-ratio:1;border-radius:50%;background:var(--paper)}}.donut span{{position:relative;text-align:center;font:700 25px/1 "SFMono-Regular",Consolas,monospace}}.donut small{{display:block;font:11px/1.5 "Noto Serif SC",serif}}.breadth-list{{width:100%}}.breadth-list p{{display:flex;justify-content:space-between;border-bottom:1px solid rgba(216,205,187,.5);padding:7px 0;font-size:13px}}.breadth-list strong{{font-family:"SFMono-Regular",Consolas,monospace}}.sentiment-state{{display:flex;justify-content:space-between;align-items:baseline;padding:11px 0 7px;border-bottom:1px solid var(--line)}}.sentiment-state strong{{font-size:30px;color:var(--gold)}}.state-ice strong{{color:#3c6294}}.state-euphoria strong{{color:var(--red)}}.state-divergence strong{{color:#a45729}}.state-repair strong{{color:var(--green)}}.rule{{font-size:14px;line-height:1.7;margin:12px 0}}dl{{display:grid;grid-template-columns:1fr auto;gap:8px;margin:12px 0;font-size:13px}}dd{{margin:0;font-family:"SFMono-Regular",Consolas,monospace}}.sector-row{{display:grid;grid-template-columns:74px 1fr 70px;gap:10px;align-items:center;margin:13px 0;font-size:13px}}.bar-track{{height:9px;background:#e5dac7;display:flex}}.bar-track.positive{{justify-content:flex-start}}.bar-track.negative{{justify-content:flex-end}}.bar-track i{{height:100%;background:var(--red)}}.bar-track.negative i{{background:var(--green)}}.evidence-list,.timeline,.signal-list{{margin:0;padding:0;list-style:none}}.evidence-list li,.timeline li{{padding:10px 0;border-bottom:1px solid rgba(216,205,187,.55);display:grid;gap:3px}}.evidence-list span{{font-size:12px;line-height:1.5}}.timeline time{{font:700 11px/1 "SFMono-Regular",Consolas,monospace;color:var(--gold)}}.future time{{color:var(--green)}}.signal-area{{margin-top:10px;background:#e3d4bc;padding:20px;border-left:5px solid var(--gold)}}.signal-list li{{margin:7px 0;line-height:1.6}}.signal-list small{{display:block;margin-left:0}}.limits{{margin-top:14px;font-size:12px;color:#5f584e}}.source-box{{margin-top:10px;background:var(--paper-2);padding:20px;overflow:auto}}table{{border-collapse:collapse;width:100%;font-size:12px}}td,th{{text-align:left;padding:9px;border-bottom:1px solid var(--line)}}a{{color:#245d58;word-break:break-all}}.empty,.no-data{{color:var(--muted);line-height:1.7}}.no-data{{padding:72px 20px;text-align:center;background:var(--paper);border:1px solid var(--line);font-size:17px}}footer{{margin-top:20px;color:#cfc5b4;font-size:12px;line-height:1.7}}@media(max-width:760px){{main{{padding:22px 14px 40px}}.masthead{{display:block}}.asof{{text-align:left;margin-top:16px}}.hero-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.metric-card{{min-height:112px;padding:15px}}.metric-card strong{{font-size:20px}}.dashboard-grid{{grid-template-columns:1fr}}.wide{{grid-column:auto}}.index-row{{grid-template-columns:1fr auto;gap:5px}}.index-row span{{grid-column:1;grid-row:1}}.index-row strong{{grid-column:2;grid-row:1}}.index-row b{{grid-column:1;grid-row:2}}.index-row small{{grid-column:1/-1;grid-row:3}}.breadth-wrap{{align-items:flex-start;gap:14px}}.donut{{width:118px}}}}
</style></head><body><main><header class="masthead"><div><p class="eyebrow">A-SHARE / DAILY INTELLIGENCE</p><h1>市场脉搏</h1></div><p class="asof">交易日 {html_text(data["market_date"])}<br />信息截止 {html_text(data["as_of"])}<br />{html_text(data["snapshot"]["type"])} · 修订 {data["snapshot"]["revision"]}<br />输入指纹 {html_text(input_sha256[:12])}</p></header><div class="coverage">{availability_badge({"availability": "available"})} {coverage_counts["available"]} 个章节 · {availability_badge({"availability": "partial"})} {coverage_counts["partial"]} 个章节 · {availability_badge({"availability": "unknown"})} {coverage_counts["unknown"]} 个章节</div><section class="hero-grid" aria-label="市场脉搏摘要">{"".join(hero_cards)}</section>{content}<section class="signal-area"><div class="panel-head"><h2>结构信号与限制</h2><span>证据优先</span></div><ul class="signal-list">{signal_html}</ul>{f'<ul class="limits">{limits}</ul>' if limits else ''}</section><section class="source-box"><div class="panel-head"><h2>来源汇总</h2><span>{len(sources)} 个来源</span></div><table><thead><tr><th>来源</th><th>URL</th><th>使用次数</th></tr></thead><tbody>{source_rows}</tbody></table></section><footer>本报告只描述输入证据和显式规则，不构成投资建议。短线情绪状态不是仓位、交易或收益预测。</footer></main></body></html>'''


def build_markdown(
    data: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    input_sha256: str,
    derived: dict[str, Any],
    signals: list[dict[str, str]],
    coverage_counts: dict[str, int],
    sources: list[dict[str, Any]],
    history: dict[str, Any],
    resolved_verifications: list[dict[str, Any]],
) -> str:
    lines = [
        f"# A股每日盘面复盘｜{data['market_date']}",
        "",
        f"- 截止日期：{data['as_of']}",
        f"- 快照：{data['snapshot']['type']} / 修订 {data['snapshot']['revision']} / 截止 {data['snapshot']['cutoff_at']}",
        f"- 输入SHA-256：`{input_sha256}`",
        f"- 覆盖：可得{coverage_counts['available']} / 部分{coverage_counts['partial']} / 未知{coverage_counts['unknown']}",
        "- 结论属性：盘面证据与结构观察，不构成投资建议",
        "",
    ]
    if data.get("legacy_migration"):
        lines.append(
            "- 兼容归一化："
            + "；".join(data["legacy_migration"].get("warnings", []))
        )
        lines.append("")
    if coverage_counts["unknown"] == len(SECTION_NAMES):
        lines.extend(["## 无可得盘面数据", "", "本次八个盘面章节均为unknown，不能形成全市场强弱结论。", ""])

    lines.extend(["## 连续历史", ""])
    lines.append(
        f"- 样本：{history['sample_size']} 个交易日；前一交易日：{history['previous_market_date'] or 'unknown'}；当前情绪状态连续 {history['sentiment_state_streak'] if history['sentiment_state_streak'] is not None else 'unknown'} 日。"
    )
    lines.extend(["", "| 指标 | 当前 | 前值 | 变化 | 20日分位 | 60日分位 |", "|---|---:|---:|---:|---:|---:|"])
    history_labels = {
        "primary_index_change_pct": "主要指数涨跌幅",
        "advancer_share_pct": "上涨参与度",
        "turnover_amount": "成交额",
        "open_board_rate_pct": "炸板率",
        "limit_balance": "涨停净差",
    }
    for metric, label in history_labels.items():
        item = history["metrics"][metric]
        percentile_20d = (
            f"{item['percentile_20d']:.2f}%"
            if item["percentile_20d"] is not None
            else "样本不足"
        )
        percentile_60d = (
            f"{item['percentile_60d']:.2f}%"
            if item["percentile_60d"] is not None
            else "样本不足"
        )
        lines.append(
            f"| {label} | {fmt_history_value(item['current'], item['unit'])} | {fmt_history_value(item['previous'], item['unit'])} | {fmt_history_value(item['change'], item['unit'])} | {percentile_20d} | {percentile_60d} |"
        )
    lines.append("")

    lines.extend(["## 一、主要指数", ""])
    indices = sections["indices"]
    if indices["availability"] == "unknown":
        lines.extend([unknown_line(indices), ""])
    else:
        lines.extend(["| 指数 | 收盘 | 涨跌幅 | 观察日 | 来源 |", "|---|---:|---:|---|---|"])
        for item in indices["items"]:
            evidence = item["change_pct"]
            lines.append(
                f"| {item['name']} | {fmt_evidence(item['close'])} | {fmt_evidence(evidence)} | {evidence['observed_at']} | {evidence['source']['name']} |"
            )
        lines.append("")

    lines.extend(["## 二、市场宽度", ""])
    breadth = sections["breadth"]
    if breadth["availability"] == "unknown":
        lines.extend([unknown_line(breadth), ""])
    else:
        lines.extend(["| 指标 | 数值 | 观察日 | 来源 |", "|---|---:|---|---|"])
        for name, label in (
            ("advancers", "上涨家数"),
            ("decliners", "下跌家数"),
            ("unchanged", "平盘家数"),
            ("limit_up", "涨停家数"),
            ("limit_down", "跌停家数"),
        ):
            evidence = breadth.get("metrics", {}).get(name)
            if evidence:
                lines.append(
                    f"| {label} | {fmt_evidence(evidence)} | {evidence['observed_at']} | {evidence['source']['name']} |"
                )
        if "advancer_share_pct" in derived:
            lines.append("")
            lines.append(f"上涨家数占比：{derived['advancer_share_pct']:.2f}%")
            ratio = derived.get("advance_decline_ratio")
            lines.append(f"涨跌家数比：{ratio:.2f}" if ratio is not None else "涨跌家数比：无法计算（下跌家数为0）")
        lines.append("")

    lines.extend(["## 三、短线情绪观察", ""])
    sentiment_section = sections["short_term_sentiment"]
    sentiment = derived["short_term_sentiment"]
    if sentiment["state"] == "unknown":
        lines.extend([f"> UNKNOWN：{sentiment['reason']}", ""])
    else:
        labels = {
            "ice": "冰点",
            "euphoria": "亢奋",
            "divergence": "分歧",
            "repair": "修复",
            "neutral": "中性",
        }
        metrics = sentiment_section["metrics"]
        lines.extend(
            [
                f"- 股票池：{sentiment_section['universe']['label']}（{sentiment_section['universe']['id']}）",
                f"- 方法：{sentiment_section['methodology']}",
                f"- 炸板率：{sentiment['open_board_rate_pct']:.2f}%（{fmt_evidence(metrics['open_board_failed'])} / {fmt_evidence(metrics['limit_attempts'])}）",
                f"- 最高连板：{fmt_evidence(metrics['highest_streak'])}",
                f"- 状态：{labels[sentiment['state']]}；规则：`{sentiment['rule']}`。",
                f"- 依据：{sentiment['evidence']}。",
            ]
        )
        if not sentiment["repair_evaluated"]:
            lines.append("- 修复：未评估（缺少完整的前一可比交易日指标）。")
        lines.append("")

    lines.extend(["## 四、成交与流动性", ""])
    turnover = sections["turnover"]
    if turnover["availability"] == "unknown":
        lines.extend([unknown_line(turnover), ""])
    else:
        amount = turnover["metrics"].get("amount")
        if amount:
            lines.append(f"- 当日成交额：{fmt_evidence(amount)}")
        if "turnover_vs_previous_pct" in derived:
            lines.append(f"- 较前值：{derived['turnover_vs_previous_pct']:+.2f}%")
        if "turnover_vs_5d_avg_pct" in derived:
            lines.append(f"- 较5日均值：{derived['turnover_vs_5d_avg_pct']:+.2f}%")
        lines.extend([f"- 覆盖说明：{turnover['status_reason']}", ""])

    lines.extend(["## 五、板块表现", ""])
    sectors = sections["sectors"]
    if sectors["availability"] == "unknown":
        lines.extend([unknown_line(sectors), ""])
    else:
        ordered = sorted(sectors["items"], key=lambda item: (-float(item["change_pct"]["value"]), item["id"]))
        lines.extend([
            f"分类体系：{sectors['classification']}；覆盖状态：{sectors['availability']}。",
            "",
            "| 板块 | 涨跌幅 | 观察日 | 来源 |",
            "|---|---:|---|---|",
        ])
        for item in ordered:
            evidence = item["change_pct"]
            lines.append(
                f"| {item['name']} | {fmt_evidence(evidence)} | {evidence['observed_at']} | {evidence['source']['name']} |"
            )
        lines.append("")

    for section_name, heading, explanation in (
        ("funds", "六、资金证据", "methodology"),
        ("style", "七、风格结构", "interpretation"),
    ):
        section = sections[section_name]
        lines.extend([f"## {heading}", ""])
        if section["availability"] == "unknown":
            lines.extend([unknown_line(section), ""])
            continue
        method_heading = "证据类别 | " if section_name == "funds" else ""
        lines.extend([f"| 项目 | 数值 | {method_heading}方法/解释 | 观察日 | 来源 |", f"|---|---:|{'---|' if section_name == 'funds' else ''}---|---|---|"])
        for item in section["items"]:
            evidence = item["metric"]
            method_cell = f"{item['method_category']} | " if section_name == "funds" else ""
            lines.append(
                f"| {item['name']} | {fmt_evidence(evidence)} | {method_cell}{item[explanation]} | {evidence['observed_at']} | {evidence['source']['name']} |"
            )
        lines.append("")

    lines.extend(["## 八、事件与验证点", ""])
    events = sections["events"]
    if events["availability"] == "unknown":
        lines.extend([unknown_line(events), ""])
    else:
        for item in events["items"]:
            lines.append(f"- {item['event_date']}｜{item['title']}｜{item['source']['name']}")
        lines.append("")
    if resolved_verifications:
        lines.append("上一期验证结果：")
        lines.append("")
        status_labels = {"passed": "成立", "failed": "未成立", "unknown": "无法判断"}
        for item in resolved_verifications:
            observed = fmt_history_value(
                item["observed_value"], item["condition"]["unit"]
            )
            lines.append(
                f"- {status_labels[item['status']]}｜{item['title']}｜观察值 {observed}（{item['observed_market_date']}）"
            )
        lines.append("")
    if data.get("verification_points"):
        lines.append("后续验证点：")
        lines.append("")
    if data.get("qualitative_verification_points"):
        lines.append("定性观察点（不自动结算）：")
        lines.append("")
        for item in data["qualitative_verification_points"]:
            lines.append(
                f"- {item['event_date']}｜{item['title']}｜{item['source']['name']}"
            )
        lines.append("")
        for item in data["verification_points"]:
            condition = item["condition"]
            lines.append(
                f"- {item['event_date']}｜{item['title']}｜`{condition['metric']} {condition['operator']} {condition['value']} {condition['unit']}`｜{item['source']['name']}"
            )
        lines.append("")

    lines.extend(["## 九、结构信号与限制", ""])
    if signals:
        for signal in signals:
            lines.append(f"- {signal['label']}：{signal['evidence']}；规则：`{signal['rule']}`。")
    else:
        lines.append("- 当前输入未触发预定义的指数—宽度背离规则。")
    lines.append("")
    for name in SECTION_NAMES:
        section = sections[name]
        if section["availability"] != "available":
            lines.append(f"- {name}：{section['availability']}，{section['status_reason']}")
    lines.extend(["", "## 十、来源汇总", "", "| 来源 | URL | 使用次数 |", "|---|---|---:|"])
    for source in sources:
        lines.append(f"| {source['name']} | {source['url'] or '派生证据'} | {source['count']} |")
    lines.extend(["", "---", "", "本报告只描述输入证据和显式规则，不构成投资建议。", ""])
    report = "\n".join(lines)
    for phrase in FORBIDDEN:
        if phrase in report:
            raise ReviewError(f"输出包含禁止的投资指令：{phrase}")
    return report


def generate(
    data: dict[str, Any],
    input_sha256: str,
    requested_as_of: date,
    history_entries: list[dict[str, Any]] | None = None,
):
    history_entries = history_entries or []
    sections = validate_input(data, requested_as_of)
    derived, signals = derive(sections)
    history = derive_history(history_entries, data, sections, derived)
    resolved_verifications = resolve_verification_points(
        history_entries, data, sections, derived
    )
    coverage_counts = coverage(sections)
    sources = source_summary(data)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "run": {
            "market_date": data["market_date"],
            "as_of": requested_as_of.isoformat(),
            "input_sha256": input_sha256,
            "snapshot": data["snapshot"],
        },
        "coverage": coverage_counts,
        "derived": derived,
        "signals": signals,
        "history": history,
        "resolved_verifications": resolved_verifications,
        "legacy_migration": data.get("legacy_migration"),
        "sections": {
            name: {
                "availability": section["availability"],
                "status_reason": section["status_reason"],
            }
            for name, section in sections.items()
        },
        "source_summary": sources,
    }
    markdown = build_markdown(
        data,
        sections,
        input_sha256,
        derived,
        signals,
        coverage_counts,
        sources,
        history,
        resolved_verifications,
    )
    html = build_html(
        data,
        sections,
        input_sha256,
        derived,
        signals,
        coverage_counts,
        sources,
        history,
        resolved_verifications,
    )
    html = html.replace(
        "</head>",
        """<style>
.verify-strip,.history-strip{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;margin:0 0 10px;padding:14px 18px;background:#dfe8df;border:1px solid #98af9c;border-left:5px solid var(--green)}
.history-strip{background:#e8e1d3;border-color:#bcae95;border-left-color:var(--gold)}.verify-strip span,.history-strip span{font:700 11px/1 "SFMono-Regular",Consolas,monospace;letter-spacing:.08em;color:#276342}.history-strip span{color:#765713}.verify-strip strong,.history-strip strong{font-size:15px}.verify-strip small,.history-strip small{white-space:nowrap}.resolved.passed small{color:var(--green)}.resolved.failed small{color:var(--red)}
.sentiment-kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:12px 0}.sentiment-kpis div{padding:9px;background:#eee6d7;border-top:2px solid var(--gold)}.sentiment-kpis span{display:block;color:var(--muted);font-size:11px}.sentiment-kpis strong{display:block;margin-top:3px;font-family:"SFMono-Regular",Consolas,monospace;font-size:19px}.method-details,.full-list{margin-top:12px;border-top:1px dashed var(--line);padding-top:10px}.method-details summary,.full-list summary{cursor:pointer;color:#275b55;font-weight:700}.sector-summary{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0;font:700 11px/1.4 "SFMono-Regular",Consolas,monospace;color:var(--muted)}.sector-divider{margin:16px 0 6px;font:700 11px/1 "SFMono-Regular",Consolas,monospace;letter-spacing:.08em;color:var(--muted);text-transform:uppercase}.full-list[open]{padding-top:14px}.full-list summary{margin-bottom:12px}
@media(max-width:620px){.hero-grid{grid-template-columns:1fr}.metric-card strong{font-size:24px}.index-row{display:block}.index-row strong,.index-row b,.index-row small{display:block;margin-top:4px}.verify-strip,.history-strip{grid-template-columns:1fr;gap:5px}.verify-strip small,.history-strip small{white-space:normal}.sentiment-kpis{grid-template-columns:repeat(3,minmax(0,1fr))}.sentiment-kpis strong{font-size:16px}.sector-row{grid-template-columns:68px 1fr 58px;gap:7px}}
</style></head>""",
        1,
    )
    return markdown, summary, html


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="可审计的A股每日盘面复盘生成器")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    parser.add_argument("--html-out", type=Path, help="可选静态 HTML 可视化输出路径")
    parser.add_argument("--history-dir", type=Path, help="可选版本化历史快照目录")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        requested_as_of = parse_date(args.as_of, "as-of")
        data, input_sha256 = load_input(args.input)
        history_entries = load_history_entries(args.history_dir) if args.history_dir else []
        markdown, summary, html = generate(
            data, input_sha256, requested_as_of, history_entries
        )
        history_path = None
        history_appended = None
        if args.history_dir:
            history_path, history_appended = persist_snapshot(
                args.history_dir, data, input_sha256, history_entries
            )
            summary["run"]["history_path"] = str(history_path)
            summary["run"]["history_appended"] = history_appended
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if args.html_out:
            args.html_out.parent.mkdir(parents=True, exist_ok=True)
            args.html_out.write_text(html, encoding="utf-8")
        result = {"output": str(args.output), "summary": str(args.summary_out)}
        if args.html_out:
            result["html"] = str(args.html_out)
        if history_path:
            result["history"] = str(history_path)
            result["history_appended"] = history_appended
        print(
            json.dumps(result, ensure_ascii=False, sort_keys=True)
        )
        return 0
    except (ReviewError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
