# A股每日盘面数据契约

采集每日数据、构造输入、写入历史或解释覆盖状态时读取本文件。当前版本为 `1.4`。

## 顶层与快照

```json
{
  "schema_version": "1.4",
  "analysis_mode": "core",
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
  "verification_points": [],
  "deep_analysis": {}
}
```

- `market_date`不得晚于`as_of`，命令行`--as-of`必须与输入一致。
- `snapshot.type`只能是`close/post_close/weekend_update`。
- `cutoff_at`必须带时区；所有`published_at/fetched_at`不得晚于该截止时间。
- `close`快照的截止日期必须等于`market_date`；盘后或周末补充使用另外两类。
- 同日首版`revision=1`且`supersedes_sha256=null`；后续修订递增并指向上一修订的输入SHA。
- `raw_evidence_sha256`是采集原始证据清单或原始响应包的SHA，不是报告输出SHA。
- `analysis_mode`只能是`core/deep`。deep是交付承诺：六个深度组件必须全部出现，缺数据用unknown和原因，不能省略。

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

### 1.1 → 1.2 升级

`1.2` 新增的章节与字段**全部可选**，旧 `1.1` 输入语义不变，因此升级只做两件事：

- 把 `schema_version` 改写为 `1.2`；
- 写入 `legacy_migration = {"from": "1.1", "warnings": [...]}`，并在摘要与 Markdown 中公开。

**不得**在升级时回填任何 1.2 专属字段（如 `fund_flow`、`mainline_matrix`、`health_thresholds`）。没有提供的章节继续按 `unknown` 处理。

1.2 发布后追加的可选细化键（如 `mainline_matrix.quadrant_rules.bleeding_threshold_cny`）仍属 1.2：**声明才有新输出，未声明时报告与摘要与 1.2 初版逐字节一致**，因此不需要再改 `schema_version`。

同一条规则适用于后来追加的四项个股颗粒度结构——`short_term_sentiment.streak_distribution` / `short_term_sentiment.high_boards` / `sectors.items[].leaders` / `sectors.concept_view`。它们都**没有新增顶层章节**：`SECTION_NAMES` 不变，因此覆盖计数（`可得N / 部分N / 未知N`）与旧输入完全一致；四项全部缺省时，Markdown、HTML 与摘要逐字节不变（`make test` 有回归用例守护）。

顶层章节只允许在**版本升级**时新增；给 1.2 追加结构时必须挂到既有章节之下，否则会静默改变所有历史输入的覆盖计数。这是本契约最容易踩的向后兼容陷阱。

历史快照（`--history-dir`）按写入时的版本落盘；读取时走同一条升级链再校验，因此旧版本历史不会被新契约拒收，跨版本比较也使用同一套字段语义。

### 1.2 → 1.3 升级

`1.3`新增顶层可选`deep_analysis`，详见[深度分析层契约](deep-analysis.md)。旧输入不回填深度证据。验证点新增`subject.scope/id/label`：旧1.2验证点只有在标题明确匹配其全市场metric时才补为`market/all-a`，其余降为`qualitative_verification_points`，不继续错误自动结算。

### 1.3 → 1.4 升级

`1.4`新增`analysis_mode`、独立深度覆盖和[四轴复盘派生](four-axis-analysis.md)。旧1.0–1.3统一迁为`core`，即使历史输入带部分深度组件也不倒推当时承诺了完整深度交付；已有组件仍照常校验和展示。新1.4输入必须显式声明模式。

基础覆盖只统计十个`sections`；深度覆盖独立统计六组件的available/partial/unknown/missing。deep模式的missing必须为0。

新1.4输入的`verification_points[].event_date`必须严格晚于`market_date`。旧版本中不满足该条件的点迁为定性观察，不继续进入未来验证计数或主题交汇。

## 章节状态

十个章节统一使用`available/partial/unknown`和非空`status_reason`。

- `available`：必需字段、日期、来源、股票池和方法完整。
- `partial`：证据可用但覆盖、时点、股票池或方法不完整；必须说明缺口。
- `unknown`：没有可用数值；不得填0或携带伪数据。

`indices/breadth/short_term_sentiment/turnover/sectors/style`标记available时，当日核心证据必须满足`observed_at == market_date`。滞后数据只能标partial。

