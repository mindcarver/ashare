#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复盘渲染的共享格式化与 HTML 片段助手。

从 render.py 抽出（1.2 分析层落地后 render.py 逼近 700 行上限），让主渲染器与
`render_analysis.py` 共用同一套数值格式与转义，避免两处各写一份导致口径漂移。
导入无副作用。
"""

from html import escape
from typing import Any


def fmt_evidence(evidence: dict[str, Any]) -> str:
    number = float(evidence["value"])
    unit = evidence["unit"]
    if unit == "percent":
        return f"{number:+.2f}%"
    if unit == "CNY":
        return f"{number / 1e8:,.2f}亿元"
    if unit == "count":
        return f"{number:,.0f}"
    if unit == "index_points":
        return f"{number:,.2f}"
    return f"{number:g} {unit}"


def fmt_history_value(number: float | None, unit: str) -> str:
    if number is None:
        return "未知"
    return fmt_evidence({"value": number, "unit": unit})


def fmt_level(number: float | None, unit: str) -> str:
    """水平值（阈值、观察值）：不带正负号，避免把水位读成变化量。"""
    if number is None:
        return "未知"
    if unit == "percent":
        return f"{number:g}%"
    if unit == "count":
        return f"{number:,.0f}"
    if unit == "CNY":
        return f"{number / 1e8:,.2f}亿元"
    if unit == "ratio":
        return f"{number:g}"
    return f"{number:g} {unit}"


def fmt_flow_cny(number: float | None) -> str:
    """资金净流入/净流出：必须保留正负号，方向是这类证据的全部信息量。"""
    if number is None:
        return "未知"
    return f"{number / 1e8:+,.2f}亿元"


def fmt_signed_pct(number: float | None) -> str:
    if number is None:
        return "未知"
    return f"{number:+.2f}%"


def unknown_line(section: dict[str, Any]) -> str:
    return f"> 未知：{public_status_reason(section)}"


def public_status_reason(section: dict[str, Any]) -> str:
    """Return a report-safe availability explanation without acquisition details."""
    declared = section.get("public_status_reason")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    return {
        "available": "证据已校验。",
        "partial": "部分字段不可得，缺失项保持未知，未以0代替。",
        "unknown": "证据不足，无法判断；未以0代替。",
    }.get(section.get("availability"), "证据状态未声明。")


def public_classification(section: dict[str, Any], fallback: str) -> str:
    """Use an explicitly public taxonomy label, never an internal provider label."""
    declared = section.get("public_classification")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    return fallback


def public_caveat(section: dict[str, Any]) -> str | None:
    """Expose caveats only through a provider-neutral public field."""
    declared = section.get("public_caveat")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    if section.get("caveat"):
        return "存在输入声明的口径限制；结论按保守口径解释。"
    return None


def public_method_category(category: str | None) -> str:
    """Map internal method categories to provider-neutral report wording."""
    return {
        "exchange_fact": "公开披露事实",
        "provider_model": "模型推导口径",
        "derived": "规则派生",
        "activity_proxy": "活跃度代理",
    }.get(category or "", "未声明方法类别")


def html_text(value: Any) -> str:
    return escape(str(value), quote=True)


def availability_badge(section: dict[str, Any]) -> str:
    status = section["availability"]
    labels = {"available": "可得", "partial": "部分", "unknown": "未知"}
    return f'<span class="badge badge-{status}">{labels[status]}</span>'


def value_tone(number: float | None) -> str:
    if number is None:
        return "neutral"
    return "rise" if number > 0 else "fall" if number < 0 else "neutral"


def html_evidence(evidence: dict[str, Any]) -> str:
    return (
        f'观测 {html_text(evidence["observed_at"])} · '
        f'发布 {html_text(evidence["published_at"])}'
    )


def html_metric_card(label: str, display: str, detail: str, tone: str = "neutral") -> str:
    return f'''<article class="metric-card tone-{tone}">
  <p>{html_text(label)}</p><strong>{html_text(display)}</strong><small>{html_text(detail)}</small>
</article>'''


def humanize_condition_value(value: float, unit: str) -> str:
    """验证点/阈值条件的观察值或阈值：单位落到读者语言（CNY→亿元、count→家…）。"""
    if unit == "CNY":
        return f"{value / 1e8:,.2f}亿元"
    if unit == "percent":
        return f"{value:g}%"
    if unit == "ratio":
        return f"{value:g}倍"
    if unit == "count":
        return f"{value:,.0f}家"
    return f"{value:g} {unit}"


def translate_rule_text(text: str, metric_labels: dict[str, str], state_labels: dict[str, str]) -> str:
    """把规则/证据文本里的英文码替换为中文标签：只做逐词替换，不改语义。

    覆盖：蛇形指标码、情绪状态码、布尔字面量、and/or/not 连接词与算子。
    未登记的词保持原文，由公开语言门禁兜底拦截。
    """
    import re as _re

    tokens = sorted(set(metric_labels) | set(state_labels), key=len, reverse=True)
    for token in tokens:
        text = _re.sub(r"(?<![A-Za-z0-9_])" + _re.escape(token) + r"(?![A-Za-z0-9_])",
                       metric_labels.get(token) or state_labels[token], text)
    for old, new in (("True", "是"), ("False", "否"), (">=", "≥"), ("<=", "≤")):
        text = text.replace(old, new)
    for old, new in ((" and ", " 且 "), (" or ", " 或 "), (" not ", " 非 ")):
        text = text.replace(old, new)
    return text
