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

# 直接导入入口模块，用于校验默认输出路径这类纯逻辑（不落盘）。
sys.path.insert(0, str(SKILL_DIR / "scripts"))
import research_journal as rj  # noqa: E402


def read_html(path):
    return Path(path).read_text(encoding="utf-8")


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

    # ---------- 落库与不可变性（仍为 JSON 输出） ----------
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
            exported = json.loads(self.run_cli(db, "export").stdout)

        self.assertRegex(first["snapshot_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(first["snapshot_sha256"], exported["records"][0]["snapshot_sha256"])
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

    # ---------- 复核计算（仍为 JSON 输出） ----------
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
            self.run_cli(
                db, "stats", "--as-of", "2026-08-31", "--out", Path(tmp) / "stats.html"
            )
            stats_html = read_html(Path(tmp) / "stats.html")

        self.assertTrue(observed["criterion_passed"])
        self.assertTrue(observed["falsifier_triggered"])
        self.assertFalse(observed["passed"])
        # 单条、概率 0.7、实际未通过 → Brier = (0.7 - 0)^2 = 0.49
        self.assertIn("0.4900", stats_html)

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
            self.run_cli(
                db, "stats", "--as-of", "2026-08-31", "--out", Path(tmp) / "stats.html"
            )
            stats_html = read_html(Path(tmp) / "stats.html")
            exported = json.loads(self.run_cli(db, "export").stdout)

        self.assertEqual([item["research_id"] for item in due], ["r-600001-20260801-30d"])
        # 命中率与均值直接体现在看板卡片 / 明细里
        self.assertIn("100.0%", stats_html)
        self.assertIn("0.0900", stats_html)
        self.assertIn("逐条明细", stats_html)
        self.assertNotIn("r-600002-20260801-30d", stats_html)
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

    # ---------- show：HTML 复盘报告 ----------
    def test_show_writes_html_with_shared_shell_and_frozen_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "journal.sqlite3"
            out = Path(tmp) / "record.html"
            self.run_cli(db, "record", "--input", SNAPSHOT)
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
            result = self.run_cli(
                db, "show", "--id", "r-600001-20260801-30d", "--out", out
            )
            html = read_html(out)

        # 落盘路径可被脚本读到
        self.assertIn(str(out), result.stdout)
        # 共享设计令牌与品牌层（外壳 + 组件）已注入（审计 P2-6 硬约束）
        self.assertIn("--ink:#111417", html)
        self.assertIn("--paper:#ffffff", html)
        self.assertIn("--accent:#1b39d8", html)
        self.assertIn('<style id="ashare-brand">', html)
        self.assertIn("box-shadow:var(--shadow-off) var(--shadow-off) 0 var(--shadow)", html)
        self.assertIn('class="masthead"', html)
        self.assertIn("A-SHARE / RESEARCH JOURNAL REVIEW", html)
        # 冻结原文逐字引用（不设禁词门禁的原因，见 SKILL.md 第五节）
        self.assertIn("订单兑现可能形成预期差", html)
        # 快照 SHA 留痕（合成 fixture 的确定性摘要）
        self.assertIn("90f4fa182619c97b9fa86d3e5f59ccf16684eb767f1d9dde78c801cb0fddc3a9", html)
        # 到期结果与审计卡片、价格路径图
        self.assertIn('<h2 class="card-title">判断审计</h2>', html)
        self.assertIn('id="ch-path"', html)
        # 固定「报告性质」声明（替代禁词硬门禁）
        self.assertIn("不构成投资建议", html)
        self.assertNotIn("{{", html)

    def test_show_before_observe_downgrades_to_not_yet_matured(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "journal.sqlite3"
            out = Path(tmp) / "pre.html"
            self.run_cli(db, "record", "--input", SNAPSHOT)
            self.run_cli(db, "show", "--id", "r-600001-20260801-30d", "--out", out)
            html = read_html(out)

        self.assertIn("尚未到期复核", html)
        # 未写结果前不得生成评分、审计卡或价格路径图
        self.assertNotIn('<h2 class="card-title">判断审计</h2>', html)
        self.assertNotIn('id="ch-path"', html)

    # ---------- stats：HTML 统计看板 ----------
    def test_stats_html_uses_ashare_color_convention(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "journal.sqlite3"
            out = Path(tmp) / "stats.html"
            self.run_cli(db, "record", "--input", SNAPSHOT)
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
            self.run_cli(db, "stats", "--as-of", "2026-08-31", "--out", out)
            html = read_html(out)

        # A 股口径：红涨绿跌（正超额红、负超额绿）
        self.assertIn("gainColor = '#d2231b'", html)
        self.assertIn("lossColor = '#0e7a45'", html)
        self.assertIn('id="ch-hit"', html)
        self.assertIn('id="ch-excess"', html)
        self.assertIn('id="ch-calibration"', html)
        self.assertIn("不构成投资建议", html)
        self.assertNotIn("{{", html)

    def test_stats_empty_state_is_honest(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "journal.sqlite3"
            out = Path(tmp) / "empty.html"
            self.run_cli(db, "record", "--input", SNAPSHOT)
            # 已到期但尚未写入结果 → 不计为失败，也不进入统计
            self.run_cli(db, "stats", "--as-of", "2026-12-31", "--out", out)
            html = read_html(out)

        self.assertIn("当前没有可统计的成熟样本", html)
        self.assertIn("截至该日期没有已成熟且已写入结果的研究记录", html)
        # 空态不画图、不编造数字
        self.assertNotIn('id="ch-hit"', html)
        self.assertNotIn('id="ch-excess"', html)
        self.assertNotIn("{{", html)

    def test_default_out_paths_are_scoped_to_research_dir(self):
        record_path = rj.default_record_out("r-600001-20260801-30d")
        self.assertEqual(record_path.name, "r-600001-20260801-30d.html")
        self.assertEqual(record_path.parent.name, "research-journal")
        self.assertEqual(rj.default_stats_out("2026-08-31", None).name,
                         "research-journal-stats-2026-08-31.html")
        self.assertEqual(rj.default_stats_out("2026-08-31", "600001").name,
                         "research-journal-stats-2026-08-31-600001.html")


if __name__ == "__main__":
    unittest.main()
