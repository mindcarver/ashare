---
name: ashare-daily-market-review
description: 生成可审计的A股每日盘面复盘，覆盖主要指数、成交活跃度、上涨/下跌家数、涨跌停、短线情绪观察、板块表现、资金证据、风格结构、公开事件和后续验证点。当用户说“复盘今天A股”“今天盘面怎么样”“每日收盘复盘”“看市场宽度、连板或短线情绪”时使用；不输出买卖或仓位指令。
---

# A股每日盘面复盘

本技能描述一个交易日的市场结构：指数怎么走、多少股票参与、成交是否扩张、短线情绪有哪些可见特征、板块和风格如何分化、资金证据是什么、出现了哪些显式背离。它不把单日盘面写成确定性买卖结论。

## 一、边界

- `ashare-capital-environment-dashboard`：全球/美国/中国/韩国的增长、通胀、流动性、资金价格、信用、宽度和拥挤度背景。
- 本技能：单个A股交易日的指数、成交、宽度、涨跌停、短线情绪、板块、资金、风格和事件。
- `ashare-company-research`：单家公司预期差、催化剂、估值与风险。

不要把三个层次混成一个巨型报告。

## 二、固定复盘口径

确认：

- `market_date`：正在复盘的交易日。
- `as_of`：报告可使用信息的截止日期。
- `snapshot.type/cutoff_at/revision`：区分收盘、盘后和周末补充；同日修订不能覆盖旧快照。
- 板块分类体系，例如申万一级；不能混合多个体系排序。
- 资金数据的方法定义；“主力资金”等供应商推导值必须说明方法。

非交易日不能冒充新盘面。如果用户要求周末复盘，使用最近交易日作为`market_date`，并把周末新事件放入验证点或事件章节。

## 三、准备证据输入

读取[数据契约](references/data-contract.md)，构造`market.json`。八个章节：

1. `indices`：主要指数收盘和涨跌幅。
2. `breadth`：上涨、下跌、平盘、涨停、跌停。
3. `short_term_sentiment`：炸板次数、封板尝试次数、最高连板高度和可选前一交易日对照。
4. `turnover`：当日成交、前值和可选均值。
5. `sectors`：统一分类体系的板块表现。
6. `funds`：两融、ETF、北向或供应商资金数据及方法。
7. `style`：大小盘、成长价值、红利等相对结构。
8. `events`：截至as-of已公开的当日事件。

每章标记`available/partial/unknown`和原因。每项数值必须保存单位、观察日、发布日期、抓取时间和来源。缺失就是unknown，不用0填充。

## 四、生成复盘

```bash
python3 scripts/generate_daily_review.py \
  --input market.json \
  --as-of 2026-08-25 \
  --output daily-review-2026-08-25.md \
  --summary-out daily-review-2026-08-25.json \
  --html-out daily-review-2026-08-25.html \
  --history-dir ~/.ashare/daily-market-history
```

生成器确定性计算：

- 上涨家数占比和涨跌家数比。
- 涨停减跌停的数量差。
- 成交额较前值和5日均值变化。
- 领涨/领跌板块。
- 显式指数—宽度背离。
- 可得且口径明确时的炸板率与短线情绪观察。
- 前一交易日变化、20/60日分位和情绪状态连续天数；样本不足时保持unknown。
- 上一期已到期验证点的`passed/failed/unknown`结算。

`--history-dir`可选但推荐。它按交易日和修订追加保存已验证输入；相同SHA幂等跳过，同日不同SHA必须用递增revision和`supersedes_sha256`连接，不能覆盖历史。

生成器可直接读取旧`schema_version=1.0`真实产物并保守归一化：用原始输入SHA作为证据包SHA，根据最晚`fetched_at`建立快照，把可识别的窗口和资金方法显式化；无法证明股票池一致的情绪降为partial，无法机器计算的旧验证点保留为“定性观察点”而不自动判定。新输入必须直接使用1.1。

