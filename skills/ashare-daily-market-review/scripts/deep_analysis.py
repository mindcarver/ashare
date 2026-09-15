#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.3 深度分析的确定性派生。

这里只把已校验证据变成可复算结构；不读取网络、不补默认阈值、不把同日资金共现
升级为因果迁移，也不推断龙虎榜席位的主观意图。
"""

from itertools import combinations
from typing import Any

from schema import DEEP_COMPONENTS, value


def _number(evidence: dict[str, Any] | None) -> float | None:
    return float(evidence["value"]) if evidence else None


def derive_security_details(component: dict[str, Any]) -> dict[str, Any]:
    items = []
    for item in component.get("items", []):
        windows = {
            entry["window"]["trading_days"]: float(entry["metric"]["value"])
            for entry in item.get("fund_flow_windows", [])
        }
        seal = item.get("seal_structure") or {}
        items.append(
            {
                "code": item["code"],
                "name": item["name"],
                "roles": list(item["roles"]),
                "streak": item.get("streak"),
                "change_pct": _number(item.get("change_pct")),
                "fund_flow_windows_cny": windows,
                "fund_flow_method_categories": {
                    entry["window"]["trading_days"]: entry["method_category"]
                    for entry in item.get("fund_flow_windows", [])
                },
                "seal_structure": {
                    "first_sealed_at": (seal.get("first_sealed_at") or {}).get("value"),
                    "last_sealed_at": (seal.get("last_sealed_at") or {}).get("value"),
                    "sealed_order_amount_cny": _number(seal.get("sealed_order_amount")),
                    "break_count": _number(seal.get("break_count")),
                }
                if seal
                else None,
            }
        )
    return {
        "availability": component["availability"],
        "status_reason": component["status_reason"],
        "items": items,
    }


def _check(code: str, observed: float | None, operator: str, target: float, unit: str) -> dict[str, Any]:
    if observed is None:
        status = "unknown"
    elif operator == ">=":
        status = "passed" if observed >= target else "failed"
    elif operator == "<=":
        status = "passed" if observed <= target else "failed"
    else:
        raise ValueError(operator)
    return {
        "code": code,
        "observed": observed,
        "operator": operator,
        "threshold": float(target),
        "unit": unit,
        "status": status,
    }


def derive_liquidity_regime(
    component: dict[str, Any], sections: dict[str, dict[str, Any]], derived: dict[str, Any]
) -> dict[str, Any]:
    thresholds = component["thresholds"]
    benchmarks = []
    all_checks = []
    for item in component.get("benchmarks", []):
        metrics = {
            key: _number(item.get(key))
            for key in (
                "change_pct",
                "volume_ratio_5d",
                "ma20_distance_pct",
                "ma60_distance_pct",
                "return_percentile_120d",
                "volume_percentile_120d",
                "consecutive_volume_days",
            )
        }
        checks = []
        for threshold_key, metric_key, operator, unit in (
            ("volume_ratio_min", "volume_ratio_5d", ">=", "ratio"),
            ("consecutive_days_min", "consecutive_volume_days", ">=", "count"),
            ("ma20_distance_min_pct", "ma20_distance_pct", ">=", "percent"),
            ("daily_change_min_pct", "change_pct", ">=", "percent"),
        ):
            if threshold_key in thresholds:
                checks.append(
                    _check(
                        threshold_key,
                        metrics[metric_key],
                        operator,
                        thresholds[threshold_key],
                        unit,
                    )
                )
        all_checks.extend(checks)
        benchmarks.append(
            {
                "id": item["id"],
                "name": item["name"],
                "kind": item["kind"],
                "history_sample_days": item.get("history_sample_days"),
                **metrics,
                "checks": checks,
            }
        )

    market_observed = {
        "advancer_share_min_pct": derived.get("advancer_share_pct"),
        "limit_up_min": value(sections["breadth"], "limit_up"),
        "limit_down_max": value(sections["breadth"], "limit_down"),
        "promotion_rate_min_pct": (
            (derived.get("prev_pool_performance") or {}).get("promotion_rate_pct")
        ),
    }
    market_checks = []
    for key, operator, unit in (
        ("advancer_share_min_pct", ">=", "percent"),
        ("limit_up_min", ">=", "count"),
        ("limit_down_max", "<=", "count"),
        ("promotion_rate_min_pct", ">=", "percent"),
    ):
        if key in thresholds:
            market_checks.append(
                _check(key, market_observed[key], operator, thresholds[key], unit)
            )
    all_checks.extend(market_checks)
    if any(item["status"] == "unknown" for item in all_checks):
        result = "unknown"
    elif all(item["status"] == "passed" for item in all_checks):
        result = "all_declared_conditions_met"
    else:
        result = "conditions_not_met"
    return {
        "availability": component["availability"],
        "status_reason": component["status_reason"],
        "thresholds": dict(thresholds),
        "benchmarks": benchmarks,
        "market_checks": market_checks,
        "result": result,
        "evaluated_count": sum(item["status"] != "unknown" for item in all_checks),
        "passed_count": sum(item["status"] == "passed" for item in all_checks),
        "note": "逐条检查已声明条件，不聚合成分数，不推导买卖或仓位",
    }


def derive_sentiment_cycle(component: dict[str, Any]) -> dict[str, Any]:
    points = []
    transitions = []
    previous = None
    for item in component.get("points", []):
        metrics = {
            key: _number(item["metrics"].get(key))
            for key in ("limit_up", "limit_down", "seal_rate_pct", "promotion_rate_pct")
        }
        point = {
            "market_date": item["market_date"],
            "state": item["state"],
            "state_rule": item["state_rule"],
            **metrics,
        }
        if previous and previous["state"] != point["state"]:
            transitions.append(
                {
                    "from_date": previous["market_date"],
                    "to_date": point["market_date"],
                    "from_state": previous["state"],
                    "to_state": point["state"],
                }
            )
        points.append(point)
        previous = point
    current = points[-1]
    prior = points[-2]
    limit_values = [point["limit_up"] for point in points if point["limit_up"] is not None]
    return {
        "availability": component["availability"],
        "status_reason": component["status_reason"],
        "points": points,
        "transitions": transitions,
        "current_state": current["state"],
        "current_state_rule": current["state_rule"],
        "limit_up_change": (
            current["limit_up"] - prior["limit_up"]
            if current["limit_up"] is not None and prior["limit_up"] is not None
            else None
        ),
        "limit_down_change": (
            current["limit_down"] - prior["limit_down"]
            if current["limit_down"] is not None and prior["limit_down"] is not None
            else None
        ),
        "new_window_low_limit_up": (
            current["limit_up"] == min(limit_values)
            if current["limit_up"] is not None and limit_values
            else None
        ),
        "note": "状态来自公开规则；不使用不可复算的综合情绪分",
    }


def _concentration(contributions: list[dict[str, Any]]) -> dict[str, Any]:
    values = [float(item["fund_flow"]["value"]) for item in contributions]
    positive = [value for value in values if value > 0]
    absolute = [abs(value) for value in values]
    positive_total = sum(positive)
    absolute_total = sum(absolute)
    return {
        "top1_positive_share_pct": (
            round(max(positive) / positive_total * 100, 6) if positive_total else None
        ),
        "absolute_hhi": (
            round(sum((value / absolute_total) ** 2 for value in absolute), 6)
            if absolute_total
            else None
        ),
        "opposite_direction_count": sum(
            value < 0 for value in values
        ),
    }


def derive_capital_co_movement(component: dict[str, Any]) -> dict[str, Any]:
    groups = []
    threshold = float(component["thresholds"]["pseudo_sector_top1_share_pct"])
    for group in component.get("groups", []):
        contributions = [
            {
                "code": item["code"],
                "name": item["name"],
                "fund_flow_cny": float(item["fund_flow"]["value"]),
            }
            for item in group.get("contributions", [])
        ]
        concentration = _concentration(group.get("contributions", []))
        if not group["contributions_complete"]:
            pseudo_status = "unknown"
        elif (
            float(group["total_fund_flow"]["value"]) > 0
            and float(group["change_pct"]["value"]) <= 0
            and concentration["top1_positive_share_pct"] is not None
            and concentration["top1_positive_share_pct"] >= threshold
        ):
            pseudo_status = "flagged"
        else:
            pseudo_status = "clear"
        groups.append(
            {
                "id": group["id"],
                "name": group["name"],
                "role": group["role"],
                "board_ids": list(group["board_ids"]),
                "total_fund_flow_cny": float(group["total_fund_flow"]["value"]),
                "change_pct": float(group["change_pct"]["value"]),
                "contributions_complete": group["contributions_complete"],
                "contributions": contributions,
                **concentration,
                "pseudo_sector_status": pseudo_status,
            }
        )
    overlaps = []
    for left, right in combinations(groups, 2):
        shared = sorted(set(left["board_ids"]) & set(right["board_ids"]))
        if shared:
            overlaps.append(
                {
                    "left_group_id": left["id"],
                    "right_group_id": right["id"],
                    "shared_board_ids": shared,
                    "overlap_rate_pct": round(
                        len(shared) / len(set(left["board_ids"]) | set(right["board_ids"])) * 100,
                        6,
                    ),
                }
            )
    board_refs = [board_id for group in groups for board_id in group["board_ids"]]
    security_refs = [item["code"] for group in groups for item in group["contributions"]]
    board_overlap_rate = (
        round((len(board_refs) - len(set(board_refs))) / len(board_refs) * 100, 6)
        if board_refs
        else 0.0
    )
    security_overlap_rate = (
        round((len(security_refs) - len(set(security_refs))) / len(security_refs) * 100, 6)
        if security_refs
        else 0.0
    )
    return {
        "availability": component["availability"],
        "status_reason": component["status_reason"],
        "claim_type": "co_movement_candidate",
        "methodology": component["methodology"],
        "thresholds": dict(component["thresholds"]),
        "groups": groups,
        "overlaps": overlaps,
        "board_overlap_rate_pct": board_overlap_rate,
        "security_overlap_rate_pct": security_overlap_rate,
        "relations": [
            {
                "from_group_id": item["from_group_id"],
                "to_group_id": item["to_group_id"],
                "hypothesis": item["hypothesis"],
                "counter_evidence": list(item["counter_evidence"]),
                "claim_type": "co_movement_candidate",
            }
            for item in component.get("relations", [])
        ],
        "note": "同日流出与流入只构成共现候选，不证明同一笔资金发生因果迁移",
    }


def derive_catalyst_chains(component: dict[str, Any]) -> dict[str, Any]:
    return {
        "availability": component["availability"],
        "status_reason": component["status_reason"],
        "items": [
            {
                "id": item["id"],
                "title": item["title"],
                "event_date": item["event_date"],
                "published_at": item["published_at"],
                "source": item["source"],
                "fact": item["fact"],
                "mechanism_hypothesis": item["mechanism_hypothesis"],
                "causal_status": item["causal_status"],
                "affected_theme_ids": list(item["affected_theme_ids"]),
                "counter_evidence": list(item["counter_evidence"]),
                "verification_point_ids": list(item["verification_point_ids"]),
            }
            for item in component.get("items", [])
        ],
    }


def derive_lhb_structure(component: dict[str, Any]) -> dict[str, Any]:
    items = []
    for item in component.get("items", []):
        items.append(
            {
                "code": item["code"],
                "name": item["name"],
                "buy_amount_cny": _number(item.get("buy_amount")),
                "sell_amount_cny": _number(item.get("sell_amount")),
                "net_amount_cny": float(item["net_amount"]["value"]),
                "buyer_count": int(item["buyer_count"]["value"]) if "buyer_count" in item else None,
                "seller_count": int(item["seller_count"]["value"]) if "seller_count" in item else None,
                "top_buyer_share_pct": _number(item.get("top_buyer_share_pct")),
                "top_seller_share_pct": _number(item.get("top_seller_share_pct")),
                "seat_types": list(item.get("seat_types", [])),
            }
        )
    return {
        "availability": component["availability"],
        "status_reason": component["status_reason"],
        "observed_at": component["observed_at"],
        "published_at": component["published_at"],
        "methodology": component["methodology"],
        "items": sorted(items, key=lambda item: (-item["net_amount_cny"], item["code"])),
        "note": "仅描述已披露席位结构与集中度，不推断派发、接力或主观意图",
    }


DERIVERS = {
    "security_details": derive_security_details,
    "sentiment_cycle": derive_sentiment_cycle,
    "capital_co_movement": derive_capital_co_movement,
    "catalyst_chains": derive_catalyst_chains,
    "lhb_structure": derive_lhb_structure,
}


def derive_deep_analysis(
    data: dict[str, Any], sections: dict[str, dict[str, Any]], derived: dict[str, Any]
) -> dict[str, Any] | None:
    deep = data.get("deep_analysis")
    if deep is None:
        return None
    result: dict[str, Any] = {}
    for name in DEEP_COMPONENTS:
        component = deep.get(name)
        if component is None:
            continue
        if component["availability"] == "unknown":
            result[name] = {
                "availability": "unknown",
                "status_reason": component["status_reason"],
            }
        elif name == "liquidity_regime":
            result[name] = derive_liquidity_regime(component, sections, derived)
        else:
            result[name] = DERIVERS[name](component)
    return result


def deep_signals(deep: dict[str, Any] | None) -> list[dict[str, str]]:
    if not deep:
        return []
    signals: list[dict[str, str]] = []
    liquidity = deep.get("liquidity_regime") or {}
    if liquidity.get("result") == "conditions_not_met":
        signals.append(
            {
                "code": "liquidity_conditions_not_met",
                "label": "量能与价格条件未同时满足",
                "rule": "all declared liquidity checks must pass",
                "evidence": f"{liquidity.get('passed_count', 0)}/{liquidity.get('evaluated_count', 0)}项成立",
            }
        )
    cycle = deep.get("sentiment_cycle") or {}
    if cycle.get("new_window_low_limit_up"):
        change = cycle.get("limit_up_change")
        change_text = f"{change:+.0f}" if change is not None else "unknown"
        signals.append(
            {
                "code": "sentiment_cycle_limit_up_low",
                "label": "涨停家数触及声明窗口低位",
                "rule": "current limit_up == min(declared sentiment cycle window)",
                "evidence": f"当前状态 {cycle.get('current_state')}，涨停较前值变化 {change_text}",
            }
        )
    capital = deep.get("capital_co_movement") or {}
    flagged = [
        item["name"] for item in capital.get("groups", []) if item["pseudo_sector_status"] == "flagged"
    ]
    if flagged:
        signals.append(
            {
                "code": "pseudo_sector_concentration",
                "label": "板块资金由少数个股主导",
                "rule": "group change <= 0 and top1 positive share >= declared threshold",
                "evidence": "、".join(flagged),
            }
        )
    return signals


def verification_observation_index(
    sections: dict[str, dict[str, Any]], derived: dict[str, Any]
) -> dict[str, dict[str, dict[str, float | None]]]:
    deep = derived.get("deep_analysis") or {}
    market = {
        "all-a": {
            "primary_index_change_pct": derived.get("primary_index_change_pct"),
            "advancer_share_pct": derived.get("advancer_share_pct"),
            "turnover_amount": derived.get("turnover_amount"),
            "turnover_vs_previous_pct": derived.get("turnover_vs_previous_pct"),
            "open_board_rate_pct": (derived.get("short_term_sentiment") or {}).get("open_board_rate_pct"),
            "limit_balance": derived.get("limit_balance"),
            "promotion_rate_pct": (derived.get("prev_pool_performance") or {}).get("promotion_rate_pct"),
        }
    }
    stocks = {}
    for item in (deep.get("security_details") or {}).get("items", []):
        stocks[item["code"]] = {
            "streak": item.get("streak"),
            "change_pct": item.get("change_pct"),
            "fund_flow_1d_cny": item.get("fund_flow_windows_cny", {}).get(1),
            "sealed_order_amount_cny": (item.get("seal_structure") or {}).get("sealed_order_amount_cny"),
            "break_count": (item.get("seal_structure") or {}).get("break_count"),
        }
    sectors = {
        item["id"]: {
            "change_pct": _number(item.get("change_pct")),
            "fund_flow_cny": _number(item.get("fund_flow")),
            "top1_positive_share_pct": None,
            "first_board_count": None,
        }
        for item in sections["sectors"].get("items", [])
    }
    themes = {
        item["id"]: {
            "limit_up_count": item.get("limit_up_count"),
            "board_fund_flow_cny": item.get("board_fund_flow_cny"),
            "top1_positive_share_pct": None,
        }
        for item in (derived.get("mainline_matrix") or {}).get("themes", [])
    }
    for group in (deep.get("capital_co_movement") or {}).get("groups", []):
        for board_id in group["board_ids"]:
            if board_id in sectors:
                sectors[board_id]["top1_positive_share_pct"] = group.get("top1_positive_share_pct")
    benchmarks = {
        item["id"]: {
            key: item.get(key)
            for key in (
                "change_pct",
                "volume_ratio_5d",
                "ma20_distance_pct",
                "ma60_distance_pct",
                "return_percentile_120d",
                "volume_percentile_120d",
            )
        }
        for item in (deep.get("liquidity_regime") or {}).get("benchmarks", [])
    }
    return {
        "market": market,
        "stock": stocks,
        "sector": sectors,
        "theme": themes,
        "benchmark": benchmarks,
    }