任意章节可选的`caveat`字段用于登记**反方证据或自我证伪**（例如「某标的的催化尚未贡献收入，属预期交易」）。它是非空字符串，聚合渲染在「结构信号与限制」一节，不改写任何数值。

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

## 十个章节

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

可选`health_thresholds`声明多条件体检阈值。**未声明即不体检，绝不套用隐藏默认值。**

```json
{
  "limit_up_min": 45,
  "limit_down_max": 5,
  "open_board_rate_max_pct": 25,
  "promotion_rate_min_pct": 30,
  "highest_streak_min": 3
}
```

派生规则统一为单调：`*_min` 成立条件 `observed >= threshold`，`*_max` 成立条件 `observed <= threshold`。`promotion_rate_min_pct` 的观察值来自 `prev_pool_performance.promotion_rate_pct`；该章节缺失时此项列入`unresolved`，不计入判定。体检只做逐条枚举，**不聚合成分数**，也不构成入场信号。

可选`streak_distribution`（连板梯队分布）：把「几板几家」写成可复算的档位表。

```json
"streak_distribution": [
  {"streak": 4, "count": { "...": "count 证据，非负整数" }},
  {"streak": 1, "count": { "...": "count 证据" }}
]
```

- 每档`streak`为正整数且**不重复**；`count`为`count`单位的非负证据。
- 最高档必须等于`metrics.highest_streak`。
- 各档家数**之和必须等于`breadth.limit_up`**（同一股票池，且必须包含首板），否则拒绝——这条约束让梯队无法与宽度口径脱钩。
- 派生：`first_board_count`（`streak == 1`）、`continued_count`（其余之和）、`highest_streak_count`、`first_board_share_pct`。只做事实归集，**不设**任何隐藏阈值，也不据此推导入场。

可选`high_boards`（最高板质量）：逐只列出高标与质量证据。

```json
"high_boards": [
  {
    "name": "闽东电力",
    "code": "600509",
    "streak": 4,
    "fund_flow": { "...": "CNY 证据，带正负号" },
    "fund_flow_method_category": "provider_model",
    "turnover_pct": { "...": "percent 证据，非负" },
    "note": "空间龙头，机构未买"
  }
]
```

- `streak`为**不小于 2**的整数，且不得高于`metrics.highest_streak`。
- 每只**至少**给`fund_flow`或`turnover_pct`之一作为质量证据，只有名字与板数的空壳被拒绝。
- 有`fund_flow`时必须同时给`fund_flow_method_category`（取值同`funds`）。
- 派生：`count`、`inflow_count`/`outflow_count`/`flat_count`（按资金流正负零计数，零点是方向分界、不是调参阈值）。只作结构观察，**不构成个股推荐**。

### turnover

`amount/previous_amount`为available必需项。`avg_5d_amount/avg_20d_amount`必须分别带：

```json
{"window": {"trading_days": 5, "end_at": "2026-08-25"}}
```

### sectors

必须给单一`classification`。`items`包含`id/name/change_pct`，不得混排行业、概念和地域。`id`在章节内唯一，供`mainline_matrix`引用。

可选`fund_flow`登记板块主力净流入，并**必须**同时给`fund_flow_method_category`（取值同`funds`的`method_category`）。板块资金流多为供应商推导值，报告按该类别披露，不得写成交易所事实，也不得用净流入方向替代成交额活跃度。

```json
{
  "id": "sw-electronics",
  "name": "电子",
  "change_pct": { "...": "percent 证据" },
  "fund_flow": { "...": "CNY 证据，带正负号" },
  "fund_flow_method_category": "provider_model"
}
```

可选`leaders`（板块内重点个股）：板块归因的下钻层，挂在具体板块项上。

```json
"leaders": [
  {
    "name": "生益电子",
    "code": "688183",
    "change_pct": { "...": "percent 证据，可为负" },
    "fund_flow": { "...": "CNY 证据" },
    "fund_flow_method_category": "provider_model",
    "turnover_pct": { "...": "percent 证据，非负" },
    "streak": 3,
    "note": "核心中唯一净流入"
  }
]
```

