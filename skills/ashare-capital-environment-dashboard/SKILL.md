---
name: ashare-capital-environment-dashboard
description: 生成资本环境仪表盘 HTML 报告：字段与覆盖语义沿用 AGUHOT 4市场×7维度证据网格，视觉沿用报告族共享的「ASHARE EDITORIAL」品牌设计系统（浅色瑞士 / 柔和粗野主义，见 skills/_shared/README.md）。当用户要"做一份资本环境仪表盘""中美韩宏观对照""资本环境多维证据""资本环境报告""类似 AGUHOT 的资本环境页面"时使用。也可用于回放某一日（asOf=YYYY-MM-DD）的资本环境状态。明确区分已观测事实和未知；默认不输出指令性投资建议/目标价/牛熊判断/买卖结论，但用户明确要求时，可输出证据驱动的"板块倾向建议层"（关注/中性/回避，仅为研究建议，不构成投资建议）。
---

# 资本环境仪表盘

生成多市场×多维度资本环境仪表盘 HTML 报告。4×7 字段与覆盖语义沿用 AGUHOT 资本环境页，视觉壳层和组件语言必须对齐 `ashare-daily-market-review` 的“市场脉搏”HTML（参考更新后的 `references/aguhot-design-spec.md`）；数据采集对齐 `references/data-routing.md`，HTML 模板见 `references/html-template.md`。

默认使用中文输出。

## 一、定位与红线

**这是环境状态的证据面板，不是指令性投资建议工具。** 默认输出证据网格；**当用户明确要求投资建议时**，可附加"板块倾向建议层"（见第 7 条），但任何一档报告都必须满足以下约束，缺一不可：

1. **固定网格**：4 市场 × 7 维度 = 28 个单元格，绝不裁剪、合并、改名。
   - 市场：`全球` / `美国` / `中国` / `韩国`
   - 维度：`增长` / `通胀` / `流动性` / `资金价格` / `风险偏好与信用` / `市场宽度` / `机构持仓与拥挤度`
2. **覆盖语义诚实**：每个单元格只能填以下 6 种状态之一，禁止编造、禁止零填充。
   - `可得`（绿）：存在观测值，证据完整
   - `部分`（灰）：数据有但不全
   - `未知`（红）：完全没有可验证来源
   - `失败`（红）：数据采集失败
   - `待复核`（浅灰）：来源已识别但 vintage/口径未核验
   - `无法还原`（红）：历史快照存在但点时不可重建
3. **证据必带溯源**：每个有值的单元格必须显示
   - 观测值 + 单位
   - 来源 id + 来源名称
   - 观测日期（observed_at）
   - 发布日期（published_at，若可得）
   - 处理版本（processingVersion）
4. **历史回放支持**：用生成器 `--as-of YYYY-MM-DD` 指定回放日期；生成的 HTML 是固定日期快照，不得用未接后端的 `?asOf` 控件伪装回放。
5. **结论层强约束**：顶部 overview、每格 analysis/takeaways、AI 综合研判卡中，必须区分"已观测事实"和"未知"，**禁止**出现以下任一词：
   - 买入、卖出、建议买、建议卖、目标价、目标仓位、牛熊分数、总分
   - 确定牛、确定熊、必然涨、必然跌
   - （"净流入/净流出"等资金流向描述词不受限；资金流向不得写成"净买入/净卖出"）
6. **免责声明固定**：底部必须有"以上为证据约束下的环境解释与研究辅助，不代表未来收益、因果关系或投资建议。"
7. **板块倾向建议层（可选，用户要求时才输出）**：
   - 输出位置：AI 综合研判卡与覆盖矩阵之间，独立成卡"板块倾向建议（研究参考）"。
   - 只到**板块/主题**粒度，禁止给个股、禁止给目标价/目标仓位、禁止指令性措辞（买入/卖出/满仓/清仓/加仓）。
   - 每条建议 = 板块名 + 倾向（`关注` / `中性` / `回避`）+ **证据依据**（引用 28 格数据或板块观测，必须带来源）+ **触发条件**（什么证据会推翻该倾向）。
   - 倾向表述用"关注/中性/回避"，不用"建议买/建议卖"；倾向只表达"证据指向的方向性观察"，不构成买卖指令。
   - 卡头必须固定一行：`以下为基于资本环境证据的板块方向性研究参考，仅为建议，不构成投资建议或买卖指令，不保证未来表现。`

