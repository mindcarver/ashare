import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "generate_company_research_html.py"
FIXTURE = Path(__file__).parent / "fixtures" / "company-research.json"


class CompanyResearchHtmlTests(unittest.TestCase):
    def run_generator(self, input_path, out, expected_returncode=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--input", str(input_path), "--out", str(out)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, expected_returncode, result.stdout + result.stderr)
        return result

    def write_input(self, directory, value):
        path = Path(directory) / "research.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def test_generates_daily_review_style_html_with_research_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.html"
            self.run_generator(FIXTURE, out)
            html = out.read_text(encoding="utf-8")

        self.assertIn("--ink:#13211f", html)
        self.assertIn("background:#18221f", html)
        self.assertIn('font-family:"Noto Serif SC","Songti SC",STSong,serif', html)
        self.assertIn("A-SHARE / COMPANY RESEARCH", html)
        self.assertIn("box-shadow:5px 5px 0 rgba(12,18,16,.25)", html)
        for heading in ("研究结论", "关键证据台账", "业务与利润引擎", "催化剂日历", "估值与情景", "风险与证伪", "技术面", "信息来源"):
            self.assertIn(heading, html)
        self.assertIn("技术面未验证", html)
        self.assertIn("样例设备2026年半年度报告", html)

    def test_rejects_fact_without_source(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["evidence"][0].pop("source_id")
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_input(tmp, data)
            result = self.run_generator(path, Path(tmp) / "report.html", expected_returncode=2)

        self.assertIn("事实证据缺少 source_id", result.stderr)

    def test_rejects_personalized_investment_directive(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["summary"]["research_label"] = "建议买入"
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_input(tmp, data)
            result = self.run_generator(path, Path(tmp) / "report.html", expected_returncode=2)

        self.assertIn("禁止个性化投资指令", result.stderr)

    def test_rejects_non_http_source_url(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["sources"][0]["url"] = "javascript:alert(1)"
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_input(tmp, data)
            result = self.run_generator(path, Path(tmp) / "report.html", expected_returncode=2)

        self.assertIn("来源 URL 必须是 http 或 https", result.stderr)

    def test_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first = Path(first_tmp) / "first.html"
            second = Path(second_tmp) / "second.html"
            self.run_generator(FIXTURE, first)
            self.run_generator(FIXTURE, second)

            self.assertEqual(first.read_text(encoding="utf-8"), second.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
