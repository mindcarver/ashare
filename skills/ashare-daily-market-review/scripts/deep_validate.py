#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.3 深度分析层校验。

深度层放在顶层 ``deep_analysis``，不进入基础章节覆盖计数。所有组件均可选；
存在才校验，缺失绝不回填。资金迁移只允许表达同日共现候选，不能声明因果迁移。
"""

import math

from datetime import date
from typing import Any

from evidence import (
    require_market_date,
    validate_event,
    validate_evidence,
    validate_source,
    validate_window,
)
from schema import (
    AVAILABILITY,
    DEEP_COMPONENTS,
    DEEP_SECURITY_ROLES,
    FUND_FLOW_WINDOWS,
    FUND_METHODS,
    ReviewError,
    SENTIMENT_STATES,
    VERIFICATION_UNITS_BY_SCOPE,
    parse_date,
    parse_datetime,
    require_text,
)


LIQUIDITY_THRESHOLD_KEYS = {
    "volume_ratio_min",
    "consecutive_days_min",
    "ma20_distance_min_pct",
    "daily_change_min_pct",
    "advancer_share_min_pct",
    "limit_up_min",
    "limit_down_max",
    "promotion_rate_min_pct",
}


def _component(data: dict[str, Any], name: str) -> dict[str, Any] | None:
    deep = data.get("deep_analysis")
    if deep is None:
        return None
    if not isinstance(deep, dict):
        raise ReviewError("deep_analysis 必须是object")
    unknown = set(deep) - set(DEEP_COMPONENTS)
    if unknown:
        raise ReviewError(f"deep_analysis 含不受支持组件：{sorted(unknown)}")
    component = deep.get(name)
    if component is None:
        return None
    if not isinstance(component, dict):
        raise ReviewError(f"deep_analysis.{name} 必须是object")
    if component.get("availability") not in AVAILABILITY:
        raise ReviewError(f"deep_analysis.{name}.availability 不受支持")
    require_text(component, "status_reason", f"deep_analysis.{name}")
    if component["availability"] == "unknown" and set(component) - {
        "availability",
        "status_reason",
    }:
        raise ReviewError(f"deep_analysis.{name} 标记unknown时不能携带分析数据")
    return component


def _validate_current_evidence(
    evidence: Any,
    field: str,
    as_of: date,
    market_date: date,
    unit: str,
    constraint: str = "any",
) -> None:
    validate_evidence(evidence, field, as_of, unit, constraint)
    require_market_date(evidence, field, market_date)


def _validate_datetime_evidence(
    evidence: Any,
    field: str,
    as_of: date,
    market_date: date,
) -> Any:
    if not isinstance(evidence, dict):
        raise ReviewError(f"{field} 必须是object")
    value = parse_datetime(evidence.get("value"), f"{field}.value")
    if value.date() != market_date:
        raise ReviewError(f"{field}.value 必须落在market_date")
    if parse_date(evidence.get("observed_at"), f"{field}.observed_at") != market_date:
        raise ReviewError(f"{field}.observed_at 必须等于market_date")
    if parse_date(evidence.get("published_at"), f"{field}.published_at") > as_of:
        raise ReviewError(f"{field}.published_at 晚于as-of")
    parse_datetime(evidence.get("fetched_at"), f"{field}.fetched_at")
    validate_source(evidence.get("source"), field)
    return value


def validate_security_details(
    data: dict[str, Any], as_of: date, market_date: date
) -> None:
    component = _component(data, "security_details")
    if component is None or component["availability"] == "unknown":
        return
    items = component.get("items")
    if not isinstance(items, list) or not items:
        raise ReviewError("deep_analysis.security_details.items 必须是非空数组")
    codes: set[str] = set()
    for index, item in enumerate(items):
        field = f"deep_analysis.security_details.items[{index}]"
        if not isinstance(item, dict):
            raise ReviewError(f"{field} 必须是object")
        code = require_text(item, "code", field)
        require_text(item, "name", field)
        if code in codes:
            raise ReviewError("security_details.code 不能重复")
        codes.add(code)
        roles = item.get("roles")
        if not isinstance(roles, list) or not roles or not set(roles) <= DEEP_SECURITY_ROLES:
            raise ReviewError(f"{field}.roles 不受支持或为空")
        if "change_pct" in item:
            _validate_current_evidence(
                item["change_pct"], f"{field}.change_pct", as_of, market_date, "percent"
            )
        if "streak" in item:
            streak = item["streak"]
            if isinstance(streak, bool) or not isinstance(streak, int) or streak < 1:
                raise ReviewError(f"{field}.streak 必须是正整数")

        windows = item.get("fund_flow_windows", [])
        if not isinstance(windows, list):
            raise ReviewError(f"{field}.fund_flow_windows 必须是数组")
        seen_windows: set[int] = set()
        for position, window_item in enumerate(windows):
            sub = f"{field}.fund_flow_windows[{position}]"
            if not isinstance(window_item, dict):
                raise ReviewError(f"{sub} 必须是object")
            window = window_item.get("window")
            validate_window(window, sub, market_date)
            days = window["trading_days"]
            if days not in FUND_FLOW_WINDOWS:
                raise ReviewError(f"{sub}.window.trading_days 只能是1/3/5/10")
            if days in seen_windows:
                raise ReviewError(f"{field}.fund_flow_windows 窗口不能重复")
            seen_windows.add(days)
            _validate_current_evidence(
                window_item.get("metric"), f"{sub}.metric", as_of, market_date, "CNY"
            )
            if window_item.get("method_category") not in FUND_METHODS:
                raise ReviewError(f"{sub}.method_category 不受支持")

        seal = item.get("seal_structure")
        if seal is not None:
            if not isinstance(seal, dict):
                raise ReviewError(f"{field}.seal_structure 必须是object")
            first = last = None
            if "first_sealed_at" in seal:
                first = _validate_datetime_evidence(
                    seal["first_sealed_at"],
                    f"{field}.seal_structure.first_sealed_at",
                    as_of,
                    market_date,
                )
            if "last_sealed_at" in seal:
                last = _validate_datetime_evidence(
                    seal["last_sealed_at"],
                    f"{field}.seal_structure.last_sealed_at",
                    as_of,
                    market_date,
                )
            if first is not None and last is not None and first > last:
                raise ReviewError(f"{field}.seal_structure 首封时间不能晚于末封时间")
            if "sealed_order_amount" in seal:
                _validate_current_evidence(
                    seal["sealed_order_amount"],
                    f"{field}.seal_structure.sealed_order_amount",
                    as_of,
                    market_date,
                    "CNY",
                    "nonnegative",
                )
            if "break_count" in seal:
                _validate_current_evidence(
                    seal["break_count"],
                    f"{field}.seal_structure.break_count",
                    as_of,
                    market_date,
                    "count",
                    "nonnegative",
                )
            if not any(
                key in seal
                for key in (
                    "first_sealed_at",
                    "last_sealed_at",
                    "sealed_order_amount",
                    "break_count",
                )
            ):
                raise ReviewError(f"{field}.seal_structure 至少需要一项封板证据")


def validate_liquidity_regime(
    data: dict[str, Any], as_of: date, market_date: date
) -> None:
    component = _component(data, "liquidity_regime")
    if component is None or component["availability"] == "unknown":
        return
    thresholds = component.get("thresholds")
    if not isinstance(thresholds, dict) or not thresholds:
        raise ReviewError("deep_analysis.liquidity_regime.thresholds 必须是非空object")
    if not set(thresholds) <= LIQUIDITY_THRESHOLD_KEYS:
        raise ReviewError("liquidity_regime.thresholds 含不受支持键")
    for key, value in thresholds.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ReviewError(f"liquidity_regime.thresholds.{key} 必须是有限数值")
        if key in {
            "volume_ratio_min",
            "consecutive_days_min",
            "advancer_share_min_pct",
            "limit_up_min",
            "limit_down_max",
            "promotion_rate_min_pct",
        } and value < 0:
            raise ReviewError(f"liquidity_regime.thresholds.{key} 必须非负")
        if key in {"advancer_share_min_pct", "promotion_rate_min_pct"} and value > 100:
            raise ReviewError(f"liquidity_regime.thresholds.{key} 必须不大于100")
        if key in {"consecutive_days_min", "limit_up_min", "limit_down_max"} and not float(value).is_integer():
            raise ReviewError(f"liquidity_regime.thresholds.{key} 必须是整数")
    benchmarks = component.get("benchmarks")
    if not isinstance(benchmarks, list) or not benchmarks:
        raise ReviewError("deep_analysis.liquidity_regime.benchmarks 必须是非空数组")
    ids: set[str] = set()
    required = (
        "change_pct",
        "volume_ratio_5d",
        "ma20_distance_pct",
        "ma60_distance_pct",
        "return_percentile_120d",
        "volume_percentile_120d",
        "consecutive_volume_days",
    )
    for index, item in enumerate(benchmarks):
        field = f"deep_analysis.liquidity_regime.benchmarks[{index}]"
        if not isinstance(item, dict):
            raise ReviewError(f"{field} 必须是object")
        item_id = require_text(item, "id", field)
        require_text(item, "name", field)
        if item.get("kind") not in {"index", "etf"}:
            raise ReviewError(f"{field}.kind 必须是index或etf")
        if item_id in ids:
            raise ReviewError("liquidity_regime.benchmarks.id 不能重复")
        ids.add(item_id)
        if component["availability"] == "available" and any(key not in item for key in required):
            raise ReviewError(f"available liquidity_regime 的benchmark缺少必需指标")
        for key, unit, constraint in (
            ("change_pct", "percent", "any"),
            ("volume_ratio_5d", "ratio", "nonnegative"),
            ("ma20_distance_pct", "percent", "any"),
            ("ma60_distance_pct", "percent", "any"),
            ("return_percentile_120d", "percent", "nonnegative"),
            ("volume_percentile_120d", "percent", "nonnegative"),
            ("consecutive_volume_days", "count", "nonnegative"),
        ):
            if key in item:
                _validate_current_evidence(
                    item[key], f"{field}.{key}", as_of, market_date, unit, constraint
                )
                if key.endswith("percentile_120d") and not 0 <= float(item[key]["value"]) <= 100:
                    raise ReviewError(f"{field}.{key} 必须在0到100之间")
        sample_days = item.get("history_sample_days")
        if any(key in item for key in ("return_percentile_120d", "volume_percentile_120d")):
            if isinstance(sample_days, bool) or not isinstance(sample_days, int) or sample_days < 120:
                raise ReviewError(f"{field}.history_sample_days 必须不小于120")


def validate_sentiment_cycle(
    data: dict[str, Any], as_of: date, market_date: date
) -> None:
    component = _component(data, "sentiment_cycle")
    if component is None or component["availability"] == "unknown":
        return
    if any(key in component for key in ("score", "sentiment_score", "composite_score")):
        raise ReviewError("sentiment_cycle 禁止不可复算的综合情绪分")
    points = component.get("points")
    if not isinstance(points, list) or len(points) < 3:
        raise ReviewError("deep_analysis.sentiment_cycle.points 至少需要3个交易日")
    dates: list[date] = []
    for index, point in enumerate(points):
        field = f"deep_analysis.sentiment_cycle.points[{index}]"
        if not isinstance(point, dict):
            raise ReviewError(f"{field} 必须是object")
        observed = parse_date(point.get("market_date"), f"{field}.market_date")
        if observed > market_date or observed in dates:
            raise ReviewError("sentiment_cycle日期必须唯一且不晚于market_date")
        dates.append(observed)
        state = point.get("state")
        if state not in SENTIMENT_STATES:
            raise ReviewError(f"{field}.state 不受支持")
        require_text(point, "state_rule", field)
        metrics = point.get("metrics")
        if not isinstance(metrics, dict):
            raise ReviewError(f"{field}.metrics 必须是object")
        if not metrics:
            raise ReviewError(f"{field}.metrics 不能为空；无数值证据时应使用unknown组件")
        if component["availability"] == "available" and any(
            key not in metrics for key in ("limit_up", "limit_down", "seal_rate_pct")
        ):
            raise ReviewError(
                f"available sentiment_cycle 的每个point必须有limit_up/limit_down/seal_rate_pct"
            )
        for key, unit, constraint in (
            ("limit_up", "count", "nonnegative"),
            ("limit_down", "count", "nonnegative"),
            ("seal_rate_pct", "percent", "nonnegative"),
            ("promotion_rate_pct", "percent", "nonnegative"),
        ):
            if key not in metrics:
                continue
            validate_evidence(metrics[key], f"{field}.metrics.{key}", as_of, unit, constraint)
            if parse_date(metrics[key]["observed_at"], f"{field}.metrics.{key}.observed_at") != observed:
                raise ReviewError(f"{field}.metrics.{key}.observed_at 必须等于point.market_date")
            if unit == "percent" and not 0 <= float(metrics[key]["value"]) <= 100:
                raise ReviewError(f"{field}.metrics.{key} 必须在0到100之间")
    if dates != sorted(dates):
        raise ReviewError("sentiment_cycle.points 必须按日期升序")
    if component["availability"] == "available" and dates[-1] != market_date:
        raise ReviewError("available sentiment_cycle 必须覆盖market_date")


def validate_capital_co_movement(
    data: dict[str, Any], sections: dict[str, dict[str, Any]], as_of: date, market_date: date
) -> None:
    component = _component(data, "capital_co_movement")
    if component is None or component["availability"] == "unknown":
        return
    require_text(component, "methodology", "deep_analysis.capital_co_movement")
    if component.get("claim_type") != "co_movement_candidate":
        raise ReviewError("capital_co_movement.claim_type 必须是co_movement_candidate")
    thresholds = component.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ReviewError("capital_co_movement.thresholds 必须是object")
    pseudo_line = thresholds.get("pseudo_sector_top1_share_pct")
    if isinstance(pseudo_line, bool) or not isinstance(pseudo_line, (int, float)) or not 0 <= pseudo_line <= 100:
        raise ReviewError("pseudo_sector_top1_share_pct 必须在0到100之间")
    sector_ids = {item["id"] for item in sections["sectors"].get("items", [])}
    groups = component.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ReviewError("capital_co_movement.groups 必须是非空数组")
    ids: set[str] = set()
    for index, group in enumerate(groups):
        field = f"deep_analysis.capital_co_movement.groups[{index}]"
        if not isinstance(group, dict):
            raise ReviewError(f"{field} 必须是object")
        group_id = require_text(group, "id", field)
        require_text(group, "name", field)
        if group_id in ids:
            raise ReviewError("capital_co_movement.groups.id 不能重复")
        ids.add(group_id)
        if group.get("role") not in {"inflow", "outflow"}:
            raise ReviewError(f"{field}.role 必须是inflow或outflow")
        board_ids = group.get("board_ids")
        if not isinstance(board_ids, list) or not board_ids or not set(board_ids) <= sector_ids:
            raise ReviewError(f"{field}.board_ids 存在悬空引用或为空")
        if len(board_ids) != len(set(board_ids)):
            raise ReviewError(f"{field}.board_ids 不能重复")
        _validate_current_evidence(
            group.get("total_fund_flow"), f"{field}.total_fund_flow", as_of, market_date, "CNY"
        )
        _validate_current_evidence(
            group.get("change_pct"), f"{field}.change_pct", as_of, market_date, "percent"
        )
        total = float(group["total_fund_flow"]["value"])
        if group["role"] == "inflow" and total <= 0:
            raise ReviewError(f"{field} inflow组的total_fund_flow必须为正")
        if group["role"] == "outflow" and total >= 0:
            raise ReviewError(f"{field} outflow组的total_fund_flow必须为负")
        complete = group.get("contributions_complete")
        if not isinstance(complete, bool):
            raise ReviewError(f"{field}.contributions_complete 必须是boolean")
        contributions = group.get("contributions", [])
        if not isinstance(contributions, list):
            raise ReviewError(f"{field}.contributions 必须是数组")
        if complete and len(contributions) < 2:
            raise ReviewError(f"{field} 完整贡献分解至少需要2只个股")
        codes: set[str] = set()
        contribution_sum = 0.0
        for position, item in enumerate(contributions):
            sub = f"{field}.contributions[{position}]"
            if not isinstance(item, dict):
                raise ReviewError(f"{sub} 必须是object")
            code = require_text(item, "code", sub)
            require_text(item, "name", sub)
            if code in codes:
                raise ReviewError(f"{field}.contributions.code 不能重复")
            codes.add(code)
            _validate_current_evidence(
                item.get("fund_flow"), f"{sub}.fund_flow", as_of, market_date, "CNY"
            )
            contribution_sum += float(item["fund_flow"]["value"])
        if complete and not math.isclose(contribution_sum, total, abs_tol=1.0):
            raise ReviewError(f"{field} 完整贡献分解之和必须等于total_fund_flow")

    relations = component.get("relations", [])
    if not isinstance(relations, list):
        raise ReviewError("capital_co_movement.relations 必须是数组")
    for index, relation in enumerate(relations):
        field = f"deep_analysis.capital_co_movement.relations[{index}]"
        if not isinstance(relation, dict):
            raise ReviewError(f"{field} 必须是object")
        if relation.get("from_group_id") not in ids or relation.get("to_group_id") not in ids:
            raise ReviewError(f"{field} 引用了不存在的group")
        lookup = {group["id"]: group for group in groups}
        if lookup[relation["from_group_id"]]["role"] != "outflow":
            raise ReviewError(f"{field}.from_group_id 必须引用outflow组")
        if lookup[relation["to_group_id"]]["role"] != "inflow":
            raise ReviewError(f"{field}.to_group_id 必须引用inflow组")
        require_text(relation, "hypothesis", field)
        counter = relation.get("counter_evidence")
        if not isinstance(counter, list) or not counter or not all(
            isinstance(item, str) and item.strip() for item in counter
        ):
            raise ReviewError(f"{field}.counter_evidence 必须是非空字符串数组")


def validate_catalyst_chains(
    data: dict[str, Any], sections: dict[str, dict[str, Any]], as_of: date
) -> None:
    component = _component(data, "catalyst_chains")
    if component is None or component["availability"] == "unknown":
        return
    items = component.get("items")
    if not isinstance(items, list) or not items:
        raise ReviewError("deep_analysis.catalyst_chains.items 必须是非空数组")
    theme_ids = {
        theme["id"]
        for theme in sections["mainline_matrix"].get("themes", [])
    }
    point_ids = {point.get("id") for point in data.get("verification_points", [])}
    ids: set[str] = set()
    for index, item in enumerate(items):
        field = f"deep_analysis.catalyst_chains.items[{index}]"
        validate_event(item, field, as_of, False)
        item_id = require_text(item, "id", field)
        if item_id in ids:
            raise ReviewError("catalyst_chains.id 不能重复")
        ids.add(item_id)
        require_text(item, "fact", field)
        require_text(item, "mechanism_hypothesis", field)
        if item.get("causal_status") not in {"hypothesis", "correlation_only"}:
            raise ReviewError(f"{field}.causal_status 不受支持")
        affected = item.get("affected_theme_ids")
        if not isinstance(affected, list) or not affected or not set(affected) <= theme_ids:
            raise ReviewError(f"{field}.affected_theme_ids 存在悬空引用或为空")
        counter = item.get("counter_evidence")
        if not isinstance(counter, list) or not counter or not all(
            isinstance(value, str) and value.strip() for value in counter
        ):
            raise ReviewError(f"{field}.counter_evidence 必须是非空字符串数组")
        verification_ids = item.get("verification_point_ids")
        if not isinstance(verification_ids, list) or not verification_ids or not set(verification_ids) <= point_ids:
            raise ReviewError(f"{field}.verification_point_ids 存在悬空引用或为空")


def validate_lhb_structure(
    data: dict[str, Any], as_of: date, market_date: date
) -> None:
    component = _component(data, "lhb_structure")
    if component is None or component["availability"] == "unknown":
        return
    require_text(component, "methodology", "deep_analysis.lhb_structure")
    observed_at = parse_date(
        component.get("observed_at"), "deep_analysis.lhb_structure.observed_at"
    )
    published_at = parse_date(
        component.get("published_at"), "deep_analysis.lhb_structure.published_at"
    )
    parse_datetime(component.get("fetched_at"), "deep_analysis.lhb_structure.fetched_at")
    validate_source(component.get("source"), "deep_analysis.lhb_structure")
    if observed_at > market_date:
        raise ReviewError("lhb_structure.observed_at 不能晚于market_date")
    if published_at > as_of:
        raise ReviewError("lhb_structure.published_at 不能晚于as-of")
    if component["availability"] == "available" and observed_at != market_date:
        raise ReviewError("available lhb_structure.observed_at 必须等于market_date")
    items = component.get("items")
    if not isinstance(items, list) or not items:
        raise ReviewError("deep_analysis.lhb_structure.items 必须是非空数组")
    codes: set[str] = set()
    for index, item in enumerate(items):
        field = f"deep_analysis.lhb_structure.items[{index}]"
        if not isinstance(item, dict):
            raise ReviewError(f"{field} 必须是object")
        if any(key in item for key in ("intent", "prediction", "action")):
            raise ReviewError(f"{field} 禁止席位主观意图、预测或动作字段")
        code = require_text(item, "code", field)
        require_text(item, "name", field)
        if code in codes:
            raise ReviewError("lhb_structure.items.code 不能重复")
        codes.add(code)
        required_keys = ("net_amount",)
        if component["availability"] == "available":
            required_keys = (
                "buy_amount",
                "sell_amount",
                "net_amount",
                "buyer_count",
                "seller_count",
                "top_buyer_share_pct",
                "top_seller_share_pct",
            )
        if any(key not in item for key in required_keys):
            raise ReviewError(f"{field} 缺少当前availability要求的龙虎榜字段")
        for key, unit, constraint in (
            ("buy_amount", "CNY", "nonnegative"),
            ("sell_amount", "CNY", "nonnegative"),
            ("net_amount", "CNY", "any"),
            ("buyer_count", "count", "nonnegative"),
            ("seller_count", "count", "nonnegative"),
            ("top_buyer_share_pct", "percent", "nonnegative"),
            ("top_seller_share_pct", "percent", "nonnegative"),
        ):
            if key in item:
                _validate_current_evidence(
                    item[key], field + "." + key, as_of, observed_at, unit, constraint
                )
        if ("buy_amount" in item) != ("sell_amount" in item):
            raise ReviewError(f"{field}.buy_amount与sell_amount必须同时声明")
        if "buy_amount" in item:
            expected_net = float(item["buy_amount"]["value"]) - float(item["sell_amount"]["value"])
            if not math.isclose(expected_net, float(item["net_amount"]["value"]), abs_tol=1.0):
                raise ReviewError(f"{field}.net_amount 必须等于buy_amount-sell_amount")
        for key in ("top_buyer_share_pct", "top_seller_share_pct"):
            if key in item and not 0 <= float(item[key]["value"]) <= 100:
                raise ReviewError(f"{field}.{key} 必须在0到100之间")
        seat_types = item.get("seat_types", [])
        if not isinstance(seat_types, list) or not all(
            isinstance(value, str) and value.strip() for value in seat_types
        ):
            raise ReviewError(f"{field}.seat_types 必须是字符串数组")


def validate_verification_subjects(
    data: dict[str, Any], sections: dict[str, dict[str, Any]]
) -> None:
    deep = data.get("deep_analysis") or {}
    stock_entities: dict[str, str] = {}
    benchmark_entities: dict[str, str] = {}
    extra_mentions: list[tuple[str, str, str]] = []

    def add_entity(target: dict[str, str], entity_id: Any, label: Any) -> None:
        if not isinstance(entity_id, str) or not entity_id.strip():
            return
        if not isinstance(label, str) or not label.strip():
            return
        target.setdefault(entity_id, label)

    for item in (deep.get("security_details") or {}).get("items", []):
        add_entity(stock_entities, item.get("code"), item.get("name"))
    for item in sections["short_term_sentiment"].get("high_boards", []):
        add_entity(stock_entities, item.get("code"), item.get("name"))
        if not item.get("code") and isinstance(item.get("name"), str):
            extra_mentions.append(("stock", "", item["name"]))
    for sector in sections["sectors"].get("items", []):
        for item in sector.get("leaders", []):
            add_entity(stock_entities, item.get("code"), item.get("name"))
            if not item.get("code") and isinstance(item.get("name"), str):
                extra_mentions.append(("stock", "", item["name"]))
    for group in (deep.get("capital_co_movement") or {}).get("groups", []):
        for item in group.get("contributions", []):
            add_entity(stock_entities, item.get("code"), item.get("name"))
    for item in (deep.get("lhb_structure") or {}).get("items", []):
        add_entity(stock_entities, item.get("code"), item.get("name"))

    for item in sections["indices"].get("items", []):
        add_entity(benchmark_entities, item.get("id"), item.get("name"))
    for item in (deep.get("liquidity_regime") or {}).get("benchmarks", []):
        add_entity(benchmark_entities, item.get("id"), item.get("name"))

    sector_entities = {
        item["id"]: item["name"] for item in sections["sectors"].get("items", [])
    }
    for item in (sections["sectors"].get("concept_view") or {}).get("items", []):
        add_entity(sector_entities, item.get("id"), item.get("name"))
    labels = {
        "market": {"all-a": "A股全市场"},
        "stock": stock_entities,
        "sector": sector_entities,
        "theme": {
            item["id"]: item["name"]
            for item in sections["mainline_matrix"].get("themes", [])
        },
        "benchmark": benchmark_entities,
    }
    primary_index_ids = {
        item["id"]
        for item in sections["indices"].get("items", [])
        if item.get("primary") is True
    }
    entity_mentions = extra_mentions + [
        (scope, entity_id, entity_label)
        for scope, entities in labels.items()
        if scope != "market"
        for entity_id, entity_label in entities.items()
    ]
    for index, point in enumerate(data.get("verification_points", [])):
        field = f"verification_points[{index}]"
        subject = point["subject"]
        if subject["id"] not in labels[subject["scope"]]:
            raise ReviewError(f"{field}.subject.id 未在当前输入中声明")
        if subject["label"] != labels[subject["scope"]][subject["id"]]:
            raise ReviewError(f"{field}.subject.label 与当前输入实体名称不一致")
        title = point["title"]
        for scope, entity_id, entity_label in entity_mentions:
            if scope == subject["scope"] and entity_id == subject["id"]:
                continue
            if entity_label == subject["label"] or entity_label in subject["label"]:
                continue
            if (
                subject["scope"] == "market"
                and point["condition"]["metric"] == "primary_index_change_pct"
                and scope == "benchmark"
                and entity_id in primary_index_ids
            ):
                continue
            mentions_id = len(entity_id) >= 4 and entity_id in title
            mentions_label = len(entity_label) >= 2 and entity_label in title
            if mentions_id or mentions_label:
                raise ReviewError(
                    f"{field}.title 引用了非subject实体{scope}:{entity_label}"
                )


def validate_deep_analysis(
    data: dict[str, Any], sections: dict[str, dict[str, Any]], as_of: date, market_date: date
) -> None:
    if data.get("deep_analysis") is None:
        validate_verification_subjects(data, sections)
        return
    validate_security_details(data, as_of, market_date)
    validate_liquidity_regime(data, as_of, market_date)
    validate_sentiment_cycle(data, as_of, market_date)
    validate_capital_co_movement(data, sections, as_of, market_date)
    validate_catalyst_chains(data, sections, as_of)
    validate_lhb_structure(data, as_of, market_date)
    validate_verification_subjects(data, sections)
