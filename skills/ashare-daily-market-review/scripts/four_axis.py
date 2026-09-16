#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纵 × 横 × 深 × 验四轴覆盖与确定性交汇。

只消费已经校验和派生的证据；不补阈值、不打综合分、不推导交易动作。
"""

from collections import Counter
from typing import Any

from schema import DEEP_COMPONENTS


def deep_coverage(data: dict[str, Any]) -> dict[str, Any]:
    deep = data.get("deep_analysis") or {}
    counts = Counter()
    missing = []
    for name in DEEP_COMPONENTS:
        component = deep.get(name)
        if component is None:
            counts["missing"] += 1
            missing.append(name)
        else:
            counts[component["availability"]] += 1
    return {
        "analysis_mode": data["analysis_mode"],
        "enabled": data["analysis_mode"] == "deep",
        "declared": len(DEEP_COMPONENTS) - counts["missing"],
        "total": len(DEEP_COMPONENTS),
        "available": counts["available"],
        "partial": counts["partial"],
        "unknown": counts["unknown"],
        "missing": counts["missing"],
        "missing_components": missing,
    }


def _check(status: str, evidence: str, rule: str) -> dict[str, str]:
    return {"status": status, "evidence": evidence, "rule": rule}


def _combine(checks: list[dict[str, str]], not_enabled: bool = False) -> str:
    if not_enabled:
        return "not_enabled"
    if not checks:
        return "unknown"
    statuses = [item["status"] for item in checks]
    if "contradicted" in statuses:
        return "contradicted"
    if statuses and all(status == "supported" for status in statuses):
        return "supported"
    return "unknown"


def _longitudinal(derived: dict[str, Any], history: dict[str, Any]) -> dict[str, Any]:
    checks = []
    deep = derived.get("deep_analysis") or {}
    cycle = deep.get("sentiment_cycle") or {}
    if cycle.get("availability") not in {None, "unknown"}:
        new_low = cycle.get("new_window_low_limit_up")
        status = "unknown" if new_low is None else ("contradicted" if new_low else "supported")
        checks.append(
            _check(
                status,
                f"当前状态{cycle.get('current_state', 'unknown')}；窗口涨停新低={new_low}",
                "current limit_up must not equal the declared-window minimum",
            )
        )
    else:
        checks.append(
            _check(
                "unknown",
                cycle.get("status_reason", "情绪周期证据未声明"),
                "sentiment_cycle must provide a declared comparison window",
            )
        )
    prev_pool = derived.get("prev_pool_performance") or {}
    if prev_pool.get("availability") not in {None, "unknown"}:
        health = prev_pool.get("health")
        health_status = {
            "at_or_above_line": "supported",
            "below_line": "contradicted",
        }.get(health, "unknown")
        checks.append(
            _check(
                health_status,
                f"晋级率{prev_pool.get('promotion_rate_pct')}%，健康状态{health}",
                "promotion_rate_pct >= declared health_threshold_pct",
            )
        )
    else:
        checks.append(
            _check(
                "unknown",
                prev_pool.get("status_reason", "前涨停池延续证据未声明"),
                "prev_pool_performance must declare a health threshold",
            )
        )
    return {
        "status": _combine(checks),
        "checks": checks,
        "history_sample_size": history.get("sample_size"),
        "sentiment_state_streak": history.get("sentiment_state_streak"),
    }


def _horizontal(derived: dict[str, Any]) -> dict[str, Any]:
    matrix = derived.get("mainline_matrix") or {}
    themes = matrix.get("themes", [])
    if matrix.get("availability") in {None, "unknown"}:
        check = _check("unknown", "主线矩阵不可得", "mainline_matrix must be available")
        dual_ids = []
    else:
        dual_ids = [item["id"] for item in themes if item.get("quadrant") == "dual_confirmed"]
        check = _check(
            "supported" if dual_ids else "contradicted",
            f"双确认主题{len(dual_ids)}个",
            "at least one theme quadrant == dual_confirmed",
        )
    return {
        "status": check["status"],
        "checks": [check],
        "dual_confirmed_theme_ids": dual_ids,
        "quadrant_counts": dict(matrix.get("quadrant_counts", {})),
        "advancer_share_pct": derived.get("advancer_share_pct"),
    }


def _liquidity_status(deep: dict[str, Any], mode: str) -> dict[str, str]:
    liquidity = deep.get("liquidity_regime") or {}
    if not liquidity:
        return _check("not_enabled" if mode == "core" else "unknown", "量价深度证据未声明", "liquidity_regime must be declared")
    if liquidity.get("availability") == "unknown":
        return _check("unknown", liquidity.get("status_reason", "量价证据未知"), "liquidity evidence must be available")
    result = liquidity.get("result")
    status = {
        "all_declared_conditions_met": "supported",
        "conditions_not_met": "contradicted",
        "unknown": "unknown",
    }.get(result, "unknown")
    return _check(
        status,
        f"{liquidity.get('passed_count', 0)}/{liquidity.get('evaluated_count', 0)}项成立；{result}",
        "all declared liquidity conditions must pass",
    )


def _depth(derived: dict[str, Any], mode: str) -> dict[str, Any]:
    deep = derived.get("deep_analysis") or {}
    if not deep:
        return {
            "status": "not_enabled" if mode == "core" else "unknown",
            "checks": [],
            "flagged_group_ids": [],
            "catalyst_theme_ids": [],
        }
    checks = [_liquidity_status(deep, mode)]
    capital = deep.get("capital_co_movement") or {}
    groups = capital.get("groups", [])
    flagged = [item["id"] for item in groups if item.get("pseudo_sector_status") == "flagged"]
    if capital.get("availability") == "unknown":
        capital_check = _check("unknown", capital.get("status_reason", "资金集中度未知"), "capital contribution evidence must be complete")
    elif capital:
        if flagged:
            capital_status = "contradicted"
        elif groups and all(item.get("pseudo_sector_status") == "clear" for item in groups):
            capital_status = "supported"
        else:
            capital_status = "unknown"
        capital_check = _check(
            capital_status,
            f"伪板块标记{len(flagged)}个；板块重叠率{capital.get('board_overlap_rate_pct', 0)}%",
            "no relevant complete group may be pseudo_sector_status == flagged",
        )
    else:
        capital_check = _check("unknown", "资金集中度未声明", "capital_co_movement must be declared")
    checks.append(capital_check)
    catalysts = deep.get("catalyst_chains") or {}
    catalyst_theme_ids = sorted(
        {
            theme_id
            for item in catalysts.get("items", [])
            for theme_id in item.get("affected_theme_ids", [])
        }
    )
    checks.append(
        _check(
            "supported" if catalyst_theme_ids else "unknown",
            f"有验证链的主题{len(catalyst_theme_ids)}个" if catalyst_theme_ids else catalysts.get("status_reason", "催化链未知"),
            "at least one sourced catalyst chain must map to a declared theme",
        )
    )
    lhb = deep.get("lhb_structure") or {}
    checks.append(
        _check(
            "supported" if lhb.get("availability") in {"available", "partial"} else "unknown",
            lhb.get("status_reason", "龙虎榜结构未知"),
            "lhb_structure must disclose available or lagged partial evidence",
        )
    )
    return {
        "status": _combine(checks),
        "checks": checks,
        "flagged_group_ids": flagged,
        "catalyst_theme_ids": catalyst_theme_ids,
    }


def _verification(data: dict[str, Any], resolved: list[dict[str, Any]]) -> dict[str, Any]:
    future = [
        item
        for item in data.get("verification_points", [])
        if item["event_date"] > data["market_date"]
    ]
    resolved_counts = Counter(item["status"] for item in resolved)
    scopes = sorted({item["subject"]["scope"] for item in future})
    status = "supported" if future or resolved else "unknown"
    return {
        "status": status,
        "future_count": len(future),
        "future_scopes": scopes,
        "resolved_counts": {
            "passed": resolved_counts["passed"],
            "failed": resolved_counts["failed"],
            "unknown": resolved_counts["unknown"],
        },
        "rule": "verification points must bind scope, subject, metric and due date",
    }


def _theme_concentration(theme: dict[str, Any], deep: dict[str, Any], mode: str) -> dict[str, str]:
    capital = deep.get("capital_co_movement") or {}
    if not capital:
        return _check("not_enabled" if mode == "core" else "unknown", "主题资金贡献分解未声明", "a complete capital group must overlap the theme boards")
    groups = [item for item in capital.get("groups", []) if set(item.get("board_ids", [])) & set(theme.get("boards", []))]
    if not groups:
        return _check("unknown", "没有与主题板块重叠的完整资金组", "a complete capital group must overlap the theme boards")
    if any(item.get("pseudo_sector_status") == "flagged" for item in groups):
        return _check("contradicted", "相关资金组存在伪板块标记", "relevant groups must not be flagged")
    if all(item.get("pseudo_sector_status") == "clear" for item in groups):
        return _check("supported", f"相关完整资金组{len(groups)}个且均未标记伪板块", "all relevant complete groups must be clear")
    return _check("unknown", "相关资金组集中度不完整", "all relevant groups need complete contributions")


def _theme_rows(
    data: dict[str, Any], derived: dict[str, Any], longitudinal: dict[str, Any]
) -> list[dict[str, Any]]:
    mode = data["analysis_mode"]
    deep = derived.get("deep_analysis") or {}
    liquidity = _liquidity_status(deep, mode)
    catalysts = deep.get("catalyst_chains") or {}
    catalyst_by_theme: dict[str, list[dict[str, Any]]] = {}
    for item in catalysts.get("items", []):
        for theme_id in item.get("affected_theme_ids", []):
            catalyst_by_theme.setdefault(theme_id, []).append(item)
    future_points = [
        item
        for item in data.get("verification_points", [])
        if item["event_date"] > data["market_date"]
    ]
    future_point_ids = {item["id"] for item in future_points}
    direct_verifications = {
        item["subject"]["id"]
        for item in future_points
        if item["subject"]["scope"] == "theme"
    }
    rows = []
    for theme in (derived.get("mainline_matrix") or {}).get("themes", []):
        horizontal = _check(
            "supported" if theme.get("quadrant") == "dual_confirmed" else ("unknown" if theme.get("quadrant") == "unknown" else "contradicted"),
            f"象限={theme.get('quadrant', 'unknown')}",
            "theme quadrant must equal dual_confirmed",
        )
        concentration = _theme_concentration(theme, deep, mode)
        mapped = catalyst_by_theme.get(theme["id"], [])
        catalyst = _check(
            "supported" if mapped else ("not_enabled" if mode == "core" and not catalysts else "unknown"),
            f"关联催化链{len(mapped)}条",
            "at least one catalyst chain must affect the theme",
        )
        verification_ids = {
            verification_id
            for item in mapped
            for verification_id in item.get("verification_point_ids", [])
            if verification_id in future_point_ids
        }
        verification = _check(
            "supported" if verification_ids or theme["id"] in direct_verifications else "unknown",
            f"关联验证点{len(verification_ids)}个",
            "theme or its catalyst chain must have a future verification point",
        )
        statuses = {
            "longitudinal": longitudinal["status"],
            "horizontal": horizontal["status"],
            "liquidity": liquidity["status"],
            "concentration": concentration["status"],
            "catalyst": catalyst["status"],
            "verification": verification["status"],
        }
        if statuses["horizontal"] == "unknown":
            result = "insufficient"
        elif statuses["horizontal"] != "supported":
            result = "not_horizontal_confirmed"
        elif any(statuses[key] == "contradicted" for key in ("longitudinal", "liquidity", "concentration")):
            result = "regime_conflicted"
        elif all(status == "supported" for status in statuses.values()):
            result = "multi_axis_supported"
        else:
            result = "horizontal_only"
        rows.append(
            {
                "id": theme["id"],
                "name": theme["name"],
                "quadrant": theme.get("quadrant"),
                "checks": {
                    "longitudinal": {"status": longitudinal["status"], "evidence": "; ".join(item["evidence"] for item in longitudinal["checks"]) or "纵向证据未知"},
                    "horizontal": horizontal,
                    "liquidity": liquidity,
                    "concentration": concentration,
                    "catalyst": catalyst,
                    "verification": verification,
                },
                "result": result,
            }
        )
    return rows


def derive_four_axis(
    data: dict[str, Any],
    derived: dict[str, Any],
    history: dict[str, Any],
    resolved_verifications: list[dict[str, Any]],
) -> dict[str, Any]:
    longitudinal = _longitudinal(derived, history)
    horizontal = _horizontal(derived)
    depth = _depth(derived, data["analysis_mode"])
    verification = _verification(data, resolved_verifications)
    return {
        "analysis_mode": data["analysis_mode"],
        "deep_coverage": deep_coverage(data),
        "axes": {
            "longitudinal": longitudinal,
            "horizontal": horizontal,
            "depth": depth,
            "verification": verification,
        },
        "theme_intersections": _theme_rows(data, derived, longitudinal),
        "result_rules": {
            "multi_axis_supported": "horizontal, longitudinal, liquidity, concentration, catalyst and verification are all supported",
            "regime_conflicted": "horizontal is supported but longitudinal, liquidity or concentration is contradicted",
            "horizontal_only": "horizontal is supported while at least one other axis is unknown or not enabled",
            "not_horizontal_confirmed": "theme quadrant is not dual_confirmed",
            "insufficient": "horizontal evidence is unknown",
        },
        "note": "四轴只枚举证据状态和公开规则，不聚合成分数，不构成交易动作",
    }


def four_axis_signals(four_axis: dict[str, Any]) -> list[dict[str, str]]:
    rows = four_axis.get("theme_intersections", [])
    supported = [item["name"] for item in rows if item["result"] == "multi_axis_supported"]
    conflicted = [item["name"] for item in rows if item["result"] == "regime_conflicted"]
    signals = []
    if supported:
        signals.append(
            {
                "code": "four_axis_supported",
                "label": "多轴证据同时支持的主题",
                "rule": four_axis["result_rules"]["multi_axis_supported"],
                "evidence": "、".join(supported),
            }
        )
    if conflicted:
        signals.append(
            {
                "code": "four_axis_regime_conflict",
                "label": "横向双确认但纵深环境冲突",
                "rule": four_axis["result_rules"]["regime_conflicted"],
                "evidence": "、".join(conflicted),
            }
        )
    return signals
