#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从已校验的市场证据派生判读、历史序列与验证点。

拆分自 generate_daily_review.py（审计 P2-5）。不读模块级可变状态、不渲染。
"""

import hashlib
import json

from pathlib import Path
from typing import Any

from analysis import (
    derive_concept_flows,
    derive_high_boards,
    derive_mainline_matrix,
    derive_prev_pool_performance,
    derive_sector_leaders,
    derive_sentiment_health_check,
    derive_streak_distribution,
    mainline_signals,
    prev_pool_signal,
)
from schema import ReviewError, VERIFICATION_UNITS, parse_date, require_text, value
from validate import normalized_sections, upgrade_legacy_input, validate_input


def derive_short_term_sentiment(
    sections: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    sentiment = sections["short_term_sentiment"]
    breadth = sections["breadth"]
    if sentiment["availability"] != "available":
        return {
            "state": "unknown",
            "reason": sentiment["status_reason"],
        }
    if breadth["availability"] != "available":
        return {
            "state": "unknown",
            "reason": "涨跌停宽度数据不可得，不能分类短线情绪",
        }

    limit_up = value(breadth, "limit_up")
    limit_down = value(breadth, "limit_down")
    failed = value(sentiment, "open_board_failed")
    attempts = value(sentiment, "limit_attempts")
    highest_streak = value(sentiment, "highest_streak")
    if None in (limit_up, limit_down, failed, attempts, highest_streak):
        return {
            "state": "unknown",
            "reason": "短线情绪必需指标不完整",
        }

    open_board_rate = round(failed / attempts * 100, 6)
    result: dict[str, Any] = {
        "open_board_rate_pct": open_board_rate,
        "repair_evaluated": False,
        "previous_metrics_available": sentiment.get("previous_metrics") is not None,
    }
    if limit_up < 20 and limit_down > 10 and highest_streak < 3:
        result.update(
            {
                "state": "ice",
                "rule": "limit_up < 20 and limit_down > 10 and highest_streak < 3",
                "evidence": f"涨停 {limit_up:.0f}，跌停 {limit_down:.0f}，最高连板 {highest_streak:.0f}",
            }
        )
        return result
    if limit_up > 80 and open_board_rate < 15 and highest_streak > 5:
        result.update(
            {
                "state": "euphoria",
                "rule": "limit_up > 80 and open_board_rate_pct < 15 and highest_streak > 5",
                "evidence": f"涨停 {limit_up:.0f}，炸板率 {open_board_rate:.2f}%，最高连板 {highest_streak:.0f}",
            }
        )
        return result
    if open_board_rate > 25:
        result.update(
            {
                "state": "divergence",
                "rule": "open_board_rate_pct > 25 and not (ice or euphoria)",
                "evidence": f"炸板率 {open_board_rate:.2f}%",
            }
        )
        return result

    previous = sentiment.get("previous_metrics")
    if previous is not None:
        previous_failed = float(previous["open_board_failed"]["value"])
        previous_attempts = float(previous["limit_attempts"]["value"])
        previous_rate = round(previous_failed / previous_attempts * 100, 6)
        previous_limit_up = float(previous["limit_up"]["value"])
        previous_limit_down = float(previous["limit_down"]["value"])
        previous_streak = float(previous["highest_streak"]["value"])
        result["repair_evaluated"] = True
        result["previous_open_board_rate_pct"] = previous_rate
        if (
            limit_up > previous_limit_up
            and limit_down < previous_limit_down
            and open_board_rate < previous_rate
            and highest_streak >= previous_streak
        ):
            result.update(
                {
                    "state": "repair",
                    "rule": "limit_up > previous_limit_up and limit_down < previous_limit_down and open_board_rate_pct < previous_open_board_rate_pct and highest_streak >= previous_highest_streak",
                    "evidence": (
                        f"涨停 {previous_limit_up:.0f}→{limit_up:.0f}，"
                        f"跌停 {previous_limit_down:.0f}→{limit_down:.0f}，"
                        f"炸板率 {previous_rate:.2f}%→{open_board_rate:.2f}%，"
                        f"最高连板 {previous_streak:.0f}→{highest_streak:.0f}"
                    ),
                }
            )
            return result

    result.update(
        {
            "state": "neutral",
            "rule": "no_predefined_state_triggered",
            "evidence": "当前数据完整但未触发预定义状态",
        }
    )
    return result


def derive(
    sections: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    derived: dict[str, Any] = {}
    signals: list[dict[str, str]] = []
    breadth = sections["breadth"]
    advances = value(breadth, "advancers")
    declines = value(breadth, "decliners")
    unchanged = value(breadth, "unchanged")
    if advances is not None and declines is not None and unchanged is not None:
        total = advances + declines + unchanged
        if total <= 0:
            raise ReviewError("上涨/下跌/平盘家数分母必须大于0")
        derived["advancer_share_pct"] = round(advances / total * 100, 6)
        derived["advance_decline_ratio"] = (
            round(advances / declines, 6) if declines > 0 else None
        )
    limit_up = value(breadth, "limit_up")
    limit_down = value(breadth, "limit_down")
    if limit_up is not None and limit_down is not None:
        derived["limit_balance"] = limit_up - limit_down
    derived["short_term_sentiment"] = derive_short_term_sentiment(sections)

    turnover = sections["turnover"]
    amount = value(turnover, "amount")
    previous = value(turnover, "previous_amount")
    average_5d = value(turnover, "avg_5d_amount")
    if amount is not None:
        derived["turnover_amount"] = amount
    if amount is not None and previous:
        derived["turnover_vs_previous_pct"] = round((amount / previous - 1) * 100, 6)
    if amount is not None and average_5d:
        derived["turnover_vs_5d_avg_pct"] = round((amount / average_5d - 1) * 100, 6)

    indices = sections["indices"].get("items", [])
    if indices:
        primary = next(item for item in indices if item["primary"])
        primary_change = float(primary["change_pct"]["value"])
        derived["primary_index"] = primary["name"]
        derived["primary_index_change_pct"] = primary_change
        if primary_change > 0 and derived.get("advancer_share_pct", 100) < 40:
            signals.append(
                {
                    "code": "index_up_breadth_narrow",
                    "label": "指数上涨但宽度偏窄",
                    "rule": "primary_index_change_pct > 0 and advancer_share_pct < 40",
                    "evidence": f"{primary['name']} {primary_change:+.2f}%，上涨家数占比 {derived['advancer_share_pct']:.2f}%",
                }
            )
        if primary_change < 0 and derived.get("advancer_share_pct", 0) > 60:
            signals.append(
                {
                    "code": "index_down_breadth_resilient",
                    "label": "指数下跌但宽度仍有韧性",
                    "rule": "primary_index_change_pct < 0 and advancer_share_pct > 60",
                    "evidence": f"{primary['name']} {primary_change:+.2f}%，上涨家数占比 {derived['advancer_share_pct']:.2f}%",
                }
            )

    sector_items = sections["sectors"].get("items", [])
    if sector_items:
        ordered = sorted(
            sector_items,
            key=lambda item: (-float(item["change_pct"]["value"]), item["id"]),
        )
        derived["leading_sector"] = ordered[0]["name"]
        derived["lagging_sector"] = ordered[-1]["name"]

    # 1.2 分析语义层：章节缺失时完全不产生新键，保证旧输入的报告与摘要逐字节不变。
    prev_pool = derive_prev_pool_performance(sections)
    if prev_pool is not None:
        derived["prev_pool_performance"] = prev_pool
        signals.extend(prev_pool_signal(prev_pool))
    mainline = derive_mainline_matrix(sections)
    if mainline is not None:
        derived["mainline_matrix"] = mainline
        signals.extend(mainline_signals(mainline))
    health_check = derive_sentiment_health_check(sections, derived)
    if health_check is not None:
        derived["sentiment_health_check"] = health_check

    # 1.2 发布后追加的四项可选结构（个股颗粒度）。与上面同一条纪律：
    # 结构缺省时**不产生任何新键**，旧输入的报告与摘要保持逐字节不变。
    ladder = derive_streak_distribution(sections)
    if ladder is not None:
        derived["streak_distribution"] = ladder
    high_boards = derive_high_boards(sections)
    if high_boards is not None:
        derived["high_board_quality"] = high_boards
    concepts = derive_concept_flows(sections)
    if concepts is not None:
        derived["concept_flows"] = concepts
    leaders = derive_sector_leaders(sections)
    if leaders is not None:
        derived["sector_leaders"] = leaders
    return derived, signals


def load_history_entries(history_dir: Path) -> list[dict[str, Any]]:
    if not history_dir.exists():
        return []
    entries = []
    for path in sorted(history_dir.glob("*/*.json")):
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReviewError(f"历史快照不可读：{path}: {exc}") from exc
        if not isinstance(envelope, dict) or not isinstance(envelope.get("snapshot"), dict):
            raise ReviewError(f"历史快照格式无效：{path}")
        input_sha = envelope.get("input_sha256")
        if not isinstance(input_sha, str) or len(input_sha) != 64:
            raise ReviewError(f"历史快照缺少input_sha256：{path}")
        expected_content_sha = envelope.get("snapshot_content_sha256")
        actual_content_sha = hashlib.sha256(
            json.dumps(
                envelope["snapshot"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if expected_content_sha != actual_content_sha:
            raise ReviewError(f"历史快照内容SHA不匹配：{path}")
        snapshot_as_of = parse_date(envelope["snapshot"].get("as_of"), "history.as_of")
        # 历史快照按写入时的版本落盘；读取时先走同一条升级链，保证旧版本历史
        # （1.0/1.1）不会被新版本契约拒收，也保证跨版本比较使用同一套字段语义。
        restored = upgrade_legacy_input(envelope["snapshot"], input_sha)
        validate_input(restored, snapshot_as_of)
        entries.append(
            {"path": path, "input_sha256": input_sha, "data": restored}
        )
    return entries


def latest_daily_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        data = entry["data"]
        market_date = require_text(data, "market_date")
        revision = data.get("snapshot", {}).get("revision")
        if not isinstance(revision, int):
            raise ReviewError(f"历史快照revision无效：{entry['path']}")
        current = latest.get(market_date)
        if current is None or revision > current["data"]["snapshot"]["revision"]:
            latest[market_date] = entry
    return [latest[key] for key in sorted(latest)]


def persist_snapshot(
    history_dir: Path,
    data: dict[str, Any],
    input_sha256: str,
    entries: list[dict[str, Any]],
) -> tuple[Path, bool]:
    duplicate = next(
        (entry for entry in entries if entry["input_sha256"] == input_sha256), None
    )
    if duplicate:
        return duplicate["path"], False

    market_date = data["market_date"]
    same_day = sorted(
        (entry for entry in entries if entry["data"]["market_date"] == market_date),
        key=lambda entry: entry["data"]["snapshot"]["revision"],
    )
    revision = data["snapshot"]["revision"]
    if same_day:
        latest = same_day[-1]
        expected_revision = latest["data"]["snapshot"]["revision"] + 1
        if revision != expected_revision:
            raise ReviewError(f"同日新修订revision必须是{expected_revision}")
        if data["snapshot"]["supersedes_sha256"] != latest["input_sha256"]:
            raise ReviewError("supersedes_sha256 必须指向同日上一修订")
    elif revision != 1:
        raise ReviewError("历史中没有同日旧快照时revision必须是1")

    target = history_dir / market_date / f"r{revision:03d}-{input_sha256[:12]}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    content_sha = hashlib.sha256(
        json.dumps(
            data, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    envelope = {
        "input_sha256": input_sha256,
        "snapshot_content_sha256": content_sha,
        "snapshot": data,
    }
    target.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target, True


def percentile_rank(numbers: list[float], current: float) -> float:
    return round(sum(number <= current for number in numbers) / len(numbers) * 100, 6)


def history_metric_values(
    sections: dict[str, dict[str, Any]], derived: dict[str, Any]
) -> dict[str, float | None]:
    sentiment = derived.get("short_term_sentiment", {})
    metrics: dict[str, float | None] = {
        "primary_index_change_pct": derived.get("primary_index_change_pct"),
        "advancer_share_pct": derived.get("advancer_share_pct"),
        "turnover_amount": derived.get("turnover_amount"),
        "turnover_vs_previous_pct": derived.get("turnover_vs_previous_pct"),
        "open_board_rate_pct": sentiment.get("open_board_rate_pct"),
        "limit_balance": derived.get("limit_balance"),
    }
    # 晋级率来自延续性检验章节：该章节缺失时不产生新键，旧输入的报告与摘要保持逐字节不变。
    # 有了这一项，以 promotion_rate_pct 为条件的验证点才能在 event_date 当天自动结算。
    prev_pool = derived.get("prev_pool_performance")
    if prev_pool is not None:
        metrics["promotion_rate_pct"] = prev_pool.get("promotion_rate_pct")
    return metrics


def derive_history(
    entries: list[dict[str, Any]],
    data: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    derived: dict[str, Any],
) -> dict[str, Any]:
    prior_daily = [
        entry
        for entry in latest_daily_entries(entries)
        if entry["data"]["market_date"] < data["market_date"]
    ]
    series: list[dict[str, Any]] = []
    states: list[str] = []
    for entry in prior_daily:
        prior_sections = normalized_sections(entry["data"])
        prior_derived, _ = derive(prior_sections)
        series.append(
            {
                "market_date": entry["data"]["market_date"],
                "metrics": history_metric_values(prior_sections, prior_derived),
            }
        )
        states.append(prior_derived["short_term_sentiment"]["state"])
    current_metrics = history_metric_values(sections, derived)
    series.append({"market_date": data["market_date"], "metrics": current_metrics})

    previous = series[-2] if len(series) > 1 else None
    metric_summary: dict[str, Any] = {}
    for name, current in current_metrics.items():
        prior = previous["metrics"].get(name) if previous else None
        item = {
            "unit": VERIFICATION_UNITS[name],
            "current": current,
            "previous": prior,
            "change": round(current - prior, 6)
            if current is not None and prior is not None
            else None,
            "percentile_20d": None,
            "percentile_60d": None,
        }
        for window in (20, 60):
            values = [
                float(row["metrics"][name])
                for row in series[-window:]
                if row["metrics"].get(name) is not None
            ]
            if current is not None and len(values) >= window:
                item[f"percentile_{window}d"] = percentile_rank(values, float(current))
        metric_summary[name] = item

    current_state = derived["short_term_sentiment"]["state"]
    streak = None
    if current_state != "unknown":
        streak = 0
        for state in reversed(states + [current_state]):
            if state != current_state:
                break
            streak += 1
    return {
        "sample_size": len(series),
        "previous_market_date": previous["market_date"] if previous else None,
        "metrics": metric_summary,
        "sentiment_state_streak": streak,
    }


def verification_metric_value(
    metric: str, sections: dict[str, dict[str, Any]], derived: dict[str, Any]
) -> float | None:
    return history_metric_values(sections, derived).get(metric)


def resolve_verification_points(
    entries: list[dict[str, Any]],
    data: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    derived: dict[str, Any],
) -> list[dict[str, Any]]:
    prior = [
        entry
        for entry in latest_daily_entries(entries)
        if entry["data"]["market_date"] < data["market_date"]
    ]
    if not prior:
        return []
    previous_market_date = prior[-1]["data"]["market_date"]
    points: dict[str, dict[str, Any]] = {}
    for entry in prior:
        for point in entry["data"].get("verification_points", []):
            points[point["id"]] = point
    results = []
    operations = {
        ">": lambda observed, target: observed > target,
        ">=": lambda observed, target: observed >= target,
        "<": lambda observed, target: observed < target,
        "<=": lambda observed, target: observed <= target,
        "==": lambda observed, target: observed == target,
    }
    for point in points.values():
        if not (previous_market_date < point["event_date"] <= data["market_date"]):
            continue
        condition = point["condition"]
        observed = verification_metric_value(condition["metric"], sections, derived)
        status = "unknown"
        if observed is not None:
            status = (
                "passed"
                if operations[condition["operator"]](observed, float(condition["value"]))
                else "failed"
            )
        results.append(
            {
                "id": point["id"],
                "title": point["title"],
                "due_date": point["event_date"],
                "status": status,
                "condition": condition,
                "observed_value": observed,
                "observed_market_date": data["market_date"],
            }
        )
    return results


def coverage(sections: dict[str, dict[str, Any]]) -> dict[str, int]:
    return {
        status: sum(section["availability"] == status for section in sections.values())
        for status in ("available", "partial", "unknown")
    }


def iter_sources(data: Any):
    if isinstance(data, dict):
        if {"id", "name"} <= set(data) and (
            data.get("kind") == "derived" or "url" in data
        ):
            yield data
        for child in data.values():
            yield from iter_sources(child)
    elif isinstance(data, list):
        for child in data:
            yield from iter_sources(child)


def source_summary(data: dict[str, Any]) -> list[dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for source in iter_sources(data):
        current = sources.setdefault(
            source["id"],
            {
                "id": source["id"],
                "name": source["name"],
                "url": source.get("url"),
                "kind": source.get("kind", "external"),
                "count": 0,
            },
        )
        if (current["name"], current["url"], current["kind"]) != (
            source["name"],
            source.get("url"),
            source.get("kind", "external"),
        ):
            raise ReviewError(f"source.id存在冲突：{source['id']}")
        current["count"] += 1
    return [sources[key] for key in sorted(sources)]