## 二、数据采集（数据路由表摘要）

详细查询措辞、来源、已知缺口见 `references/data-routing.md`（**28 格逐一验证过，含实测值**）。本节只列骨架。

数据采集主源（按优先级）：
1. `neodata-financial-search` —— 行情、估值、宏观日历（中国/美国宏观最顺）
2. `westock-data` —— 美/中/港/韩/日股票/指数/ETF
3. `a-stock-data` —— A股全栈（资金流、两融、宽度、解禁、分红、龙虎榜）
4. `WebSearch` —— 宏观面板、信用利差、VIX、Saxo Options Brief、Barchart、各央行官网、CFTC 等
5. `wb-finance-skill` 的 `market-state` / `institutional-holding` / `fund-flow` 判读框架（用于覆盖判读）

通用纪律：
- **单指标短查询**优于"GDP+PMI+工增+社零"混合查询；拆成"2026年X月中国制造业PMI""美国6月CPI年率"这类带期次+指标名的短查询，一轮并行 4-6 个 Bash。
- **先看发布日期再采信**：宏观库可能有"事件日历"和"指标库"两路，同一指标两路可能不一致——都列出、标注分歧，采信最新发布的一路。
- **WebSearch 鉴别内容农场**：AI 生成农场站（fazen.markets 等）数据自相矛盾，与 neodata 一手行情交叉验证，矛盾即弃用。可信免费源：Saxo Options Brief（CBOE 期权数据）、Barchart（美股宽度）、YCharts（VIX 序列）、propfirmtrading.net/macro、GFdaily（FactSet 估值引用）、thetrading.tools / macroradar（Fed 资产负债表）。
- **缺口兜底**：库内召回失败的指标（DR007、SHIBOR 隔夜、SOFR、信用利差、宽基估值错路由）直接走 WebSearch，并标"需核实"。
- **时效口径**：先确定今天是否交易日、指标发布频率（如美国 7 月非农 8/7 才发布），用"最新已发布期"，禁止把上月值说成当月。

## 三、28 格数据获取地图（速查）

> 详细版（含查询措辞、实测值、缺口）在 `references/data-routing.md`。这里是"从哪拿"的速查：
> ✅ 指可直接采信为 `可得`；🟡 指可用但标 `部分`（口径/覆盖不全）；❌ 指无公开免费源。

| 维度 | 全球 | 美国 | 中国 | 韩国 |
|---|---|---|---|---|
| 增长 | ✅ IMF WEO（imf.org，预测值标"预测"） | ✅ neodata（BEA GDP + 非农/PMI） | ✅ neodata（统计局 GDP/PMI） | ✅ WebSearch 企划财政部 GDP 预期 |
| 通胀 | ✅ IMF WEO 全球通胀预测 | ✅ neodata（CPI/PCE/核心） | ✅ neodata（CPI/PPI） | ✅ WebSearch BOK（CPI YoY） |
| 流动性 | 🟡 各央行资产负债表（Fed WALCL + ECB 周报，bar 对比） | ✅ neodata M2 / Fed H.4.1 | ✅ neodata（M2/M1/社融剪刀差） | ✅ WebSearch BOK M2（Yonhap 引官方） |
| 资金价格 | ✅ 四大央行政策利率（官网，bar） | 🟡 neodata 10Y 月值 + WebSearch Saxo 日值 | ✅ neodata 中债 10Y 日值 | ✅ WebSearch BOK 基准利率 |
| 风险偏好与信用 | 🟡 ICE BofA US HY OAS 作全球代理 | ✅ WebSearch Saxo Options Brief（VIX/SKEW/put-call/MOVE 全有） | ✅ neodata A股上涨占比/涨跌停 | ✅ WebSearch KRX（KOSPI 点位/涨跌） |
| 市场宽度 | 🟡 **S&P 500 above 200-day MA 作代理**（Baird 周报 + Investing.com S5TH） | 🟡 WebSearch Barchart / 主要指数涨跌 | ✅ neodata 涨跌家数分布 | 🟡 WebSearch KRX（KOSPI/KOSDAQ） |
| 机构持仓与拥挤度 | 🟡 **CFTC COT 净投机持仓作代理**（cftc.gov 周报） | ✅ WebSearch forward PE（FactSet/TrendOnify） | ✅ neodata 两融余额 | 🟡 WebSearch KRX 外资净流入 |

