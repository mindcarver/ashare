#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Schema 1.4 深度分析层的 Markdown/HTML 片段。"""

from typing import Any

from formatting import (
    fmt_flow_cny,
    fmt_level,
    fmt_signed_pct,
    html_text,
    public_status_reason,
    translate_rule_text,
    value_tone,
)
from schema import (CAUSAL_STATUS_LABELS, CATALYST_SCOPE_LABELS, CATALYST_TYPE_LABELS,
    CAPITAL_ROLE_LABELS, LIQUIDITY_CHECK_LABELS, LIQUIDITY_RESULT_LABELS,
    PUBLIC_METRIC_LABELS, PSEUDO_STATUS_LABELS, SECURITY_ROLE_LABELS,
    SENTIMENT_STATE_LABELS)


STATUS_LABELS = {"passed": "成立", "failed": "未成立", "unknown": "缺观察值"}


def _flow(value: float | None) -> str:
    return fmt_flow_cny(value) if value is not None else "未知"


def _pct(value: float | None) -> str:
    return fmt_signed_pct(value) if value is not None else "未知"


def _time(value: str | None) -> str:
    if not value:
        return "未知"
    return value.split("T")[-1].split("+")[0]


def _yes_no_unknown(value: bool | None) -> str:
    if value is None:
        return "未知"
    return "是" if value else "否"


def _security_notes(component: dict[str, Any]) -> str:
    """个股证据纵深的公开口径说明：只用输入声明的公开文本，不回显采集渠道。"""
    parts = ["多周期资金按1/3/5/10个交易日显式窗口展示；供应商模型只作交易结构归因，不等同真实账户资金。"]
    tolerance = component.get("cross_check_tolerance_pct")
    if tolerance is not None:
        parts.append(f"1日窗口与基础章节同一交易日的当日资金口径交叉校验，容差 ±{tolerance:g}%。")
    caveat = component.get("public_caveat")
    if caveat:
        parts.append(caveat)
    return "".join(parts)


def markdown_security(component: dict[str, Any]) -> list[str]:
    if component["availability"] == "unknown":
        return [f"> 未知：{public_status_reason(component)}", ""]
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
            f"| {item['name']}（{item['code']}） | {'、'.join(SECURITY_ROLE_LABELS.get(r, r) for r in item['roles'])} | "
            f"{item['streak'] if item['streak'] is not None else '—'} | {_pct(item['change_pct'])} | "
            f"{first} / {last} | {_flow(seal.get('sealed_order_amount_cny'))} | "
            f"{fmt_level(seal.get('break_count'), 'count')} | {flows} |"
        )
    lines.extend(
        [
            "",
            f"> {_security_notes(component)}",
            "",
        ]
    )
    return lines


def _group_name(component: dict[str, Any], group_id: str) -> str:
    """共现关系展示用组名：资金组ID只在审计层存在，公开层一律用名称。"""
    for group in component.get("groups", []):
        if group["id"] == group_id:
            return group["name"]
    return group_id


def _check_label(code: str) -> str:
    return LIQUIDITY_CHECK_LABELS.get(code, code)


def _condition_label(check: dict[str, Any]) -> str:
    operator = {"<=": "≤", ">=": "≥"}.get(check["operator"], check["operator"])
    return f"{_check_label(check['code'])} {operator} {fmt_level(check['threshold'], check['unit'])}"


def _observed(check: dict[str, Any]) -> str:
    """条件观察值：百分比统一两位小数，与指标表的展示精度对齐。"""
    if check["unit"] == "percent" and check["observed"] is not None:
        return f"{check['observed']:.2f}%"
    return fmt_level(check["observed"], check["unit"])


def _benchmark_check_codes(benchmarks: list[dict[str, Any]]) -> list[str]:
    declared = {check["code"] for item in benchmarks for check in item["checks"]}
    ordered = [code for code in LIQUIDITY_CHECK_LABELS if code in declared]
    return ordered + sorted(declared - set(LIQUIDITY_CHECK_LABELS))


def _volume_ratio_word(ratio: float) -> str:
    if ratio < 0.9:
        return "量能明显低于5日均量"
    if ratio < 1.1:
        return "量能与5日均量基本持平"
    if ratio < 1.3:
        return "量能温和高于5日均量"
    return "量能明显高于5日均量"


