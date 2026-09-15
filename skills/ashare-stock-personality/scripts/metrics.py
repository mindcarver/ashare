#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""六维指标计算。

分工：本模块只把「观测事实」变成「原始特征」，再把原始特征在**同一股票池内**
做百分位归一化得到 0-100 的维度分。不做阈值判断（那是 archetypes.py），
不做编排（那是 derive.py）。

口径纪律：
  - 缺证据的维度返回 None，绝不用 0 顶替。综合分只在六个维度都有值时给出。
  - 百分位是「池内相对位置」，不是绝对好坏；样本内相对比较必须随池子一起解释。
  - 换手率口径的容量是透明计算（成交量 ÷ 流通股本，流通股本取快照日），
    与交易所披露的成交额不是同一证据等级，报告里分开标注。
"""

from typing import Any

from schema import (
    DIMENSIONS,
    PersonalityError,
    RISK_DIMENSIONS,
    blend,
    percentile_rank,
)


def years_in_window(window_days: int) -> float:
    if window_days <= 0:
        raise PersonalityError("窗口交易日数必须为正")
    # A 股一年按 243 个交易日折算，与波动率的年化系数保持一致。
    return window_days / 243.0


def raw_features(stock: dict[str, Any], window_days: int, thresholds: dict[str, Any]) -> dict[str, Any]:
    """把单只股票的观测事实压缩成原始特征。"""
    spikes = stock.get("spikes") or []
    lhb = stock.get("lhb") or []
    years = years_in_window(window_days)
    dump_line = float(thresholds["dump_drawdown_pct"])
    # 净额门槛只过滤「资金关注度」维度用的记录；「被选中次数」仍按全部上榜日计，
    # 因为上榜本身就是被资金选中，与净额大小是两件事。
    lhb_min = float(thresholds.get("lhb_net_min_cny") or 0.0)
    notable_lhb = (
        [
            item
            for item in lhb
            if item.get("net_amt_cny") is not None
            and abs(float(item["net_amt_cny"])) >= lhb_min
        ]
        if lhb_min > 0
        else lhb
    )

    next_days = [item["next_day_pct"] for item in spikes if item.get("next_day_pct") is not None]
    drawdowns = [
        item["drawdown_nd_pct"] for item in spikes if item.get("drawdown_nd_pct") is not None
    ]
    lhb_nets = [item["net_amt_cny"] for item in notable_lhb if item.get("net_amt_cny") is not None]
    lhb_days = {item["date"] for item in lhb if item.get("date")}
    spike_days = {item["date"] for item in spikes if item.get("date")}

    features: dict[str, Any] = {
        "spike_count": len(spikes),
        "limit_up_count": sum(1 for item in spikes if item.get("limit_up")),
        "max_streak": max((int(item.get("streak") or 0) for item in spikes), default=0),
        "spikes_per_year": round(len(spikes) / years, 4),
        "limit_up_per_year": round(sum(1 for item in spikes if item.get("limit_up")) / years, 4),
        "selected_days_per_year": round(len(spike_days | lhb_days) / years, 4),
        "lhb_count": len(lhb),
        "lhb_per_year": round(len(notable_lhb) / years, 4),
        # validate.py 已把容量统一归一到 capacity 键（口径记在 capacity_metric），
        # 这里只读归一化后的字段，不再猜测原始列名。
        "capacity": stock.get("capacity"),
        "volatility_ann_pct": stock.get("volatility_ann_pct"),
        "ret_60d_pct": stock.get("ret_60d_pct"),
    }

    features["avg_next_day_pct"] = (
        round(sum(next_days) / len(next_days), 4) if next_days else None
    )
    features["next_day_win_rate_pct"] = (
        round(sum(1 for value in next_days if value > 0) / len(next_days) * 100, 4)
        if next_days
        else None
    )
    features["bury_rate_pct"] = (
        round(sum(1 for value in drawdowns if value <= dump_line) / len(drawdowns) * 100, 4)
        if drawdowns
        else None
    )
    features["severe_drop_rate_pct"] = (
        round(sum(1 for value in next_days if value <= -5.0) / len(next_days) * 100, 4)
        if next_days
        else None
    )
    features["event_sample"] = len(drawdowns)
    features["lhb_net_mean_cny"] = (
        round(sum(lhb_nets) / len(lhb_nets), 2) if lhb_nets else None
    )
    return features


def _column(features: list[dict[str, Any]], key: str) -> list[float]:
    return [row[key] for row in features if row.get(key) is not None]


def _pct(values: list[float], target: Any):
    if target is None:
        return None
    return percentile_rank(values, float(target))


def score_dimensions(features: list[dict[str, Any]]) -> None:
    """就地为每条特征加上 d1-d6、_elasticity、_trend 与综合分。"""
    if not features:
        raise PersonalityError("计算维度分需要非空特征表")

    columns = {
        key: _column(features, key)
        for key in (
            "spikes_per_year",
            "limit_up_per_year",
            "max_streak",
            "avg_next_day_pct",
            "next_day_win_rate_pct",
            "bury_rate_pct",
            "severe_drop_rate_pct",
            "capacity",
            "lhb_per_year",
            "lhb_net_mean_cny",
            "volatility_ann_pct",
            "ret_60d_pct",
        )
    }

    for row in features:
        spikes_pct = _pct(columns["spikes_per_year"], row.get("spikes_per_year"))
        limit_pct = _pct(columns["limit_up_per_year"], row.get("limit_up_per_year"))
        streak_pct = _pct(columns["max_streak"], row.get("max_streak"))
        premium_pct = _pct(columns["avg_next_day_pct"], row.get("avg_next_day_pct"))
        win_pct = _pct(columns["next_day_win_rate_pct"], row.get("next_day_win_rate_pct"))
        bury_pct = _pct(columns["bury_rate_pct"], row.get("bury_rate_pct"))
        severe_pct = _pct(columns["severe_drop_rate_pct"], row.get("severe_drop_rate_pct"))
        capacity_pct = _pct(columns["capacity"], row.get("capacity"))
        lhb_pct = _pct(columns["lhb_per_year"], row.get("lhb_per_year"))
        net_pct = _pct(columns["lhb_net_mean_cny"], row.get("lhb_net_mean_cny"))
        elastic_pct = _pct(columns["volatility_ann_pct"], row.get("volatility_ann_pct"))
        trend_pct = _pct(columns["ret_60d_pct"], row.get("ret_60d_pct"))

        d1 = _combine([(spikes_pct, 0.4), (limit_pct, 0.35), (streak_pct, 0.25)])
        d2 = _combine([(premium_pct, 0.6), (win_pct, 0.4)])
        d3 = _combine([(bury_pct, 0.75), (severe_pct, 0.25)])
        d4 = capacity_pct
        d5 = _combine([(lhb_pct, 0.6), (net_pct, 0.4)])
        d6 = _combine([(elastic_pct, 0.5), (trend_pct, 0.5)])

        row["_elasticity"] = elastic_pct
        row["_trend"] = trend_pct
        row["d1"], row["d2"], row["d3"] = d1, d2, d3
        row["d4"], row["d5"], row["d6"] = d4, d5, d6


def _combine(parts: list[tuple[Any, float]]):
    available = [(score, weight) for score, weight in parts if score is not None]
    if not available:
        return None
    return blend(*available)


def composite_score(row: dict[str, Any], weights: dict[str, float]) -> float | None:
    """综合股性分 = Σ 权重 × 维度分；风险维度先取 (100 - 分)。

    六个维度必须全部可得才给综合分：只要缺一维，综合分返回 None，
    由上层如实标注缺口，而不是把缺失当 0 拉低分数。
    """
    given = {dim: row.get(dim) for dim in DIMENSIONS}
    missing = [dim for dim, value in given.items() if value is None]
    if missing:
        return None
    total_weight = sum(float(weights[dim]) for dim in DIMENSIONS)
    if total_weight <= 0:
        raise PersonalityError("score_weights 合计必须为正")
    value = 0.0
    for dim in DIMENSIONS:
        score = float(given[dim])
        if dim in RISK_DIMENSIONS:
            score = 100.0 - score
        value += score * float(weights[dim]) / total_weight
    return round(min(100.0, max(0.0, value)), 4)
