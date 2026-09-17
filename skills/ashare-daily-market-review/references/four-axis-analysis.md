# 纵 × 横 × 深 × 验四轴复盘

用户要求深度复盘、判断主线是否真实、解释资金去了哪里或比较盘后报告时读取。四轴是Schema 1.4的派生层，不新增原始事实；它只交叉已经通过契约校验的证据。

## 两种交付模式与默认路由

- `analysis_mode=deep`：**默认模式**。只要用户调用本技能复盘某个日期，即使用深度交付；六个`deep_analysis`组件必须全部声明，没有证据的组件使用`availability=unknown`并写原因。
- `analysis_mode=core`：仅当用户明确要求简版、快速版或core时使用。它只承诺基础十章，并明确“深度模式未启用”。

旧Schema 1.0–1.3文件重放时仍升级为`core`以保留历史语义；这不改变新任务默认deep的路由。

## 四轴语义

| 轴 | 数据 | 支持条件 | 冲突条件 |
|---|---|---|---|
| 纵｜时间演化 | 情绪周期窗口、窗口新低、前涨停池晋级健康线 | 窗口覆盖market_date、未触及声明窗口新低且晋级率不低于声明健康线 | 触及新低或低于健康线；窗口过期或健康线未声明保持unknown |
| 横｜当日截面 | 宽度、主线矩阵、主题象限 | 至少一个主题为`dual_confirmed` | 矩阵可得但没有双确认主题 |
| 深｜机制与贡献 | 量价条件、完整资金贡献、伪板块、催化链、龙虎榜 | 声明条件成立、贡献分解不集中、催化和披露证据可得 | 量价条件失败或相关完整资金组被标记`flagged` |
| 验｜事后闭环 | 未来验证点、已到期结果及scope | 至少存在一个`event_date > market_date`的结构化未来点或到期结果 | 无点时保持unknown，不当作失败；过去/同日点不得充当未来证据 |

轴状态只允许`supported/contradicted/unknown/not_enabled`，不转换为数值分数。

## 主题交汇

每个`mainline_matrix.theme`逐项检查：

1. `horizontal`：主题是否`dual_confirmed`。
2. `longitudinal`：市场情绪和延续性是否支持。
3. `liquidity`：全部已声明量价条件是否通过。
4. `concentration`：与主题板块重叠的完整资金组是否存在伪板块标记。
5. `catalyst`：是否有带来源、机制、反证的催化链映射到该主题。
6. `verification`：主题本身或其催化链是否有未来验证条件。

交汇结果：

- `multi_axis_supported`：六项全部supported。
- `regime_conflicted`：横向已确认，但纵向、量价或集中度至少一项contradicted。
- `horizontal_only`：横向已确认，其他轴仍有unknown/not_enabled。
- `not_horizontal_confirmed`：主题不在双确认象限。
- `insufficient`：横向证据本身unknown。

这些结果描述证据组合，不是主线评级、收益预测、仓位或交易信号。

## 覆盖展示

报告必须同时公开：

- 基础覆盖：十个`sections`的available/partial/unknown。
- 深度覆盖：六个组件的available/partial/unknown/missing。

`deep`模式的missing必须为0。`core`模式没有深度组件时，显示“深度模式未启用”，不能只显示基础覆盖满格后称为完整深度复盘。
