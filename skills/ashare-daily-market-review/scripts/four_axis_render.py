#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纵 × 横 × 深 × 验四轴总览的Markdown/HTML片段。"""

from typing import Any

from formatting import fmt_flow_cny, html_text
from schema import ANALYSIS_MODE_LABELS, QUADRANT_ORDER, QUADRANT_SHORT_LABELS, SCOPE_LABELS


STATUS_LABELS = {
    "supported": "支持",
    "contradicted": "冲突",
    "unknown": "未知",
    "not_enabled": "未启用",
}

RESULT_LABELS = {
    "multi_axis_supported": "多轴支持",
    "regime_conflicted": "环境冲突",
    "horizontal_only": "仅横向成立",
    "not_horizontal_confirmed": "横向未确认",
    "insufficient": "证据不足",
}

# 主题表六列各回答什么问题（渲染层公开文本，与列头一一对应）。
AXIS_COLUMN_HEADERS = {
    "longitudinal": "时间轴",
    "horizontal": "截面",
    "liquidity": "量价",
    "concentration": "集中度",
    "catalyst": "催化链",
    "verification": "验证链",
}
AXIS_LEGEND = (
    "列含义：时间轴＝近几日情绪与晋级是否同向；截面＝当日主线矩阵象限是否双确认；"
    "量价＝指数量价条件是否全部成立；集中度＝主题相关资金组是否完整且无伪板块；"
    "催化链＝是否有催化证据挂到该主题；验证链＝该主题是否挂了未来验证点。"
    "时间轴与量价为全市场同一判定，主题间无差异，当日原因见上方「四轴状态」表。"
)
RESULT_LEGEND = (
    "结果读法：多轴支持＝六项全部支持；环境冲突＝截面达标但时间轴/量价/集中度任一反向；"
    "仅横向成立＝截面达标、其余轴缺证；横向未确认＝当日象限未达双确认；证据不足＝象限未知。"
)

_QUADRANT_SHORT = {
    "dual_confirmed": "双确认",
    "capital_led": "资金先行",
    "sentiment_only": "情绪脉冲",
    "sentiment_bleeding": "情绪失血",
    "bleeding": "失血",
    "unknown": "象限未知",
}


def _cell_reason(axis_key: str, check: dict[str, Any]) -> str:
    """主题表格子里的短原因：只做状态证据的压缩转述，不引入新判断。"""
    evidence = check.get("evidence", "")
    if axis_key == "horizontal":
        code = evidence.split("=", 1)[1] if "=" in evidence else ""
        return _QUADRANT_SHORT.get(code, evidence)
    if axis_key == "concentration":
        if "存在伪板块" in evidence:
            return "有伪板块"
        if evidence.startswith("相关完整资金组"):
            return "无伪板块"
        if "不完整" in evidence:
            return "贡献分解不完整"
        if "重叠" in evidence:
            return "无重叠资金组"
        return evidence or "未声明"
    if axis_key == "catalyst":
        digits = "".join(ch for ch in evidence if ch.isdigit())
        return f"{digits}条" if digits else evidence
    if axis_key == "verification":
        digits = "".join(ch for ch in evidence if ch.isdigit())
        if "主题自有" in evidence:
            return f"{digits}个＋自有" if digits and digits != "0" else "挂主题验证点"
        return f"{digits}个" if digits else evidence
    return ""  # 市场级轴（时间/量价）原因全表相同，不逐格重复


def _axis_evidence(axis: dict[str, Any]) -> str:
    checks = axis.get("checks", [])
    if checks:
        return "；".join(item["evidence"] for item in checks)
    return "该轴未启用或没有可得证据"



def _status_word(status: str) -> str:
    return {"supported": "支持", "contradicted": "反向", "unknown": "未知", "not_enabled": "未启用"}.get(
        status, status
    )


