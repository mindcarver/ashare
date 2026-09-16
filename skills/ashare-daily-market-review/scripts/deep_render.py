#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.4 深度分析层的 Markdown/HTML 片段。"""

from typing import Any

from formatting import fmt_flow_cny, fmt_level, fmt_signed_pct, html_text, value_tone


STATUS_LABELS = {"passed": "成立", "failed": "未成立", "unknown": "缺观察值"}


def _flow(value: float | None) -> str:
    return fmt_flow_cny(value) if value is not None else "unknown"


def _pct(value: float | None) -> str:
    return fmt_signed_pct(value) if value is not None else "unknown"


def _time(value: str | None) -> str:
    if not value:
        return "unknown"
    return value.split("T")[-1].split("+")[0]


def _yes_no_unknown(value: bool | None) -> str:
    if value is None:
        return "未知"
    return "是" if value else "否"


def markdown_security(component: dict[str, Any]) -> list[str]:
    if component["availability"] == "unknown":
        return [f"> UNKNOWN：{component['status_reason']}", ""]
    lines = [
        "### 个股证据纵深",
        "",
        "| 个股 | 身份 | 连板 | 涨跌 | 首封 / 末封 | 封单 | 炸板 | 1日 / 3日 / 5日 / 10日资金 |",
        "|---|---|---:|---:|---|---:|---:|---|",
    ]
    for item in component["items"]:
        seal = item.get("seal_structure") or {}
        first = _time(seal.get("first_sealed_at"))
        last = _time(seal.get("last_sealed_at"))
        windows = item["fund_flow_windows_cny"]
        flows = " / ".join(_flow(windows.get(days)) for days in (1, 3, 5, 10))
        lines.append(
            f"| {item['name']}（{item['code']}） | {'、'.join(item['roles'])} | "
            f"{item['streak'] if item['streak'] is not None else '—'} | {_pct(item['change_pct'])} | "
            f"{first} / {last} | {_flow(seal.get('sealed_order_amount_cny'))} | "
            f"{fmt_level(seal.get('break_count'), 'count')} | {flows} |"
        )
    lines.extend(
        [
            "",
            "> 多周期资金按1/3/5/10个交易日显式窗口展示；供应商模型只作交易结构归因，不等同真实账户资金。",
            "",
        ]
    )
    return lines