def _ma_position(distance: float | None, line: str) -> str | None:
    if distance is None:
        return None
    side = "上方" if distance >= 0 else "下方"
    return f"{line}{side}{abs(distance):.2f}%"


def _percentile_position(pct: float | None, label: str) -> str | None:
    if pct is None:
        return None
    half = "上半区" if pct >= 50 else "下半区"
    return f"{label}处近120日区间{half}（分位{pct:.0f}%）"


def _liquidity_reading(item: dict[str, Any]) -> str:
    parts: list[str] = []
    change = item.get("change_pct")
    if change is not None:
        parts.append(f"当日{'收涨' if change >= 0 else '收跌'}{abs(change):.2f}%")
    ratio = item.get("volume_ratio_5d")
    if ratio is not None:
        parts.append(f"量比{ratio:.2f}，{_volume_ratio_word(ratio)}")
    days = item.get("consecutive_volume_days")
    if days is not None:
        parts.append(f"连续放量{days:.0f}日")
    trend = [
        text
        for text in (
            _ma_position(item.get("ma20_distance_pct"), "20日线"),
            _ma_position(item.get("ma60_distance_pct"), "60日线"),
        )
        if text
    ]
    if trend:
        parts.append("位于" + "、".join(trend))
    for text in (
        _percentile_position(item.get("return_percentile_120d"), "收益"),
        _percentile_position(item.get("volume_percentile_120d"), "成交"),
    ):
        if text:
            parts.append(text)
    if not parts:
        return ""
    return f"{item['name']}：" + "；".join(parts) + "。"


def _market_reading(checks: list[dict[str, Any]]) -> str:
    if not checks:
        return ""
    parts = []
    for check in checks:
        parts.append(f"{_check_label(check['code'])}观察值{_observed(check)}，{STATUS_LABELS[check['status']]}")
    return "全市场条件：" + "；".join(parts) + "。"


