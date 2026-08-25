# A股研究日志数据契约

创建快照、追加结果或解释统计时读取本文件。

## 快照

顶层`schema_version`固定为`1.0`。必填字段：

| 字段 | 含义 |
|---|---|
| `research_id` | 用户或Agent生成的稳定唯一ID |
| `code/name/market` | 研究对象 |
| `as_of` | 研究截止日 |
| `evaluation_date` | 明确评价日，不自动推算交易日 |
| `horizon_label` | 人类可读周期说明 |
| `thesis` | 当时可证伪的核心假设 |
| `probability` | 可选，0到1 |
| `benchmark_code` | 使用基准时必填，标识指数或比较资产 |
| `criterion` | 结构化成功标准 |
| `baseline` | 股票及可选基准的基线证据 |
| `catalysts/falsifiers` | 当时定义的验证和证伪条件 |
| `evidence` | 支撑研究的证据列表 |

`criterion.metric`支持：

- `stock_return_pct`
- `benchmark_return_pct`
- `excess_return_pct`
- `max_drawdown_pct`
- `max_favorable_excursion_pct`
- `max_adverse_excursion_pct`

操作符：`lt/lte/gt/gte/eq/ne`。使用基准或超额指标时`baseline.benchmark`必填。
`probability`表示最终`passed`为真的主观概率，即同时满足成功标准且没有触发预定义证伪条件。

## 价格和研究证据

价格证据：

```json
{
  "value": 10.0,
  "unit": "CNY",
  "observed_at": "2026-08-01",
  "published_at": "2026-08-01",
  "fetched_at": "2026-08-01T18:00:00+08:00",
  "source": {
    "id": "provider-symbol-date",
    "name": "来源名称",
    "url": "https://example.com/replace-with-real-source"
  }
}
```

研究证据使用相同时间与来源字段，并增加`claim`。`observed_at`和`published_at`必须不晚于快照`as_of`。

## 结果

结果输入包含：

- 与快照一致的`research_id`和`evaluation_date`。
- `stock_path`；有基准时包含`benchmark_path`。
- `falsifiers_triggered`，只能引用原快照已定义的证伪条件。
- 可选`notes`。

价格路径至少两个点、日期严格递增；第一个点必须等于快照基线。所有观察日和发布日期不得晚于`evaluation_date`。

## 计算口径

```text
区间收益 = 终点价格 / 基线价格 - 1
超额收益 = 股票收益 - 基准收益
最大回撤 = min(当前价格 / 此前峰值 - 1)
MFE = max(路径价格 / 基线价格 - 1)
MAE = min(路径价格 / 基线价格 - 1)
Brier = mean((预测概率 - 实际passed)^2)
```

这里的最大回撤只覆盖输入价格路径。路径缺交易日会低估真实回撤，报告必须说明覆盖范围。

## 不可变性

- 相同research_id不能再次record。
- 同一research_id不能再次observe。
- SQLite同时保存原始规范JSON和SHA-256。
- 需要修正时创建新research_id并在thesis或evidence中引用原ID；不得改写历史。
