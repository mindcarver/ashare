#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输入读取与全部不可变契约校验。

拆分自 research_journal.py（沿用 P2-5 纪律）。只做校验，不落库、不渲染。
"""

import json
import math

from datetime import date
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from schema import (
    CRITERION_METRICS,
    JournalError,
    MARKET_METRICS,
    OPERATORS,
    SCHEMA_VERSION,
    parse_date,
    require_text,
)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise JournalError(f"无法读取输入：{exc}") from exc
    except json.JSONDecodeError as exc:
        raise JournalError(f"输入不是有效JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise JournalError("输入顶层必须是object")
    return value


def validate_source(source: Any, field: str) -> None:
    if not isinstance(source, dict):
        raise JournalError(f"{field}.source 必须是object")
    for key in ("id", "name", "url"):
        if not isinstance(source.get(key), str) or not source[key].strip():
            raise JournalError(f"{field}.source.{key} 必须是非空字符串")
    parsed = urlparse(source["url"])
    is_web = parsed.scheme in {"http", "https"} and parsed.netloc
    is_file = parsed.scheme == "file" and parsed.path.startswith("/")
    if not (is_web or is_file):
        raise JournalError(f"{field}.source.url 必须是http(s)或绝对file URL")


def validate_evidence(
    evidence: Any,
    field: str,
    cutoff: date,
    require_value: bool = True,
) -> None:
    if not isinstance(evidence, dict):
        raise JournalError(f"{field} 必须是object")
    if require_value:
        raw_value = evidence.get("value")
        if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
            raise JournalError(f"{field}.value 必须是数值")
        if not math.isfinite(float(raw_value)) or float(raw_value) <= 0:
            raise JournalError(f"{field}.value 必须是正的有限数值")
        require_text(evidence, "unit")
    observed_at = parse_date(evidence.get("observed_at"), f"{field}.observed_at")
    published_at = parse_date(evidence.get("published_at"), f"{field}.published_at")
    if observed_at > cutoff:
        raise JournalError(f"{field}.observed_at 晚于截止日期")
    if published_at > cutoff:
        raise JournalError(f"{field}.published_at 晚于 as_of")
    try:
        datetime.fromisoformat(evidence.get("fetched_at"))
    except (TypeError, ValueError) as exc:
        raise JournalError(f"{field}.fetched_at 必须是ISO-8601 datetime") from exc
    validate_source(evidence.get("source"), field)


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise JournalError(f"schema_version 必须是{SCHEMA_VERSION}")
    for field in (
        "research_id",
        "code",
        "name",
        "market",
        "horizon_label",
        "thesis",
    ):
        require_text(snapshot, field)
    as_of = parse_date(snapshot.get("as_of"), "as_of")
    evaluation_date = parse_date(snapshot.get("evaluation_date"), "evaluation_date")
    if evaluation_date < as_of:
        raise JournalError("evaluation_date 不能早于 as_of")

    probability = snapshot.get("probability")
    if probability is not None:
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise JournalError("probability 必须是0到1数值")
        if not 0 <= float(probability) <= 1:
            raise JournalError("probability 必须在0到1之间")

    criterion = snapshot.get("criterion")
    if not isinstance(criterion, dict):
        raise JournalError("criterion 必须是object")
    if criterion.get("metric") not in CRITERION_METRICS:
        raise JournalError("criterion.metric 不受支持")
    if criterion.get("operator") not in OPERATORS:
        raise JournalError("criterion.operator 不受支持")
    raw_target = criterion.get("value")
    if isinstance(raw_target, bool) or not isinstance(raw_target, (int, float)):
        raise JournalError("criterion.value 必须是有限数值")
    if not math.isfinite(float(raw_target)):
        raise JournalError("criterion.value 必须是有限数值")

    baseline = snapshot.get("baseline")
    if not isinstance(baseline, dict) or "stock" not in baseline:
        raise JournalError("baseline.stock 必填")
    validate_evidence(baseline["stock"], "baseline.stock", as_of)
    if criterion["metric"] in {"benchmark_return_pct", "excess_return_pct"}:
        if "benchmark" not in baseline:
            raise JournalError("该criterion要求baseline.benchmark")
    if "benchmark" in baseline:
        require_text(snapshot, "benchmark_code")
        validate_evidence(baseline["benchmark"], "baseline.benchmark", as_of)

    for field in ("catalysts", "falsifiers"):
        items = snapshot.get(field)
        if not isinstance(items, list) or not all(
            isinstance(item, str) and item.strip() for item in items
        ):
            raise JournalError(f"{field} 必须是非空字符串数组")
    evidence_items = snapshot.get("evidence")
    if not isinstance(evidence_items, list):
        raise JournalError("evidence 必须是数组")
    for index, item in enumerate(evidence_items):
        if not isinstance(item, dict):
            raise JournalError(f"evidence[{index}] 必须是object")
        require_text(item, "claim")
        validate_evidence(item, f"evidence[{index}]", as_of, require_value=False)


def validate_path(
    path: Any,
    field: str,
    evaluation_date: date,
    baseline: dict[str, Any],
) -> list[dict[str, Any]]:
    if not isinstance(path, list) or len(path) < 2:
        raise JournalError(f"{field} 至少需要两个价格点")
    dates = []
    for index, point in enumerate(path):
        point_date = parse_date(
            point.get("observed_at") if isinstance(point, dict) else None,
            f"{field}[{index}].observed_at",
        )
        if point_date > evaluation_date:
            raise JournalError("价格路径超出 evaluation_date")
        validate_evidence(point, f"{field}[{index}]", evaluation_date)
        dates.append(point_date)
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise JournalError(f"{field} 日期必须严格递增")
    baseline_date = parse_date(baseline["observed_at"], "baseline.observed_at")
    if dates[0] != baseline_date:
        raise JournalError(f"{field} 首个日期必须等于基线观察日")
    if not math.isclose(float(path[0]["value"]), float(baseline["value"])):
        raise JournalError(f"{field} 首个价格必须等于基线价格")
    if path[0]["unit"] != baseline["unit"]:
        raise JournalError(f"{field} 单位必须与基线一致")
    return path


def validate_outcome(
    outcome: dict[str, Any],
    snapshot: dict[str, Any],
    review_as_of: date,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]] | None]:
    if outcome.get("schema_version") != SCHEMA_VERSION:
        raise JournalError(f"schema_version 必须是{SCHEMA_VERSION}")
    if outcome.get("research_id") != snapshot["research_id"]:
        raise JournalError("outcome.research_id 与快照不一致")
    if outcome.get("evaluation_date") != snapshot["evaluation_date"]:
        raise JournalError("outcome.evaluation_date 与快照不一致")
    evaluation_date = parse_date(snapshot["evaluation_date"], "evaluation_date")
    if review_as_of < evaluation_date:
        raise JournalError("尚未到 evaluation_date，不能提前评分")
    baseline = snapshot["baseline"]
    stock_path = validate_path(
        outcome.get("stock_path"), "stock_path", evaluation_date, baseline["stock"]
    )
    benchmark_path = None
    if "benchmark" in baseline:
        benchmark_path = validate_path(
            outcome.get("benchmark_path"),
            "benchmark_path",
            evaluation_date,
            baseline["benchmark"],
        )
    falsifiers = outcome.get("falsifiers_triggered", [])
    if not isinstance(falsifiers, list) or not all(isinstance(item, str) for item in falsifiers):
        raise JournalError("falsifiers_triggered 必须是字符串数组")
    unknown_falsifiers = sorted(set(falsifiers) - set(snapshot["falsifiers"]))
    if unknown_falsifiers:
        raise JournalError(
            "falsifiers_triggered 包含快照未定义项：" + ", ".join(unknown_falsifiers)
        )
    return stock_path, benchmark_path


# ============ 市场级记录（无价格路径） ============

def validate_market_evidence(
    evidence: Any,
    field: str,
    cutoff: date,
    unit: str | None = None,
) -> str:
    """市场级指标证据。与价格证据的区别：数值允许为 0 或负数（如涨停净差）。

    返回该证据声明的 metric，便于调用方核对单位与去重。
    """
    if not isinstance(evidence, dict):
        raise JournalError(f"{field} 必须是object")
    metric = evidence.get("metric")
    if metric not in MARKET_METRICS:
        raise JournalError(f"{field}.metric 不受支持")
    expected_unit = MARKET_METRICS[metric]
    if evidence.get("unit") != expected_unit:
        raise JournalError(
            f"{field}.unit 必须是{expected_unit}（{metric} 的固定单位）"
        )
    if unit is not None and unit != expected_unit:
        raise JournalError(f"{field}.unit 与criterion.metric的单位不一致")
    raw_value = evidence.get("value")
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise JournalError(f"{field}.value 必须是数值")
    if not math.isfinite(float(raw_value)):
        raise JournalError(f"{field}.value 必须是有限数值")
    observed_at = parse_date(evidence.get("observed_at"), f"{field}.observed_at")
    published_at = parse_date(evidence.get("published_at"), f"{field}.published_at")
    if observed_at > cutoff:
        raise JournalError(f"{field}.observed_at 晚于评价日")
    if published_at > cutoff:
        raise JournalError(f"{field}.published_at 晚于评价日")
    try:
        datetime.fromisoformat(evidence.get("fetched_at"))
    except (TypeError, ValueError) as exc:
        raise JournalError(f"{field}.fetched_at 必须是ISO-8601 datetime") from exc
    validate_source(evidence.get("source"), field)
    return metric


def validate_market_snapshot(snapshot: dict[str, Any]) -> None:
    """冻结的市场级研究快照。没有 baseline / 价格，研究对象是「盘面」而非个股。"""
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise JournalError(f"schema_version 必须是{SCHEMA_VERSION}")
    for field in ("research_id", "subject", "market", "horizon_label", "thesis"):
        require_text(snapshot, field)
    if "code" in snapshot or "name" in snapshot or "baseline" in snapshot:
        raise JournalError(
            "市场级快照不得包含 code/name/baseline；个股价格路径请用 record"
        )
    as_of = parse_date(snapshot.get("as_of"), "as_of")
    evaluation_date = parse_date(snapshot.get("evaluation_date"), "evaluation_date")
    if evaluation_date < as_of:
        raise JournalError("evaluation_date 不能早于 as_of")

    probability = snapshot.get("probability")
    if probability is not None:
        if isinstance(probability, bool) or not isinstance(probability, (int, float)):
            raise JournalError("probability 必须是0到1数值")
        if not 0 <= float(probability) <= 1:
            raise JournalError("probability 必须在0到1之间")

    criterion = snapshot.get("criterion")
    if not isinstance(criterion, dict):
        raise JournalError("criterion 必须是object")
    if criterion.get("metric") not in MARKET_METRICS:
        raise JournalError("criterion.metric 不受支持（市场级指标见 MARKET_METRICS）")
    if criterion.get("operator") not in OPERATORS:
        raise JournalError("criterion.operator 不受支持")
    raw_target = criterion.get("value")
    if isinstance(raw_target, bool) or not isinstance(raw_target, (int, float)):
        raise JournalError("criterion.value 必须是有限数值")
    if not math.isfinite(float(raw_target)):
        raise JournalError("criterion.value 必须是有限数值")

    for field in ("catalysts", "falsifiers"):
        items = snapshot.get(field)
        if not isinstance(items, list) or not all(
            isinstance(item, str) and item.strip() for item in items
        ):
            raise JournalError(f"{field} 必须是非空字符串数组")
    evidence_items = snapshot.get("evidence")
    if not isinstance(evidence_items, list):
        raise JournalError("evidence 必须是数组")
    for index, item in enumerate(evidence_items):
        if not isinstance(item, dict):
            raise JournalError(f"evidence[{index}] 必须是object")
        require_text(item, "claim")
        observed = parse_date(item.get("observed_at"), f"evidence[{index}].observed_at")
        published = parse_date(
            item.get("published_at"), f"evidence[{index}].published_at"
        )
        if observed > as_of or published > as_of:
            raise JournalError(f"evidence[{index}] 的时间晚于 as_of")
        try:
            datetime.fromisoformat(item.get("fetched_at"))
        except (TypeError, ValueError) as exc:
            raise JournalError(
                f"evidence[{index}].fetched_at 必须是ISO-8601 datetime"
            ) from exc
        validate_source(item.get("source"), f"evidence[{index}]")


def validate_market_outcome(
    outcome: dict[str, Any],
    snapshot: dict[str, Any],
    review_as_of: date,
) -> list[dict[str, Any]]:
    if outcome.get("schema_version") != SCHEMA_VERSION:
        raise JournalError(f"schema_version 必须是{SCHEMA_VERSION}")
    if outcome.get("research_id") != snapshot["research_id"]:
        raise JournalError("outcome.research_id 与快照不一致")
    if outcome.get("evaluation_date") != snapshot["evaluation_date"]:
        raise JournalError("outcome.evaluation_date 与快照不一致")
    evaluation_date = parse_date(snapshot["evaluation_date"], "evaluation_date")
    if review_as_of < evaluation_date:
        raise JournalError("尚未到 evaluation_date，不能提前评分")
    if "stock_path" in outcome or "benchmark_path" in outcome:
        raise JournalError("市场级结果不得包含 stock_path/benchmark_path；请用 market_metrics")
    metrics = outcome.get("market_metrics")
    if not isinstance(metrics, list) or not metrics:
        raise JournalError("market_metrics 必须是非空数组")
    criterion_unit = MARKET_METRICS[snapshot["criterion"]["metric"]]
    seen: set[str] = set()
    for index, item in enumerate(metrics):
        metric = validate_market_evidence(
            item, f"market_metrics[{index}]", evaluation_date, criterion_unit
        )
        if metric in seen:
            raise JournalError(f"market_metrics 中 {metric} 重复")
        seen.add(metric)
    if snapshot["criterion"]["metric"] not in seen:
        raise JournalError(
            "market_metrics 缺少criterion.metric："
            + snapshot["criterion"]["metric"]
        )
    falsifiers = outcome.get("falsifiers_triggered", [])
    if not isinstance(falsifiers, list) or not all(
        isinstance(item, str) for item in falsifiers
    ):
        raise JournalError("falsifiers_triggered 必须是字符串数组")
    unknown_falsifiers = sorted(set(falsifiers) - set(snapshot["falsifiers"]))
    if unknown_falsifiers:
        raise JournalError(
            "falsifiers_triggered 包含快照未定义项：" + ", ".join(unknown_falsifiers)
        )
    return metrics
