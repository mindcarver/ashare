---
name: ashare-daily-market-review
description: 生成可审计的A股每日深度复盘；用户只需指定交易日，默认以deep模式和“纵 × 横 × 深 × 验”分析指数宽度、量价、情绪周期、封板、多周期资金、主题集中度、催化链、龙虎榜和验证点。只有用户明确要求简版/core时才降级；不输出买卖、仓位或目标价。
---

# A股每日盘面复盘

本技能描述一个交易日的市场结构。`1.2`把双确认主线矩阵与延续性检验做成可复算结构；`1.3`加入深度分析层；`1.4`增加`core/deep`交付模式、独立深度覆盖和“纵 × 横 × 深 × 验”四轴交汇，避免新版外壳静默缺少深度内容。

同属 `1.2` 的还有**四项可选的个股颗粒度结构**，用来回答「这个板块里谁在动、动得结实不结实」：**连板梯队分布**（几板几家，且与涨停家数、最高板同池自洽）、**最高板质量**（逐只高标的板数与资金/换手证据）、**板块内重点个股**（板块归因下钻）、**概念层资金流**（区别于行业层的第二套分类，容纳概念与风格项）。四者在语义上都是**归因**，不是选股，报告里必须原样保留这句声明。它不把单日盘面写成确定性买卖结论。

## 一、边界

- `ashare-capital-environment-dashboard`：全球/美国/中国/韩国的增长、通胀、流动性、资金价格、信用、宽度和拥挤度背景。
- 本技能：单个A股交易日的指数、成交、宽度、涨跌停、短线情绪、板块、资金、风格和事件，以及围绕它们的双确认主线矩阵与前一涨停池延续性检验。
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

读取[数据契约](references/data-contract.md)，构造`market.json`。十个章节：

1. `indices`：主要指数收盘和涨跌幅。
2. `breadth`：上涨、下跌、平盘、涨停、跌停。
3. `short_term_sentiment`：炸板次数、封板尝试次数、最高连板高度、可选前一交易日对照和可选体检阈值。可再挂两项个股颗粒度结构：`streak_distribution`（连板梯队分布）与 `high_boards`（最高板质量）。
4. `turnover`：当日成交、前值和可选均值。
5. `sectors`：统一分类体系的板块表现，可选板块主力净流入及其方法类别。可再挂 `leaders`（板块内重点个股）与 `concept_view`（概念层资金流，第二套分类）。
6. `funds`：两融、ETF、北向或供应商资金数据及方法。
7. `style`：大小盘、成长价值、红利等相对结构。
8. `events`：截至as-of已公开的当日事件。
9. `mainline_matrix`：双确认主线矩阵——主题的涨停家数与声明板块资金流，象限由显式规则派生。
10. `prev_pool_performance`：延续性检验——前一交易日涨停池在当日的表现与晋级率。

每章标记`available/partial/unknown`和原因。每项数值必须保存单位、观察日、发布日期、抓取时间和来源。缺失就是unknown，不用0填充。第9、10章是`1.2`新增的**可选**分析层：不提供即按unknown处理，旧输入无需改动。

### 公开报告与内部证据分离（强制）

HTML/Markdown 是面向用户的公开报告，**不得写出数据从哪里获取**。禁止展示或暗示：平台/连接器名称、域名与URL、API/接口名、请求参数、字段编号、文件路径、采集命令、抓取主机、来源汇总表和采集故障细节。产业事件也只写事实、发布日期、机制、反证与验证点，不在正文署名媒体或链接。

公开报告只保留判断所必需的证据边界：观察日、发布日期、单位、窗口、`available/partial/unknown`、`exchange_fact/provider_model/derived`等方法类别，以及不含采集渠道的口径说明。需要向用户解释缺口、分类或反方证据时，分别使用可选的`public_status_reason`、`public_classification`、`public_caveat`；没有安全公开文本时由渲染器输出保守通用说明，不得直接回显内部`status_reason/methodology/source`。

完整来源、URL、抓取时间和可复现证据继续保存在`market.json`、摘要JSON和历史快照中，作为内部审计侧车；不得把它们嵌入HTML/Markdown，也不得随公开报告主动列出。隐藏采集渠道不能成为删掉时间口径、资金方法类别或把缺失值改成0的理由。

