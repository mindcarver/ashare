# 输入契约（schema_version = 1.0）

本文件是 `generate_personality.py` 接受的输入结构唯一说明。契约由 `scripts/validate.py` 强制执行：**不合规一律非零退出，不做静默降级**。

## 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `schema_version` | string | ✓ | 必须是 `"1.0"`；本技能不做版本升级 |
| `as_of` | `YYYY-MM-DD` | ✓ | 信息截止日 |
| `window.start` | `YYYY-MM-DD` | ✓ | 窗口起 |
| `window.end` | `YYYY-MM-DD` | ✓ | 窗口止 |
| `window.trading_days` | int ≥ 5 | ✓ | 真实交易日数（用于把事件数折成「每年」） |
| `capacity_metric` | enum | ✓ | `amount_avg_cny` / `float_cap_cny` / `turnover_avg_pct` |
| `thresholds` | object | ✓ | 见下，全部必填 |
| `universe` | object | ✓ | `name`（必填）、`description`、`count`、`selection_rule`、`excluded_count` |
| `stocks` | array | ✓ | 非空，见下 |
| `sources` | array | | `[{name, url}]`，渲染进「来源汇总」 |

硬约束：`window.start ≤ window.end ≤ as_of`；`universe.count` 必须等于 `len(stocks)`。

## thresholds（全部必填，无隐藏默认）

```jsonc
{
  "limit_up_pct": {"main": 9.8, "gem": 19.8, "star": 19.8, "bse": 29.8, "st": 4.8},
  "spike_pct": 7.0,              // 视为「异动」的最小绝对涨跌幅，0.5–30
  "dump_drawdown_pct": -8.0,     // 埋人的回撤阈值，-50 – -1
  "dump_window_days": 5,         // 埋人观察窗口（天），1–20
  "lhb_net_min_cny": 5000000,
  "score_weights": {"d1":.., "d2":.., "d3":.., "d4":.., "d5":.., "d6":..},  // 各自 0–1，合计 > 0
  "archetype": {
    "high": 70, "mid": 55, "low": 40,   // 必须满足 low ≤ mid ≤ high
    "legend_streak": 6,                 // 2–20 的整数；按窗口长度标定，见 methodology.md
    "capacity_high": 70, "elastic_high": 70, "trend_high": 70
  }
}
```

任何缺失键都会被点名拒收（错误信息列出缺失键名）。

`lhb_net_min_cny` 是**唯一会过滤样本**的阈值：它只作用于「资金关注度」维度（`lhb_per_year`、`lhb_net_mean_cny`），不影响「被选中次数/年」（那一项按全部上榜日计）。取 0 表示不过滤；取正值表示只把净额达标的龙虎榜算作资金关注度证据。

## stocks[]

| 字段 | 必填 | 说明 |
|---|---|---|
| `code` | ✓ | 6 位数字，池内不重复 |
| `name` | ✓ | 非空 |
| `board` | ✓ | `main` / `gem` / `star` / `bse` / `st` |
| `sector` | | 东财行业名；缺省记「未知行业」 |
| `bars` | ✓ | 入档日线根数 ≥ 1 |
| `first_bar` / `last_bar` | | 首末交易日 |
| `spikes[]` | ✓（可为空数组） | 异动事件，见下 |
| `lhb[]` | ✓（可为空数组） | 龙虎榜记录，见下 |
| `<capacity_metric>` | ✓ | 必须是顶层声明的那个口径键名 |
| `float_cap_cny` | | 流通市值 |
| `volatility_ann_pct` | | 年化波动率 |
| `ret_60d_pct` / `ret_20d_pct` / `ret_5d_pct` | | 区间涨跌幅 |

### spikes[]

```jsonc
{"date": "2026-08-03", "change_pct": 19.8, "limit_up": true,
 "streak": 4, "next_day_pct": 1.0, "drawdown_nd_pct": -12.0}
```

- `date` 必须落在窗口 `[start, end]` 内，否则拒收。
- `change_pct` ∈ [-35, 45]；`limit_up=true` 时若 `change_pct` 明显低于该板块阈值（差 > 3 个百分点）会拒收，避免口径自相矛盾。
- `streak` ∈ [0, 30]，表示该事件当日的**连板数**；连板链遇到停牌即断（由取数工具保证）。
- `next_day_pct` / `drawdown_nd_pct` 可为 null（缺证据）；有值时 ∈ [-100, 200]。

### lhb[]

```jsonc
{"date": "2026-08-03", "net_amt_cny": 180000000,
 "d1_pct": 10.0, "d2_pct": 12.5, "d5_pct": 8.0, "d10_pct": -4.0}
```

`d1/d2/d5/d10_pct` 是上榜后 1/2/5/10 个交易日的复权涨跌幅，来自东财龙虎榜，只用于统计已发生的历史事件。

## 派生自洽（validate_derived）

- 每维值 ∈ [0, 100]，小数位 ≤ 4。
- 六维齐全才允许有 `composite`；有维度缺失却给出综合分 → 拒收（缺证据不得当 0 用）。
- `archetype` 必须 ∈ 七个原型键之一，且必须有可读的 `archetype_reason`。
- 板块×原型矩阵的单元格只数合计必须等于股票池只数。
- 单元格 `scored_count > 0` 时 `mean_composite` 不得为 None；`scored_count == 0`（无样本，或样本全缺证据）时必须是 None，不允许用 0 占位。

## 一键取数产物的口径

`tools/fetch_personality_archive.py` 输出的 JSON 完全满足本契约。它按证据等级自动挑容量口径（真实成交额 → 流通市值 → 换手率），并把 `capacity_metric` 写成实际使用的那个；`universe.description` 会如实记录北交所排除数与日线不足剔除数。
