# A 股研究技能库审计报告

- 审计日期：2026-09-10
- 审计范围：`skills/` 下 6 个技能（ashare-company-research / ashare-daily-market-review / ashare-capital-environment-dashboard / ashare-news-investment-targets / ashare-stock-screening / ashare-research-journal）
- 审计方法：通读 6 份 SKILL.md（合计 1,113 行）、22 份 references、6 个脚本（合计 4,285 行）、6 份 evals、6 个测试套件；交叉比对禁词清单、CSS 实现、输出路径、跨技能引用；实际执行 6 个测试套件。
- 结论摘要：**53 个测试全部通过，单技能内部一致性良好；问题集中在「技能之间」——本该共享的东西被复制成多份，且已经发生漂移和冲突。**

---

## 〇、执行进展（同日完成）

按本报告建议的序列执行了三批，测试从 53 增至 **89 个，全部通过**。

### 已完成

| 项 | 内容 | 验证方式 |
|---|---|---|
| **P0-1** | news 技术面口径冲突已按**方案 A** 对齐全库：删除价位输出要求、禁止「区间估算」兜底、阶段C 改为引用共享技术面文件；生成器禁词表新增止损/止盈/买入观察价/目标价位/数据为估算 | 新增 2 条回归测试：注入价位锚点必须被拒（`test_rejects_price_anchors`） |
| **P0-2** | 新建 `skills/_shared/forbidden-terms.json`，取四套清单并集并按 tier 分组（core / no_price / strict / score_ok）；四个生成器已全部改为 `forbidden_terms(tier)` | 共享层测试覆盖 tier 语义；`make audit` 检查是否有人重新内联 |
| **P1-1** | 新建 `skills/_shared/design-tokens.css`；四个生成器的 `:root` 清空为占位，渲染时由 `inject_design_tokens()` 注入共享令牌（注入时剥除维护者注释） | 逐字段比对确认 22 个令牌取值原本完全一致；端到端生成 4 份报告验证 |
| **P1-1 剩余** | 新建 `skills/_shared/shell.css`（页面骨架 + 徽章基座，注入时 896 字符）；四个生成器改用 `inject_shared_css()`（令牌 + 外壳），模板里删除全部骨架规则；顺带修掉 daily 的 `.badge` 缺 `display:inline-flex;align-items:center` 漂移，并把泄漏进交付物的中文维护者注释移出模板字符串 | **逐选择器结构化比对**：确认四份报告原本逐字节一致的只有 5 条骨架规则（≈900 字符，非最初估计的 2.4 万字符）；重构后四份报告的规则数完全持平（113/61/64/92），取值差异仅剩 body 补字体平滑与 daily 徽章补 `display/align` 两项有意改动 |
| **P1-2** | 技术面口径上移为 `skills/_shared/technical-analysis.md`；company 的本地文件改为指路文件；news 删除硬编码的 45 行 prompt | 护栏测试：本地文件必须指向共享层且短于共享文件 |
| **P1-3** | capital 的实测避坑清单移入 `data-routing.md` 第六节；**顺带修掉该文件的结构 bug**——小节序号乱序（五·六/五·七 排在 五·五 前）与 3 条掉队列表项（5/6/7 卡在错误章节） | 章节序号已连续 |
| **P1-4** | daily 的两段「实测口径经验」按主题重组进 `references/data-pitfalls.md`（147 行）；SKILL.md 128 → 119 行，只留三条高频规则 + 指针 | `make audit` 输出 SKILL.md 行数供持续观察 |
| **P1-6** | `install.sh` 改为**自动发现** `skills/*/SKILL.md`（去掉手写数组），挂载目标增加 `~/.workbuddy/skills`，新增 `--dry-run` 与共享层缺失检查，顺带清理 `__pycache__` | `./install.sh --dry-run` 实测发现 6 技能 × 3 目标 |
| **P2-1/P2-2** | 新增 `tools/run_skill_tests.py`（测试运行器）+ `Makefile`（test / test S= / audit / selftest / install / clean）+ `.github/workflows/skills-test.yml`（Python 3.10 & 3.13 矩阵） | `make test` / `make test S=xxx` / `make audit` 均实测可用 |

### 本次新增的关键护栏

`skills/_shared/tests/test_ashare_shared.py` 与 `tools/audit_shared_layer.py` 专门防止漂移重新长出来：

