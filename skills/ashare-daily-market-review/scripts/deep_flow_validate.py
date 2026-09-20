#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度层里「资金」与「催化」两块的契约校验（Schema 1.5 起独立成模块）。

拆出来的原因：这两块在 1.5 各自长了一条日常纪律，放在 `deep_validate.py` 里会
顶破单文件 700 行上限。校验口径与其它深度组件共用 `evidence.py` 的通用断言。

1.5 的两条纪律：

- 催化必须声明 `scope` 与 `catalyst_type`，宏观事件用 `macro_backdrop` 明确不绑主题；
  绑主题的催化必须写出 `transmission`（事件→主题的传导路径），用来拦住硬挂。
- 集中度允许在显式声明样本覆盖率的前提下输出「样本内口径」，但覆盖率与下限
  都必须由输入声明，不允许出现隐式默认值。
"""

import math

from datetime import date
from typing import Any

from evidence import deep_component, require_current_evidence, validate_event
from schema import (
    CATALYST_SCOPES,
    CATALYST_TYPES,
    CONCENTRATION_SCOPES,
    ReviewError,
    require_text,
)


def _percent(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ReviewError(f"{field} 必须是有限数值")
    number = float(value)
    if not 0 <= number <= 100:
        raise ReviewError(f"{field} 必须在0到100之间")
    return number


def validate_capital_co_movement(
    data: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    as_of: date,
    market_date: date,
    strict: bool,
) -> None:
    component = deep_component(data, "capital_co_movement")
    if component is None or component["availability"] == "unknown":
        return
    require_text(component, "methodology", "deep_analysis.capital_co_movement")
    if component.get("claim_type") != "co_movement_candidate":
        raise ReviewError("capital_co_movement.claim_type 必须是co_movement_candidate")
    thresholds = component.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ReviewError("capital_co_movement.thresholds 必须是object")
    _percent(
        thresholds.get("pseudo_sector_top1_share_pct"),
        "pseudo_sector_top1_share_pct",
    )
    scope = component.get("concentration_scope", "complete")
    if scope not in CONCENTRATION_SCOPES:
        raise ReviewError("capital_co_movement.concentration_scope 必须是complete或sample")
    sample_floor = None
    if scope == "sample":
        sample_floor = _percent(
            thresholds.get("min_sample_coverage_pct"),
            "capital_co_movement.thresholds.min_sample_coverage_pct",
        )
    elif "min_sample_coverage_pct" in thresholds:
        raise ReviewError(
            "concentration_scope=complete 时不该声明 min_sample_coverage_pct"
        )
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
        require_current_evidence(
            group.get("total_fund_flow"), f"{field}.total_fund_flow", as_of, market_date, "CNY"
        )
        require_current_evidence(
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
        if "sample_coverage_pct" in group:
            coverage = _percent(group["sample_coverage_pct"], f"{field}.sample_coverage_pct")
            if sample_floor is not None and coverage < sample_floor:
                raise ReviewError(
                    f"{field}.sample_coverage_pct 低于声明的 min_sample_coverage_pct"
                )
        elif scope == "sample":
            raise ReviewError(f"{field}.sample_coverage_pct 在样本口径下必须声明")
        contributions = group.get("contributions", [])
        if not isinstance(contributions, list):
            raise ReviewError(f"{field}.contributions 必须是数组")
        if complete and len(contributions) < 2:
            raise ReviewError(f"{field} 完整贡献分解至少需要2只个股")
        if scope == "sample" and not contributions:
            raise ReviewError(f"{field} 样本口径至少要有一只贡献股")
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
            require_current_evidence(
                item.get("fund_flow"), f"{sub}.fund_flow", as_of, market_date, "CNY"
            )
            contribution_sum += float(item["fund_flow"]["value"])
        # 板块级聚合值与成分股逐只加总存在供应商侧聚合噪声（实测约1e-8量级相对偏差），
        # 用相对容差放行噪声、拦下缺成分：缺一只成分股的偏差通常远超总额的百万分之一。
        if complete and not math.isclose(contribution_sum, total, rel_tol=1e-6, abs_tol=1.0):
            raise ReviewError(
                f"{field} 完整贡献分解之和必须等于total_fund_flow（相对容差1e-6）"
            )

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
    data: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    as_of: date,
    strict: bool,
) -> None:
    component = deep_component(data, "catalyst_chains")
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
        if not isinstance(item, dict):
            raise ReviewError(f"{field} 必须是object")
        validate_event(item, field, as_of, False)
        item_id = require_text(item, "id", field)
        if item_id in ids:
            raise ReviewError("catalyst_chains.id 不能重复")
        ids.add(item_id)
        require_text(item, "fact", field)
        require_text(item, "mechanism_hypothesis", field)
        if item.get("causal_status") not in {"hypothesis", "correlation_only"}:
            raise ReviewError(f"{field}.causal_status 不受支持")
        scope = item.get("scope")
        if scope is None:
            if strict:
                raise ReviewError(
                    f"{field}.scope 必须声明：theme（绑主题）或 macro_backdrop（宏观背景，不绑主题）"
                )
            scope = "theme"
        if scope not in CATALYST_SCOPES:
            raise ReviewError(f"{field}.scope 不受支持")
        catalyst_type = item.get("catalyst_type")
        if catalyst_type is None:
            if strict:
                raise ReviewError(f"{field}.catalyst_type 必须声明")
        elif catalyst_type not in CATALYST_TYPES:
            raise ReviewError(f"{field}.catalyst_type 不受支持")
        if "transmission" in item:
            require_text(item, "transmission", field)
        elif strict:
            raise ReviewError(f"{field}.transmission 必须写出事件到主题/市场的传导路径")
        affected = item.get("affected_theme_ids")
        if scope == "macro_backdrop":
            if affected != []:
                raise ReviewError(
                    f"{field}.scope=macro_backdrop 时 affected_theme_ids 必须为空数组，不得挂主题"
                )
            if catalyst_type not in {"macro", "policy"}:
                raise ReviewError(
                    f"{field} 宏观背景只用于 macro/policy 类事件；其它类型请用 scope=theme"
                )
        elif not isinstance(affected, list) or not affected or not set(affected) <= theme_ids:
            raise ReviewError(f"{field}.affected_theme_ids 存在悬空引用或为空")
        counter = item.get("counter_evidence")
        if not isinstance(counter, list) or not counter or not all(
            isinstance(value, str) and value.strip() for value in counter
        ):
            raise ReviewError(f"{field}.counter_evidence 必须是非空字符串数组")
        verification_ids = item.get("verification_point_ids")
        if not isinstance(verification_ids, list) or not verification_ids or not set(verification_ids) <= point_ids:
            raise ReviewError(f"{field}.verification_point_ids 存在悬空引用或为空")
