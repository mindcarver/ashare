# 数据路由表（4 市场 × 7 维度 = 28 格）

> 本表是数据采集的执行手册。每个单元格列出：**优先数据源 → 备选 → 查询措辞 → 已知缺口与兜底**。
>
> 通用纪律见 SKILL.md 第二节，引用本表时一并遵守。

## 〇、数据源优先级

1. `neodata-financial-search`（先跑 `python3 scripts/query.py --query`，TOKEN_MISSING 时 connect_cloud_service 取 tempToken 再 `--save-token`）
2. `westock-data` / `a-stock-data`（A股全栈、A 股宽度/资金/解限/分红、ETF 持仓）
3. `WebSearch`（宏观面板、信用利差、VIX、Saxo Options Brief、Barchart、YCharts、propfirmtrading.net/macro、GFdaily）
4. `wb-finance-skill` 的判读框架（`market-state` / `institutional-holding` / `fund-flow`）

## 一、全球（Global）

> **2026-08-02 实测升级**：全球 7 格从"待复核"升级为 4 可得/部分 + 3 未知。IMF WEO、各央行官网、ICE BofA 均为可审计公开源。

| 维度 | 优先源 | 备选/兜底 | 查询措辞示例 | 2026-07 实测值 |
|---|---|---|---|---|
| 增长 | **IMF WEO**（imf.org） | WebSearch | "IMF World Economic Outlook 2026 global GDP growth forecast" | 2026 全球增速预测 **3.0%**（2026/7/8 更新）；4 月版 3.1% |
| 通胀 | **IMF WEO** | WebSearch | "IMF global inflation forecast 2026" | 全球通胀 **4.4%**（2026/4 WEO，7 月版称"下行趋势已停止"） |
| 流动性 | **各央行资产负债表**：Fed（FRED WALCL）→ thetrading.tools / macroradar；ECB 周报（ecb.europa.eu） | WebSearch | "Fed balance sheet total assets latest H.4.1"、"ECB consolidated financial statement weekly" | Fed 总资产 **$6.74T**（7/29，同比+0.4%）；ECB 基准货币 €3.96T（7/24）；BOJ/PBoC 官网 |
| 资金价格 | **四大央行政策利率**（官网各自） | WebSearch | "ECB deposit facility rate"、"BOJ policy rate" | Fed 3.50-3.75%（7/30 维持）、ECB 存款 **2.25%**（7/23 维持）、BOJ **1.0%**（7/31 维持）、PBoC 7天逆回购 1.40% |
| 风险偏好与信用 | **ICE BofA US HY OAS**（FRED BAMLH0A0HYM2）作全球代理 | WebSearch katusaresearch/modigin | "ICE BofA US High Yield OAS latest" | **2.87%**（7/29，3 年最低 2.59% / 2025-01） |
| 市场宽度 | **S&P 500 above MA 作全球代理**（Baird 5-for-Friday 周报 + Investing.com S5TH 指数） | WebSearch 板块宽度 | "S&P 500 percent above 200-day moving average July 2026"、"Barchart percent stocks above 50-day MA" | S&P 500 above 200-day MA **~75%**（7/31 Baird报告；6/8 时为 56%）；S5TH 7/30 收 68.58% |
| 机构持仓 | **CFTC COT S&P 500 净投机持仓**（cftc.gov 周五发布） + **13F 聚合**（13f.info/whale-wisdom） | EPFR Global | "CFTC Commitment of Traders S&P 500 futures"、"13F institutional holdings change" | S&P 500 净投机持仓 **-16.8K contracts**（从 -38.9K 改善，CFTC 7/25 发布覆盖 7/22） |