### 代理口径决策规则（2026-08-02 实测沉淀）

**当某格没有"完美"的公开源时，代理 + 诚实标注 = 比 `未知` 更可用。** 这是本技能 4 轮迭代从 7/28 空到 0 空的核心经验：

1. **优先找"最接近的免费可审计代理"**，而不是放弃：
   - 全球宽度 → S&P 500 above 200-day MA（Baird 周报 / Investing.com S5TH，免费）
   - 全球机构拥挤度 → CFTC COT 周报（cftc.gov 免费，周五发布）
   - 全球信用 → ICE BofA US HY OAS（FRED 免费）
2. **代理必须标 `partial` + 注明代理口径**：如"S&P 500 above 200-day MA 作全球权益宽度代理，其他市场公开覆盖不全"。
3. **代理必须有来源 + 时间戳**：不能只说"据市场"，要写清源站名和发布日期。
4. **明确边界**：代理覆盖了哪部分、没覆盖哪部分（如"MSCI ACWI 需订阅，未纳入"）。
5. **绝不把代理说成原指标**：全球宽度代理就是代理，不能写成"MSCI ACWI 上涨家数占比"。
6. **仍有硬缺口才 `未知`**：MSCI ACWI 宽度、13F 合计等确实无免费可审计源的，才保持 `未知` + reason。

### 实测避坑清单

**已移到 `references/data-routing.md` 第六节**（每次跑必读）。最常见三条：宽基估值路由错改 WebSearch、DR007/SHIBOR/SOFR/信用利差召回失败率高直接走 WebSearch、fazen.markets 等内容农场站与一手行情交叉验证后弃用。

### 禁词与视觉系统已上移共享层

本技能的禁词表、设计令牌与品牌层不再定义在生成脚本内：

- 禁词 tier：`strict`（比其它技能更严——连裸「买入/卖出」和「总分」都不允许，因为本技能完全不产生聚合评分）
- 真源：`skills/_shared/forbidden-terms.json`
- 设计令牌：`skills/_shared/design-tokens.css`
- 品牌层（外壳 + 组件）：`skills/_shared/shell.css` + `skills/_shared/components.css`；渲染末尾由 `ashare_shared.inject_shared_css()` 注入

注入顺序要点：品牌层插在 `</head>` 之前，即**排在本技能模板的 `<style>` 之后**，对同名选择器有最终解释权。因此模板里只保留资本环境独有的内部结构（`.tw-*` / `.sa-*` / `.an-*` / `.cell-head` / `.cell-evidence`）与更高的特异性覆盖（如 `.market-grid .cell{padding:14px}`）。

**不要在脚本里重新内联禁词表、`:root` 色值、页面骨架或组件规则**——`make audit` 与 `make test` 会直接报错。改禁词请改共享文件，改配色请改 `design-tokens.css`。

### 脚本结构（已按审计 P2-5 拆分）

`scripts/` 不再是单个巨型文件，校验 / 派生 / 渲染 / 模板 / CLI 各归其位：