- 每只至少给`change_pct`或`fund_flow`之一；同一板块内`name`不得重复。
- `change_pct`与`fund_flow`允许为负（它们描述方向），只有`turnover_pct`必须非负。
- 有`fund_flow`时必须同时给`fund_flow_method_category`。
- 这是**归因**不是推荐：报告必须显式声明它不构成个股推荐。

可选`concept_view`（概念层资金流）：与行业层**分开成表**的第二套分类，用来容纳概念与风格项（如「MSCI中国」「融资融券」「科技风格」）。

```json
"concept_view": {
  "classification": "东财概念",
  "status_reason": "东财概念与风格项资金流，同源同口径",
  "items": [
    {
      "id": "cp-001",
      "name": "PCB",
      "change_pct": { "...": "percent 证据，可选" },
      "fund_flow": { "...": "CNY 证据" },
      "fund_flow_method_category": "provider_model"
    }
  ]
}
```

- `classification`**必须区别于**`sectors.classification`——这个字段存在的意义就是第二套分类，与行业层同体系会直接拒绝，防止把两套口径混排成一个榜单。
- `items`内`id`不得重复；每项至少给`change_pct`或`fund_flow`之一；有`fund_flow`时必须给方法类别。
- 派生：`inflows`（资金流为正，按金额降序）与`outflows`（资金流为负，按金额升序）**分别排序**，不合并。

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

### mainline_matrix（1.2 新增，可选）

双确认主线矩阵：把「游资情绪面（涨停家数）× 机构资金面（板块主力净流入）」变成可复算的二维结构分类。

```json
{
  "availability": "available",
  "status_reason": "主题成分板块与涨停家数由输入显式声明",
  "classification": "申万一级",
  "methodology": "按输入声明的成分板块与涨停归组",
  "quadrant_rules": { "limit_up_threshold": 3, "capital_threshold_cny": 0, "bleeding_threshold_cny": -2000000000 },
  "caveat": "主题成分由输入人工归组，跨主题个股可能重复计入。",
  "themes": [
    {
      "id": "pcb",
      "name": "AI硬件·PCB链",
      "boards": ["sw-electronics", "sw-medicine"],
      "limit_up": { "...": "count 证据" },
      "limit_up_fund_flow": { "...": "CNY 证据，可选" },
      "prev_pool_premium_pct": { "...": "percent 证据，可选" }
    }
  ]
}
```

硬约束：

- 非`unknown`时必须给`classification`与`methodology`；`classification`必须与`sectors.classification`一致，否则拒绝。
- `quadrant_rules.limit_up_threshold`（正整数）与`capital_threshold_cny`（有限数值）**必须显式声明**，禁止隐藏默认值。
- `quadrant_rules.bleeding_threshold_cny`（可选，有限数值）**必须严格小于`capital_threshold_cny`**，否则「情绪脉冲」与「资金先行」的判定区间会倒挂或重叠，校验直接拒绝。`quadrant_rules`只接受这三个键，多写即拒绝。
- `themes[].boards`必须引用真实存在于`sectors.items[].id`的板块且非空；引用悬空即拒绝。
- available时`themes[].limit_up.observed_at`必须等于`market_date`。

派生（确定性）：

```text
board_fund_flow_cny = Σ 声明板块的 fund_flow.value        # 任一板块缺资金流 ⇒ 该主题象限 unknown
board_change_pct_equal_weight = 声明板块 change_pct 的等权均值
capital_positive   = board_fund_flow_cny > capital_threshold_cny
sentiment_positive = limit_up_count >= limit_up_threshold

dual_confirmed（双确认） = capital_positive 且 sentiment_positive
capital_led（资金先行）  = capital_positive 且非 sentiment_positive
sentiment_positive 时按「资金流出深度」再拆一档：
  sentiment_bleeding（情绪失血）= 声明了 bleeding_threshold_cny 且 board_fund_flow_cny <= bleeding_threshold_cny
  sentiment_only（情绪脉冲）    = 其余情况（未声明失血线，或资金流出未达失血线）
bleeding（失血）        = 两者皆非
unknown（象限待补）      = 声明板块缺少 fund_flow
```

`bleeding_threshold_cny` 是一个**可选**的分档线，用来区分两种截然不同的「家数达标」：资金面弱正/小额流出（真实情绪脉冲）与资金面大额净流出（失血中继，涨幅由存量资金推动、缺乏增量承接）。

