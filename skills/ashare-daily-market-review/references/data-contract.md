# A股每日盘面数据契约

采集每日数据、构造输入或解释覆盖状态时读取本文件。

## 顶层

```json
{
  "schema_version": "1.0",
  "market_date": "2026-08-25",
  "as_of": "2026-08-25",
  "sections": {},
  "verification_points": []
}
```

`market_date`不得晚于`as_of`，命令行`--as-of`必须与输入一致。

## 章节状态

八个章节统一使用：

```json
{
  "availability": "available|partial|unknown",
  "status_reason": "覆盖或缺失原因"
}
```

- `available`：本章必需字段、日期和来源完整。
- `partial`：有可用证据但覆盖或时点不完整；必须说明缺什么。
- `unknown`：没有可用数值；不得填0或携带伪数据。

`indices/breadth/short_term_sentiment/turnover/sectors/style`标记available时，代表当日的核心证据必须满足`observed_at == market_date`。滞后数据只能标partial。

## 数值证据

```json
{
  "value": 1.2,
  "unit": "percent",
  "observed_at": "2026-08-25",
  "published_at": "2026-08-25",
  "fetched_at": "2026-08-25T16:00:00+08:00",
  "source": {
    "id": "provider-endpoint-date",
    "name": "来源名称",
    "url": "https://example.com/replace-with-real-source"
  }
}
```

规范单位：

- 指数点：`index_points`
- 涨跌幅和相对变化：`percent`
- 家数：`count`
- 金额：`CNY`
- 其他指标保留清晰单位，不做隐式缩放。

## 八个章节

### indices

`items`中每项包含`id/name/primary/close/change_pct`。必须且只能有一个`primary=true`，用于显式指数—宽度背离。

### breadth

`metrics`支持`advancers/decliners/unchanged/limit_up/limit_down`。available时五项必填。

若`short_term_sentiment`为available，`breadth`还必须给出非空`universe`，如“全A非ST普通股”；其值必须与短线情绪章节完全一致。

### short_term_sentiment

短线情绪章节只描述市场状态，不生成仓位、买卖或个股指令。它必须给出非空`universe`和`methodology`，并使用与`breadth`相同的股票池和交易日：

- `open_board_failed`：炸板次数，单位`count`。
- `limit_attempts`：用于计算炸板率的封板尝试次数，单位`count`，必须大于0且不小于`open_board_failed`。
- `highest_streak`：最高连板高度，单位`count`。

`availability=available`时三项均必填且`observed_at == market_date`。炸板率为`open_board_failed / limit_attempts`，必须记录供应商对两项计数的定义；不把“最终涨停家数”替代为分母。

可选`previous_metrics`可提供上一可比交易日的同名三项，以及`limit_up`、`limit_down`。其来源、观察日和单位与当前指标相同，但观察日必须早于`market_date`。只有前后两组完整且口径一致时，才评估“修复”。详细状态规则见[短线情绪规则](short-term-sentiment.md)。

### turnover

`metrics.amount`为当日成交额；`previous_amount`为前一可比交易日；可选`avg_5d_amount/avg_20d_amount`。所有金额使用CNY。

### sectors

必须给`classification`，如“申万一级”。`items`包含`id/name/change_pct`，不得把申万行业、概念板块和地域板块混排。

### funds

每项包含`name/methodology/metric`。`methodology`必须说明数据是交易所事实、余额差分还是供应商模型；来源不透明则unknown。

### style

每项包含`name/interpretation/metric`。相对强弱必须说明正负值代表什么。

### events

每项包含`title/event_date/published_at/fetched_at/source`。事件必须在as-of时已经公开。

## 后续验证点

`verification_points`可以包含as-of之后的事件日期，但其日历信息本身必须在as-of前已经发布。这些是未来验证安排，不是未来事实。

## 派生口径

```text
上涨占比 = 上涨家数 / (上涨 + 下跌 + 平盘)
涨跌家数比 = 上涨家数 / 下跌家数
成交变化 = 当日成交额 / 比较成交额 - 1
```

下跌家数为0时涨跌比输出unknown，不制造无穷大。输入缺失时不计算对应派生指标。