- 生成器不得再内联禁词表（必须 `forbidden_terms(tier)`）
- 模板里 `:root` 必须为空占位，不得写回色值
- 模板里不得再出现页面骨架规则（`*{box-sizing}` / `.masthead{` / `.eyebrow{` / `body:before{` / 字体平滑），必须走 `inject_shared_css()`
- 技能不得保留技术面规则的完整副本
- `_shared` 不得出现 `SKILL.md`
- 核心令牌取值不得被改动
- 共享外壳自身不得含禁词（会被注入每一份报告）
- **任一脚本模块不得超过 700 行**（P2-5 拆分后防止重新长回巨型单文件）
- **扫描范围是技能 `scripts/` 下全部 `.py`**，不是入口脚本单个文件——拆分后漂移可能藏在任一模块里
- **禁词豁免技能（research-journal）不得加载禁词 tier，且必须保留「不构成投资建议」声明**（P2-6；报告逐字引用冻结原文，无法设硬门禁）

### 尚未执行（建议下一批）

> **关于 P1-1 的认知更正**：最初估计「四个生成器有约 2.4 万字符重复的组件 CSS」。逐选择器结构化比对后证明该估计是错的——真正四份逐字节一致的只有约 900 字符的页面骨架，其余是有意不同的组件样式。P1-1 已在第一批（令牌）与第二批（外壳）收口，**不要再把「合并四份组件 CSS」当作未完成项**：强行合并只会破坏各报告的差异化布局，收益为负。

| 项 | 内容 | 说明 |
|---|---|---|
| **P2-3** | evals 的 `files` 仍全为空数组，无法自动回归 | 多数技能已有 `tests/fixtures/` 可挂 |
| **P2-4** | 渲染层断言只补了 news 一个技能 | 另外三个生成器仍缺「禁词零命中/JSON 可解析/缺字段即拒绝」的测试 |
| ~~**P2-5**~~ | ~~两个生成器未拆分；`gen_dashboard.py` 顶部硬编码 28 格样例数据~~ | **已完成**（2026-09-10）：见下方「P2-5 收口记录」 |
| ~~**P2-6**~~ | ~~`ashare-research-journal` 仍无 HTML 输出~~ | **已完成**（2026-09-10）：见下方「P2-6 收口记录」 |
| **P3** | description 瘦身与引号统一、输出路径约定统一、跨技能字段契约、示例日期占位符 | 细节批次 |
| **新增发现** | `data-routing.md` 结构 bug 已修，但 capital 与 news 的 SKILL.md 仍偏长（250 / 361 行） | 建议按 daily 的方式继续把「按日期沉淀」的段落移入 references |

### P2-5 收口记录（2026-09-10）

**目标**：把模板与数据、校验与渲染从巨型单文件里拆开，同时保证对外行为零变化。

| 技能 | 拆分前 | 拆分后 |
|---|---|---|
| capital | `gen_dashboard.py` 1,108 行（含 422 行内联 28 格样例数据，真实行数 672） | `gen_dashboard.py`(90) · `schema.py`(32) · `validate.py`(121) · `derive.py`(96) · `render.py`(170) · `page_template.py`(262) · `_paths.py`(17) |
| daily | `generate_daily_review.py` 1,761 行 | `generate_daily_review.py`(157) · `schema.py`(105) · `validate.py`(630) · `derive.py`(465) · `render.py`(483) · `_paths.py`(17) |

**关键动作**

1. capital 的 28 格样例数据移到 `examples/sample-cells.json`（含 `_comment` 标明「演示用样例数据（非生产数据）」），`load_records(None)` 改读该文件；测试不再 AST 解析脚本内 `CELLS`。
2. capital 消除 `SECTOR_ADVICE` 模块级副作用：`load_records` 改为返回 `(records, sector_advice)`。
3. daily 用 AST 机械迁移（按顶层节点切分 + 引用分析自动生成 import），消除 `validate ↔ derive` 循环：把通用取值器 `value()` 上移到 `schema.py`。
4. 护栏升级：`tools/audit_shared_layer.py` 与 `_shared/tests/test_ashare_shared.py` 改为扫描技能 `scripts/` 下**全部** `.py`，并新增 700 行单文件上限。
5. 文档同步：两个技能的 SKILL.md / references、`_shared/README.md`。

**行为不变证据**