**全球已知缺口**：MSCI ACWI 上涨家数需 MSCI Index Pro 订阅；STOXX 600/日经 宽度部分公开但口径不同；13F 合计滞后 45 天且口径分散（仅顶级对冲基金/资管）。
**实测兜底**：用 **S&P 500 Stocks Above 200-day MA**（Baird / Investing.com S5TH）作全球权益宽度的可审计代理，标 `partial` + 注明代理口径；用 **CFTC COT S&P 500 净投机持仓**（cftc.gov 周报，免费）作全球权益拥挤度代理，标 `partial` + 注明代理口径。
**实测注意**：全球增长/通胀是 IMF **预测值**（非已发布观测值），格内必须标"预测"并给 WEO 期次；资金价格是四央行利率罗列（可用 bar 图展示四行对比），不是单一加权值。

## 二、美国（United States）

| 维度 | 优先源 | 备选/兜底 | 查询措辞示例 |
|---|---|---|---|
| 增长 | neodata | WebSearch Barchart 宽度 | "美国2026年二季度GDP环比折年率"、"美国7月ISM制造业PMI 最新"、"美国7月非农就业人数、失业率" |
| 通胀 | neodata | WebSearch BLS breakeven | "美国最新CPI同比、核心CPI同比、PCE物价指数和核心PCE同比"、"10Y breakeven inflation rate" |
| 流动性 | neodata M2 | WebSearch Fed H.4.1 | "美国最新M2同比增速"、"Federal Reserve balance sheet RRP TGA latest H.4.1"、"NFCI Chicago Fed latest" |
| 资金价格 | neodata 10Y | WebSearch 2Y / SOFR / 纽约联储 | "美国10年期和2年期国债收益率"、"SOFR rate latest"、"effective federal funds rate" |
| 风险偏好与信用 | WebSearch Saxo Options Brief + ICE BofA HY OAS + YCharts | — | "VIX SKEW put/call ratio latest"、"ICE BofA US High Yield OAS latest"、"MOVE index latest" |
| 市场宽度 | WebSearch Barchart | — | "S&P 500 percent above 5 20 50 100 200 day moving average"、"S&P 500 new highs new lows" |
| 机构持仓 | WebSearch GFdaily 引 FactSet | CFTC COT / FINRA 保证金 → 官网 | "S&P 500 forward PE FactSet"、"S&P 500 sector weight concentration latest" |

**美国已知缺口**：
- 2Y 国债收益率召回不稳 → WebSearch
- SOFR → 纽约联储官网（ICBC 外币利率每日概览也报 SOFR，免费）
- 宽基估值（标普500 PE）→ neodata 路由错（返回创业板指）→ 改 WebSearch 媒体引用
- CFTC COT 滞后、FINRA 保证金/AAII/13F → 各官网免费源

**2026-08-03 实测补充**：
- **7 月 ISM 口径分歧警示**：8/3 发布的 7 月 ISM 制造业，aastocks 报 56.3（6 月前值 57.8），而 investing.com/finlogix 日历显示 6 月为 53.3——两路口径冲突。**以 BEA GDP（7/30 发布 Q2 年化 1.5%）为增长格锚值更稳**，ISM 在 analysis 中标注分歧。
- **美债 10Y 日值免费源**：investing.com/rates-bonds/u.s.-10-year-bond-yield-historical-data 提供近月逐日收盘（4.60-4.73% 量级），比 Saxo 单点更适合作 line 图。
- **美国宽度可选代理**：thetrading.tools/market-breadth 提供全美股 ~5600 只四档均线占比（10/50/100/200 日），标 partial（快照滞后数日）。

## 三、中国（China）

