---
name: ashare-stock-personality
description: 把一只或多只 A 股过去一段时间的交易行为统计成「股性画像」——六维指标（异动基因/溢价质量/埋人风险/流动性容量/资金关注度/弹性与趋势）、两个直读指标（每股年被选中次数、埋人率）、七个原型标签（连板妖股型/高波动题材型/情绪活跃型/高埋人风险型/趋势慢牛型/权重稳重型/普通型），并输出板块×原型矩阵与「股性地图」散点。适合用户说"这只股票股性好/股性差"“算一下股性”“埋人率高不高”“多长时间被拉一次涨停”“哪些票是连板妖股”“哪些票埋人”“做一份股性画像”“板块里谁最妖”等场景；也适合在一个股票池内做交易行为结构的横向比较。完整结果可生成与每日盘面复盘同风格的自包含可视化 HTML。
---

# 个股股性画像

本技能回答的问题不是「这只股票好不好」，而是：

```
这只股票过去的交易行为，属于哪一种结构？
（多久被拉一次、拉完给不给溢价、追进去埋不埋人、装得下多少成交、常不常被资金选中、涨得猛不猛）
```

输出的是**历史行为的统计描述**与**结构分类**，不是评级、不是买卖判断、不出现任何价位。默认市场为中国 A 股。

视觉系统来自报告族共享的「ASHARE EDITORIAL」品牌层（`skills/_shared/`：白纸黑字最高对比、可见网格、纯黑结构线、零圆角、硬投影），**不得在生成脚本里回填骨架或组件样式**；本技能只保留股性特有的版式（地图、矩阵、明细筛选）。

---

## 一、六维框架

| 维度 | 回答什么 | 原始特征（池内百分位 0–100） |
|---|---|---|
| D1 异动基因 | 多久被拉一次、连得上吗 | 异动次数/年、涨停次数/年、最高连板数 |
| D2 溢价质量 | 拉完次日给不给溢价 | 异动后次日平均涨跌幅、次日胜率 |
| D3 埋人风险 | 追进去后回撤有多深 | 埋人率（异动后 N 日回撤≤阈值占比）、次日大跌占比 |
| D4 流动性容量 | 装得下多少成交 | 成交额 / 流通市值 / 换手率（三选一，见下） |
| D5 资金关注度 | 常被资金选中吗 | 龙虎榜次数/年、龙虎榜净额均值 |
| D6 弹性与趋势 | 涨得多猛、守不守得住 | 年化波动率、60 日区间涨跌幅 |

**两条直读指标**（不参与百分位，直接给数）：

- **被选中次数/年** = (异动日 ∪ 龙虎榜日) 去重后的天数 ÷ 窗口年数。这是「这只票多久被市场挑中一次」的直接口径。
- **埋人率** = 异动事件中，事后 N 日内最大回撤 ≤ 阈值的比例。这是「追高被埋」的直接口径。

**综合股性分** = Σ 权重 × 维度分（权重由输入显式声明）。D3 是风险维度，进入综合分前先取 `100 − 分`。**六个维度必须全部可得才给综合分**：缺任何一维一律留空，绝不用 0 顶替。

> 所有维度分都是**池内百分位**：只表示在这批股票里的相对位置，换一个池子必须重算。这是相对比较，不是绝对好坏。

## 二、七个原型（固定优先级，首个命中即归类）

1. **连板妖股型** — 窗口内最高连板 ≥ 阈值（直接由连板数触发，与百分位无关；阈值须按窗口长度标定，12 个月窗口默认取 6，约命中前 15%）
2. **高波动题材型** — D1 高 + 弹性高，但 D2 低于中位切点
3. **情绪活跃型** — D1 高 + D2 高，且 D3 未到高位
4. **高埋人风险型** — D3 高 + D2 低于低切点
5. **趋势慢牛型** — 趋势分位高、60 日区间为正，且异动频率未达中位
6. **权重稳重型** — 容量分位高、弹性低、异动频率低
7. **普通型** — 未命中任何规则（**代表「未获足够证据归类」，不代表质地普通**）