- capital：`--as-of` 取 2026-07-31 / 2026-07-05 / 2020-01-01 三档，重构前后 HTML 逐字节相同（`cmp` 通过）；`--check` 输出相同。
- daily：market / unknown 两个 fixture 跑出的 `report.md`、`report.html`、`unknown.*`、history 快照全部逐字节相同；`summary.json` 仅 `history_path` 字面量不同（因为输出目录不同）。
- `make test` 84 个测试全绿；`make audit` 无漂移；`make selftest` 正常。

**有意保留**：daily 的 `validate.py` 630 行，是内聚的一整套契约校验；再往下切会产生循环导入，故上限设为 700 行留出余量。


### P2-6 收口记录（2026-09-10）

**目标**：`ashare-research-journal` 的 `show` / `stats` 从 JSON 改为**自包含 HTML 报告**，替换原文字输出
（用户明确选择「替换」而非新增 `--html-out`）。`record` / `observe` / `due` / `export` 保持 JSON，供脚本消费。

| 技能 | 拆分前 | 拆分后 |
|---|---|---|
| research-journal | `research_journal.py` 641 行（单文件，无 HTML） | `research_journal.py`(118) · `schema.py`(64) · `validate.py`(201) · `derive.py`(388) · `render.py`(548) · `page_template.py` · `_paths.py` |

**关键动作**

1. 先按 P2-5 同款 AST 机械迁移拆出 `schema / validate / derive`，12 条命令输出逐字节一致（仅 `recorded_at` 时间戳与 `history_path` 字面量在归一化后不同）——**先证明拆分零行为变化，再动输出格式**。
2. `stats()` 扩展返回 `records` 逐条明细（聚合值逐字段比对不变），用于画超额分布与 Brier 校准散点。
3. 新建 `render.py` + `page_template.py`：`render_record()`（记录标识/冻结判断/证据表/到期结果+价格路径图/判断审计）、`render_stats()`（命中率仪表 + 超额分布 + Brier 校准散点 + 逐条明细 + 限定说明）；末尾 `inject_shared_css()` 注入令牌与外壳。
4. 入口改输出分发：`show` / `stats` 写 HTML（默认 `research/research-journal/`，`--out` 可覆盖）并打印路径与字节数；其余命令仍 `print_json`。
5. **禁词门禁的例外**：报告逐字引用冻结原文，不可改写，故不设禁词硬门禁，改用固定「报告性质」声明（`不构成投资建议…`）。审计与共享层测试新增 `FORBIDDEN_EXEMPT_SKILLS`：豁免技能不得加载禁词 tier、必须保留该声明，同时仍接受令牌/外壳/`_paths`/700 行上限的全部检查。
6. `_shared/README.md` 的「谁引用」列更新为 5 个 HTML 报告生成器，并单列豁免说明；`report-template.md` 由 Markdown 模板改写为「HTML 报告结构 + 人写归因」。

**验证**

- 12 条 CLI 记录/复核/统计命令在拆分后输出逐字节一致（HTML 改造前的基线对照）。
- 新增 12 条测试：`show` 断言共享令牌/外壳已注入、冻结原文逐字出现、两个 SHA 留痕、价格路径图存在；未写结果时只降级（无审计卡、无路径图、无评分）；`stats` 断言 A 股红涨绿跌口径、命中率/Brier 数值、空态不画图不编数；默认输出路径作用域。
- 内联 JS 全部 `node --check` 通过；生成的 HTML 无残留 `{{占位符}}`。
- `make test` 89 个测试全绿；`make audit` 无漂移（表内已含 research-journal，标记为「豁免」）。

**有意保留**：豁免技能不登记进 `tier_map`（它确实不加载禁词），避免后来者误以为存在门禁。


---

## 一、总体判断

| 维度 | 状态 | 说明 |
|---|---|---|
| 单技能内部质量 | 好 | 边界、证据纪律、质量门、点时口径写得清楚，明显强于一般 skill |
| 技能间一致性 | **差** | 视觉、禁词、技术面口径、输出路径四类本该共享的东西各写一份 |
| 工程化防护 | **缺失** | 无 CI、无 Makefile、无 pyproject；53 个测试靠手动跑 |
| 可回归性 | **弱** | 6 份 evals 的 `files` 全为空，无法自动验收 |
| 安装/分发 | **过时** | `install.sh` 只挂 codex/claude，实际生效的是 `~/.workbuddy/skills` |

