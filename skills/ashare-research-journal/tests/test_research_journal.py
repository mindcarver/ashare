import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "research_journal.py"
FIXTURES = Path(__file__).parent / "fixtures"
SNAPSHOT = FIXTURES / "snapshot.json"
OUTCOME = FIXTURES / "outcome.json"


class ResearchJournalTests(unittest.TestCase):
    def run_cli(self, db, *args, expected_returncode=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--db", str(db), *map(str, args)],
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

    def write_json(self, directory, name, value):
        path = Path(directory) / name
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_record_is_immutable_and_reproducible(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "journal.sqlite3"
            first = json.loads(self.run_cli(db, "record", "--input", SNAPSHOT).stdout)
            duplicate = self.run_cli(
                db,
                "record",
                "--input",
                SNAPSHOT,
                expected_returncode=2,
            )
            shown = json.loads(
                self.run_cli(db, "show", "--id", "r-600001-20260801-30d").stdout
            )

        self.assertRegex(first["snapshot_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["snapshot_sha256"], shown["snapshot_sha256"])
        self.assertIn("research_id 已存在", duplicate.stderr)

    def test_record_rejects_evidence_published_after_as_of(self):
        snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        snapshot["evidence"][0]["published_at"] = "2026-08-02"
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "journal.sqlite3"
            path = self.write_json(tmp, "future.json", snapshot)
            result = self.run_cli(
                db,
                "record",
                "--input",
                path,
                expected_returncode=2,
            )

        self.assertIn("published_at 晚于 as_of", result.stderr)

    def test_observe_computes_outcome_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "journal.sqlite3"
            self.run_cli(db, "record", "--input", SNAPSHOT)
            observed = json.loads(
                self.run_cli(
                    db,
                    "observe",
                    "--id",
                    "r-600001-20260801-30d",
                    "--input",
                    OUTCOME,
                    "--as-of",
                    "2026-08-31",
                ).stdout
            )
            duplicate = self.run_cli(
                db,
                "observe",
                "--id",
                "r-600001-20260801-30d",
                "--input",
                OUTCOME,
                "--as-of",
                "2026-08-31",
                expected_returncode=2,
            )

        self.assertAlmostEqual(observed["stock_return_pct"], 10.0)
        self.assertAlmostEqual(observed["benchmark_return_pct"], 2.5)
        self.assertAlmostEqual(observed["excess_return_pct"], 7.5)
        self.assertAlmostEqual(observed["max_drawdown_pct"], -10.0)
        self.assertAlmostEqual(observed["max_favorable_excursion_pct"], 20.0)
        self.assertAlmostEqual(observed["max_adverse_excursion_pct"], -10.0)
        self.assertRegex(observed["outcome_sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(observed["passed"])
        self.assertIn("结果已存在", duplicate.stderr)

    def test_observe_rejects_review_before_evaluation_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "journal.sqlite3"
            self.run_cli(db, "record", "--input", SNAPSHOT)
            result = self.run_cli(
                db,
                "observe",
                "--id",
                "r-600001-20260801-30d",
                "--input",
                OUTCOME,
                "--as-of",
                "2026-08-30",
                expected_returncode=2,
            )

        self.assertIn("尚未到 evaluation_date", result.stderr)

    def test_defined_falsifier_prevents_thesis_pass(self):
        outcome = json.loads(OUTCOME.read_text(encoding="utf-8"))
        outcome["falsifiers_triggered"] = ["订单延期"]
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "journal.sqlite3"
            path = self.write_json(tmp, "falsified.json", outcome)
            self.run_cli(db, "record", "--input", SNAPSHOT)
            observed = json.loads(
                self.run_cli(
                    db,
                    "observe",
                    "--id",
                    "r-600001-20260801-30d",
                    "--input",
                    path,
                    "--as-of",
                    "2026-08-31",
                ).stdout
            )
            stats = json.loads(
                self.run_cli(db, "stats", "--as-of", "2026-08-31").stdout
            )

        self.assertTrue(observed["criterion_passed"])
        self.assertTrue(observed["falsifier_triggered"])
        self.assertFalse(observed["passed"])
        self.assertAlmostEqual(stats["brier_score"], 0.49)

    def test_due_stats_and_export_only_use_matured_records(self):
        second = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        second["research_id"] = "r-600002-20260801-30d"
        second["code"] = "600002"
        second["name"] = "乙公司"
        second["evaluation_date"] = "2026-09-30"
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "journal.sqlite3"
            second_path = self.write_json(tmp, "second.json", second)
            self.run_cli(db, "record", "--input", SNAPSHOT)
            self.run_cli(db, "record", "--input", second_path)
            due = json.loads(
                self.run_cli(db, "due", "--as-of", "2026-08-31").stdout
            )
            self.run_cli(
                db,
                "observe",
                "--id",
                "r-600001-20260801-30d",
                "--input",
                OUTCOME,
                "--as-of",
                "2026-08-31",
            )
            stats = json.loads(
                self.run_cli(db, "stats", "--as-of", "2026-08-31").stdout
            )
            exported = json.loads(self.run_cli(db, "export").stdout)

        self.assertEqual([item["research_id"] for item in due], ["r-600001-20260801-30d"])
        self.assertEqual(stats["matured_count"], 1)
        self.assertEqual(stats["passed_count"], 1)
        self.assertAlmostEqual(stats["hit_rate_pct"], 100.0)
        self.assertAlmostEqual(stats["brier_score"], 0.09)
        self.assertEqual(len(exported["records"]), 2)
        self.assertEqual(len(exported["outcomes"]), 1)
        self.assertAlmostEqual(
            exported["outcomes"][0]["metrics"]["excess_return_pct"], 7.5
        )
        self.assertTrue(exported["outcomes"][0]["metrics"]["criterion_passed"])
        self.assertFalse(exported["outcomes"][0]["metrics"]["falsifier_triggered"])

    def test_outcome_path_cannot_extend_beyond_evaluation_date(self):
        outcome = copy.deepcopy(json.loads(OUTCOME.read_text(encoding="utf-8")))
        outcome["stock_path"][-1]["observed_at"] = "2026-09-01"
        outcome["stock_path"][-1]["published_at"] = "2026-09-01"
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "journal.sqlite3"
            path = self.write_json(tmp, "future-outcome.json", outcome)
            self.run_cli(db, "record", "--input", SNAPSHOT)
            result = self.run_cli(
                db,
                "observe",
                "--id",
                "r-600001-20260801-30d",
                "--input",
                path,
                "--as-of",
                "2026-09-01",
                expected_returncode=2,
            )

        self.assertIn("价格路径超出 evaluation_date", result.stderr)


if __name__ == "__main__":
    unittest.main()
