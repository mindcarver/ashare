import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "screen_stocks.py"
FIXTURE = Path(__file__).parent / "fixtures" / "stocks.json"


class StockScreeningTests(unittest.TestCase):
    def run_screener(self, input_path=FIXTURE, *args, expected_returncode=0):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(input_path),
                "--as-of",
                "2026-08-25",
                *args,
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
        return result

    def parse_result(self, *args, input_path=FIXTURE):
        result = self.run_screener(input_path, *args)
        return json.loads(result.stdout)

    def write_fixture(self, directory, data):
        path = Path(directory) / "stocks.json"
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    def test_executes_all_criteria_and_reports_missing_metrics(self):
        output = self.parse_result(
            "--criterion",
            "pe_ttm:lt:15",
            "--criterion",
            "roe_ttm:gte:15",
            "--sort",
            "roe_ttm:desc",
        )

        self.assertEqual(
            [stock["code"] for stock in output["selected"]], ["600005", "600001"]
        )
        excluded = {stock["code"]: stock["reasons"] for stock in output["excluded"]}
        self.assertTrue(
            any(
                reason["reason"] == "missing_metric"
                and reason["metric"] == "roe_ttm"
                for reason in excluded["600002"]
            )
        )
        self.assertIn(
            {"metric": "roe_ttm", "reason": "missing_metric", "count": 1},
            output["missing_summary"],
        )
        self.assertEqual(output["counts"], {"input": 5, "selected": 2, "excluded": 3})

    def test_rejects_evidence_published_after_as_of(self):
        output = self.parse_result("--criterion", "pe_ttm:lt:15")
        gamma = next(stock for stock in output["excluded"] if stock["code"] == "600003")

        self.assertTrue(
            any(reason["reason"] == "published_after_as_of" for reason in gamma["reasons"])
        )
        self.assertNotIn("600003", [stock["code"] for stock in output["selected"]])

    def test_invalid_source_is_explicit_and_cannot_pass(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        fixture["stocks"][1]["metrics"]["roe_ttm"]["source"].pop("url")

        with tempfile.TemporaryDirectory() as tmp:
            input_path = self.write_fixture(tmp, fixture)
            output = self.parse_result(
                "--criterion",
                "roe_ttm:gte:15",
                input_path=input_path,
            )

        zeta = next(stock for stock in output["excluded"] if stock["code"] == "600005")
        self.assertTrue(
            any(reason["reason"] == "invalid_evidence" for reason in zeta["reasons"])
        )

    def test_wrong_canonical_unit_is_explicit_and_cannot_pass(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        fixture["stocks"][0]["metrics"]["roe_ttm"]["unit"] = "ratio"

        with tempfile.TemporaryDirectory() as tmp:
            input_path = self.write_fixture(tmp, fixture)
            output = self.parse_result(
                "--criterion",
                "roe_ttm:gte:15",
                input_path=input_path,
            )

        alpha = next(stock for stock in output["excluded"] if stock["code"] == "600001")
        self.assertTrue(
            any(
                reason["reason"] == "invalid_evidence"
                and "要求 percent" in reason["detail"]
                for reason in alpha["reasons"]
            )
        )

    def test_rejects_universe_published_after_as_of(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        fixture["universe"]["published_at"] = "2026-08-26"

        with tempfile.TemporaryDirectory() as tmp:
            input_path = self.write_fixture(tmp, fixture)
            result = self.run_screener(
                input_path,
                "--criterion",
                "pe_ttm:lt:15",
                expected_returncode=2,
            )

        self.assertIn("universe.published_at 不能晚于 as-of", result.stderr)

    def test_output_is_deterministic_and_has_no_arbitrary_score(self):
        args = (
            "--criterion",
            "pe_ttm:lt:15",
            "--criterion",
            "roe_ttm:gte:15",
            "--sort",
            "roe_ttm:desc",
        )
        first = self.parse_result(*args)
        second = self.parse_result(*args)

        self.assertEqual(first, second)
        self.assertRegex(first["run"]["input_sha256"], r"^[0-9a-f]{64}$")
        for stock in first["selected"]:
            self.assertNotIn("score", stock)
            self.assertNotIn("评分", stock)

    def test_warns_when_industry_sensitive_threshold_spans_industries(self):
        output = self.parse_result("--criterion", "debt_ratio:lte:60")

        self.assertTrue(
            any(
                warning["code"] == "industry_sensitive_threshold"
                and warning["metric"] == "debt_ratio"
                for warning in output["warnings"]
            )
        )

    def test_writes_limited_result_to_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "result.json"
            result = self.run_screener(
                FIXTURE,
                "--criterion",
                "pe_ttm:lt:15",
                "--criterion",
                "roe_ttm:gte:15",
                "--sort",
                "roe_ttm:desc",
                "--limit",
                "1",
                "--output",
                str(output_path),
            )
            output = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result.stdout, "")
        self.assertEqual([stock["code"] for stock in output["selected"]], ["600005"])
        self.assertIn(
            {"metric": "roe_ttm", "reason": "outside_limit", "count": 1},
            output["exclusion_summary"],
        )

    def test_rejects_invalid_as_of(self):
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(FIXTURE),
                "--as-of",
                "2026/08/25",
                "--criterion",
                "pe_ttm:lt:15",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("as-of 必须是 YYYY-MM-DD", result.stderr)


if __name__ == "__main__":
    unittest.main()
