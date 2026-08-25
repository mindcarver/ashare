# A股筛选数据契约

构造筛选输入或排查筛选结果时读取本文件。筛选器只消费已经规范化的证据，不负责猜测字段含义。

## 顶层结构

```json
{
  "schema_version": "1.0",
  "universe": {
    "name": "沪深300",
    "description": "截止日有效成分股",
    "members_as_of": "2026-08-25",
    "published_at": "2026-08-25",
    "fetched_at": "2026-08-25T08:00:00+08:00",
    "source": {
      "id": "csi-000300-members",
      "name": "中证指数有限公司成分股列表",
      "url": "https://example.com/replace-with-real-universe-source"
    }
  },
  "stocks": [
    {
      "code": "600519",
      "name": "贵州茅台",
      "market": "SSE",
      "board": "main",
      "industry": "白酒",
      "metrics": {
        "roe_ttm": {
          "value": 31.2,
          "unit": "percent",
          "period_type": "ttm",
          "observed_at": "2026-06-30",
          "published_at": "2026-08-13",
          "fetched_at": "2026-08-25T08:30:00+08:00",
          "source": {
            "id": "sse-2026-h1-report",
            "name": "上海证券交易所半年报",
            "url": "https://example.com/replace-with-real-source"
          }
        }
      }
    }
  ]
}
```

实际数据必须把示例 URL 换成真实、可访问来源。

`universe` 本身也必须可审计。`members_as_of` 和 `published_at` 均不得晚于筛选 `as_of`，避免用今天的指数成分股或上市公司列表回放过去。用户自定义本地列表可以使用绝对 `file:///` URL，并保留抓取/整理时间。

## 时间语义

- `observed_at`：数值对应的行情日或报告期末。
- `published_at`：外部世界首次可获得该证据的日期；点时筛选以此防未来信息泄漏。
- `fetched_at`：本次取得证据的时间，可晚于 `as_of`，用于审计回放过程。
- `as_of`：筛选截止日。只有 `observed_at <= as_of` 且 `published_at <= as_of` 的指标可用于当次筛选。

不要把财报期末当成发布日期。例如半年报对应 6 月 30 日，不代表 6 月 30 日市场已经知道半年报内容。

## 期间类型

`period_type` 只能是：

- `spot`：某一交易日行情或估值。
- `point_in_time`：资产负债表类时点值。
- `single_quarter`：单季度流量。
- `cumulative_ytd`：年初至报告期累计流量。
- `ttm`：过去十二个月。
- `annual`：完整年度。

季度收入、利润和现金流不得把 Q1、半年累计、前三季度累计、全年累计直接相加。需要单季度值时，使用相邻累计值相减；需要 TTM 时，使用四个互不重叠的单季度值相加。

## 规范指标与单位

| 指标 | 单位 | 说明 |
|---|---|---|
| `price` | `CNY` | 截止日收盘价或明确标注的行情价 |
| `market_cap` | `CNY` | 总市值，不使用“亿元”缩放 |
| `pe_ttm` / `pb` / `ps_ttm` | `multiple` | 倍数 |
| `roe_ttm` / `roa_ttm` | `percent` | 百分点，15 表示 15% |
| `gross_margin` / `net_margin` | `percent` | 百分点 |
| `revenue_growth` / `net_profit_growth` | `percent` | 同比百分点 |
| `debt_ratio` / `dividend_yield` | `percent` | 百分点 |
| `current_ratio` / `quick_ratio` / `ocf_to_net_profit` | `ratio` | 比值，1.2 表示 1.2 倍 |
| `inventory_days` | `days` | 天数 |

筛选器允许其他数值指标，但使用者必须定义单位和期间。规范指标若单位错误会被拒绝。

## 来源规则

`source.id`、`source.name`、`source.url` 都是必需字段。来源应尽量指向具体公告、数据页或接口说明，而不是搜索结果页。

同一股票的不同指标可以来自不同来源。发生冲突时保留各来源、说明采信理由，并在输入中只放入最终采信值；不要平均不同口径的数字。

## 数据准备门

写入输入前确认：

- 股票池成分本身也符合截止日期，避免用今天的成分股回测过去。
- 退市股、暂停上市股和新上市股没有被当前列表造成幸存者偏差。
- 指标口径对所有股票一致；银行等特殊行业需要单独规则或分组筛选。
- 缺失值使用缺字段表达，不使用 0、空字符串或行业均值填充。
