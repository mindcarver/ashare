# 新闻标的可视化输入契约

当用户要求“可视化/HTML/研报页面”，或完整新闻标的提取需要随研究结论交付静态页面时，先完成现有新闻原文、传导链、候选分层、评分和核验流程，再将结果写成 `news-targets.json`，由 `scripts/generate_news_targets_html.py` 渲染。

生成器不读取新闻链接、不抓取行情、不补股票代码、不调用技术指标。它只呈现已验证的研究结果和明确的待核验缺口。

## 命令

```bash
python3 scripts/generate_news_targets_html.py \
  --input news-targets.json \
  --out news-targets-2026-08-29.html
```

只验证输入：

```bash
python3 scripts/generate_news_targets_html.py --input news-targets.json --check
```

## 最小结构

```json
{
  "meta": {
    "headline": "新闻标题",
    "market": "中国A股",
    "as_of": "YYYY-MM-DD",
    "accessed_at": "ISO-8601 datetime",
    "source_trust": "高/中/低"
  },
  "news": {
    "source_id": "source-id",
    "published_at": "YYYY-MM-DD",
    "category": "政策类",
    "strength": "强/中/弱",
    "one_line": "新闻一句话结论"
  },
  "transmission_chain": {
    "event": "",
    "industry_variable": "",
    "company_impact": "",
    "expectation_state": "",
    "verification_node": ""
  },
  "candidates": [],
  "deep_updates": [],
  "technical": [],
  "watch_plan": [],
  "gaps": [],
  "sources": []
}
```

## 评分与缺口规则

- 每个候选使用 100 分维度：新闻强度20、关联强度20、预期差15、业绩弹性15、股价位置10、板块强度10、资金痕迹10。
- 实时股价、板块强度、资金痕迹无法核验时，写入 `pending`，该维度必须按 0 分处理；生成器显示“调整后分”和待核验项数。
- `ticker` 可以为空或写“代码待核验”；生成器绝不补代码。
- 新闻的 `published_at` 必须不晚于 `as_of`；新闻来源必须在 `sources` 中存在，且 URL 只能是 HTTP(S)。
- `technical.availability != available` 时只显示“技术面未验证”和原因，不显示K线、均线、MACD、支撑压力或任何价格。
- 禁止 `建议买入/建议卖出/目标价/目标仓位/建议加仓/建议减仓/建议满仓/建议清仓/保证收益`。

## 视觉交付

HTML必须显示新闻传导链、候选分层、评分与待核验、前3名深度补充、技术面与资金确认、观察计划、数据缺口与来源。页面沿用 `ashare-daily-market-review` 与 `ashare-capital-environment-dashboard` 的深墨绿网格、宋体正文、金色眉题、米白硬投影卡和红涨绿跌研报风。
