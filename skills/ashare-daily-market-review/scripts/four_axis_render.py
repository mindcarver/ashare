#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纵 × 横 × 深 × 验四轴总览的Markdown/HTML片段。"""

from typing import Any

from formatting import html_text


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


def _axis_evidence(axis: dict[str, Any]) -> str:
    checks = axis.get("checks", [])
    if checks:
        return "；".join(item["evidence"] for item in checks)
    return "该轴未启用或没有可得证据"


def markdown_four_axis(four_axis: dict[str, Any] | None, base_coverage: dict[str, int]) -> list[str]:
    if not four_axis:
        return []
    deep = four_axis["deep_coverage"]
    mode_text = "深度交付" if four_axis["analysis_mode"] == "deep" else "基础交付（深度模式未启用）"
    lines = [
        "## 四轴交汇总览（纵 × 横 × 深 × 验）",
        "",
        f"- 分析模式：`{four_axis['analysis_mode']}`｜{mode_text}",
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
                f"未来{axis['future_count']}项，scope={','.join(axis['future_scopes']) or 'none'}；"
                f"到期passed/failed/unknown="
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
                "| 主题 | 纵 | 横 | 量价 | 集中度 | 催化 | 验证 | 交汇结果 |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        for item in rows:
            checks = item["checks"]
            lines.append(
                f"| {item['name']} | {STATUS_LABELS[checks['longitudinal']['status']]} | "
                f"{STATUS_LABELS[checks['horizontal']['status']]} | {STATUS_LABELS[checks['liquidity']['status']]} | "
                f"{STATUS_LABELS[checks['concentration']['status']]} | {STATUS_LABELS[checks['catalyst']['status']]} | "
                f"{STATUS_LABELS[checks['verification']['status']]} | {RESULT_LABELS[item['result']]} |"
            )
        lines.extend(
            [
                "",
                "> “多轴支持”要求六项检查全部有证据支持；任一缺证保持仅横向或证据不足，任一市场环境/集中度反证落为环境冲突。",
                "",
            ]
        )
    return lines


def html_four_axis(four_axis: dict[str, Any] | None, base_coverage: dict[str, int]) -> str:
    if not four_axis:
        return ""
    deep = four_axis["deep_coverage"]
    mode_label = "DEEP · 深度交付" if four_axis["analysis_mode"] == "deep" else "CORE · 深度模式未启用"
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
                f"未来{axis['future_count']}项 · scope={','.join(axis['future_scopes']) or 'none'} · "
                f"到期{axis['resolved_counts']['passed']}/{axis['resolved_counts']['failed']}/{axis['resolved_counts']['unknown']}"
            )
        else:
            evidence = _axis_evidence(axis)
        axis_rows.append(
            f"<tr><td>{html_text(label)}</td><td>{html_text(STATUS_LABELS[axis['status']])}</td><td>{html_text(evidence)}</td></tr>"
        )
    theme_rows = []
    for item in four_axis.get("theme_intersections", []):
        checks = item["checks"]
        theme_rows.append(
            "<tr>"
            f"<td>{html_text(item['name'])}</td>"
            + "".join(
                f"<td>{html_text(STATUS_LABELS[checks[key]['status']])}</td>"
                for key in ("longitudinal", "horizontal", "liquidity", "concentration", "catalyst", "verification")
            )
            + f"<td>{html_text(RESULT_LABELS[item['result']])}</td></tr>"
        )
    theme_table = ""
    if theme_rows:
        theme_table = (
            '<article class="panel wide"><div class="panel-head"><h2>主题跨轴交汇</h2><span>显式规则 · 无总分</span></div>'
            '<div class="table-wrap"><table class="tbl four-axis-theme-table"><thead><tr><th>主题</th><th>纵</th><th>横</th><th>量价</th><th>集中度</th><th>催化</th><th>验证</th><th>结果</th></tr></thead><tbody>'
            + "".join(theme_rows)
            + '</tbody></table></div><p class="section-note">多轴支持要求六项均有证据支持；缺证不补通过，环境或集中度反证优先。</p></article>'
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
