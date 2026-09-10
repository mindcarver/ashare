#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 show / stats 的结构化结果渲染成自包含 HTML 报告。

沿用 P2-5 纪律：模板与组件样式在 page_template.py，本文件只做「数据 → HTML」的组装，
末尾由 ashare_shared.inject_shared_css() 注入共享设计令牌与页面外壳。

关于禁词门禁（本技能与另外四个生成器不同，理由见 SKILL.md 第五节）：
报告逐字引用用户当时冻结的研究文本（假设 / 催化剂 / 证伪条件），审查性引用不能改写，
因此**不设禁词硬门禁**，改用固定的「报告性质」声明：本报告是事后复盘与历史统计，
不是投资建议，也不代表未来能力。
"""
import json
import re
from html import escape

import _paths  # noqa: F401  确保 skills/_shared 在 sys.path 上
from ashare_shared import inject_shared_css

from page_template import COMMON_CSS, PAGE_TEMPLATE, RECORD_CSS, STATS_CSS

METRIC_LABEL = {
    "stock_return_pct": "股票区间收益",
    "benchmark_return_pct": "基准区间收益",
    "excess_return_pct": "相对基准超额",
    "max_drawdown_pct": "最大回撤",
    "max_favorable_excursion_pct": "最大有利偏离 MFE",
    "max_adverse_excursion_pct": "最大不利偏离 MAE",
}
OPERATOR_LABEL = {"lt": "<", "lte": "≤", "gt": ">", "gte": "≥", "eq": "=", "ne": "≠"}

RECORD_FOOT = (
    "本报告为研究结论的事后复盘：快照与结果写入后不可覆盖；引用文字来自当时冻结的"
    "研究记录，未作改写。报告不构成投资建议，也不预测未来表现。"
)
STATS_FOOT = (
    "统计结果描述历史样本，不代表未来能力。样本量、行业集中、市场阶段与选择偏差"
    "必须与数值同时阅读。报告不构成投资建议。"
)

_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")


# ============ 格式化助手 ============
def _pct(value, digits=2):
    """不带符号的百分比（用于比例类指标）。"""
    return "—" if value is None else f"{float(value):.{digits}f}%"


def _pct_signed(value, digits=2):
    """带符号的百分比（用于收益、回撤等有方向的数值）。"""
    return "—" if value is None else f"{float(value):+.{digits}f}%"


def _num(value, digits=4):
    return "—" if value is None else f"{float(value):.{digits}f}"


def _direction_class(value):
    """A 股口径：正数用红（--red），负数用绿（--green）。"""
    if value is None:
        return ""
    number = float(value)
    return "pos" if number > 0 else ("neg" if number < 0 else "")


def _e(value):
    return escape(str(value), quote=True)


def _badge(text, kind):
    return f'<span class="badge {kind}">{_e(text)}</span>'


def _tile(label, value, sub="", tone=""):
    tone_cls = f" {tone}" if tone else ""
    sub_html = f'<div class="t-sub">{_e(sub)}</div>' if sub else ""
    return (f'<div class="tile"><div class="t-label">{_e(label)}</div>'
            f'<div class="t-value{tone_cls}">{value}</div>{sub_html}</div>')


def _json_for_script(payload):
    """内联进 <script> 的 JSON：转义 < 以免出现 </script> 提前收尾。"""
    return json.dumps(payload, ensure_ascii=False).replace("<", "\\u003c")


# ============ 整页组装 ============
def _page(*, title, desc, eyebrow, h1, asof_line, lede, body, script, report_css, foot):
    html = (PAGE_TEMPLATE
            .replace("{{PAGE_TITLE}}", _e(title))
            .replace("{{PAGE_DESC}}", _e(desc))
            .replace("{{EYEBROW}}", _e(eyebrow))
            .replace("{{H1}}", _e(h1))
            .replace("{{ASOF_LINE}}", asof_line)
            .replace("{{LEDE}}", _e(lede))
            .replace("{{COMMON_CSS}}", COMMON_CSS)
            .replace("{{REPORT_CSS}}", report_css)
            .replace("{{BODY}}", body)
            .replace("{{FOOT}}", _e(foot))
            .replace("{{SCRIPT}}", script))
    leftover = _PLACEHOLDER_RE.search(html)
    if leftover:
        raise RuntimeError(f"HTML 模板仍有未替换占位符：{leftover.group(0)}")
    return inject_shared_css(html)


def _render_card(title, inner, kind=""):
    kind_cls = f" {kind}" if kind else ""
    return f'  <section class="card{kind_cls}">\n    <h2 class="card-title">{_e(title)}</h2>\n{inner}\n  </section>'


def _kv_list(rows):
    items = "".join(f"      <dt>{_e(k)}</dt><dd>{_e(v)}</dd>\n" for k, v in rows)
    return f'    <dl class="kv">\n{items}    </dl>'


def _bullet_list(items, dim=False):
    cls = "list dim" if dim else "list"
    lis = "".join(f"      <li>{_e(item)}</li>\n" for item in items)
    return f'    <ul class="{cls}">\n{lis}    </ul>'


# ============ 单条复盘 ============
def _align_paths(stock_path, benchmark_path):
    """把个股与基准路径对齐到同一日期轴，缺失点用 None 占位。"""
    dates = sorted({point["observed_at"] for point in stock_path}
                   | {point["observed_at"] for point in benchmark_path})

    def series(path):
        lookup = {point["observed_at"]: float(point["value"]) for point in path}
        return [lookup.get(day) for day in dates]

    return dates, series(stock_path), (series(benchmark_path) if benchmark_path else None)


def _path_chart(outcome_input):
    stock_path = outcome_input.get("stock_path") or []
    benchmark_path = outcome_input.get("benchmark_path") or []
    if len(stock_path) < 2:
        return ""
    dates, stock_values, benchmark_values = _align_paths(stock_path, benchmark_path)
    unit = stock_path[0].get("unit", "")
    payload = {
        "dates": dates,
        "unit": unit,
        "stock": stock_values,
        "benchmark": benchmark_values,
        "benchmarkName": "基准",
    }
    return (
        '    <div class="chart" id="ch-path"></div>\n'
        '    <script>\n'
        f'const PATH = {_json_for_script(payload)};\n'
        "const inkColor = '#111417', accentColor = '#1b39d8',\n"
        "      secColor = '#4b5158', terColor = '#7d838a', gridColor = '#c9c6c0';\n"
        "(function(){\n"
        "  const el = document.getElementById('ch-path');\n"
        "  if (!el || typeof echarts === 'undefined') return;\n"
        "  const chart = echarts.init(el);\n"
        "  const series = [{ name: '个股', type: 'line', data: PATH.stock, smooth: true,\n"
        "      symbol: 'circle', symbolSize: 6, connectNulls: true,\n"
        "      lineStyle: { color: inkColor, width: 2 }, itemStyle: { color: inkColor } }];\n"
        "  if (PATH.benchmark) {\n"
        "    series.push({ name: PATH.benchmarkName, type: 'line', data: PATH.benchmark,\n"
        "      smooth: true, symbol: 'circle', symbolSize: 5, connectNulls: true,\n"
        "      lineStyle: { color: accentColor, width: 2, type: 'dashed' }, itemStyle: { color: accentColor } });\n"
        "  }\n"
        "  chart.setOption({\n"
        "    tooltip: { trigger: 'axis',\n"
        "      formatter: function(ps){ return ps[0].axisValue + '<br/>' + ps.map(function(p){\n"
        "        return p.marker + p.seriesName + '：' + (p.value === null || p.value === undefined ? '—' : p.value + ' ' + PATH.unit); }).join('<br/>'); } },\n"
        "    legend: { data: series.map(function(s){ return s.name; }), textStyle: { color: secColor, fontSize: 10 }, top: 0 },\n"
        "    grid: { left: 52, right: 16, top: 34, bottom: 26 },\n"
        "    xAxis: { type: 'category', data: PATH.dates, boundaryGap: false,\n"
        "      axisLine: { lineStyle: { color: secColor } }, axisTick: { show: false },\n"
        "      axisLabel: { color: terColor, fontSize: 9 } },\n"
        "    yAxis: { type: 'value', scale: true, axisLabel: { color: terColor, fontSize: 9 },\n"
        "      splitLine: { lineStyle: { color: gridColor } } },\n"
        "    series: series\n"
        "  });\n"
        "  window.addEventListener('resize', function(){ chart.resize(); });\n"
        "})();\n"
        "    </script>"
    )


def _metrics_table(metrics):
    rows = []
    for key, label, scope in (
        ("stock_return_pct", "股票收益", "区间收益（路径首末）"),
        ("benchmark_return_pct", "基准收益", "区间收益（路径首末）"),
        ("excess_return_pct", "超额收益", "股票 − 基准"),
        ("max_drawdown_pct", "最大回撤", "输入路径覆盖"),
        ("max_favorable_excursion_pct", "MFE", "相对基线最大有利偏离"),
        ("max_adverse_excursion_pct", "MAE", "相对基线最大不利偏离"),
    ):
        value = metrics.get(key)
        tone = _direction_class(value)
        rows.append(f'      <tr><td>{_e(label)}</td>'
                    f'<td class="num {tone}">{_pct_signed(value)}</td>'
                    f'<td>{_e(scope)}</td></tr>')
    return ('    <table class="tbl">\n      <thead><tr><th>指标</th><th class="num">结果</th>'
            '<th>口径</th></tr></thead>\n    <tbody>\n' + "\n".join(rows) + "\n    </tbody>\n    </table>")


def _evidence_table(evidence):
    if not evidence:
        return '    <p class="list dim">快照未记录证据条目。</p>'
    rows = []
    for item in evidence:
        source = item.get("source") or {}
        value = item.get("value")
        if value is None:
            shown = "—"
        else:
            shown = f'{value} {_e(item.get("unit", ""))}'.strip()
        rows.append(
            f'      <tr><td>{_e(item.get("claim", ""))}</td>'
            f'<td class="num">{shown}</td>'
            f'<td class="mono">{_e(item.get("observed_at", ""))}</td>'
            f'<td class="mono">{_e(item.get("published_at", ""))}</td>'
            f'<td class="src">{_e(source.get("name", ""))}<br />{_e(source.get("url", ""))}</td></tr>'
        )
    return ('    <table class="tbl">\n      <thead><tr><th>论断</th><th class="num">取值</th>'
            '<th>观察日</th><th>发布日</th><th>来源</th></tr></thead>\n    <tbody>\n'
            + "\n".join(rows) + "\n    </tbody>\n    </table>")


def render_record(record):
    """单条研究的完整复盘报告。record 即 derive.show() 的返回结构。"""
    snapshot = record["snapshot"]
    outcome = record.get("outcome")
    criterion = snapshot["criterion"]

    meta_rows = [
        ("Research ID", snapshot["research_id"]),
        ("标的", f'{snapshot["name"]}（{snapshot["code"]} · {snapshot["market"]}）'),
        ("研究截止日 as_of", snapshot["as_of"]),
        ("评价日 evaluation_date", snapshot["evaluation_date"]),
        ("持有期标签", snapshot["horizon_label"]),
        ("原快照 SHA-256", record["snapshot_sha256"]),
        ("记录时间", record["recorded_at"]),
    ]
    if outcome:
        meta_rows.append(("结果输入 SHA-256", outcome["outcome_sha256"]))
    meta_card = _render_card("记录标识与不可变性", _kv_list(meta_rows))

    probability = snapshot.get("probability")
    judge_rows = [
        ('研究假设', f'<p class="judge">{_e(snapshot["thesis"])}</p>'),
        ('当时概率', f'<p class="judge">{_pct(probability * 100) if probability is not None else "未提供"}</p>'),
    ]
    judge_inner = "\n".join(f'    <p class="judge"><b>{title}</b></p>\n{html}'
                            for title, html in judge_rows)
    criterion_text = (f'{METRIC_LABEL.get(criterion["metric"], criterion["metric"])} '
                      f'{OPERATOR_LABEL.get(criterion["operator"], criterion["operator"])} '
                      f'{criterion["value"]}')
    judge_inner += f'\n    <p class="judge" style="margin-top:0.5rem"><b>成功标准</b></p>\n    <div class="crit">{_e(criterion_text)}</div>'
    judge_inner += f'\n    <p class="judge" style="margin-top:0.75rem"><b>催化剂</b></p>\n{_bullet_list(snapshot["catalysts"])}'
    judge_inner += f'\n    <p class="judge" style="margin-top:0.75rem"><b>证伪条件</b></p>\n{_bullet_list(snapshot["falsifiers"])}'
    judge_card = _render_card("当时判断（冻结原文，未改写）", judge_inner)

    evidence_card = _render_card("当时证据", _evidence_table(snapshot.get("evidence") or []))

    if outcome:
        metrics = outcome["metrics"]
        tiles = ('    <div class="tiles">\n'
                 + _tile("股票区间收益", _pct_signed(metrics.get("stock_return_pct")),
                         tone=_direction_class(metrics.get("stock_return_pct")))
                 + _tile("相对基准超额", _pct_signed(metrics.get("excess_return_pct")),
                         tone=_direction_class(metrics.get("excess_return_pct")))
                 + _tile("最大回撤", _pct_signed(metrics.get("max_drawdown_pct")),
                         tone=_direction_class(metrics.get("max_drawdown_pct")))
                 + _tile("MFE / MAE",
                         f'{_pct_signed(metrics.get("max_favorable_excursion_pct"), 1)} / '
                         f'{_pct_signed(metrics.get("max_adverse_excursion_pct"), 1)}')
                 + "\n    </div>")
        outcome_card = _render_card("到期结果", tiles + "\n" + _metrics_table(metrics) + "\n" + _path_chart(outcome["input"]),
                                    kind="pass" if metrics.get("passed") else "fail")
    else:
        outcome_card = _render_card(
            "到期结果",
            '    <p class="verdict"><span class="dot wait"></span>尚未到期复核</p>\n'
            '    <p class="judge">该记录已到评价日但尚未写入结果，或评价日尚未到达。'
            '未写入结果前不产生任何评分。</p>',
            kind="wait",
        )

    if outcome:
        metrics = outcome["metrics"]
        triggered = outcome["input"].get("falsifiers_triggered") or []
        verdict = ("<span class=\"dot ok\"></span>成功标准通过且未触发证伪条件 → passed"
                   if metrics.get("passed")
                   else "<span class=\"dot no\"></span>未通过（成功标准未达成或触发了证伪条件）")
        audit_inner = (
            f'    <p class="verdict">{verdict}</p>\n'
            '    <div class="tiles">\n'
            + _tile("成功标准达成", "是" if metrics.get("criterion_passed") else "否")
            + _tile("触发证伪条件", "是" if metrics.get("falsifier_triggered") else "否")
            + _tile("最终 passed", "是" if metrics.get("passed") else "否")
            + "\n    </div>"
        )
        if triggered:
            audit_inner += f'\n    <p class="judge" style="margin-top:0.75rem"><b>已触发的证伪条件</b></p>\n{_bullet_list(triggered)}'
        notes = outcome["input"].get("notes")
        if notes:
            audit_inner += f'\n    <div class="note">结果输入备注：{_e(notes)}</div>'
        audit_inner += ('\n    <div class="note">剩余定性归因（逻辑兑现 / 市场贝塔 / 风格 / 其他）'
                        '与流程改进由复盘人在正文中给出——一次结果不构成普遍规律。</div>')
        audit_card = _render_card("判断审计", audit_inner)
    else:
        audit_card = ""

    cards = [meta_card, judge_card, evidence_card, outcome_card]
    if audit_card:
        cards.append(audit_card)
    body = "\n\n".join(cards)

    passed = outcome["metrics"].get("passed") if outcome else None
    if outcome is None:
        lede = f'{snapshot["name"]} 的研究结论尚未进入到期复核：以下为当时冻结的判断与证据。'
    elif passed:
        lede = f'{snapshot["name"]} 的研究结论已到期复核：成功标准达成且未触发证伪条件。'
    else:
        lede = f'{snapshot["name"]} 的研究结论已到期复核：未通过成功标准或触发了证伪条件。'

    return _page(
        title=f'{snapshot["name"]} 研究结论事后复盘 · {snapshot["research_id"]}',
        desc="A股研究结论的事后复盘：冻结快照、到期表现与判断审计（本地研究工具）",
        eyebrow="A-SHARE / RESEARCH JOURNAL REVIEW",
        h1="研究结论事后复盘",
        asof_line=(f'{_e(snapshot["name"])}（{_e(snapshot["code"])}）<br />'
                   f'研究截止 {_e(snapshot["as_of"])} · 评价日 {_e(snapshot["evaluation_date"])}'),
        lede=lede,
        body=body,
        script="",
        report_css=RECORD_CSS,
        foot=RECORD_FOOT,
    )


# ============ 统计看板 ============
def _stats_script(stats):
    payload = {
        "hitRate": stats.get("hit_rate_pct"),
        "records": [
            {
                "label": record["name"] or record["code"],
                "id": record["research_id"],
                "excess": record.get("excess_return_pct"),
                "probability": record.get("probability"),
                "passed": 1 if record.get("passed") else 0,
                "date": record.get("evaluation_date"),
            }
            for record in stats.get("records", [])
        ],
    }
    return (
        f'const STATS = {_json_for_script(payload)};\n'
        "const inkColor = '#111417', secColor = '#4b5158', terColor = '#7d838a',\n"
        "      gridColor = '#c9c6c0', accentColor = '#1b39d8',\n"
        "      gainColor = '#d2231b', lossColor = '#0e7a45';\n"
        "(function(){\n"
        "  if (typeof echarts === 'undefined') return;\n"
        "  const charts = [];\n"
        "  function mount(id, option){\n"
        "    const el = document.getElementById(id);\n"
        "    if (!el) return;\n"
        "    const chart = echarts.init(el);\n"
        "    chart.setOption(option);\n"
        "    charts.push(chart);\n"
        "  }\n"
        "  if (STATS.hitRate !== null && STATS.hitRate !== undefined) {\n"
        "    mount('ch-hit', {\n"
        "      series: [{\n"
        "        type: 'gauge', startAngle: 210, endAngle: -30, min: 0, max: 100,\n"
        "        radius: '95%', center: ['50%','60%'],\n"
        "        axisLine: { lineStyle: { width: 14, color: [[1, gridColor]] } },\n"
        "        progress: { show: true, width: 14, itemStyle: { color: accentColor } },\n"
        "        pointer: { itemStyle: { color: inkColor }, length: '58%', width: 4 },\n"
        "        axisTick: { distance: -16, length: 3, lineStyle: { color: '#fff', width: 1 } },\n"
        "        splitLine: { distance: -18, length: 10, lineStyle: { color: '#fff', width: 2 } },\n"
        "        axisLabel: { distance: 20, color: terColor, fontSize: 9 },\n"
        "        title: { offsetCenter: [0, '74%'], fontSize: 10, color: secColor },\n"
        "        detail: { valueAnimation: true, formatter: '{value}%', color: inkColor,\n"
        "          fontSize: 22, fontWeight: 600, offsetCenter: [0, '36%'] },\n"
        "        data: [{ value: STATS.hitRate, name: '命中率' }]\n"
        "      }]\n"
        "    });\n"
        "  }\n"
        "  const withExcess = STATS.records.filter(function(r){ return r.excess !== null && r.excess !== undefined; });\n"
        "  if (withExcess.length) {\n"
        "    const showLabel = withExcess.length <= 12;\n"
        "    mount('ch-excess', {\n"
        "      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' },\n"
        "        formatter: function(ps){ const r = withExcess[ps[0].dataIndex];\n"
        "          return r.label + '<br/>' + r.id + '<br/>超额：' + r.excess + '%<br/>' + (r.passed ? '通过' : '未通过'); } },\n"
        "      grid: { left: 52, right: 16, top: 22, bottom: 62 },\n"
        "      xAxis: { type: 'category', data: withExcess.map(function(r){ return r.label; }),\n"
        "        axisLabel: { color: terColor, fontSize: 9, rotate: 38, interval: 0 },\n"
        "        axisTick: { show: false }, axisLine: { lineStyle: { color: secColor } } },\n"
        "      yAxis: { type: 'value', name: '超额 %', nameTextStyle: { color: terColor, fontSize: 9 },\n"
        "        axisLabel: { color: terColor, fontSize: 9 }, splitLine: { lineStyle: { color: gridColor } } },\n"
        "      series: [{ type: 'bar', barWidth: '52%',\n"
        "        data: withExcess.map(function(r){ return { value: r.excess,\n"
        "          itemStyle: { color: r.excess >= 0 ? gainColor : lossColor, borderRadius: [3,3,0,0] } }; }),\n"
        "        label: { show: showLabel, position: 'top', color: inkColor, fontSize: 9, fontWeight: 600,\n"
        "          formatter: function(p){ return p.value + '%'; } } }]\n"
        "    });\n"
        "  }\n"
        "  const withProb = STATS.records.filter(function(r){ return r.probability !== null && r.probability !== undefined; });\n"
        "  if (withProb.length) {\n"
        "    mount('ch-calibration', {\n"
        "      tooltip: { formatter: function(p){ const r = withProb[p.dataIndex];\n"
        "        return r.label + '<br/>' + r.id + '<br/>当时概率：' + r.probability + '<br/>实际：' + (r.passed ? '通过' : '未通过'); } },\n"
        "      grid: { left: 66, right: 20, top: 22, bottom: 34 },\n"
        "      xAxis: { type: 'value', min: 0, max: 1, name: '当时概率', nameLocation: 'middle', nameGap: 24,\n"
        "        nameTextStyle: { color: terColor, fontSize: 9 },\n"
        "        axisLabel: { color: terColor, fontSize: 9 }, splitLine: { lineStyle: { color: gridColor } } },\n"
        "      yAxis: { type: 'value', min: -0.08, max: 1.08, name: '实际结果', nameLocation: 'middle', nameGap: 34,\n"
        "        nameTextStyle: { color: terColor, fontSize: 9 },\n"
        "        axisLabel: { color: terColor, fontSize: 9,\n"
        "          formatter: function(v){ return v === 1 ? '通过' : (v === 0 ? '未通过' : ''); } },\n"
        "        splitLine: { lineStyle: { color: gridColor } } },\n"
        "      series: [\n"
        "        { type: 'line', data: [[0,0],[1,1]], symbol: 'none', silent: true,\n"
        "          lineStyle: { color: terColor, type: 'dashed', width: 1 } },\n"
        "        { type: 'scatter', symbolSize: 11, itemStyle: { color: accentColor },\n"
        "          data: withProb.map(function(r){ return [r.probability, r.passed]; }) }\n"
        "      ]\n"
        "    });\n"
        "  }\n"
        "  window.addEventListener('resize', function(){ charts.forEach(function(c){ c.resize(); }); });\n"
        "})();"
    )


def _stats_table(records):
    rows = []
    for record in records:
        excess = record.get("excess_return_pct")
        stock = record.get("stock_return_pct")
        drawdown = record.get("max_drawdown_pct")
        probability = record.get("probability")
        verdict = ('<span class="badge b-pass">通过</span>' if record.get("passed")
                   else '<span class="badge b-fail">未通过</span>')
        rows.append(
            f'      <tr><td class="mono">{_e(record["research_id"])}</td>'
            f'<td>{_e(record["name"])}<br /><span class="src">{_e(record["code"])}</span></td>'
            f'<td class="mono">{_e(record["evaluation_date"])}</td>'
            f'<td class="num">{_pct(probability * 100) if probability is not None else "—"}</td>'
            f'<td class="num {_direction_class(stock)}">{_pct_signed(stock)}</td>'
            f'<td class="num {_direction_class(excess)}">{_pct_signed(excess)}</td>'
            f'<td class="num {_direction_class(drawdown)}">{_pct_signed(drawdown)}</td>'
            f'<td>{verdict}</td></tr>'
        )
    return ('    <table class="tbl">\n      <thead><tr><th>Research ID</th><th>标的</th>'
            '<th>评价日</th><th class="num">当时概率</th><th class="num">股票收益</th>'
            '<th class="num">超额</th><th class="num">最大回撤</th><th>判定</th></tr></thead>\n'
            '    <tbody>\n' + "\n".join(rows) + "\n    </tbody>\n    </table>")


def render_stats(stats):
    """已成熟样本的统计看板。stats 即 derive.stats() 的返回结构。"""
    matured = stats.get("matured_count", 0)
    code = stats.get("code")
    scope = f'（限定代码 {code}）' if code else '（全部标的）'
    as_of = stats["as_of"]

    title = f'研究结论命中率统计 · 截至 {as_of}'
    desc = "A股研究结论的事后统计看板：命中率、超额分布与概率校准（本地研究工具）"

    if not matured:
        body = (
            '  <div class="empty">截至该日期没有已成熟且已写入结果的研究记录。'
            '统计只使用到期并已复核的样本。</div>\n\n'
            + _render_card(
                "口径说明",
                '    <ul class="list">\n'
                '      <li>统计只纳入 evaluation_date ≤ 截止日且已写入结果的记录。</li>\n'
                '      <li>未到期的记录不参与，未写入结果的记录不参与，二者都不计为失败。</li>\n'
                '      <li>Brier 分数只使用提供了 probability 的记录作为分母。</li>\n'
                '    </ul>',
            )
        )
        return _page(
            title=title, desc=desc,
            eyebrow="A-SHARE / RESEARCH JOURNAL STATS",
            h1="命中率统计",
            asof_line=f'截至 {_e(as_of)}<br />{_e(scope)}<br />无成熟样本',
            lede="当前没有可统计的成熟样本。",
            body=body, script="", report_css=STATS_CSS, foot=STATS_FOOT,
        )

    calibrated = stats.get("calibrated_count") or 0
    tiles = ('    <div class="tiles">\n'
             + _tile("成熟样本", str(matured), sub=f'{_e(scope)}')
             + _tile("命中数", str(stats.get("passed_count", 0)))
             + _tile("命中率", _pct(stats.get("hit_rate_pct"), 1))
             + _tile("Brier 分数", _num(stats.get("brier_score"), 4),
                     sub=f'校准分母 {calibrated} 条' if calibrated else "无提供概率的记录")
             + _tile("平均股票收益", _pct_signed(stats.get("avg_stock_return_pct")),
                     tone=_direction_class(stats.get("avg_stock_return_pct")))
             + _tile("平均超额", _pct_signed(stats.get("avg_excess_return_pct")),
                     tone=_direction_class(stats.get("avg_excess_return_pct")))
             + _tile("平均最大回撤", _pct_signed(stats.get("avg_max_drawdown_pct")),
                     tone=_direction_class(stats.get("avg_max_drawdown_pct")))
             + "\n    </div>")

    charts = ('    <div class="chart-grid two">\n'
              '      <div class="chart" id="ch-hit"></div>\n'
              '      <div class="chart" id="ch-excess"></div>\n'
              '    </div>\n'
              '    <div class="chart tall" id="ch-calibration"></div>\n'
              '    <div class="note">超额分布按 Research ID 排序，红=正超额、绿=负超额（A 股口径）。'
              'Brier 分数 = 平均（当时概率 − 实际结果）²，越小越接近校准；'
              '虚线为「概率=实际」的完美校准线，散点越贴近虚线校准越好。</div>')

    aggregate_card = _render_card("总体指标", tiles + "\n" + charts)
    detail_card = _render_card("逐条明细", _stats_table(stats.get("records", [])))
    caveat_card = _render_card(
        "必须同时阅读的限定",
        '    <ul class="list">\n'
        f'      <li>样本量：本次仅 {matured} 条成熟记录，'
        + ('任何比例都接近噪声，不要据此推断能力。' if matured < 20 else '仍不足以代表全市场。')
        + '</li>\n'
        '      <li>行业集中：记录来自主观选题，行业分布未经加权。</li>\n'
        '      <li>市场阶段：所有样本落在同一市场阶段时，结果很大程度上是阶段收益。</li>\n'
        '      <li>选择偏差：只有被记录下来的研究进入样本，未记录的研究不在分母里。</li>\n'
        '      <li>命中率不等于赚钱：成功标准可以是任意指标，且未计入仓位与成本。</li>\n'
        '    </ul>'
        + '\n    <div class="note">统计结果描述历史样本，不代表未来能力。</div>',
    )

    body = "\n\n".join([aggregate_card, detail_card, caveat_card])
    lede = f'截至 {as_of} 共 {matured} 条成熟样本{scope}，命中 {stats.get("passed_count", 0)} 条。'

    return _page(
        title=title, desc=desc,
        eyebrow="A-SHARE / RESEARCH JOURNAL STATS",
        h1="命中率统计",
        asof_line=f'截至 {_e(as_of)}<br />{_e(scope)}<br />成熟样本 {matured} 条',
        lede=lede,
        body=body,
        script=_stats_script(stats),
        report_css=STATS_CSS,
        foot=STATS_FOOT,
    )
