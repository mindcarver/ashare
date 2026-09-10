#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTML 片段与整页渲染（拆分自 gen_dashboard.py，审计 P2-5）。

页面模板在 page_template.py；设计令牌与报告外壳的注入在 build_html() 末尾完成。
"""
import json

import _paths  # noqa: F401  确保 skills/_shared 在 sys.path 上
from ashare_shared import inject_shared_css

from derive import avail_badge_class, avail_class, avail_label, digest, limited, mkt_aggregate
from page_template import PAGE_TEMPLATE
from schema import DIM_LABEL, DIMS, MARKETS, MKT_LABEL, SECTOR_STANCE_CLS

DISCLAIMER = "以上为证据约束下的环境解释与研究辅助，不代表未来收益、因果关系或投资建议。"


def risk_badge(cfg):
    """风险徽章：高=红点/中=橙点/低=绿点"""
    risk = cfg.get("risk")
    if not risk:
        return ""
    lvl = risk.get("level")
    cls = {"high": "rk-high", "medium": "rk-medium", "low": "rk-low"}.get(lvl, "rk-low")
    title = {"high": "高风险", "medium": "需验证", "low": "缓解"}.get(lvl, "")
    return f'<span class="risk-dot {cls}" title="{title}"></span>'


def cell_html(cells, m, d):
    cfg = cells[f"{m}|{d}"]
    a = cfg["availability"]
    # AI 分析摘要（透镜式）：analysis 数组，每项 [透镜名, 一句话]
    analysis_html = ""
    if cfg.get("analysis"):
        items = "".join(
            f'<li><span class="an-lens">{lens}</span><span class="an-txt">{txt}</span></li>'
            for lens, txt in cfg["analysis"]
        )
        analysis_html = (f'<div class="cell-analysis"><div class="an-head">AI 分析</div>'
                         f'<ul class="an-list">{items}</ul></div>')
    return (f'<div class="cell" data-key="{m}|{d}">'
            f'<div class="cell-head"><span class="cell-name">{DIM_LABEL[d]}{risk_badge(cfg)}</span>'
            f'<span class="badge {avail_badge_class(a)}">{avail_label(a)}</span></div>'
            f'<div class="chart-box" id="ch-{m}-{d}"></div>'
            f'{analysis_html}'
            f'<div class="cell-evidence" id="ev-{m}-{d}"></div></div>')


def matrix_rows_html(cells):
    matrix_rows = []
    for m in MARKETS:
        row = [f'<div class="matrix-cell lbl">{MKT_LABEL[m]}</div>']
        for d in DIMS:
            c = cells[f"{m}|{d}"]["availability"]
            row.append(f'<div class="matrix-cell {avail_class(c)}">{"●" if m != "global" else "▲"}</div>')
        matrix_rows.append("\n    ".join(row))
    return "\n".join("    " + row for row in matrix_rows)


def sections_html(cells):
    sections = []
    for m in MARKETS:
        agg = mkt_aggregate(cells, m)
        cells_html = "\n".join("        " + cell_html(cells, m, d) for d in DIMS)
        sections.append(
            f'<section class="market" aria-label="{MKT_LABEL[m]}资本环境">\n'
            f'  <div class="market-head"><h2>{MKT_LABEL[m]}</h2>'
            f'<span class="badge {avail_badge_class(agg)}">{avail_label(agg)}</span></div>\n'
            f'  <div class="market-grid">\n{cells_html}\n  </div>\n</section>')
    return "\n\n".join(sections)


def dashboard_content(cells, all_unknown):
    if all_unknown:
        return ('<div class="empty-state">该日期无可得的资本环境数据。'
                '请选择一个有可靠数据的日期。</div>')
    return (f'<div class="matrix-wrap">\n'
            f'  <div class="matrix-cell lbl">市场/维度</div>\n'
            f'  <div class="matrix-cell lbl">增长</div>\n'
            f'  <div class="matrix-cell lbl">通胀</div>\n'
            f'  <div class="matrix-cell lbl">流动性</div>\n'
            f'  <div class="matrix-cell lbl">资金价格</div>\n'
            f'  <div class="matrix-cell lbl">风险偏好与信用</div>\n'
            f'  <div class="matrix-cell lbl">市场宽度</div>\n'
            f'  <div class="matrix-cell lbl">机构持仓与拥挤度</div>\n'
            f'{matrix_rows_html(cells)}\n'
            f'</div>\n'
            f'<div class="matrix-legend">\n'
            f'  <span><i class="swatch" style="background:var(--state-ok-soft)"></i>可得</span>\n'
            f'  <span><i class="swatch" style="background:var(--state-warn-soft)"></i>部分/待复核</span>\n'
            f'  <span><i class="swatch" style="background:var(--state-bad-soft)"></i>未知/失败/无法还原</span>\n'
            f'</div>\n'
            f'<div id="markets">\n{sections_html(cells)}\n</div>')


def takeaway_html(cells, all_unknown):
    ai_takeaways, risk_high, risk_medium, risk_low = digest(cells)
    if all_unknown or not ai_takeaways:
        return ""
    top_takeaways = limited(ai_takeaways, 8)
    items = "".join(
        f'<div class="tw-item"><span class="tw-tag">{tag}</span><span class="tw-txt">{txt}</span></div>'
        for tag, txt in top_takeaways
    )

    def risk_block(title, entries, cls):
        if not entries:
            return ""
        rows = "".join(
            f'<div class="tw-item"><span class="tw-tag">{tag}</span><span class="tw-txt">{txt}</span></div>'
            for tag, txt in entries
        )
        return f'<div class="risk-section {cls}"><div class="risk-title">{title}</div><div class="tw-list">{rows}</div></div>'

    risk_html = (risk_block("高优先级风险", limited(risk_high, 3), "risk-high")
                 + risk_block("需验证信号", limited(risk_medium, 3), "risk-medium")
                 + risk_block("缓解因素", limited(risk_low, 2), "risk-low"))
    return (f'<div class="takeaway-box">'
            f'<div class="tw-head">AI 综合研判 · 跨格交叉验证</div>'
            f'<div class="tw-list">{items}</div></div>'
            f'<div class="risk-box">'
            f'<div class="tw-head">风险信号清单 · 投资视角</div>'
            f'{risk_html}</div>')


def sector_advice_html(sector_advice):
    """板块倾向建议层（可选）：用户要求投资/板块建议时，从 cells JSON 顶层 sectorAdvice 渲染。
    约束：仅板块/主题粒度；倾向只用 关注/中性/回避；每条必须带证据来源 + 证伪条件；卡头固定免责声明。"""
    if not sector_advice or not sector_advice.get("markets"):
        return ""
    disclaimer = (sector_advice.get("disclaimer")
                  or "以下为基于资本环境证据的板块方向性研究参考，仅为建议，不构成投资建议或买卖指令，不保证未来表现。")
    market_blocks = []
    for mkt in sector_advice.get("markets", []):
        rows = []
        for it in mkt.get("items", []):
            stance = it.get("stance", "中性")
            cls = SECTOR_STANCE_CLS.get(stance, "st-mid")
            rows.append(
                '<div class="sa-item">'
                f'<span class="sa-stance {cls}">{stance}</span>'
                f'<span class="sa-sector">{it.get("sector", "")}</span>'
                f'<div class="sa-ev"><b>证据：</b>{it.get("evidence", "")}</div>'
                f'<div class="sa-tr"><b>证伪条件：</b>{it.get("trigger", "")}</div>'
                '</div>'
            )
        mkt_name = mkt.get("market", "")
        mkt_date = f'<span class="sa-mkt-date">{mkt.get("date", "")}</span>' if mkt.get("date") else ""
        market_blocks.append(
            f'<div class="sa-mkt"><div class="sa-mkt-name">{mkt_name}</div>{mkt_date}'
            f'<div class="sa-list">{"".join(rows)}</div></div>'
        )
    return (f'<div class="sector-advice-box">'
            f'<div class="tw-head">板块倾向建议 · 研究参考（仅建议）</div>'
            f'<p class="sa-disclaimer">{disclaimer}</p>'
            f'{"".join(market_blocks)}</div>')



def build_html(cells, as_of, sector_advice, overview_text, all_unknown):
    """组装整页 HTML 并注入共享设计令牌 + 报告外壳。"""
    html = (PAGE_TEMPLATE
            .replace("{{AS_OF}}", as_of)
            .replace("{{OVERVIEW}}", overview_text).replace("{{DISCLAIMER}}", DISCLAIMER)
            .replace("{{TAKEAWAYS_HTML}}", takeaway_html(cells, all_unknown))
            .replace("{{SECTOR_ADVICE_HTML}}", sector_advice_html(sector_advice))
            .replace("{{DASHBOARD_CONTENT}}", dashboard_content(cells, all_unknown))
            .replace("{{CELLS_JSON}}", json.dumps(cells, ensure_ascii=False, indent=1)))
    return inject_shared_css(html)
