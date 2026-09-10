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

        # 共享设计令牌与品牌层（外壳 + 组件）
        self.assertIn("--ink:#111417", html)
        self.assertIn("--accent:#1b39d8", html)
        self.assertIn('"Noto Serif SC","Songti SC",STSong,serif', html)
        self.assertIn("A-SHARE / NEWS TARGETS", html)
        self.assertIn('<style id="ashare-brand">', html)
        self.assertIn("box-shadow:var(--shadow-off) var(--shadow-off) 0 var(--shadow)", html)
        self.assertNotIn("background:#18221f", html)
        for heading in ("新闻传导链", "候选标的分层", "评分与待核验", "前3名标的深度补充", "技术面与资金确认", "观察计划", "数据缺口与限制", "信息来源"):
            self.assertIn(heading, html)
        self.assertIn("技术面未验证", html)
        self.assertIn("调整后分", html)
        self.assertIn(".hero-grid{grid-template-columns:repeat(2,minmax(0,1fr))}", html)
        self.assertIn(".dashboard-grid,.grid,.split,.candidate-grid,.signal-grid,.chain-grid{grid-template-columns:1fr}", html)

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

    def test_rejects_price_anchors(self):
        """P0-1 回归：价位锚点必须被共享禁词门禁拦截（tier=score_ok）。"""
        for term in ("止损价 12.5 元", "止盈价 18 元", "买入观察价 10 元", "目标价位 20 元", "数据为估算"):
            with self.subTest(term=term):
                data = json.loads(FIXTURE.read_text(encoding="utf-8"))
                data["candidates"][0]["logic"] = data["candidates"][0]["logic"] + " " + term
                with tempfile.TemporaryDirectory() as tmp:
                    result = self.run_generator(
                        self.write_input(tmp, data), Path(tmp) / "report.html", expected_returncode=2
                    )
                self.assertIn("禁止个性化投资指令", result.stderr)

    def test_shared_forbidden_layer_tier_semantics(self):
        """共享禁词层必须就位，且 score_ok 与 strict 的差别符合设计。"""
        sys.path.insert(0, str(SKILL_DIR.parent / "_shared"))
        from ashare_shared import forbidden_terms, tier_for_skill

        self.assertEqual(tier_for_skill("ashare-news-investment-targets"), "score_ok")
        # 本技能自有 100 分评分模型，「总分」是合法字段，故 score_ok 不禁止它；
        # 资本环境面板不产生聚合评分，strict 连「总分」都禁。这是两个 tier 的设计差别。
        self.assertNotIn("总分", forbidden_terms("score_ok"))
        self.assertIn("总分", forbidden_terms("strict"))
        # 价位锚点在两个 tier 下都必须被禁
        for tier in ("no_price", "score_ok", "strict"):
            self.assertIn("止损", forbidden_terms(tier))
            self.assertIn("止盈", forbidden_terms(tier))

    def test_output_is_deterministic(self):
        with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
            first = Path(first_tmp) / "first.html"
            second = Path(second_tmp) / "second.html"
            self.run_generator(FIXTURE, first)
            self.run_generator(FIXTURE, second)
            self.assertEqual(first.read_text(encoding="utf-8"), second.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