**向后兼容是硬约束**：未声明`bleeding_threshold_cny`时，`sentiment_bleeding`**不参与计数、不进图例、不产出信号、不出现在摘要的任何字段里**，报告与摘要与声明前的 1.2 输出逐字节一致。需要一个共用的真源，见`schema.active_quadrant_order`。

任一板块缺资金流时**不得**用 0 或部分求和冒充，象限返回`unknown`并在`missing_board_fund_flow`列出缺口。象限是结构分类，不是评分，不得渲染为入场信号或仓位指令。

### prev_pool_performance（1.2 新增，可选）

延续性检验：前一交易日涨停池在**当日**的整体表现与晋级率。这是「回溯归因」，与`verification_points`的「前瞻验证」互补——后者问明日条件会不会成立，前者问昨日判断今天兑现了没有。

```json
{
  "availability": "available",
  "status_reason": "前一交易日涨停池当日表现全量重算",
  "previous_market_date": "2026-09-11",
  "universe": { "...": "必须与 breadth.universe 完全一致" },
  "health_threshold_pct": 30,
  "metrics": {
    "pool_size": { "...": "count 证据，正数" },
    "promotion_count": { "...": "count 证据，非负" },
    "avg_change_pct": { "...": "percent 证据" },
    "median_change_pct": { "...": "percent 证据，可选" }
  },
  "by_group": [
    {
      "id": "group-electronics",
      "name": "电子元件",
      "count": { "...": "count 证据" },
      "avg_change_pct": { "...": "percent 证据" }
    }
  ]
}
```

硬约束：

- `universe`必须与`breadth.universe`结构化一致（名称相似但`population_rule/includes_st/includes_bse/exclusions`不同仍视为不一致）。
- `previous_market_date`必须是合法日期且**严格早于**`market_date`。
- available时必需`pool_size`（正整数）、`avg_change_pct`、`promotion_count`（非负）。
- `promotion_count`不得大于`pool_size`。

派生：

```text
promotion_rate_pct = promotion_count / pool_size * 100
health = promotion_rate_pct >= health_threshold_pct ? at_or_above_line : below_line
```

未声明`health_threshold_pct`时`health`为`null`，报告只给晋级率、**不作**高于或低于的判断。

`promotion_rate_pct`同时进入连续历史序列，可作为**可结算的验证点指标**：以交易日 D 为`event_date`、`metric`为`promotion_rate_pct`的条件，会在 D 当天用 D 的同一口径（D-1 涨停池于 D 的晋级率）自动结算为`passed/failed`。该章节缺失或`pool_size`为 0 时观察值为`null`，验证点落回`unknown`，绝不用 0 或上期值顶替。没有该章节的旧输入（1.0/1.1）不会在连续历史表中新增这一行。

## 结构化验证点

```json
{
  "id": "verify-turnover",
  "title": "次日成交额是否保持在一万亿元上方",
  "event_date": "2026-08-26",
  "published_at": "2026-08-25",
  "fetched_at": "2026-08-25T17:30:00+08:00",
  "subject": {"scope": "market", "id": "all-a", "label": "A股全市场"},
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

允许指标：`primary_index_change_pct/advancer_share_pct/turnover_amount/turnover_vs_previous_pct/open_board_rate_pct/limit_balance/promotion_rate_pct`。允许操作符：`>/>=/</<=/==`。下一交易日生成时，上一交易日已到期条件自动结算为`passed/failed/unknown`。单位固定：除`turnover_amount`为`CNY`、`limit_balance`为`count`外，其余为`percent`；`promotion_rate_pct`必须配`unit: percent`，且只有在数据声明了`prev_pool_performance`章节时才可能结算，否则恒为`unknown`。

## 派生口径

```text
上涨占比 = 上涨家数 / (上涨 + 下跌 + 平盘)
涨跌家数比 = 上涨家数 / 下跌家数
成交变化 = 当日成交额 / 比较成交额 - 1
历史分位 = 窗口内小于等于当前值的有效样本数 / 有效样本数
```

下跌家数为0时涨跌比输出unknown。输入或历史不足时不计算相应派生指标。