**默认路由是deep。** 用户只说“复盘YYYY-MM-DD”“用A股复盘技能看某日”或其他普通日期复盘请求时，也必须读取[深度分析层契约](references/deep-analysis.md)和[四轴复盘规则](references/four-axis-analysis.md)，使用`analysis_mode=deep`并声明六个深度组件。先尽力采集；仍缺数据时保留组件、写`availability=unknown`和原因，绝不退回core。只有用户明确说“简版”“快速版”或`core`时才允许`analysis_mode=core`。

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
- 声明`health_thresholds`时逐条给出阈值体检结果（不聚合成分数）。
- 提供`mainline_matrix`时按显式阈值判定象限，并公开`quadrant_rule`；可选声明`bleeding_threshold_cny`（必须严格小于`capital_threshold_cny`）把「家数达标」再拆出「情绪失血」，未声明时该档不出现。
- 提供`prev_pool_performance`时计算晋级率，并按声明的健康线判定高于/低于；该晋级率同时可作为可结算验证点指标`promotion_rate_pct`，在`event_date`当天用同一口径自动结算。
- 提供`streak_distribution`时按档位归集家数并给出首板/连板只数与首板占比；各档之和与最高档已在契约层与同一股票池对齐。
- 提供`high_boards`时逐只列出板数与质量证据，并统计主力净流入为正/为负的只数（只数正负，不作评级）。
- 提供`sectors[].leaders`时按资金流排序输出板块归因下钻；提供`sectors.concept_view`时把概念层按净流入/净流出**分开**排序，不与行业层合并。
- 以上四项只保留「至少一行有值」的列：整列缺证据的列不出现，不用整列 unknown 占版面。
- 提供`deep_analysis`时，输出事实、规则派生、机制假设和反方证据四层；逐条检查量价条件，不聚合隐藏分数。
- 始终分别输出基础覆盖和深度覆盖；`deep`模式缺任一组件直接拒绝。
- 四轴层交叉时间延续、截面象限、量价/集中度/催化纵深和验证闭环；主题结论只使用公开结果规则，不生成总分。
- 资金“迁移”只输出同日流出/流入共现候选，同时计算板块/个股重叠率、Top1正流入占比、绝对流量HHI和伪板块标记，不声称追踪到同一笔钱。
- 验证点必须声明`subject.scope/id/label`；个股、板块、主题、基准和全市场只能使用各自scope允许的指标。

`--history-dir`可选但推荐。它按交易日和修订追加保存已验证输入；相同SHA幂等跳过，同日不同SHA必须用递增revision和`supersedes_sha256`连接，不能覆盖历史。

生成器可直接读取旧`schema_version=1.0/1.1/1.2/1.3`产物并保守归一化为`core`。1.2验证点若不能证明标题与condition语义一致，会降为定性观察；不会为了兼容伪造深度证据。新输入必须使用1.4并显式声明`analysis_mode`。

`--html-out`是可选的静态可视化交付：以同一份已校验输入生成市场脉搏卡、宽度环图、板块强弱条、情绪状态、下一交易日验证和限制；不生成来源汇总，不显示采集渠道。板块默认只展示涨幅前10与跌幅前10，完整榜单折叠；条形按真实绝对涨跌幅绘制，不人为放大接近零的波动。HTML不依赖在线图表库；数据缺失时展示unknown/公开原因，不绘制零值替代图表。视觉由报告族共享的「ASHARE EDITORIAL」品牌层统一提供（`skills/_shared/design-tokens.css` + `shell.css` + `components.css`，由 `inject_shared_css()` 注入，注入点在 head 结束标签之前，对同名选择器有最终解释权）；本技能模板只保留短线情绪五态语义色（`.state-ice/-euphoria/-divergence/-repair`）与 `.section-note` / `.evidence` 附注小字，**不得回填骨架或组件规则**。

内置背离和情绪规则公开在JSON摘要中。读取[短线情绪规则](references/short-term-sentiment.md)以确认所需字段、口径和状态优先级。例如：主要指数上涨但上涨家数占比低于40%，标记“指数上涨但宽度偏窄”；这只是结构观察，不预测次日方向。

## 五、解释顺序

按照[报告模板](references/report-template.md)交付：

