#!/usr/bin/env python3
"""将已核验的新闻标的提取 JSON 渲染为自包含研究 HTML。"""

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


# 本技能自有 100 分评分模型，「总分」是合法字段，因此用允许评分词的 tier，
# 但仍禁止一切价格锚点（止损/止盈/买入观察价/目标价位）。
# 禁词表唯一真源：skills/_shared/forbidden-terms.json
FORBIDDEN = forbidden_terms("score_ok")
SCORE_LIMITS = {
    "news_intensity": 20,
    "relevance": 20,
    "expectation_gap": 15,
    "earnings_elasticity": 15,
    "price_position": 10,
    "sector_strength": 10,
    "fund_trace": 10,
}
TIERS = {"一级受益", "二级受益", "三级概念", "伪受益或风险"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成新闻标的提取可视化 HTML")
    parser.add_argument("--input", required=True, type=Path, help="news-targets.json")
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


def objects(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{field} 必须是对象数组")
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
    news = data.get("news")
    chain = data.get("transmission_chain")
    if not isinstance(meta, dict) or not isinstance(news, dict) or not isinstance(chain, dict):
        raise ValueError("meta、news 和 transmission_chain 必须是对象")
    for key in ("headline", "market", "as_of", "accessed_at", "source_trust"):
        text(meta.get(key), f"meta.{key}")
    as_of = parse_day(meta["as_of"], "meta.as_of")
    for key in ("source_id", "published_at", "category", "strength", "one_line"):
        text(news.get(key), f"news.{key}")
    if parse_day(news["published_at"], "news.published_at") > as_of:
        raise ValueError("新闻发布时间晚于 as_of")
    for key in ("event", "industry_variable", "company_impact", "expectation_state", "verification_node"):
        text(chain.get(key), f"transmission_chain.{key}")

    sources = objects(data.get("sources"), "sources")
    source_ids = set()
    for index, source in enumerate(sources):
        for key in ("id", "name", "url"):
            text(source.get(key), f"sources[{index}].{key}")
        if urlparse(source["url"]).scheme not in {"http", "https"}:
            raise ValueError("来源 URL 必须是 http 或 https")
        if source["id"] in source_ids:
            raise ValueError(f"sources.id 重复：{source['id']}")
        source_ids.add(source["id"])
    if news["source_id"] not in source_ids:
        raise ValueError("新闻引用了未知来源")

    candidates = objects(data.get("candidates"), "candidates")
    if not candidates:
        raise ValueError("至少需要一个候选标的")
    ranks = set()
    for index, item in enumerate(candidates):
        for key in ("rank", "company", "tier", "role", "logic", "evidence", "market_priced", "risk"):
            if key == "rank":
                if not isinstance(item.get(key), int) or item[key] < 1:
                    raise ValueError(f"candidates[{index}].rank 必须是正整数")
            else:
                text(item.get(key), f"candidates[{index}].{key}")
        if item["rank"] in ranks:
            raise ValueError("候选标的排名重复")
        ranks.add(item["rank"])
        if item["tier"] not in TIERS:
            raise ValueError("候选标的层级非法")
        if item.get("ticker") is not None and not isinstance(item["ticker"], str):
            raise ValueError("ticker 必须是字符串或 null")
        if not isinstance(item.get("verification"), list) or not all(isinstance(v, str) and v.strip() for v in item["verification"]):
            raise ValueError("候选标的 verification 必须是非空字符串数组")
        score = item.get("score")
        if not isinstance(score, dict):
            raise ValueError("候选标的 score 必须是对象")
        pending = score.get("pending", [])
        if not isinstance(pending, list) or any(field not in SCORE_LIMITS for field in pending):
            raise ValueError("score.pending 包含未知维度")
        for field, limit in SCORE_LIMITS.items():
            value = score.get(field)
            if not isinstance(value, int) or value < 0 or value > limit:
                raise ValueError(f"score.{field} 超出范围")
            if field in pending and value != 0:
                raise ValueError(f"待核验 score.{field} 必须按0分处理")

    for field, keys in {
        "deep_updates": ("company", "status", "content", "impact"),
        "technical": ("company", "availability"),
        "watch_plan": ("window", "item", "strengthen", "weaken"),
    }.items():
        for index, item in enumerate(objects(data.get(field, []), field)):
            for key in keys:
                text(item.get(key), f"{field}[{index}].{key}")
            if field == "technical":
                if item["availability"] not in {"available", "partial", "unknown"}:
                    raise ValueError("technical.availability 必须是 available/partial/unknown")
                if item["availability"] == "available":
                    text(item.get("summary"), f"technical[{index}].summary")
                else:
                    text(item.get("status_reason"), f"technical[{index}].status_reason")

    gaps = data.get("gaps", [])
    if not isinstance(gaps, list) or not all(isinstance(item, str) and item.strip() for item in gaps):
        raise ValueError("gaps 必须是非空字符串数组")
    return data


def total_score(candidate: dict[str, Any]) -> tuple[int, float, int]:
    score = candidate["score"]
    total = sum(score[field] for field in SCORE_LIMITS)
    pending = score.get("pending", [])
    available_max = 100 - sum(SCORE_LIMITS[field] for field in pending)
    adjusted = total / available_max * 100 if available_max else 0
    return total, adjusted, len(pending)


def tier_class(tier: str) -> str:
    return {"一级受益": "tier-one", "二级受益": "tier-two", "三级概念": "tier-three", "伪受益或风险": "tier-risk"}[tier]


def render(data: dict[str, Any]) -> str:
    meta, news, chain = data["meta"], data["news"], data["transmission_chain"]
    ordered = sorted(data["candidates"], key=lambda item: item["rank"])
    candidate_cards = "".join(
        f'<article class="candidate-card {tier_class(item["tier"])}"><div class="candidate-head"><span>{html_text(item["tier"])}</span><strong>#{item["rank"]} {html_text(item["company"])}</strong><small>{html_text(item.get("ticker") or "代码待核验")}</small></div><p>{html_text(item["logic"])}</p><div class="candidate-meta"><span>{html_text(item["role"])}</span><b>{total_score(item)[1]:.1f}</b><small>调整后分 · {total_score(item)[2]} 项待核验</small></div></article>'
        for item in ordered
    )
    score_rows = "".join(
        f'<tr><td>#{item["rank"]} {html_text(item["company"])}</td><td>{item["score"]["news_intensity"]}</td><td>{item["score"]["relevance"]}</td><td>{item["score"]["expectation_gap"]}</td><td>{item["score"]["earnings_elasticity"]}</td><td>{item["score"]["price_position"]}</td><td>{item["score"]["sector_strength"]}</td><td>{item["score"]["fund_trace"]}</td><td><strong>{total_score(item)[1]:.1f}</strong></td></tr>'
        for item in ordered
    )
    updates = "".join(
        f'<li><strong>{html_text(item["company"])} · {html_text(item["status"])}</strong><span>{html_text(item["content"])}</span><small>对评分影响：{html_text(item["impact"])}</small></li>'
        for item in data["deep_updates"]
    ) or '<li>尚未形成可更新的深度补充记录。</li>'
    technical = "".join(
        f'<li><strong>{html_text(item["company"])}</strong><span>{html_text(item.get("summary") if item["availability"] == "available" else "技术面未验证：" + item["status_reason"])}</span></li>'
        for item in data["technical"]
    ) or '<li>技术面未验证：未提供可复核的OHLCV数据。</li>'
    watch_rows = "".join(
        f'<tr><td>{html_text(item["window"])}</td><td>{html_text(item["item"])}</td><td>{html_text(item["strengthen"])}</td><td>{html_text(item["weaken"])}</td></tr>'
        for item in data["watch_plan"]
    ) or '<tr><td colspan="4">暂无观察计划。</td></tr>'
    source_rows = "".join(
        f'<tr><td>{html_text(item["name"])}</td><td><a href="{html_text(item["url"])}" rel="noreferrer" target="_blank">{html_text(item["url"])}</a></td></tr>'
        for item in data["sources"]
    )
    gaps = "".join(f"<li>{html_text(item)}</li>" for item in data["gaps"]) or '<li>未记录额外数据缺口。</li>'

    return inject_shared_css(f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width,initial-scale=1" /><meta name="robots" content="noindex,nofollow" /><title>新闻标的提取 · {html_text(meta["headline"])}</title><style>:root{{}}
main{{max-width:1180px;margin:auto;padding:32px 20px 56px}}
/* 候选卡：顶规标识分层，内部三段式（头部 / 说明 / 评分） */
.candidate-grid .candidate-card{{border-top:4px solid var(--accent);display:flex;flex-direction:column}}
.candidate-head{{display:grid;gap:4px}}
.candidate-head span{{font-family:var(--font-mono);font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-tertiary)}}
.candidate-head strong{{font-family:var(--font-display);font-size:19px;letter-spacing:-.02em}}
.candidate-head small{{font-family:var(--font-mono);font-size:11px;color:var(--ink-secondary)}}
.candidate-card p{{margin:14px 0;font-size:13.5px;line-height:1.7;color:var(--ink-secondary)}}
.candidate-meta{{border-top:var(--hair) solid var(--line);padding-top:10px;display:grid;grid-template-columns:1fr auto;gap:4px;align-items:end}}
.candidate-meta span{{font-family:var(--font-ui);font-size:11px;color:var(--ink-tertiary)}}
.candidate-meta b{{font-family:var(--font-mono);font-size:25px;font-weight:700;line-height:1;letter-spacing:-.04em;color:var(--accent)}}
.candidate-meta small{{grid-column:1/-1}}
/* 传导链：五格等分，格间用发丝线分隔 */
.chain-grid div{{min-width:0;padding-right:10px}}
.chain-grid div+div{{border-left:var(--hair) solid var(--line);padding-left:10px}}
.chain-grid span{{display:block;font-family:var(--font-mono);font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase;color:var(--ink-tertiary)}}
.chain-grid b{{display:block;margin-top:8px;font-family:var(--font-body);font-size:13.5px;font-weight:600;line-height:1.55}}
@media(max-width:760px){{main{{padding:22px 14px 40px}}}}</style></head><body><main><header class="masthead"><div><p class="eyebrow">A-SHARE / NEWS TARGETS</p><h1>新闻标的提取</h1></div><p class="asof">{html_text(meta["market"])}<br />截止 {html_text(meta["as_of"])}<br />访问 {html_text(meta["accessed_at"])}</p></header><div class="coverage"><span class="badge badge-available">新闻可信度 {html_text(meta["source_trust"])}</span><span class="badge badge-partial">{len(ordered)} 个候选</span><span class="badge badge-unknown">待核验项按0分换算</span></div><section class="hero-grid" aria-label="新闻摘要"><article class="metric-card metric-text"><p>新闻一句话结论</p><strong>{html_text(news["one_line"])}</strong></article><article class="metric-card metric-text"><p>新闻分类</p><strong>{html_text(news["category"])} · {html_text(news["strength"])}</strong></article><article class="metric-card metric-text"><p>核心行业变量</p><strong>{html_text(chain["industry_variable"])}</strong></article><article class="metric-card metric-text"><p>后续验证</p><strong>{html_text(chain["verification_node"])}</strong></article></section><section class="chain"><div class="panel-head"><h2>新闻传导链</h2><span>证据优先</span></div><div class="chain-grid"><div><span>新闻事件</span><b>{html_text(chain["event"])}</b></div><div><span>行业变量</span><b>{html_text(chain["industry_variable"])}</b></div><div><span>公司影响</span><b>{html_text(chain["company_impact"])}</b></div><div><span>市场预期</span><b>{html_text(chain["expectation_state"])}</b></div><div><span>验证节点</span><b>{html_text(chain["verification_node"])}</b></div></div></section><section class="dashboard-grid"><article class="panel wide"><div class="panel-head"><h2>候选标的分层</h2><span>一级/二级/三级/风险</span></div><div class="candidate-grid">{candidate_cards}</div></article><article class="panel wide"><div class="panel-head"><h2>评分与待核验</h2><span>待核验维度按0分换算</span></div><table class="score-table"><thead><tr><th>标的</th><th>新闻</th><th>关联</th><th>预期差</th><th>业绩</th><th>股价</th><th>板块</th><th>资金</th><th>调整后分</th></tr></thead><tbody>{score_rows}</tbody></table></article><article class="panel"><div class="panel-head"><h2>前3名标的深度补充</h2><span>阶段B</span></div><ul class="update-list">{updates}</ul></article><article class="panel"><div class="panel-head"><h2>技术面与资金确认</h2><span>阶段C</span></div><ul class="technical-list">{technical}</ul></article><article class="panel wide"><div class="panel-head"><h2>观察计划</h2><span>条件而非指令</span></div><table><thead><tr><th>时间窗口</th><th>观察事项</th><th>强化信号</th><th>弱化信号</th></tr></thead><tbody>{watch_rows}</tbody></table></article></section><section class="chain"><div class="panel-head"><h2>数据缺口与限制</h2><span>不强行闭合</span></div><ul class="gaps">{gaps}</ul></section><section class="source-box"><div class="panel-head"><h2>信息来源</h2><span>{len(data["sources"])} 个来源</span></div><table><thead><tr><th>来源</th><th>URL</th></tr></thead><tbody>{source_rows}</tbody></table></section><footer>本报告只呈现新闻驱动研究线索、观察条件和风险证伪，不构成个性化投资建议。</footer></main></body></html>''')


def main() -> int:
    args = parse_args()
    try:
        data = validate(json.loads(args.input.read_text(encoding="utf-8")))
        if args.check:
            print(f"✅ 新闻标的输入验证通过：{len(data['candidates'])} 个候选，{len(data['sources'])} 个来源")
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
