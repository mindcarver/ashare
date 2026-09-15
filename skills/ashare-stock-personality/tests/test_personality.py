import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT_DIR = SKILL_DIR / "scripts"
GENERATOR = SCRIPT_DIR / "generate_personality.py"
FIXTURE = Path(__file__).parent / "fixtures" / "personality.json"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class PersonalityCliTests(unittest.TestCase):
    def run_generator(self, input_path, out=None, html_out=None, summary_out=None,
                      check=False, expected_returncode=0):
        args = [sys.executable, str(GENERATOR), "--input", str(input_path)]
        if check:
            args.append("--check")
        if out is not None:
            args += ["--out", str(out)]
        if html_out is not None:
            args += ["--html-out", str(html_out)]
        if summary_out is not None:
            args += ["--summary-out", str(summary_out)]
        result = subprocess.run(
            args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False
        )
        self.assertEqual(
            result.returncode, expected_returncode, result.stdout + result.stderr
        )
        return result

    def write_input(self, directory, value) -> Path:
        path = Path(directory) / "personality.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def test_check_mode_passes_on_fixture(self):
        result = self.run_generator(FIXTURE, check=True)
        self.assertIn("通过", result.stdout)

    def test_generates_html_markdown_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.md"
            html_out = Path(tmp) / "report.html"
            summary_out = Path(tmp) / "summary.json"
            self.run_generator(FIXTURE, out, html_out, summary_out)
            markdown = out.read_text(encoding="utf-8")
            html = html_out.read_text(encoding="utf-8")
            summary = json.loads(summary_out.read_text(encoding="utf-8"))

        # 共享设计令牌与品牌层（外壳 + 组件）必须注入
        self.assertIn("--ink:#111417", html)
        self.assertIn("--accent:#1b39d8", html)
        self.assertIn('"Noto Serif SC","Songti SC",STSong,serif', html)
        self.assertIn('<style id="ashare-brand">', html)
        self.assertIn("box-shadow:var(--shadow-off) var(--shadow-off) 0 var(--shadow)", html)
        self.assertIn("A-SHARE / STOCK PERSONALITY", html)
        self.assertNotIn("background:#18221f", html)
        self.assertIn(".hero-grid{grid-template-columns:repeat(2,minmax(0,1fr))}", html)

        for heading in (
            "个股股性画像",
            "六维框架与本池均值",
            "股性原型分布",
            "板块 × 股性原型矩阵",
            "板块 × 股性 排序",
            "股性地图",
            "个股明细",
            "结构信号与限制",
            "来源汇总",
        ):
            self.assertIn(heading, html)

        # 固定「报告性质」声明必须逐字出现在两份产物里
        self.assertIn("不构成投资建议", html)
        self.assertIn("不构成投资建议", markdown)

        self.assertEqual(summary["schema_version"], "1.0")
        self.assertEqual(summary["overview"]["total"], 6)
        self.assertEqual(len(summary["archetype_table"]), 7)
        self.assertEqual(summary["run"]["capacity_metric"], "turnover_avg_pct")

    def test_wire_legend_is_detected_from_streak(self):
        """连板型由 max_streak 直接触发，不依赖池内百分位，必须稳定命中。"""
        with tempfile.TemporaryDirectory() as tmp:
            summary_out = Path(tmp) / "summary.json"
            self.run_generator(FIXTURE, Path(tmp) / "r.md", summary_out=summary_out)
            summary = json.loads(summary_out.read_text(encoding="utf-8"))
        legend = next(
            row for row in summary["archetype_table"] if row["archetype"] == "wire_legend"
        )
        self.assertGreaterEqual(legend["count"], 1)

    # --- 契约拒绝路径 ---------------------------------------------------------

    def test_rejects_missing_threshold_key(self):
        data = load_fixture()
        del data["thresholds"]["dump_window_days"]
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_generator(
                self.write_input(tmp, data), Path(tmp) / "r.md", expected_returncode=2
            )
        self.assertIn("dump_window_days", result.stderr)

    def test_rejects_contradictory_archetype_cuts(self):
        data = load_fixture()
        data["thresholds"]["archetype"]["low"] = 90
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_generator(
                self.write_input(tmp, data), Path(tmp) / "r.md", expected_returncode=2
            )
        self.assertIn("low", result.stderr)

    def test_rejects_capacity_missing_on_all_stocks(self):
        data = load_fixture()
        for stock in data["stocks"]:
            stock["turnover_avg_pct"] = None
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_generator(
                self.write_input(tmp, data), Path(tmp) / "r.md", expected_returncode=2
            )
        self.assertIn("流动性口径", result.stderr)

    def test_rejects_duplicate_code(self):
        data = load_fixture()
        data["stocks"][1]["code"] = data["stocks"][0]["code"]
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_generator(
                self.write_input(tmp, data), Path(tmp) / "r.md", expected_returncode=2
            )
        self.assertIn("重复", result.stderr)

    def test_rejects_spike_outside_window(self):
        data = load_fixture()
        data["stocks"][0]["spikes"][0]["date"] = "2024-01-04"
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_generator(
                self.write_input(tmp, data), Path(tmp) / "r.md", expected_returncode=2
            )
        self.assertIn("窗口", result.stderr)

    def test_rejects_price_anchor_in_input(self):
        """score_ok tier 仍禁止价位锚点：输入文本命中禁词必须拒收。"""
        data = load_fixture()
        data["universe"]["description"] = "该池用于测试目标价位口径。"
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_generator(
                self.write_input(tmp, data), Path(tmp) / "r.md", expected_returncode=2
            )
        self.assertIn("禁词", result.stderr)

    def test_rejects_universe_count_mismatch(self):
        data = load_fixture()
        data["universe"]["count"] = 99
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_generator(
                self.write_input(tmp, data), Path(tmp) / "r.md", expected_returncode=2
            )
        self.assertIn("universe.count", result.stderr)