| 维度 | 优先源 | 备选/兜底 | 查询措辞示例 |
|---|---|---|---|
| 增长 | neodata | a-stock-data 行情校验 | "2026年二季度中国GDP同比增速"、"2026年7月中国制造业PMI" |
| 通胀 | neodata | — | "中国6月CPI年率、核心CPI年率"、"中国6月PPI同比" |
| 流动性 | neodata | a-stock-data 资金面 | "中国最新M2同比增速、M1同比、社会融资规模存量同比、新增人民币贷款" |
| 资金价格 | neodata 10Y/LPR | WebSearch 中国货币网（DR007/SHIBOR 隔夜） | "中国10年期国债到期收益率最新值"、"最新1年期LPR和5年期以上LPR报价"、"DR007最新值" |
| 风险偏好与信用 | a-stock-data 涨跌停/炸板率/成交额 + WebSearch 信用利差 | — | "2026年7月31日A股上涨家数、下跌家数、涨停家数、跌停家数、两市成交额"、"中国信用利差 AAA-AA 最新" |
| 市场宽度 | a-stock-data 全市场涨跌分布、申万行业、新高新低、均线占比 | a-share-limitboard-report 流水线 | "A股市场宽度 新高新低 申万一级行业涨幅榜"、"A股均线占比 站上20日均线家数占比" |
| 机构持仓 | a-stock-data 两融/担保比例 + westock-tool ETF 排名 | — | "沪深两市融资融券余额最新规模"、"宽基 ETF 沪深300 中证500 中证1000 净流入"、"国家队 ETF 增持" |

**中国已知缺口**：
- DR007、SHIBOR 隔夜召回失败率高（返回 SHIBOR 1M 充数）→ WebSearch 中国货币网
- 北向日度 2024-08 起官方停披露（非工具问题）→ 用 ETF + 两融替代
- 炸板率 → a-share-limitboard-report 流水线
- 新高新低 / 均线占比 → a-stock-data 全市场行情自算

**2026-08-03 实测补充**：
- **两融周度序列**：证券时报·数据宝（stcn.com）披露深沪北两融余额近 5 个交易日序列 + 「连续 N 周回落」口径，比单点更有信号价值（如 7/31 报 26,113.27 亿，连续 5 周回落）。
- **中国 10Y 国债日值**：工行「人民币利率市场每日概览」（ICBC 官网）收盘值 + 观点网/财联社活跃券 260010 盘中值，可拼出近 3 日 line（1.72→1.71→1.70%）。

## 四、韩国（Korea）

> **2026-08-02 实测升级**：流动性（M2）、机构持仓（外资流向）两格已找到官方来源，从"未知/待复核"升级为可得/部分。

| 维度 | 优先源 | 备选/兜底 | 查询措辞示例 | 2026-07 实测值 |
|---|---|---|---|---|
| 增长 | WebSearch MOEF（企划财政部） | KOSTAT / ECOS | "Korea GDP forecast 2026"、"韩国2026年GDP增速预期" | 2026 GDP 增速预期上调至 **3.0%**（7/14 政府发布，原 2.0%） |
| 通胀 | WebSearch KOSTAT / ECOS | neodata | "Korea CPI YoY June 2026" | 6月 CPI 同比 **3.2%**（30 个月新高，7/2 发布）；核心 2.5% |
| 流动性 | **WebSearch BOK ECOS M2**（Yonhap/Xinhua 引 BOK） | CEIC | "Korea M2 money supply May 2026 BOK" | M2 **4,184.4 万亿韩元**（5月，环比+0.8%，7/15 BOK 发布；old M2 同比+11.7%） |
| 资金价格 | WebSearch BOK 基准利率 | ECOS / 韩国国债 | "Korea base rate BOK July 2026" | 基准利率 **2.75%**（7/16 加息 25bp，2023/1 来首次）；3Y 国债 3.848% |
| 风险偏好与信用 | WebSearch KRX | Yonhap | "KOSPI close July 31 2026" | KOSPI **6595.45**（7/31，单日 **+17.91%** 历史最大涨幅） |
| 市场宽度 | WebSearch KRX / Yonhap | — | "KOSPI KOSDAQ July 31 2026 close" | KOSDAQ 791.84（7/16）；7/31 KOSPI 暴涨 17.91%、日经 +4.03% |
| 机构持仓 | **WebSearch KRX 外资净买入**（Yonhap/韩联社引交易所） | FSS（金融监督院） | "Korea foreign investors net buy KOSPI July 2026" | 外资 7/21 净买入 **5,959 亿韩元**、机构净买入 1.65 万亿韩元；7/15 外资净买入 2.32 万亿韩元 |

