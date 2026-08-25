import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "generate_daily_review.py"
FIXTURES = Path(__file__).parent / "fixtures"
MARKET = FIXTURES / "market.json"
UNKNOWN = FIXTURES / "unknown.json"


class DailyMarketReviewTests(unittest.TestCase):
    def run_generator(self, input_path, directory, expected_returncode=0):
        markdown = Path(directory) / "report.md"
        summary = Path(directory) / "summary.json"
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(input_path),
                "--as-of",
                "2026-08-25",
                "--output",
                str(markdown),
                "--summary-out",
                str(summary),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            expected_returncode,
            result.stdout + result.stderr,
        )
        return result, markdown, summary

    def write_json(self, directory, name, value):
        path = Path(directory) / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_generates_derived_breadth_turnover_and_sector_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, markdown_path, summary_path = self.run_generator(MARKET, tmp)
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertAlmostEqual(summary["derived"]["advancer_share_pct"], 58.823529)
        self.assertAlmostEqual(summary["derived"]["advance_decline_ratio"], 1.5)
        self.assertAlmostEqual(summary["derived"]["turnover_vs_previous_pct"], 25.0)
        self.assertEqual(summary["derived"]["leading_sector"], "电子")
        self.assertEqual(summary["derived"]["lagging_sector"], "银行")
        self.assertIn("## 二、市场宽度", markdown)
        self.assertIn("## 四、板块表现", markdown)

    def test_detects_index_breadth_divergence_by_explicit_rule(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        market["sections"]["breadth"]["metrics"]["advancers"]["value"] = 1000
        market["sections"]["breadth"]["metrics"]["decliners"]["value"] = 3000
        market["sections"]["breadth"]["metrics"]["unchanged"]["value"] = 0
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "divergence.json", market)
            _, _, summary_path = self.run_generator(path, tmp)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertIn("index_up_breadth_narrow", [item["code"] for item in summary["signals"]])
        signal = next(item for item in summary["signals"] if item["code"] == "index_up_breadth_narrow")
        self.assertEqual(signal["rule"], "primary_index_change_pct > 0 and advancer_share_pct < 40")

    def test_rejects_future_evidence_and_missing_source(self):
        future = json.loads(MARKET.read_text(encoding="utf-8"))
        future["sections"]["indices"]["items"][0]["change_pct"]["published_at"] = "2026-08-26"
        missing = copy.deepcopy(future)
        missing["sections"]["indices"]["items"][0]["change_pct"]["published_at"] = "2026-08-25"
        missing["sections"]["indices"]["items"][0]["change_pct"]["source"].pop("url")
        with tempfile.TemporaryDirectory() as tmp:
            future_path = self.write_json(tmp, "future.json", future)
            missing_path = self.write_json(tmp, "missing.json", missing)
            future_result, _, _ = self.run_generator(future_path, tmp, expected_returncode=2)
            missing_result, _, _ = self.run_generator(missing_path, tmp, expected_returncode=2)

        self.assertIn("published_at 晚于 as-of", future_result.stderr)
        self.assertIn("source.url", missing_result.stderr)

    def test_all_unknown_preserves_reasons_and_does_not_fill_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, markdown_path, summary_path = self.run_generator(UNKNOWN, tmp)
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(summary["coverage"], {"available": 0, "partial": 0, "unknown": 7})
        self.assertEqual(summary["derived"], {})
        self.assertIn("无可得盘面数据", markdown)
        self.assertIn("宽度源不可用", markdown)

    def test_output_is_deterministic_and_has_no_investment_directives(self):
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            _, first_md, first_summary = self.run_generator(MARKET, first_tmp)
            _, second_md, second_summary = self.run_generator(MARKET, second_tmp)
            first_text = first_md.read_text(encoding="utf-8")
            second_text = second_md.read_text(encoding="utf-8")
            first_json = json.loads(first_summary.read_text(encoding="utf-8"))
            second_json = json.loads(second_summary.read_text(encoding="utf-8"))

        self.assertEqual(first_text, second_text)
        self.assertEqual(first_json, second_json)
        self.assertRegex(first_json["run"]["input_sha256"], r"^[0-9a-f]{64}$")
        for forbidden in ("建议买入", "建议卖出", "目标价", "目标仓位", "确定牛市", "确定熊市"):
            self.assertNotIn(forbidden, first_text)

    def test_rejects_market_date_after_as_of(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        market["market_date"] = "2026-08-26"
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "future-market.json", market)
            result, _, _ = self.run_generator(path, tmp, expected_returncode=2)

        self.assertIn("market_date 不能晚于 as-of", result.stderr)

    def test_available_daily_evidence_must_match_market_date(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        market["sections"]["indices"]["items"][0]["change_pct"]["observed_at"] = "2026-08-24"
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "stale-index.json", market)
            result, _, _ = self.run_generator(path, tmp, expected_returncode=2)

        self.assertIn("observed_at必须等于market_date", result.stderr)

    def test_count_metrics_must_be_integers(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        market["sections"]["breadth"]["metrics"]["advancers"]["value"] = 1000.5
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "fractional-count.json", market)
            result, _, _ = self.run_generator(path, tmp, expected_returncode=2)

        self.assertIn("使用count时必须是整数", result.stderr)


if __name__ == "__main__":
    unittest.main()