def markdown_liquidity(component: dict[str, Any]) -> list[str]:
    if component["availability"] == "unknown":
        return [f"> 未知：{public_status_reason(component)}", ""]
    lines = [
        "### 量能、价格位置与历史分位",
        "",
        f"- 逐条条件结果：{component['passed_count']} / {component['evaluated_count']} 项成立；状态：{LIQUIDITY_RESULT_LABELS.get(component['result'], component['result'])}。",
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
    codes = _benchmark_check_codes(component["benchmarks"])
    if codes:
        first_by_code = {
            check["code"]: check for item in component["benchmarks"] for check in item["checks"]
        }
        headers = [_condition_label(first_by_code[code]) for code in codes]
        lines.extend(
            [
                "",
                "条件矩阵（行=基准，列=输入声明的条件与阈值；✓=成立，✗=未成立，—=未声明）：",
                "",
                "| 基准 | " + " | ".join(headers) + " |",
                "|" + "|".join(["---"] + ["---:"] * len(codes)) + "|",
            ]
        )
        for item in component["benchmarks"]:
            by_code = {check["code"]: check for check in item["checks"]}
            cells = [item["name"]]
            for code in codes:
                check = by_code.get(code)
                if check is None:
                    cells.append("—")
                elif check["status"] == "unknown":
                    cells.append("缺观察值")
                else:
                    cells.append(f"{_observed(check)} {'✓' if check['status'] == 'passed' else '✗'}")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
    if component["market_checks"]:
        lines.extend(["", "全市场条件：", "", "| 条件（含阈值） | 观察值 | 结果 |", "|---|---:|---|"])
        for check in component["market_checks"]:
            lines.append(
                f"| {_condition_label(check)} | {_observed(check)} | "
                f"{STATUS_LABELS[check['status']]} |"
            )
        lines.append("")
    readings = [text for text in (_liquidity_reading(item) for item in component["benchmarks"]) if text]
    market = _market_reading(component["market_checks"])
    if readings or market:
        lines.extend(["逐基准解读（由上表当日数值直接归纳，不预测方向）：", ""])
        lines.extend(f"- {text}" for text in readings)
        if market:
            lines.append(f"- {market}")
    lines.append("")
    return lines


def markdown_cycle(component: dict[str, Any]) -> list[str]:
    if component["availability"] == "unknown":
        return [f"> 未知：{public_status_reason(component)}", ""]
    lines = [
        "### 情绪周期（公开规则序列）",
        "",
        f"- 当前：{SENTIMENT_STATE_LABELS.get(component['current_state'], component['current_state'])}；涨停较前值 {fmt_level(component['limit_up_change'], 'count')}；"
        f"跌停较前值 {fmt_level(component['limit_down_change'], 'count')}；窗口新低："
        f"{_yes_no_unknown(component['new_window_low_limit_up'])}。",
        f"- {component['note']}。",
        "",
        "| 日期 | 状态 | 涨停 | 跌停 | 封板率 | 晋级率 | 规则 |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for item in component["points"]:
        lines.append(
            f"| {item['market_date']} | {SENTIMENT_STATE_LABELS.get(item['state'], item['state'])} | {fmt_level(item['limit_up'], 'count')} | "
            f"{fmt_level(item['limit_down'], 'count')} | {_pct(item['seal_rate_pct'])} | "
            f"{_pct(item['promotion_rate_pct'])} | {translate_rule_text(item['state_rule'], PUBLIC_METRIC_LABELS, SENTIMENT_STATE_LABELS)} |"
        )
    lines.append("")
    return lines


def markdown_capital(component: dict[str, Any]) -> list[str]:
    if component["availability"] == "unknown":
        return [f"> 未知：{public_status_reason(component)}", ""]
    sample = component.get("concentration_scope", "complete") == "sample"
    # 集中度四列只在至少一组可计算时出现；整列缺证据不占版面（同「不用0补缺」纪律）。
    show_concentration = any(item["top1_positive_share_pct"] is not None for item in component["groups"])
    lines = [
        "### 资金流入/流出共现与伪板块检查",
        "",
        f"- {component['note']}。",
        f"- 板块引用重叠率：{component['board_overlap_rate_pct']:.2f}%；成分股跨组重叠率：{component['security_overlap_rate_pct']:.2f}%。",
    ]
    if sample:
        floor = component.get("thresholds", {}).get("min_sample_coverage_pct")
        lines.append(f"- 集中度口径：样本内，覆盖率下限 {_pct(floor)}，只在各组声明的覆盖率内成立。")
    if not show_concentration:
        coverage = "、".join(
            f"{item['name']}已覆盖{len(item.get('contributions', []))}只" for item in component["groups"]
        )
        lines.append(
            "- 贡献分解不完整：Top1占比、HHI、反向个股与伪板块列按契约不展示，不用样本冒充全成分"
            + (f"（{coverage}）。" if coverage else "。")
        )
    lines.append("")
    headers = ["组", "角色", "涨跌", "资金"]
    if sample:
        headers.append("样本覆盖率")
    if show_concentration:
        headers.extend(["Top1正流入占比", "绝对流量HHI", "反向个股数", "伪板块"])
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] + ["---:"] * (len(headers) - 1)) + "|")
    for item in component["groups"]:
        top1 = item["top1_positive_share_pct"]
        cells = [
            item["name"],
            CAPITAL_ROLE_LABELS.get(item["role"], item["role"]),
            _pct(item["change_pct"]),
            _flow(item["total_fund_flow_cny"]),
        ]
        if sample:
            cells.append(_pct(item.get("sample_coverage_pct")))
        if show_concentration:
            cells.extend(
                [
                    _pct(top1),
                    f"{item['absolute_hhi'] if item['absolute_hhi'] is not None else '未知'}",
                    fmt_level(item["opposite_direction_count"], "count"),
                    PSEUDO_STATUS_LABELS.get(item["pseudo_sector_status"], item["pseudo_sector_status"]),
                ]
            )
        lines.append("| " + " | ".join(cells) + " |")
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
                f"- {_group_name(component, item['from_group_id'])} → {_group_name(component, item['to_group_id'])}：{item['hypothesis']}；"
                f"反方证据：{'；'.join(item['counter_evidence'])}。"
            )
    lines.append("")
    return lines