def markdown_liquidity(component: dict[str, Any]) -> list[str]:
    if component["availability"] == "unknown":
        return [f"> UNKNOWN：{component['status_reason']}", ""]
    lines = [
        "### 量能、价格位置与历史分位",
        "",
        f"- 逐条条件结果：{component['passed_count']} / {component['evaluated_count']} 项成立；状态：`{component['result']}`。",
        f"- {component['note']}。",
        "",
        "| 基准 | 涨跌 | 量比(5日) | 距MA20 | 距MA60 | 收益120日分位 | 成交120日分位 | 连续放量日 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in component["benchmarks"]:
        lines.append(
            f"| {item['name']} | {_pct(item['change_pct'])} | "
            f"{fmt_level(item['volume_ratio_5d'], 'ratio')} | {_pct(item['ma20_distance_pct'])} | "
            f"{_pct(item['ma60_distance_pct'])} | {_pct(item['return_percentile_120d'])} | "
            f"{_pct(item['volume_percentile_120d'])} | {fmt_level(item['consecutive_volume_days'], 'count')} |"
        )
    checks = [check for item in component["benchmarks"] for check in item["checks"]]
    checks.extend(component["market_checks"])
    if checks:
        lines.extend(["", "| 条件 | 观察值 | 关系 | 阈值 | 结果 |", "|---|---:|---|---:|---|"])
        for check in checks:
            lines.append(
                f"| {check['code']} | {fmt_level(check['observed'], check['unit'])} | "
                f"`{check['operator']}` | {fmt_level(check['threshold'], check['unit'])} | "
                f"{STATUS_LABELS[check['status']]} |"
            )
    lines.append("")
    return lines


def markdown_cycle(component: dict[str, Any]) -> list[str]:
    if component["availability"] == "unknown":
        return [f"> UNKNOWN：{component['status_reason']}", ""]
    lines = [
        "### 情绪周期（公开规则序列）",
        "",
        f"- 当前：`{component['current_state']}`；涨停较前值 {fmt_level(component['limit_up_change'], 'count')}；"
        f"跌停较前值 {fmt_level(component['limit_down_change'], 'count')}；窗口新低："
        f"{_yes_no_unknown(component['new_window_low_limit_up'])}。",
        f"- {component['note']}。",
        "",
        "| 日期 | 状态 | 涨停 | 跌停 | 封板率 | 晋级率 | 规则 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for item in component["points"]:
        lines.append(
            f"| {item['market_date']} | {item['state']} | {fmt_level(item['limit_up'], 'count')} | "
            f"{fmt_level(item['limit_down'], 'count')} | {_pct(item['seal_rate_pct'])} | "
            f"{_pct(item['promotion_rate_pct'])} | `{item['state_rule']}` |"
        )
    lines.append("")
    return lines


def markdown_capital(component: dict[str, Any]) -> list[str]:
    if component["availability"] == "unknown":
        return [f"> UNKNOWN：{component['status_reason']}", ""]
    lines = [
        "### 资金流入/流出共现与伪板块检查",
        "",
        f"- {component['note']}。",
        f"- 方法：{component['methodology']}",
        f"- 板块引用重叠率：{component['board_overlap_rate_pct']:.2f}%；成分股跨组重叠率：{component['security_overlap_rate_pct']:.2f}%。",
        "",
        "| 组 | 角色 | 涨跌 | 资金 | Top1正流入占比 | 绝对流量HHI | 反向个股数 | 伪板块 |",
        "|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for item in component["groups"]:
        top1 = item["top1_positive_share_pct"]
        lines.append(
            f"| {item['name']} | {item['role']} | {_pct(item['change_pct'])} | "
            f"{_flow(item['total_fund_flow_cny'])} | {_pct(top1)} | "
            f"{item['absolute_hhi'] if item['absolute_hhi'] is not None else 'unknown'} | "
            f"{fmt_level(item['opposite_direction_count'], 'count')} | {item['pseudo_sector_status']} |"
        )
    if component["overlaps"]:
        lines.extend(["", "重叠警告："])
        for item in component["overlaps"]:
            lines.append(
                f"- `{item['left_group_id']}` 与 `{item['right_group_id']}` 共享板块："
                + "、".join(item["shared_board_ids"])
            )
    if component["relations"]:
        lines.extend(["", "共现候选关系："])
        for item in component["relations"]:
            lines.append(
                f"- `{item['from_group_id']}` → `{item['to_group_id']}`：{item['hypothesis']}；"
                f"反方证据：{'；'.join(item['counter_evidence'])}。"
            )
    lines.append("")
    return lines


def markdown_catalysts(component: dict[str, Any]) -> list[str]:
    if component["availability"] == "unknown":
        return [f"> UNKNOWN：{component['status_reason']}", ""]
    lines = ["### 产业催化证据链", ""]
    for item in component["items"]:
        lines.extend(
            [
                f"#### {item['title']}",
                "",
                f"- 已观察事实：{item['fact']}",
                f"- 机制假设（`{item['causal_status']}`）：{item['mechanism_hypothesis']}",
                f"- 关联主题：{'、'.join(item['affected_theme_ids'])}",
                f"- 反方证据：{'；'.join(item['counter_evidence'])}",
                f"- 后续验证：{'、'.join(item['verification_point_ids'])}",
                f"- 来源：{item['source']['name']}；发布：{item['published_at']}",
                "",
            ]
        )
    return lines


def markdown_lhb(component: dict[str, Any]) -> list[str]:
    if component["availability"] == "unknown":
        return [f"> UNKNOWN：{component['status_reason']}", ""]
    lines = [
        "### 龙虎榜结构（只报披露事实）",
        "",
        f"- 观察日：{component['observed_at']}；发布日期：{component['published_at']}；{component['note']}。",
        f"- 方法：{component['methodology']}",
        "",
        "| 个股 | 买入 | 卖出 | 净额 | 买/卖席位数 | 买一占比 | 卖一占比 | 席位类型 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in component["items"]:
        lines.append(
            f"| {item['name']}（{item['code']}） | {_flow(item['buy_amount_cny'])} | "
            f"{_flow(item['sell_amount_cny'])} | {_flow(item['net_amount_cny'])} | "
            f"{item['buyer_count'] if item['buyer_count'] is not None else 'unknown'}/{item['seller_count'] if item['seller_count'] is not None else 'unknown'} | {_pct(item['top_buyer_share_pct'])} | "
            f"{_pct(item['top_seller_share_pct'])} | {'、'.join(item['seat_types']) or '未分类'} |"
        )
    lines.append("")
    return lines


MARKDOWN_RENDERERS = {
    "security_details": markdown_security,
    "liquidity_regime": markdown_liquidity,
    "sentiment_cycle": markdown_cycle,
    "capital_co_movement": markdown_capital,
    "catalyst_chains": markdown_catalysts,
    "lhb_structure": markdown_lhb,
}


def markdown_deep_analysis(deep: dict[str, Any] | None) -> list[str]:
    if not deep:
        return []
    lines = ["## 深度分析层（Schema 1.4）", "", "事实、规则派生、机制假设和反方证据分层展示。", ""]
    for name, renderer in MARKDOWN_RENDERERS.items():
        if name in deep:
            lines.extend(renderer(deep[name]))
    return lines


def _html_table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{html_text(value)}</th>" for value in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{value}</td>" for value in row) + "</tr>"
        for row in rows
    )
    return f'<div class="table-wrap"><table class="tbl"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def html_deep_analysis(deep: dict[str, Any] | None) -> str:
    if not deep:
        return ""
    panels = []
    security = deep.get("security_details")
    if security and security["availability"] != "unknown":
        rows = []
        for item in security["items"]:
            seal = item.get("seal_structure") or {}
            windows = item["fund_flow_windows_cny"]
            rows.append(
                [
                    html_text(item["name"]),
                    html_text("、".join(item["roles"])),
                    html_text(item["streak"] if item["streak"] is not None else "—"),
                    html_text(_pct(item["change_pct"])),
                    html_text(_time(seal.get("first_sealed_at"))),
                    html_text(_time(seal.get("last_sealed_at"))),
                    html_text(_flow(seal.get("sealed_order_amount_cny"))),
                    html_text(fmt_level(seal.get("break_count"), "count")),
                    html_text(" / ".join(_flow(windows.get(days)) for days in (1, 3, 5, 10))),
                ]
            )
        panels.append(
            '<article class="panel wide"><div class="panel-head"><h2>个股证据纵深</h2><span>1/3/5/10日</span></div>'
            + _html_table(
                ["个股", "身份", "连板", "涨跌", "首封", "末封", "封单", "炸板", "1/3/5/10日资金"],
                rows,
            )
            + '<p class="section-note">结构归因，不构成个股推荐。资金窗口显式标注，供应商模型不等同真实账户资金。</p></article>'
        )
    liquidity = deep.get("liquidity_regime")
    if liquidity and liquidity["availability"] != "unknown":
        rows = [
            [
                html_text(item["name"]),
                html_text(_pct(item["change_pct"])),
                html_text(fmt_level(item["volume_ratio_5d"], "ratio")),
                html_text(_pct(item["ma20_distance_pct"])),
                html_text(_pct(item["ma60_distance_pct"])),
                html_text(_pct(item["return_percentile_120d"])),
                html_text(_pct(item["volume_percentile_120d"])),
                html_text(fmt_level(item["consecutive_volume_days"], "count")),
            ]
            for item in liquidity["benchmarks"]
        ]
        checks = [check for item in liquidity["benchmarks"] for check in item["checks"]]
        checks.extend(liquidity["market_checks"])
        check_rows = [
            [
                html_text(item["code"]),
                html_text(fmt_level(item["observed"], item["unit"])),
                html_text(item["operator"]),
                html_text(fmt_level(item["threshold"], item["unit"])),
                html_text(STATUS_LABELS[item["status"]]),
            ]
            for item in checks
        ]
        panels.append(
            '<article class="panel wide"><div class="panel-head"><h2>量能与价格位置</h2>'
            f'<span>{liquidity["passed_count"]}/{liquidity["evaluated_count"]} 项成立</span></div>'
            + _html_table(
                ["基准", "涨跌", "量比", "距MA20", "距MA60", "收益120日分位", "量能120日分位", "连续放量日"],
                rows,
            )
            + (_html_table(["条件", "观察值", "关系", "阈值", "结果"], check_rows) if check_rows else "")
            + f'<p class="section-note">{html_text(liquidity["note"])} · {html_text(liquidity["result"])}</p></article>'
        )
    cycle = deep.get("sentiment_cycle")
    if cycle and cycle["availability"] != "unknown":
        rows = [
            [
                html_text(item["market_date"]),
                html_text(item["state"]),
                html_text(fmt_level(item["limit_up"], "count")),
                html_text(fmt_level(item["limit_down"], "count")),
                html_text(_pct(item["seal_rate_pct"])),
                html_text(_pct(item["promotion_rate_pct"])),
                html_text(item["state_rule"]),
            ]
            for item in cycle["points"]
        ]
        panels.append(
            '<article class="panel wide"><div class="panel-head"><h2>情绪周期</h2>'
            f'<span>{html_text(cycle["current_state"])} · 新低 {_yes_no_unknown(cycle["new_window_low_limit_up"])}</span></div>'
            + _html_table(["日期", "状态", "涨停", "跌停", "封板率", "晋级率", "公开规则"], rows)
            + f'<p class="section-note">{html_text(cycle["note"])}</p></article>'
        )
    capital = deep.get("capital_co_movement")
    if capital and capital["availability"] != "unknown":
        rows = [
            [
                html_text(item["name"]),
                html_text(item["role"]),
                html_text(_pct(item["change_pct"])),
                html_text(_flow(item["total_fund_flow_cny"])),
                html_text(_pct(item["top1_positive_share_pct"])),
                html_text(item["absolute_hhi"] if item["absolute_hhi"] is not None else "unknown"),
                html_text(fmt_level(item["opposite_direction_count"], "count")),
                html_text(item["pseudo_sector_status"]),
            ]
            for item in capital["groups"]
        ]
        relations = "".join(
            '<li><strong>' + html_text(item["from_group_id"] + " → " + item["to_group_id"]) + '</strong>'
            '<span>机制假设：' + html_text(item["hypothesis"]) + '</span>'
            '<small>反方证据：' + html_text("；".join(item["counter_evidence"])) + '</small></li>'
            for item in capital["relations"]
        )
        panels.append(
            '<article class="panel wide"><div class="panel-head"><h2>资金共现与集中度</h2><span>非因果迁移</span></div>'
            + _html_table(["组", "角色", "涨跌", "资金", "Top1占比", "HHI", "反向个股", "伪板块"], rows)
            + (f'<ul class="evidence-list">{relations}</ul>' if relations else "")
            + f'<p class="section-note">板块引用重叠率 {capital["board_overlap_rate_pct"]:.2f}% · 成分股跨组重叠率 {capital["security_overlap_rate_pct"]:.2f}% · {html_text(capital["note"])}</p></article>'
        )
    catalysts = deep.get("catalyst_chains")
    if catalysts and catalysts["availability"] != "unknown":
        items = "".join(
            '<li><strong>' + html_text(item["title"]) + '</strong>'
            '<span>事实：' + html_text(item["fact"]) + '</span>'
            '<span>机制假设（' + html_text(item["causal_status"]) + '）：' + html_text(item["mechanism_hypothesis"]) + '</span>'
            '<small>主题：' + html_text("、".join(item["affected_theme_ids"]))
            + ' · 验证：' + html_text("、".join(item["verification_point_ids"]))
            + ' · 反方证据：' + html_text("；".join(item["counter_evidence"]))
            + ' · 来源：' + html_text(item["source"]["name"]) + '（' + html_text(item["published_at"]) + '）</small></li>'
            for item in catalysts["items"]
        )
        panels.append(
            '<article class="panel wide"><div class="panel-head"><h2>产业催化证据链</h2><span>事实 / 假设 / 反证</span></div>'
            f'<ul class="evidence-list">{items}</ul></article>'
        )
    lhb = deep.get("lhb_structure")
    if lhb and lhb["availability"] != "unknown":
        rows = [
            [
                html_text(item["name"]),
                html_text(_flow(item["buy_amount_cny"])),
                html_text(_flow(item["sell_amount_cny"])),
                html_text(_flow(item["net_amount_cny"])),
                html_text(f'{item["buyer_count"] if item["buyer_count"] is not None else "unknown"}/{item["seller_count"] if item["seller_count"] is not None else "unknown"}'),
                html_text(_pct(item["top_buyer_share_pct"])),
                html_text(_pct(item["top_seller_share_pct"])),
                html_text("、".join(item["seat_types"]) or "未分类"),
            ]
            for item in lhb["items"]
        ]
        panels.append(
            '<article class="panel wide"><div class="panel-head"><h2>龙虎榜结构</h2>'
            f'<span>观察日 {html_text(lhb["observed_at"])}</span></div>'
            + _html_table(["个股", "买入", "卖出", "净额", "买/卖席位", "买一占比", "卖一占比", "席位类型"], rows)
            + f'<p class="section-note">{html_text(lhb["methodology"])} · {html_text(lhb["note"])}</p></article>'
        )
    unknown_labels = {
        "security_details": "个股证据纵深",
        "liquidity_regime": "量能与价格位置",
        "sentiment_cycle": "情绪周期",
        "capital_co_movement": "资金共现与集中度",
        "catalyst_chains": "产业催化证据链",
        "lhb_structure": "龙虎榜结构",
    }
    for name, label in unknown_labels.items():
        component = deep.get(name)
        if component and component["availability"] == "unknown":
            panels.append(
                '<article class="panel wide"><div class="panel-head"><h2>'
                + html_text(label)
                + '</h2><span>UNKNOWN</span></div><p class="empty-state">'
                + html_text(component["status_reason"])
                + "</p></article>"
            )
    if not panels:
        return ""
    return '<section id="deep-analysis" class="dashboard-grid" aria-label="深度分析层">' + "".join(panels) + "</section>"
