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

        self.assertEqual(summary["coverage"], {"available": 0, "partial": 0, "unknown": 10})
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

    def test_legacy_schema_is_conservatively_normalized(self):
        legacy = json.loads(MARKET.read_text(encoding="utf-8"))
        legacy["schema_version"] = "1.0"
        legacy.pop("snapshot")
        legacy["sections"]["breadth"]["universe"] = "全A非ST普通股"
        legacy["sections"]["turnover"]["metrics"]["avg_5d_amount"].pop("window")
        legacy["sections"]["funds"]["items"][0].pop("method_category")
        legacy["sections"]["style"]["items"][0].pop("window")
        legacy["verification_points"][0].pop("id")
        legacy["verification_points"][0].pop("condition")
        legacy["verification_points"][0]["source"] = {
            "id": "legacy-calendar",
            "name": "旧版日历来源",
            "url": "https://example.com/calendar",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "legacy.json", legacy)
            _, markdown_path, summary_path = self.run_generator(path, tmp)
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(summary["schema_version"], "1.2")
        self.assertEqual(summary["legacy_migration"]["from"], "1.0")
        self.assertIn("兼容归一化", markdown)
        self.assertIn("定性观察点（不自动结算）", markdown)

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
        self.assertEqual(summary["coverage"], {"available": 4, "partial": 3, "unknown": 3})

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


    def with_extension(self, market):
        """给基础 fixture 叠加 1.2 的可选分析层：板块资金流、主线矩阵、延续性检验、体检阈值。"""
        sentiment_evidence = self.evidence
        sectors = market["sections"]["sectors"]["items"]
        # 板块资金流：只有 sw-d 故意缺失，用来验证「引用板块缺资金流 → 象限 unknown」。
        flows = {"sw-a": 2_884_000_000, "sw-b": -500_000_000, "sw-c": 2_898_000_000}
        for item in sectors:
            if item["id"] in flows:
                item["fund_flow"] = {
                    "value": flows[item["id"]],
                    "unit": "CNY",
                    "observed_at": "2026-08-25",
                    "published_at": "2026-08-25",
                    "fetched_at": "2026-08-25T16:00:00+08:00",
                    "source": {
                        "id": "fixture-board-flow",
                        "name": "测试板块资金源",
                        "url": "https://example.com/board-flow",
                    },
                }
                item["fund_flow_method_category"] = "provider_model"
        exemplar = copy.deepcopy(sectors[0])
        exemplar["id"] = "sw-d"
        exemplar["name"] = "计算机"
        exemplar.pop("fund_flow")
        exemplar.pop("fund_flow_method_category")
        sectors.append(exemplar)

        theme_specs = [
            ("pcb", "AI硬件·PCB链", ["sw-a", "sw-c"], 10),
            ("upstream", "上游材料", ["sw-c"], 0),
            ("aiapp", "AI应用·AI安全", ["sw-b"], 11),
            ("optical", "光模块·光通信", ["sw-b"], 1),
            ("pending", "待补主题", ["sw-d"], 5),
        ]
        market["sections"]["mainline_matrix"] = {
            "availability": "available",
            "status_reason": "主题成分板块与涨停家数由输入显式声明",
            "classification": "申万一级",
            "methodology": "按输入声明的成分板块与涨停归组，象限由派生规则判定",
            "quadrant_rules": {
                "limit_up_threshold": 3,
                "capital_threshold_cny": 0,
            },
            "caveat": "主题成分由输入人工归组，跨主题个股可能重复计入。",
            "themes": [
                {
                    "id": theme_id,
                    "name": name,
                    "boards": boards,
                    "limit_up": sentiment_evidence(count),
                }
                for theme_id, name, boards, count in theme_specs
            ],
        }
        market["sections"]["prev_pool_performance"] = {
            "availability": "available",
            "status_reason": "前一交易日涨停池当日表现全量重算",
            "previous_market_date": "2026-08-24",
            "universe": copy.deepcopy(market["sections"]["breadth"]["universe"]),
            "health_threshold_pct": 30,
            "metrics": {
                "pool_size": sentiment_evidence(40),
                "promotion_count": sentiment_evidence(11),
                "avg_change_pct": {
                    **sentiment_evidence(3.21),
                    "unit": "percent",
                },
                "median_change_pct": {
                    **sentiment_evidence(3.12),
                    "unit": "percent",
                },
            },
            "by_group": [
                {
                    "id": "group-electronics",
                    "name": "电子元件",
                    "count": sentiment_evidence(9),
                    "avg_change_pct": {
                        **sentiment_evidence(6.42),
                        "unit": "percent",
                    },
                }
            ],
        }
        self.with_sentiment(
            market,
            {"open_board_failed": 10, "limit_attempts": 100, "highest_streak": 6},
        )
        market["sections"]["short_term_sentiment"]["health_thresholds"] = {
            "limit_up_min": 45,
            "limit_down_max": 5,
            "open_board_rate_max_pct": 25,
            "promotion_rate_min_pct": 30,
            "highest_streak_min": 3,
        }
        return market

    def test_derives_mainline_quadrants_from_declared_rules(self):
        market = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "extended.json", market)
            _, markdown_path, summary_path = self.run_generator(path, tmp)
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        mainline = summary["derived"]["mainline_matrix"]
        quadrants = {theme["id"]: theme["quadrant"] for theme in mainline["themes"]}
        self.assertEqual(
            quadrants,
            {
                "pcb": "dual_confirmed",
                "upstream": "capital_led",
                "aiapp": "sentiment_only",
                "optical": "bleeding",
                "pending": "unknown",
            },
        )
        pcb = next(theme for theme in mainline["themes"] if theme["id"] == "pcb")
        # 多板块：资金求和、涨跌幅等权均值，都要可复算
        self.assertAlmostEqual(pcb["board_fund_flow_cny"], 5_782_000_000)
        self.assertAlmostEqual(pcb["board_change_pct_equal_weight"], 2.35)
        self.assertEqual(pcb["missing_board_fund_flow"], [])
        pending = next(theme for theme in mainline["themes"] if theme["id"] == "pending")
        self.assertIsNone(pending["board_fund_flow_cny"])
        self.assertEqual(pending["missing_board_fund_flow"], ["sw-d"])
        self.assertEqual(mainline["quadrant_counts"]["dual_confirmed"], 1)
        self.assertEqual(mainline["quadrant_counts"]["unknown"], 1)
        self.assertIn("## 九、双确认主线矩阵", markdown)
        self.assertIn("双确认主题：涨停家数达标且板块资金净流入", markdown)
        self.assertIn("反方证据与自我证伪", markdown)

    def test_bleeding_threshold_splits_sentiment_pulse_into_bleeding(self):
        """声明失血线后，「家数达标」按资金流出深度拆成情绪脉冲与情绪失血。"""
        market = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        market["sections"]["mainline_matrix"]["quadrant_rules"]["bleeding_threshold_cny"] = (
            -200_000_000
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "bleeding.json", market)
            _, markdown_path, summary_path = self.run_generator(path, tmp)
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        mainline = summary["derived"]["mainline_matrix"]
        quadrants = {theme["id"]: theme["quadrant"] for theme in mainline["themes"]}
        # aiapp 板块资金 -5 亿 ≤ 失血线 -2 亿 → 情绪失血；optical 涨停仅 1 家未达标，仍是失血。
        self.assertEqual(quadrants["aiapp"], "sentiment_bleeding")
        self.assertEqual(quadrants["optical"], "bleeding")
        self.assertEqual(quadrants["pcb"], "dual_confirmed")
        self.assertEqual(mainline["quadrant_rules"]["bleeding_threshold_cny"], -200_000_000)
        self.assertEqual(mainline["quadrant_counts"]["sentiment_bleeding"], 1)
        self.assertEqual(mainline["quadrant_counts"]["sentiment_only"], 0)
        self.assertIn("情绪失血主题：涨停家数达标但板块资金大额净流出", markdown)
        self.assertIn("情绪失血 1 个", markdown)
        self.assertIn("失血线", markdown)
        codes = [signal["code"] for signal in summary["signals"]]
        self.assertIn("mainline_sentiment_bleeding", codes)
        self.assertNotIn("mainline_sentiment_only", codes)

    def test_undeclared_bleeding_threshold_keeps_legacy_quadrants(self):
        """未声明失血线时，情绪失血不参与计数/图例/信号，输出与 1.2 原样一致。"""
        market = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "extended.json", market)
            _, markdown_path, summary_path = self.run_generator(path, tmp)
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        mainline = summary["derived"]["mainline_matrix"]
        self.assertNotIn("bleeding_threshold_cny", mainline["quadrant_rules"])
        self.assertNotIn("sentiment_bleeding", mainline["quadrant_counts"])
        self.assertEqual(mainline["quadrant_counts"]["sentiment_only"], 1)
        self.assertNotIn("情绪失血", markdown)
        codes = [signal["code"] for signal in summary["signals"]]
        self.assertIn("mainline_sentiment_only", codes)
        self.assertNotIn("mainline_sentiment_bleeding", codes)

    def test_rejects_invalid_bleeding_threshold_and_unsupported_rule_key(self):
        not_below = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        not_below["sections"]["mainline_matrix"]["quadrant_rules"][
            "bleeding_threshold_cny"
        ] = 0  # 等于资金线：区间会倒挂，必须拒收
        unsupported = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        unsupported["sections"]["mainline_matrix"]["quadrant_rules"]["bogus_rule"] = 1
        bad_type = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        bad_type["sections"]["mainline_matrix"]["quadrant_rules"]["bleeding_threshold_cny"] = "低"
        with tempfile.TemporaryDirectory() as tmp:
            below_path = self.write_json(tmp, "not-below.json", not_below)
            extra_path = self.write_json(tmp, "unsupported.json", unsupported)
            type_path = self.write_json(tmp, "bad-type.json", bad_type)
            below_result, _, _ = self.run_generator(below_path, tmp, expected_returncode=2)
            extra_result, _, _ = self.run_generator(extra_path, tmp, expected_returncode=2)
            type_result, _, _ = self.run_generator(type_path, tmp, expected_returncode=2)

        self.assertIn(
            "bleeding_threshold_cny 必须严格小于 capital_threshold_cny",
            below_result.stderr,
        )
        self.assertIn("quadrant_rules 含不支持的键：bogus_rule", extra_result.stderr)
        self.assertIn("bleeding_threshold_cny 必须是有限数值", type_result.stderr)

    def test_derives_prev_pool_promotion_rate_and_health_line(self):
        market = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "extended.json", market)
            _, markdown_path, summary_path = self.run_generator(path, tmp)
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        prev_pool = summary["derived"]["prev_pool_performance"]
        self.assertAlmostEqual(prev_pool["promotion_rate_pct"], 27.5)
        self.assertEqual(prev_pool["health"], "below_line")
        self.assertEqual(prev_pool["previous_market_date"], "2026-08-24")
        self.assertIn("## 八、延续性检验：前一涨停池当日表现", markdown)
        self.assertIn("晋级率：27.50%，低于声明的健康线 30%", markdown)

    def test_health_check_enumerates_conditions_without_aggregate_score(self):
        market = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "extended.json", market)
            _, markdown_path, summary_path = self.run_generator(path, tmp)
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        health = summary["derived"]["sentiment_health_check"]
        self.assertEqual(health["evaluated_count"], 5)
        self.assertEqual(health["passed_count"], 4)
        failed = [check["code"] for check in health["checks"] if check["status"] == "failed"]
        self.assertEqual(failed, ["promotion_rate_min_pct"])
        self.assertEqual(health["unresolved"], [])
        self.assertNotIn("总分", markdown)
        self.assertIn("不聚合成分数", markdown)

    def test_health_check_omits_conditions_without_observed_value(self):
        market = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        market["sections"].pop("prev_pool_performance")
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "no-prev-pool.json", market)
            _, _, summary_path = self.run_generator(path, tmp)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        health = summary["derived"]["sentiment_health_check"]
        self.assertIn("promotion_rate_min_pct", health["unresolved"])
        self.assertEqual(health["evaluated_count"], 4)
        self.assertEqual(health["passed_count"], 4)

    def test_promotion_rate_pct_is_settlable_verification_point(self):
        """晋级率必须能被 event_date 当天的同一口径自动结算，而不是停在 unknown。"""
        current = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        prior = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        prior_date = "2026-08-24"
        prior["market_date"] = prior_date
        prior["as_of"] = prior_date
        prior["snapshot"]["cutoff_at"] = f"{prior_date}T18:00:00+08:00"
        self.retime_snapshot(prior["sections"], prior_date)
        for event in prior["sections"]["events"]["items"]:
            event["event_date"] = prior_date
        # 前一日快照自身的延续性检验必须指向更早的交易日，否则会被契约拒收。
        prior["sections"]["prev_pool_performance"]["previous_market_date"] = "2026-08-21"
        prior["verification_points"] = [
            {
                "id": "verify-promotion-rate",
                "title": "次日涨停池晋级率是否达到 20%",
                "event_date": current["market_date"],
                "published_at": prior_date,
                "fetched_at": f"{prior_date}T16:00:00+08:00",
                "condition": {
                    "metric": "promotion_rate_pct",
                    "operator": ">=",
                    "value": 20,
                    "unit": "percent",
                },
                "source": {
                    "id": "derived-prev-pool",
                    "name": "复盘派生验证点",
                    "kind": "derived",
                    "evidence_refs": ["sections.prev_pool_performance.metrics.pool_size"],
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            history_dir = Path(tmp) / "history"
            self.write_history_entry(history_dir, prior, "f" * 64)
            path = self.write_json(tmp, "current.json", current)
            _, markdown_path, summary_path = self.run_generator(
                path, tmp, history_dir=history_dir
            )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        resolved = summary["resolved_verifications"]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["id"], "verify-promotion-rate")
        self.assertEqual(resolved[0]["status"], "passed")
        self.assertAlmostEqual(resolved[0]["observed_value"], 27.5)
        self.assertEqual(resolved[0]["observed_market_date"], current["market_date"])
        series = summary["history"]["metrics"]["promotion_rate_pct"]
        self.assertEqual(series["unit"], "percent")
        self.assertAlmostEqual(series["current"], 27.5)
        self.assertIn("| 昨日涨停池晋级率 | +27.50% |", markdown)

    def test_rejects_promotion_rate_point_with_wrong_unit(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        market["verification_points"][0]["condition"] = {
            "metric": "promotion_rate_pct",
            "operator": ">=",
            "value": 20,
            "unit": "count",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "wrong-unit.json", market)
            result, _, _ = self.run_generator(path, tmp, expected_returncode=2)

        self.assertIn("unit 与metric不匹配", result.stderr)

    def test_history_omits_promotion_rate_without_prev_pool_section(self):
        """旧输入没有延续性检验章节时，指标表不新增行，输出保持原样。"""
        with tempfile.TemporaryDirectory() as tmp:
            _, markdown_path, summary_path = self.run_generator(MARKET, tmp)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertNotIn("promotion_rate_pct", summary["history"]["metrics"])
        self.assertNotIn("昨日涨停池晋级率", markdown)

    def test_rejects_mainline_with_missing_board_or_undeclared_rules(self):
        missing = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        missing["sections"]["mainline_matrix"]["themes"][0]["boards"] = ["sw-nonexistent"]
        undeclared = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        undeclared["sections"]["mainline_matrix"]["quadrant_rules"].pop("limit_up_threshold")
        mismatched = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        mismatched["sections"]["mainline_matrix"]["classification"] = "东财概念"
        with tempfile.TemporaryDirectory() as tmp:
            missing_path = self.write_json(tmp, "missing-board.json", missing)
            undeclared_path = self.write_json(tmp, "undeclared.json", undeclared)
            mismatched_path = self.write_json(tmp, "mismatched.json", mismatched)
            missing_result, _, _ = self.run_generator(
                missing_path, tmp, expected_returncode=2
            )
            undeclared_result, _, _ = self.run_generator(
                undeclared_path, tmp, expected_returncode=2
            )
            mismatched_result, _, _ = self.run_generator(
                mismatched_path, tmp, expected_returncode=2
            )

        self.assertIn("引用了sectors中不存在的板块", missing_result.stderr)
        self.assertIn("必须显式声明", undeclared_result.stderr)
        self.assertIn("必须与sections.sectors.classification一致", mismatched_result.stderr)

    def test_rejects_prev_pool_with_mismatched_universe_or_impossible_promotion(self):
        mismatched = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        mismatched["sections"]["prev_pool_performance"]["universe"]["id"] = "csi-300"
        impossible = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        impossible["sections"]["prev_pool_performance"]["metrics"]["promotion_count"][
            "value"
        ] = 41
        with tempfile.TemporaryDirectory() as tmp:
            mismatched_path = self.write_json(tmp, "pool-universe.json", mismatched)
            impossible_path = self.write_json(tmp, "pool-impossible.json", impossible)
            mismatched_result, _, _ = self.run_generator(
                mismatched_path, tmp, expected_returncode=2
            )
            impossible_result, _, _ = self.run_generator(
                impossible_path, tmp, expected_returncode=2
            )

        self.assertIn(
            "prev_pool_performance.universe 必须与breadth.universe一致",
            mismatched_result.stderr,
        )
        self.assertIn("promotion_count 不能大于pool_size", impossible_result.stderr)

    def test_rejects_board_fund_flow_without_declared_method_category(self):
        market = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        market["sections"]["sectors"]["items"][0].pop("fund_flow_method_category")
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "flow-method.json", market)
            result, _, _ = self.run_generator(path, tmp, expected_returncode=2)

        self.assertIn("fund_flow_method_category 不受支持", result.stderr)

    def test_schema_1_1_input_is_upgraded_without_backfilling_sections(self):
        legacy = json.loads(MARKET.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write_json(tmp, "v11.json", legacy)
            _, markdown_path, summary_path = self.run_generator(path, tmp)
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertEqual(legacy["schema_version"], "1.1")
        self.assertEqual(summary["schema_version"], "1.2")
        self.assertEqual(summary["legacy_migration"]["from"], "1.1")
        self.assertIn("可选", summary["legacy_migration"]["warnings"][0])
        self.assertIn("兼容归一化", markdown)
        self.assertEqual(
            sorted(summary["sections"]),
            sorted(
                [
                    "indices",
                    "breadth",
                    "short_term_sentiment",
                    "turnover",
                    "sectors",
                    "funds",
                    "style",
                    "events",
                    "mainline_matrix",
                    "prev_pool_performance",
                ]
            ),
        )

    def test_html_renders_new_panels_and_keeps_unknown_honest(self):
        market = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "extended.html"
            path = self.write_json(tmp, "extended-html.json", market)
            _, _, _ = self.run_generator(path, tmp, html_out=html_path)
            html = html_path.read_text(encoding="utf-8")

        self.assertIn("双确认主线矩阵", html)
        self.assertIn("延续性检验", html)
        self.assertIn("阈值体检", html)
        self.assertIn("反方证据 · mainline_matrix", html)
        self.assertIn("不是评分", html)
        self.assertNotIn("<script", html)

    def unit_evidence(self, value, unit, observed_at="2026-08-25"):
        return {
            "value": value,
            "unit": unit,
            "observed_at": observed_at,
            "published_at": "2026-08-25",
            "fetched_at": "2026-08-25T16:00:00+08:00",
            "source": {
                "id": "fixture-security",
                "name": "测试个股源",
                "url": "https://example.com/security",
            },
        }

    def with_extended_structures(self, market):
        """叠加 1.2 发布后追加的四项可选结构：连板梯队、高标质量、概念层资金流、板块内个股。"""
        self.with_extension(market)
        sentiment = market["sections"]["short_term_sentiment"]
        # 各档之和 70+6+3+1 = 80 = breadth.limit_up；最高档 6 = highest_streak。
        sentiment["streak_distribution"] = [
            {"streak": streak, "count": self.evidence(count)}
            for streak, count in ((1, 70), (2, 6), (3, 3), (6, 1))
        ]
        sentiment["high_boards"] = [
            {
                "name": "闽东电力",
                "code": "600509",
                "streak": 6,
                "fund_flow": self.unit_evidence(55_000_000, "CNY"),
                "fund_flow_method_category": "provider_model",
                "turnover_pct": self.unit_evidence(12.3, "percent"),
                "note": "空间龙头，机构未买",
            },
            {
                "name": "超声电子",
                "streak": 3,
                "fund_flow": self.unit_evidence(282_000_000, "CNY"),
                "fund_flow_method_category": "provider_model",
                "turnover_pct": self.unit_evidence(19.3, "percent"),
            },
            {
                "name": "中新赛克",
                "streak": 3,
                "fund_flow": self.unit_evidence(13_000_000, "CNY"),
                "fund_flow_method_category": "provider_model",
                "turnover_pct": self.unit_evidence(1.06, "percent"),
            },
            {
                "name": "凯盛新能",
                "streak": 3,
                "fund_flow": self.unit_evidence(-1_000_000, "CNY"),
                "fund_flow_method_category": "provider_model",
                "turnover_pct": self.unit_evidence(10.4, "percent"),
            },
        ]
        market["sections"]["sectors"]["concept_view"] = {
            "classification": "东财概念",
            "status_reason": "概念层与风格项资金流，与行业层分开成表",
            "items": [
                {
                    "id": "cp-pcb",
                    "name": "PCB",
                    "fund_flow": self.unit_evidence(4_385_000_000, "CNY"),
                    "fund_flow_method_category": "provider_model",
                },
                {
                    "id": "cp-mlcc",
                    "name": "MLCC",
                    "fund_flow": self.unit_evidence(2_241_000_000, "CNY"),
                    "fund_flow_method_category": "provider_model",
                },
                {
                    "id": "cp-msci",
                    "name": "MSCI中国",
                    "fund_flow": self.unit_evidence(-23_116_000_000, "CNY"),
                    "fund_flow_method_category": "provider_model",
                },
                {
                    "id": "cp-margin",
                    "name": "融资融券",
                    "fund_flow": self.unit_evidence(-18_933_000_000, "CNY"),
                    "fund_flow_method_category": "provider_model",
                },
            ],
        }
        market["sections"]["sectors"]["items"][0]["leaders"] = [
            {
                "name": "科翔股份",
                "code": "300476",
                "change_pct": self.unit_evidence(20.0, "percent"),
                "turnover_pct": self.unit_evidence(25.5, "percent"),
                "note": "二线小票放量",
            },
            {
                "name": "深南电路",
                "change_pct": self.unit_evidence(-1.9, "percent"),
                "fund_flow": self.unit_evidence(-165_000_000, "CNY"),
                "fund_flow_method_category": "provider_model",
                "turnover_pct": self.unit_evidence(1.16, "percent"),
                "note": "核心票缩量休整",
            },
        ]
        return market

    def test_extended_structures_render_and_enter_summary(self):
        market = self.with_extended_structures(json.loads(MARKET.read_text(encoding="utf-8")))
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "extended.html"
            path = self.write_json(tmp, "extended.json", market)
            _, markdown_path, summary_path = self.run_generator(
                path, tmp, html_out=html_path
            )
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            html = html_path.read_text(encoding="utf-8")

        derived = summary["derived"]
        ladder = derived["streak_distribution"]
        self.assertEqual([tier["streak"] for tier in ladder["tiers"]], [6, 3, 2, 1])
        self.assertEqual(ladder["total"], 80)
        self.assertEqual(ladder["first_board_count"], 70)
        self.assertEqual(ladder["continued_count"], 10)
        self.assertAlmostEqual(ladder["first_board_share_pct"], 87.5)
        self.assertEqual(ladder["highest_streak_count"], 1)

        quality = derived["high_board_quality"]
        self.assertEqual(quality["count"], 4)
        self.assertEqual(quality["declared_fund_flow_count"], 4)
        self.assertEqual(quality["inflow_count"], 3)
        self.assertEqual(quality["outflow_count"], 1)
        self.assertEqual(quality["boards"][0]["name"], "闽东电力")

        concept = derived["concept_flows"]
        self.assertEqual(concept["classification"], "东财概念")
        self.assertEqual([item["id"] for item in concept["inflows"]], ["cp-pcb", "cp-mlcc"])
        self.assertEqual([item["id"] for item in concept["outflows"]], ["cp-msci", "cp-margin"])

        leaders = derived["sector_leaders"]
        self.assertEqual(len(leaders), 1)
        self.assertEqual(leaders[0]["id"], "sw-a")
        # 有资金流的按金额降序排在前，缺资金流的排最后（缺失视为 -inf）。
        self.assertEqual(
            [row["name"] for row in leaders[0]["leaders"]], ["深南电路", "科翔股份"]
        )

        for phrase in ("连板梯队", "最高板质量", "概念层（东财概念", "板块内重点个股"):
            self.assertIn(phrase, markdown)
        self.assertIn("| 6 板 | 1 |", markdown)
        self.assertIn("不构成个股推荐", markdown)
        for phrase in ("连板梯队", "最高板质量", "概念层资金流", "板块内重点个股"):
            self.assertIn(phrase, html)
        self.assertNotIn("<script", html)

    def test_undeclared_extended_structures_keep_legacy_output(self):
        """四项结构全部缺省时，摘要不产生任何新键，报告不出现任何新段落。"""
        market = self.with_extension(json.loads(MARKET.read_text(encoding="utf-8")))
        with tempfile.TemporaryDirectory() as tmp:
            _, markdown_path, summary_path = self.run_generator(
                self.write_json(tmp, "legacy.json", market), tmp
            )
            markdown = markdown_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))

        for key in (
            "streak_distribution",
            "high_board_quality",
            "concept_flows",
            "sector_leaders",
        ):
            self.assertNotIn(key, summary["derived"])
        for phrase in ("连板梯队", "最高板质量", "概念层（", "板块内重点个股"):
            self.assertNotIn(phrase, markdown)
        # 章节数不变：追加结构没有新增顶层章节，coverage 分母与旧版一致。
        self.assertEqual(summary["coverage"]["unknown"], 0)

    def test_rejects_ladder_that_disagrees_with_limit_up_and_highest_streak(self):
        with tempfile.TemporaryDirectory() as tmp:
            mismatch_total = self.with_extended_structures(
                json.loads(MARKET.read_text(encoding="utf-8"))
            )
            tiers = mismatch_total["sections"]["short_term_sentiment"]["streak_distribution"]
            next(item for item in tiers if item["streak"] == 1)["count"]["value"] = 69
            total_result, _, _ = self.run_generator(
                self.write_json(tmp, "total.json", mismatch_total),
                tmp,
                expected_returncode=2,
            )

            mismatch_max = self.with_extended_structures(
                json.loads(MARKET.read_text(encoding="utf-8"))
            )
            tiers = mismatch_max["sections"]["short_term_sentiment"]["streak_distribution"]
            next(item for item in tiers if item["streak"] == 6)["streak"] = 5
            max_result, _, _ = self.run_generator(
                self.write_json(tmp, "max.json", mismatch_max),
                tmp,
                expected_returncode=2,
            )

        self.assertIn(
            "streak_distribution 各档家数之和必须等于breadth.limit_up",
            total_result.stderr,
        )
        self.assertIn("streak_distribution 的最高档必须等于", max_result.stderr)

    def test_rejects_high_board_above_declared_max_and_missing_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            above = self.with_extended_structures(json.loads(MARKET.read_text(encoding="utf-8")))
            above["sections"]["short_term_sentiment"]["high_boards"][0]["streak"] = 7
            above_result, _, _ = self.run_generator(
                self.write_json(tmp, "above.json", above), tmp, expected_returncode=2
            )

            hollow = self.with_extended_structures(json.loads(MARKET.read_text(encoding="utf-8")))
            board = hollow["sections"]["short_term_sentiment"]["high_boards"][0]
            board.pop("fund_flow")
            board.pop("fund_flow_method_category")
            board.pop("turnover_pct")
            hollow_result, _, _ = self.run_generator(
                self.write_json(tmp, "hollow.json", hollow), tmp, expected_returncode=2
            )

        self.assertIn("不能高于short_term_sentiment最高连板", above_result.stderr)
        self.assertIn("至少需要fund_flow或turnover_pct之一", hollow_result.stderr)

    def test_rejects_concept_view_sharing_industry_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            market = self.with_extended_structures(json.loads(MARKET.read_text(encoding="utf-8")))
            market["sections"]["sectors"]["concept_view"]["classification"] = "申万一级"
            result, _, _ = self.run_generator(
                self.write_json(tmp, "same.json", market), tmp, expected_returncode=2
            )

        self.assertIn("必须区别于sectors.classification", result.stderr)

    def test_rejects_sector_leader_without_any_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            market = self.with_extended_structures(json.loads(MARKET.read_text(encoding="utf-8")))
            market["sections"]["sectors"]["items"][0]["leaders"][0].pop("change_pct")
            result, _, _ = self.run_generator(
                self.write_json(tmp, "leader.json", market), tmp, expected_returncode=2
            )

        self.assertIn("至少需要change_pct或fund_flow之一", result.stderr)


if __name__ == "__main__":
    unittest.main()
