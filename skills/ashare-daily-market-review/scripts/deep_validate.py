#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.5 深度分析层校验。

深度层放在顶层 ``deep_analysis``，不进入基础章节覆盖计数。所有组件均可选；
存在才校验，缺失绝不回填。资金迁移只允许表达同日共现候选，不能声明因果迁移。
1.5 的两条「资金/催化」纪律拆到 ``deep_flow_validate.py``，本模块只管其余组件。
"""

import math

from datetime import date
from typing import Any

from evidence import (
    deep_component,
    require_current_evidence,
    require_market_date,
    validate_event,
    validate_evidence,
    validate_source,
    validate_window,
)
from deep_flow_validate import (
    validate_capital_co_movement,
    validate_catalyst_chains,
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


def _baseline_daily_flows(
    sections: dict[str, dict[str, Any]],
) -> dict[str, tuple[str, float]]:
    """基础章节里同一交易日的「当日主力净额」，用于和深度表 1 日窗口交叉校验。

    同一份报告里同一只票同一天的当日资金不该出现两个数。基础章节（高标池、板块
    重点股）已经记录了当日口径，深度表再算一次时必须落在声明的容差内——这是
    「深度表 1 日列按可得性分裂成两套供应商」那个坑的机器拦截点。
    """
    baseline: dict[str, tuple[str, float]] = {}

    def remember(code: Any, flow: Any, label: str) -> None:
        if not isinstance(code, str) or not code.strip():
            return
        raw = (flow or {}).get("value") if isinstance(flow, dict) else flow
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return
        baseline.setdefault(code, (label, float(raw)))

    for item in sections["short_term_sentiment"].get("high_boards") or []:
        remember(item.get("code"), item.get("fund_flow"), "短线情绪高标池")
    for sector in sections["sectors"].get("items", []):
        for item in sector.get("leaders") or []:
            remember(item.get("code"), item.get("fund_flow"), f"板块重点股（{sector['name']}）")
    return baseline


def validate_security_details(
    data: dict[str, Any], sections: dict[str, dict[str, Any]], as_of: date, market_date: date, strict: bool
) -> None:
    component = deep_component(data, "security_details")
    if component is None or component["availability"] == "unknown":
        return
    if "methodology" in component:
        require_text(component, "methodology", "deep_analysis.security_details")
    if "public_caveat" in component:
        require_text(component, "public_caveat", "deep_analysis.security_details")
    tolerance = None
    if "cross_check_tolerance_pct" in component:
        raw_tolerance = component["cross_check_tolerance_pct"]
        if (
            isinstance(raw_tolerance, bool)
            or not isinstance(raw_tolerance, (int, float))
            or not math.isfinite(raw_tolerance)
            or not 0 <= raw_tolerance <= 100
        ):
            raise ReviewError("deep_analysis.security_details.cross_check_tolerance_pct 必须在0到100之间")
        tolerance = float(raw_tolerance)
    elif strict:
        raise ReviewError(
            "deep_analysis.security_details.cross_check_tolerance_pct 必须声明："
            "1日窗口要与基础章节同一交易日的当日资金口径交叉校验，容差由输入显式给出"
        )
    baseline = _baseline_daily_flows(sections) if tolerance is not None else {}
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
            require_current_evidence(
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
            require_current_evidence(
                window_item.get("metric"), f"{sub}.metric", as_of, market_date, "CNY"
            )
            if window_item.get("method_category") not in FUND_METHODS:
                raise ReviewError(f"{sub}.method_category 不受支持")
            if days == 1 and tolerance is not None and code in baseline:
                label, base_value = baseline[code]
                deep_value = float(window_item["metric"]["value"])
                if base_value:
                    diff_pct = abs(deep_value - base_value) / abs(base_value) * 100
                    if diff_pct > tolerance + 1e-9:
                        raise ReviewError(
                            f"{sub}.metric 与基础章节同一交易日口径相差 {diff_pct:.2f}%"
                            f"（{label}），超过声明的 cross_check_tolerance_pct={tolerance}%；"
                            "请统一到同一口径，或提高容差并在 methodology 写明来源差异"
                        )

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
                require_current_evidence(
                    seal["sealed_order_amount"],
                    f"{field}.seal_structure.sealed_order_amount",
                    as_of,
                    market_date,
                    "CNY",
                    "nonnegative",
                )
            if "break_count" in seal:
                require_current_evidence(
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
    component = deep_component(data, "liquidity_regime")
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
        from price_volume import validate_bar_metrics
        validate_bar_metrics(item, market_date.isoformat())
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
                require_current_evidence(
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
    component = deep_component(data, "sentiment_cycle")
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


def validate_lhb_structure(
    data: dict[str, Any], as_of: date, market_date: date
) -> None:
    component = deep_component(data, "lhb_structure")
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
                require_current_evidence(
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
    if "deep_analysis" not in data:
        validate_verification_subjects(data, sections)
        return
    if data["deep_analysis"] is None:
        raise ReviewError("deep_analysis 不能是null")
    # 由 1.4 升级进来的输入豁免 1.5 新增的必填项，历史 deep 输入因此仍可重放。
    strict = data.get("legacy_migration") is None
    validate_security_details(data, sections, as_of, market_date, strict)
    validate_liquidity_regime(data, as_of, market_date)
    validate_sentiment_cycle(data, as_of, market_date)
    validate_capital_co_movement(data, sections, as_of, market_date, strict)
    validate_catalyst_chains(data, sections, as_of, strict)
    validate_lhb_structure(data, as_of, market_date)
    validate_verification_subjects(data, sections)
