import ast
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
EXPECTED_KEYS = {
    f"{market}|{dimension}"
    for market in ("global", "us", "cn", "kr")
    for dimension in ("growth", "inflation", "liquidity", "funding-price", "risk-credit", "market-breadth", "institutional-positioning")
}


def sample_cells():
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "CELLS":
            if isinstance(node.value, ast.Dict):
                return ast.literal_eval(node.value)
    raise AssertionError("未找到样例 CELLS")


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


if __name__ == "__main__":
    unittest.main()