严重度分布：P0（会直接导致错误输出）2 项，P1（持续制造漂移）6 项，P2（可维护性）6 项，P3（细节）4 项。

---

## 二、P0 — 会直接产生错误输出的问题

### P0-1. news-investment-targets 与 company-research 的技术面口径直接冲突

这是全库唯一的实质性红线冲突，同一个问题在两个技能里得到相反答案。

| 技能 | 原文 | 位置 |
|---|---|---|
| company-research | 「没有精确数据时写"技术面未验证"，**禁止估算**均线、MACD、支撑压力、中枢、买卖点或关注价位」 | SKILL.md:84 |
| company-research | 「无法取得精确序列时，只能输出"技术面未验证"和待获取字段；**禁止估算**股价、均线、MACD、成交量、支撑压力、中枢或买卖点」 | references/technical-analysis.md:14 |
| news-investment-targets | 「具体的关注价位：**买入观察价、止损价、止盈参考价**」 | SKILL.md:328 |
| news-investment-targets | 「如果无法获取精确数据，**用区间估算**并标注"数据为估算"」 | SKILL.md:330 |

放大伤害的三点：

1. news 的 `FORBIDDEN` 清单**不含**「止损 / 止盈 / 买入观察 / 关注价位」，所以自己的质检拦不住自己。
2. news 的其他三处仍在强调反编造（「不得补股票代码、价格、行情」「不能把空白项渲染成图表、价格或买卖建议」），与阶段C 的「区间估算出价」在同一份文件里自相矛盾。
3. 6 个技能中有 4 个明确禁止价位（company / daily / journal / screening），news 是唯一的例外。库整体口径是「不给价位」，news 是异类。

**建议（二选一，推荐方案 A）**

- 方案 A（与全库对齐）：删除 news SKILL.md 第 328 行的价位输出要求，改为条件式表达——「若跌破 X，则原判断失效」，并把阶段C 改为引用 company 的 `references/technical-analysis.md`，删掉硬编码的 45 行 prompt。同步在 `generate_news_targets_html.py` 的 `FORBIDDEN` 中加入「止损 / 止盈 / 买入观察 / 关注价位 / 数据为估算」。
- 方案 B（保留短线价位能力）：承认这是有意的例外，在 news SKILL.md 顶部显式声明「本技能是库内唯一允许输出价位区间的技能」，并把价位披露规则写清（必须标注数据来源 + 复权口径 + 截止日；「区间估算」只能标未验证、不得用于价位）。同时仍需给 FORBIDDEN 加词，把「估算出来的价位」和「真实数据算出的价位」在渲染层区分开。

---

### P0-2. 禁词清单 4 套不同，同一句话在不同技能被拦或放行

| 技能 | 禁词清单 | 拦截强度 |
|---|---|---|
| capital-environment | 买入 / 卖出 / 建议买 / 建议卖 / 目标价 / 目标仓位 / 牛熊分数 / 总分 / 确定牛 / 确定熊 / 必然涨 / 必然跌 | **最严**（拦裸「买入」） |
| daily-market-review | 建议买入 / 建议卖出 / 目标价 / 目标仓位 / 建议轻仓 / 建议半仓 / 建议重仓 / 建议空仓 / 建议加仓 / 建议减仓 / 确定牛市 / 确定熊市 / 必然上涨 / 必然下跌 | 中 |
| company-research | 建议买入 / 建议卖出 / 目标价 / 目标仓位 / 建议加仓 / 建议减仓 / 建议满仓 / 建议清仓 / 保证收益 | 中 |
| news-targets | 建议买入 / 建议卖出 / 目标价 / 目标仓位 / 建议加仓 / 建议减仓 / 建议满仓 / 建议清仓 / 保证收益 | 中（且无价位词，见 P0-1） |
| research-journal | 无（脚本不生成 HTML，无扫描机制） | — |
| stock-screening | 无 | — |

后果：「建议满仓」在 capital 被放行（它只拦裸「买入」，不拦「满仓」），在 company 被拦；「确定牛市」在 daily 被拦，在 capital 也被拦但拦的是不同写法。

**建议**：新建 `skills/_shared/forbidden-terms.json`，取四套的**并集**并分组（交易指令类 / 仓位类 / 价格目标类 / 收益承诺类 / 绝对化断言类）。四个生成器 `import` 同一份，各技能按需取子集并在 SKILL.md 里改为「禁词以 _shared/forbidden-terms.json 为准，本技能额外补充：…」。这样新增一个词只改一处。

