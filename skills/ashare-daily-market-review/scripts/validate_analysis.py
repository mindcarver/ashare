#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1.2 分析层的契约校验：双确认主线矩阵与延续性检验。

从 validate.py 抽出，保持每个模块在审计的 700 行上限内。这里只做跨章节引用与
口径一致性检查——主题引用的板块必须真实存在于 `sectors`，沿用同一次校验的
`as_of` 与 `market_date`，不重复实现通用证据断言。
"""

import math

from datetime import date
from typing import Any

from evidence import require_market_date, validate_evidence, validate_universe
from schema import (
    FUND_METHODS,
    MAINLINE_QUADRANT_RULES,
    OPTIONAL_MAINLINE_QUADRANT_RULES,
    ReviewError,
    parse_date,
    require_text,
    value,
)


def validate_mainline_matrix(
    sections: dict[str, dict[str, Any]], as_of: date, market_date: date
) -> None:
    """双确认主线矩阵：主题必须声明成分板块引用，象限阈值必须显式给出。"""
    section = sections["mainline_matrix"]
    if section["availability"] == "unknown":
        return
    require_text(section, "classification", "sections.mainline_matrix")
    require_text(section, "methodology", "sections.mainline_matrix")
    sectors = sections["sectors"]
    if sectors["availability"] == "unknown":
        raise ReviewError("mainline_matrix 需要 sectors 章节提供板块基准")
    if section["classification"] != sectors["classification"]:
        raise ReviewError(
            "sections.mainline_matrix.classification 必须与sections.sectors.classification一致"
        )
    rules = section.get("quadrant_rules")
    if not isinstance(rules, dict):
        raise ReviewError("sections.mainline_matrix.quadrant_rules 必须是object")
    for key in MAINLINE_QUADRANT_RULES:
        if key not in rules:
            raise ReviewError(f"quadrant_rules.{key} 必须显式声明，不得使用隐藏默认值")
    threshold = rules.get("limit_up_threshold")
    if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
        raise ReviewError("quadrant_rules.limit_up_threshold 必须是正整数")
    capital = rules.get("capital_threshold_cny")
    if (
        isinstance(capital, bool)
        or not isinstance(capital, (int, float))
        or not math.isfinite(capital)
    ):
        raise ReviewError("quadrant_rules.capital_threshold_cny 必须是有限数值")
    patient = rules.get("bleeding_threshold_cny")
    if patient is not None:
        if (
            isinstance(patient, bool)
            or not isinstance(patient, (int, float))
            or not math.isfinite(patient)
        ):
            raise ReviewError(
                "quadrant_rules.bleeding_threshold_cny 必须是有限数值"
            )
        # 失血线必须低于资金线，否则「情绪失血」与「资金先行」的判定区间会重叠或倒挂。
        if float(patient) >= float(capital):
            raise ReviewError(
                "quadrant_rules.bleeding_threshold_cny 必须严格小于 capital_threshold_cny"
            )
    unsupported = sorted(
        key
        for key in rules
        if key not in MAINLINE_QUADRANT_RULES and key not in OPTIONAL_MAINLINE_QUADRANT_RULES
    )
    if unsupported:
        raise ReviewError(
            "quadrant_rules 含不支持的键：" + "、".join(unsupported)
        )

    board_ids = {item["id"] for item in sectors["items"]}
    themes = section.get("themes")
    if not isinstance(themes, list) or not themes:
        raise ReviewError("sections.mainline_matrix.themes 必须是非空数组")
    theme_ids: set[str] = set()
    for index, theme in enumerate(themes):
        field = f"sections.mainline_matrix.themes[{index}]"
        if not isinstance(theme, dict):
            raise ReviewError(f"{field} 必须是object")
        require_text(theme, "id", field)
        require_text(theme, "name", field)
        if theme["id"] in theme_ids:
            raise ReviewError("mainline_matrix.themes.id 不能重复")
        theme_ids.add(theme["id"])
        boards = theme.get("boards")
        if not isinstance(boards, list) or not boards or not all(
            isinstance(item, str) and item.strip() for item in boards
        ):
            raise ReviewError(f"{field}.boards 必须是非空字符串数组")
        missing = sorted(board for board in boards if board not in board_ids)
        if missing:
            raise ReviewError(
                f"{field}.boards 引用了sectors中不存在的板块：{'、'.join(missing)}"
            )
        validate_evidence(
            theme.get("limit_up"),
            f"{field}.limit_up",
            as_of,
            "count",
            "nonnegative",
        )
        if "limit_up_fund_flow" in theme:
            validate_evidence(
                theme["limit_up_fund_flow"], f"{field}.limit_up_fund_flow", as_of, "CNY"
            )
        if "prev_pool_premium_pct" in theme:
            validate_evidence(
                theme["prev_pool_premium_pct"],
                f"{field}.prev_pool_premium_pct",
                as_of,
                "percent",
            )
        if section["availability"] == "available":
            require_market_date(theme["limit_up"], f"{field}.limit_up", market_date)


def validate_prev_pool_performance(
    sections: dict[str, dict[str, Any]], as_of: date, market_date: date
) -> None:
    """延续性检验：必须与 breadth 同股票池，且前值日期严格早于当前交易日。"""
    section = sections["prev_pool_performance"]
    if section["availability"] == "unknown":
        return
    validate_universe(
        section.get("universe"), "sections.prev_pool_performance.universe"
    )
    breadth = sections["breadth"]
    if breadth["availability"] == "unknown":
        raise ReviewError("prev_pool_performance 需要 breadth 章节提供股票池基准")
    if section["universe"] != breadth["universe"]:
        raise ReviewError(
            "prev_pool_performance.universe 必须与breadth.universe一致"
        )
    previous_date = parse_date(
        section.get("previous_market_date"),
        "sections.prev_pool_performance.previous_market_date",
    )
    if previous_date >= market_date:
        raise ReviewError(
            "prev_pool_performance.previous_market_date 必须早于market_date"
        )
    metrics = section.get("metrics")
    if not isinstance(metrics, dict):
        raise ReviewError("sections.prev_pool_performance.metrics 必须是object")
    required = ("pool_size", "avg_change_pct", "promotion_count")
    if section["availability"] == "available" and any(
        name not in metrics for name in required
    ):
        raise ReviewError("available prev_pool_performance 缺少必需指标")
    for name, evidence in metrics.items():
        if name in ("pool_size", "promotion_count"):
            validate_evidence(
                evidence,
                f"sections.prev_pool_performance.metrics.{name}",
                as_of,
                "count",
                "positive" if name == "pool_size" else "nonnegative",
            )
        else:
            validate_evidence(
                evidence,
                f"sections.prev_pool_performance.metrics.{name}",
                as_of,
                "percent",
            )
    pool_size = value({"metrics": metrics}, "pool_size")
    promotion = value({"metrics": metrics}, "promotion_count")
    if pool_size is not None and promotion is not None and promotion > pool_size:
        raise ReviewError("prev_pool_performance.promotion_count 不能大于pool_size")
    health = section.get("health_threshold_pct")
    if health is not None and (
        isinstance(health, bool)
        or not isinstance(health, (int, float))
        or not math.isfinite(health)
    ):
        raise ReviewError(
            "sections.prev_pool_performance.health_threshold_pct 必须是有限数值"
        )
    groups = section.get("by_group", [])
    if not isinstance(groups, list):
        raise ReviewError("sections.prev_pool_performance.by_group 必须是数组")
    for index, group in enumerate(groups):
        field = f"sections.prev_pool_performance.by_group[{index}]"
        if not isinstance(group, dict):
            raise ReviewError(f"{field} 必须是object")
        require_text(group, "id", field)
        require_text(group, "name", field)
        validate_evidence(group.get("count"), f"{field}.count", as_of, "count", "positive")
        validate_evidence(
            group.get("avg_change_pct"), f"{field}.avg_change_pct", as_of, "percent"
        )
    if section["availability"] == "available":
        for name in required:
            require_market_date(
                metrics[name],
                f"sections.prev_pool_performance.metrics.{name}",
                market_date,
            )


def _validate_security_evidence(
    item: dict[str, Any],
    field: str,
    as_of: date,
    market_date: date,
    available: bool,
) -> int:
    """板块内个股与连板高标共用的证据校验，返回声明的「质量证据」条数。

    `change_pct` 允许为负（它描述涨跌），`fund_flow` 允许为负（它描述净流出方向），
    只有 `turnover_pct` 必须非负。资金流是供应商推导时**必须**同时声明方法类别，
    否则无法在报告里披露口径，直接拒绝。
    """
    quality = 0
    for key, unit, constraint in (
        ("change_pct", "percent", "any"),
        ("fund_flow", "CNY", "any"),
        ("turnover_pct", "percent", "nonnegative"),
    ):
        if key not in item:
            continue
        validate_evidence(item[key], f"{field}.{key}", as_of, unit, constraint)
        if available:
            require_market_date(item[key], f"{field}.{key}", market_date)
        if key != "change_pct":
            quality += 1
    if "fund_flow" in item:
        if item.get("fund_flow_method_category") not in FUND_METHODS:
            raise ReviewError(f"{field}.fund_flow_method_category 不受支持")
    elif "fund_flow_method_category" in item:
        raise ReviewError(f"{field}.fund_flow_method_category 只能随fund_flow一起声明")
    return quality


def validate_streak_distribution(
    sections: dict[str, dict[str, Any]], as_of: date, market_date: date
) -> None:
    """连板梯队分布：各档家数必须与同一股票池的涨停总数、最高板严格自洽。"""
    sentiment = sections["short_term_sentiment"]
    distribution = sentiment.get("streak_distribution")
    if distribution is None:
        return
    if sentiment["availability"] == "unknown":
        raise ReviewError(
            "sections.short_term_sentiment.streak_distribution 不能在章节为unknown时声明"
        )
    if not isinstance(distribution, list) or not distribution:
        raise ReviewError(
            "sections.short_term_sentiment.streak_distribution 必须是非空数组"
        )
    streaks: set[int] = set()
    total = 0
    for index, tier in enumerate(distribution):
        field = f"sections.short_term_sentiment.streak_distribution[{index}]"
        if not isinstance(tier, dict):
            raise ReviewError(f"{field} 必须是object")
        streak = tier.get("streak")
        if isinstance(streak, bool) or not isinstance(streak, int) or streak < 1:
            raise ReviewError(f"{field}.streak 必须是正整数")
        if streak in streaks:
            raise ReviewError("streak_distribution.streak 不能重复")
        streaks.add(streak)
        validate_evidence(tier.get("count"), f"{field}.count", as_of, "count", "nonnegative")
        if sentiment["availability"] == "available":
            require_market_date(tier["count"], f"{field}.count", market_date)
        total += int(float(tier["count"]["value"]))
    highest = value(sentiment, "highest_streak")
    if highest is not None and max(streaks) != int(highest):
        raise ReviewError("streak_distribution 的最高档必须等于short_term_sentiment最高连板")
    limit_up = value(sections["breadth"], "limit_up")
    if limit_up is not None and total != int(limit_up):
        raise ReviewError(
            "streak_distribution 各档家数之和必须等于breadth.limit_up（须包含首板）"
        )


def validate_high_boards(
    sections: dict[str, dict[str, Any]], as_of: date, market_date: date
) -> None:
    """最高板质量：每只高标必须带至少一项质量证据，且板数不超过声明最高板。"""
    sentiment = sections["short_term_sentiment"]
    boards = sentiment.get("high_boards")
    if boards is None:
        return
    if sentiment["availability"] == "unknown":
        raise ReviewError(
            "sections.short_term_sentiment.high_boards 不能在章节为unknown时声明"
        )
    if not isinstance(boards, list) or not boards:
        raise ReviewError("sections.short_term_sentiment.high_boards 必须是非空数组")
    highest = value(sentiment, "highest_streak")
    names: set[str] = set()
    for index, board in enumerate(boards):
        field = f"sections.short_term_sentiment.high_boards[{index}]"
        if not isinstance(board, dict):
            raise ReviewError(f"{field} 必须是object")
        require_text(board, "name", field)
        if board["name"] in names:
            raise ReviewError("high_boards.name 不能重复")
        names.add(board["name"])
        for key in ("code", "note"):
            if key in board:
                require_text(board, key, field)
        streak = board.get("streak")
        if isinstance(streak, bool) or not isinstance(streak, int) or streak < 2:
            raise ReviewError(f"{field}.streak 必须是不小于2的整数")
        if highest is not None and streak > int(highest):
            raise ReviewError(f"{field}.streak 不能高于short_term_sentiment最高连板")
        quality = _validate_security_evidence(
            board, field, as_of, market_date, sentiment["availability"] == "available"
        )
        if quality == 0:
            raise ReviewError(f"{field} 至少需要fund_flow或turnover_pct之一作为质量证据")


def validate_concept_view(
    sections: dict[str, dict[str, Any]], as_of: date, market_date: date
) -> None:
    """概念层资金流：必须是区别于行业层的第二套分类，不能与行业层同体系混排。"""
    sectors = sections["sectors"]
    view = sectors.get("concept_view")
    if view is None:
        return
    if sectors["availability"] == "unknown":
        raise ReviewError("sections.sectors.concept_view 不能在sectors为unknown时声明")
    if not isinstance(view, dict):
        raise ReviewError("sections.sectors.concept_view 必须是object")
    require_text(view, "classification", "sections.sectors.concept_view")
    require_text(view, "status_reason", "sections.sectors.concept_view")
    if view["classification"] == sectors["classification"]:
        raise ReviewError(
            "sections.sectors.concept_view.classification 必须区别于sectors.classification"
        )
    items = view.get("items")
    if not isinstance(items, list) or not items:
        raise ReviewError("sections.sectors.concept_view.items 必须是非空数组")
    ids: set[str] = set()
    available = sectors["availability"] == "available"
    for index, item in enumerate(items):
        field = f"sections.sectors.concept_view.items[{index}]"
        if not isinstance(item, dict):
            raise ReviewError(f"{field} 必须是object")
        require_text(item, "id", field)
        require_text(item, "name", field)
        if item["id"] in ids:
            raise ReviewError("concept_view.items.id 不能重复")
        ids.add(item["id"])
        if "change_pct" not in item and "fund_flow" not in item:
            raise ReviewError(f"{field} 至少需要change_pct或fund_flow之一")
        if "change_pct" in item:
            validate_evidence(item["change_pct"], f"{field}.change_pct", as_of, "percent")
            if available:
                require_market_date(item["change_pct"], f"{field}.change_pct", market_date)
        if "fund_flow" in item:
            validate_evidence(item["fund_flow"], f"{field}.fund_flow", as_of, "CNY")
            if item.get("fund_flow_method_category") not in FUND_METHODS:
                raise ReviewError(f"{field}.fund_flow_method_category 不受支持")
            if available:
                require_market_date(item["fund_flow"], f"{field}.fund_flow", market_date)
        elif "fund_flow_method_category" in item:
            raise ReviewError(f"{field}.fund_flow_method_category 只能随fund_flow一起声明")


def validate_sector_leaders(
    sections: dict[str, dict[str, Any]], as_of: date, market_date: date
) -> None:
    """板块内重点个股：只做板块归因，每只至少给涨跌幅或资金流之一。"""
    sectors = sections["sectors"]
    if sectors["availability"] == "unknown":
        return
    available = sectors["availability"] == "available"
    for index, item in enumerate(sectors.get("items", [])):
        leaders = item.get("leaders")
        if leaders is None:
            continue
        field = f"sections.sectors.items[{index}].leaders"
        if not isinstance(leaders, list) or not leaders:
            raise ReviewError(f"{field} 必须是非空数组")
        names: set[str] = set()
        for position, leader in enumerate(leaders):
            sub = f"{field}[{position}]"
            if not isinstance(leader, dict):
                raise ReviewError(f"{sub} 必须是object")
            require_text(leader, "name", sub)
            if leader["name"] in names:
                raise ReviewError(f"{field} 内个股name不能重复")
            names.add(leader["name"])
            for key in ("code", "note"):
                if key in leader:
                    require_text(leader, key, sub)
            if "streak" in leader:
                streak = leader["streak"]
                if isinstance(streak, bool) or not isinstance(streak, int) or streak < 1:
                    raise ReviewError(f"{sub}.streak 必须是正整数")
            if "change_pct" not in leader and "fund_flow" not in leader:
                raise ReviewError(f"{sub} 至少需要change_pct或fund_flow之一")
            _validate_security_evidence(leader, sub, as_of, market_date, available)


def validate_extended_structures(
    sections: dict[str, dict[str, Any]], as_of: date, market_date: date
) -> None:
    """1.2 发布后追加的四项可选结构。全部缺省时不产生任何新输出。"""
    validate_streak_distribution(sections, as_of, market_date)
    validate_high_boards(sections, as_of, market_date)
    validate_concept_view(sections, as_of, market_date)
    validate_sector_leaders(sections, as_of, market_date)