| 文件 | 职责 |
|---|---|
| `gen_dashboard.py` | CLI 入口：参数解析、编排、写盘、禁词兜底扫描（**唯一入口，调用方式不变**） |
| `schema.py` | 契约常量：市场/维度/标签/可用性枚举、日期解析、默认输入路径 |
| `validate.py` | 输入读取、契约校验、点时筛选（返回 `(records, sectorAdvice)`，无全局副作用） |
| `derive.py` | 可用性映射、市场聚合、overview 文案、跨格研判清单 |
| `render.py` | HTML 片段与整页组装，末尾调 `inject_shared_css` |
| `page_template.py` | 整页 HTML 模板（只有一个字符串常量，与渲染逻辑分离） |
| `_paths.py` | 把 `skills/_shared` 挂到 `sys.path` 的唯一入口 |

**演示样例数据与生产逻辑物理隔离**：28 格样例在 `examples/sample-cells.json`（非生产数据），
不传 `--cells` 时默认读它。生产请始终显式传 `--cells cells.json`。

## 四、报告骨架（图表化）

无论回放哪一天，HTML 结构固定为 6 段。**全部 28 格用 ECharts 图表渲染 + AI 透镜分析**：

1. **顶部导航**：标题 + 回放日期 + 静态快照说明；其他日期必须重新运行生成器，或由已验证的服务端按同一规则处理 `asOf`。
2. **顶部摘要卡**：纸灰底 + 钴蓝 6px 左边线 + 零圆角（`.summary-box`，骨架来自共享组件层），第一行是 overview，第二行是 disclaimer。overview 句式：
   ```
   截至 {YYYY-MM-DD} 的资本环境：{覆盖等级}。以下为各市场维度的可观测状态，区分已观测事实与未知。
   ```
   覆盖等级：`完全覆盖`（28/28 格有值）/ `部分覆盖，N/4 市场、M/28 格有可得数据` / `无可得数据`。
3. **AI 综合研判卡**（`takeaway-box`，蓝边）：**跨格交叉验证**，从 28 格 takeaways 汇总 4-8 条一句话结论。每条 = 标签（市场/主题）+ 一句交叉验证（如"中国两融下降 + 指数上涨 = 被动资金接棒"）。位置在摘要卡与覆盖矩阵之间。
4. **覆盖矩阵**：4 市场 × 7 维度色块热力图（可得=绿/部分=灰/未知失败=红），一眼看全 28 格覆盖情况，附图例。
5. **市场×维度图表网格**：每个市场一个 section，标题右侧挂覆盖徽章。下方 3 列网格（`md:grid-cols-3`），每格结构 = 维度名 + 徽章 + **ECharts 图表**（180px）+ **AI 分析摘要**（透镜式，虚线边框）+ 一行证据脚注（来源/观测日/发布日/处理版本）：
   - 增长 → gauge（指针=最新同比，marker=前值/荣枯线）
   - 通胀 → gauge 或 line（有历史序列用 line + 2% 参考线）
   - 流动性 → line（M2 同比趋势）
   - 资金价格 → line（10Y 国债近 N 日）
   - 风险偏好与信用 → gauge（VIX 或 HY OAS）
   - 市场宽度 → bar（涨跌家数分布，红涨绿跌）
   - 机构持仓与拥挤度 → gauge（PE 分位 / 两融水平）
   - 无数据格 → 灰色占位"无可得数值（非零值）" + reason，**不画图不填零**
6. **底部免责声明**：固定一行。

`allUnknown` 时（整个 replay 完全无数据）：显示"该日期无可得的资本环境数据。请选择一个有可靠数据的日期。"，不渲染市场 section 与覆盖矩阵。

### AI 分析层规范（analysis / takeaways 字段）

每格 `analysis` 是 `[[透镜名, 一句话], ...]` 列表，3-4 条，透镜名用 8 通用透镜或维度特有视角（见第三节地图）：
- 通用透镜：`水平` / `趋势` / `结构` / `相对` / `预期差` / `政策含义` / `逆向` / `波动` / `局限`
- 维度特有：增长用"产出缺口/领先滞后"、通胀用"核心口径/工资螺旋"等
- **写法纪律**：
  - 每条 = 判断 + 证据（数据/来源），如"水平：2.87% 处近 3 年 6% 分位"
  - 用「」括内嵌引用（**禁止在字符串里用 ASCII 双引号**，会破坏生成脚本语法——2026-08-02 实测踩坑）
  - 代理口径必须说明（"作全球权益宽度代理"）
  - 每条都是观察/推理，**不出现禁词、不给方向性建议**（方向性观察只允许出现在第七节"板块倾向建议层"）