**韩国已知缺口**：
- ECOS 历史 vintage 保留能力未验证 → 历史回放 `待复核`，但**最新一期官方发布**（BOK/KOSTAT 新闻稿）可直接采信为 `可得`
- KRX 指数收盘点位仅观察日可得，无 provider 发布日期 → `部分`
- 机构持仓格以"最新交易日外资净买入"表达，勿声称持仓总量（FSS 月度持仓数据滞后约 2 周）

## 五、跨市场通用注意事项

1. **单指标短查询**：避免"GDP+PMI+工增+社零"混合，拆成"2026年X月中国制造业PMI"这种短查询，一轮 4-6 个 Bash 并行。
2. **先看发布日期**：宏观库有"事件日历"和"指标库"两路，同一指标可能不一致——都列出、标分歧、采信最新发布的一路。
3. **neodata 已知怪癖**：
   - 宽基估值路由错（沪深300 PE 返回创业板指）→ 改 WebSearch
   - DR007、SHIBOR 隔夜、SOFR、信用利差召回失败率高 → 直接 WebSearch
   - westock-data `quote usVIX` 返回"数据为空" → WebSearch
4. **WebSearch 鉴别内容农场**：AI 生成农场站（如 fazen.markets）数据自相矛盾，与 neodata 交叉验证矛盾即弃用。
5. **时效口径**：先确定今天是否交易日、指标发布频率，禁止把上月值说成当月。
6. **asOf 回放语义**：asOf 必须严格大于等于所有 published_at；越界数据剔除，缺数据 = `未知`。
7. **跨市场不串味**：任何一格只能填该市场的数据，缺数据 = `未知` + statusReason。

## 六、实测避坑清单（每次跑必读）

| 坑 | 处理 |
|---|---|
| neodata 宽基估值路由错（沪深300 PE 返回创业板指） | 改 WebSearch 媒体引用 |
| neodata DR007/SHIBOR 隔夜/SOFR/信用利差召回失败率高 | 直接 WebSearch，别反复重试 |
| fazen.markets 是内容农场（同一站 S&P 既 5825 又 7557） | 弃用，与一手行情交叉验证 |
| 资金流向写成"净买入/净卖出"触发禁词误报 | 统一用"净流入/净流出" |
| 中国 6 月 CPI 年率事件日历缺 7/9 那期 | WebSearch 国家统计局解读（6 月 CPI +1.0%/PPI +4.1%） |
| 韩国 M2 库内无发布时间戳 | 最新一期官方新闻稿（Yonhap/Xinhua 引 BOK）可直接采信 |
| 美债 10Y neodata 只有月值 | 日值用 WebSearch（Saxo / Dow Jones Market Update） |
| neodata VIX 返回「K线: 暂无数据」（2026-09-11 实测） | 直接 WebSearch（Saxo/Dow Jones 晨报），别反复重试 |
| neodata 查 KOSPI 返回 KOSPI200 且为盘中值 | WebSearch「韩国 KOSPI 收盘 外资」（韩联社/Yonhap）取主板收盘 |
| neodata 中国 PMI 只返回分项、无整体值（49.8） | WebSearch 国家统计局发布稿（8/31 制造业 49.8/非制造业 49.0/综合 49.5） |
| neodata 中国 CPI 只到 7 月 | WebSearch 统计局 9/9 发布（8 月 CPI +0.8%/核心 +1.0%/PPI +3.8%） |

## 七、westock MCP 实战路由（2026-08-24 实测沉淀）

> westock-mcp 已连接时优先用工具而非 neodata 脚本，一次调用可顶多轮 WebSearch。

