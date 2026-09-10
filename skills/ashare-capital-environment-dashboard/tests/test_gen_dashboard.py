import json
import re
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "gen_dashboard.py"
# 样例数据已与生产逻辑物理隔离（审计 P2-5）：不再从脚本内联 CELLS 提取。
SAMPLE_CELLS_PATH = SKILL_DIR / "examples" / "sample-cells.json"
EXPECTED_KEYS = {
    f"{market}|{dimension}"
    for market in ("global", "us", "cn", "kr")
    for dimension in ("growth", "inflation", "liquidity", "funding-price", "risk-credit", "market-breadth", "institutional-positioning")
}


def sample_cells():
    payload = json.loads(SAMPLE_CELLS_PATH.read_text(encoding="utf-8"))
    cells = payload.get("cells", payload)
    if not isinstance(cells, dict):
        raise AssertionError("examples/sample-cells.json 未包含 cells 对象")
    return cells


def html_cells(html):
    match = re.search(r"const CELLS = (\{.*?\});", html, re.S)
    if not match:
        raise AssertionError("生成的 HTML 未包含 CELLS JSON")
    return json.loads(match.group(1))


class DashboardGeneratorTests(unittest.TestCase):
    def run_generator(self, *args, expected_returncode=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, expected_returncode, result.stdout + result.stderr)
        return result

    def write_cells(self, directory, cells):
        path = Path(directory) / "cells.json"
        path.write_text(json.dumps({"cells": cells}, ensure_ascii=False), encoding="utf-8")
        return path

    def test_selects_latest_record_published_by_as_of(self):
        cells = sample_cells()
        old = deepcopy(cells["global|growth"])
        old.update({"value": 2.9, "publishedAt": "2026-07-01", "observedAt": "2026-07-01"})
        cells["global|growth"] = [old, cells["global|growth"]]

        with tempfile.TemporaryDirectory() as tmp:
            cells_path = self.write_cells(tmp, cells)
            out = Path(tmp) / "replay.html"
            self.run_generator("--cells", cells_path, "--as-of", "2026-07-05", "--out", out)
            selected = html_cells(out.read_text(encoding="utf-8"))

        self.assertEqual(set(selected), EXPECTED_KEYS)
        self.assertEqual(selected["global|growth"]["value"], 2.9)
        self.assertTrue(any(cell["availability"] == "unknown" for cell in selected.values()))
        for cell in selected.values():
            if cell.get("publishedAt"):
                self.assertLessEqual(date.fromisoformat(cell["publishedAt"]), date(2026, 7, 5))

    def test_all_unknown_hides_matrix_and_market_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            cells_path = self.write_cells(tmp, sample_cells())
            out = Path(tmp) / "empty.html"
            self.run_generator("--cells", cells_path, "--as-of", "2020-01-01", "--out", out)
            html = out.read_text(encoding="utf-8")

        self.assertIn("该日期无可得的资本环境数据。请选择一个有可靠数据的日期。", html)
        self.assertNotIn('<div class="matrix-wrap">', html)
        self.assertNotIn('<section class="market"', html)
        self.assertNotIn('<div id="markets">', html)
        self.assertNotIn("来源：undefined", html)

    def test_contract_rejects_available_cell_without_required_evidence(self):
        cells = sample_cells()
        cells["us|growth"] = deepcopy(cells["us|growth"])
        cells["us|growth"].pop("publishedAt")

        with tempfile.TemporaryDirectory() as tmp:
            cells_path = self.write_cells(tmp, cells)
            result = self.run_generator("--cells", cells_path, "--as-of", "2026-07-31", "--check", expected_returncode=1)

        self.assertIn("缺少证据字段：publishedAt", result.stdout + result.stderr)

    def test_top_summary_is_limited_to_eight_takeaways_and_eight_risk_signals(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "summary.html"
            self.run_generator("--as-of", "2026-07-31", "--out", out)
            html = out.read_text(encoding="utf-8")

        takeaway_start = html.index('<div class="takeaway-box">')
        risk_start = html.index('<div class="risk-box">')
        matrix_start = html.index('<div class="matrix-wrap">')
        self.assertLessEqual(html[takeaway_start:risk_start].count('class="tw-item"'), 8)
        self.assertLessEqual(html[risk_start:matrix_start].count('class="tw-item"'), 8)

    def test_html_uses_shared_editorial_visual_system(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "styled.html"
            self.run_generator("--as-of", "2026-07-31", "--out", out)
            html = out.read_text(encoding="utf-8")

        # 共享设计令牌（浅色瑞士色板）+ 品牌层（外壳 + 组件）已注入
        self.assertIn("--ink:#111417", html)
        self.assertIn("--paper:#ffffff", html)
        self.assertIn("--line:#c9c6c0", html)
        self.assertIn("--accent:#1b39d8", html)
        self.assertIn('"Noto Serif SC","Songti SC",STSong,serif', html)
        self.assertIn('<style id="ashare-brand">', html)
        self.assertIn("box-shadow:var(--shadow-off) var(--shadow-off) 0 var(--shadow)", html)
        self.assertIn('class="masthead"', html)
        self.assertIn("GLOBAL / CAPITAL ENVIRONMENT", html)
        # 旧深色骨架与行情词别名不得回潮
        self.assertNotIn("background:#18221f", html)
        self.assertNotIn("--market-up", html)
        self.assertNotIn("--market-down", html)
        self.assertNotIn("border-radius:9999px", html)
        cells = html_cells(html)
        self.assertEqual(cells["cn|market-breadth"]["colors"][:2], ["#d2231b", "#0e7a45"])

    def test_sample_data_is_isolated_from_production_scripts(self):
        """审计 P2-5：28 格样例数据只允许放在 examples/，不得内联回 scripts/。"""
        payload = json.loads(SAMPLE_CELLS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(payload["cells"]), 28)
        # 取样例里独有、且不会出现在代码/文档里的来源串做探针
        probes = ["cn-nbs（国家统计局, ", "cn-pbc（中国人民银行, "]
        for probe in probes:
            self.assertIn(probe, SAMPLE_CELLS_PATH.read_text(encoding="utf-8"))
        for script in sorted((SKILL_DIR / "scripts").glob("*.py")):
            source = script.read_text(encoding="utf-8")
            for probe in probes:
                self.assertNotIn(probe, source, f"{script.name} 内联了样例数据（应放在 examples/）")
            self.assertLess(len(source.splitlines()), 400, f"{script.name} 仍然过大，应继续拆分模块")


if __name__ == "__main__":
    unittest.main()
