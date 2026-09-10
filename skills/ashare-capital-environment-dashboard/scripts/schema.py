#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资本环境仪表盘的契约层：市场/维度常量、标签、可用性枚举与日期解析。

拆分自 gen_dashboard.py（审计 P2-5）。本模块只放常量与纯函数，导入无副作用。
"""
from datetime import date
from pathlib import Path

# ============ 覆盖矩阵 ============
DIMS = ["growth", "inflation", "liquidity", "funding-price", "risk-credit", "market-breadth", "institutional-positioning"]
MARKETS = ["global", "us", "cn", "kr"]
MKT_LABEL = {"global": "全球", "us": "美国", "cn": "中国", "kr": "韩国"}
DIM_LABEL = {"growth": "增长", "inflation": "通胀", "liquidity": "流动性", "funding-price": "资金价格",
             "risk-credit": "风险偏好与信用", "market-breadth": "市场宽度", "institutional-positioning": "机构持仓与拥挤度"}
EXPECTED_KEYS = {f"{market}|{dimension}" for market in MARKETS for dimension in DIMS}
AVAILABILITIES = {"available", "partial", "unknown", "failed", "pending_review", "incomplete_reconstruction"}

# 板块倾向建议层（可选）：倾向只用 关注/中性/回避，映射到固定 CSS class
SECTOR_STANCE_CLS = {"关注": "st-up", "中性": "st-mid", "回避": "st-down"}

# ============ 输入来源 ============
# 演示样例数据与生产逻辑物理隔离：默认输入放在 examples/sample-cells.json。
# 不要把 28 格数据写回脚本（审计 P2-5）；生产请显式传 --cells cells.json。
DEFAULT_CELLS_PATH = Path(__file__).resolve().parents[1] / "examples" / "sample-cells.json"


def parse_date(value, field):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} 必须是 YYYY-MM-DD：{value!r}") from exc
