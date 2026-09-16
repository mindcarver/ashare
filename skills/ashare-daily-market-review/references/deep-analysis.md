# Schema 1.3 深度分析层

当用户要求全景复盘、资金迁移、量能启动、产业催化、龙虎榜或比普通日报更深的分析时读取。`deep_analysis`位于输入顶层，不加入十个基础章节的覆盖计数。六个组件都可选；缺省不输出，`unknown`不得携带分析数据。

## 共同原则

1. 事实、规则派生、机制假设、反方证据分层输出。
2. 东财“主力资金”等字段统一标`provider_model`，不写成账户级真实资金。
3. “资金迁移”只能称同日流出/流入共现候选；没有账户追踪或干预证据，不能宣称因果。
4. 所有阈值由输入声明。生成器只逐条判断，不输出隐藏总分。
5. 个股表用于市场结构归因，不构成推荐。

## 顶层形状

```json
{
  "deep_analysis": {
    "security_details": {},
    "liquidity_regime": {},
    "sentiment_cycle": {},
    "capital_co_movement": {},
    "catalyst_chains": {},
    "lhb_structure": {}
  }
}
```

每个组件使用`availability/status_reason`。只有组件存在时才进入摘要、Markdown与HTML。

## 个股证据纵深

`security_details.items[]`用于统一高标、板块重点股和主题中军的多周期证据。

```json
{
  "code": "603186",
  "name": "华正新材",
  "roles": ["high_board", "sector_leader"],
  "streak": 2,
  "change_pct": {"...": "percent证据"},
  "fund_flow_windows": [
    {
      "window": {"trading_days": 3, "end_at": "2026-09-15"},
      "metric": {"...": "CNY证据"},
      "method_category": "provider_model"
    }
  ],
  "seal_structure": {
    "first_sealed_at": {"value": "2026-09-15T09:31:07+08:00", "...": "来源元数据"},
    "last_sealed_at": {"value": "2026-09-15T09:41:39+08:00", "...": "来源元数据"},
    "sealed_order_amount": {"...": "CNY证据"},
    "break_count": {"...": "count证据"}
  }
}
```

- `roles`只能是`high_board/sector_leader/theme_leader`。
- 资金窗口只允许1/3/5/10日且不得重复。东财实测：`f62/f267/f164/f174`分别为1/3/5/10日。
- 首封、末封必须落在`market_date`且首封不晚于末封。
- 缺封板证据的非涨停股保留unknown，不用0补。

## 量能、均线与历史分位

`liquidity_regime.benchmarks[]`支持指数和ETF。available时每个基准要求：

- `change_pct`
- `volume_ratio_5d`
- `ma20_distance_pct/ma60_distance_pct`
- `return_percentile_120d/volume_percentile_120d`
- `consecutive_volume_days`
- `history_sample_days >= 120`

`thresholds`可声明：`volume_ratio_min/consecutive_days_min/ma20_distance_min_pct/daily_change_min_pct/advancer_share_min_pct/limit_up_min/limit_down_max/promotion_rate_min_pct`。

生成器输出每个基准和市场条件的`passed/failed/unknown`，以及`all_declared_conditions_met/conditions_not_met/unknown`，不聚合成情绪分或交易信号。

## 情绪周期

`sentiment_cycle.points[]`至少三个交易日、按日期升序，使用同口径的`limit_up/limit_down/seal_rate_pct/promotion_rate_pct`。每点必须声明公开五态`state`与`state_rule`；禁止`score/sentiment_score/composite_score`。

派生输出：状态切换、涨跌停较前值、窗口涨停新低。它描述历史状态，不预测下一交易日。

## 资金共现、集中度与伪板块

`capital_co_movement.claim_type`固定为`co_movement_candidate`。每个group声明：

```json
{
  "id": "communication-cable",
  "name": "通信线缆",
  "role": "inflow",
  "board_ids": ["BK1592"],
  "total_fund_flow": {"...": "CNY证据"},
  "change_pct": {"...": "percent证据"},
  "contributions_complete": true,
  "contributions": [
    {"code": "002491", "name": "通鼎互联", "fund_flow": {"...": "CNY证据"}}
  ]
}
```

- `inflow`总额必须为正，`outflow`必须为负。
- 完整贡献分解至少两只，逐只之和必须等于group总额。
- 派生Top1正流入占比、绝对流量HHI、反向个股数、板块引用重叠率和成分股跨组重叠率。
- `contributions_complete=false`时Top1、HHI、反向个股数和依赖它们的自动验证全部保持unknown；不得用样本子集冒充整个板块。
- `pseudo_sector_top1_share_pct`由输入声明。板块上涨不强、净流入为正且Top1占比越线时标`flagged`；贡献不完整时只能unknown。
- `relations[].from_group_id`必须指向outflow，`to_group_id`必须指向inflow；每条关系必须有`hypothesis`和非空`counter_evidence`。

## 产业催化证据链

每条催化必须包含：事件元数据、`fact`、`mechanism_hypothesis`、`causal_status`、`affected_theme_ids`、`counter_evidence`和`verification_point_ids`。

- `causal_status`只能是`hypothesis/correlation_only`，不能把新闻与股价共现写成已证实因果。
- 主题必须存在于`mainline_matrix`，验证点必须存在于当前输入。
- 至少一条反方证据和一条未来验证；政策发布不等于订单、订单不等于利润。

## 龙虎榜结构

available要求买入、卖出、净额、买卖席位数、买一/卖一占比齐全，且`net = buy - sell`。当日榜单未披露时使用partial，可只声明已知净额与席位类型，其余保持unknown。

禁止`intent/prediction/action`字段，不输出“派发”“接力”“明日砸盘”等主观意图判断。

## 验证点语义绑定

Schema 1.3验证点必须新增：

```json
"subject": {"scope": "stock", "id": "603186", "label": "华正新材"}
```

允许scope及典型metric：

- `market`：成交额、宽度、炸板率、涨停净差、晋级率；subject固定`all-a/A股全市场`。
- `stock`：`streak/change_pct/fund_flow_1d_cny/sealed_order_amount_cny/break_count`。
- `sector`：`change_pct/fund_flow_cny/top1_positive_share_pct/first_board_count`。
- `theme`：`limit_up_count/board_fund_flow_cny/top1_positive_share_pct`。
- `benchmark`：`change_pct/volume_ratio_5d/ma20_distance_pct/ma60_distance_pct/return_percentile_120d/volume_percentile_120d`。

scope决定metric与unit，subject id/label必须与当前输入实体完全一致；标题也必须包含非市场subject名称/ID及对应metric语义词，并且不能引用另一个已声明实体。实体表覆盖深度个股、龙虎榜、资金贡献股，以及基础指数、高标、板块重点股、行业/概念和主题，不能通过省略`security_details`绕过。同名别名（如`sh000688/000688`）视为同一现实实体；当前subject全名包含的跨分类短名不触发误杀，但标题出现另一个更长实体全名仍拒绝。联合多个板块的贡献分解不下放为任一单板块的验证观察值。旧1.2验证点只有在标题明确匹配其全市场metric时才迁为`market`；否则降为定性观察，防止“某个股能否连板”被全市场涨停净差错误结算。