- `takeaways` 是 `[[标签, 一句话], ...]`，1 条/格，用于顶部综合研判卡的跨格交叉验证；语句要体现"格与格的关系"（如"两融降 + 指数涨 = 被动资金接棒"）

### 板块倾向建议层规范（sectorAdvice 字段 + 板块建议卡，2026-08-03 新增）

用户明确要求"给投资建议/板块建议"时才输出。格式（`cells.json` 顶层增加 `sectorAdvice` 字段）：

```json
"sectorAdvice": {
  "disclaimer": "以下为基于资本环境证据的板块方向性研究参考，仅为建议，不构成投资建议或买卖指令，不保证未来表现。",
  "markets": [
    {
      "market": "中国",
      "date": "2026-08-03",
      "items": [
        {"sector": "核电/电网设备（政策+开工链）", "stance": "关注",
         "evidence": "国常会 8/3 核准 4 个核电项目/总投资超 1700 亿（zjlnqh 早班车）；8/3 核电、可控核聚变、电网设备领涨（界面新闻）",
         "trigger": "若新订单持续走弱且开工不及预期则降为中性"},
        {"sector": "存储芯片/半导体", "stance": "回避",
         "evidence": "8/3 存储芯片、HBM、玻纤领跌、科创50 -5.08%（jrj）；7 月 SOX 单月 -21%（智通财经）",
         "trigger": "若 AI 资本开支财报验证转好且宽度回升则转中性"}
      ]
    }
  ]
}
```

- `stance` 只能是 `关注` / `中性` / `回避` 三选一。
- 每条必须有 `evidence`（带来源）和 `trigger`（证伪条件）——没有证据或触发条件的条目禁止输出。
- 只到板块/主题粒度，禁止个股、禁止目标价/目标仓位。
- 倾向是"证据指向的方向性观察"，与 risk 字段互补：risk 说风险，sectorAdvice 说"证据指向哪里"。
- 板块数据采集：A股用申万一级/概念板块涨跌与资金流（a-stock-data / WebSearch 收评），美股用板块涨跌与 etc（Barchart/Zacks），韩国用行业表现（Yonhap）；禁止编造板块数据，缺失即不列。

### 风险信号层规范（risk 字段 + 风险清单卡）

投资视角解读：数据不是结论，是**假设检验器**——回答"市场定价了什么、什么证据能证伪、什么会打破现状"。每格 `risk` 字段格式：

```json
"risk": {"level": "high|medium|low", "label": "风险标签", "text": "风险描述（判断+证据）"}
```

- **分级规则**：
  - `high` 高优先级风险：当前已可确认、冲击直接（类滞胀钳制、信用缓冲极薄、极端波动、PMI 跌破荣枯线）
  - `medium` 需验证信号：背离/分歧/拥挤，方向未明（SKEW 高 vs VIX 低、量松价紧、杠杆撤被动资金进、政策分歧）
  - `low` 缓解因素：数据指向健康/改善（宽度健康、空头回补、流动性转松）
- **渲染**：顶部"AI 综合研判卡"下方自动生成"风险信号清单"卡，按 高/中/缓解 三分层汇总；每格维度名旁挂风险点（红=high/橙=medium/绿=low）
- **写作纪律**：
  - 描述 = 判断 + 证据 + 触发条件（如"若 8 月数据续弱则衰退预期升温"）
  - **写"风险"不写"建议"**：说清"什么会亏钱/什么会打破现状"，不给"应该买/卖"——禁词清单同样适用
  - 优先识别**背离**（信用松 vs 尾部防、杠杆撤 vs 指数涨、量松 vs 价紧），背离是最大风险信号
