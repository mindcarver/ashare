# 公司研究可视化输入契约

标准/深度公司研究必须同时交付 HTML 仪表盘；快速诊断在用户要求“可视化/HTML/研报页面”时也使用同一契约。先完成既有研究流程，再把已验证的结果写成 `company-research.json`，由 `scripts/generate_company_research_html.py` 渲染。

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
  "dashboard": {
    "headline_thesis": {"statement": "一句研究命题", "detail": "一句解释"},
    "signals": [
      {"label": "信号名", "value": "数值或待核验", "detail": "最多60字", "kind": "事实", "tone": "red", "source_id": "source-id"}
    ],
    "expectation_gap": {"market_pricing": "", "verified_facts": "", "next_proof": ""},
    "catalysts": [{"title": "", "detail": ""}],
    "invalidations": [{"title": "", "detail": ""}]
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

- `dashboard.signals` 必须恰好有 5 项。每项只允许简短的 `label/value/detail`；`detail` 最多60字。事实信号必须带有效 `source_id`。
- `headline_thesis.statement/detail`、预期差三列、催化和证伪也有长度限制；生成器拒绝将大段报告文字塞回首层。
- 每个 `事实` 证据必须有 `source_id`、`observed_at` 和 `published_at`；来源需在 `sources` 中有 `id/name/url`，且 `published_at <= as_of`。
- `推断` 与 `判断` 必须与事实分开，不得伪装成披露数据。
- `technical.availability != available` 时只显示“技术面未验证”和原因；不得补均线、支撑位、MACD 或价格。
- `gaps` 必须保留未核验项；空数据不填 0、行业均值或模型默认值。
- 禁止 `建议买入/建议卖出/目标价/目标仓位/建议加仓/建议减仓/建议满仓/建议清仓/保证收益`。
- HTML首层必须显示：研究命题、五个关键信号、市场定价/已验证事实/下一步验证、催化与证伪。关键证据台账、业务与利润引擎、估值与情景、风险与证伪、技术面、待核验限制和信息来源在第二层按需展开。所有面向读者的栏目和标签必须使用中文。视觉沿用报告族共享的「ASHARE EDITORIAL」品牌设计系统（`skills/_shared/`：白纸黑字最高对比、可见 32px 网格、纯黑 2px 结构线、零圆角、7px 硬投影、宋体正文 + 等宽来源元数据），本技能只保留 `.thesis` / `.signal` 卡内排版与三档 `.panel.market` / `.facts` / `.proof` 顶规。