1. 先报数据覆盖，不足时先说不能判断什么。
2. 再看指数与成交。
3. 检查上涨参与度、涨跌停和指数—宽度关系；短线情绪字段完整时再报告状态与触发依据；声明了体检阈值时追加逐条体检表。
4. 分析板块、资金和风格，但保留分类与供应商口径；板块带资金流时披露其方法类别。
5. 回溯：做延续性检验，报告前一涨停池当日表现、晋级率与声明的健康线。
6. 结构：报告双确认主线矩阵的象限分布、缺口与读法。
7. 声明深度层时依次解释个股证据、量能价格、情绪周期、资金共现与集中度、催化链、龙虎榜；先事实再假设，再列反证。
8. 先结算上一期验证点，再列出公开事件和结构化未来验证点。
9. 最后只写显式结构信号、输入声明的反方证据、限制和需要后续验证的条件。

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
- `mainline_matrix`的`quadrant_rules`是否显式声明，没有隐藏默认阈值。
- 若声明`bleeding_threshold_cny`，是否严格小于`capital_threshold_cny`（否则区间倒挂），且`quadrant_rules`没有多余的自造键。
- 未声明`bleeding_threshold_cny`时，是否没有在计数、图例、信号或摘要里凭空出现「情绪失血」，输出与声明前逐字节一致。
- `themes[].boards`是否全部存在于`sectors.items[].id`，没有悬空引用。
- 缺板块资金流的主题是否标`unknown`并列出`missing_board_fund_flow`，没有用0或部分求和冒充。
- `prev_pool_performance.universe`是否与`breadth.universe`结构一致，`previous_market_date`是否严格早于`market_date`。
- `promotion_count`是否不大于`pool_size`。
- `promotion_rate_pct`验证点是否配`unit: percent`，且只有在声明了`prev_pool_performance`时才结算；缺该章节或`pool_size`为0时是否诚实落回`unknown`，没有用0或上期值顶替。
- 未声明`health_thresholds`时是否没有体检输出，没有回退到隐藏默认阈值。
- `streak_distribution`各档家数之和是否等于`breadth.limit_up`、最高档是否等于`highest_streak`（两处都要同池自洽，否则拒绝）。
- `high_boards`每只是否至少给了一项质量证据（`fund_flow`或`turnover_pct`），`streak`是否不小于2且不高于`highest_streak`。
- 板块内个股与高标的`fund_flow`是否都配了`fund_flow_method_category`，没有把供应商推导值写成客观资金。
- `sectors.concept_view.classification`是否**区别于**`sectors.classification`；概念层是否独立成表、没有与行业榜合并排序。
- 个股颗粒度四张表是否都带「不构成个股推荐 / 只作结构归因」的声明；是否没有整列 unknown 的空壳列。
- 未声明四项结构时，报告、摘要与覆盖计数是否与声明前逐字节一致（`SECTION_NAMES`未变，不得新增顶层章节）。
- 深度层是否符合[深度分析层契约](references/deep-analysis.md)：资金窗口、量价样本、贡献分解、催化引用、龙虎榜滞后和验证subject全部通过门禁。
- 深度请求是否设置`analysis_mode=deep`并声明六组件；四轴结果是否按[四轴复盘规则](references/four-axis-analysis.md)逐项可复算。
- 象限与体检结果是否只作结构枚举，没有被渲染成评分、入场信号或仓位指令。
- 相同输入和as-of是否产生相同Markdown、JSON和SHA。
- HTML/Markdown是否完全不含来源汇总、平台/连接器名称、URL、接口、字段编号、文件路径或采集命令；内部JSON与历史快照是否仍保留完整证据链。
- 是否避免隐藏总分、个股推荐、买卖、目标价和仓位指令；情绪状态是否只作为市场观察。

## 七、实测口径与避坑

完整清单（股票池口径、备用主机矩阵、滚动窗口、资金断供、脚本维护）见 [实测口径与避坑清单](references/data-pitfalls.md)。**每次跑复盘前读该文件**；新增经验也追加到那里，不要写回本文件。

先记住最高频五条：

1. **采集通道故障 ≠ 数据缺失**：`push2` 报 `ProxyError` / `RemoteDisconnected` 时先换备用主机（`push2delay` 供 clist/ulist，`push2his` 供 K 线）并串行长重试（≥8 次、指数退避），不要直接判 unknown；`push2his` 整体限流时 `push2delay` 的 kline 端点返回 0 行，不能顶替。
2. **不同来源的涨停家数不能互认**：东财涨停池不含 ST，指数级涨跌家数含 ST，两者不是同一股票池；`short_term_sentiment` 最多 partial，除非重建同池宽度。跌停家数尤其不能跨源比较（同一交易日曾出现 5 与 21 两个口径）。
3. **滚动均值窗口必须显式声明**：取 5/20 日均值时 `lmt` 至少 25，否则 20 日会被静默算成更短窗口；输出时写 `window.trading_days`。
4. **全A宽度翻页必须 `pz=100`**：`pz=500` 会提前中断翻页并把下跌家数静默算成 0，不报错、只出错数；翻完自检「上涨+下跌+平盘 ≤ 有报价样本」。
5. **宽度/指数/板块是「最新快照」接口，不能回填历史交易日**：`clist`/`ulist.np` 没有 `date` 参数，只返回当前最新快照，可用 `f124` 时间戳反推其所属日；能按日期取历史的是涨停池/跌停池/炸板池、日K线与两融。把别日的宽度挂到今天的标签下会静默混日期。

一键取数：`make fetch-market DATE=<交易日> [OUT=market.json] [CTX=ctx.json]`组装1.4输入并校验。未声明模式时默认deep，自动把缺少的深度组件补为显式unknown；只有context明确声明core才走轻量路径。详见避坑清单第十一节。

修改脚本后运行：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

或在仓库根跑 `make test`（会连同共享层一起验证）。