**股性地图**：横轴 D1、纵轴 D2，以全样本中位数切四象限（高异动·高溢价 / 高异动·低溢价 / 低异动·高溢价 / 低异动·低溢价），气泡大小为容量、颜色深浅为 D3 风险。低溢价一侧代表「被选中频繁但次日承接偏弱」的结构。

## 三、数据来源与口径（重要）

| 数据 | 来源 | 回溯边界 |
|---|---|---|
| 个股日 K（前复权） | 腾讯 `web.ifzq.gtimg.cn/appstock/app/fqkline/get` | 长历史可用，含北交所外的全部 A 股 |
| 龙虎榜明细（含 D1/D2/D5/D10） | 东财 `datacenter-web` `RPT_DAILYBILLBOARD_DETAILSNEW` | ≥ 1 年 |
| 全 A 快照（成交额/换手/流通市值/行业） | 东财 `push2delay` clist | 当期快照 |
| 日均成交额 | 东财 `push2his` 日 K f57 | **接口常限流**，不可得时回退 |

**容量口径按证据等级从高到低自动挑选**：

1. `amount_avg_cny` 日均成交额 —— 交易所级一手证据（最优）
2. `float_cap_cny` 流通市值 —— 东财快照直接披露，代理「装得下多少成交」
3. `turnover_avg_pct` 日均换手率 —— 透明计算（成交量÷流通股本），**证据等级最低**，报告里单独标注

口径不同，D4 的含义不同：用换手率时 D4 读作「换手强度」，**不等于体量大**；用流通市值时 D4 读作「体量代理」。报告会自动把实际口径与含义写进口径区。

**已实测的坑**（详见 `references/data-pitfalls.md`）：

- 东财 `push2his` 日 K **本机限流**（curl 52 空响应），因此价格/成交量主源改用腾讯，东财只补龙虎榜与快照。
- 腾讯 `web.ifzq.gtimg.cn` 连续抓几百只后会**触发 WAF 返回 501**（响应体是 WAF 跳转页而非 JSON）。因此：交易日历在腾讯不可得时**降级为「缓存日线日期并集」**并在报告里写明来源；个股日线设**断路器**，连续 5 次失败即跳过剩余并如实记录跳过只数。
- 北交所 `920xxx` 腾讯日 K 不覆盖 → 直接排除，不猜。
- 涨跌幅由前复权序列相邻收盘价算出，除权日会失真，该日若真实涨停可能被低估。
- 龙虎榜 D1/D2/D5/D10 是上榜后的事后涨跌幅，只用于统计已发生的历史事件。

## 四、执行流程

```
① 确定股票池与窗口  →  ② 一键取数（组装 1.0 输入）  →  ③ 校验契约
→  ④ 派生（六维→综合分→原型→象限→矩阵→地图）  →  ⑤ 渲染 HTML/Markdown  →  ⑥ 禁词门
```

### 取数

```bash
make fetch-personality DATE=2026-09-15 MAX=600 OUT=research/stock-personality/personality_input.json
# 等价于：
python3 tools/fetch_personality_archive.py --as-of 2026-09-15 --lhb-months 12 \
  --max-stocks 600 --cache-dir /tmp/personality-cache \
  --out research/stock-personality/personality_input.json
```

默认股票池 = **近 12 个月登上东财龙虎榜、按上榜次数降序的前 N 只**（即「常被资金选中」的样本，股性差异最大、最有分析价值）。也可以传入自定义股票池 JSON。

### 生成

```bash
python3 skills/ashare-stock-personality/scripts/generate_personality.py \
  --input research/stock-personality/personality_input.json \
  --out   research/stock-personality/personality.md \
  --html-out research/stock-personality/personality.html \
  --summary-out research/stock-personality/personality_summary.json
# 只校验输入契约与禁词门：
python3 skills/ashare-stock-personality/scripts/generate_personality.py \
  --input research/stock-personality/personality_input.json --check
```

