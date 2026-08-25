---
name: ashare-research-journal
description: 持久记录并事后复核A股研究判断，冻结“当时证据、研究假设、评价日期、成功标准和证伪条件”，到期后计算真实收益、基准超额、最大回撤、MFE/MAE、命中率和概率校准。当用户说“记录这次研究”“到期复盘”“看看以前判断准不准”“统计AI研究命中率”时使用；不用于生成新的公司研究、交割单分析或自动交易。
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

```bash
python3 scripts/research_journal.py --db journal.sqlite3 show --id RESEARCH_ID
python3 scripts/research_journal.py --db journal.sqlite3 stats --as-of 2026-12-31
python3 scripts/research_journal.py --db journal.sqlite3 export
```

统计只使用已成熟且已有结果的记录：

- 命中率。
- 平均股票收益、平均超额和平均最大回撤。
- 提供概率的记录计算Brier分数；没有概率的记录不进入校准分母。

统计结果描述历史样本，不代表未来能力。样本量、行业集中、市场阶段和选择偏差必须同时说明。

## 五、输出

向用户汇报时读取[复盘模板](references/report-template.md)，至少展示：

1. 原始快照SHA和当时证据。
2. 成功标准与证伪条件。
3. 到期表现和计算口径。
4. 命中、证伪和校准结论。
5. 对研究流程的可复用改进，不把一次输赢归因成普遍规律。

## 六、质量门

- 是否能证明每项证据在`as_of`时已经公开。
- 是否使用显式评价日期和成功标准。
- 是否避免用评价日后的价格进入路径。
- 是否保留原快照、结果输入和两个SHA。
- 是否把触发证伪与市场结果分别说明。
- 是否只用成熟样本计算统计。

修改脚本后运行：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```