- 投资视角三层解读框架（写 risk 时的思考顺序）：
  1. 宏观环境：增长×通胀×政策 → 周期相位与政策方向
  2. 流动性资金面：量×价×结构 → 钱多钱少、流向哪里
  3. 市场结构：风险偏好×宽度×持仓 → 定价了什么、谁在交易

## 五、产出规范

- **输出格式**：自包含 HTML（外链仅 ECharts CDN），ECharts 套骨架别从零写嵌套。文件命名：`ashare-capital-environment-dashboard-{YYYY-MM-DD}.html`，放项目根或用户指定位置。
- **生成脚本（推荐）**：`scripts/gen_dashboard.py`（已拆分为 schema/validate/derive/render/page_template，见第三节）内置完整模板 + 渲染引擎 + 覆盖矩阵生成逻辑。不传 `--cells` 时读取 `examples/sample-cells.json` 的演示样例（**非生产数据**）；生产输入使用 `--cells cells.json --as-of YYYY-MM-DD --out file.html`。每个 `market|dimension` 可是一条记录或按版本保存的记录数组；脚本只选 `publishedAt ≤ asOf` 的最新记录，无合格记录自动标 `未知`。
- **视觉风格（必须）**：报告族共享的「ASHARE EDITORIAL」品牌设计系统——白纸黑字最高对比、可见 32px 网格、纯黑 2px 结构线、零圆角、7px 硬投影、grotesk 标题 + 宋体正文 + 等宽数据。令牌、外壳与组件全部来自 `skills/_shared/`（`design-tokens.css` / `shell.css` / `components.css`），**本技能模板不再自带任何骨架或组件样式**；A 股涨跌保持红涨绿跌，覆盖度用状态色（`--state-*`）。资本仪表盘只保留自身 4×7 信息架构与 `tw-*` / `sa-*` / `an-*` 内部结构，不再使用 AGUHOT 浅色后台壳层。
- **数据注入**：所有 28 格数据通过模板唯一的 `{{CELLS_JSON}}` 占位符注入（见 `references/html-template.md` 第三节配置格式），禁止硬编码在 HTML 标签里。
- **HTML 模板**：见 `references/html-template.md`（脚本内已内嵌此模板）。
- **交付前必做**（三条全过才交付）：
  ```bash
  # 1) 节点语法检查
  awk '/^<script>$/{f=1;next}/^<\/script>$/{f=0}f' file.html > /tmp/_check.js && node --check /tmp/_check.js
  # 2) CELLS JSON 有效性（注意：grep 会贪婪匹配到后续 JS，用 python 正则更稳）
  python3 -c "import re,json;json.loads(re.search(r'const CELLS = (\{.*?\});',open('file.html').read(),re.S).group(1));print('JSON OK')"
  # 3) 禁词扫描
  grep -oE "买入|卖出|建议买|建议卖|目标价|目标仓位|牛熊分数|总分|确定牛|确定熊|必然涨|必然跌" file.html
  ```
- **覆盖徽章配色**（状态语义，**不使用行情词 up/down**——旧版 `--market-up` 取绿色表示「可得」，与红涨绿跌相反，是明确事故源，v2 已删除）：
  | 状态 | 颜色类 | 含义 |
  |---|---|---|
  | 可得 | `badge-available` | 数据+溯源完整（状态绿） |
  | 部分 | `badge-partial` | 数据有但不全（常为代理口径，状态琥珀） |
  | 未知 / 失败 / 无法还原 | `badge-unknown` | 数据缺失或采集失败（状态红） |
  | 待复核 | `badge-muted` | 来源已识别但 vintage 未核验（中性灰） |

  矩阵格同步用 `.matrix-cell.a` / `.p` / `.u`（在 `components.css` 里定义为 state-ok / state-warn / state-bad）。

## 六、工作流程