def _verdict_phrase(item: dict[str, Any]) -> str:
    """主线速览的读法：由结果码与象限确定性生成，描述结构、不预测方向。"""
    result = item["result"]
    if item.get('capital_scope_note'):
        return item['capital_scope_note'] + '；' + RESULT_LABELS[result]
    quadrant = item.get("quadrant")
    flow = item.get("board_fund_flow_cny")
    if result == "multi_axis_supported":
        return "六项证据同向，当日最强结构"
    if result == "regime_conflicted":
        return "当日达标，但生在大盘反向环境里（逆风主线）"
    if result == "horizontal_only":
        return "当日达标，其余证据未齐（待确认）"
    if result == "insufficient":
        return "象限证据不足，无法判定"
    if quadrant == "capital_led":
        return "资金在流入、涨停未成潮（资金先行）"
    if quadrant == "sentiment_only":
        return "涨停达标、资金未跟（情绪先行）"
    if quadrant == "sentiment_bleeding":
        return "涨停达标但资金大额流出（情绪失血）"
    if quadrant == "bleeding":
        if flow is not None and flow > 0:
            return "涨停与资金均未达确认线（资金为小幅净流入）"
        return "涨停与资金均未达确认线（资金净流出）"
    return "当日未达双确认"


def _sorted_digest_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def rank(item: dict[str, Any]) -> tuple:
        quadrant = item.get("quadrant") or "unknown"
        order = QUADRANT_ORDER.index(quadrant) if quadrant in QUADRANT_ORDER else len(QUADRANT_ORDER)
        count = item.get("limit_up_count") or 0
        return (order, -float(count), item["name"])

    return sorted(rows, key=rank)


