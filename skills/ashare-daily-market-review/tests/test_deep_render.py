import unittest

from pathlib import Path
import sys


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from deep_analysis import derive_liquidity_regime  # noqa: E402
from deep_render import markdown_capital, markdown_liquidity  # noqa: E402


SOURCE = {"id": "render-fixture", "name": "渲染测试源", "url": "https://example.com/render"}


def evidence(value, unit):
    return {
        "value": value,
        "unit": unit,
        "observed_at": "2026-09-17",
        "published_at": "2026-09-17",
        "fetched_at": "2026-09-17T16:00:00+08:00",
        "source": SOURCE,
    }


def component():
    return {
        "availability": "available",
        "status_reason": "指数量价历史完整",
        "thresholds": {
            "volume_ratio_min": 1.0,
            "consecutive_days_min": 2,
            "ma20_distance_min_pct": 0,
            "daily_change_min_pct": 0,
            "limit_up_min": 45,
        },
        "benchmarks": [
            {
                "id": "000001",
                "name": "上证指数",
                "kind": "index",
                "history_sample_days": 120,
                "change_pct": evidence(-0.41, "percent"),
                "volume_ratio_5d": evidence(1.05, "ratio"),
                "ma20_distance_pct": evidence(-1.19, "percent"),
                "ma60_distance_pct": evidence(-1.27, "percent"),
                "return_percentile_120d": evidence(30.0, "percent"),
                "volume_percentile_120d": evidence(10.83, "percent"),
                "consecutive_volume_days": evidence(0, "count"),
            }
        ],
    }


class LiquidityRenderingTests(unittest.TestCase):
    def setUp(self):
        sections = {
            "breadth": {
                "availability": "available",
                "metrics": {
                    "limit_up": {"value": 47, "unit": "count"},
                    "limit_down": {"value": 1, "unit": "count"},
                },
            }
        }
        derived = {"advancer_share_pct": 46.38, "prev_pool_performance": {"promotion_rate_pct": 10.11}}
        self.markdown = "\n".join(
            markdown_liquidity(derive_liquidity_regime(component(), sections, derived))
        )

    def test_raw_condition_codes_are_not_leaked_into_markdown(self):
        for code in ("volume_ratio_min", "consecutive_days_min", "ma20_distance_min_pct", "limit_up_min"):
            self.assertNotIn(code, self.markdown)

    def test_condition_matrix_uses_chinese_headers_with_thresholds(self):
        self.assertIn("量比(5日) ≥ 1", self.markdown)
        self.assertIn("连续放量天数 ≥ 2", self.markdown)
        self.assertIn("距20日均线 ≥ 0%", self.markdown)
        self.assertIn("| 上证指数 |", self.markdown)

    def test_matrix_cells_carry_observation_and_verdict(self):
        self.assertIn("1.05 ✓", self.markdown)
        self.assertIn("0 ✗", self.markdown)
        self.assertIn("-1.19% ✗", self.markdown)

    def test_market_checks_render_in_chinese(self):
        self.assertIn("涨停家数 ≥ 45", self.markdown)
        self.assertIn("全市场条件", self.markdown)

    def test_per_benchmark_reading_present_and_interpretive(self):
        self.assertIn("上证指数：当日收跌0.41%；量比1.05，量能与5日均量基本持平", self.markdown)
        self.assertIn("位于20日线下方1.19%、60日线下方1.27%", self.markdown)
        self.assertIn("收益处近120日区间下半区（分位30%）", self.markdown)
        self.assertIn("逐基准解读", self.markdown)
        self.assertIn("不预测方向", self.markdown)


def derived_capital(complete: bool) -> dict:
    concentration = (
        {
            "top1_positive_share_pct": 86.1,
            "absolute_hhi": 0.42,
            "opposite_direction_count": 15,
            "pseudo_sector_status": "clear",
        }
        if complete
        else {
            "top1_positive_share_pct": None,
            "absolute_hhi": None,
            "opposite_direction_count": None,
            "pseudo_sector_status": "unknown",
        }
    )
    return {
        "availability": "available",
        "status_reason": "测试",
        "claim_type": "co_movement_candidate",
        "methodology": "测试口径",
        "thresholds": {"pseudo_sector_top1_share_pct": 50.0},
        "concentration_scope": "complete",
        "note": "共现不等于因果迁移",
        "board_overlap_rate_pct": 0.0,
        "security_overlap_rate_pct": 0.0,
        "groups": [
            {
                "id": "g1",
                "name": "元件·PCB链",
                "role": "outflow",
                "board_ids": ["BK0459"],
                "total_fund_flow_cny": -80.96e8,
                "change_pct": -2.25,
                "contributions_complete": complete,
                "concentration_scope": "complete",
                "sample_coverage_pct": None,
                "contributions": [
                    {"code": "002384", "name": "东山精密", "fund_flow_cny": 5.33e8},
                    {"code": "600183", "name": "生益科技", "fund_flow_cny": -16.81e8},
                ],
                **concentration,
            }
        ],
        "overlaps": [],
        "relations": [],
    }


class CapitalRenderingTests(unittest.TestCase):
    def test_incomplete_contributions_hide_unknown_columns(self):
        markdown = "\n".join(markdown_capital(derived_capital(complete=False)))
        self.assertNotIn("Top1正流入占比", markdown)
        self.assertNotIn("| 伪板块 |", markdown)
        self.assertNotIn("| unknown | unknown", markdown)
        self.assertIn("贡献分解不完整", markdown)
        self.assertIn("已覆盖2只", markdown)
        self.assertIn("| 元件·PCB链 | 流出 | -2.25% | -80.96亿元 |", markdown)

    def test_complete_contributions_show_concentration_columns(self):
        markdown = "\n".join(markdown_capital(derived_capital(complete=True)))
        self.assertIn("Top1正流入占比", markdown)
        self.assertIn("| 伪板块 |", markdown)
        self.assertIn("| 元件·PCB链 | 流出 | -2.25% | -80.96亿元 | +86.10% |", markdown)
        self.assertNotIn("贡献分解不完整", markdown)


if __name__ == "__main__":
    unittest.main()