---

## 三、P1 — 持续制造漂移的结构问题

### P1-1. 视觉系统被复制 4 份，且已经开始漂移

SKILL.md 里反复强调「视觉必须与 ashare-daily-market-review 完全一致」，但没有任何共享机制，靠人工自律。

| 生成器 | 内嵌 CSS | 自定义属性数 |
|---|---|---|
| generate_daily_review.py | 8,236 字符 | 8 |
| gen_dashboard.py | 9,242 字符 | **22** |
| generate_news_targets_html.py | 4,913 字符 | 8 |
| generate_company_research_html.py | 4,045 字符（`STYLE` 常量） | 5 处 `--paper` |
| **合计** | **约 26,400 字符** | 已不一致 |

自定义属性从 22 → 8 → 8，说明「完全一致」这个断言现在**已经不成立**。改一次配色要改 4 处，任何一处漏改就会让两个报告长得不一样。

> **实测更正（同日）**：上表的「约 26,400 字符」是四份 CSS 的**总量**，不是重复量。把它们按「选择器 + 声明」结构化比对后发现：真正四份逐字节一致的只有 5 条页面骨架规则（`*` / `body` / `body:before` / `.masthead` / `.eyebrow`，约 900 字符），其余约 2.5 万字符是各报告**有意不同**的组件样式。因此真正该共享的只有两块：**配色令牌**与**页面骨架**；组件样式不要动。

**已执行**：新建 `skills/_shared/`，落 `design-tokens.css`（令牌唯一真源）+ `shell.css`（页面骨架 + 徽章基座唯一真源）+ `ashare_shared.py`（零依赖加载器，`inject_shared_css()` = 令牌 + 外壳）。四个生成器改为 import，模板只留空的 `:root{}` 占位。SKILL.md 里所有「视觉必须与 X 一致」的表述应改为「视觉规范见 `_shared/`，本技能不得新增色板或改写页面骨架」。

### P1-2. 技术面分析 prompt 重复实现，且完全没有交叉引用

- company-research 有专门的 `references/technical-analysis.md`（60 行，含数据门、趋势跟踪、缠论边界、输出规范）。
- news-investment-targets 把整套技术面 prompt **硬编码**在 SKILL.md 第 296–331 行（约 45 行，覆盖趋势 6 项 + 缠论 7 项）。
- 两者讲的是同一套方法，但 news **零引用** company 的资料（已 grep 证实 `technical-analysis` 在 news 目录下无任何出现）。

**建议**：提升为 `skills/_shared/technical-analysis.md`，两边引用同一份；news 的子 agent prompt 只保留「标的清单 + 数据获取指令」，分析框架指向共享文件。

### P1-3. capital-environment 的 28 格地图写了两份

SKILL.md 第三节「28 格数据获取地图（速查）」与 `references/data-routing.md`（161 行）内容重叠。SKILL 自己也写了「详细版在 references/data-routing.md，这里是速查」，但速查表里同样含实测值、代理口径、缺口标记——两边都会随实测更新而漂移。

**建议**：SKILL.md 只保留「从哪拿」的一句话摘要（每维度一行）+ 3 条通用纪律，实测值/查询措辞/缺口全部只留在 `data-routing.md`。

### P1-4. daily-market-review 的「实测口径经验」已膨胀成 changelog

SKILL.md 共 128 行，其中第 103–122 行是按日期追加的两段经验（「2026-08-29 沉淀」6 条、「2026-09-10 沉淀」9 条），占约 20 行且会继续增长。SKILL.md 是给模型读的操作手册，不是开发日志；而且这些经验（采集通道故障、股票池口径、滚动窗口、北向断供）**已经都是操作规则，不是历史记录**。

**建议**：新建 `references/data-pitfalls.md`，按主题重组为四类——「股票池口径」「采集通道与重试」「滚动指标窗口」「数据源断供与兜底」；SKILL.md 只留 3 条最关键规则 + 一行指针。后续每次沉淀写进 references，SKILL.md 不再增长。

### P1-5. 输出路径与命名 5 套不统一