1. **确认回放日期**：用户指定 `asOf=YYYY-MM-DD` 则通过 `--as-of` 传入；非交易日保留最近一次已发布数据的观察日期，绝不把 URL 或文件名日期当成新观测。
2. **并行采集 28 格**：按 `references/data-routing.md`（速查见第三节地图）一轮并行 4-6 个 Bash 调用，分多轮把 28 格填齐；每格记录：观测值、单位、来源 id、来源名称、observedAt、publishedAt、processingVersion、availability、statusReason。
3. **诚实归类**：对照 6 种覆盖状态，把每格归类；缺数据优先用**代理口径**（见第三节决策规则）标 `partial`，确实无源的才 `未知` + statusReason；**绝不**用 0 填充、绝不**用相邻市场数据冒充**。
4. **生成 overview**：统计有多少市场是 `可得` 或 `部分`，套句式生成 overview。
5. **禁词自检**：overview + disclaimer + 每个维度句子的拼接文本扫描禁词清单；命中即重写至通过。
   - ⚠️ **实测坑（2026-08-02）**：资金流向类数据（外资/机构/散户的买盘卖盘）如果写成"净买入/净卖出"会触发禁词清单误报。**统一用"净流入/净流出"措辞**（如"外资净流入 5,959 亿韩元"），既专业又不触发禁词。
6. **（可选）板块倾向建议层**：仅当用户要求投资/板块建议时执行。采集各市场板块层面数据（A股申万行业/概念涨跌+资金流、美股板块、韩国行业），写入 `cells.json` 顶层 `sectorAdvice`（见第四节规范）；每条必须带证据来源 + 证伪条件；倾向只用"关注/中性/回避"；卡头 disclaimer 固定句式。
7. **写 HTML**：运行 `python3 scripts/gen_dashboard.py --cells cells.json --as-of YYYY-MM-DD --out file.html`；28 格数据全部进 `{{CELLS_JSON}}`；同一维度跨市场保持图表类型一致；`sectorAdvice` 存在时自动渲染板块建议卡。
8. **交付前自检**：先运行 `python3 scripts/gen_dashboard.py --cells cells.json --as-of YYYY-MM-DD --check`，再做节点语法检查 + CELLS JSON 校验 + 禁词自检 + 至少 3 格图表有 tooltip 数据可交互；若含板块建议卡，额外校验：无个股、无"买入/卖出"指令、每条有 evidence+trigger、卡头 disclaimer 存在。
9. **交付**：present_files 交付 HTML，正文给出"截至日期 / 覆盖等级 / 28 格中可得:部分:未知 分布 / 关键缺口 3-5 条"；若含板块建议，正文注明"板块建议仅为研究参考，不构成投资建议"。

## 七、与其他技能的关系

- **macro-7dim-dashboard**：宏观七维面板的"中国/美国"专项版（更聚焦宏观），本技能是它的"四市场对等展开 + 证据网格"升级版。两者数据源与查询纪律通用，可以共享禁词清单与时效口径规则。
- **ashare-company-research**：单只 A股公司深度调研，本技能在"中国市场 × 市场宽度 / 机构持仓"维度上为其提供宏观背景。
- **ashare-news-investment-targets**：新闻→标的评分，本技能可作为"标的所属市场的资本环境快照"快速参考。
- **a-share-limitboard-report**：A 股涨停全景日报，本技能在"中国市场 × 市场宽度"维度上消费其涨跌家数/成交额/涨停数。

## 八、交付清单

1. `ashare-capital-environment-dashboard-{YYYY-MM-DD}.html` —— 自包含 HTML（present_files 交付，正文给覆盖等级 + 关键缺口）。
2. 若用户提"每日/每周更新" → 用 `automation_update` 建定时任务，prompt 引用本 SKILL.md 的"工作流程"段。

## 九、口径与命名约定

- "观测值" = 该指标在 asOf 时点可观测的数值（非零值才显示为"有值"，零或 null 显示为"无可得数值"）
- "观测日期" = 指标实际对应的统计期/交易日（如 2026-07-31 的成交额）
- "发布日期" = 指标被官方或来源首次公布的日期（如非农 8/7 公布，对应 7 月观测）
- "处理版本" = AGUHOT sidecar 加工该值时使用的处理版本号（用于跨日对比时识别重算）
- "覆盖状态" = 单元格级 availability（见第一节红线 2）
