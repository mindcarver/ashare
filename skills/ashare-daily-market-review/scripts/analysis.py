#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1.2 分析层的派生规则：延续性检验、双确认主线矩阵、阈值体检。

从 derive.py 抽出，保持每个模块在审计的 700 行上限内。这里只做确定性派生：
同样的已验证输入必须得到同样的象限、晋级率与体检结果；任何阈值都由输入显式声明，
缺省即不作判断，绝不回退到隐藏默认值。
"""

from typing import Any

from schema import HEALTH_THRESHOLD_KEYS, active_quadrant_order, value


def derive_prev_pool_performance(
    sections: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """延续性检验：前一交易日涨停池在当日的整体表现与晋级率。

    这是「回溯归因」，与 `verification_points` 的「前瞻验证」互补——后者问明日条件会不会
    成立，前者问昨日判断到今天兑现了没有。健康线阈值必须由输入声明，缺省即不作判断。
    """
    section = sections["prev_pool_performance"]
    if section["availability"] == "unknown":
        return None
    pool_size = value(section, "pool_size")
    promotion = value(section, "promotion_count")
    promotion_rate = None
    if pool_size is not None and promotion is not None and pool_size > 0:
        promotion_rate = round(promotion / pool_size * 100, 6)
    threshold = section.get("health_threshold_pct")
    health = None
    if promotion_rate is not None and threshold is not None:
        health = (
            "at_or_above_line"
            if promotion_rate >= float(threshold)
            else "below_line"
        )
    return {
        "availability": section["availability"],
        "status_reason": section["status_reason"],
        "previous_market_date": section["previous_market_date"],
        "universe_id": section["universe"]["id"],
        "pool_size": pool_size,
        "promotion_count": promotion,
        "promotion_rate_pct": promotion_rate,
        "health_threshold_pct": float(threshold) if threshold is not None else None,
        "health": health,
        "avg_change_pct": value(section, "avg_change_pct"),
        "median_change_pct": value(section, "median_change_pct"),
        "groups": [
            {
                "id": group["id"],
                "name": group["name"],
                "count": value({"metrics": group}, "count"),
                "avg_change_pct": value({"metrics": group}, "avg_change_pct"),
            }
            for group in section.get("by_group", [])
        ],
    }


def derive_mainline_matrix(
    sections: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """双确认主线矩阵：把「游资情绪面 × 机构资金面」变成可复算的象限分类。

    主题的成分板块由输入显式声明，板块资金流从 `sectors.items[].fund_flow` 求和；
    任一声明板块缺少资金流时该主题象限返回 unknown，不用 0 或部分求和冒充。
    板块涨跌幅在多个声明板块之间取等权均值，并在报告中显式标注为等权。
    """
    section = sections["mainline_matrix"]
    if section["availability"] == "unknown":
        return None
    board_lookup = {item["id"]: item for item in sections["sectors"]["items"]}
    rules = section["quadrant_rules"]
    limit_up_threshold = rules["limit_up_threshold"]
    capital_threshold = float(rules["capital_threshold_cny"])
    bleeding_threshold = rules.get("bleeding_threshold_cny")
    if bleeding_threshold is not None:
        bleeding_threshold = float(bleeding_threshold)
    themes = []
    for theme in section["themes"]:
        boards = [board_lookup[board_id] for board_id in theme["boards"]]
        missing_flow = sorted(
            board["id"] for board in boards if board.get("fund_flow") is None
        )
        if missing_flow:
            board_fund_flow = None
        else:
            board_fund_flow = sum(
                float(board["fund_flow"]["value"]) for board in boards
            )
        board_change = round(
            sum(float(board["change_pct"]["value"]) for board in boards) / len(boards),
            6,
        )
        limit_up = float(theme["limit_up"]["value"])
        if board_fund_flow is None:
            quadrant = "unknown"
            quadrant_rule = "缺少板块资金流：" + "、".join(missing_flow)
        else:
            capital_positive = board_fund_flow > capital_threshold
            sentiment_positive = limit_up >= limit_up_threshold
            if capital_positive and sentiment_positive:
                quadrant = "dual_confirmed"
                quadrant_rule = (
                    f"board_fund_flow_cny > {capital_threshold:g} "
                    f"且 limit_up_count >= {limit_up_threshold}"
                )
            elif capital_positive:
                quadrant = "capital_led"
                quadrant_rule = (
                    f"board_fund_flow_cny > {capital_threshold:g} "
                    f"且 limit_up_count < {limit_up_threshold}"
                )
            elif sentiment_positive:
                # 声明失血线后，把「家数达标」再按资金流出深度拆一档：
                # 资金弱正/小额流出 = 真实情绪脉冲；大额净流出 = 失血中继。
                if bleeding_threshold is not None and board_fund_flow <= bleeding_threshold:
                    quadrant = "sentiment_bleeding"
                    quadrant_rule = (
                        f"limit_up_count >= {limit_up_threshold} "
                        f"且 board_fund_flow_cny <= {bleeding_threshold:g}"
                    )
                else:
                    quadrant = "sentiment_only"
                    quadrant_rule = (
                        f"limit_up_count >= {limit_up_threshold} "
                        f"且 board_fund_flow_cny <= {capital_threshold:g}"
                    )
            else:
                quadrant = "bleeding"
                quadrant_rule = (
                    f"limit_up_count < {limit_up_threshold} "
                    f"且 board_fund_flow_cny <= {capital_threshold:g}"
                )
        themes.append(
            {
                "id": theme["id"],
                "name": theme["name"],
                "boards": list(theme["boards"]),
                "limit_up_count": limit_up,
                "limit_up_fund_flow_cny": (
                    float(theme["limit_up_fund_flow"]["value"])
                    if "limit_up_fund_flow" in theme
                    else None
                ),
                "prev_pool_premium_pct": (
                    float(theme["prev_pool_premium_pct"]["value"])
                    if "prev_pool_premium_pct" in theme
                    else None
                ),
                "board_fund_flow_cny": board_fund_flow,
                "board_change_pct_equal_weight": board_change,
                "missing_board_fund_flow": missing_flow,
                "quadrant": quadrant,
                "quadrant_rule": quadrant_rule,
            }
        )
    counts = {
        name: sum(theme["quadrant"] == name for theme in themes)
        for name in active_quadrant_order(bleeding_threshold is not None)
    }
    declared_rules: dict[str, Any] = {
        "limit_up_threshold": limit_up_threshold,
        "capital_threshold_cny": capital_threshold,
    }
    if bleeding_threshold is not None:
        declared_rules["bleeding_threshold_cny"] = bleeding_threshold
    return {
        "availability": section["availability"],
        "status_reason": section["status_reason"],
        "classification": section["classification"],
        "methodology": section["methodology"],
        "quadrant_rules": declared_rules,
        "themes": themes,
        "quadrant_counts": counts,
    }


def derive_sentiment_health_check(
    sections: dict[str, dict[str, Any]], derived: dict[str, Any]
) -> dict[str, Any] | None:
    """短线情绪多条件阈值体检：逐条给出观察值、阈值与成立与否。

    只枚举条件成立情况，不聚合成任何总分，也不推导入场结论。未声明 `health_thresholds`
    时不体检，绝不套用隐藏默认值。
    """
    sentiment = sections["short_term_sentiment"]
    if sentiment["availability"] == "unknown":
        return None
    thresholds = sentiment.get("health_thresholds")
    if not thresholds:
        return None
    prev_pool = derived.get("prev_pool_performance") or {}
    observed = {
        "limit_up_min": (value(sections["breadth"], "limit_up"), "count", ">="),
        "limit_down_max": (value(sections["breadth"], "limit_down"), "count", "<="),
        "open_board_rate_max_pct": (
            derived["short_term_sentiment"].get("open_board_rate_pct"),
            "percent",
            "<=",
        ),
        "promotion_rate_min_pct": (prev_pool.get("promotion_rate_pct"), "percent", ">="),
        "highest_streak_min": (value(sentiment, "highest_streak"), "count", ">="),
    }
    checks = []
    for key in HEALTH_THRESHOLD_KEYS:
        if key not in thresholds:
            continue
        number, unit, operator = observed[key]
        target = float(thresholds[key])
        if number is None:
            checks.append(
                {
                    "code": key,
                    "operator": operator,
                    "threshold": target,
                    "unit": unit,
                    "observed": None,
                    "status": "unknown",
                    "reason": "缺少该条件的观察值",
                }
            )
            continue
        passed = number >= target if operator == ">=" else number <= target
        checks.append(
            {
                "code": key,
                "operator": operator,
                "threshold": target,
                "unit": unit,
                "observed": float(number),
                "status": "passed" if passed else "failed",
                "reason": None,
            }
        )
    evaluated = [check for check in checks if check["status"] != "unknown"]
    return {
        "checks": checks,
        "evaluated_count": len(evaluated),
        "passed_count": sum(check["status"] == "passed" for check in evaluated),
        "unresolved": [
            check["code"] for check in checks if check["status"] == "unknown"
        ],
        "note": "逐条阈值观察，不聚合成分数，也不构成入场信号或仓位建议",
    }


QUADRANT_SIGNAL_LABELS = {
    "dual_confirmed": ("mainline_dual_confirmed", "双确认主题：涨停家数达标且板块资金净流入"),
    "capital_led": ("mainline_capital_led", "资金先行主题：板块资金净流入但涨停家数未达标"),
    "sentiment_only": ("mainline_sentiment_only", "情绪脉冲主题：涨停家数达标但板块资金未净流入"),
    "sentiment_bleeding": (
        "mainline_sentiment_bleeding",
        "情绪失血主题：涨停家数达标但板块资金大额净流出",
    ),
    "bleeding": ("mainline_bleeding", "失血主题：涨停家数未达标且板块资金未净流入"),
    "unknown": ("mainline_quadrant_unknown", "象限待补：声明板块缺少资金流"),
}


def prev_pool_signal(prev_pool: dict[str, Any] | None) -> list[dict[str, str]]:
    if not prev_pool or prev_pool["promotion_rate_pct"] is None or prev_pool["health"] is None:
        return []
    rate = prev_pool["promotion_rate_pct"]
    threshold = prev_pool["health_threshold_pct"]
    healthy = prev_pool["health"] == "at_or_above_line"
    return [
        {
            "code": "prev_pool_promotion_line",
            "label": "昨日涨停池晋级率"
            + ("达到声明健康线" if healthy else "低于声明健康线"),
            "rule": f"promotion_rate_pct >= {threshold:g}",
            "evidence": (
                f"前一日（{prev_pool['previous_market_date']}）涨停池 "
                f"{prev_pool['pool_size']:.0f} 只，当日再涨停 {prev_pool['promotion_count']:.0f} 只，"
                f"晋级率 {rate:.2f}%（健康线 {threshold:g}%）"
            ),
        }
    ]


def mainline_signals(mainline: dict[str, Any] | None) -> list[dict[str, str]]:
    if not mainline:
        return []
    signals = []
    # 未声明 bleeding_threshold_cny 时不会有主题落入 sentiment_bleeding，该格自然跳过，
    # 信号顺序与内容保持不变。
    for quadrant in active_quadrant_order(
        mainline["quadrant_rules"].get("bleeding_threshold_cny") is not None
    ):
        members = [
            theme for theme in mainline["themes"] if theme["quadrant"] == quadrant
        ]
        if not members:
            continue
        code, label = QUADRANT_SIGNAL_LABELS[quadrant]
        detail = "、".join(
            f"{theme['name']}（涨停 {theme['limit_up_count']:.0f}，板块资金 "
            + (
                "unknown"
                if theme["board_fund_flow_cny"] is None
                else f"{theme['board_fund_flow_cny'] / 1e8:+.2f}亿元"
            )
            + "）"
            for theme in members
        )
        signals.append(
            {
                "code": code,
                "label": label,
                "rule": (
                    mainline["themes"][0]["quadrant_rule"]
                    if len(mainline["themes"]) == 1
                    else f"quadrant == {quadrant}"
                ),
                "evidence": detail,
            }
        )
    return signals


def derive_streak_distribution(
    sections: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """连板梯队分布：把「几板几家」变成可复算的档位表。

    只做事实归集——各档家数、首板/连板家数、最高板家数与首板占比。**不设**任何
    隐藏阈值，也不据此推导入场；档位之和与最高档已在契约层与同一股票池对齐。
    """
    distribution = sections["short_term_sentiment"].get("streak_distribution")
    if not distribution:
        return None
    tiers = sorted(
        (
            {
                "streak": int(tier["streak"]),
                "count": int(float(tier["count"]["value"])),
            }
            for tier in distribution
        ),
        key=lambda item: -item["streak"],
    )
    total = sum(tier["count"] for tier in tiers)
    first_board = next((tier["count"] for tier in tiers if tier["streak"] == 1), None)
    return {
        "tiers": tiers,
        "total": total,
        "highest_streak": tiers[0]["streak"],
        "highest_streak_count": tiers[0]["count"],
        "first_board_count": first_board,
        "continued_count": (total - first_board) if first_board is not None else None,
        "first_board_share_pct": (
            round(first_board / total * 100, 6)
            if first_board is not None and total > 0
            else None
        ),
    }


def derive_high_boards(
    sections: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """最高板质量：逐个高标列出板数与质量证据，并统计主力净流入/流出的家数。

    这里只数「净流入为正/为负」的只数（零点是资金流方向的天然分界，不是调参阈值），
    不作强弱评级，也不构成个股推荐。
    """
    boards = sections["short_term_sentiment"].get("high_boards")
    if not boards:
        return None
    ordered = sorted(
        (
            {
                "name": board["name"],
                "code": board.get("code"),
                "streak": int(board["streak"]),
                "change_pct": (
                    float(board["change_pct"]["value"]) if "change_pct" in board else None
                ),
                "fund_flow_cny": (
                    float(board["fund_flow"]["value"]) if "fund_flow" in board else None
                ),
                "fund_flow_method_category": board.get("fund_flow_method_category"),
                "turnover_pct": (
                    float(board["turnover_pct"]["value"])
                    if "turnover_pct" in board
                    else None
                ),
                "note": board.get("note"),
            }
            for board in boards
        ),
        key=lambda item: (-item["streak"], item["name"]),
    )
    flows = [item["fund_flow_cny"] for item in ordered if item["fund_flow_cny"] is not None]
    return {
        "boards": ordered,
        "count": len(ordered),
        "declared_fund_flow_count": len(flows),
        "inflow_count": sum(flow > 0 for flow in flows),
        "outflow_count": sum(flow < 0 for flow in flows),
        "flat_count": sum(flow == 0 for flow in flows),
    }


def derive_concept_flows(
    sections: dict[str, dict[str, Any]]
) -> dict[str, Any] | None:
    """概念层资金流：与行业层分开的第二套分类，按净流入/净流出分离排序。

    两套分类**不合并排序**——行业层看产业归属，概念层看资金主题，混排会把
    「MSCI中国」「融资融券」这类风格项读成行业。
    """
    view = sections["sectors"].get("concept_view")
    if not view:
        return None
    items = [
        {
            "id": item["id"],
            "name": item["name"],
            "change_pct": (
                float(item["change_pct"]["value"]) if "change_pct" in item else None
            ),
            "fund_flow_cny": (
                float(item["fund_flow"]["value"]) if "fund_flow" in item else None
            ),
            "fund_flow_method_category": item.get("fund_flow_method_category"),
        }
        for item in view["items"]
    ]
    inflows = sorted(
        (item for item in items if (item["fund_flow_cny"] or 0) > 0),
        key=lambda item: (-item["fund_flow_cny"], item["id"]),
    )
    outflows = sorted(
        (item for item in items if (item["fund_flow_cny"] or 0) < 0),
        key=lambda item: (item["fund_flow_cny"], item["id"]),
    )
    return {
        "classification": view["classification"],
        "status_reason": view["status_reason"],
        "items": items,
        "inflows": inflows,
        "outflows": outflows,
    }


def derive_sector_leaders(
    sections: dict[str, dict[str, Any]]
) -> list[dict[str, Any]] | None:
    """板块内重点个股：只列输入显式声明的个股，按资金流强弱排列供归因。

    这是板块归因的下钻层，不是选股输出——报告必须显式声明它不构成个股推荐。
    """
    boards = []
    for item in sections["sectors"].get("items", []):
        leaders = item.get("leaders")
        if not leaders:
            continue
        rows = sorted(
            (
                {
                    "name": leader["name"],
                    "code": leader.get("code"),
                    "change_pct": (
                        float(leader["change_pct"]["value"])
                        if "change_pct" in leader
                        else None
                    ),
                    "fund_flow_cny": (
                        float(leader["fund_flow"]["value"])
                        if "fund_flow" in leader
                        else None
                    ),
                    "fund_flow_method_category": leader.get("fund_flow_method_category"),
                    "turnover_pct": (
                        float(leader["turnover_pct"]["value"])
                        if "turnover_pct" in leader
                        else None
                    ),
                    "streak": int(leader["streak"]) if "streak" in leader else None,
                    "note": leader.get("note"),
                }
                for leader in leaders
            ),
            key=lambda row: (
                -(row["fund_flow_cny"] if row["fund_flow_cny"] is not None else float("-inf")),
                row["name"],
            ),
        )
        boards.append({"id": item["id"], "name": item["name"], "leaders": rows})
    return boards or None
