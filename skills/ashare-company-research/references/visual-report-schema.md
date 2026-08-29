# 公司研究可视化输入契约

当用户要求标准/深度公司研究的 HTML 可视化，或明确要求“可视化/HTML/研报页面”时，先完成既有研究流程，再把已验证的结果写成 `company-research.json`，由 `scripts/generate_company_research_html.py` 渲染。

生成器不采集数据、不计算估值、不补全缺口；它只将已验证事实、显式推断和研究判断排版为静态报告。

## 命令

```bash
python3 scripts/generate_company_research_html.py \
  --input company-research.json \
  --out company-research-000001-SZ-2026-08-29.html
```

只验证输入契约：

```bash
python3 scripts/generate_company_research_html.py --input company-research.json --check
```

## 最小结构

```json
{
  "meta": {
    "company": "公司名称",
    "ticker": "000001.SZ",
    "exchange": "深交所",
    "as_of": "YYYY-MM-DD",
    "accessed_at": "ISO-8601 datetime",
    "period": "1个月到6个月",
    "mode": "标准报告",
    "confidence": "中"
  },
  "summary": {
    "research_label": "观察",
    "market_view": "市场当前如何理解公司",
    "evidence_view": "证据支持的真实经营状态",
    "expectation_gap": "差异来自哪里",
    "valuation_view": "适用估值方法和边界",
    "primary_risk": "最重要失败风险"
  },
  "evidence": [],
  "business_engine": [],
  "catalysts": [],
  "valuation": {"method": "", "conclusion": "", "scenarios": []},
  "risks": [],
  "technical": {"availability": "unknown", "status_reason": "技术面未验证"},
  "gaps": [],
  "sources": []
}
```

## 约束

- 每个 `事实` 证据必须有 `source_id`、`observed_at` 和 `published_at`；来源需在 `sources` 中有 `id/name/url`，且 `published_at <= as_of`。
- `推断` 与 `判断` 必须与事实分开，不得伪装成披露数据。
- `technical.availability != available` 时只显示“技术面未验证”和原因；不得补均线、支撑位、MACD 或价格。
- `gaps` 必须保留未核验项；空数据不填 0、行业均值或模型默认值。
- 禁止 `建议买入/建议卖出/目标价/目标仓位/建议加仓/建议减仓/建议满仓/建议清仓/保证收益`。
- 输出 HTML 的视觉系统与 `ashare-daily-market-review` 和 `ashare-capital-environment-dashboard` 一致：深墨绿网格背景、宋体正文、金色眉题、米白纸张卡、细棕边和 5px 硬投影。