| 技能 | 产物命名 | 落盘位置 |
|---|---|---|
| daily-market-review | `daily-review-{date}.md/.json/.html` | 当前目录 + `~/.ashare/daily-market-history` |
| capital-environment | `ashare-capital-environment-dashboard-{date}.html` | 默认 `research/capital-environment/` |
| company-research | `company-research-{ticker}-{as_of}.html` | 当前目录 |
| news-investment-targets | `news-targets-{as_of}.html` | 当前目录 |
| research-journal | （无 HTML） | `~/.ashare/research-journal.sqlite3` |

命名前缀不一致（`ashare-` 前缀只出现在 capital），日期字段名不一致（`date` vs `as_of`），落盘位置不一致（三个技能落当前目录，一个落固定子目录）。用户要批量找产物时必须记 5 套规则。

**建议**：定 `skills/_shared/output-conventions.md`——产物统一 `research/{skill-short}/`，文件名统一 `{skill-short}-{YYYY-MM-DD}[-{ticker}].{ext}`，本地状态统一 `~/.ashare/`。

### P1-6. `install.sh` 与实际安装方式脱节，README 是第三份重复清单

- `install.sh` 只 link 到 `~/.codex/skills` 和 `~/.claude/skills`；实际生效的是 `~/.workbuddy/skills/ashare-*`（2026-08-30 建立的软链）。
- README「同步」表也只写 codex/claude。
- `install.sh` 的 `SKILLS` 数组需手动追加；README 的表格列了同样 6 个技能名。**同一份清单现在有 3 处**（install.sh / README / 文件系统），新增技能必漏。
- `install.sh` 也不清理技能目录里的 `.pyc`（当前磁盘 14 个）。

**建议**：`install.sh` 增加 `~/.workbuddy/skills`；技能列表改为自动发现 `for src in "$ROOT_DIR"/skills/*/; do`（要求存在 `SKILL.md` 才挂），彻底去掉手写数组；README 的清单改为从脚本生成或直接删掉，只留一句「`./install.sh` 自动挂载 `skills/` 下所有技能」。

---

## 四、P2 — 可维护性与可回归性

### P2-1. 无 CI，53 个测试全靠手动

6 个测试套件、53 个测试**全部通过**（实测：daily 20 / screening 9 / company 7 / journal 7 / capital 5 / news 5）。但每次都在 SKILL.md 里写「修改脚本后运行 unittest」——4 处 SKILL.md 有这句，说明这是明确的手动检查点。用户的既定习惯是「每次运行后把经验沉淀回 skill / scripts」，脚本会被频繁改，没有 CI 迟早带着红测试提交。

**建议**：加 `.github/workflows/skills-test.yml`，矩阵跑 6 个技能目录；本地加根 `Makefile`（`make test` / `make test S=ashare-daily-market-review` / `make install`）。

### P2-2. 无任何工程配置

没有 `pyproject.toml`、`requirements.txt`、`Makefile`、`pytest.ini`。「脚本只用标准库」是优点（零依赖可移植），但连一个统一的测试入口都没有，新技能加进来要重新读 SKILL.md 找命令。

**建议**：根目录一个 `Makefile` 即可，不引入新依赖。

### P2-3. evals.json 全部 `files: []`，无法自动回归

6 个技能都有 evals（5–13 条不等，内容质量不错，覆盖了禁词、点时、非交易日、股票池不一致等关键场景），但 `files` 字段全是空数组，且没有 `expected_output` 以外的机器可判据。结果是最有价值的一份资产只能靠人读。

**建议**：给每条 eval 挂 fixture（多数技能已有 `tests/fixtures/` 可直接复用），并为可机判的项（禁词零命中、缓存 SHA 一致性、缺失即拒绝、非交易日不冒充）补断言，做成 `make eval` 一键跑。

### P2-4. 测试覆盖不均，且缺渲染产物断言

| 技能 | 脚本行数 | 测试数 |
|---|---|---|
| daily-market-review | 1,769 | 20 |
| capital-environment | 1,108 | **5** |
| research-journal | 641 | 7 |
| stock-screening | 513 | 9 |
| news-targets | 235 | 5 |
| company-research | 219 | 7 |

capital-environment 的脚本最大第二、测试最少（5 个）。同时 4 个 HTML 生成器都**没有渲染产物的断言**——而 SKILL.md 里恰好写了三条人工自检命令（node 语法检查、CELLS JSON 可解析、禁词扫描），这些本该是测试。