def markdown_catalysts(component: dict[str, Any]) -> list[str]:
    if component["availability"] == "unknown":
        return [f"> 未知：{public_status_reason(component)}", ""]
    lines = ["### 产业催化证据链", ""]
    coverage = component.get("type_coverage")
    if coverage:
        breakdown = "、".join(
            f"{CATALYST_TYPE_LABELS.get(key, key)} {count}"
            for key, count in sorted(coverage.items(), key=lambda pair: (-pair[1], pair[0]))
        )
        lines.extend(
            [
                f"- 分类覆盖：{breakdown}；其中产业级 {component.get('industrial_catalyst_count', 0)} 条。",
                f"- {component.get('note', '')}",
                "",
            ]
        )
    for item in component["items"]:
        affected = "、".join(item.get("affected_theme_labels") or item["affected_theme_ids"])
        lines.extend(
            [
                f"#### {item['title']}",
                "",
                f"- 已观察事实：{item['fact']}",
                f"- 机制假设（{CAUSAL_STATUS_LABELS.get(item['causal_status'], item['causal_status'])}）：{item['mechanism_hypothesis']}",
            ]
        )
        if item.get("catalyst_type"):
            lines.append(f"- 催化类型：{CATALYST_TYPE_LABELS.get(item['catalyst_type'], item['catalyst_type'])}")
        if item.get("scope"):
            lines.append(f"- 作用域：{CATALYST_SCOPE_LABELS.get(item['scope'], item['scope'])}")
        if item.get("scope") == "macro_backdrop":
            lines.append("- 关联主题：无（宏观背景，不按主题归因）")
        else:
            lines.append(f"- 关联主题：{affected}")
        if item.get("transmission"):
            lines.append(f"- 传导路径：{item['transmission']}")
        lines.extend(
            [
                f"- 反方证据：{'；'.join(item['counter_evidence'])}",
                f"- 后续验证：已挂{len(item['verification_point_ids'])}个验证点（详见「事件与验证点」）",
                f"- 发布日：{item['published_at']}",
                "",
            ]
        )
    return lines


