---
name: ashare-research-journal
description: 持久记录并事后复核A股研究判断，冻结“当时证据、研究假设、评价日期、成功标准和证伪条件”，到期后计算真实收益、基准超额、最大回撤、MFE/MAE、命中率和概率校准。查看(show)与统计(stats)输出自包含HTML复盘报告，记录/复核/导出保持JSON。当用户说“记录这次研究”“到期复盘”“看看以前判断准不准”“统计AI研究命中率”时使用；不用于生成新的公司研究、交割单分析或自动交易。
---

# A股研究结论事后复盘

本技能让研究结论接受时间检验。记录的是“当时可见证据和明确假设”，不是事后回忆；评价的是结构化标准和证伪条件，不是模糊地看股价是否上涨。

## 一、授权与边界

只有用户明确要求记录、保存或复盘时才写入本地数据库。不要因为完成了`ashare-company-research`或`ashare-news-investment-targets`就自动持久化。

- 默认数据库：`~/.ashare/research-journal.sqlite3`，可用`--db`指定。
- 数据仅写本地SQLite，不上传、不接券商、不自动抓行情。
- 快照和结果写入后不可覆盖；发现错误时保留原记录并另建新的research_id。
- 本技能不生成买卖、目标价、仓位或止损指令。

## 二、冻结研究快照

读取[数据契约](references/data-contract.md)，准备`snapshot.json`。快照至少包含：

- 股票、市场、`as_of`、显式`evaluation_date`。
- 当时研究假设、催化剂和证伪条件。
- 结构化成功标准：`metric/operator/value`。
- 股票和基准的基线价格证据。
- 可选概率`probability`，范围0到1。
- 原始证据及观察日、发布日期、抓取时间和来源。

```bash
python3 scripts/research_journal.py \
  --db ~/.ashare/research-journal.sqlite3 \
  record --input snapshot.json
```

脚本保存规范JSON和SHA-256。`published_at > as_of`、重复research_id、来源缺失或评价日期早于as-of都会失败关闭。

## 三、到期复核

先列出已经到期但没有结果的记录：

```bash
python3 scripts/research_journal.py --db journal.sqlite3 \
  due --as-of 2026-08-31
```

准备`outcome.json`，提供股票价格路径；快照包含基准时还要提供基准路径。每个价格点继续携带来源和时间字段。

```bash
python3 scripts/research_journal.py --db journal.sqlite3 \
  observe --id r-600001-20260801-30d \
  --input outcome.json --as-of 2026-08-31
```

结果计算：

- 区间收益和相对基准超额。
- 最大回撤。
- 相对基线的最大有利偏离MFE和最大不利偏离MAE。
- 结构化成功标准是否通过。
- 是否触发快照中预先定义的证伪条件。

只有成功标准通过且没有触发证伪条件，`passed`才为真。评价日前禁止提前打分，结果存在后禁止覆盖。

## 四、查看和统计

`show` 与 `stats` 直接产出**自包含 HTML 报告**（不再打印 JSON），默认写到
`research/research-journal/`，可用 `--out` 覆盖；stdout 只回一行落盘路径与字节数。

```bash
# 单条复盘报告 → research/research-journal/<research_id>.html
python3 scripts/research_journal.py --db journal.sqlite3 show --id RESEARCH_ID

# 命中率统计看板 → research/research-journal/research-journal-stats-<as-of>.html
python3 scripts/research_journal.py --db journal.sqlite3 stats --as-of 2026-12-31

# 机器可读的导出仍是 JSON（保持管道可用）
python3 scripts/research_journal.py --db journal.sqlite3 export
python3 scripts/research_journal.py --db journal.sqlite3 due --as-of 2026-12-31
```

`record` / `observe` / `due` / `export` 仍是 JSON 输出，方便脚本消费；只有给人看的两条
（`show`、`stats`）改成了 HTML。

统计只使用已成熟且已有结果的记录：

- 命中率。
- 平均股票收益、平均超额和平均最大回撤。
- 提供概率的记录计算Brier分数；没有概率的记录不进入校准分母。

统计结果描述历史样本，不代表未来能力。样本量、行业集中、市场阶段和选择偏差必须同时说明。

## 五、输出与交付

`show` / `stats` 生成的 HTML 是最终交付物，生成后用 `present_files` 交给用户查看。

报告由 `scripts/render.py` 组装、`page_template.py` 提供模板，末尾统一经
`inject_shared_css()` 注入 `skills/_shared/` 的设计令牌与页面外壳——配色、报头、徽章基座
都来自共享层，**不要在模板里回填色值或骨架规则**。

报告结构见[复盘模板](references/report-template.md)：

1. 记录标识与不可变性（原快照 SHA、结果输入 SHA、记录时间）。
2. 当时判断：逐字引用冻结的研究假设、概率、成功标准、催化剂与证伪条件。
3. 当时证据表（论断 / 取值 / 观察日 / 发布日 / 来源）。
4. 到期结果：股票与基准价格路径图、区间收益、超额、回撤、MFE/MAE、成功标准判定。
5. 统计看板：命中率仪表、超额分布（红正绿负）、Brier 校准散点与逐条明细。

### 报告性质声明（本技能为何没有禁词硬门禁）

其余四个 HTML 生成器都对报告文字跑禁词 tier 硬门禁。本技能**不设**——报告逐字引用
用户当时冻结的研究原文（假设、催化剂、证伪条件），审查性引用不可改写，扫描禁词只会命中
不可避免的引用（例如用户自己写的「止损」「目标价」），拦下来只会逼人篡改历史。

替代方案是**固定的「报告性质」声明**，必须出现在每份报告里：

> 本报告为研究结论的事后复盘……报告不构成投资建议，也不预测未来表现。

这条声明留在 `render.py`（`RECORD_FOOT` / `STATS_FOOT`），`make audit` 与 `make test`
都会检查它是否还在；豁免技能若反过来加载禁词 tier，审计同样会失败。

## 六、质量门

- 是否能证明每项证据在`as_of`时已经公开。
- 是否使用显式评价日期和成功标准。
- 是否避免用评价日后的价格进入路径。
- 是否保留原快照、结果输入和两个SHA。
- 是否把触发证伪与市场结果分别说明。
- 是否只用成熟样本计算统计。
- HTML 是否注入了共享令牌与品牌层、是否保留「不构成投资建议」声明、未写结果前是否只降级不评分。

修改脚本后运行：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```
