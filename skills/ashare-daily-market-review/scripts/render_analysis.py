#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1.2 分析层的渲染片段：延续性检验、双确认主线矩阵、阈值体检。

从 render.py 抽出，保持每个模块在审计的 700 行上限内。这里只做「把已校验的派生结果
排版成文字」，不重新计算任何指标、不引入新的口径。
"""

from typing import Any

from formatting import (
    fmt_flow_cny,
    fmt_level,
    fmt_signed_pct,
    html_text,
    public_classification,
    public_status_reason,
    unknown_line,
    value_tone,
)
from schema import active_quadrant_order

HEALTH_STATUS = {
    "passed": ("ok", "成立"),
    "failed": ("no", "未成立"),
    "unknown": ("wait", "缺观察值"),
}

QUADRANT_LABELS = {
    "dual_confirmed": "双确认",
    "capital_led": "资金先行",
    "sentiment_only": "情绪脉冲",
    "sentiment_bleeding": "情绪失血",
    "bleeding": "失血",
    "unknown": "象限待补",
}

QUADRANT_DOT = {
    "dual_confirmed": "ok",
    "capital_led": "wait",
    "sentiment_only": "wait",
    "sentiment_bleeding": "no",
    "bleeding": "no",
    "unknown": "wait",
}


def active_quadrants(mainline: dict[str, Any]) -> tuple[str, ...]:
    """图例、计数与读法的输出顺序。

    未声明 `bleeding_threshold_cny` 时不展示「情绪失血」格，保证既有 1.2 输入的报告
    与摘要逐字节不变；声明后才多出这一格。真源见 `schema.active_quadrant_order`。
    """
    return active_quadrant_order(
        mainline["quadrant_rules"].get("bleeding_threshold_cny") is not None
    )


def quadrant_distribution(counts: dict[str, int], names: tuple[str, ...]) -> str:
    return "、".join(f"{QUADRANT_LABELS[name]} {counts[name]} 个" for name in names)


def bleeding_clause(rules: dict[str, Any], *, html: bool) -> str:
    """声明失血线时追加的规则片段；未声明时返回空串，基础文案保持不变。"""
    value = rules.get("bleeding_threshold_cny")
    if value is None:
        return ""
    if html:
        return f'；失血线 &lt;= {value / 1e8:,.2f} 亿元'
    return f"；失血线 `<= {value / 1e8:,.2f}亿元`"


def markdown_health_check(health: dict[str, Any]) -> list[str]:
    lines = [
        "",
        f"阈值体检：{health['evaluated_count']} 项可判定，其中 {health['passed_count']} 项成立。"
        "以下只做逐条阈值枚举，不聚合成分数，也不构成入场或仓位指令。",
        "",
        "| 条件 | 观察值 | 关系 | 阈值 | 结果 |",
        "|---|---:|---|---:|---|",
    ]
    for check in health["checks"]:
        lines.append(
            f"| {check['code']} | {fmt_level(check['observed'], check['unit'])} "
            f"| `{check['operator']}` | {fmt_level(check['threshold'], check['unit'])} "
            f"| {HEALTH_STATUS[check['status']][1]} |"
        )
    if health["unresolved"]:
        lines.extend(["", f"缺观察值、未纳入判定：{'、'.join(health['unresolved'])}。"])
    return lines


def markdown_prev_pool(
    prev_pool: dict[str, Any] | None, section: dict[str, Any], market_date: str
) -> list[str]:
    lines: list[str] = []
    if not prev_pool:
        return [unknown_line(section), ""]
    lines.append(
        f"- 对比区间：{prev_pool['previous_market_date']} 涨停池 → {market_date} 收盘；"
        f"股票池：{prev_pool['universe_id']}（与市场宽度同池）。"
    )
    lines.append(
        f"- 池内只数：{prev_pool['pool_size']:.0f}；当日再涨停：{prev_pool['promotion_count']:.0f}。"
    )
    rate = prev_pool["promotion_rate_pct"]
    if rate is not None:
        if prev_pool["health"] is None:
            lines.append(
                f"- 晋级率：{rate:.2f}%（未声明健康线阈值，不作高于或低于的判断）。"
            )
        else:
            verdict = "达到" if prev_pool["health"] == "at_or_above_line" else "低于"
            lines.append(
                f"- 晋级率：{rate:.2f}%，{verdict}声明的健康线 "
                f"{prev_pool['health_threshold_pct']:g}%。"
            )
    if prev_pool["avg_change_pct"] is not None:
        lines.append(f"- 池内平均涨跌幅：{fmt_signed_pct(prev_pool['avg_change_pct'])}")
    if prev_pool["median_change_pct"] is not None:
        lines.append(
            f"- 池内涨跌幅中位数：{fmt_signed_pct(prev_pool['median_change_pct'])}"
        )
    if prev_pool["groups"]:
        lines.extend(["", "| 昨日分组 | 只数 | 当日均涨跌 |", "|---|---:|---:|"])
        for group in prev_pool["groups"]:
            lines.append(
                f"| {group['name']} | {group['count']:.0f} "
                f"| {fmt_signed_pct(group['avg_change_pct'])} |"
            )
    lines.append("")
    return lines


def markdown_mainline(
    mainline: dict[str, Any] | None, section: dict[str, Any]
) -> list[str]:
    if not mainline:
        return [unknown_line(section), ""]
    rules = mainline["quadrant_rules"]
    counts = mainline["quadrant_counts"]
    names = active_quadrants(mainline)
    lines = [
        f"- 分类体系：{public_classification(mainline, '统一行业分类（详细映射保留在审计快照）')}；主题按声明成分归组。",
        f"- 象限规则（由输入显式声明，非隐藏默认）：涨停家数 `>= {rules['limit_up_threshold']}`；"
        f"板块资金净流入 `> {rules['capital_threshold_cny'] / 1e8:,.2f}亿元`"
        f"{bleeding_clause(rules, html=False)}。",
        f"- 象限分布：{quadrant_distribution(counts, names)}。",
        "",
        "| 主题 | 涨停家数 | 主题涨停股资金 | 板块资金（声明板块求和） | 板块涨跌（等权） | 象限 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for theme in sorted(
        mainline["themes"], key=lambda item: (-item["limit_up_count"], item["id"])
    ):
        lines.append(
            f"| {theme['name']} | {theme['limit_up_count']:.0f} "
            f"| {fmt_flow_cny(theme['limit_up_fund_flow_cny'])} "
            f"| {fmt_flow_cny(theme['board_fund_flow_cny'])} "
            f"| {fmt_signed_pct(theme['board_change_pct_equal_weight'])} "
            f"| {theme['quadrant']} |"
        )
    lines.extend(
        [
            "",
            "读法：右上＝双确认（情绪与资金同向）；左上＝资金先行（资金面先于情绪面）；"
            "右下＝情绪脉冲（家数达标但资金未跟）；左下＝失血。"
            + (
                "声明失血线后，右下再拆一档：家数达标但大额净流出判为情绪失血。"
                if rules.get("bleeding_threshold_cny") is not None
                else ""
            ),
            "",
            "> 象限是二维结构分类，不是评分，也不构成入场信号或仓位指令。",
            "",
        ]
    )
    return lines


def html_health_check(health: dict[str, Any]) -> str:
    rows = "".join(
        f'<tr><td>{html_text(check["code"])}</td>'
        f'<td class="num">{html_text(fmt_level(check["observed"], check["unit"]))}</td>'
        f'<td class="src">{html_text(check["operator"])} '
        f'{html_text(fmt_level(check["threshold"], check["unit"]))}</td>'
        f'<td><span class="dot {HEALTH_STATUS[check["status"]][0]}"></span>'
        f'{HEALTH_STATUS[check["status"]][1]}</td></tr>'
        for check in health["checks"]
    )
    unresolved = (
        f' 缺观察值、未纳入判定：{html_text("、".join(health["unresolved"]))}。'
        if health["unresolved"]
        else ""
    )
    return (
        '<div class="panel-head"><h3>阈值体检</h3>'
        f'<span>{health["passed_count"]} / {health["evaluated_count"]} 项成立</span></div>'
        '<div class="table-wrap"><table class="tbl"><thead><tr><th>条件</th>'
        '<th>观察值</th><th>关系</th><th>结果</th></tr></thead>'
        f'<tbody>{rows}</tbody></table></div>'
        f'<p class="section-note">{html_text(health["note"])}{unresolved}</p>'
    )


def html_prev_pool(
    prev_pool: dict[str, Any] | None, section: dict[str, Any], market_date: str
) -> str:
    if not prev_pool:
        return f'<p class="empty">{html_text(public_status_reason(section))}</p>'
    promotion = (
        f'{prev_pool["promotion_rate_pct"]:.2f}%'
        if prev_pool["promotion_rate_pct"] is not None
        else "unknown"
    )
    health_note = "未声明健康线阈值"
    if prev_pool["health"] == "at_or_above_line":
        health_note = f'达到健康线 {prev_pool["health_threshold_pct"]:g}%'
    elif prev_pool["health"] == "below_line":
        health_note = f'低于健康线 {prev_pool["health_threshold_pct"]:g}%'
    group_rows = "".join(
        f'<tr><td>{html_text(group["name"])}</td>'
        f'<td class="num">{group["count"]:.0f}</td>'
        f'<td class="num {value_tone(group["avg_change_pct"])}">'
        f'{html_text(fmt_signed_pct(group["avg_change_pct"]))}</td></tr>'
        for group in prev_pool["groups"]
    )
    groups_block = (
        '<div class="table-wrap"><table class="tbl"><thead><tr><th>昨日分组</th>'
        f'<th>只数</th><th>当日均涨跌</th></tr></thead><tbody>{group_rows}</tbody></table></div>'
        if group_rows
        else ""
    )
    return (
        '<dl class="kv">'
        f'<dt>对比区间</dt><dd>{html_text(prev_pool["previous_market_date"])} 涨停池 → '
        f'{html_text(market_date)} 收盘</dd>'
        f'<dt>股票池</dt><dd>{html_text(prev_pool["universe_id"])}（与市场宽度同池）</dd>'
        f'<dt>池内只数</dt><dd>{prev_pool["pool_size"]:.0f}</dd>'
        f'<dt>当日再涨停</dt><dd>{prev_pool["promotion_count"]:.0f}</dd>'
        f'<dt>晋级率</dt><dd>{html_text(promotion)} · {html_text(health_note)}</dd>'
        f'<dt>池内平均涨跌</dt><dd class="{value_tone(prev_pool["avg_change_pct"])}">'
        f'{html_text(fmt_signed_pct(prev_pool["avg_change_pct"]))}</dd>'
        f'<dt>涨跌幅中位数</dt><dd class="{value_tone(prev_pool["median_change_pct"])}">'
        f'{html_text(fmt_signed_pct(prev_pool["median_change_pct"]))}</dd>'
        "</dl>" + groups_block
    )


def html_mainline(
    mainline: dict[str, Any] | None, section: dict[str, Any]
) -> str:
    if not mainline:
        return f'<p class="empty">{html_text(public_status_reason(section))}</p>'
    rules = mainline["quadrant_rules"]
    counts = mainline["quadrant_counts"]
    theme_rows = "".join(
        f'<tr><td>{html_text(theme["name"])}</td>'
        f'<td class="num">{theme["limit_up_count"]:.0f}</td>'
        f'<td class="num {value_tone(theme["limit_up_fund_flow_cny"])}">'
        f'{html_text(fmt_flow_cny(theme["limit_up_fund_flow_cny"]))}</td>'
        f'<td class="num {value_tone(theme["board_fund_flow_cny"])}">'
        f'{html_text(fmt_flow_cny(theme["board_fund_flow_cny"]))}</td>'
        f'<td class="num {value_tone(theme["board_change_pct_equal_weight"])}">'
        f'{html_text(fmt_signed_pct(theme["board_change_pct_equal_weight"]))}</td>'
        f'<td>{html_text(QUADRANT_LABELS[theme["quadrant"]])}</td></tr>'
        for theme in sorted(
            mainline["themes"], key=lambda item: (-item["limit_up_count"], item["id"])
        )
    )
    legend = "".join(
        f'<span><span class="dot {QUADRANT_DOT[name]}"></span>{label} {counts[name]}</span>'
        for name, label in (
            (name, QUADRANT_LABELS[name]) for name in active_quadrants(mainline)
        )
    )
    return (
        f'<p class="section-note">分类体系：{html_text(public_classification(mainline, "统一行业分类（详细映射保留在审计快照）"))}；'
        '主题按声明成分归组。'
        f'象限规则由输入显式声明：涨停家数 &gt;= {rules["limit_up_threshold"]}；'
        f'板块资金净流入 &gt; {rules["capital_threshold_cny"] / 1e8:,.2f} 亿元'
        f'{bleeding_clause(rules, html=True)}。</p>'
        '<div class="table-wrap"><table class="tbl"><thead><tr><th>主题</th><th>涨停</th>'
        '<th>主题涨停股资金</th><th>板块资金</th><th>板块涨跌(等权)</th><th>象限</th>'
        f'</tr></thead><tbody>{theme_rows}</tbody></table></div>'
        f'<div class="matrix-legend">{legend}</div>'
        '<p class="note">象限是「游资情绪面 × 机构资金面」的二维结构分类，不是评分，'
        "也不构成入场信号或仓位指令。板块涨跌在多个声明板块之间取等权均值。</p>"
    )


STOCK_VIEW_NOTE = "只列输入显式声明的个股，用于板块与情绪的结构归因，不构成个股推荐。"


def _tier_label(streak: int) -> str:
    return "首板" if streak == 1 else f"{streak} 板"


def _ladder_summary(ladder: dict[str, Any]) -> str:
    parts = [f"合计 {ladder['total']:,} 只"]
    if ladder["first_board_count"] is not None:
        parts.append(
            f"首板 {ladder['first_board_count']:,}"
            f"（占 {ladder['first_board_share_pct']:.2f}%）"
        )
        parts.append(f"连板 {ladder['continued_count']:,}")
    parts.append(
        f"最高板 {ladder['highest_streak']} 板共 {ladder['highest_streak_count']:,} 只"
    )
    return "；".join(parts) + "。"


def markdown_streak_distribution(ladder: dict[str, Any]) -> list[str]:
    lines = ["", "连板梯队（各档家数之和等于市场宽度的涨停家数）：", "", "| 板数 | 家数 |", "|---|---:|"]
    for tier in ladder["tiers"]:
        lines.append(f"| {_tier_label(tier['streak'])} | {tier['count']:,} |")
    lines.extend(["", f"- {_ladder_summary(ladder)}"])
    return lines


def html_streak_distribution(ladder: dict[str, Any]) -> str:
    maximum = max((tier["count"] for tier in ladder["tiers"]), default=0) or 1
    rows = "".join(
        f'<div class="sector-row"><span>{html_text(_tier_label(tier["streak"]))}</span>'
        f'<div class="bar-track positive"><i style="width:{tier["count"] / maximum * 100:.2f}%"></i></div>'
        f'<b class="num">{tier["count"]:,}</b></div>'
        for tier in ladder["tiers"]
    )
    return (
        '<p class="sector-divider">连板梯队</p>'
        + rows
        + f'<p class="section-note">{html_text(_ladder_summary(ladder))}</p>'
    )


def _security_columns(
    rows: list[dict[str, Any]], streak_header: str | None = None
) -> list[tuple[str, str, str]]:
    """只保留至少一行有值的列。

    整列 unknown 会淹没报告，也会让人误以为「这里本该有数」。缺失列直接不出现，
    这与「不用 0 补缺」是同一条纪律：没有证据就留白，而不是留一个空壳。
    """
    columns: list[tuple[str, str, str]] = []
    if streak_header and any(row.get("streak") is not None for row in rows):
        columns.append(("streak", streak_header, "int"))
    for key, label, kind in (
        ("change_pct", "涨跌幅", "pct"),
        ("fund_flow_cny", "今日主力", "flow"),
        ("turnover_pct", "换手", "level_pct"),
    ):
        if any(row.get(key) is not None for row in rows):
            columns.append((key, label, kind))
    return columns


def _security_cell(kind: str, value: Any) -> str:
    if value is None:
        return "—"
    if kind == "int":
        return f"{value:,}"
    if kind == "pct":
        return fmt_signed_pct(value)
    if kind == "flow":
        return fmt_flow_cny(value)
    return fmt_level(value, "percent")


def _security_tone(kind: str, value: Any) -> str:
    return "" if kind == "int" else value_tone(value)


def _security_note(row: dict[str, Any]) -> str:
    return row.get("note") or "—"


def _security_html_row(row: dict[str, Any], columns: list[tuple[str, str, str]]) -> str:
    return (
        "<tr><td>"
        + html_text(row["name"])
        + (f'<span class="src"> {html_text(row["code"])}</span>' if row["code"] else "")
        + "</td>"
        + "".join(
            f'<td class="num {_security_tone(kind, row[key])}">'
            f"{html_text(_security_cell(kind, row[key]))}</td>"
            for key, _, kind in columns
        )
        + f'<td>{html_text(_security_note(row))}</td></tr>'
    )


def _security_head(columns: list[tuple[str, str, str]]) -> str:
    return (
        "<th>个股</th>"
        + "".join(f"<th>{html_text(label)}</th>" for _, label, _ in columns)
        + "<th>说明</th>"
    )


def markdown_high_boards(quality: dict[str, Any]) -> list[str]:
    rows = quality["boards"]
    columns = _security_columns(rows, streak_header="连板")
    lines = [
        "",
        f"最高板质量（{quality['count']} 只；其中声明资金流的 {quality['declared_fund_flow_count']} 只："
        f"净流入为正 {quality['inflow_count']}、为负 {quality['outflow_count']}"
        + (f"、为零 {quality['flat_count']}" if quality["flat_count"] else "")
        + "）：",
        "",
        "| 个股 | " + " | ".join(label for _, label, _ in columns) + " | 说明 |",
        "|---|" + "".join("---:|" for _ in columns) + "---|",
    ]
    for row in rows:
        cells = " | ".join(_security_cell(kind, row[key]) for key, _, kind in columns)
        lines.append(f"| {row['name']} | {cells} | {_security_note(row)} |")
    lines.extend(["", f"> {STOCK_VIEW_NOTE}"])
    return lines


def html_high_boards(quality: dict[str, Any]) -> str:
    rows = quality["boards"]
    columns = _security_columns(rows, streak_header="连板")
    body = "".join(_security_html_row(row, columns) for row in rows)
    return (
        '<p class="sector-divider">最高板质量</p>'
        '<div class="table-wrap"><table class="tbl"><thead><tr>'
        f"{_security_head(columns)}</tr></thead><tbody>{body}</tbody></table></div>"
        f'<p class="section-note">{html_text(STOCK_VIEW_NOTE)}'
        f"共 {quality['count']} 只；净流入为正 {quality['inflow_count']}、为负 {quality['outflow_count']}。"
        "</p>"
    )


def _concept_columns(items: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    columns: list[tuple[str, str, str]] = []
    if any(item.get("change_pct") is not None for item in items):
        columns.append(("change_pct", "涨跌幅", "pct"))
    columns.append(("fund_flow_cny", "主力净流入", "flow"))
    return columns


def _concept_md_table(
    items: list[dict[str, Any]],
    columns: list[tuple[str, str, str]],
    title: str,
) -> list[str]:
    lines = [
        f"{title}：",
        "",
        "| 概念/风格项 | " + " | ".join(label for _, label, _ in columns) + " |",
        "|---|" + "".join("---:|" for _ in columns),
    ]
    if items:
        for item in items:
            lines.append(
                f"| {item['name']} | "
                + " | ".join(_security_cell(kind, item[key]) for key, _, kind in columns)
                + " |"
            )
    else:
        lines.append("| — | " + " | ".join("—" for _ in columns) + " |")
    return lines


def markdown_concept_flows(concept: dict[str, Any]) -> list[str]:
    columns = _concept_columns(concept["items"])
    lines = [
        "",
        f"概念层（{public_classification(concept, '独立概念/风格分类')}，独立成表）。",
        "",
    ]
    lines.extend(
        _concept_md_table(concept["inflows"], columns, "净流入居前（概念/风格项口径）")
    )
    lines.append("")
    lines.extend(_concept_md_table(concept["outflows"], columns, "净流出居前"))
    return lines


def html_concept_flows(concept: dict[str, Any]) -> str:
    columns = _concept_columns(concept["items"])

    def table(items: list[dict[str, Any]], limit: int | None, title: str) -> str:
        selected = items if limit is None else items[:limit]
        body = "".join(
            "<tr><td>"
            + html_text(item["name"])
            + "</td>"
            + "".join(
                f'<td class="num {_security_tone(kind, item[key])}">'
                f"{html_text(_security_cell(kind, item[key]))}</td>"
                for key, _, kind in columns
            )
            + "</tr>"
            for item in selected
        ) or f'<tr><td colspan="{len(columns) + 1}">无</td></tr>'
        return (
            '<div class="table-wrap" style="margin-top:10px"><table class="tbl"><thead><tr>'
            f"<th>{html_text(title)}</th>"
            + "".join(f"<th>{html_text(label)}</th>" for _, label, _ in columns)
            + f"</tr></thead><tbody>{body}</tbody></table></div>"
        )

    featured = table(concept["inflows"], 10, "净流入居前") + table(
        concept["outflows"], 10, "净流出居前"
    )
    full = ""
    if len(concept["items"]) > 20:
        full = (
            '<details class="full-list"><summary>展开全部概念层资金流</summary>'
            + table(concept["inflows"], None, "净流入")
            + table(concept["outflows"], None, "净流出")
            + "</details>"
        )
    return (
        '<p class="sector-divider">概念层资金流</p>'
        f'<p class="section-note">{html_text(public_classification(concept, "独立概念/风格分类"))}</p>'
        + featured
        + full
    )


def markdown_sector_leaders(boards: list[dict[str, Any]]) -> list[str]:
    lines = ["", "板块内重点个股（板块归因下钻，非选股输出）：", ""]
    for board in boards:
        columns = _security_columns(board["leaders"], streak_header="连板")
        lines.extend(
            [
                f"**{board['name']}**",
                "",
                "| 个股 | " + " | ".join(label for _, label, _ in columns) + " | 说明 |",
                "|---|" + "".join("---:|" for _ in columns) + "---|",
            ]
        )
        for row in board["leaders"]:
            cells = " | ".join(_security_cell(kind, row[key]) for key, _, kind in columns)
            lines.append(f"| {row['name']} | {cells} | {_security_note(row)} |")
        lines.append("")
    lines.append(f"> {STOCK_VIEW_NOTE}")
    return lines


def html_sector_leaders(boards: list[dict[str, Any]]) -> str:
    blocks = []
    for board in boards:
        columns = _security_columns(board["leaders"], streak_header="连板")
        body = "".join(_security_html_row(row, columns) for row in board["leaders"])
        blocks.append(
            f'<details class="full-list"><summary>{html_text(board["name"])} · '
            f'{len(board["leaders"])} 只</summary>'
            '<div class="table-wrap"><table class="tbl"><thead><tr>'
            f"{_security_head(columns)}</tr></thead><tbody>{body}</tbody></table></div></details>"
        )
    return (
        '<p class="sector-divider">板块内重点个股</p>' + "".join(blocks)
        + f'<p class="section-note">{html_text(STOCK_VIEW_NOTE)}</p>'
    )
