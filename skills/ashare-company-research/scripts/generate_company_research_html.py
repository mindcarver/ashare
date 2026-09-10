#!/usr/bin/env python3
"""Render verified company research as a concise, expandable dashboard."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# 共享层：禁词与设计令牌的唯一真源（见 skills/_shared/README.md）
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from ashare_shared import forbidden_terms, inject_shared_css  # noqa: E402


# 公司研究不输出任何价格锚点，因此用含价位禁令的 tier。
# 禁词表唯一真源：skills/_shared/forbidden-terms.json
FORBIDDEN = forbidden_terms("no_price")
META_KEYS = ("company", "ticker", "exchange", "as_of", "accessed_at", "period", "mode", "confidence")
SUMMARY_KEYS = ("research_label", "market_view", "evidence_view", "expectation_gap", "valuation_view", "primary_risk")
KINDS = {"事实", "推断", "判断"}
TONES = {"red", "green", "gold", "muted"}
# 设计令牌为空占位（:root{}）：渲染时由 ashare_shared.inject_shared_css() 注入
# _shared/design-tokens.css + shell.css + components.css。
# **组件样式一律不写在这里** —— 品牌层插在 head 结束标签之前（本样式块之后），
# 对同名选择器有最终解释权，这里再写一份只会变成永不生效的死代码。
# 本文件只保留公司研究页独有、品牌层不该知道的布局。
STYLE = """:root{}
main{max-width:1180px;margin:auto;padding:32px 20px 56px}
/* 研究命题卡：大一号正文，是全页唯一被强调的长句 */
.thesis h2{font-size:21px;letter-spacing:-.02em;line-height:1.35}
.thesis p{margin-top:10px;font-size:16px;line-height:1.8}
.thesis strong{color:var(--accent)}
/* 五格关键信号：数值置底、描述两行截断，保证五格等高 */
.signal{display:flex;flex-direction:column;justify-content:space-between;min-height:140px}
.signal-grid .signal{border-top:4px solid var(--accent)}
.signal span{font-family:var(--font-ui);font-size:11px;line-height:1.6;color:var(--ink-tertiary)}
.signal b{font-family:var(--font-mono);font-size:24px;font-weight:700;letter-spacing:-.05em;line-height:1.1}
.signal p{font-family:var(--font-body);font-size:12.5px;line-height:1.6;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
/* 三格口径卡：顶规区分「市场 / 事实 / 证伪」。
   用 .panel.* 提高一级特异性——品牌层后写，同特异性的 border-top 会被它压掉。 */
.panel.market{border-top:4px solid var(--state-unknown)}
.panel.facts{border-top:4px solid var(--state-ok)}
.panel.proof{border-top:4px solid var(--state-bad)}
.panel.source{background:var(--paper-2);border-left:6px solid var(--line)}
.panel.source a{word-break:break-all}
@media(max-width:760px){main{padding:22px 14px 40px}}"""


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 A 股公司研究仪表盘 HTML")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args()


def html(value: Any) -> str:
    return escape(str(value), quote=True)


def required(value: Any, field: str, limit: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空字符串")
    value = value.strip()
    if limit is not None and len(value) > limit:
        raise ValueError(f"{field} 超过 {limit} 字，首层必须可扫读")
    return value


def day(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 不是 ISO 日期") from exc


def objects(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{field} 必须是对象数组")
    return value


def forbidden(value: Any) -> str | None:
    if isinstance(value, str):
        return next((item for item in FORBIDDEN if item in value), None)
    if isinstance(value, dict):
        for child in value.values():
            hit = forbidden(child)
            if hit:
                return hit
    if isinstance(value, list):
        for child in value:
            hit = forbidden(child)
            if hit:
                return hit
    return None


def validate_dashboard(value: Any, source_ids: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("dashboard 必须是对象")
    thesis = value.get("headline_thesis")
    if not isinstance(thesis, dict):
        raise ValueError("dashboard.headline_thesis 必须是对象")
    required(thesis.get("statement"), "dashboard.headline_thesis.statement", 120)
    required(thesis.get("detail"), "dashboard.headline_thesis.detail", 180)
    signals = objects(value.get("signals"), "dashboard.signals")
    if len(signals) != 5:
        raise ValueError("dashboard.signals 必须恰好包含5个关键信号")
    for index, signal in enumerate(signals):
        for key, limit in (("label", 24), ("value", 30), ("detail", 60)):
            required(signal.get(key), f"dashboard.signals[{index}].{key}", limit)
        if signal.get("kind") not in KINDS:
            raise ValueError("dashboard.signals.kind 必须是 事实/推断/判断")
        if signal.get("tone") not in TONES:
            raise ValueError("dashboard.signals.tone 必须是 red/green/gold/muted")
        if signal["kind"] == "事实" and signal.get("source_id") not in source_ids:
            raise ValueError("首层事实信号缺少有效 source_id")
    gap = value.get("expectation_gap")
    if not isinstance(gap, dict):
        raise ValueError("dashboard.expectation_gap 必须是对象")
    for key in ("market_pricing", "verified_facts", "next_proof"):
        required(gap.get(key), f"dashboard.expectation_gap.{key}", 120)
    for field in ("catalysts", "invalidations"):
        items = objects(value.get(field), f"dashboard.{field}")
        if not 1 <= len(items) <= 3:
            raise ValueError(f"dashboard.{field} 必须包含1到3项")
        for index, item in enumerate(items):
            required(item.get("title"), f"dashboard.{field}[{index}].title", 60)
            required(item.get("detail"), f"dashboard.{field}[{index}].detail", 100)
    return value


def validate(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("根节点必须是对象")
    hit = forbidden(data)
    if hit:
        raise ValueError(f"禁止个性化投资指令：{hit}")
    meta, summary = data.get("meta"), data.get("summary")
    if not isinstance(meta, dict) or not isinstance(summary, dict):
        raise ValueError("meta 和 summary 必须是对象")
    for key in META_KEYS:
        required(meta.get(key), f"meta.{key}")
    as_of = day(meta["as_of"], "meta.as_of")
    for key in SUMMARY_KEYS:
        required(summary.get(key), f"summary.{key}")
    source_ids: set[str] = set()
    for index, source in enumerate(objects(data.get("sources"), "sources")):
        for key in ("id", "name", "url"):
            required(source.get(key), f"sources[{index}].{key}")
        if urlparse(source["url"]).scheme not in {"http", "https"}:
            raise ValueError("来源 URL 必须是 http 或 https")
        if source["id"] in source_ids:
            raise ValueError(f"sources.id 重复：{source['id']}")
        source_ids.add(source["id"])
    validate_dashboard(data.get("dashboard"), source_ids)
    for index, item in enumerate(objects(data.get("evidence", []), "evidence")):
        required(item.get("label"), f"evidence[{index}].label")
        required(item.get("content"), f"evidence[{index}].content")
        if item.get("kind") not in KINDS:
            raise ValueError(f"evidence[{index}].kind 必须是 事实/推断/判断")
        if item["kind"] == "事实":
            if item.get("source_id") not in source_ids:
                raise ValueError("事实证据缺少 source_id")
            for key in ("observed_at", "published_at"):
                required(item.get(key), f"evidence[{index}].{key}")
            if day(item["published_at"], f"evidence[{index}].published_at") > as_of:
                raise ValueError("事实证据 published_at 晚于 as_of")
    for field, keys in {"business_engine": ("label", "content"), "catalysts": ("window", "event", "evidence", "upside", "downside"), "risks": ("risk", "signal", "trigger", "impact")}.items():
        for index, item in enumerate(objects(data.get(field, []), field)):
            for key in keys:
                required(item.get(key), f"{field}[{index}].{key}")
    valuation = data.get("valuation")
    if not isinstance(valuation, dict):
        raise ValueError("valuation 必须是对象")
    required(valuation.get("method"), "valuation.method")
    required(valuation.get("conclusion"), "valuation.conclusion")
    for index, item in enumerate(objects(valuation.get("scenarios", []), "valuation.scenarios")):
        for key in ("name", "assumption", "trigger"):
            required(item.get(key), f"valuation.scenarios[{index}].{key}")
    technical = data.get("technical")
    if not isinstance(technical, dict) or technical.get("availability") not in {"available", "partial", "unknown"}:
        raise ValueError("technical.availability 必须是 available/partial/unknown")
    required(technical.get("summary") if technical["availability"] == "available" else technical.get("status_reason"), "technical.summary")
    gaps = data.get("gaps", [])
    if not isinstance(gaps, list) or not all(isinstance(item, str) and item.strip() for item in gaps):
        raise ValueError("gaps 必须是非空字符串数组")
    return data


def badge(kind: str) -> str:
    mapping = {"事实": "fact", "推断": "inference", "判断": "judgment"}
    return f'<span class="badge badge-{mapping[kind]}">{html(kind)}</span>'


def timeline(items: list[dict[str, Any]]) -> str:
    return "".join(f'<li><strong>{html(item["title"])}</strong><small>{html(item["detail"])}</small></li>' for item in items)


def render(data: dict[str, Any]) -> str:
    meta, summary, dashboard = data["meta"], data["summary"], data["dashboard"]
    sources = {item["id"]: item for item in data["sources"]}
    fact_count = sum(item["kind"] == "事实" for item in data["evidence"])
    signal_html = "".join(f'<article class="signal {html(item["tone"])}"><span>{html(item["label"])} · {badge(item["kind"])}</span><b>{html(item["value"])}</b><p>{html(item["detail"])}</p></article>' for item in dashboard["signals"])
    gap = dashboard["expectation_gap"]
    evidence_rows = []
    for item in data["evidence"]:
        source = sources.get(item.get("source_id"))
        trace = "—" if not source else f'{html(source["name"])} · 观测 {html(item["observed_at"])} · 发布 {html(item["published_at"])}'
        evidence_rows.append(f'<tr><td>{html(item["label"])}</td><td>{html(item["content"])}</td><td>{badge(item["kind"])}</td><td>{trace}</td></tr>')
    engine = "".join(f'<li><strong>{html(item["label"])}：</strong>{html(item["content"])}</li>' for item in data["business_engine"]) or '<li>未取得可验证的业务拆分。</li>'
    catalysts = "".join(f'<li><strong>{html(item["window"])} · {html(item["event"])}</strong><small>依据：{html(item["evidence"])}；强化：{html(item["upside"])}；弱化：{html(item["downside"])}</small></li>' for item in data["catalysts"]) or '<li>暂无已知催化剂。</li>'
    risks = "".join(f'<li><strong>{html(item["risk"])}</strong><small>信号：{html(item["signal"])}；触发：{html(item["trigger"])}；影响：{html(item["impact"])}</small></li>' for item in data["risks"]) or '<li>未取得足够风险证据。</li>'
    scenarios = "".join(f'<tr><td>{html(item["name"])}</td><td>{html(item["assumption"])}</td><td>{html(item["trigger"])}</td></tr>' for item in data["valuation"]["scenarios"]) or '<tr><td colspan="3">未取得可审计情景。</td></tr>'
    technical = data["technical"]
    technical_text = technical["summary"] if technical["availability"] == "available" else f'技术面未验证：{technical["status_reason"]}'
    source_rows = "".join(f'<tr><td>{html(item["name"])}</td><td><a href="{html(item["url"])}" rel="noreferrer" target="_blank">{html(item["url"])}</a></td></tr>' for item in data["sources"])
    gaps = "".join(f'<li>{html(item)}</li>' for item in data["gaps"])
    return inject_shared_css(f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>{html(meta["company"])} · A股公司研究仪表盘</title><style>{STYLE}</style></head><body><main><header class="masthead"><div><p class="eyebrow">A股 / 公司研究</p><h1>{html(meta["company"])}</h1></div><p class="asof">{html(meta["ticker"])} · {html(meta["exchange"])}<br>截止 {html(meta["as_of"])}<br>事实 {fact_count} · 推断 {sum(x["kind"] == "推断" for x in data["evidence"])} · 判断 {sum(x["kind"] == "判断" for x in data["evidence"])}</p></header><div class="badges">{badge("事实")} 已核验数据 · {badge("推断")} 机制解释 · {badge("判断")} 研究标签 {html(summary["research_label"])} · <span class="badge badge-inference">{html(meta["mode"])} · 置信度 {html(meta["confidence"])}</span></div><section class="panel thesis"><h2>当前研究命题：<strong>{html(dashboard["headline_thesis"]["statement"])}</strong></h2><p>{html(dashboard["headline_thesis"]["detail"])}</p></section><section class="signal-grid" aria-label="五个关键研究信号">{signal_html}</section><section class="grid"><article class="panel market"><span class="num">01 · 市场定价</span><h2>市场定价什么</h2><p>{html(gap["market_pricing"])}</p></article><article class="panel facts"><span class="num">02 · 已验证事实</span><h2>已验证事实</h2><p>{html(gap["verified_facts"])}</p></article><article class="panel proof"><span class="num">03 · 下一步验证</span><h2>下一步验证</h2><p>{html(gap["next_proof"])}</p></article></section><section class="split"><article class="panel"><span class="num">催化剂</span><h2>催化剂</h2><ul class="timeline">{timeline(dashboard["catalysts"])}</ul></article><article class="panel"><span class="num">证伪信号</span><h2>证伪信号</h2><ul class="timeline">{timeline(dashboard["invalidations"])}</ul></article></section><details class="details"><summary>展开关键证据台账 · 只在需要追溯时阅读</summary><section class="panel table-wrap"><table><thead><tr><th>信号</th><th>内容</th><th>类型</th><th>来源与时间</th></tr></thead><tbody>{"".join(evidence_rows) or '<tr><td colspan="4">未取得可验证证据。</td></tr>'}</tbody></table></section></details><details class="details"><summary>展开业务、估值、风险与技术面</summary><section class="grid"><article class="panel"><h2>业务与利润引擎</h2><ul class="timeline">{engine}</ul></article><article class="panel"><h2>催化剂日历</h2><ul class="timeline">{catalysts}</ul></article><article class="panel"><h2>估值与情景</h2><p>{html(data["valuation"]["method"])}：{html(data["valuation"]["conclusion"])}</p><div class="table-wrap"><table><thead><tr><th>情景</th><th>假设</th><th>触发</th></tr></thead><tbody>{scenarios}</tbody></table></div></article><article class="panel"><h2>风险与证伪</h2><ul class="timeline">{risks}</ul></article></section><section class="panel" style="margin-top:10px"><h2>技术面</h2><p>{html(technical_text)}</p><div class="notice"><strong>待核验：</strong><ul>{gaps}</ul></div></section></details><details class="details"><summary>展开来源与完整研究记录</summary><section class="panel source table-wrap"><h2>信息来源</h2><table><thead><tr><th>来源</th><th>URL</th></tr></thead><tbody>{source_rows}</tbody></table></section></details><footer>首层只呈现可决策信息；完整事实、推断、判断和来源均可展开追溯，不构成个性化投资建议。</footer></main></body></html>''')


def main() -> int:
    parsed = args()
    try:
        data = validate(json.loads(parsed.input.read_text(encoding="utf-8")))
        if parsed.check:
            print(f"✅ 公司研究仪表盘输入验证通过：{data['meta']['company']}，{len(data['dashboard']['signals'])} 个关键信号")
            return 0
        if not parsed.out:
            raise ValueError("生成 HTML 时必须提供 --out")
        parsed.out.parent.mkdir(parents=True, exist_ok=True)
        parsed.out.write_text(render(data), encoding="utf-8")
        print(f"✅ 已生成 {parsed.out}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
