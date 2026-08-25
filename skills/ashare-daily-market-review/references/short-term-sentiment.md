# A股短线情绪观察规则

本参考定义的是可复现的盘面分类，不是交易或仓位模型。只有`breadth`和`short_term_sentiment`都为`available`时才分类；否则输出`unknown`和缺失原因。

## 指标口径

- `limit_up`、`limit_down`来自`breadth`，必须与短线情绪章节使用同一股票池。
- `open_board_rate_pct = open_board_failed / limit_attempts × 100`。
- `highest_streak`是该股票池当日可验证的最高连板高度。
- 计数口径、供应商、观察日或股票池不一致时，不得计算状态。

## 初始状态规则

规则以当前市场的可见特征为目的，尚未经过本技能自身的历史样本校准。JSON必须保存规则字符串和触发证据。

1. `ice`：`limit_up < 20`、`limit_down > 10`且`highest_streak < 3`。
2. `euphoria`：`limit_up > 80`、`open_board_rate_pct < 15`且`highest_streak > 5`。
3. `divergence`：不属于`ice`或`euphoria`，且`open_board_rate_pct > 25`。
4. `repair`：不属于上述状态，且前一可比交易日完整可得；当前涨停数上升、跌停数下降、炸板率下降，并且最高连板高度不低于前值。
5. `neutral`：当前数据完整但未触发任一预定义状态。

优先级按上述顺序执行。`repair`缺少前一交易日指标时不能推断；若当前数据完整但无前值且未命中前三类，输出`neutral`，并标注“未评估修复”。

## 限制

- 阈值不是收益预测，也不能直接推出加仓、减仓、空仓或个股交易结论。
- 指标依赖数据供应商对炸板和连板的定义；报告必须展示来源和股票池范围。
- 若要评估这些规则的历史表现，应先通过`ashare-research-journal`冻结规则版本、样本范围和评价窗口。
