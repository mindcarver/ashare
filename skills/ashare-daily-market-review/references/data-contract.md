# A股每日盘面数据契约

采集每日数据、构造输入、写入历史或解释覆盖状态时读取本文件。当前版本为 `1.1`。

## 顶层与快照

```json
{
  "schema_version": "1.1",
  "market_date": "2026-08-25",
  "as_of": "2026-08-25",
  "snapshot": {
    "type": "close",
    "cutoff_at": "2026-08-25T18:00:00+08:00",
    "revision": 1,
    "supersedes_sha256": null,
    "raw_evidence_sha256": "64位小写SHA-256"
  },
  "sections": {},
  "verification_points": []
}
```

- `market_date`不得晚于`as_of`，命令行`--as-of`必须与输入一致。
- `snapshot.type`只能是`close/post_close/weekend_update`。
- `cutoff_at`必须带时区；所有`published_at/fetched_at`不得晚于该截止时间。
- `close`快照的截止日期必须等于`market_date`；盘后或周末补充使用另外两类。
- 同日首版`revision=1`且`supersedes_sha256=null`；后续修订递增并指向上一修订的输入SHA。
- `raw_evidence_sha256`是采集原始证据清单或原始响应包的SHA，不是报告输出SHA。

## 版本化历史

使用`--history-dir PATH`时，生成器把已验证输入追加保存为：

```text
PATH/YYYY-MM-DD/rNNN-<input-sha前12位>.json
```

- 相同输入SHA幂等跳过，不重复写入。
- 同日不同SHA必须作为下一修订追加，不能覆盖旧版。
- 摘要计算前一交易日、20/60日分位和情绪状态连续天数；样本不足时输出`null/样本不足`。
- 历史比较按每个交易日的最高修订计算。

### 1.0兼容归一化

生成器可以直接读取历史`schema_version=1.0`产物，以便真实旧复盘继续重放。归一化遵循fail closed：

- 原始输入文件SHA作为`raw_evidence_sha256`，最晚`fetched_at`作为`cutoff_at`。
- 能从字段名明确识别的5日、20日或当日窗口才补入`window`。
- 旧方法文本披露供应商或股票池差异时，短线情绪降为partial。
- 旧资金按方法文本分为交易所事实、供应商模型或活跃度代理；证据等级不足时降为partial。
- 没有结构化condition的旧验证点保留为`qualitative_verification_points`，展示但不自动结算。
- 摘要和Markdown公开`legacy_migration.warnings`，不静默美化旧输入。

## 章节状态

八个章节统一使用`available/partial/unknown`和非空`status_reason`。

- `available`：必需字段、日期、来源、股票池和方法完整。
- `partial`：证据可用但覆盖、时点、股票池或方法不完整；必须说明缺口。
- `unknown`：没有可用数值；不得填0或携带伪数据。

`indices/breadth/short_term_sentiment/turnover/sectors/style`标记available时，当日核心证据必须满足`observed_at == market_date`。滞后数据只能标partial。

## 数值证据与来源

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
    "url": "https://example.com/real-source"
  }
}
```

外部来源默认`kind=external`并要求真实HTTP(S)或绝对file URL。自设验证条件使用派生来源，不伪造URL：

```json
{
  "id": "derived-turnover-threshold",
  "name": "复盘派生验证点",
  "kind": "derived",
  "evidence_refs": ["sections.turnover.metrics.amount"]
}
```

规范单位：指数点`index_points`、比例`percent`、家数`count`、金额`CNY`。缺失不做隐式缩放。

## 股票池

`breadth`和`short_term_sentiment`使用结构化且完全一致的`universe`：

```json
{
  "id": "all-a-non-st",
  "label": "全A非ST普通股",
  "population_rule": "沪深京A股，排除ST、退市整理与停牌",
  "includes_st": false,
  "includes_bse": true,
  "exclusions": ["ST", "退市整理", "停牌"]
}
```

供应商、统计时点或股票池不一致时，`short_term_sentiment`最多标`partial`，状态输出unknown；不能以“差异不改变结果”的文字说明绕过门禁。

## 八个章节

### indices

`items`每项包含`id/name/primary/close/change_pct`。必须且只能有一个`primary=true`。

### breadth

available时`advancers/decliners/unchanged/limit_up/limit_down`必填，且必须给结构化`universe`。

### short_term_sentiment

available时必须给与breadth完全一致的`universe`、非空`methodology`以及：

- `open_board_failed`
- `limit_attempts`：正整数且不小于炸板数
- `highest_streak`

可选`previous_metrics`提供前一可比交易日的上述三项和`limit_up/limit_down`；只有整组同口径时评估修复。

### turnover

`amount/previous_amount`为available必需项。`avg_5d_amount/avg_20d_amount`必须分别带：

```json
{"window": {"trading_days": 5, "end_at": "2026-08-25"}}
```

### sectors

必须给单一`classification`。`items`包含`id/name/change_pct`，不得混排行业、概念和地域。

### funds

每项包含`name/methodology/metric/method_category`。类别只能是：

- `exchange_fact`：交易所或法定披露事实。
- `transparent_calculation`：透明公式；额外要求`calculation.formula/input_refs`。
- `provider_model`：供应商模型推导值。
- `activity_proxy`：成交活跃度等方向性有限的代理。

仅有`provider_model/activity_proxy`时，funds不能标available。北向成交额属于活跃度代理，不能写成净流入方向。

### style

每项包含`name/interpretation/metric/window`。`window.trading_days`和`end_at`必须显式给出，不能把5日数据命名为当日。

### events

每项包含`title/event_date/published_at/fetched_at/source`，且必须在快照截止前公开。

## 结构化验证点

```json
{
  "id": "verify-turnover",
  "title": "次日成交额是否保持在一万亿元上方",
  "event_date": "2026-08-26",
  "published_at": "2026-08-25",
  "fetched_at": "2026-08-25T17:30:00+08:00",
  "condition": {
    "metric": "turnover_amount",
    "operator": ">=",
    "value": 1000000000000,
    "unit": "CNY"
  },
  "source": {
    "id": "derived-turnover-threshold",
    "name": "复盘派生验证点",
    "kind": "derived",
    "evidence_refs": ["sections.turnover.metrics.amount"]
  }
}
```

允许指标：`primary_index_change_pct/advancer_share_pct/turnover_amount/turnover_vs_previous_pct/open_board_rate_pct/limit_balance`。允许操作符：`>/>=/</<=/==`。下一交易日生成时，上一交易日已到期条件自动结算为`passed/failed/unknown`。

## 派生口径

```text
上涨占比 = 上涨家数 / (上涨 + 下跌 + 平盘)
涨跌家数比 = 上涨家数 / 下跌家数
成交变化 = 当日成交额 / 比较成交额 - 1
历史分位 = 窗口内小于等于当前值的有效样本数 / 有效样本数
```

下跌家数为0时涨跌比输出unknown。输入或历史不足时不计算相应派生指标。