**建议**：把这 3 条自检变成测试用例，对每个生成器都跑：①禁词零命中；②注入的 JSON 可解析；③必填字段缺失时生成器必须拒绝；④无数据格不画图不填零。

### P2-5. 巨型单文件脚本，模板与数据混装

- `generate_daily_review.py` 1,769 行；`gen_dashboard.py` 1,108 行。校验、派生、渲染、CLI 混在一个文件。
- `gen_dashboard.py` 第 26 行起把**28 格真实样例数据**（含实测值、来源、analysis、risk）硬编码在脚本顶部，与生产逻辑同处一文件；SKILL.md 还说「样例数据可直接生成」——演示数据和生产数据没有物理隔离，容易误用。

**建议**：拆为 `validate.py` / `derive.py` / `render.py`（同目录），样例数据移到 `examples/sample-cells.json`。

### P2-6. 只有 4/6 技能有可视化，journal 的缺失最可惜

company / news / daily / capital 都有 HTML，**stock-screening 和 research-journal 没有**。research-journal 尤其可惜——它的 `stats` 已经算好了命中率、平均超额、平均最大回撤、Brier 分数，这些是整库最适合图表的数据（且用户明确偏好图表优于文字）。现在这些关键结论只能以文字呈现。

**建议**：给 `research_journal.py` 加 `--html-out`，渲染命中率仪表、超额分布、Brier 校准散点；复用 `_shared/design-tokens.css`。screening 可选（漏斗图 + 排除原因分布）。

---

## 五、P3 — 细节

| # | 问题 | 位置 | 建议 |
|---|---|---|---|
| P3-1 | description 过长，且含中文弯引号 `”`（不是 `“`） | news 274 字、capital 287 字、company 222 字；news 第 3 行 | 收紧到 ~120 字，触发词列全、实现细节移入正文；统一引号 |
| P3-2 | 「与其他技能的关系 / 何时不用」结构不统一 | daily 有专章并点名 3 个技能；capital 第七节；company/screening/journal/news 只在正文零散提及 | 统一一段「何时不用本技能 → 交给谁」，并维护 `_shared/routing.md` 一张技能关系图 |
| P3-3 | 跨技能交接无字段契约 | screening 输出 JSON → company-research 输入 JSON，证券标识字段未统一定义 | 定义 `_shared/entities.md` 的最小公共同构（证券标识 / 日期 / 来源 / 证据对象） |
| P3-4 | SKILL.md 示例命令用具体历史日期（`--as-of 2026-08-25` 等 20 处） | 各技能 | 示例统一改 `<YYYY-MM-DD>` 占位符，避免被照抄成默认值 |
| P3-5 | 14 个 `.pyc` 散落技能目录 | 各 `scripts/__pycache__`、`tests/__pycache__` | 未入 git（`.gitignore` 已排除），但会随目录被打包；install.sh 里顺带清理 |

---

## 六、建议的执行顺序

1. **先修 P0-1**（技术面冲突）——这是唯一会让同一份输入得到相反输出的问题，且涉及红线一致性。
2. **再建 `skills/_shared/`**（P0-2 + P1-1 + P1-2）——禁词表与设计 tokens 是最高频的共享点，建好后 P1 里的重复项顺势解决。
3. **加 `Makefile` + CI**（P2-1 + P2-2）——在动共享层之前先有防护网，重构才有底气。
4. **拆 SKILL.md 里的日志**（P1-4 + P1-3）——把 changelog 挪进 references，让 SKILL.md 回归操作手册。
5. **修 install.sh + README**（P1-6）——去掉三份重复清单。
6. ~~**给 journal 加 HTML**（P2-6）——结果选择「替换现有文字输出」而非新增开关~~ **已完成**（2026-09-10）。
7. **P3 细节**——批量清理。

---

## 七、值得保留的部分（不要在重构中弄丢）

- **点时纪律**：`published_at ≤ as_of` 的硬门禁，6 个技能一致，是整库最扎实的设计。
- **缺口诚实**：unknown / partial 不用 0 填充、代理必须标注口径，这套「诚实降级」逻辑在金融技能里非常少见且正确。
- **不可覆盖的研究日志**：research-journal 的 SHA + revision + supersedes 设计，以及「评价日前禁止打分」，是真正的审计级设计。
- **实测经验沉淀的习惯**：把踩坑写回技能本身（如「westock K 线倒序必须先反转」「东财涨停池不含 ST」）——价值很高，问题只在**存放位置**（该进 references，不该留在 SKILL.md 正文）。
- **53 个测试全绿**：单技能内部的测试纪律是好的，只需要补渲染层断言和 CI 自动化。

