import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "generate_daily_review.py"
FIXTURES = Path(__file__).parent / "fixtures"
MARKET = FIXTURES / "market.json"
UNKNOWN = FIXTURES / "unknown.json"


class DailyMarketReviewTests(unittest.TestCase):
    def run_generator(
        self,
        input_path,
        directory,
        expected_returncode=0,
        html_out=None,
        history_dir=None,
        as_of="2026-08-25",
    ):
        markdown = Path(directory) / "report.md"
        summary = Path(directory) / "summary.json"
        command = [
                sys.executable,
                str(SCRIPT),
                "--input",
                str(input_path),
                "--as-of",
                as_of,
                "--output",
                str(markdown),
                "--summary-out",
                str(summary),
            ]
        if html_out is not None:
            command.extend(["--html-out", str(html_out)])
        if history_dir is not None:
            command.extend(["--history-dir", str(history_dir)])
        result = subprocess.run(
            command,
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

    def write_history_entry(self, history_dir, market, input_sha):
        directory = Path(history_dir) / market["market_date"]
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"r{market['snapshot']['revision']:03d}-{input_sha[:12]}.json"
        content_sha = hashlib.sha256(
            json.dumps(
                market,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        path.write_text(
            json.dumps(
                {
                    "input_sha256": input_sha,
                    "snapshot_content_sha256": content_sha,
                    "snapshot": market,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return path

    def retime_snapshot(self, value, market_date):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"observed_at", "published_at"}:
                    value[key] = market_date
                elif key == "fetched_at":
                    value[key] = f"{market_date}T16:00:00+08:00"
                elif key == "end_at":
                    value[key] = market_date
                else:
                    self.retime_snapshot(child, market_date)
        elif isinstance(value, list):
            for child in value:
                self.retime_snapshot(child, market_date)

    @staticmethod
    def evidence(value, observed_at="2026-08-25"):
        return {
            "value": value,
            "unit": "count",
            "observed_at": observed_at,
            "published_at": "2026-08-25",
            "fetched_at": "2026-08-25T16:00:00+08:00",
            "source": {
                "id": "fixture-sentiment",
                "name": "测试情绪源",
                "url": "https://example.com/sentiment",
            },
        }

    def with_sentiment(self, market, current, previous=None):
        universe = {
            "id": "all-a-non-st",
            "label": "全A非ST普通股",
            "population_rule": "沪深京A股，排除ST、退市整理与停牌",
            "includes_st": False,
            "includes_bse": True,
            "exclusions": ["ST", "退市整理", "停牌"],
        }
        market["sections"]["breadth"]["universe"] = copy.deepcopy(universe)
        market["sections"]["short_term_sentiment"] = {
            "availability": "available",
            "status_reason": "同一股票池的短线情绪数据完整",
            "universe": universe,
            "methodology": "供应商按盘中封板尝试和炸板事件计数",
            "metrics": {
                name: self.evidence(value) for name, value in current.items()
            },
        }
        if previous is not None:
            market["sections"]["short_term_sentiment"]["previous_metrics"] = {
                name: self.evidence(value, "2026-08-24")
                for name, value in previous.items()
            }
        return market

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
        self.assertIn("## 五、板块表现", markdown)

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

        self.assertIn("published_at 晚于snapshot.cutoff_at", future_result.stderr)
        self.assertIn("source.url", missing_result.stderr)

    def test_all_unknown_preserves_reasons_and_does_not_fill_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, markdown_path, summary_path = self.run_generator(UNKNOWN, tmp)
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(summary["coverage"], {"available": 0, "partial": 0, "unknown": 8})
        self.assertEqual(
            summary["derived"],
            {"short_term_sentiment": {"state": "unknown", "reason": "输入未提供该章节"}},
        )
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
        for forbidden in (
            "建议买入",
            "建议卖出",
            "目标价",
            "目标仓位",
            "建议轻仓",
            "建议半仓",
            "建议重仓",
            "建议空仓",
            "建议加仓",
            "建议减仓",
            "确定牛市",
            "确定熊市",
        ):
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

    def test_classifies_euphoria_with_complete_evidence(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        market["sections"]["breadth"]["metrics"]["limit_up"]["value"] = 81
        market["sections"]["breadth"]["metrics"]["limit_down"]["value"] = 1
        self.with_sentiment(
            market,
            {"open_board_failed": 10, "limit_attempts": 100, "highest_streak": 6},
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "euphoria.json", market)
            _, markdown_path, summary_path = self.run_generator(path, tmp)
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        sentiment = summary["derived"]["short_term_sentiment"]
        self.assertEqual(sentiment["state"], "euphoria")
        self.assertEqual(sentiment["open_board_rate_pct"], 10.0)
        self.assertIn("状态：亢奋", markdown)
        self.assertNotIn("建议重仓", markdown)

    def test_classifies_repair_only_with_complete_previous_metrics(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        market["sections"]["breadth"]["metrics"]["limit_up"]["value"] = 40
        market["sections"]["breadth"]["metrics"]["limit_down"]["value"] = 5
        self.with_sentiment(
            market,
            {"open_board_failed": 10, "limit_attempts": 100, "highest_streak": 4},
            {
                "limit_up": 30,
                "limit_down": 8,
                "open_board_failed": 20,
                "limit_attempts": 100,
                "highest_streak": 3,
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "repair.json", market)
            _, _, summary_path = self.run_generator(path, tmp)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        sentiment = summary["derived"]["short_term_sentiment"]
        self.assertEqual(sentiment["state"], "repair")
        self.assertTrue(sentiment["repair_evaluated"])

    def test_rejects_sentiment_with_mismatched_universe_or_invalid_denominator(self):
        mismatched = json.loads(MARKET.read_text(encoding="utf-8"))
        self.with_sentiment(
            mismatched,
            {"open_board_failed": 10, "limit_attempts": 100, "highest_streak": 4},
        )
        mismatched["sections"]["short_term_sentiment"]["universe"] = copy.deepcopy(
            mismatched["sections"]["breadth"]["universe"]
        )
        mismatched["sections"]["short_term_sentiment"]["universe"]["id"] = "csi-300"
        invalid = json.loads(MARKET.read_text(encoding="utf-8"))
        self.with_sentiment(
            invalid,
            {"open_board_failed": 101, "limit_attempts": 100, "highest_streak": 4},
        )
        with tempfile.TemporaryDirectory() as tmp:
            mismatched_path = self.write_json(tmp, "mismatched.json", mismatched)
            invalid_path = self.write_json(tmp, "invalid.json", invalid)
            mismatched_result, _, _ = self.run_generator(
                mismatched_path, tmp, expected_returncode=2
            )
            invalid_result, _, _ = self.run_generator(
                invalid_path, tmp, expected_returncode=2
            )

        self.assertIn("universe 必须与breadth.universe一致", mismatched_result.stderr)
        self.assertIn("open_board_failed 不能大于limit_attempts", invalid_result.stderr)

    def test_rejects_invalid_snapshot_cutoff_window_and_fund_tier(self):
        cutoff = json.loads(MARKET.read_text(encoding="utf-8"))
        cutoff["snapshot"]["cutoff_at"] = "2026-08-25T15:00:00+08:00"
        window = json.loads(MARKET.read_text(encoding="utf-8"))
        window["sections"]["turnover"]["metrics"]["avg_5d_amount"]["window"][
            "trading_days"
        ] = 20
        funds = json.loads(MARKET.read_text(encoding="utf-8"))
        funds["sections"]["funds"]["availability"] = "available"
        funds["sections"]["funds"]["items"][0]["method_category"] = "provider_model"
        with tempfile.TemporaryDirectory() as tmp:
            cutoff_path = self.write_json(tmp, "cutoff.json", cutoff)
            window_path = self.write_json(tmp, "window.json", window)
            funds_path = self.write_json(tmp, "funds.json", funds)
            cutoff_result, _, _ = self.run_generator(
                cutoff_path, tmp, expected_returncode=2
            )
            window_result, _, _ = self.run_generator(
                window_path, tmp, expected_returncode=2
            )
            funds_result, _, _ = self.run_generator(
                funds_path, tmp, expected_returncode=2
            )

        self.assertIn("fetched_at 晚于snapshot.cutoff_at", cutoff_result.stderr)
        self.assertIn("avg_5d_amount.window.trading_days 必须是5", window_result.stderr)
        self.assertIn("funds仅含供应商模型或活跃度代理", funds_result.stderr)

    def test_derived_verification_source_does_not_accept_fake_url(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        market["verification_points"][0]["source"]["url"] = "https://example.com/fake"
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "fake-derived-source.json", market)
            result, _, _ = self.run_generator(path, tmp, expected_returncode=2)

        self.assertIn("kind=derived 时不能伪造url", result.stderr)

    def test_history_is_append_only_idempotent_and_requires_revision_chain(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            history_dir = Path(tmp) / "history"
            path = self.write_json(tmp, "market.json", market)
            first, _, first_summary_path = self.run_generator(
                path, tmp, history_dir=history_dir
            )
            first_summary = json.loads(first_summary_path.read_text(encoding="utf-8"))
            second, _, second_summary_path = self.run_generator(
                path, tmp, history_dir=history_dir
            )
            second_summary = json.loads(second_summary_path.read_text(encoding="utf-8"))
            first_sha = hashlib.sha256(path.read_bytes()).hexdigest()

            revised = copy.deepcopy(market)
            revised["snapshot"]["revision"] = 2
            revised["snapshot"]["supersedes_sha256"] = first_sha
            revised["snapshot"]["raw_evidence_sha256"] = "c" * 64
            revised["sections"]["breadth"]["metrics"]["advancers"]["value"] += 1
            revised_path = self.write_json(tmp, "market-r2.json", revised)
            third, _, third_summary_path = self.run_generator(
                revised_path, tmp, history_dir=history_dir
            )
            third_summary = json.loads(third_summary_path.read_text(encoding="utf-8"))

        self.assertTrue(first_summary["run"]["history_appended"])
        self.assertFalse(second_summary["run"]["history_appended"])
        self.assertTrue(third_summary["run"]["history_appended"])
        self.assertIn('"history_appended": true', first.stdout)
        self.assertIn('"history_appended": false', second.stdout)
        self.assertIn('"history_appended": true', third.stdout)

    def test_history_rejects_broken_revision_and_tampered_snapshot(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            history_dir = Path(tmp) / "history"
            path = self.write_json(tmp, "market.json", market)
            self.run_generator(path, tmp, history_dir=history_dir)

            first_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            broken = copy.deepcopy(market)
            broken["snapshot"]["revision"] = 2
            broken["snapshot"]["supersedes_sha256"] = "d" * 64
            broken["snapshot"]["raw_evidence_sha256"] = "e" * 64
            broken_path = self.write_json(tmp, "broken.json", broken)
            broken_result, _, _ = self.run_generator(
                broken_path, tmp, history_dir=history_dir, expected_returncode=2
            )

            history_path = next(history_dir.glob("*/*.json"))
            envelope = json.loads(history_path.read_text(encoding="utf-8"))
            envelope["snapshot"]["sections"]["breadth"]["metrics"]["advancers"][
                "value"
            ] += 10
            history_path.write_text(
                json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tampered_result, _, _ = self.run_generator(
                path, tmp, history_dir=history_dir, expected_returncode=2
            )

        self.assertNotEqual(first_sha, "d" * 64)
        self.assertIn("supersedes_sha256 必须指向同日上一修订", broken_result.stderr)
        self.assertIn("历史快照内容SHA不匹配", tampered_result.stderr)

    def test_history_derives_percentiles_and_resolves_previous_verification(self):
        current = json.loads(MARKET.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            history_dir = Path(tmp) / "history"
            for day in range(1, 61):
                prior = copy.deepcopy(current)
                prior_date = (date(2026, 6, 20) + timedelta(days=day - 1)).isoformat()
                prior["market_date"] = prior_date
                prior["as_of"] = prior_date
                prior["snapshot"]["cutoff_at"] = f"{prior_date}T18:00:00+08:00"
                prior["snapshot"]["raw_evidence_sha256"] = f"{day:064x}"
                self.retime_snapshot(prior["sections"], prior_date)
                self.retime_snapshot(prior["verification_points"], prior_date)
                for event in prior["sections"]["events"]["items"]:
                    event["event_date"] = prior_date
                prior["sections"]["breadth"]["metrics"]["advancers"]["value"] = 2000 + day
                prior["sections"]["turnover"]["metrics"]["amount"]["value"] = (
                    1_000_000_000_000 + day * 1_000_000_000
                )
                if day == 60:
                    prior["verification_points"][0]["event_date"] = current["market_date"]
                self.write_history_entry(history_dir, prior, f"{day + 100:064x}")

            path = self.write_json(tmp, "current.json", current)
            _, markdown_path, summary_path = self.run_generator(
                path, tmp, history_dir=history_dir
            )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(summary["history"]["sample_size"], 61)
        self.assertIsNotNone(
            summary["history"]["metrics"]["turnover_amount"]["percentile_20d"]
        )
        self.assertIsNotNone(
            summary["history"]["metrics"]["turnover_amount"]["percentile_60d"]
        )
        self.assertEqual(summary["resolved_verifications"][0]["status"], "passed")
        self.assertIn("上一期验证结果", markdown)
        self.assertIn("成立｜次日成交额是否保持在一万亿元上方", markdown)

    def test_generates_self_contained_visual_html_and_escapes_input(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        market["sections"]["indices"]["items"][0]["name"] = "<script>alert(1)</script>"
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "report.html"
            path = self.write_json(tmp, "market.html.json", market)
            _, _, summary_path = self.run_generator(path, tmp, html_out=html_path)
            html = html_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertIn("A-SHARE / DAILY INTELLIGENCE", html)
        self.assertIn("市场宽度", html)
        self.assertIn("板块温度", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<script", html)
        self.assertEqual(summary["coverage"], {"available": 4, "partial": 3, "unknown": 1})

    def test_visual_html_all_unknown_does_not_draw_zero_value_charts(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "unknown.html"
            _, _, _ = self.run_generator(UNKNOWN, tmp, html_out=html_path)
            html = html_path.read_text(encoding="utf-8")

        self.assertIn("该日期没有可得的盘面数据", html)
        self.assertNotIn('class="donut"', html)

    def test_visual_html_focuses_sector_view_and_keeps_full_list_collapsed(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        exemplar = market["sections"]["sectors"]["items"][0]
        sectors = []
        for index in range(25):
            item = copy.deepcopy(exemplar)
            item["id"] = f"sector-{index:02d}"
            item["name"] = f"行业{index:02d}"
            item["change_pct"]["value"] = index - 12
            sectors.append(item)
        market["sections"]["sectors"]["items"] = sectors
        self.with_sentiment(
            market,
            {"open_board_failed": 10, "limit_attempts": 100, "highest_streak": 6},
        )
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "focused.html"
            path = self.write_json(tmp, "focused.json", market)
            _, _, _ = self.run_generator(path, tmp, html_out=html_path)
            html = html_path.read_text(encoding="utf-8")

        self.assertIn("涨幅靠前", html)
        self.assertIn("跌幅靠前", html)
        self.assertIn("展开完整 25 个行业榜单", html)
        self.assertIn('style="width:0.00%"', html)
        self.assertIn("下一交易日验证", html)
        self.assertIn('class="sentiment-kpis"', html)
        self.assertIn("查看股票池、口径与规则", html)


if __name__ == "__main__":
    unittest.main()
