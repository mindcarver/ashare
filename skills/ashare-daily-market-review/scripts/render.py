#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Markdown 与 HTML 渲染（拆分自 generate_daily_review.py，审计 P2-5）。

1.2 分析层（延续性检验、双确认主线矩阵、阈值体检）的渲染片段在
`render_analysis.py`；本模块只保留八个基础章节与整体骨架。
"""

from typing import Any

from formatting import (
    availability_badge,
    fmt_evidence,
    fmt_flow_cny,
    fmt_history_value,
    fmt_signed_pct,
    html_evidence,
    html_metric_card,
    html_text,
    unknown_line,
    value_tone,
)
from render_analysis import (
    html_concept_flows,
    html_health_check,
    html_high_boards,
    html_mainline,
    html_prev_pool,
    html_sector_leaders,
    html_streak_distribution,
    markdown_concept_flows,
    markdown_health_check,
    markdown_high_boards,
    markdown_mainline,
    markdown_prev_pool,
    markdown_sector_leaders,
    markdown_streak_distribution,
)
from schema import FORBIDDEN, ReviewError, SECTION_NAMES


def build_html(
    data: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    input_sha256: str,
    derived: dict[str, Any],
    signals: list[dict[str, str]],
    coverage_counts: dict[str, int],
    sources: list[dict[str, Any]],
    history: dict[str, Any],
    resolved_verifications: list[dict[str, Any]],
) -> str:
    """Build a self-contained visual report from the same validated evidence."""
    indices = sections["indices"]
    breadth = sections["breadth"]
    turnover = sections["turnover"]
    sectors = sections["sectors"]
    sentiment_section = sections["short_term_sentiment"]
    sentiment = derived["short_term_sentiment"]

    primary = None
    if indices["availability"] != "unknown":
        primary = next(item for item in indices["items"] if item["primary"])
    primary_change = float(primary["change_pct"]["value"]) if primary else None
    amount = turnover.get("metrics", {}).get("amount")
    metrics = breadth.get("metrics", {})
    advance_share = derived.get("advancer_share_pct")

    hero_cards = []
    if primary:
        hero_cards.append(html_metric_card(
            primary["name"], fmt_evidence(primary["close"]), fmt_evidence(primary["change_pct"]), value_tone(primary_change)
        ))
    if amount:
        hero_cards.append(html_metric_card(
            "全市场成交额", fmt_evidence(amount),
            f"较前值 {derived['turnover_vs_previous_pct']:+.2f}%" if "turnover_vs_previous_pct" in derived else turnover["status_reason"],
            value_tone(derived.get("turnover_vs_previous_pct")),
        ))
    if advance_share is not None:
        hero_cards.append(html_metric_card("上涨参与度", f"{advance_share:.2f}%", "上涨家数占总样本", value_tone(advance_share - 50)))
    if "limit_balance" in derived:
        hero_cards.append(html_metric_card("涨停净差", f"{derived['limit_balance']:+.0f}", "涨停家数减跌停家数", value_tone(derived["limit_balance"])))
    if not hero_cards:
        hero_cards.append(html_metric_card("市场脉搏", "未知", "缺少可得的盘面核心数据"))

    index_rows = ""
    if indices["availability"] == "unknown":
        index_rows = f'<p class="empty">{html_text(indices["status_reason"])}</p>'
    else:
        index_rows = "".join(
            f'''<div class="index-row"><span>{html_text(item["name"])}</span>
<strong>{html_text(fmt_evidence(item["close"]))}</strong>
<b class="value-{value_tone(float(item["change_pct"]["value"]))}">{html_text(fmt_evidence(item["change_pct"]))}</b>
<small>{html_evidence(item["change_pct"])}</small></div>'''
            for item in indices["items"]
        )

    breadth_chart = '<p class="empty">宽度数据不可得</p>'
    if advance_share is not None:
        breadth_chart = f'''<div class="breadth-wrap">
  <div class="donut" style="--advance:{advance_share:.4f}%"><span>{advance_share:.1f}%<small>上涨</small></span></div>
  <div class="breadth-list">
    <p><span>上涨</span><strong>{metrics["advancers"]["value"]:,}</strong></p>
    <p><span>下跌</span><strong>{metrics["decliners"]["value"]:,}</strong></p>
    <p><span>平盘</span><strong>{metrics["unchanged"]["value"]:,}</strong></p>
    <p><span>涨停 / 跌停</span><strong>{metrics["limit_up"]["value"]:,} / {metrics["limit_down"]["value"]:,}</strong></p>
  </div>
</div>'''

    state_labels = {"ice": "冰点", "euphoria": "亢奋", "divergence": "分歧", "repair": "修复", "neutral": "中性", "unknown": "未知"}
    if sentiment["state"] == "unknown":
        sentiment_html = f'<p class="empty">短线情绪未知：{html_text(sentiment["reason"])}</p>'
    else:
        sentiment_cards = [
            ("炸板率", f"{sentiment['open_board_rate_pct']:.2f}%"),
            ("最高连板", fmt_evidence(sentiment_section["metrics"]["highest_streak"])),
        ]
        if "limit_balance" in derived:
            sentiment_cards.append(("涨停净差", f"{derived['limit_balance']:+.0f}"))
        cards = "".join(
            f'<div><span>{html_text(label)}</span><strong>{html_text(number)}</strong></div>'
            for label, number in sentiment_cards
        )
        sentiment_html = f'''<div class="sentiment-state state-{html_text(sentiment["state"])}">
  <span>市场状态</span><strong>{state_labels[sentiment["state"]]}</strong>
</div><p class="rule">{html_text(sentiment["evidence"])}</p>
<div class="sentiment-kpis">{cards}</div>
<details class="method-details"><summary>查看股票池、口径与规则</summary><p class="evidence">股票池：{html_text(sentiment_section["universe"]["label"])}（{html_text(sentiment_section["universe"]["id"])}）<br />{html_text(sentiment_section["methodology"])}<br />规则：<code>{html_text(sentiment["rule"])}</code></p></details>'''

    ladder = derived.get("streak_distribution")
    if ladder:
        sentiment_html += html_streak_distribution(ladder)
    quality = derived.get("high_board_quality")
    if quality:
        sentiment_html += html_high_boards(quality)

    health = derived.get("sentiment_health_check")
    if health:
        sentiment_html += html_health_check(health)

    prev_pool_html = html_prev_pool(
        derived.get("prev_pool_performance"),
        sections["prev_pool_performance"],
        data["market_date"],
    )

    mainline_html = html_mainline(
        derived.get("mainline_matrix"), sections["mainline_matrix"]
    )

    sector_html = f'<p class="empty">{html_text(sectors["status_reason"])}</p>'
    if sectors["availability"] != "unknown":
        ordered = sorted(sectors["items"], key=lambda item: (-float(item["change_pct"]["value"]), item["id"]))
        max_change = max(abs(float(item["change_pct"]["value"])) for item in ordered) or 1
        winners = ordered[:10]
        losers = sorted(ordered, key=lambda item: (float(item["change_pct"]["value"]), item["id"]))[:10]

        def sector_rows(items: list[dict[str, Any]]) -> str:
            rows = []
            for item in items:
                change = float(item["change_pct"]["value"])
                width = abs(change) / max_change * 100
                side = "positive" if change >= 0 else "negative"
                rows.append(f'''<div class="sector-row"><span>{html_text(item["name"])}</span><div class="bar-track {side}"><i style="width:{width:.2f}%"></i></div><b class="value-{value_tone(change)}">{html_text(fmt_evidence(item["change_pct"]))}</b></div>''')
            return "".join(rows)

        up_count = sum(float(item["change_pct"]["value"]) > 0 for item in ordered)
        down_count = sum(float(item["change_pct"]["value"]) < 0 for item in ordered)
        flat_count = len(ordered) - up_count - down_count
        full_rows = sector_rows(ordered)
        featured_rows = sector_rows(winners)
        if any(item["id"] not in {winner["id"] for winner in winners} for item in losers):
            featured_rows += '<p class="sector-divider">跌幅靠前</p>' + sector_rows(losers)
        sector_html = f'''<p class="section-note">{html_text(sectors["classification"])} · {html_text(sectors["status_reason"])}</p>
<div class="sector-summary"><span>覆盖 {len(ordered)} 个行业</span><span class="value-rise">上涨 {up_count}</span><span class="value-fall">下跌 {down_count}</span><span>平盘 {flat_count}</span></div>
<p class="sector-divider">涨幅靠前</p>{featured_rows}
<details class="full-list"><summary>展开完整 {len(ordered)} 个行业榜单</summary>{full_rows}</details>'''
    concept = derived.get("concept_flows")
    if concept:
        sector_html += html_concept_flows(concept)
    sector_leaders = derived.get("sector_leaders")
    if sector_leaders:
        sector_html += html_sector_leaders(sector_leaders)

    def evidence_rows(section_name: str, description_key: str) -> str:
        section = sections[section_name]
        if section["availability"] == "unknown":
            return f'<p class="empty">{html_text(section["status_reason"])}</p>'
        rows = []
        for item in section["items"]:
            evidence = item["metric"]
            method = f' · {html_text(item["method_category"])}' if section_name == "funds" else ""
            rows.append(f'''<li><strong>{html_text(item["name"])} · {html_text(fmt_evidence(evidence))}</strong><span>{html_text(item[description_key])}</span><small>{html_evidence(evidence)}{method}</small></li>''')
        return '<ul class="evidence-list">' + "".join(rows) + "</ul>"

    event_items = []
    status_labels = {"passed": "已验证", "failed": "未成立", "unknown": "待补证"}
    event_items.extend(
        f'<li class="resolved {html_text(item["status"])}"><time>{html_text(item["observed_market_date"])}</time>{html_text(item["title"])}<small>上期验证 · {status_labels[item["status"]]} · 观察值 {html_text(fmt_history_value(item["observed_value"], item["condition"]["unit"]))}</small></li>'
        for item in resolved_verifications
    )
    if sections["events"]["availability"] != "unknown":
        event_items.extend(f'<li><time>{html_text(item["event_date"])}</time>{html_text(item["title"])}<small>{html_text(item["source"]["name"])}</small></li>' for item in sections["events"]["items"])
    event_items.extend(
        f'<li class="future"><time>{html_text(item["event_date"])}</time>{html_text(item["title"])}<small>后续验证 · {html_text(item["condition"]["metric"])} {html_text(item["condition"]["operator"])} {html_text(item["condition"]["value"])} {html_text(item["condition"]["unit"])} · {html_text(item["source"]["name"])}</small></li>'
        for item in data.get("verification_points", [])
    )
    event_items.extend(
        f'<li class="future qualitative"><time>{html_text(item["event_date"])}</time>{html_text(item["title"])}<small>定性观察点 · 不自动结算 · {html_text(item["source"]["name"])}</small></li>'
        for item in data.get("qualitative_verification_points", [])
    )
    events_html = '<ul class="timeline">' + "".join(event_items) + "</ul>" if event_items else '<p class="empty">暂无可得事件或验证点</p>'

    signal_html = "".join(f'<li><strong>{html_text(signal["label"])}：</strong>{html_text(signal["evidence"])}<small>{html_text(signal["rule"])}</small></li>' for signal in signals)
    if not signal_html:
        signal_html = '<li>当前输入未触发任何预定义的结构规则。</li>'
    caveat_html = "".join(
        f'<li><strong>反方证据 · {html_text(name)}：</strong>{html_text(section["caveat"])}</li>'
        for name, section in sections.items()
        if section.get("caveat")
    )
    limits = "".join(f'<li>{html_text(name)}：{html_text(section["availability"])}，{html_text(section["status_reason"])}</li>' for name, section in sections.items() if section["availability"] != "available")

    source_row_parts = []
    for source in sources:
        location = "派生证据"
        if source["url"]:
            url = html_text(source["url"])
            location = f'<a href="{url}" rel="noreferrer" target="_blank">{url}</a>'
        source_row_parts.append(
            f'<tr><td>{html_text(source["name"])}</td><td>{location}</td><td>{source["count"]}</td></tr>'
        )
    source_rows = "".join(source_row_parts)
    all_unknown = coverage_counts["unknown"] == len(SECTION_NAMES)
    content = '<div class="no-data">该日期没有可得的盘面数据；未绘制任何零值替代图表。</div>' if all_unknown else f'''<section class="dashboard-grid" aria-label="盘面核心数据"><article class="panel wide"><div class="panel-head"><h2>主要指数</h2>{availability_badge(indices)}</div>{index_rows}</article><article class="panel"><div class="panel-head"><h2>市场宽度</h2>{availability_badge(breadth)}</div>{breadth_chart}</article><article class="panel"><div class="panel-head"><h2>短线情绪</h2>{availability_badge(sentiment_section)}</div>{sentiment_html}</article><article class="panel wide"><div class="panel-head"><h2>板块温度</h2>{availability_badge(sectors)}</div>{sector_html}</article><article class="panel"><div class="panel-head"><h2>资金证据</h2>{availability_badge(sections["funds"])}</div>{evidence_rows("funds", "methodology")}</article><article class="panel"><div class="panel-head"><h2>风格结构</h2>{availability_badge(sections["style"])}</div>{evidence_rows("style", "interpretation")}</article><article class="panel wide"><div class="panel-head"><h2>延续性检验</h2>{availability_badge(sections["prev_pool_performance"])}</div>{prev_pool_html}</article><article class="panel wide"><div class="panel-head"><h2>双确认主线矩阵</h2>{availability_badge(sections["mainline_matrix"])}</div>{mainline_html}</article><article class="panel wide"><div class="panel-head"><h2>事件与验证点</h2>{availability_badge(sections["events"])}</div>{events_html}</article></section>'''
    if not all_unknown and data.get("verification_points"):
        next_point = min(data["verification_points"], key=lambda item: item["event_date"])
        remaining = len(data["verification_points"]) - 1
        suffix = f"；另有 {remaining} 项" if remaining else ""
        content = f'''<aside class="verify-strip" aria-label="下一交易日验证"><span>下一交易日验证</span><strong>{html_text(next_point["event_date"])} · {html_text(next_point["title"])}{suffix}</strong><small>{html_text(next_point["source"]["name"])} · 已在信息截止日前公开</small></aside>''' + content

    breadth_history = history["metrics"]["advancer_share_pct"]
    turnover_history = history["metrics"]["turnover_amount"]
    history_strip = f'''<aside class="history-strip" aria-label="连续历史"><span>连续历史</span><strong>{history["sample_size"]} 个交易日 · 前值 {html_text(history["previous_market_date"] or "unknown")}</strong><small>上涨参与度20日分位 {html_text(breadth_history["percentile_20d"] if breadth_history["percentile_20d"] is not None else "样本不足")} · 成交额20日分位 {html_text(turnover_history["percentile_20d"] if turnover_history["percentile_20d"] is not None else "样本不足")}</small></aside>'''
    content = history_strip + content

    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1" /><meta name="robots" content="noindex,nofollow" /><title>A股每日盘面复盘 · {html_text(data["market_date"])}</title><style>
:root{{}}
main{{max-width:1180px;margin:auto;padding:32px 20px 56px}}
/* 每日复盘保留项：短线情绪五态语义色 + 附注小字 + 后续验证点 */
.section-note,.evidence{{color:var(--ink-tertiary);font-family:var(--font-ui);font-size:11.5px;line-height:1.55}}
.sentiment-state strong{{color:var(--ink-secondary)}}
.state-ice strong{{color:#2f5b93}}
.state-euphoria strong{{color:var(--gain)}}
.state-divergence strong{{color:var(--state-warn)}}
.state-repair strong{{color:var(--loss)}}
.timeline .future time{{color:var(--state-warn)}}
@media(max-width:760px){{main{{padding:22px 14px 40px}}}}

</style></head><body><main><header class="masthead"><div><p class="eyebrow">A-SHARE / DAILY INTELLIGENCE</p><h1>市场脉搏</h1></div><p class="asof">交易日 {html_text(data["market_date"])}<br />信息截止 {html_text(data["as_of"])}<br />{html_text(data["snapshot"]["type"])} · 修订 {data["snapshot"]["revision"]}<br />输入指纹 {html_text(input_sha256[:12])}</p></header><div class="coverage">{availability_badge({"availability": "available"})} {coverage_counts["available"]} 个章节 · {availability_badge({"availability": "partial"})} {coverage_counts["partial"]} 个章节 · {availability_badge({"availability": "unknown"})} {coverage_counts["unknown"]} 个章节</div><section class="hero-grid" aria-label="市场脉搏摘要">{"".join(hero_cards)}</section>{content}<section class="signal-area"><div class="panel-head"><h2>结构信号与限制</h2><span>证据优先</span></div><ul class="signal-list">{signal_html}{caveat_html}</ul>{f'<ul class="limits">{limits}</ul>' if limits else ''}</section><section class="source-box"><div class="panel-head"><h2>来源汇总</h2><span>{len(sources)} 个来源</span></div><table><thead><tr><th>来源</th><th>URL</th><th>使用次数</th></tr></thead><tbody>{source_rows}</tbody></table></section><footer>本报告只描述输入证据和显式规则，不构成投资建议。短线情绪状态不是仓位、交易或收益预测。</footer></main></body></html>'''


def _history_row(history: dict[str, Any], metric: str, label: str) -> str:
    item = history["metrics"][metric]
    percentile_20d = (
        f"{item['percentile_20d']:.2f}%" if item["percentile_20d"] is not None else "样本不足"
    )
    percentile_60d = (
        f"{item['percentile_60d']:.2f}%" if item["percentile_60d"] is not None else "样本不足"
    )
    return (
        f"| {label} | {fmt_history_value(item['current'], item['unit'])} | "
        f"{fmt_history_value(item['previous'], item['unit'])} | "
        f"{fmt_history_value(item['change'], item['unit'])} | {percentile_20d} | {percentile_60d} |"
    )


def build_markdown(
    data: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    input_sha256: str,
    derived: dict[str, Any],
    signals: list[dict[str, str]],
    coverage_counts: dict[str, int],
    sources: list[dict[str, Any]],
    history: dict[str, Any],
    resolved_verifications: list[dict[str, Any]],
) -> str:
    lines = [
        f"# A股每日盘面复盘｜{data['market_date']}",
        "",
        f"- 截止日期：{data['as_of']}",
        f"- 快照：{data['snapshot']['type']} / 修订 {data['snapshot']['revision']} / 截止 {data['snapshot']['cutoff_at']}",
        f"- 输入SHA-256：`{input_sha256}`",
        f"- 覆盖：可得{coverage_counts['available']} / 部分{coverage_counts['partial']} / 未知{coverage_counts['unknown']}",
        "- 结论属性：盘面证据与结构观察，不构成投资建议",
        "",
    ]
    if data.get("legacy_migration"):
        lines.append(
            "- 兼容归一化："
            + "；".join(data["legacy_migration"].get("warnings", []))
        )
        lines.append("")
    if coverage_counts["unknown"] == len(SECTION_NAMES):
        lines.extend(["## 无可得盘面数据", "", "本次八个盘面章节均为unknown，不能形成全市场强弱结论。", ""])

    lines.extend(["## 连续历史", ""])
    lines.append(
        f"- 样本：{history['sample_size']} 个交易日；前一交易日：{history['previous_market_date'] or 'unknown'}；当前情绪状态连续 {history['sentiment_state_streak'] if history['sentiment_state_streak'] is not None else 'unknown'} 日。"
    )
    lines.extend(["", "| 指标 | 当前 | 前值 | 变化 | 20日分位 | 60日分位 |", "|---|---:|---:|---:|---:|---:|"])
    history_labels = (
        ("primary_index_change_pct", "主要指数涨跌幅"),
        ("advancer_share_pct", "上涨参与度"),
        ("turnover_amount", "成交额"),
        ("open_board_rate_pct", "炸板率"),
        ("limit_balance", "涨停净差"),
    )
    for metric, label in history_labels:
        lines.append(_history_row(history, metric, label))
    # 晋级率只在延续性检验章节存在时才入表：旧输入没有该指标，表格保持原样。
    if "promotion_rate_pct" in history["metrics"]:
        lines.append(_history_row(history, "promotion_rate_pct", "昨日涨停池晋级率"))
    lines.append("")

    lines.extend(["## 一、主要指数", ""])
    indices = sections["indices"]
    if indices["availability"] == "unknown":
        lines.extend([unknown_line(indices), ""])
    else:
        lines.extend(["| 指数 | 收盘 | 涨跌幅 | 观察日 | 来源 |", "|---|---:|---:|---|---|"])
        for item in indices["items"]:
            evidence = item["change_pct"]
            lines.append(
                f"| {item['name']} | {fmt_evidence(item['close'])} | {fmt_evidence(evidence)} | {evidence['observed_at']} | {evidence['source']['name']} |"
            )
        lines.append("")

    lines.extend(["## 二、市场宽度", ""])
    breadth = sections["breadth"]
    if breadth["availability"] == "unknown":
        lines.extend([unknown_line(breadth), ""])
    else:
        lines.extend(["| 指标 | 数值 | 观察日 | 来源 |", "|---|---:|---|---|"])
        for name, label in (
            ("advancers", "上涨家数"),
            ("decliners", "下跌家数"),
            ("unchanged", "平盘家数"),
            ("limit_up", "涨停家数"),
            ("limit_down", "跌停家数"),
        ):
            evidence = breadth.get("metrics", {}).get(name)
            if evidence:
                lines.append(
                    f"| {label} | {fmt_evidence(evidence)} | {evidence['observed_at']} | {evidence['source']['name']} |"
                )
        if "advancer_share_pct" in derived:
            lines.append("")
            lines.append(f"上涨家数占比：{derived['advancer_share_pct']:.2f}%")
            ratio = derived.get("advance_decline_ratio")
            lines.append(f"涨跌家数比：{ratio:.2f}" if ratio is not None else "涨跌家数比：无法计算（下跌家数为0）")
        lines.append("")

    lines.extend(["## 三、短线情绪观察", ""])
    sentiment_section = sections["short_term_sentiment"]
    sentiment = derived["short_term_sentiment"]
    if sentiment["state"] == "unknown":
        lines.extend([f"> UNKNOWN：{sentiment['reason']}", ""])
    else:
        labels = {
            "ice": "冰点",
            "euphoria": "亢奋",
            "divergence": "分歧",
            "repair": "修复",
            "neutral": "中性",
        }
        metrics = sentiment_section["metrics"]
        lines.extend(
            [
                f"- 股票池：{sentiment_section['universe']['label']}（{sentiment_section['universe']['id']}）",
                f"- 方法：{sentiment_section['methodology']}",
                f"- 炸板率：{sentiment['open_board_rate_pct']:.2f}%（{fmt_evidence(metrics['open_board_failed'])} / {fmt_evidence(metrics['limit_attempts'])}）",
                f"- 最高连板：{fmt_evidence(metrics['highest_streak'])}",
                f"- 状态：{labels[sentiment['state']]}；规则：`{sentiment['rule']}`。",
                f"- 依据：{sentiment['evidence']}。",
            ]
        )
        if not sentiment["repair_evaluated"]:
            if sentiment.get("previous_metrics_available"):
                lines.append(
                    "- 修复：未评估（当前状态由更高优先级的预定义规则先行判定，未进入修复比较）。"
                )
            else:
                lines.append("- 修复：未评估（缺少完整的前一可比交易日指标）。")
        health = derived.get("sentiment_health_check")
        if health:
            lines.extend(markdown_health_check(health))
        ladder = derived.get("streak_distribution")
        if ladder:
            lines.extend(markdown_streak_distribution(ladder))
        quality = derived.get("high_board_quality")
        if quality:
            lines.extend(markdown_high_boards(quality))
        lines.append("")

    lines.extend(["## 四、成交与流动性", ""])
    turnover = sections["turnover"]
    if turnover["availability"] == "unknown":
        lines.extend([unknown_line(turnover), ""])
    else:
        amount = turnover["metrics"].get("amount")
        if amount:
            lines.append(f"- 当日成交额：{fmt_evidence(amount)}")
        if "turnover_vs_previous_pct" in derived:
            lines.append(f"- 较前值：{derived['turnover_vs_previous_pct']:+.2f}%")
        if "turnover_vs_5d_avg_pct" in derived:
            lines.append(f"- 较5日均值：{derived['turnover_vs_5d_avg_pct']:+.2f}%")
        lines.extend([f"- 覆盖说明：{turnover['status_reason']}", ""])

    lines.extend(["## 五、板块表现", ""])
    sectors = sections["sectors"]
    if sectors["availability"] == "unknown":
        lines.extend([unknown_line(sectors), ""])
    else:
        ordered = sorted(sectors["items"], key=lambda item: (-float(item["change_pct"]["value"]), item["id"]))
        has_flow = any(item.get("fund_flow") for item in ordered)
        lines.append(f"分类体系：{sectors['classification']}；覆盖状态：{sectors['availability']}。")
        if has_flow:
            methods = sorted(
                {
                    item["fund_flow_method_category"]
                    for item in ordered
                    if item.get("fund_flow")
                }
            )
            lines.append(
                f"板块资金流证据类别：{'、'.join(methods)}；资金流为供应商推导值时按该类别披露，不等同交易所事实。"
            )
        lines.append("")
        if has_flow:
            lines.extend(
                [
                    "| 板块 | 涨跌幅 | 板块资金净流入 | 观察日 | 来源 |",
                    "|---|---:|---:|---|---|",
                ]
            )
            for item in ordered:
                evidence = item["change_pct"]
                flow = item.get("fund_flow")
                flow_cell = fmt_flow_cny(float(flow["value"])) if flow else "unknown"
                lines.append(
                    f"| {item['name']} | {fmt_evidence(evidence)} | {flow_cell} | {evidence['observed_at']} | {evidence['source']['name']} |"
                )
        else:
            lines.extend(["| 板块 | 涨跌幅 | 观察日 | 来源 |", "|---|---:|---|---|"])
            for item in ordered:
                evidence = item["change_pct"]
                lines.append(
                    f"| {item['name']} | {fmt_evidence(evidence)} | {evidence['observed_at']} | {evidence['source']['name']} |"
                )
        concept = derived.get("concept_flows")
        if concept:
            lines.extend(markdown_concept_flows(concept))
        sector_leaders = derived.get("sector_leaders")
        if sector_leaders:
            lines.extend(markdown_sector_leaders(sector_leaders))
        lines.append("")

    for section_name, heading, explanation in (
        ("funds", "六、资金证据", "methodology"),
        ("style", "七、风格结构", "interpretation"),
    ):
        section = sections[section_name]
        lines.extend([f"## {heading}", ""])
        if section["availability"] == "unknown":
            lines.extend([unknown_line(section), ""])
            continue
        method_heading = "证据类别 | " if section_name == "funds" else ""
        lines.extend([f"| 项目 | 数值 | {method_heading}方法/解释 | 观察日 | 来源 |", f"|---|---:|{'---|' if section_name == 'funds' else ''}---|---|---|"])
        for item in section["items"]:
            evidence = item["metric"]
            method_cell = f"{item['method_category']} | " if section_name == "funds" else ""
            lines.append(
                f"| {item['name']} | {fmt_evidence(evidence)} | {method_cell}{item[explanation]} | {evidence['observed_at']} | {evidence['source']['name']} |"
            )
        lines.append("")

    lines.extend(["## 八、延续性检验：前一涨停池当日表现", ""])
    lines.extend(
        markdown_prev_pool(
            derived.get("prev_pool_performance"),
            sections["prev_pool_performance"],
            data["market_date"],
        )
    )

    lines.extend(["## 九、双确认主线矩阵", ""])
    lines.extend(
        markdown_mainline(derived.get("mainline_matrix"), sections["mainline_matrix"])
    )

    lines.extend(["## 十、事件与验证点", ""])
    events = sections["events"]
    if events["availability"] == "unknown":
        lines.extend([unknown_line(events), ""])
    else:
        for item in events["items"]:
            lines.append(f"- {item['event_date']}｜{item['title']}｜{item['source']['name']}")
        lines.append("")
    if resolved_verifications:
        lines.append("上一期验证结果：")
        lines.append("")
        status_labels = {"passed": "成立", "failed": "未成立", "unknown": "无法判断"}
        for item in resolved_verifications:
            observed = fmt_history_value(
                item["observed_value"], item["condition"]["unit"]
            )
            lines.append(
                f"- {status_labels[item['status']]}｜{item['title']}｜观察值 {observed}（{item['observed_market_date']}）"
            )
        lines.append("")
    if data.get("qualitative_verification_points"):
        lines.append("定性观察点（不自动结算）：")
        lines.append("")
        for item in data["qualitative_verification_points"]:
            lines.append(
                f"- {item['event_date']}｜{item['title']}｜{item['source']['name']}"
            )
        lines.append("")
    if data.get("verification_points"):
        lines.append("后续验证点：")
        lines.append("")
        for item in data["verification_points"]:
            condition = item["condition"]
            lines.append(
                f"- {item['event_date']}｜{item['title']}｜`{condition['metric']} {condition['operator']} {condition['value']} {condition['unit']}`｜{item['source']['name']}"
            )
        lines.append("")

    lines.extend(["## 十一、结构信号与限制", ""])
    caveats = [
        (name, section["caveat"])
        for name, section in sections.items()
        if section.get("caveat")
    ]
    if caveats:
        lines.extend(["反方证据与自我证伪（由输入显式声明）：", ""])
        for name, caveat in caveats:
            lines.append(f"- {name}：{caveat}")
        lines.append("")
    if signals:
        for signal in signals:
            lines.append(f"- {signal['label']}：{signal['evidence']}；规则：`{signal['rule']}`。")
    else:
        lines.append("- 当前输入未触发预定义的指数—宽度背离规则。")
    lines.append("")
    for name in SECTION_NAMES:
        section = sections[name]
        if section["availability"] != "available":
            lines.append(f"- {name}：{section['availability']}，{section['status_reason']}")
    lines.extend(["", "## 十二、来源汇总", "", "| 来源 | URL | 使用次数 |", "|---|---|---:|"])
    for source in sources:
        lines.append(f"| {source['name']} | {source['url'] or '派生证据'} | {source['count']} |")
    lines.extend(["", "---", "", "本报告只描述输入证据和显式规则，不构成投资建议。", ""])
    report = "\n".join(lines)
    for phrase in FORBIDDEN:
        if phrase in report:
            raise ReviewError(f"输出包含禁止的投资指令：{phrase}")
    return report