def markdown_lhb(component: dict[str, Any]) -> list[str]:
    if component["availability"] == "unknown":
        return [f"> 未知：{public_status_reason(component)}", ""]
    lines = [
        "### 龙虎榜结构（只报披露事实）",
        "",
        f"- 观察日：{component['observed_at']}；发布日期：{component['published_at']}；{component['note']}。",
        "",
        "| 个股 | 买入 | 卖出 | 净额 | 买/卖席位数 | 买一占比 | 卖一占比 | 席位类型 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in component["items"]:
        lines.append(
            f"| {item['name']}（{item['code']}） | {_flow(item['buy_amount_cny'])} | "
            f"{_flow(item['sell_amount_cny'])} | {_flow(item['net_amount_cny'])} | "
            f"{item['buyer_count'] if item['buyer_count'] is not None else '未知'}/{item['seller_count'] if item['seller_count'] is not None else '未知'} | {_pct(item['top_buyer_share_pct'])} | "
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
    lines = ["## 深度分析层", "", "事实、规则派生、机制假设和反方证据分层展示。", ""]
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
                    html_text("、".join(SECURITY_ROLE_LABELS.get(r, r) for r in item["roles"])),
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
            + f'<p class="section-note">{html_text(_security_notes(security))}</p></article>'
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
        matrix_html = ""
        codes = _benchmark_check_codes(liquidity["benchmarks"])
        if codes:
            first_by_code = {
                check["code"]: check for item in liquidity["benchmarks"] for check in item["checks"]
            }
            matrix_rows = []
            for item in liquidity["benchmarks"]:
                by_code = {check["code"]: check for check in item["checks"]}
                cells = [html_text(item["name"])]
                for code in codes:
                    check = by_code.get(code)
                    if check is None:
                        cells.append("—")
                    elif check["status"] == "unknown":
                        cells.append("缺观察值")
                    else:
                        mark = "✓" if check["status"] == "passed" else "✗"
                        cells.append(html_text(f"{_observed(check)} {mark}"))
                matrix_rows.append(cells)
            matrix_html = _html_table(
                ["基准"] + [_condition_label(first_by_code[code]) for code in codes],
                matrix_rows,
            )
        market_html = ""
        if liquidity["market_checks"]:
            market_rows = [
                [
                    html_text(_condition_label(check)),
                    html_text(_observed(check)),
                    html_text(STATUS_LABELS[check["status"]]),
                ]
                for check in liquidity["market_checks"]
            ]
            market_html = _html_table(["全市场条件（含阈值）", "观察值", "结果"], market_rows)
        readings = [
            html_text(text)
            for text in (_liquidity_reading(item) for item in liquidity["benchmarks"])
            if text
        ]
        market = _market_reading(liquidity["market_checks"])
        if market:
            readings.append(html_text(market))
        readings_html = (
            f'<ul class="evidence-list"><li><span>逐基准解读（由当日数值归纳，不预测方向）</span></li>'
            + "".join(f"<li><span>{text}</span></li>" for text in readings)
            + "</ul>"
            if readings
            else ""
        )
        panels.append(
            '<article class="panel wide"><div class="panel-head"><h2>量能与价格位置</h2>'
            f'<span>{liquidity["passed_count"]}/{liquidity["evaluated_count"]} 项成立</span></div>'
            + _html_table(
                ["基准", "涨跌", "量比", "距MA20", "距MA60", "收益120日分位", "量能120日分位", "连续放量日"],
                rows,
            )
            + matrix_html
            + market_html
            + readings_html
            + f'<p class="section-note">{html_text(liquidity["note"])} · {html_text(LIQUIDITY_RESULT_LABELS.get(liquidity["result"], liquidity["result"]))} · ✓=成立，✗=未成立</p></article>'
        )
    cycle = deep.get("sentiment_cycle")
    if cycle and cycle["availability"] != "unknown":
        rows = [
            [
                html_text(item["market_date"]),
                html_text(SENTIMENT_STATE_LABELS.get(item["state"], item["state"])),
                html_text(fmt_level(item["limit_up"], "count")),
                html_text(fmt_level(item["limit_down"], "count")),
                html_text(_pct(item["seal_rate_pct"])),
                html_text(_pct(item["promotion_rate_pct"])),
                html_text(translate_rule_text(item["state_rule"], PUBLIC_METRIC_LABELS, SENTIMENT_STATE_LABELS)),
            ]
            for item in cycle["points"]
        ]
        panels.append(
            '<article class="panel wide"><div class="panel-head"><h2>情绪周期</h2>'
            f'<span>{html_text(SENTIMENT_STATE_LABELS.get(cycle["current_state"], cycle["current_state"]))} · 新低 {_yes_no_unknown(cycle["new_window_low_limit_up"])}</span></div>'
            + _html_table(["日期", "状态", "涨停", "跌停", "封板率", "晋级率", "公开规则"], rows)
            + f'<p class="section-note">{html_text(cycle["note"])}</p></article>'
        )
    capital = deep.get("capital_co_movement")
    if capital and capital["availability"] != "unknown":
        sample = capital.get("concentration_scope", "complete") == "sample"
        show_concentration = any(item["top1_positive_share_pct"] is not None for item in capital["groups"])
        rows = []
        for item in capital["groups"]:
            row = [
                html_text(item["name"]),
                html_text(CAPITAL_ROLE_LABELS.get(item["role"], item["role"])),
                html_text(_pct(item["change_pct"])),
                html_text(_flow(item["total_fund_flow_cny"])),
            ]
            if sample:
                row.append(html_text(_pct(item.get("sample_coverage_pct"))))
            if show_concentration:
                row.extend(
                    [
                        html_text(_pct(item["top1_positive_share_pct"])),
                        html_text(item["absolute_hhi"] if item["absolute_hhi"] is not None else "未知"),
                        html_text(fmt_level(item["opposite_direction_count"], "count")),
                        html_text(PSEUDO_STATUS_LABELS.get(item["pseudo_sector_status"], item["pseudo_sector_status"])),
                    ]
                )
            rows.append(row)
        headers = ["组", "角色", "涨跌", "资金"]
        if sample:
            headers.append("样本覆盖率")
        if show_concentration:
            headers.extend(["Top1占比", "HHI", "反向个股", "伪板块"])
        incomplete_note = (
            '<p class="section-note">贡献分解不完整：Top1占比、HHI、反向个股与伪板块列按契约不展示，不用样本冒充全成分。</p>'
            if not show_concentration
            else ""
        )
        relations = "".join(
            '<li><strong>' + html_text(_group_name(capital, item["from_group_id"]) + " → " + _group_name(capital, item["to_group_id"])) + '</strong>'
            '<span>机制假设：' + html_text(item["hypothesis"]) + '</span>'
            '<small>反方证据：' + html_text("；".join(item["counter_evidence"])) + '</small></li>'
            for item in capital["relations"]
        )
        panels.append(
            '<article class="panel wide"><div class="panel-head"><h2>资金共现与集中度</h2><span>非因果迁移</span></div>'
            + _html_table(headers, rows)
            + incomplete_note
            + (f'<ul class="evidence-list">{relations}</ul>' if relations else "")
            + f'<p class="section-note">板块引用重叠率 {capital["board_overlap_rate_pct"]:.2f}% · 成分股跨组重叠率 {capital["security_overlap_rate_pct"]:.2f}% · {html_text(capital["note"])}</p></article>'
        )
    catalysts = deep.get("catalyst_chains")
    if catalysts and catalysts["availability"] != "unknown":
        entries = []
        for item in catalysts["items"]:
            meta = []
            if item.get("catalyst_type"):
                meta.append("类型：" + CATALYST_TYPE_LABELS.get(item["catalyst_type"], item["catalyst_type"]))
            if item.get("scope"):
                meta.append("作用域：" + CATALYST_SCOPE_LABELS.get(item["scope"], item["scope"]))
            if item.get("scope") == "macro_backdrop":
                meta.append("主题：无（宏观背景，不按主题归因）")
            else:
                meta.append("主题：" + "、".join(item.get("affected_theme_labels") or item["affected_theme_ids"]))
            if item.get("transmission"):
                meta.append("传导：" + item["transmission"])
            meta.append(f"验证：已挂{len(item['verification_point_ids'])}个验证点")
            meta.append("反方证据：" + "；".join(item["counter_evidence"]))
            meta.append("发布日：" + item["published_at"])
            entries.append(
                '<li><strong>' + html_text(item["title"]) + '</strong>'
                '<span>事实：' + html_text(item["fact"]) + '</span>'
                '<span>机制假设（' + html_text(CAUSAL_STATUS_LABELS.get(item["causal_status"], item["causal_status"])) + '）：' + html_text(item["mechanism_hypothesis"]) + '</span>'
                '<small>' + html_text(" · ".join(meta)) + '</small></li>'
            )
        items = "".join(entries)
        coverage = catalysts.get("type_coverage")
        coverage_note = ""
        if coverage:
            breakdown = "、".join(
                f"{CATALYST_TYPE_LABELS.get(key, key)} {count}"
                for key, count in sorted(coverage.items(), key=lambda pair: (-pair[1], pair[0]))
            )
            coverage_note = (
                '<p class="section-note">分类覆盖：'
                + html_text(breakdown)
                + f'；产业级 {catalysts.get("industrial_catalyst_count", 0)} 条 · '
                + html_text(catalysts.get("note", ""))
                + "</p>"
            )
        panels.append(
            '<article class="panel wide"><div class="panel-head"><h2>产业催化证据链</h2><span>事实 / 假设 / 反证</span></div>'
            f'<ul class="evidence-list">{items}</ul>{coverage_note}</article>'
        )
    lhb = deep.get("lhb_structure")
    if lhb and lhb["availability"] != "unknown":
        rows = [
            [
                html_text(item["name"]),
                html_text(_flow(item["buy_amount_cny"])),
                html_text(_flow(item["sell_amount_cny"])),
                html_text(_flow(item["net_amount_cny"])),
                html_text(f'{item["buyer_count"] if item["buyer_count"] is not None else "未知"}/{item["seller_count"] if item["seller_count"] is not None else "未知"}'),
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
            + f'<p class="section-note">{html_text(lhb["note"])}</p></article>'
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
                + '</h2><span>未声明</span></div><p class="empty-state">'
                + html_text(public_status_reason(component))
                + "</p></article>"
            )
    if not panels:
        return ""
    return '<section id="deep-analysis" class="dashboard-grid" aria-label="深度分析层">' + "".join(panels) + "</section>"