| 工具 | 用途 | 实测要点 |
|---|---|---|
| `data_market_overview type=all date=YYYY-MM-DD` | **A 股一格顶七格**：三大指数收盘/区间统计/技术指标/涨跌分布（涨跌家数、新高新低、涨停跌停）/两融变动/估值分位/风格轮动 | 当日复盘首选；type 子项（summary/trade/updown/valuation/rotation/technical）可单查；margin 变动表偶有空行需 WebSearch 补 |
| `data_macro names=macro_lpr,...` | 中美宏观事件库 | **必须用 listCode**（mode=list 先查目录，如 macro_lpr/macro_us_inflation），中文名直接报"未识别"；names 传多个 listCode 一次拉全 |
| `data_macro` 大结果落盘 | 返回 >10 万字符自动存 tool-results 目录 | 用 python 读文件按 OccurDate 过滤 2026 最新期，切忌整读 |
| `data_kline/data_quote codes=多码` | 指数/个股行情 | 批量码一次返回，适合拉全球指数对照 |

**新增免费源（本轮验证）**：
- **chartrow.com/sp500/market-breadth**：S&P 500 多档均线占比 + 涨跌家数 + 52 周新高新低，实时刷新，优于 Barchart（后者只给 S5TH 单档）。
- **MOEF 官网英文版（english.mofe.go.kr）最新指标栏**：韩国利率体系一次拿全（BOK 基准/隔夜拆借/KORIBOR/CD/3Y/5Y 国债/公司债 AA-），日更新，是韩国「资金价格」格最优源。
- **MOEF 官网 LATEST INDICATORS 同时给 KOSPI/KOSDAQ/汇率**：韩国宽度格可复用。
- **证券时报数据宝两融周报**（stcn.com）：两融余额逐日序列 + 分行业融资流向，比交易所原始披露更易采信。

**事件时间锚（本轮）**：美 Q2 GDP 二读 8/26、BOK 议息 8/27、Jackson Hole 8/27-29、9/4 非农——复盘报告中应标注「即将到来的验证点」。

## 八、westock MCP 补充实测（2026-08-29 沉淀）

- **`data_macro` 两类 listCode 必须区分**：指标库类（`macro_gdp`/`macro_cpi_ppi`/`macro_financing`/`macro_fundquantity`，带 `*_INFO_DATE` 发布日期字段）数据新鲜可用；**事件日历类（`macro_lpr`/`macro_us_*`/`macro_caixin_pmi`）数据陈旧错乱**（会返回 2025/12、2026/2 等过期期次），最新值一律 WebSearch 交叉，勿信接口。
- **`data_market_overview type=margin`**：row 偶发为空（仅返回 schema），连续多日（8/26-8/28 实测）无数据 → 两融改走证券时报数据宝（stcn.com）WebSearch。
- **韩国收盘与外资流向一条龙**：`data_finsearch` 关键词「韩国 KOSPI 外资」可命中 ajudaily（亚洲日报中文版）单条新闻全覆盖（KOSPI/KOSDAQ 收盘、外资/机构/个人净流向、汇率），比 KRX 官网易取。
- **禁词扫描（生成 HTML 交付前）**：grep 连「融资买入额」「净卖出」等资金术语都会命中「买入/卖出」禁词——统一改写为「融资额」「净流出」措辞；生成器 `--check` 通过后仍要对最终 HTML 再跑一遍 `grep -oE` 确认。**注意**：本技能禁词已上移共享层（tier=`strict`，见 `skills/_shared/forbidden-terms.json`），不要在脚本里重新内联禁词表，`make audit` 会报错。

## 八·补、全球/美国/韩国实测补充（2026-09-11 沉淀）

