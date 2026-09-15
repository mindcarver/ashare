#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从已通过校验的 28 格派生视图：可用性映射、市场聚合、概览与研判清单。

拆分自 gen_dashboard.py（审计 P2-5）。所有函数都接收 cells 参数，
不读模块级全局状态，便于单独测试与复用。
"""
from schema import DIMS, EXPECTED_KEYS, MARKETS

AVAIL_CLASS = {"available": "a", "partial": "p", "unknown": "u", "failed": "u",
               "incomplete_reconstruction": "u", "pending_review": "p"}
AVAIL_LABEL = {"available": "可得", "partial": "部分", "unknown": "未知", "failed": "失败",
               "incomplete_reconstruction": "无法还原", "pending_review": "待复核"}
# 徽章类名走「状态」语义（available/partial/unknown），不引入行情词（up/down）——
# 旧名 --market-up 取绿色表示「可得」，与 A 股红涨绿跌正好相反，是明确的事故源。
AVAIL_BADGE_CLASS = {"available": "badge-available", "partial": "badge-partial",
                     "unknown": "badge-unknown", "failed": "badge-unknown",
                     "incomplete_reconstruction": "badge-unknown",
                     "pending_review": "badge-muted"}


def avail_class(a):
    return AVAIL_CLASS.get(a, "u")


def avail_label(a):
    return AVAIL_LABEL.get(a, "未知")


def avail_badge_class(a):
    return AVAIL_BADGE_CLASS.get(a, "badge-muted")


def mkt_aggregate(cells, market):
    """市场级聚合：全available=available；有值格(available/partial)=partial；含待复核=pending_review；全未知=unknown"""
    avails = [cells[f"{market}|{d}"]["availability"] for d in DIMS]
    if all(a == "available" for a in avails):
        return "available"
    if any(a in ("available", "partial") for a in avails):
        return "partial"
    if any(a == "pending_review" for a in avails):
        return "pending_review"
    return "unknown"


def market_summary(cells):
    """各市场聚合等级，供 overview 与 CLI 打印共用。"""
    return {market: mkt_aggregate(cells, market) for market in MARKETS}


def overview(cells, as_of):
    """返回 (overview 文案, all_unknown)。无任何可得市场时给诚实降级文案。"""
    summary = market_summary(cells)
    mkts_ok = [market for market in MARKETS if summary[market] in ("available", "partial")]
    covered_cells = sum(cfg["availability"] in ("available", "partial") for cfg in cells.values())
    all_unknown = len(mkts_ok) == 0
    if all_unknown:
        return f"截至 {as_of} 的资本环境：无可得数据。", True
    # 「完全覆盖」只应在每个市场全部 7 格都为 available 时出现；
    # 否则即使 28 格都「有数据」（含 partial），也只算部分覆盖——
    # 避免文案说"完全覆盖"而市场徽章却显示"部分"的自相矛盾。
    fully = [m for m in MARKETS if summary[m] == "available"]
    grade = "完全覆盖" if len(fully) == len(MARKETS) else "部分覆盖"
    return (f"截至 {as_of} 的资本环境：{grade}（{len(fully)}/{len(MARKETS)} 市场全部格子可得，"
            f"{len(mkts_ok)}/{len(MARKETS)} 市场有可得数据，{covered_cells}/{len(EXPECTED_KEYS)} 格有数据）。"
            f"以下为各市场维度的可观测状态，区分已观测事实与未知。"), False


def digest(cells):
    """跨格交叉验证：汇总 takeaways（一句话）与 risk（风险信号）。

    返回 (takeaways, risk_high, risk_medium, risk_low)，元素均为 (标签, 文本)。
    """
    takeaways, risk_high, risk_medium, risk_low = [], [], [], []
    for key, cfg in cells.items():
        for tag, txt in (cfg.get("takeaways") or []):
            takeaways.append((tag, txt))
        risk = cfg.get("risk")
        if risk:
            entry = (risk.get("label") or key.split("|")[0], risk["text"])
            if risk.get("level") == "high":
                risk_high.append(entry)
            elif risk.get("level") == "medium":
                risk_medium.append(entry)
            else:
                risk_low.append(entry)
    return takeaways, risk_high, risk_medium, risk_low


def limited(items, limit):
    """保留稳定顺序，避免同一条证据在顶部重复占位。"""
    result = []
    seen = set()
    for item in items:
        if item in seen:
            continue
        result.append(item)
        seen.add(item)
        if len(result) == limit:
            break
    return result
