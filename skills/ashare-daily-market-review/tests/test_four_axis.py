import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest

from pathlib import Path

import test_deep_analysis as deep_fixture


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "generate_daily_review.py"
MARKET = Path(__file__).parent / "fixtures" / "market.json"


class FourAxisTests(unittest.TestCase):
    def run_generator(self, market, directory, expected=0):
        input_path = Path(directory) / "market.json"
        report = Path(directory) / "report.md"
        summary = Path(directory) / "summary.json"
        html = Path(directory) / "report.html"
        input_path.write_text(json.dumps(market, ensure_ascii=False, indent=2), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(input_path),
                "--as-of",
                market["as_of"],
                "--output",
                str(report),
                "--summary-out",
                str(summary),
                "--html-out",
                str(html),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result, report, summary, html

    def test_legacy_input_upgrades_to_core_with_separate_coverage(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            _, report_path, summary_path, html_path = self.run_generator(market, tmp)
            report = report_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            html = html_path.read_text(encoding="utf-8")
        self.assertEqual(summary["schema_version"], "1.4")
        self.assertEqual(summary["analysis_mode"], "core")
        self.assertFalse(summary["deep_coverage"]["enabled"])
        self.assertEqual(summary["deep_coverage"]["missing"], 6)
        self.assertIn("深度模式未启用", report)
        self.assertIn("CORE · 深度模式未启用", html)
        self.assertIn('aria-label="纵横深验四轴总览"', html)

    def test_new_schema_requires_mode_and_deep_requires_all_components(self):
        missing_mode = json.loads(MARKET.read_text(encoding="utf-8"))
        missing_mode["schema_version"] = "1.4"
        deep = deep_fixture.DeepAnalysisTests().deep_market()
        deep["deep_analysis"].pop("lhb_structure")
        with tempfile.TemporaryDirectory() as tmp:
            first, *_ = self.run_generator(missing_mode, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            second, *_ = self.run_generator(deep, tmp, expected=2)
        self.assertIn("analysis_mode 必须是core或deep", first.stderr)
        self.assertIn("deep模式缺少深度组件", second.stderr)
        self.assertIn("lhb_structure", second.stderr)

    def test_deep_unknown_is_explicit_and_counted(self):
        market = deep_fixture.DeepAnalysisTests().deep_market()
        market["deep_analysis"]["lhb_structure"] = {
            "availability": "unknown",
            "status_reason": "当日龙虎榜尚未披露",
        }
        with tempfile.TemporaryDirectory() as tmp:
            _, report_path, summary_path, html_path = self.run_generator(market, tmp)
            report = report_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            html = html_path.read_text(encoding="utf-8")
        self.assertEqual(summary["analysis_mode"], "deep")
        self.assertEqual(summary["deep_coverage"]["available"], 5)
        self.assertEqual(summary["deep_coverage"]["unknown"], 1)
        self.assertEqual(summary["deep_coverage"]["missing"], 0)
        self.assertIn("深度覆盖：可得5 / 部分0 / 未知1 / 未声明0", report)
        self.assertIn("当日龙虎榜尚未披露", html)

    def test_four_axis_marks_dual_confirmed_theme_as_regime_conflicted(self):
        market = deep_fixture.DeepAnalysisTests().deep_market()
        with tempfile.TemporaryDirectory() as tmp:
            _, report_path, summary_path, html_path = self.run_generator(market, tmp)
            report = report_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            html = html_path.read_text(encoding="utf-8")
        four_axis = summary["derived"]["four_axis"]
        theme = next(item for item in four_axis["theme_intersections"] if item["id"] == "electronics-chain")
        self.assertEqual(theme["checks"]["horizontal"]["status"], "supported")
        self.assertEqual(theme["checks"]["longitudinal"]["status"], "contradicted")
        self.assertEqual(theme["checks"]["liquidity"]["status"], "contradicted")
        self.assertEqual(theme["checks"]["concentration"]["status"], "contradicted")
        self.assertEqual(theme["result"], "regime_conflicted")
        self.assertNotIn("score", json.dumps(four_axis, ensure_ascii=False).lower())
        self.assertIn("主题跨轴交汇", report)
        self.assertIn("环境冲突", html)
        self.assertIn("纵 × 横 × 深 × 验", html)

    def test_missing_depth_stays_horizontal_only(self):
        market = deep_fixture.DeepAnalysisTests().deep_market()
        market["analysis_mode"] = "core"
        market.pop("deep_analysis")
        with tempfile.TemporaryDirectory() as tmp:
            _, _, summary_path, _ = self.run_generator(market, tmp)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        theme = next(
            item
            for item in summary["derived"]["four_axis"]["theme_intersections"]
            if item["id"] == "electronics-chain"
        )
        self.assertEqual(theme["checks"]["horizontal"]["status"], "supported")
        self.assertEqual(theme["checks"]["liquidity"]["status"], "not_enabled")
        self.assertEqual(theme["checks"]["concentration"]["status"], "not_enabled")
        self.assertEqual(theme["result"], "horizontal_only")

    def test_incomplete_capital_group_does_not_support_depth_axis(self):
        market = deep_fixture.DeepAnalysisTests().deep_market()
        group = market["deep_analysis"]["capital_co_movement"]["groups"][0]
        group["contributions_complete"] = False
        group["contributions"] = group["contributions"][:1]
        with tempfile.TemporaryDirectory() as tmp:
            _, _, summary_path, _ = self.run_generator(market, tmp)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        depth_checks = summary["derived"]["four_axis"]["axes"]["depth"]["checks"]
        capital_check = next(
            item
            for item in depth_checks
            if item["rule"] == "no relevant complete group may be pseudo_sector_status == flagged"
        )
        self.assertEqual(capital_check["status"], "unknown")

    def test_all_six_checks_can_produce_multi_axis_supported(self):
        market = deep_fixture.DeepAnalysisTests().deep_market()
        cycle = market["deep_analysis"]["sentiment_cycle"]
        cycle["points"][-1]["metrics"]["limit_up"]["value"] = 70
        liquidity = market["deep_analysis"]["liquidity_regime"]
        liquidity["thresholds"].update(
            {
                "advancer_share_min_pct": 50,
                "limit_up_min": 0,
                "limit_down_max": 100,
            }
        )
        benchmark = liquidity["benchmarks"][0]
        benchmark["change_pct"]["value"] = 4
        benchmark["volume_ratio_5d"]["value"] = 2
        benchmark["ma20_distance_pct"]["value"] = 1
        benchmark["consecutive_volume_days"]["value"] = 3
        group = market["deep_analysis"]["capital_co_movement"]["groups"][0]
        group["change_pct"]["value"] = 1
        with tempfile.TemporaryDirectory() as tmp:
            _, _, summary_path, _ = self.run_generator(market, tmp)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        theme = next(
            item
            for item in summary["derived"]["four_axis"]["theme_intersections"]
            if item["id"] == "electronics-chain"
        )
        self.assertTrue(all(check["status"] == "supported" for check in theme["checks"].values()))
        self.assertEqual(theme["result"], "multi_axis_supported")

    def test_verification_axis_preserves_scope_and_resolved_counts(self):
        market = deep_fixture.DeepAnalysisTests().deep_market()
        with tempfile.TemporaryDirectory() as tmp:
            _, _, summary_path, _ = self.run_generator(market, tmp)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        axis = summary["derived"]["four_axis"]["axes"]["verification"]
        self.assertEqual(axis["future_count"], 1)
        self.assertEqual(axis["future_scopes"], ["market"])
        self.assertEqual(axis["resolved_counts"], {"passed": 0, "failed": 0, "unknown": 0})

    def test_fetch_context_mode_routing(self):
        tool_path = SKILL_DIR.parents[1] / "tools" / "fetch_daily_market.py"
        spec = importlib.util.spec_from_file_location("fetch_daily_market", tool_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        self.assertEqual(module.analysis_mode_from_context({}), "core")
        self.assertEqual(module.analysis_mode_from_context({"deep_analysis": {"x": 1}}), "deep")
        self.assertEqual(module.analysis_mode_from_context({"analysis_mode": "core", "deep_analysis": {"x": 1}}), "core")
        with self.assertRaises(SystemExit):
            module.analysis_mode_from_context({"analysis_mode": "full"})


if __name__ == "__main__":
    unittest.main()
