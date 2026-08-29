#!/usr/bin/env python3
"""将已核验的单公司研究 JSON 渲染为自包含的研报风 HTML。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


FORBIDDEN = (
    "建议买入", "建议卖出", "目标价", "目标仓位", "建议加仓", "建议减仓",
    "建议满仓", "建议清仓", "保证收益",
)
SUMMARY_KEYS = (
    "research_label", "market_view", "evidence_view", "expectation_gap",
    "valuation_view", "primary_risk",
)
META_KEYS = ("company", "ticker", "exchange", "as_of", "accessed_at", "period", "mode", "confidence")
EVIDENCE_KINDS = {"事实", "推断", "判断"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 A 股公司研究静态 HTML")
    parser.add_argument("--input", required=True, type=Path, help="company-research.json")
    parser.add_argument("--out", type=Path, help="输出 HTML 路径；--check 时可省略")
    parser.add_argument("--check", action="store_true", help="只验证输入契约")
    return parser.parse_args()


def html_text(value: Any) -> str:
    return escape(str(value), quote=True)


def text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空字符串")
    return value.strip()


def parse_day(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value[:10])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 不是 ISO 日期") from exc


def ensure_list(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{field} 必须是数组")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{field} 的每项必须是对象")
    return value


def contains_forbidden(value: Any) -> str | None:
    if isinstance(value, str):
        return next((term for term in FORBIDDEN if term in value), None)
    if isinstance(value, dict):
        for item in value.values():
            found = contains_forbidden(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = contains_forbidden(item)
            if found:
                return found
    return None


def validate(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("根节点必须是对象")
    forbidden = contains_forbidden(data)
    if forbidden:
        raise ValueError(f"禁止个性化投资指令：{forbidden}")

    meta = data.get("meta")
    summary = data.get("summary")
    if not isinstance(meta, dict) or not isinstance(summary, dict):
        raise ValueError("meta 和 summary 必须是对象")
    for key in META_KEYS:
        text(meta.get(key), f"meta.{key}")
    as_of = parse_day(meta["as_of"], "meta.as_of")
    for key in SUMMARY_KEYS:
        text(summary.get(key), f"summary.{key}")

    sources = ensure_list(data.get("sources"), "sources")
    source_ids = set()
    for index, source in enumerate(sources):
        for key in ("id", "name", "url"):
            text(source.get(key), f"sources[{index}].{key}")
        if urlparse(source["url"]).scheme not in {"http", "https"}:
            raise ValueError("来源 URL 必须是 http 或 https")
        if source["id"] in source_ids:
            raise ValueError(f"sources.id 重复：{source['id']}")
        source_ids.add(source["id"])

    evidence = ensure_list(data.get("evidence", []), "evidence")
    for index, item in enumerate(evidence):
        text(item.get("label"), f"evidence[{index}].label")
        text(item.get("content"), f"evidence[{index}].content")
        kind = item.get("kind")
        if kind not in EVIDENCE_KINDS:
            raise ValueError(f"evidence[{index}].kind 必须是 事实/推断/判断")
        if kind == "事实":
            source_id = item.get("source_id")
            if not source_id:
                raise ValueError("事实证据缺少 source_id")
            if source_id not in source_ids:
                raise ValueError(f"事实证据引用了未知来源：{source_id}")
            for key in ("observed_at", "published_at"):
                text(item.get(key), f"evidence[{index}].{key}")
            if parse_day(item["published_at"], f"evidence[{index}].published_at") > as_of:
                raise ValueError("事实证据 published_at 晚于 as_of")

    for field, keys in {
        "business_engine": ("label", "content"),
        "catalysts": ("window", "event", "evidence", "upside", "downside"),
        "risks": ("risk", "signal", "trigger", "impact"),
    }.items():
        for index, item in enumerate(ensure_list(data.get(field, []), field)):
            for key in keys:
                text(item.get(key), f"{field}[{index}].{key}")

    valuation = data.get("valuation")
    if not isinstance(valuation, dict):
        raise ValueError("valuation 必须是对象")
    for key in ("method", "conclusion"):
        text(valuation.get(key), f"valuation.{key}")
    for index, scenario in enumerate(ensure_list(valuation.get("scenarios", []), "valuation.scenarios")):
        for key in ("name", "assumption", "trigger"):
            text(scenario.get(key), f"valuation.scenarios[{index}].{key}")

    technical = data.get("technical")
    if not isinstance(technical, dict) or technical.get("availability") not in {"available", "partial", "unknown"}:
        raise ValueError("technical.availability 必须是 available/partial/unknown")
    if technical["availability"] != "available":
        text(technical.get("status_reason"), "technical.status_reason")
    elif not technical.get("summary"):
        raise ValueError("technical.available 时必须提供 summary")

    gaps = data.get("gaps", [])
    if not isinstance(gaps, list) or not all(isinstance(item, str) and item.strip() for item in gaps):
        raise ValueError("gaps 必须是非空字符串数组")
    return data


def badge(kind: str) -> str:
    mapping = {"事实": "fact", "推断": "inference", "判断": "judgment"}
    return f'<span class="badge badge-{mapping.get(kind, "judgment")}">{html_text(kind)}</span>'


def cards(summary: dict[str, Any]) -> str:
    values = (
        ("市场交易逻辑", summary["market_view"], "neutral"),
        ("最大预期差", summary["expectation_gap"], "rise"),
        ("估值视角", summary["valuation_view"], "neutral"),
        ("首要风险", summary["primary_risk"], "fall"),
    )
    return "".join(
        f'<article class="metric-card tone-{tone}"><p>{html_text(label)}</p><strong>{html_text(value)}</strong></article>'
        for label, value, tone in values
    )


def list_items(items: list[str]) -> str:
    if not items:
        return '<p class="empty">未取得可验证条目。</p>'
    return "<ul>" + "".join(f"<li>{html_text(item)}</li>" for item in items) + "</ul>"


def render(data: dict[str, Any]) -> str:
    meta = data["meta"]
    summary = data["summary"]
    sources = {source["id"]: source for source in data["sources"]}
    evidence_rows = []
    for item in data["evidence"]:
        source = sources.get(item.get("source_id"))
        provenance = ""
        if source:
            provenance = (
                f'{html_text(source["name"])} · 观测 {html_text(item["observed_at"])} · '
                f'发布 {html_text(item["published_at"])}'
            )
        evidence_rows.append(
            f'<tr><td>{html_text(item["label"])}</td><td>{html_text(item["content"])}</td>'
            f'<td>{badge(item["kind"])}</td><td>{provenance or "—"}</td></tr>'
        )

    engine = "".join(
        f'<li><strong>{html_text(item["label"])}：</strong>{html_text(item["content"])}</li>'
        for item in data["business_engine"]
    ) or '<li>未取得可验证的业务与利润引擎拆分。</li>'
    catalysts = "".join(
        f'<li><time>{html_text(item["window"])}</time><strong>{html_text(item["event"])}</strong>'
        f'<span>{html_text(item["evidence"])}</span><small>超预期：{html_text(item["upside"])}；低于预期：{html_text(item["downside"])}</small></li>'
        for item in data["catalysts"]
    ) or '<li>暂无已知日期或时间窗口的催化剂。</li>'
    scenarios = "".join(
        f'<tr><td>{html_text(item["name"])}</td><td>{html_text(item["assumption"])}</td><td>{html_text(item["trigger"])}</td></tr>'
        for item in data["valuation"]["scenarios"]
    ) or '<tr><td colspan="3">未取得可审计情景。</td></tr>'
    risks = "".join(
        f'<li><strong>{html_text(item["risk"])}</strong><span>当前信号：{html_text(item["signal"])}</span>'
        f'<small>触发：{html_text(item["trigger"])}；影响：{html_text(item["impact"])}</small></li>'
        for item in data["risks"]
    ) or '<li>未取得足够信息以列出具体风险。</li>'
    technical = data["technical"]
    technical_html = (
        f'<p>{html_text(technical["summary"])}</p>'
        if technical["availability"] == "available"
        else f'<p class="empty">技术面未验证：{html_text(technical["status_reason"])}</p>'
    )
    source_rows = "".join(
        f'<tr><td>{html_text(source["name"])}</td><td><a href="{html_text(source["url"])}" rel="noreferrer" target="_blank">{html_text(source["url"])}</a></td></tr>'
        for source in data["sources"]
    )
    fact_count = sum(item["kind"] == "事实" for item in data["evidence"])

    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1" /><meta name="robots" content="noindex,nofollow" /><title>{html_text(meta["company"])} · A股公司深度调研</title><style>
:root{{--ink:#13211f;--paper:#f6f1e7;--paper-2:#eee6d7;--line:#d8cdbb;--red:#bf332d;--green:#19724b;--gold:#ba8a35;--muted:#756f66}}*{{box-sizing:border-box}}body{{margin:0;background:#18221f;color:var(--ink);font-family:"Noto Serif SC","Songti SC",STSong,serif;overflow-x:hidden}}body:before{{content:"";position:fixed;inset:0;pointer-events:none;opacity:.15;background-image:linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.04) 1px,transparent 1px);background-size:24px 24px}}main{{max-width:1180px;margin:auto;padding:32px 20px 56px}}.masthead{{color:#f8f2e6;border-bottom:1px solid rgba(248,242,230,.25);padding:0 0 24px;display:flex;justify-content:space-between;gap:24px;align-items:end}}.eyebrow{{font:700 11px/1 "SFMono-Regular",Consolas,monospace;letter-spacing:.18em;color:#e3bc70;margin:0 0 12px}}h1,h2,p{{margin:0}}h1{{font-size:clamp(34px,6vw,68px);line-height:.95;letter-spacing:-.06em}}.asof{{font-size:14px;color:#cfc5b4;line-height:1.65;text-align:right}}.coverage{{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0}}.badge{{display:inline-flex;align-items:center;font:700 11px/1 "SFMono-Regular",Consolas,monospace;padding:6px 8px;border-radius:999px;letter-spacing:.04em}}.badge-fact{{background:#d8eedf;color:#155836}}.badge-inference{{background:#efe4c7;color:#725210}}.badge-judgment{{background:#edd8d2;color:#8a2c27}}.hero-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:10px}}.metric-card,.panel{{background:var(--paper);border:1px solid var(--line);box-shadow:5px 5px 0 rgba(12,18,16,.25)}}.metric-card{{min-width:0;min-height:150px;padding:18px;display:flex;flex-direction:column;justify-content:space-between;border-top:4px solid var(--gold);overflow:hidden}}.metric-card p,.section-note,small{{color:var(--muted);font-size:12px;line-height:1.5}}.metric-card strong{{font-size:18px;line-height:1.55;overflow-wrap:anywhere}}.tone-rise{{border-top-color:var(--red)}}.tone-fall{{border-top-color:var(--green)}}.dashboard-grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}}.panel{{padding:20px;min-width:0}}.wide{{grid-column:span 2}}.panel-head{{display:flex;justify-content:space-between;gap:12px;align-items:center;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:14px}}h2{{font-size:19px;letter-spacing:-.03em}}.thesis{{font-size:15px;line-height:1.8}}.evidence-table,.scenario-table,table{{border-collapse:collapse;width:100%;font-size:12px}}td,th{{text-align:left;padding:9px;border-bottom:1px solid var(--line);vertical-align:top}}.evidence-table td:nth-child(2){{min-width:260px}}.engine-list,.timeline,.risk-list{{margin:0;padding:0;list-style:none}}.engine-list li,.timeline li,.risk-list li{{padding:10px 0;border-bottom:1px solid rgba(216,205,187,.55);display:grid;gap:4px;line-height:1.6}}.timeline time{{font:700 11px/1 "SFMono-Regular",Consolas,monospace;color:var(--gold)}}.risk-list strong{{color:var(--red)}}.risk-list span{{font-size:13px}}.signal-area{{margin-top:10px;background:#e3d4bc;padding:20px;border-left:5px solid var(--gold)}}.gaps{{margin:0;padding-left:20px;line-height:1.7}}.technical-state{{font:700 11px/1 "SFMono-Regular",Consolas,monospace;color:var(--muted)}}.source-box{{margin-top:10px;background:var(--paper-2);padding:20px;overflow:auto}}a{{color:#245d58;word-break:break-all}}.empty{{color:var(--muted);line-height:1.7}}footer{{margin-top:20px;color:#cfc5b4;font-size:12px;line-height:1.7}}@media(max-width:760px){{main{{padding:22px 14px 40px}}.masthead{{display:block}}.asof{{text-align:left;margin-top:16px}}.hero-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}.metric-card{{min-height:125px;padding:15px}}.metric-card strong{{font-size:16px}}.dashboard-grid{{grid-template-columns:1fr}}.wide{{grid-column:auto}}.evidence-table,.scenario-table{{font-size:11px}}.evidence-table th:nth-child(4),.evidence-table td:nth-child(4){{display:none}}}}
</style></head><body><main><header class="masthead"><div><p class="eyebrow">A-SHARE / COMPANY RESEARCH</p><h1>{html_text(meta["company"])}</h1></div><p class="asof">{html_text(meta["ticker"])} · {html_text(meta["exchange"])}<br />截止 {html_text(meta["as_of"])}<br />访问 {html_text(meta["accessed_at"])}</p></header><div class="coverage">{badge("事实")} {fact_count} 条事实 · {badge("推断")} {sum(item["kind"] == "推断" for item in data["evidence"])} 条推断 · {badge("判断")} {sum(item["kind"] == "判断" for item in data["evidence"])} 条判断 · <span class="badge badge-inference">{html_text(meta["mode"])} · 置信度 {html_text(meta["confidence"])}</span></div><section class="hero-grid" aria-label="研究摘要">{cards(summary)}</section><section class="dashboard-grid"><article class="panel wide"><div class="panel-head"><h2>研究结论</h2><span>{html_text(summary["research_label"])}</span></div><p class="thesis"><strong>市场当前逻辑：</strong>{html_text(summary["market_view"])}</p><p class="thesis"><strong>证据支持：</strong>{html_text(summary["evidence_view"])}</p></article><article class="panel wide"><div class="panel-head"><h2>关键证据台账</h2><span>{len(data["evidence"])} 条</span></div><table class="evidence-table"><thead><tr><th>事实或指标</th><th>内容</th><th>类型</th><th>来源与时间</th></tr></thead><tbody>{"".join(evidence_rows) or '<tr><td colspan="4">未取得可验证证据。</td></tr>'}</tbody></table></article><article class="panel"><div class="panel-head"><h2>业务与利润引擎</h2><span>机制</span></div><ul class="engine-list">{engine}</ul></article><article class="panel"><div class="panel-head"><h2>催化剂日历</h2><span>{html_text(meta["period"])}</span></div><ul class="timeline">{catalysts}</ul></article><article class="panel wide"><div class="panel-head"><h2>估值与情景</h2><span>{html_text(data["valuation"]["method"])}</span></div><p class="section-note">{html_text(data["valuation"]["conclusion"])}</p><table class="scenario-table"><thead><tr><th>情景</th><th>业务假设</th><th>触发条件</th></tr></thead><tbody>{scenarios}</tbody></table></article><article class="panel"><div class="panel-head"><h2>风险与证伪</h2><span>至少三项</span></div><ul class="risk-list">{risks}</ul></article><article class="panel"><div class="panel-head"><h2>技术面</h2><span class="technical-state">{html_text(technical["availability"])}</span></div>{technical_html}</article></section><section class="signal-area"><div class="panel-head"><h2>待核验与研究限制</h2><span>证据优先</span></div>{list_items(data["gaps"])}</section><section class="source-box"><div class="panel-head"><h2>信息来源</h2><span>{len(data["sources"])} 个来源</span></div><table><thead><tr><th>来源</th><th>URL</th></tr></thead><tbody>{source_rows}</tbody></table></section><footer>本报告区分事实、推断与判断，仅作为研究框架与情景推演，不构成个性化投资建议。</footer></main></body></html>'''


def main() -> int:
    args = parse_args()
    try:
        data = validate(json.loads(args.input.read_text(encoding="utf-8")))
        if args.check:
            print(f"✅ 公司研究输入验证通过：{data['meta']['company']}，{len(data['evidence'])} 条证据，{len(data['sources'])} 个来源")
            return 0
        if not args.out:
            raise ValueError("生成 HTML 时必须提供 --out")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(render(data), encoding="utf-8")
        print(f"✅ 已生成 {args.out}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