---

## 八、追加：v2 统一品牌设计系统（2026-09-10 下午）

### 起因

用户要求：**所有会产出展示的技能，统一成同一套品牌视觉**——新瑞士平面设计 / 现代科技编辑系统 / 柔和粗野主义 / 高对比、网格化。原状态是「4 份各写一遍的深墨绿研报风」，正是 P1-1 未彻底解决的尾部：骨架与令牌已上移共享层，但**组件样式仍各留一份**，且配色仍是从 v1 深色画布演化的产物。

### 结论：三层品牌层 + 后注入

| 层 | 文件 | 注入点 |
|---|---|---|
| 令牌 | `skills/_shared/design-tokens.css` | 替换模板里的空 `:root{}` |
| 外壳 | `skills/_shared/shell.css` | 与组件一起包成 `<style id="ashare-brand">` |
| 组件 | `skills/_shared/components.css` | **插在 `</head>` 之前**（排在各技能 `<style>` 之后） |

`inject_shared_css(html) == inject_brand_css(inject_design_tokens(html))`。

**注入顺序是本次最关键的架构决定**：品牌层后写，才能覆盖各技能模板里遗留的旧组件样式。v1 插在 `:root` 之后（技能之前），那时外壳只能放技能绝不重定义的东西。代价是**技能模板里不能再重复任何组件规则**——写了会变成被覆盖的死代码，因此新增了两组护栏针（`SHELL_NEEDLES` / `COMPONENT_NEEDLES`），`make audit` / `make test` 都会拦下回写。

### 语义色重构（消除事故源）

| 轴 | 令牌 | 用途 |
|---|---|---|
| 涨跌 | `--gain` / `--loss`（A 股：红涨绿跌） | 收益、涨跌幅、超额 |
| 状态 | `--state-ok` / `--state-warn` / `--state-bad` / `--state-unknown` | 可得性、覆盖度、通过与否、风险等级 |
| 品牌 | `--accent`（钴蓝） | 眉题、规线、链接、编号，不承载语义 |

删除 `--market-up` / `--market-down`（旧义「绿=可得」，与红涨绿跌相反）及其徽章别名 `badge-up` / `badge-down` / `badge-mid`。capital 的 `AVAIL_BADGE_CLASS` 改为 `badge-available` / `badge-partial` / `badge-unknown` / `badge-muted`。等级与优先级刻意走「黑→灰」明度阶梯，避免与涨跌/状态串轴。

### 各技能收敛结果

| 技能 | 内联 CSS（压缩后） | 保留在模板里的独有部分 |
|---|---|---|
| capital | 5253 → 4681 | `.tw-*` / `.sa-*` / `.an-*` / `.cell-head` / `.cell-evidence` |
| daily | 5253 + 2147（两处） → 560 | 情绪五态语义色、`.section-note` / `.evidence` |
| company | 3093 → 1212 | `.thesis` / `.signal` / 三档 `.panel.market\|facts\|proof` |
| news | ~3940 → 1613 | `.candidate-head` / `.candidate-meta` / `.chain-grid` |
| journal | 已在上轮收敛 | `.judge` / `.crit` |

同时：capital 的 `examples/sample-cells.json` 色值、ECharts 内联配色、`references/html-template.md`（去掉 320 行重复模板，改为指路 + 图表约定 + JSON 契约）、`aguhot-design-spec.md` 视觉章节、5 个 SKILL.md、3 个 evals、`.scd/ux/` 说明，全部同步到 v2。

### 护栏升级

- `REQUIRED_ASSETS` 增加 `components.css`；审计新增身份硬约束检查（禁止胶囊圆角、禁止带模糊的柔和阴影、禁止行情词徽章别名）。
- 共享层测试新增 `ComponentsTests`（8 条），并区分「表面层」与「抗回写」两组断言。
- 测试规模：53 → **100 个**（7 个套件）；`make audit` 新增组件层字符数与回写检测。

### 未做（有意留白）

- `ashare-stock-screening` 只产出 JSON，没有展示层，因此不在本次换装范围。
- 各技能的组件内边距与栅格列数仍未令牌化，继续留在各自模板——它们本就是布局语义，硬拧只会坏事。
