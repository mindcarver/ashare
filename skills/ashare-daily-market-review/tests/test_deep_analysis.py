import copy
import json
import subprocess
import sys
import tempfile
import unittest

from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "generate_daily_review.py"
MARKET = Path(__file__).parent / "fixtures" / "market.json"
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from deep_analysis import verification_observation_index  # noqa: E402


SOURCE = {"id": "deep-fixture", "name": "深度测试源", "url": "https://example.com/deep"}


def evidence(value, unit, observed="2026-08-25"):
    return {
        "value": value,
        "unit": unit,
        "observed_at": observed,
        "published_at": observed,
        "fetched_at": f"{observed}T16:00:00+08:00",
        "source": SOURCE,
    }


def datetime_evidence(value, observed="2026-08-25"):
    return {
        "value": value,
        "observed_at": observed,
        "published_at": observed,
        "fetched_at": f"{observed}T16:00:00+08:00",
        "source": SOURCE,
    }


class DeepAnalysisTests(unittest.TestCase):
    def deep_market(self):
        market = json.loads(MARKET.read_text(encoding="utf-8"))
        market["schema_version"] = "1.4"
        market["analysis_mode"] = "deep"
        market["verification_points"][0]["subject"] = {
            "scope": "market",
            "id": "all-a",
            "label": "A股全市场",
        }
        for item, flow in zip(market["sections"]["sectors"]["items"], (3e9, -2e9, 1e8)):
            item["fund_flow"] = evidence(flow, "CNY")
            item["fund_flow_method_category"] = "provider_model"
        market["sections"]["mainline_matrix"] = {
            "availability": "available",
            "status_reason": "主题证据完整",
            "classification": "申万一级",
            "methodology": "按测试板块显式归组",
            "quadrant_rules": {"limit_up_threshold": 2, "capital_threshold_cny": 1e9},
            "themes": [
                {
                    "id": "electronics-chain",
                    "name": "电子链",
                    "boards": ["sw-a"],
                    "limit_up": evidence(3, "count"),
                }
            ],
        }
        market["deep_analysis"] = {
            "security_details": {
                "availability": "available",
                "status_reason": "高标与板块重点股证据完整",
                "items": [
                    {
                        "code": "603186",
                        "name": "华正新材",
                        "roles": ["high_board", "sector_leader"],
                        "streak": 2,
                        "change_pct": evidence(10.0, "percent"),
                        "fund_flow_windows": [
                            {
                                "window": {"trading_days": days, "end_at": "2026-08-25"},
                                "metric": evidence(value, "CNY"),
                                "method_category": "provider_model",
                            }
                            for days, value in ((1, 7.07e8), (3, 14.49e8), (5, 24.73e8), (10, 30.17e8))
                        ],
                        "seal_structure": {
                            "first_sealed_at": datetime_evidence("2026-08-25T09:31:07+08:00"),
                            "last_sealed_at": datetime_evidence("2026-08-25T09:41:39+08:00"),
                            "sealed_order_amount": evidence(2.92e8, "CNY"),
                            "break_count": evidence(1, "count"),
                        },
                    }
                ],
            },
            "liquidity_regime": {
                "availability": "available",
                "status_reason": "指数与ETF的量价历史完整",
                "thresholds": {
                    "volume_ratio_min": 1.3,
                    "consecutive_days_min": 2,
                    "ma20_distance_min_pct": 0,
                    "daily_change_min_pct": 3,
                    "advancer_share_min_pct": 60,
                    "limit_up_min": 45,
                    "limit_down_max": 10,
                },
                "benchmarks": [
                    {
                        "id": "000688",
                        "name": "科创50",
                        "kind": "index",
                        "history_sample_days": 121,
                        "change_pct": evidence(1.55, "percent"),
                        "volume_ratio_5d": evidence(0.88, "ratio"),
                        "ma20_distance_pct": evidence(-3.89, "percent"),
                        "ma60_distance_pct": evidence(-12.62, "percent"),
                        "return_percentile_120d": evidence(61.0, "percent"),
                        "volume_percentile_120d": evidence(32.0, "percent"),
                        "consecutive_volume_days": evidence(0, "count"),
                    }
                ],
            },
            "sentiment_cycle": {
                "availability": "available",
                "status_reason": "三个交易日同口径情绪序列",
                "points": [
                    self.cycle_point("2026-08-21", 60, 8, 70, 32, "neutral"),
                    self.cycle_point("2026-08-22", 45, 12, 64, 25, "divergence"),
                    self.cycle_point("2026-08-25", 32, 27, 57.14, 12.73, "divergence"),
                ],
            },
            "capital_co_movement": {
                "availability": "available",
                "status_reason": "流入与流出两端均有完整贡献分解",
                "claim_type": "co_movement_candidate",
                "methodology": "同日供应商模型资金流共现，不作账户级追踪",
                "thresholds": {"pseudo_sector_top1_share_pct": 80},
                "groups": [
                    self.capital_group("inflow-electronics", "电子流入", "inflow", ["sw-a"], 3e9, -0.2, [("603186", "华正新材", 2.7e9), ("600183", "生益科技", 0.3e9)]),
                    self.capital_group("outflow-bank", "银行流出", "outflow", ["sw-b"], -2e9, -1.1, [("600000", "浦发银行", -1.5e9), ("601398", "工商银行", -0.5e9)]),
                ],
                "relations": [
                    {
                        "from_group_id": "outflow-bank",
                        "to_group_id": "inflow-electronics",
                        "hypothesis": "同日银行流出与电子流入并存，可能反映风格切换",
                        "counter_evidence": ["全市场成交额未扩张，不能证明增量资金进入"],
                    }
                ],
            },
            "catalyst_chains": {
                "availability": "available",
                "status_reason": "事实、机制、反证与验证均完整",
                "items": [
                    {
                        "id": "ccl-price-rise",
                        "title": "覆铜板上游提价",
                        "event_date": "2026-08-25",
                        "published_at": "2026-08-25",
                        "fetched_at": "2026-08-25T16:00:00+08:00",
                        "source": SOURCE,
                        "fact": "供应商发布新的电子布提价函",
                        "mechanism_hypothesis": "若订单接受提价，上游材料收入弹性可能改善",
                        "causal_status": "hypothesis",
                        "affected_theme_ids": ["electronics-chain"],
                        "counter_evidence": ["提价可能尚未传导到实际成交与利润"],
                        "verification_point_ids": ["verify-turnover"],
                    }
                ],
            },
            "lhb_structure": {
                "availability": "partial",
                "status_reason": "当日榜单未披露，使用前一交易日",
                "observed_at": "2026-08-24",
                "published_at": "2026-08-25",
                "fetched_at": "2026-08-25T16:00:00+08:00",
                "source": SOURCE,
                "methodology": "按已披露买卖席位金额聚合",
                "items": [
                    {
                        "code": "603186",
                        "name": "华正新材",
                        "buy_amount": evidence(5e8, "CNY", "2026-08-24"),
                        "sell_amount": evidence(2e8, "CNY", "2026-08-24"),
                        "net_amount": evidence(3e8, "CNY", "2026-08-24"),
                        "buyer_count": evidence(5, "count", "2026-08-24"),
                        "seller_count": evidence(5, "count", "2026-08-24"),
                        "top_buyer_share_pct": evidence(38, "percent", "2026-08-24"),
                        "top_seller_share_pct": evidence(29, "percent", "2026-08-24"),
                        "seat_types": ["机构专用", "营业部"],
                    }
                ],
            },
        }
        return market

    @staticmethod
    def cycle_point(day, up, down, seal, promotion, state):
        return {
            "market_date": day,
            "state": state,
            "state_rule": "公开五态规则",
            "metrics": {
                "limit_up": evidence(up, "count", day),
                "limit_down": evidence(down, "count", day),
                "seal_rate_pct": evidence(seal, "percent", day),
                "promotion_rate_pct": evidence(promotion, "percent", day),
            },
        }

    @staticmethod
    def capital_group(group_id, name, role, boards, total, change, contributions):
        return {
            "id": group_id,
            "name": name,
            "role": role,
            "board_ids": boards,
            "total_fund_flow": evidence(total, "CNY"),
            "change_pct": evidence(change, "percent"),
            "contributions_complete": True,
            "contributions": [
                {"code": code, "name": stock_name, "fund_flow": evidence(flow, "CNY")}
                for code, stock_name, flow in contributions
            ],
        }

    def run_generator(self, market, directory, expected=0, history=None, as_of="2026-08-25"):
        input_path = Path(directory) / "market.json"
        output = Path(directory) / "report.md"
        summary = Path(directory) / "summary.json"
        html = Path(directory) / "report.html"
        input_path.write_text(json.dumps(market, ensure_ascii=False, indent=2), encoding="utf-8")
        command = [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(input_path),
            "--as-of",
            as_of,
            "--output",
            str(output),
            "--summary-out",
            str(summary),
            "--html-out",
            str(html),
        ]
        if history:
            command.extend(["--history-dir", str(history)])
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result, output, summary, html

    @staticmethod
    def retime(value, old_day, new_day):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"observed_at", "published_at", "end_at"} and child == old_day:
                    value[key] = new_day
                elif key == "fetched_at" and isinstance(child, str) and child.startswith(old_day):
                    value[key] = child.replace(old_day, new_day, 1)
                elif key == "value" and isinstance(child, str) and child.startswith(old_day + "T"):
                    value[key] = child.replace(old_day, new_day, 1)
                else:
                    DeepAnalysisTests.retime(child, old_day, new_day)
        elif isinstance(value, list):
            for child in value:
                DeepAnalysisTests.retime(child, old_day, new_day)

    def test_full_deep_analysis_renders_and_derives_without_hidden_score(self):
        market = self.deep_market()
        with tempfile.TemporaryDirectory() as tmp:
            _, report_path, summary_path, html_path = self.run_generator(market, tmp)
            report = report_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            html = html_path.read_text(encoding="utf-8")

        deep = summary["derived"]["deep_analysis"]
        self.assertEqual(deep["liquidity_regime"]["result"], "conditions_not_met")
        self.assertTrue(deep["sentiment_cycle"]["new_window_low_limit_up"])
        self.assertEqual(
            deep["capital_co_movement"]["groups"][0]["pseudo_sector_status"],
            "flagged",
        )
        outflow = deep["capital_co_movement"]["groups"][1]
        self.assertEqual(outflow["opposite_direction_count"], 0)
        self.assertIn("## 深度分析层（Schema 1.4）", report)
        self.assertIn("产业催化证据链", report)
        self.assertIn("同日流出与流入只构成共现候选", report)
        self.assertIn('aria-label="深度分析层"', html)
        for visible in (
            "首封",
            "末封",
            "炸板",
            "收益120日分位",
            "公开规则",
            "反向个股",
            "反方证据",
            "卖一占比",
            "席位类型",
        ):
            self.assertIn(visible, html)
        self.assertNotIn("情绪总分", report)
        for public_report in (report, html):
            self.assertNotIn("深度测试源", public_report)
            self.assertNotIn("https://example.com/deep", public_report)
            self.assertNotIn("来源汇总", public_report)

    def test_declared_unknown_deep_component_is_visible_in_html(self):
        market = self.deep_market()
        market["deep_analysis"] = {
            name: {
                "availability": "unknown",
                "status_reason": "深度证据尚未披露",
            }
            for name in (
                "security_details",
                "liquidity_regime",
                "sentiment_cycle",
                "capital_co_movement",
                "catalyst_chains",
                "lhb_structure",
            )
        }
        market["deep_analysis"]["lhb_structure"]["status_reason"] = "当日龙虎榜尚未披露"
        with tempfile.TemporaryDirectory() as tmp:
            _, _, _, html_path = self.run_generator(market, tmp)
            html = html_path.read_text(encoding="utf-8")
        self.assertIn("龙虎榜结构", html)
        self.assertIn("证据不足，无法判断", html)
        self.assertIn("UNKNOWN", html)

    def test_rejects_wrong_fund_window_and_reversed_seal_times(self):
        wrong_window = self.deep_market()
        wrong_window["deep_analysis"]["security_details"]["items"][0]["fund_flow_windows"][1]["window"]["trading_days"] = 7
        reversed_time = self.deep_market()
        seal = reversed_time["deep_analysis"]["security_details"]["items"][0]["seal_structure"]
        seal["first_sealed_at"]["value"] = "2026-08-25T14:40:00+08:00"
        seal["last_sealed_at"]["value"] = "2026-08-25T09:40:00+08:00"
        with tempfile.TemporaryDirectory() as tmp:
            first, *_ = self.run_generator(wrong_window, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            second, *_ = self.run_generator(reversed_time, tmp, expected=2)
        self.assertIn("只能是1/3/5/10", first.stderr)
        self.assertIn("首封时间不能晚于末封时间", second.stderr)

    def test_rejects_short_history_hidden_score_and_bad_capital_sum(self):
        history = self.deep_market()
        history["deep_analysis"]["liquidity_regime"]["benchmarks"][0]["history_sample_days"] = 119
        score = self.deep_market()
        score["deep_analysis"]["sentiment_cycle"]["score"] = 15.1
        capital = self.deep_market()
        capital["deep_analysis"]["capital_co_movement"]["groups"][0]["contributions"][0]["fund_flow"]["value"] = 2.6e9
        with tempfile.TemporaryDirectory() as tmp:
            first, *_ = self.run_generator(history, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            second, *_ = self.run_generator(score, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            third, *_ = self.run_generator(capital, tmp, expected=2)
        self.assertIn("history_sample_days 必须不小于120", first.stderr)
        self.assertIn("禁止不可复算的综合情绪分", second.stderr)
        self.assertIn("贡献分解之和必须等于", third.stderr)

    def test_incomplete_contributions_do_not_produce_concentration_or_observation(self):
        market = self.deep_market()
        group = market["deep_analysis"]["capital_co_movement"]["groups"][0]
        group["contributions_complete"] = False
        group["contributions"] = group["contributions"][:1]
        with tempfile.TemporaryDirectory() as tmp:
            _, _, summary_path, html_path = self.run_generator(market, tmp)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            html = html_path.read_text(encoding="utf-8")
        derived_group = summary["derived"]["deep_analysis"]["capital_co_movement"]["groups"][0]
        self.assertIsNone(derived_group["top1_positive_share_pct"])
        self.assertIsNone(derived_group["absolute_hhi"])
        self.assertIsNone(derived_group["opposite_direction_count"])
        self.assertEqual(derived_group["pseudo_sector_status"], "unknown")
        observations = verification_observation_index(
            market["sections"], summary["derived"]
        )
        self.assertIsNone(observations["sector"]["sw-a"]["top1_positive_share_pct"])
        self.assertNotIn(">None<", html)

    def test_joint_board_concentration_does_not_settle_single_board_metric(self):
        market = self.deep_market()
        group = market["deep_analysis"]["capital_co_movement"]["groups"][0]
        group["board_ids"] = ["sw-a", "sw-c"]
        with tempfile.TemporaryDirectory() as tmp:
            _, _, summary_path, _ = self.run_generator(market, tmp)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        observations = verification_observation_index(
            market["sections"], summary["derived"]
        )
        self.assertIsNone(observations["sector"]["sw-a"]["top1_positive_share_pct"])
        self.assertIsNone(observations["sector"]["sw-c"]["top1_positive_share_pct"])

    def test_sentiment_cycle_requires_evidence_and_renders_unknown_as_unknown(self):
        empty = self.deep_market()
        for point in empty["deep_analysis"]["sentiment_cycle"]["points"]:
            point["metrics"] = {}
        partial = self.deep_market()
        cycle = partial["deep_analysis"]["sentiment_cycle"]
        cycle["availability"] = "partial"
        cycle["status_reason"] = "当前涨停家数缺失"
        cycle["points"][-1]["metrics"].pop("limit_up")
        with tempfile.TemporaryDirectory() as tmp:
            first, *_ = self.run_generator(empty, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            _, report_path, summary_path, html_path = self.run_generator(partial, tmp)
            report = report_path.read_text(encoding="utf-8")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            html = html_path.read_text(encoding="utf-8")
        self.assertIn("metrics 不能为空", first.stderr)
        self.assertIsNone(
            summary["derived"]["deep_analysis"]["sentiment_cycle"]["new_window_low_limit_up"]
        )
        self.assertIn("窗口新低：未知", report)
        self.assertIn("新低 未知", html)

    def test_rejects_catalyst_without_counterevidence_and_lhb_intent(self):
        catalyst = self.deep_market()
        catalyst["deep_analysis"]["catalyst_chains"]["items"][0]["counter_evidence"] = []
        lhb = self.deep_market()
        lhb["deep_analysis"]["lhb_structure"]["items"][0]["intent"] = "派发"
        with tempfile.TemporaryDirectory() as tmp:
            first, *_ = self.run_generator(catalyst, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            second, *_ = self.run_generator(lhb, tmp, expected=2)
        self.assertIn("counter_evidence 必须是非空", first.stderr)
        self.assertIn("禁止席位主观意图", second.stderr)

    def test_rejects_invalid_liquidity_thresholds_and_future_lhb_metadata(self):
        threshold = self.deep_market()
        threshold["deep_analysis"]["liquidity_regime"]["thresholds"]["limit_up_min"] = 45.5
        lhb = self.deep_market()
        lhb["deep_analysis"]["lhb_structure"]["published_at"] = "2026-08-26"
        with tempfile.TemporaryDirectory() as tmp:
            first, *_ = self.run_generator(threshold, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            second, *_ = self.run_generator(lhb, tmp, expected=2)
        self.assertIn("limit_up_min 必须是整数", first.stderr)
        self.assertIn("published_at 晚于snapshot.cutoff_at", second.stderr)

    def test_verification_scope_rejects_wrong_metric_and_unknown_subject(self):
        wrong_metric = self.deep_market()
        wrong_metric["verification_points"][0]["subject"] = {
            "scope": "stock",
            "id": "603186",
            "label": "华正新材",
        }
        unknown = self.deep_market()
        unknown["verification_points"][0]["subject"] = {
            "scope": "stock",
            "id": "000000",
            "label": "不存在个股",
        }
        unknown["verification_points"][0]["condition"] = {
            "metric": "streak",
            "operator": ">=",
            "value": 3,
            "unit": "count",
        }
        unknown["verification_points"][0]["title"] = "不存在个股能否达到3连板"
        mismatched_title = self.deep_market()
        mismatched_title["verification_points"][0]["title"] = "超声电子能否完成4板"
        mismatched_entity = self.deep_market()
        mismatched_entity["verification_points"][0]["title"] = "华正新材成交额能否超过100亿元"
        with tempfile.TemporaryDirectory() as tmp:
            first, *_ = self.run_generator(wrong_metric, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            second, *_ = self.run_generator(unknown, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            third, *_ = self.run_generator(mismatched_title, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            fourth, *_ = self.run_generator(mismatched_entity, tmp, expected=2)
        self.assertIn("condition.metric 不受支持", first.stderr)
        self.assertIn("subject.id 未在当前输入中声明", second.stderr)
        self.assertIn("title 与condition.metric语义不一致", third.stderr)
        self.assertIn("title 引用了非subject实体stock:华正新材", fourth.stderr)

    def test_core_entities_cannot_masquerade_as_market_verification(self):
        leader = self.deep_market()
        leader.pop("deep_analysis")
        leader["analysis_mode"] = "core"
        leader["sections"]["sectors"]["items"][0]["leaders"] = [
            {
                "code": "603186",
                "name": "华正新材",
                "change_pct": evidence(10, "percent"),
            }
        ]
        leader["verification_points"][0]["title"] = "华正新材成交额能否超过100亿元"

        index = self.deep_market()
        index.pop("deep_analysis")
        index["analysis_mode"] = "core"
        index["verification_points"][0]["title"] = "沪深300成交额能否超过100亿元"

        primary = self.deep_market()
        primary.pop("deep_analysis")
        primary["analysis_mode"] = "core"
        primary["verification_points"][0]["title"] = "沪深300指数涨跌幅能否为正"
        primary["verification_points"][0]["condition"] = {
            "metric": "primary_index_change_pct",
            "operator": ">",
            "value": 0,
            "unit": "percent",
        }

        with tempfile.TemporaryDirectory() as tmp:
            first, *_ = self.run_generator(leader, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            second, *_ = self.run_generator(index, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            self.run_generator(primary, tmp)
        self.assertIn("title 引用了非subject实体stock:华正新材", first.stderr)
        self.assertIn("title 引用了非subject实体benchmark:沪深300", second.stderr)

    def test_benchmark_aliases_and_nested_names_do_not_false_positive(self):
        alias = self.deep_market()
        index_alias = copy.deepcopy(alias["sections"]["indices"]["items"][1])
        index_alias.update({"id": "sh000688", "name": "科创50", "primary": False})
        alias["sections"]["indices"]["items"].append(index_alias)
        alias["verification_points"][0].update(
            {
                "title": "科创50量比能否达到1.3倍",
                "subject": {"scope": "benchmark", "id": "000688", "label": "科创50"},
                "condition": {
                    "metric": "volume_ratio_5d",
                    "operator": ">=",
                    "value": 1.3,
                    "unit": "ratio",
                },
            }
        )

        etf = copy.deepcopy(alias)
        etf_benchmark = copy.deepcopy(
            etf["deep_analysis"]["liquidity_regime"]["benchmarks"][0]
        )
        etf_benchmark.update({"id": "588000", "name": "科创50ETF", "kind": "etf"})
        etf["deep_analysis"]["liquidity_regime"]["benchmarks"].append(etf_benchmark)
        etf["verification_points"][0]["title"] = "科创50ETF量比能否达到1.3倍"
        etf["verification_points"][0]["subject"] = {
            "scope": "benchmark",
            "id": "588000",
            "label": "科创50ETF",
        }

        wrong = copy.deepcopy(etf)
        wrong["verification_points"][0]["subject"] = {
            "scope": "benchmark",
            "id": "000688",
            "label": "科创50",
        }

        theme = self.deep_market()
        theme["verification_points"][0].update(
            {
                "title": "电子链涨停家数能否达到3只",
                "subject": {
                    "scope": "theme",
                    "id": "electronics-chain",
                    "label": "电子链",
                },
                "condition": {
                    "metric": "limit_up_count",
                    "operator": ">=",
                    "value": 3,
                    "unit": "count",
                },
            }
        )
        wrong_sector = self.deep_market()
        wrong_sector["verification_points"][0].update(
            {
                "title": "电子链涨幅能否为正",
                "subject": {"scope": "sector", "id": "sw-a", "label": "电子"},
                "condition": {
                    "metric": "change_pct",
                    "operator": ">",
                    "value": 0,
                    "unit": "percent",
                },
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            self.run_generator(alias, tmp)
        with tempfile.TemporaryDirectory() as tmp:
            self.run_generator(etf, tmp)
        with tempfile.TemporaryDirectory() as tmp:
            rejected, *_ = self.run_generator(wrong, tmp, expected=2)
        with tempfile.TemporaryDirectory() as tmp:
            self.run_generator(theme, tmp)
        with tempfile.TemporaryDirectory() as tmp:
            rejected_sector, *_ = self.run_generator(wrong_sector, tmp, expected=2)
        self.assertIn("title 引用了非subject实体benchmark:科创50ETF", rejected.stderr)
        self.assertIn("title 引用了非subject实体theme:电子链", rejected_sector.stderr)

    def test_legacy_mismatched_verifications_become_qualitative(self):
        market = self.deep_market()
        market["schema_version"] = "1.2"
        market.pop("deep_analysis")
        market["verification_points"] = [
            {
                "id": "wrong-stock",
                "title": "超声电子能否完成4板",
                "event_date": "2026-08-26",
                "published_at": "2026-08-25",
                "fetched_at": "2026-08-25T16:00:00+08:00",
                "condition": {"metric": "limit_balance", "operator": ">=", "value": 10, "unit": "count"},
                "source": SOURCE,
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            _, _, summary_path, _ = self.run_generator(market, tmp)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        self.assertEqual(summary["resolved_verifications"], [])
        self.assertTrue(
            any("降为定性观察" in item for item in summary["legacy_migration"]["warnings"])
        )

    def test_stock_scoped_verification_resolves_against_same_stock(self):
        prior = self.deep_market()
        prior["analysis_mode"] = "core"
        prior["deep_analysis"] = {
            "security_details": prior["deep_analysis"]["security_details"]
        }
        prior["verification_points"] = [
            {
                "id": "verify-huazheng-streak",
                "title": "华正新材能否达到3连板",
                "event_date": "2026-08-26",
                "published_at": "2026-08-25",
                "fetched_at": "2026-08-25T16:00:00+08:00",
                "subject": {"scope": "stock", "id": "603186", "label": "华正新材"},
                "condition": {"metric": "streak", "operator": ">=", "value": 3, "unit": "count"},
                "source": SOURCE,
            }
        ]
        current = copy.deepcopy(prior)
        current["market_date"] = "2026-08-26"
        current["as_of"] = "2026-08-26"
        current["snapshot"]["cutoff_at"] = "2026-08-26T18:00:00+08:00"
        current["snapshot"]["raw_evidence_sha256"] = "d" * 64
        current["verification_points"] = []
        self.retime(current["sections"], "2026-08-25", "2026-08-26")
        self.retime(current["deep_analysis"], "2026-08-25", "2026-08-26")
        for event in current["sections"]["events"]["items"]:
            event["event_date"] = "2026-08-26"
        current["deep_analysis"]["security_details"]["items"][0]["streak"] = 3

        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history"
            self.run_generator(prior, tmp, history=history)
            _, report_path, summary_path, _ = self.run_generator(
                current, tmp, history=history, as_of="2026-08-26"
            )
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            report = report_path.read_text(encoding="utf-8")

        result = summary["resolved_verifications"][0]
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["subject"]["id"], "603186")
        self.assertEqual(result["observed_value"], 3)
        self.assertIn("stock:华正新材", report)


if __name__ == "__main__":
    unittest.main()