class PersonalityDeriveTests(unittest.TestCase):
    """直接调派生层，检查矩阵守恒、维度区间与原型合法性。"""

    def setUp(self):
        import derive  # noqa: WPS433 - 由 sys.path 注入脚本目录
        import validate

        self.derive = derive
        self.validate = validate

    def test_matrix_and_sector_totals_conserve_pool(self):
        sections = self.validate.validate_input(load_fixture())
        derived, signals = self.derive.derive(sections)
        self.validate.validate_derived(derived, sections["thresholds"])

        records = derived["stocks"]
        matrix = derived["archetype_sector_matrix"]
        cell_total = sum(cell["count"] for row in matrix["cells"] for cell in row["cells"])
        self.assertEqual(cell_total, len(records))
        self.assertEqual(sum(item["count"] for item in derived["sector_table"]), len(records))
        quadrant_total = sum(derived["map"]["quadrant_counts"].values())
        self.assertEqual(
            quadrant_total, sum(1 for row in records if row.get("quadrant"))
        )
        self.assertTrue(any(sig["kind"] == "quadrant_structure" for sig in signals))

    def test_dimensions_in_range_and_composite_requires_all_six(self):
        sections = self.validate.validate_input(load_fixture())
        derived, _ = self.derive.derive(sections)
        for row in derived["stocks"]:
            for dim in ("d1", "d2", "d3", "d4", "d5", "d6"):
                value = row.get(dim)
                if value is not None:
                    self.assertGreaterEqual(value, 0.0)
                    self.assertLessEqual(value, 100.0)
            if row["composite"] is not None:
                self.assertTrue(
                    all(row.get(dim) is not None for dim in ("d1", "d2", "d3", "d4", "d5", "d6")),
                    f"{row['code']} 有维度缺失却给了综合分",
                )

    def test_turnover_capacity_metric_is_flagged_in_caveats(self):
        sections = self.validate.validate_input(load_fixture())
        derived, _ = self.derive.derive(sections)
        joined = " ".join(derived["caveats"])
        self.assertIn("换手率", joined)
        self.assertEqual(derived["capacity_metric"], "turnover_avg_pct")

    def test_float_cap_metric_makes_weight_steady_reachable(self):
        """换上流通市值口径后，大市值低波动的样本应被归为权重稳重型。"""
        data = load_fixture()
        data["capacity_metric"] = "float_cap_cny"
        for stock in data["stocks"]:
            stock.pop("turnover_avg_pct", None)
        sections = self.validate.validate_input(data)
        derived, _ = self.derive.derive(sections)
        self.validate.validate_derived(derived, sections["thresholds"])
        by_code = {row["code"]: row for row in derived["stocks"]}
        self.assertEqual(by_code["600519"]["archetype"], "weight_steady")
        self.assertIn("流通市值", " ".join(derived["caveats"]))


class FetchToolSymbolTests(unittest.TestCase):
    """取数工具的代码前缀映射：北交所 920xxx 曾因「首位 9 → sh」被误拼成 sh920xxx。"""

    def setUp(self):
        import importlib.util

        tool = SKILL_DIR.parents[1] / "tools" / "fetch_personality_archive.py"
        spec = importlib.util.spec_from_file_location("fetch_personality_archive", tool)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.module = module

    def test_bse_prefixes_are_recognised(self):
        for code in ("920088", "430047", "830799", "871981", "889999"):
            self.assertTrue(self.module.is_bse(code), f"{code} 应判为北交所")
            self.assertEqual(self.module.board_of(code, "样本"), "bse")
            self.assertTrue(self.module.tencent_symbol(code).startswith("bj"))

    def test_shanghai_shenzhen_symbols(self):
        self.assertEqual(self.module.tencent_symbol("600519"), "sh600519")
        self.assertEqual(self.module.tencent_symbol("688111"), "sh688111")
        self.assertEqual(self.module.tencent_symbol("002790"), "sz002790")
        self.assertEqual(self.module.tencent_symbol("300750"), "sz300750")
        # 900xxx 是沪市 B 股，不能被 920 前缀规则误伤
        self.assertFalse(self.module.is_bse("900901"))
        self.assertEqual(self.module.tencent_symbol("900901"), "sh900901")

    def test_board_classification(self):
        self.assertEqual(self.module.board_of("600519", "贵州茅台"), "main")
        self.assertEqual(self.module.board_of("300750", "宁德时代"), "gem")
        self.assertEqual(self.module.board_of("688111", "金山办公"), "star")
        self.assertEqual(self.module.board_of("000001", "ST某某"), "st")

    def test_default_thresholds_satisfy_the_contract(self):
        """取数工具吐出的阈值必须能让契约校验通过，否则一键取数产物不可用。"""
        import schema

        thresholds = self.module.DEFAULT_THRESHOLDS
        self.assertEqual(set(schema.THRESHOLD_KEYS) - set(thresholds), set())
        cuts = thresholds["archetype"]
        self.assertEqual(set(schema.ARCHETYPE_THRESHOLD_KEYS) - set(cuts), set())
        self.assertEqual(set(schema.BOARD_KEYS) - set(thresholds["limit_up_pct"]), set())
        self.assertEqual(set(schema.DIMENSIONS) - set(thresholds["score_weights"]), set())
        # 连板阈值必须能把「连板妖股型」压成少数派，取 3 会吞掉过半样本。
        self.assertGreaterEqual(cuts["legend_streak"], 5)


if __name__ == "__main__":
    unittest.main()