- **VIX/SKEW/MOVE 同源一次取全**：neodata「K线: 暂无数据」→ Saxo 9/10 晨报一次给 VIX 16.46 / SKEW 149.25 / MOVE 76.74，同源口径一致，优于拼多家。
- **韩国收盘 + 外资一条龙**：WebSearch「韩国 KOSPI 收盘 外资」命中韩联社中文稿，一次覆盖 KOSPI 7,033.92（-0.25%）/ KOSDAQ +0.79% / 外资净流出 2.49 万亿韩元 / 机构 +4,615 亿 / 个人 +3,622 亿；DigitalToday 可交叉印证。
- **全球央行资产负债表**：Fed 6.737T / ECB 5.912T / BOJ 644.66 万亿日元 / PBoC 50.21 万亿元——neodata 无直连，逐家官网新闻稿 + WebSearch 汇总。
- **CFTC 持仓**：杠杆基金 E-mini S&P 净空 307,558 张（cftc.gov 周报；发布滞后约 T+3，注意以此对应 observedAt）。
- **S&P 200 日均线上方占比**：chartrow.com/sp500/market-breadth 给 67.1%（与 8 月笔记同源，可复用）。
- **韩国跟随指标**：BOK 8/27 第二次加息至 3.00%、8 月 CPI +3.1%/核心 +3.4%（统计厅 9/2）、6 月 M2 同比 +9.4%（BOK 8/14）——韩国「资金价格/通胀/流动性」三格可一并取。

**生成器修复（2026-09-11）**：`scripts/derive.py` 的 `overview()` 曾以「有数据格子数 == 28」判「完全覆盖」，于是市场徽章显示「部分」时 overview 却写「完全覆盖」，文案自相矛盾。已改为：仅当 4 个市场全部 7 格均为 `available` 才输出「完全覆盖」，否则输出「部分覆盖」并给出 N/4 市场完全可得。回归测试：`tests/test_gen_dashboard.py::test_overview_grade_reflects_market_level_coverage`。

## 九、板块倾向建议层数据路由（sectorAdvice，2026-08-03 新增）

> 用户要求"投资建议/板块建议"时使用。**只到板块/主题粒度，禁止个股**；每条必须有证据来源 + 证伪条件；倾向只用 关注/中性/回避。

| 市场 | 板块数据源 | 查询措辞示例 |
|---|---|---|
| 全球 | WebSearch（板块轮动/大宗） | "全球 半导体 能源 黄金 板块 7月 表现" |
| 美国 | Barchart / Zacks / Metatrader（板块涨跌） | "S&P 500 sector performance July 31 2026"、"Zacks stock market news sector" |
| 中国 | a-stock-data（申万一级/概念涨跌+资金流）+ WebSearch 收评 | "A股 8月3日 收评 板块 涨幅榜 跌幅榜"、"申万一级行业 8月3日 涨幅" |
| 韩国 | WebSearch Yonhap（行业表现） | "KOSPI sector semiconductor auto shipbuilding July 31 2026" |

**纪律**：
- 板块数据必须来自当日/当周可审计报道（收评、交易所、主流财经），禁止凭空罗列板块。
- 每条建议 = 板块名 + 倾向 + evidence（带来源）+ trigger（证伪条件）。
- 倾向是"证据指向的方向性观察"，与 risk 互补：risk 说风险，sectorAdvice 说"证据指向哪里"。
- 关联 28 格证据：如「中国两融连续 5 周回落」→ 高杠杆科技板块给"回避/中性"；「美国 10Y 高位 + 估值高分位」→ 美成长板块给"中性/回避"。

## 十、按维度速查"我应该跑哪些工具"

| 维度 | 主要工具 | 备选 |
|---|---|---|
| 增长 | neodata | WebSearch |
| 通胀 | neodata | WebSearch |
| 流动性 | neodata | WebSearch + a-stock-data |
| 资金价格 | neodata | WebSearch（中国货币网、纽约联储、ECOS） |
| 风险偏好与信用 | WebSearch（Saxo / YCharts / ICE BofA）+ a-stock-data | neodata |
| 市场宽度 | a-stock-data + a-share-limitboard-report | WebSearch（Barchart / KRX） |
| 机构持仓 | a-stock-data + westock-tool | WebSearch（GFdaily / FactSet） |