`--html-out`是可选的静态可视化交付：以同一份已校验输入生成市场脉搏卡、宽度环图、板块强弱条、情绪状态、下一交易日验证、限制与来源。板块默认只展示涨幅前10与跌幅前10，完整榜单折叠；条形按真实绝对涨跌幅绘制，不人为放大接近零的波动。HTML不依赖在线图表库；数据缺失时展示unknown/原因，不绘制零值替代图表。视觉由报告族共享的「ASHARE EDITORIAL」品牌层统一提供（`skills/_shared/design-tokens.css` + `shell.css` + `components.css`，由 `inject_shared_css()` 注入，注入点在 head 结束标签之前，对同名选择器有最终解释权）；本技能模板只保留短线情绪五态语义色（`.state-ice/-euphoria/-divergence/-repair`）与 `.section-note` / `.evidence` 附注小字，**不得回填骨架或组件规则**。

内置背离和情绪规则公开在JSON摘要中。读取[短线情绪规则](references/short-term-sentiment.md)以确认所需字段、口径和状态优先级。例如：主要指数上涨但上涨家数占比低于40%，标记“指数上涨但宽度偏窄”；这只是结构观察，不预测次日方向。

## 五、解释顺序

按照[报告模板](references/report-template.md)交付：

1. 先报数据覆盖，不足时先说不能判断什么。
2. 再看指数与成交。
3. 检查上涨参与度、涨跌停和指数—宽度关系；短线情绪字段完整时再报告状态与触发依据。
4. 分析板块、资金和风格，但保留分类与供应商口径。
5. 先结算上一期验证点，再列出公开事件和结构化未来验证点。
6. 最后只写显式结构信号、限制和需要后续验证的条件。

## 六、质量门

- available日频证据的`observed_at`是否等于`market_date`。
- 所有`published_at`是否不晚于`as_of`。
- 宽度分母是否大于0且口径一致。
- 板块是否来自同一分类体系。
- 资金数据是否说明方法，避免把模型推导当客观资金流。
- unknown/partial是否保留原因，没有用0补齐；短线情绪的分母是否口径明确且大于0。
- 快照截止时间是否覆盖所有证据；close/盘后/周末信息是否分开。
- breadth与short-term sentiment是否使用完全一致的结构化股票池；不一致时必须partial/unknown。
- 滚动指标是否显式保存`window`，没有把5日值命名为当日。
- funds是否保存`method_category`；仅有供应商模型或活跃度代理时不能标available。
- 自设验证点是否使用结构化condition和派生证据引用，没有伪造来源URL。
- 相同输入和as-of是否产生相同Markdown、JSON和SHA。
- 是否避免隐藏总分、个股推荐、买卖、目标价和仓位指令；情绪状态是否只作为市场观察。

## 七、实测口径与避坑

完整清单（股票池口径、备用主机矩阵、滚动窗口、资金断供、脚本维护）见 [实测口径与避坑清单](references/data-pitfalls.md)。**每次跑复盘前读该文件**；新增经验也追加到那里，不要写回本文件。

先记住最高频三条：

1. **采集通道故障 ≠ 数据缺失**：`push2` 报 `ProxyError` / `RemoteDisconnected` 时先换备用主机（`push2delay` 供 clist/ulist，`push2his` 供 K 线）并串行长重试（≥8 次、指数退避），不要直接判 unknown。
2. **不同来源的涨停家数不能互认**：东财涨停池不含 ST，指数级涨跌家数含 ST，两者不是同一股票池；`short_term_sentiment` 最多 partial，除非重建同池宽度。
3. **滚动均值窗口必须显式声明**：取 5/20 日均值时 `lmt` 至少 25，否则 20 日会被静默算成更短窗口；输出时写 `window.trading_days`。

修改脚本后运行：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

或在仓库根跑 `make test`（会连同共享层一起验证）。
