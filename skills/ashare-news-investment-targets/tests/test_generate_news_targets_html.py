import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "generate_news_targets_html.py"
FIXTURE = Path(__file__).parent / "fixtures" / "news-targets.json"


class NewsTargetsHtmlTests(unittest.TestCase):
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
        path = Path(directory) / "news.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def test_generates_daily_review_style_news_target_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "report.html"
            self.run_generator(FIXTURE, out)
            html = out.read_text(encoding="utf-8")

        self.assertIn("--ink:#13211f", html)
        self.assertIn("background:#18221f", html)
        self.assertIn('font-family:"Noto Serif SC","Songti SC",STSong,serif', html)
        self.assertIn("A-SHARE / NEWS TARGETS", html)
        self.assertIn("box-shadow:5px 5px 0 rgba(12,18,16,.25)", html)
        for heading in ("新闻传导链", "候选标的分层", "评分与待核验", "前3名标的深度补充", "技术面与资金确认", "观察计划", "数据缺口与限制", "信息来源"):
            self.assertIn(heading, html)
        self.assertIn("技术面未验证", html)
        self.assertIn("调整后分", html)
        self.assertIn(".hero-grid{grid-template-columns:repeat(2,minmax(0,1fr))}", html)
        self.assertIn(".chain-grid,.dashboard-grid,.candidate-grid{grid-template-columns:1fr}", html)

    def test_rejects_news_source_after_as_of(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["news"]["published_at"] = "2026-08-30"
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_generator(self.write_input(tmp, data), Path(tmp) / "report.html", expected_returncode=2)

        self.assertIn("新闻发布时间晚于 as_of", result.stderr)

    def test_rejects_score_total_mismatch(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["candidates"][0]["score"]["relevance"] = 30
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_generator(self.write_input(tmp, data), Path(tmp) / "report.html", expected_returncode=2)

        self.assertIn("score.relevance 超出范围", result.stderr)

    def test_rejects_non_http_source_url(self):
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        data["sources"][0]["url"] = "javascript:alert(1)"
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_generator(self.write_input(tmp, data), Path(tmp) / "report.html", expected_returncode=2)

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