def _market_context(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    checks = rows[0]["checks"]
    return (
        f"大盘环境（各主题共用同一判定）：时间轴{_status_word(checks['longitudinal']['status'])}、"
        f"量价{_status_word(checks['liquidity']['status'])}"
        "——这两项全市场一致，明细见上方「四轴状态」，下方主线表不再逐行重复。"
    )


def _digest_cells(item: dict[str, Any]) -> list[str]:
    count = item.get("limit_up_count")
    flow = item.get("board_fund_flow_cny")
    key_data = (
        f"涨停{count:.0f}家｜板块资金{fmt_flow_cny(flow)}" if count is not None and flow is not None else "数据未知"
    )
    catalyst = item.get("catalyst_count") or 0
    verification = item.get("verification_count") or 0
    own = item.get("has_own_verification") or False
    evidence = []
    if catalyst or verification or own:
        parts = []
        if catalyst:
            parts.append(f"催化{catalyst}条")
        if verification and own:
            parts.append(f"验证{verification}个＋自有")
        elif own:
            parts.append("挂主题验证点")
        elif verification:
            parts.append(f"验证{verification}个")
        evidence.append("｜".join(parts))
    else:
        evidence.append("无")
    return [
        QUADRANT_SHORT_LABELS.get(item.get("quadrant") or "", item.get("quadrant") or "未知"),
        key_data,
        evidence[0],
        _verdict_phrase(item),
    ]

def markdown_four_axis(four_axis: dict[str, Any] | None, base_coverage: dict[str, int]) -> list[str]:
    if not four_axis:
        return []
    deep = four_axis["deep_coverage"]
    mode_text = "深度交付" if four_axis["analysis_mode"] == "deep" else "基础交付（深度模式未启用）"
    lines = [
        "## 四轴交汇总览（纵 × 横 × 深 × 验）",
        "",
        f"- 分析模式：{ANALYSIS_MODE_LABELS.get(four_axis['analysis_mode'], four_axis['analysis_mode'])}｜{mode_text}",
        f"- 基础覆盖：可得{base_coverage['available']} / 部分{base_coverage['partial']} / 未知{base_coverage['unknown']}",
        f"- 深度覆盖：可得{deep['available']} / 部分{deep['partial']} / 未知{deep['unknown']} / 未声明{deep['missing']}（{deep['declared']}/{deep['total']}已声明）",
        f"- {four_axis['note']}。",
        "",
        "| 轴 | 状态 | 证据 |",
        "|---|---|---|",
    ]
    for key, label in (
        ("longitudinal", "纵｜时间演化"),
        ("horizontal", "横｜当日截面"),
        ("depth", "深｜机制与贡献"),
        ("verification", "验｜事后闭环"),
    ):
        axis = four_axis["axes"][key]
        if key == "verification":
            evidence = (
                f"未来{axis['future_count']}项（范围："
                f"{'、'.join(SCOPE_LABELS.get(s, s) for s in axis['future_scopes']) or '无'}）；"
                f"到期判定 成立/未成立/缺观察值="
                f"{axis['resolved_counts']['passed']}/{axis['resolved_counts']['failed']}/{axis['resolved_counts']['unknown']}"
            )
        else:
            evidence = _axis_evidence(axis)
        lines.append(f"| {label} | {STATUS_LABELS[axis['status']]} | {evidence} |")
    rows = four_axis.get("theme_intersections", [])
    if rows:
        lines.extend(
            [
                "",
                "### 主题跨轴交汇",
                "",
                f"> {_market_context(rows)}",
                "",
                "当日主线速览（按当日判定强弱排序；读法描述结构，不预测方向）：",
                "",
                "| 主线 | 当日判定 | 关键数据 | 催化与验证 | 读法 |",
                "|---|---|---|---|---|",
            ]
        )
        for item in _sorted_digest_rows(rows):
            cells = [item["name"]] + _digest_cells(item)
            lines.append("| " + " | ".join(cells) + " |")
        header_cells = ["主题"] + [AXIS_COLUMN_HEADERS[key] for key in (
            "longitudinal", "horizontal", "liquidity", "concentration", "catalyst", "verification"
        )] + ["交汇结果"]
        lines.extend(
            [
                "",
                "<details>",
                "<summary>审计明细：六轴逐项判定（每格状态与原因，规则复算用）</summary>",
                "",
                f"> {AXIS_LEGEND}",
                "",
                "| " + " | ".join(header_cells) + " |",
                "|" + "|".join(["---"] + ["---"] * (len(header_cells) - 1)) + "|",
            ]
        )
        for item in rows:
            checks = item["checks"]
            cells = [item["name"]]
            for key in (
                "longitudinal", "horizontal", "liquidity", "concentration", "catalyst", "verification"
            ):
                label = STATUS_LABELS[checks[key]["status"]]
                reason = _cell_reason(key, checks[key])
                cells.append(f"{label}（{reason}）" if reason else label)
            cells.append(RESULT_LABELS[item["result"]])
            lines.append("| " + " | ".join(cells) + " |")
        lines.extend(
            [
                "",
                f"> {RESULT_LEGEND}",
                "",
                "</details>",
                "",
            ]
        )
    return lines


def html_four_axis(four_axis: dict[str, Any] | None, base_coverage: dict[str, int]) -> str:
    if not four_axis:
        return ""
    deep = four_axis["deep_coverage"]
    mode_label = "深度交付" if four_axis["analysis_mode"] == "deep" else "基础交付 · 深度组件未启用"
    axis_rows = []
    for key, label in (
        ("longitudinal", "纵｜时间演化"),
        ("horizontal", "横｜当日截面"),
        ("depth", "深｜机制与贡献"),
        ("verification", "验｜事后闭环"),
    ):
        axis = four_axis["axes"][key]
        if key == "verification":
            evidence = (
                f"未来{axis['future_count']}项 · 范围：{'、'.join(SCOPE_LABELS.get(s, s) for s in axis['future_scopes']) or '无'} · "
                f"到期 成立/未成立/缺观察值={axis['resolved_counts']['passed']}/{axis['resolved_counts']['failed']}/{axis['resolved_counts']['unknown']}"
            )
        else:
            evidence = _axis_evidence(axis)
        axis_rows.append(
            f"<tr><td>{html_text(label)}</td><td>{html_text(STATUS_LABELS[axis['status']])}</td><td>{html_text(evidence)}</td></tr>"
        )
    theme_rows = []
    for item in four_axis.get("theme_intersections", []):
        checks = item["checks"]
        cells = [f"<td>{html_text(item['name'])}</td>"]
        for key in (
            "longitudinal", "horizontal", "liquidity", "concentration", "catalyst", "verification"
        ):
            label = STATUS_LABELS[checks[key]["status"]]
            reason = _cell_reason(key, checks[key])
            cell = f"{label}<br><small>{html_text(reason)}</small>" if reason else label
            cells.append(f"<td>{cell}</td>")
        cells.append(f"<td>{html_text(RESULT_LABELS[item['result']])}</td>")
        theme_rows.append("<tr>" + "".join(cells) + "</tr>")
    theme_table = ""
    raw_rows = four_axis.get("theme_intersections", [])
    if raw_rows:
        digest_rows = "".join(
            "<tr><td>"
            + html_text(item["name"])
            + "</td><td>"
            + "</td><td>".join(html_text(cell) for cell in _digest_cells(item))
            + "</td></tr>"
            for item in _sorted_digest_rows(raw_rows)
        )
        detail_header = "".join(
            f"<th>{html_text(text)}</th>"
            for text in ["主题"] + [AXIS_COLUMN_HEADERS[key] for key in (
                "longitudinal", "horizontal", "liquidity", "concentration", "catalyst", "verification"
            )] + ["结果"]
        )
        theme_table = (
            '<article class="panel wide"><div class="panel-head"><h2>主题跨轴交汇</h2>'
            '<span>当日主线速览 · 显式规则 · 无总分</span></div>'
            f'<p class="section-note">{html_text(_market_context(raw_rows))}</p>'
            '<div class="table-wrap"><table class="tbl four-axis-theme-table"><thead><tr>'
            + "".join(f"<th>{html_text(t)}</th>" for t in ["主线", "当日判定", "关键数据", "催化与验证", "读法"])
            + "</tr></thead><tbody>"
            + digest_rows
            + '</tbody></table></div>'
            '<details class="method-details"><summary>审计明细：六轴逐项判定（每格状态与原因）</summary>'
            '<div class="table-wrap"><table class="tbl"><thead><tr>'
            + detail_header
            + "</tr></thead><tbody>"
            + "".join(theme_rows)
            + '</tbody></table></div>'
            f'<p class="section-note">{html_text(AXIS_LEGEND)}</p>'
            f'<p class="section-note">{html_text(RESULT_LEGEND)}</p>'
            "</details></article>"
        )
    return (
        '<section id="four-axis" class="dashboard-grid" aria-label="纵横深验四轴总览">'
        '<article class="panel"><div class="panel-head"><h2>交付模式</h2><span>'
        + html_text(mode_label)
        + '</span></div><dl class="facts"><dt>基础覆盖</dt><dd>'
        + html_text(f"可得{base_coverage['available']} / 部分{base_coverage['partial']} / 未知{base_coverage['unknown']}")
        + '</dd><dt>深度覆盖</dt><dd>'
        + html_text(f"可得{deep['available']} / 部分{deep['partial']} / 未知{deep['unknown']} / 未声明{deep['missing']}")
        + f'</dd><dt>深度组件</dt><dd>{deep["declared"]}/{deep["total"]} 已声明</dd></dl></article>'
        '<article class="panel"><div class="panel-head"><h2>四轴状态</h2><span>纵 × 横 × 深 × 验</span></div>'
        '<div class="table-wrap"><table class="tbl"><thead><tr><th>轴</th><th>状态</th><th>证据</th></tr></thead><tbody>'
        + "".join(axis_rows)
        + '</tbody></table></div><p class="section-note">'
        + html_text(four_axis["note"])
        + "</p></article>"
        + theme_table
        + "</section>"
    )