## 五、输入契约（schema_version = 1.0）

阈值**必须由输入显式声明**，缺任何一个切点直接拒收，不回退隐藏默认：

```jsonc
{
  "schema_version": "1.0",
  "as_of": "2026-09-15",
  "window": {"start": "2025-09-15", "end": "2026-09-15", "trading_days": 243},
  "capacity_metric": "float_cap_cny",          // amount_avg_cny | float_cap_cny | turnover_avg_pct
  "thresholds": {
    "limit_up_pct": {"main": 9.8, "gem": 19.8, "star": 19.8, "bse": 29.8, "st": 4.8},
    "spike_pct": 7.0,                           // 视为「异动」的最小绝对涨跌幅
    "dump_drawdown_pct": -8.0,                  // 埋人的回撤阈值
    "dump_window_days": 5,                      // 埋人观察窗口（天）
    "lhb_net_min_cny": 5000000,
    "score_weights": {"d1": 0.2, "d2": 0.2, "d3": 0.2, "d4": 0.1, "d5": 0.15, "d6": 0.15},
    "archetype": {"high": 70, "mid": 55, "low": 40, "legend_streak": 3,
                  "capacity_high": 70, "elastic_high": 70, "trend_high": 70}
  },
  "universe": {"name": "...", "description": "...", "count": 6,
               "selection_rule": "...", "excluded_count": 0},
  "stocks": [{
    "code": "300001", "name": "...", "board": "gem", "sector": "计算机",
    "bars": 243, "first_bar": "...", "last_bar": "...",
    "float_cap_cny": 8.2e9, "volatility_ann_pct": 95.0, "ret_60d_pct": 35.0,
    "spikes": [{"date": "2026-08-03", "change_pct": 19.8, "limit_up": true,
                "streak": 4, "next_day_pct": 1.0, "drawdown_nd_pct": -12.0}],
    "lhb": [{"date": "2026-08-03", "net_amt_cny": 1.8e8,
             "d1_pct": 10.0, "d2_pct": 12.5, "d5_pct": 8.0, "d10_pct": -4.0}]
  }],
  "sources": [{"name": "...", "url": "https://..."}]
}
```

硬校验：`code` 必须 6 位数字且不重复；`board` ∈ {main, gem, star, bse, st}；异动日必须落在窗口内；容量口径不允许全部缺失；阈值必须满足 `low ≤ mid ≤ high`。

## 六、输出

- `personality.md` / `personality.html`：总览 → 六维框架与本池均值 → 原型分布 → 板块×原型矩阵 → 板块排序 → 股性地图 → 个股明细（可按原型筛选/搜索/排序）→ 口径与方法 → 来源汇总。
- `personality_summary.json`：`overview` / `archetype_table` / `quadrant_counts` / `signals` / `caveats`，供下游引用。

**派生自洽校验**（`validate_derived`）：维度必须落在 0–100 且小数位 ≤ 4；六维齐全才允许有综合分；原型必须合法且有归类依据；板块×原型矩阵的只数必须与股票池守恒；无可计分样本的单元格均值必须为 None，不能用 0 占位。

## 七、合规红线

- 全文过共享禁词门，tier = **score_ok**：允许自有「综合股性分」这类评分聚合词，**禁止一切价位锚点**（止损/止盈/买入观察价/目标价位）与交易指令。
- 原型与分位是**结构分类**，不是评级，也不是买卖或仓位判断。
- 报告结尾固定声明：「本报告的每一项都是对历史交易行为的统计描述，不构成投资建议；原型与分位是结构分类，不是评级，也不是任何买卖或仓位判断。」
- 埋人率、次日溢价等只在有异动事件的样本上计算，事件数少的个股统计噪声大，必须如实标注。

## 八、自迭代

每次运行后把新增数据源、踩坑、口径决策沉淀回本文件、`references/data-pitfalls.md`、`references/data-contract.md` 与 `evals.json`；改了脚本后至少跑一次 `make test` 与 `make audit`。
