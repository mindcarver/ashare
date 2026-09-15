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
        return "unknown"
    return fmt_evidence({"value": number, "unit": unit})


def fmt_level(number: float | None, unit: str) -> str:
    """水平值（阈值、观察值）：不带正负号，避免把水位读成变化量。"""
    if number is None:
        return "unknown"
    if unit == "percent":
        return f"{number:g}%"
    if unit == "count":
        return f"{number:,.0f}"
    if unit == "CNY":
        return f"{number / 1e8:,.2f}亿元"
    return f"{number:g} {unit}"


def fmt_flow_cny(number: float | None) -> str:
    """资金净流入/净流出：必须保留正负号，方向是这类证据的全部信息量。"""
    if number is None:
        return "unknown"
    return f"{number / 1e8:+,.2f}亿元"


def fmt_signed_pct(number: float | None) -> str:
    if number is None:
        return "unknown"
    return f"{number:+.2f}%"


def unknown_line(section: dict[str, Any]) -> str:
    return f"> {section['availability'].upper()}：{section['status_reason']}"


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
    source = evidence["source"]
    return (
        f'{html_text(source["name"])} · 观测 {html_text(evidence["observed_at"])} · '
        f'发布 {html_text(evidence["published_at"])}'
    )


def html_metric_card(label: str, display: str, detail: str, tone: str = "neutral") -> str:
    return f'''<article class="metric-card tone-{tone}">
  <p>{html_text(label)}</p><strong>{html_text(display)}</strong><small>{html_text(detail)}</small>
</article>'''
