#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""股性报告的 HTML 与 Markdown 渲染。

版式约定：
  - 页面骨架、组件样式、设计令牌全部来自 skills/_shared（inject_shared_css 注入），
    本文件只写股性特有的版式（地图、矩阵、明细筛选），不得重定义共享类。
  - 报告全文过禁词门（tier = score_ok：允许自有评分，禁止价位与交易指令）。
  - 只描述结构，不给方向、不给动作、不给价位。
"""

import html

from typing import Any

from schema import (
    ARCHETYPE_LABELS,
    ARCHETYPE_ORDER,
    DIMENSION_LABELS,
    DIMENSION_QUESTIONS,
    DIMENSIONS,
    QUADRANT_LABELS,
)

DISCLAIMER = (
    "本报告的每一项都是对历史交易行为的统计描述，不构成投资建议；"
    "原型与分位是结构分类，不是评级，也不是任何买卖或仓位判断。"
)

MAP_WIDTH = 900
MAP_HEIGHT = 470
MAP_PAD_LEFT = 70
MAP_PAD_RIGHT = 30
MAP_PAD_TOP = 30
MAP_PAD_BOTTOM = 60

# 容量口径 → 气泡图例文案（三种口径语义不同，不能混用一句话）。
_SIZE_METRIC_LABELS = {
    "amount_avg_cny": "日均成交额",
    "float_cap_cny": "流通市值",
    "turnover_avg_pct": "日均换手率",
}


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _num(value: Any, digits: int = 2, suffix: str = "", dash: str = "—") -> str:
    if value is None:
        return dash
    if isinstance(value, float):
        text = f"{value:,.{digits}f}"
    else:
        text = f"{value:,}"
    return f"{text}{suffix}"


def _signed(value: Any, digits: int = 2, suffix: str = "%") -> str:
    if value is None:
        return "—"
    tone = "pm-pos" if float(value) >= 0 else "pm-neg"
    return f'<span class="{tone}">{float(value):+,.{digits}f}{suffix}</span>'


def _capacity_text(value: Any, metric: str) -> str:
    if value is None:
        return "—"
    if metric == "amount_avg_cny":
        return f"{float(value) / 1e8:,.2f}亿元"
    return f"{float(value):,.2f}%"


def _risk_color(value: Any) -> str:
    """埋人风险 → 语义色。用共享层状态色（不是涨跌色），并在地图图例里写明。"""
    if value is None:
        return "var(--state-unknown)"
    level = float(value)
    if level >= 75:
        return "var(--state-bad)"
    if level >= 55:
        return "var(--state-warn)"
    if level >= 35:
        return "var(--muted)"
    return "var(--state-ok)"


def _risk_word(value: Any) -> str:
    if value is None:
        return "未评估"
    level = float(value)
    if level >= 75:
        return "高"
    if level >= 55:
        return "偏高"
    if level >= 35:
        return "中"
    return "低"


def _dim_cell(value: Any) -> str:
    if value is None:
        return '<td class="num">—</td>'
    return f'<td class="num">{float(value):.1f}</td>'


def _panel(title: str, body: str, badge: str = "", badge_class: str = "badge-available") -> str:
    head = f'<div class="panel-head"><h2>{_esc(title)}</h2>'
    if badge:
        head += f'<span class="badge {badge_class}">{_esc(badge)}</span>'
    head += "</div>"
    return f'<article class="panel wide">{head}{body}</article>'


# --- 各面板 -----------------------------------------------------------------


def _hero(derived: dict[str, Any]) -> str:
    overview = derived["overview"]
    counts = derived["map"]["quadrant_counts"]
    cards = [
        ("池内标的数", _num(overview["total"]), f"六维齐全 {overview['scored']} 只"),
        (
            "平均股性分",
            _num(overview["mean_composite"], 1),
            f"仅 {_num(overview['scored_share_pct'], 1, '%')} 的标的六维齐全",
        ),
        (
            "高异动·高溢价",
            _num(counts.get("hh", 0)),
            f"高异动·低溢价 {counts.get('hl', 0)} 只",
        ),
        (
            "高埋人风险型",
            _num(
                next(
                    row["count"]
                    for row in derived["archetype_table"]
                    if row["archetype"] == "bury_trap"
                )
            ),
            "埋人风险进入池内前段",
        ),
        ("平均埋人率", _num(overview["mean_bury_rate_pct"], 1, "%"), "异动后窗口内回撤越线占比"),
        (
            "平均被选中次数",
            _num(overview["mean_selected_per_year"], 1, " 次/年"),
            "异动日与龙虎榜日去重",
        ),
    ]
    cells = "".join(
        f'<div class="metric-card"><span>{_esc(label)}</span><strong>{value}</strong>'
        f"<small>{_esc(note)}</small></div>"
        for label, value, note in cards
    )
    window = derived["window"]
    strip = (
        f'<aside class="verify-strip" aria-label="窗口与口径"><span>窗口与口径</span>'
        f'<strong>{_esc(window["start"])} ~ {_esc(window["end"])} · '
        f'{window["trading_days"]} 个交易日</strong>'
        f'<small>容量口径 {_esc(derived["capacity_metric"])} · '
        f'池内百分位是相对位置，不是绝对好坏</small></aside>'
    )
    return f'<section class="hero-grid" aria-label="总览">{cells}</section>{strip}'


def _framework(derived: dict[str, Any]) -> str:
    records = derived["stocks"]
    weights = derived["thresholds"]["score_weights"]
    rows = []
    for dim in DIMENSIONS:
        values = [row[dim] for row in records if row.get(dim) is not None]
        mean = sum(values) / len(values) if values else None
        rows.append(
            f"<tr><td>{_esc(DIMENSION_LABELS[dim])}</td>"
            f"<td>{_esc(DIMENSION_QUESTIONS[dim])}</td>"
            f'<td class="num">{_num(weights[dim] * 100, 0, "%")}</td>'
            f'<td class="num">{_num(mean, 1)}</td>'
            f'<td class="num">{len(values)}</td></tr>'
        )
    note = (
        "综合股性分 = Σ 权重 × 维度分，其中埋人风险先取 (100 − 分) 再进入加权；"
        "六个维度必须全部可得才给综合分，缺任何一维一律留空，不用 0 顶替。"
    )
    return _panel(
        "六维框架与本池均值",
        '<div class="table-wrap"><table class="tbl"><thead><tr><th>维度</th><th>回答什么</th>'
        "<th>权重</th><th>池内均值</th><th>有效样本</th></tr></thead><tbody>"
        + "".join(rows)
        + f'</tbody></table></div><p class="note">{_esc(note)}</p>',
        f"{len(records)} 只",
    )


def _archetype_panel(derived: dict[str, Any]) -> str:
    table = [row for row in derived["archetype_table"] if row["count"] > 0]
    top = max((row["count"] for row in table), default=1)
    rows = []
    for row in table:
        width = round(row["count"] / top * 100, 2)
        rows.append(
            f'<div class="sector-row"><span>{_esc(row["label"])}</span>'
            f'<div class="bar-track positive"><i style="width:{width}%"></i></div>'
            f'<b class="num">{row["count"]}</b>'
            f'<span class="pm-share">{_num(row["share_pct"], 1, "%")}</span></div>'
        )
    head = (
        '<div class="table-wrap"><table class="tbl"><thead><tr><th>原型</th><th>只数</th>'
        "<th>占比</th><th>平均股性分</th><th>平均次日溢价</th><th>平均埋人率</th>"
        "<th>平均被选中</th></tr></thead><tbody>"
    )
    body = "".join(
        f'<tr><td>{_esc(row["label"])}</td><td class="num">{row["count"]}</td>'
        f'<td class="num">{_num(row["share_pct"], 1, "%")}</td>'
        f'<td class="num">{_num(row["mean_composite"], 1)}</td>'
        f'<td class="num">{_signed(row["mean_next_day_pct"])}</td>'
        f'<td class="num">{_num(row["mean_bury_rate_pct"], 1, "%")}</td>'
        f'<td class="num">{_num(row["mean_selected_per_year"], 1)}</td></tr>'
        for row in table
    )
    note = (
        "原型按固定优先级首个命中即归类：连板妖股型 → 高波动题材型 → 情绪活跃型 → "
        "高埋人风险型 → 趋势慢牛型 → 权重稳重型 → 普通型。普通型代表「未获足够证据归类」。"
    )
    return _panel(
        "股性原型分布",
        "".join(rows) + head + body + f'</tbody></table></div><p class="note">{_esc(note)}</p>',
        f"{len(table)} 类命中",
    )


def _matrix_panel(derived: dict[str, Any]) -> str:
    matrix = derived["archetype_sector_matrix"]
    columns = matrix["sectors"]
    scores = [
        cell["mean_composite"]
        for row in matrix["cells"]
        for cell in row["cells"]
        if cell["mean_composite"] is not None
    ]
    head = "<tr><th>原型 \\ 板块</th>" + "".join(f"<th>{_esc(name)}</th>" for name in columns) + "</tr>"
    body = []
    for row in matrix["cells"]:
        cells = []
        for cell in row["cells"]:
            if cell["count"] == 0:
                cells.append('<td class="matrix-cell empty">·</td>')
                continue
            score = cell["mean_composite"]
            if score is None:
                # 有样本但样本全都缺证据：只报只数，不染色、不编造均值。
                cells.append(
                    f'<td class="matrix-cell"><b>{cell["count"]}</b><small>—</small></td>'
                )
                continue
            alpha = 0.0 if not scores else max(0.0, min(1.0, (score - min(scores)) / max(1e-9, max(scores) - min(scores))))
            cells.append(
                f'<td class="matrix-cell" style="background:rgba(27,57,216,{alpha * 0.28:.3f})">'
                f'<b>{cell["count"]}</b><small>{_num(score, 1)}</small></td>'
            )
        body.append(f'<tr><th>{_esc(row["label"])}</th>{"".join(cells)}</tr>')
    note = (
        f'板块取池内只数前 {len(columns)} 个，其余 {matrix["collapsed_sector_count"]} 个合并为「其他行业」。'
        "单元格上行是只数、下行是该格平均股性分；空格代表该板块没有这个原型的样本，不是 0 分。"
    )
    return _panel(
        "板块 × 股性原型矩阵",
        f'<div class="table-wrap"><table class="tbl pm-matrix">{head}{"".join(body)}</table></div>'
        f'<p class="note">{_esc(note)}</p>',
        f"{len(columns)} 个板块",
    )


def _sector_panel(derived: dict[str, Any]) -> str:
    rows = []
    for item in derived["sector_table"]:
        rows.append(
            f'<tr><td>{_esc(item["sector"])}</td><td class="num">{item["count"]}</td>'
            f'<td class="num">{_num(item["mean_composite"], 1)}</td>'
            f'<td class="num">{_signed(item["mean_next_day_pct"])}</td>'
            f'<td class="num">{_num(item["mean_bury_rate_pct"], 1, "%")}</td>'
            f'<td class="num">{item["legend_count"]}</td>'
            f'<td class="num">{item["trap_count"]}</td></tr>'
        )
    note = (
        "平均股性分为「—」代表该板块内没有任何标的同时具备六维证据；"
        "只数与板块×原型矩阵一致，不用 0 顶替缺失。"
    )
    return _panel(
        "板块 × 股性 排序",
        '<div class="table-wrap"><table class="tbl"><thead><tr><th>板块</th><th>只数</th>'
        "<th>平均股性分</th><th>平均次日溢价</th><th>平均埋人率</th><th>连板妖股型</th>"
        "<th>高埋人风险型</th></tr></thead><tbody>"
        + "".join(rows)
        + f'</tbody></table></div><p class="note">{_esc(note)}</p>',
        f"{len(rows)} 个板块",
    )


def _map_panel(derived: dict[str, Any]) -> str:
    data = derived["map"]
    points = data["points"]
    if not points:
        return _panel("股性地图", '<p class="note">没有可绘制的点：全部标的缺少 D1 或 D2。</p>', "0 个点", "badge-unknown")

    min_size = data["size_min"] if data["size_min"] is not None else 1.0
    max_size = data["size_max"] if data["size_max"] is not None else 1.0
    span = max(1e-9, max_size - min_size)
    axis_left = MAP_PAD_LEFT
    axis_right = MAP_WIDTH - MAP_PAD_RIGHT
    axis_top = MAP_PAD_TOP
    axis_bottom = MAP_HEIGHT - MAP_PAD_BOTTOM

    def x_of(value: float) -> float:
        return axis_left + (axis_right - axis_left) * min(1.0, max(0.0, value / 100.0))

    def y_of(value: float) -> float:
        return axis_bottom - (axis_bottom - axis_top) * min(1.0, max(0.0, value / 100.0))

    def r_of(value: Any) -> float:
        if value is None:
            return 3.0
        ratio = (float(value) - min_size) / span
        return 3.5 + 9.5 * max(0.0, min(1.0, ratio))

    marks = []
    for point in sorted(points, key=lambda item: -(item["danger"] or 0)):
        marks.append(
            f'<circle cx="{x_of(point["x"]):.1f}" cy="{y_of(point["y"]):.1f}" '
            f'r="{r_of(point["size"]):.1f}" fill="{_risk_color(point["danger"])}" '
            f'fill-opacity="0.55" stroke="{_risk_color(point["danger"])}" stroke-width="0.6">'
            f'<title>{_esc(point["name"])} {_esc(point["code"])} · '
            f'D1 {point["x"]:.1f} / D2 {point["y"]:.1f} / '
            f'容量 {_esc(_capacity_text(point["size"], data["size_metric"]))} / '
            f'埋人风险 {_risk_word(point["danger"])}</title></circle>'
        )

    grid = []
    for tick in (0, 25, 50, 75, 100):
        grid.append(
            f'<line x1="{x_of(tick):.1f}" y1="{axis_top}" x2="{x_of(tick):.1f}" y2="{axis_bottom}" '
            f'stroke="var(--hair)" stroke-width="0.5"/>'
        )
        grid.append(
            f'<line x1="{axis_left}" y1="{y_of(tick):.1f}" x2="{axis_right}" y2="{y_of(tick):.1f}" '
            f'stroke="var(--hair)" stroke-width="0.5"/>'
        )
        grid.append(
            f'<text x="{x_of(tick):.1f}" y="{axis_bottom + 18}" class="pm-tick" text-anchor="middle">{tick}</text>'
        )
        grid.append(
            f'<text x="{axis_left - 10}" y="{y_of(tick) + 4:.1f}" class="pm-tick" text-anchor="end">{tick}</text>'
        )

    labels = []
    for key, anchor, dx, dy in (
        ("hh", "end", axis_right - 8, axis_top + 20),
        ("hl", "end", axis_right - 8, axis_bottom - 10),
        ("lh", "start", axis_left + 8, axis_top + 20),
        ("ll", "start", axis_left + 8, axis_bottom - 10),
    ):
        labels.append(
            f'<text x="{dx}" y="{dy}" class="pm-quad" text-anchor="{anchor}">'
            f'{_esc(QUADRANT_LABELS[key])} {data["quadrant_counts"].get(key, 0)} 只</text>'
        )

    svg = (
        f'<svg class="pm-map" viewBox="0 0 {MAP_WIDTH} {MAP_HEIGHT}" role="img" '
        f'aria-label="股性地图：异动基因 × 溢价质量">'
        + "".join(grid)
        + "".join(labels)
        + "".join(marks)
        + f'<text x="{(axis_left + axis_right) / 2:.0f}" y="{MAP_HEIGHT - 14}" class="pm-axis" '
        f'text-anchor="middle">{_esc(data["x_label"])}</text>'
        + f'<text x="18" y="{(axis_top + axis_bottom) / 2:.0f}" class="pm-axis" '
        f'transform="rotate(-90 18 {(axis_top + axis_bottom) / 2:.0f})" text-anchor="middle">'
        f'{_esc(data["y_label"])}</text>'
        + "</svg>"
    )
    legend = (
        '<div class="matrix-legend">'
        '<span><span class="swatch" style="background:var(--state-ok)"></span>埋人风险低</span>'
        '<span><span class="swatch" style="background:var(--muted)"></span>中</span>'
        '<span><span class="swatch" style="background:var(--state-warn)"></span>偏高</span>'
        '<span><span class="swatch" style="background:var(--state-bad)"></span>高</span>'
        f'<span>气泡大小 = {_esc(_SIZE_METRIC_LABELS.get(data["size_metric"], data["size_metric"]))}</span>'
        f'<span>已绘制 {data["plotted"]} 只 · 缺 D1/D2 未绘制 {data["skipped"]} 只</span>'
        "</div>"
    )
    note = (
        f'象限由全样本 D1、D2 的中位数切分（D1 中位 {_num(data.get("x_median"), 1)}、'
        f'D2 中位 {_num(data.get("y_median"), 1)}）。'
        "右下角代表被选中频繁但次日承接偏弱的结构，是回撤风险最集中的区域。"
    )
    return _panel("股性地图：异动基因 × 溢价质量", svg + legend + f'<p class="note">{_esc(note)}</p>', f'{data["plotted"]} 个点')


def _detail_panel(derived: dict[str, Any]) -> str:
    metric = derived["capacity_metric"]
    head = (
        '<div class="pm-tabs" role="tablist">'
        '<button class="pm-tab is-on" data-filter="all">全部</button>'
        + "".join(
            f'<button class="pm-tab" data-filter="{key}">{_esc(ARCHETYPE_LABELS[key])}</button>'
            for key in ARCHETYPE_ORDER
        )
        + "</div>"
        '<input class="pm-search" type="search" placeholder="搜索代码或名称" aria-label="搜索代码或名称" />'
        '<div class="table-wrap"><table class="tbl pm-detail"><thead><tr>'
        "<th>个股</th><th>板块</th><th>原型</th>"
        + "".join(f"<th>{_esc(DIMENSION_LABELS[dim].split()[0])}</th>" for dim in DIMENSIONS)
        + "<th>股性分</th><th>次日溢价</th><th>埋人率</th><th>被选中/年</th><th>归类依据</th>"
        "</tr></thead><tbody>"
    )
    rows = []
    for row in derived["stocks"]:
        rows.append(
            f'<tr data-archetype="{row["archetype"]}" data-code="{_esc(row["code"])}" '
            f'data-name="{_esc(row["name"])}">'
            f'<td>{_esc(row["name"])} <small>{_esc(row["code"])}</small></td>'
            f'<td>{_esc(row["sector"])}</td>'
            f'<td>{_esc(ARCHETYPE_LABELS[row["archetype"]])}</td>'
            + "".join(_dim_cell(row.get(dim)) for dim in DIMENSIONS)
            + f'<td class="num">{_num(row["composite"], 1)}</td>'
            f'<td class="num">{_signed(row.get("avg_next_day_pct"))}</td>'
            f'<td class="num">{_num(row.get("bury_rate_pct"), 1, "%")}</td>'
            f'<td class="num">{_num(row.get("selected_per_year"), 1)}</td>'
            f'<td class="pm-reason">{_esc(row["archetype_reason"])}</td></tr>'
        )
    note = (
        "个股名只用于结构归因与复核，不构成个股推荐。缺证据的维度显示为「—」，"
        "其综合分同时留空。按原型标签或代码名称可筛选，点击表头可按该列排序。"
    )
    return _panel(
        "个股明细",
        head + "".join(rows) + f'</tbody></table></div><p class="note">{_esc(note)}</p>',
        f'{len(derived["stocks"])} 只',
    )


def _method_panel(derived: dict[str, Any], signals: list[dict[str, str]]) -> str:
    items = "".join(
        f"<li><strong>{_esc(signal['kind'])}</strong>{_esc(signal['text'])}"
        f"<small>{_esc(signal['evidence'])}</small></li>"
        for signal in signals
    )
    limits = "".join(f"<li>{_esc(note)}</li>" for note in derived["caveats"])
    universe = derived["universe"]
    return _panel(
        "结构信号与限制",
        f'<ul class="signal-list">{items}</ul><ul class="limits">{limits}</ul>'
        f'<p class="note">股票池：{_esc(universe["name"])} · {_esc(universe["description"])}</p>',
        "证据优先",
    )


def _source_panel(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return ""
    rows = "".join(
        f'<tr><td>{_esc(item.get("name"))}</td><td class="pm-url">{_esc(item.get("url"))}</td></tr>'
        for item in sources
    )
    return (
        '<section class="source-box"><div class="panel-head"><h2>来源汇总</h2>'
        f'<span>{len(sources)} 个来源</span></div><table><thead><tr><th>来源</th><th>URL</th>'
        f"</tr></thead><tbody>{rows}</tbody></table></section>"
    )


STYLE = """
.pm-share{color:var(--ink-tertiary);font-family:var(--font-ui);font-size:12px}
.pm-map{width:100%;height:auto;display:block;margin:4px 0 6px}
.pm-tick,.pm-axis,.pm-quad{font-family:var(--font-ui);font-size:11px;fill:var(--ink-tertiary)}
.pm-quad{font-size:11.5px;fill:var(--ink-secondary)}
.pm-matrix th,.pm-matrix td{font-size:12px;text-align:center}
.pm-matrix td.matrix-cell b{display:block;font-size:13px}
.pm-matrix td.matrix-cell small{color:var(--ink-tertiary);font-size:11px}
.pm-matrix td.empty{color:var(--ink-tertiary)}
.pm-tabs{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
.pm-tab{font-family:var(--font-ui);font-size:12px;padding:4px 10px;border:1px solid var(--rule);background:transparent;color:var(--ink-secondary);cursor:pointer}
.pm-tab.is-on{background:var(--accent);color:var(--accent-foreground);border-color:var(--accent)}
.pm-search{font-family:var(--font-ui);font-size:12px;padding:5px 8px;border:1px solid var(--rule);background:transparent;color:var(--ink-primary);margin:0 0 10px;width:220px}
.pm-detail td,.pm-detail th{white-space:nowrap}
.pm-detail td small{color:var(--ink-tertiary)}
.pm-reason{white-space:normal;max-width:320px;color:var(--ink-secondary);font-size:11.5px}
.pm-pos{color:var(--gain)}
.pm-neg{color:var(--loss)}
.pm-url{max-width:520px;word-break:break-all;color:var(--ink-tertiary);font-size:11.5px}
@media(max-width:760px){.pm-reason{max-width:200px}}
"""

SCRIPT = """
(function(){
  var table=document.querySelector('.pm-detail');
  if(!table){return;}
  var rows=Array.prototype.slice.call(table.querySelectorAll('tbody tr'));
  var tabs=Array.prototype.slice.call(document.querySelectorAll('.pm-tab'));
  var search=document.querySelector('.pm-search');
  var state={filter:'all',query:''};
  function apply(){
    rows.forEach(function(row){
      var okTab=state.filter==='all'||row.getAttribute('data-archetype')===state.filter;
      var hay=(row.getAttribute('data-code')+' '+row.getAttribute('data-name')).toLowerCase();
      var okQuery=!state.query||hay.indexOf(state.query)>=0;
      row.style.display=(okTab&&okQuery)?'':'none';
    });
  }
  tabs.forEach(function(tab){
    tab.addEventListener('click',function(){
      tabs.forEach(function(other){other.classList.remove('is-on');});
      tab.classList.add('is-on');
      state.filter=tab.getAttribute('data-filter');
      apply();
    });
  });
  if(search){
    search.addEventListener('input',function(){
      state.query=(search.value||'').trim().toLowerCase();
      apply();
    });
  }
  var headers=Array.prototype.slice.call(table.querySelectorAll('thead th'));
  headers.forEach(function(head,index){
    head.style.cursor='pointer';
    var ascending=true;
    head.addEventListener('click',function(){
      var body=table.querySelector('tbody');
      var sorted=rows.slice().sort(function(a,b){
        var av=a.children[index].innerText.trim();
        var bv=b.children[index].innerText.trim();
        var an=parseFloat(av.replace(/[^0-9.\\-+]/g,''));
        var bn=parseFloat(bv.replace(/[^0-9.\\-+]/g,''));
        var both=!isNaN(an)&&!isNaN(bn);
        if(both){return ascending?an-bn:bn-an;}
        return ascending?av.localeCompare(bv,'zh'):bv.localeCompare(av,'zh');
      });
      ascending=!ascending;
      sorted.forEach(function(row){body.appendChild(row);});
      apply();
    });
  });
})();
"""


def build_html(
    sections: dict[str, Any],
    derived: dict[str, Any],
    signals: list[dict[str, str]],
    input_sha256: str,
) -> str:
    map_panel = _map_panel(derived)
    content = (
        _framework(derived)
        + _archetype_panel(derived)
        + _matrix_panel(derived)
        + _sector_panel(derived)
        + map_panel
        + _detail_panel(derived)
        + _method_panel(derived, signals)
    )
    overview = derived["overview"]
    as_of = sections["as_of"]
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<meta name="robots" content="noindex,nofollow" />
<title>个股股性画像 · {_esc(as_of)}</title><style>
:root{{}}
{STYLE}
</style></head><body><main>
<header class="masthead"><div><p class="eyebrow">A-SHARE / STOCK PERSONALITY</p><h1>个股股性画像</h1></div>
<p class="asof">信息截止 {_esc(as_of)}<br />窗口 {_esc(overview["window_start"])} ~ {_esc(overview["window_end"])}<br />
池内 {overview["total"]} 只 · 容量口径 {_esc(overview["capacity_metric"])}<br />输入指纹 {_esc(input_sha256[:12])}</p></header>
<p class="lede">把一只股票过去一段时间的交易行为统计成六维指标与原型标签，用于板块与情绪的结构归因。原型是结构分类，不是评级。</p>
{_hero(derived)}
{content}
{_source_panel(sections.get("sources") or [])}
<footer>{_esc(DISCLAIMER)}</footer>
</main><script>{SCRIPT}</script></body></html>'''


def build_markdown(
    sections: dict[str, Any],
    derived: dict[str, Any],
    signals: list[dict[str, str]],
    input_sha256: str,
) -> str:
    overview = derived["overview"]
    lines = [
        f"# 个股股性画像｜{sections['as_of']}",
        "",
        f"- 窗口：{overview['window_start']} ~ {overview['window_end']}（{overview['trading_days']} 个交易日）",
        f"- 池内标的：{overview['total']} 只（六维齐全 {overview['scored']} 只）",
        f"- 容量口径：{overview['capacity_metric']}",
        f"- 平均股性分：{overview['mean_composite']}",
        f"- 平均埋人率：{overview['mean_bury_rate_pct']}%",
        f"- 输入SHA-256：`{input_sha256}`",
        f"- 结论属性：{DISCLAIMER}",
        "",
        "## 股性原型分布",
        "",
        "| 原型 | 只数 | 占比 | 平均股性分 | 平均次日溢价 | 平均埋人率 |",
        "|---|---|---|---|---|---|",
    ]
    for row in derived["archetype_table"]:
        if row["count"] == 0:
            continue
        lines.append(
            f"| {row['label']} | {row['count']} | {row['share_pct']}% | {row['mean_composite']} | "
            f"{row['mean_next_day_pct']} | {row['mean_bury_rate_pct']}% |"
        )
    lines.extend(["", "## 板块 × 股性 排序", "", "| 板块 | 只数 | 平均股性分 | 平均次日溢价 | 平均埋人率 |", "|---|---|---|---|---|"])
    for item in derived["sector_table"]:
        if item["mean_composite"] is None:
            continue
        lines.append(
            f"| {item['sector']} | {item['count']} | {item['mean_composite']} | "
            f"{item['mean_next_day_pct']} | {item['mean_bury_rate_pct']}% |"
        )
    lines.extend(["", "## 股性地图象限分布", ""])
    for key, label in QUADRANT_LABELS.items():
        lines.append(f"- {label}：{derived['map']['quadrant_counts'].get(key, 0)} 只")
    lines.extend(["", "## 结构信号与限制", ""])
    for signal in signals:
        lines.append(f"- **{signal['kind']}**：{signal['text']}（证据：{signal['evidence']}）")
    lines.append("")
    for note in derived["caveats"]:
        lines.append(f"- 限制：{note}")
    lines.append("")
    return "\n".join(lines)
