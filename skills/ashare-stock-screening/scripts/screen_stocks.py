#!/usr/bin/env python3
"""Deterministic screening for normalized A-share evidence records."""

import argparse
import hashlib
import json
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "1.0"
OPERATORS = {"lt", "lte", "gt", "gte", "eq", "ne", "between"}
INDUSTRY_SENSITIVE_METRICS = {
    "current_ratio",
    "debt_ratio",
    "gross_margin",
    "inventory_days",
    "pb",
    "pe_ttm",
    "quick_ratio",
}
METRIC_UNITS = {
    "current_ratio": "ratio",
    "debt_ratio": "percent",
    "dividend_yield": "percent",
    "gross_margin": "percent",
    "inventory_days": "days",
    "market_cap": "CNY",
    "net_margin": "percent",
    "net_profit_growth": "percent",
    "ocf_to_net_profit": "ratio",
    "pb": "multiple",
    "pe_ttm": "multiple",
    "price": "CNY",
    "ps_ttm": "multiple",
    "quick_ratio": "ratio",
    "revenue_growth": "percent",
    "roa_ttm": "percent",
    "roe_ttm": "percent",
}
PERIOD_TYPES = {
    "annual",
    "cumulative_ytd",
    "point_in_time",
    "single_quarter",
    "spot",
    "ttm",
}


class ScreeningError(ValueError):
    """Raised when the screening request or top-level dataset is invalid."""


@dataclass(frozen=True)
class Criterion:
    metric: str
    operator: str
    values: tuple[float, ...]

    def as_dict(self) -> dict[str, Any]:
        value: float | list[float]
        value = self.values[0] if len(self.values) == 1 else list(self.values)
        return {"metric": self.metric, "operator": self.operator, "value": value}


def parse_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ScreeningError(f"{field} 必须是 YYYY-MM-DD") from exc


def parse_number(value: str, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ScreeningError(f"{label} 必须是有限数值") from exc
    if not math.isfinite(number):
        raise ScreeningError(f"{label} 必须是有限数值")
    return number


def parse_criterion(raw: str) -> Criterion:
    parts = raw.split(":", 2)
    if len(parts) != 3 or not parts[0]:
        raise ScreeningError(
            "criterion 格式必须是 metric:operator:value，例如 roe_ttm:gte:15"
        )
    metric, operator, raw_value = parts
    if operator not in OPERATORS:
        raise ScreeningError(
            f"不支持的 operator：{operator}；可用值为 {', '.join(sorted(OPERATORS))}"
        )
    if operator == "between":
        bounds = raw_value.split(",")
        if len(bounds) != 2:
            raise ScreeningError("between 的 value 必须是 lower,upper")
        values = tuple(parse_number(item, metric) for item in bounds)
        if values[0] > values[1]:
            raise ScreeningError("between 下界不能大于上界")
    else:
        values = (parse_number(raw_value, metric),)
    return Criterion(metric=metric, operator=operator, values=values)


def parse_sort(raw: str | None) -> tuple[str, str] | None:
    if raw is None:
        return None
    parts = raw.split(":", 1)
    if len(parts) != 2 or not parts[0] or parts[1] not in {"asc", "desc"}:
        raise ScreeningError("sort 格式必须是 metric:asc 或 metric:desc")
    return parts[0], parts[1]


def load_dataset(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ScreeningError(f"无法读取输入文件：{exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ScreeningError(f"输入不是有效 JSON：{exc}") from exc
    if not isinstance(data, dict):
        raise ScreeningError("输入顶层必须是 JSON object")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ScreeningError(f"schema_version 必须是 {SCHEMA_VERSION}")
    if not isinstance(data.get("universe"), dict):
        raise ScreeningError("universe 必须是 object")
    if not isinstance(data.get("stocks"), list):
        raise ScreeningError("stocks 必须是 array")
    return data, hashlib.sha256(raw).hexdigest()


def validate_stock(stock: Any, index: int) -> None:
    if not isinstance(stock, dict):
        raise ScreeningError(f"stocks[{index}] 必须是 object")
    for field in ("code", "name", "market", "industry"):
        if not isinstance(stock.get(field), str) or not stock[field].strip():
            raise ScreeningError(f"stocks[{index}].{field} 必须是非空字符串")
    if not isinstance(stock.get("metrics"), dict):
        raise ScreeningError(f"stocks[{index}].metrics 必须是 object")


def validate_source(source: Any) -> str | None:
    if not isinstance(source, dict):
        return "source 必须是 object"
    for field in ("id", "name", "url"):
        if not isinstance(source.get(field), str) or not source[field].strip():
            return f"source.{field} 必须是非空字符串"
    parsed_url = urlparse(source["url"])
    is_web = parsed_url.scheme in {"http", "https"} and parsed_url.netloc
    is_local_file = parsed_url.scheme == "file" and parsed_url.path.startswith("/")
    if not (is_web or is_local_file):
        return "source.url 必须是 http(s) URL 或绝对 file URL"
    return None


def validate_universe(universe: dict[str, Any], as_of: date) -> None:
    if not isinstance(universe.get("name"), str) or not universe["name"].strip():
        raise ScreeningError("universe.name 必须是非空字符串")
    members_as_of = parse_date(universe.get("members_as_of"), "universe.members_as_of")
    published_at = parse_date(universe.get("published_at"), "universe.published_at")
    try:
        datetime.fromisoformat(universe.get("fetched_at"))
    except (TypeError, ValueError) as exc:
        raise ScreeningError("universe.fetched_at 必须是 ISO-8601 datetime") from exc
    source_error = validate_source(universe.get("source"))
    if source_error:
        raise ScreeningError(f"universe.{source_error}")
    if members_as_of > as_of:
        raise ScreeningError("universe.members_as_of 不能晚于 as-of")
    if published_at > as_of:
        raise ScreeningError("universe.published_at 不能晚于 as-of")


def validate_evidence(evidence: Any, metric: str) -> tuple[float | None, str | None]:
    if not isinstance(evidence, dict):
        return None, "指标证据必须是 object"
    value = evidence.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, "value 必须是数值"
    value = float(value)
    if not math.isfinite(value):
        return None, "value 必须是有限数值"
    unit = evidence.get("unit")
    if not isinstance(unit, str) or not unit:
        return None, "unit 必须是非空字符串"
    expected_unit = METRIC_UNITS.get(metric)
    if expected_unit and unit != expected_unit:
        return None, f"unit={unit}，但 {metric} 要求 {expected_unit}"
    if evidence.get("period_type") not in PERIOD_TYPES:
        return None, "period_type 不在允许集合内"
    for field in ("observed_at", "published_at"):
        try:
            parse_date(evidence.get(field), field)
        except ScreeningError as exc:
            return None, str(exc)
    try:
        datetime.fromisoformat(evidence.get("fetched_at"))
    except (TypeError, ValueError):
        return None, "fetched_at 必须是 ISO-8601 datetime"
    source_error = validate_source(evidence.get("source"))
    if source_error:
        return None, source_error
    return value, None


def usable_value(
    evidence: Any, metric: str, as_of: date
) -> tuple[float | None, dict[str, Any] | None]:
    value, invalid_reason = validate_evidence(evidence, metric)
    if invalid_reason:
        return None, {
            "metric": metric,
            "reason": "invalid_evidence",
            "detail": invalid_reason,
        }
    published_at = parse_date(evidence["published_at"], "published_at")
    if published_at > as_of:
        return None, {
            "metric": metric,
            "reason": "published_after_as_of",
            "detail": f"published_at={published_at.isoformat()} > as_of={as_of.isoformat()}",
        }
    observed_at = parse_date(evidence["observed_at"], "observed_at")
    if observed_at > as_of:
        return None, {
            "metric": metric,
            "reason": "observed_after_as_of",
            "detail": f"observed_at={observed_at.isoformat()} > as_of={as_of.isoformat()}",
        }
    return value, None


def matches(value: float, criterion: Criterion) -> bool:
    target = criterion.values[0]
    if criterion.operator == "lt":
        return value < target
    if criterion.operator == "lte":
        return value <= target
    if criterion.operator == "gt":
        return value > target
    if criterion.operator == "gte":
        return value >= target
    if criterion.operator == "eq":
        return value == target
    if criterion.operator == "ne":
        return value != target
    return criterion.values[0] <= value <= criterion.values[1]


def evaluate_stock(
    stock: dict[str, Any], criteria: list[Criterion], as_of: date
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    reasons = []
    used_metrics = {}
    matched = []
    for criterion in criteria:
        evidence = stock["metrics"].get(criterion.metric)
        if evidence is None:
            reasons.append(
                {
                    "metric": criterion.metric,
                    "reason": "missing_metric",
                    "detail": "指标不存在，默认缺失策略为排除",
                }
            )
            continue
        value, evidence_reason = usable_value(evidence, criterion.metric, as_of)
        if evidence_reason:
            reasons.append(evidence_reason)
            continue
        if not matches(value, criterion):
            reasons.append(
                {
                    "metric": criterion.metric,
                    "reason": "criterion_not_met",
                    "detail": f"value={value:g}",
                }
            )
            continue
        used_metrics[criterion.metric] = evidence
        matched.append({**criterion.as_dict(), "actual": value})
    identity = {
        key: stock.get(key)
        for key in ("code", "name", "market", "board", "industry")
        if stock.get(key) is not None
    }
    if reasons:
        return None, {**identity, "reasons": reasons}
    return {**identity, "metrics": used_metrics, "matched": matched}, None


def sort_candidates(
    candidates: list[dict[str, Any]],
    stocks_by_code: dict[str, dict[str, Any]],
    sort_spec: tuple[str, str] | None,
    as_of: date,
    warnings: list[dict[str, Any]],
) -> None:
    if sort_spec is None:
        candidates.sort(key=lambda item: item["code"])
        return
    metric, direction = sort_spec
    sort_values = {}
    for candidate in candidates:
        evidence = stocks_by_code[candidate["code"]]["metrics"].get(metric)
        value, reason = usable_value(evidence, metric, as_of) if evidence is not None else (None, None)
        if value is None:
            warnings.append(
                {
                    "code": "sort_metric_unavailable",
                    "stock_code": candidate["code"],
                    "metric": metric,
                    "detail": reason["detail"] if reason else "指标不存在，排在末尾",
                }
            )
        else:
            candidate["metrics"].setdefault(metric, evidence)
        sort_values[candidate["code"]] = value

    def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        value = sort_values[item["code"]]
        if direction == "desc":
            return value is None, -(value or 0), item["code"]
        return value is None, value or 0, item["code"]

    candidates.sort(key=sort_key)


def build_source_summary(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for stock in selected:
        for evidence in stock["metrics"].values():
            source = evidence["source"]
            entry = sources.setdefault(
                source["id"],
                {
                    "id": source["id"],
                    "name": source["name"],
                    "url": source["url"],
                    "metric_count": 0,
                    "stock_codes": set(),
                },
            )
            if (entry["name"], entry["url"]) != (source["name"], source["url"]):
                raise ScreeningError(f"source.id 存在冲突定义：{source['id']}")
            entry["metric_count"] += 1
            entry["stock_codes"].add(stock["code"])
    result = []
    for source_id in sorted(sources):
        entry = sources[source_id]
        result.append(
            {
                **{key: entry[key] for key in ("id", "name", "url", "metric_count")},
                "stock_codes": sorted(entry["stock_codes"]),
            }
        )
    return result


def build_reason_summary(
    excluded: list[dict[str, Any]], reasons: set[str] | None = None
) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str], int] = {}
    for stock in excluded:
        for reason in stock["reasons"]:
            if reasons is not None and reason["reason"] not in reasons:
                continue
            key = reason["metric"], reason["reason"]
            counts[key] = counts.get(key, 0) + 1
    return [
        {"metric": metric, "reason": reason, "count": counts[(metric, reason)]}
        for metric, reason in sorted(counts)
    ]


def screen(
    data: dict[str, Any],
    input_sha256: str,
    criteria: list[Criterion],
    as_of: date,
    sort_spec: tuple[str, str] | None,
    limit: int | None,
) -> dict[str, Any]:
    stocks = data["stocks"]
    validate_universe(data["universe"], as_of)
    for index, stock in enumerate(stocks):
        validate_stock(stock, index)
    warnings = []
    industries = sorted({stock["industry"] for stock in stocks})
    for metric in sorted({item.metric for item in criteria} & INDUSTRY_SENSITIVE_METRICS):
        if len(industries) > 1:
            warnings.append(
                {
                    "code": "industry_sensitive_threshold",
                    "metric": metric,
                    "industries": industries,
                    "detail": "同一阈值跨行业执行；结果必须结合行业口径复核",
                }
            )

    selected = []
    excluded = []
    stocks_by_code = {}
    for stock in stocks:
        if stock["code"] in stocks_by_code:
            raise ScreeningError(f"股票代码重复：{stock['code']}")
        stocks_by_code[stock["code"]] = stock
        candidate, rejected = evaluate_stock(stock, criteria, as_of)
        if candidate:
            selected.append(candidate)
        else:
            excluded.append(rejected)

    sort_candidates(selected, stocks_by_code, sort_spec, as_of, warnings)
    if limit is not None and len(selected) > limit:
        overflow, selected = selected[limit:], selected[:limit]
        excluded.extend(
            {
                **{key: stock.get(key) for key in ("code", "name", "market", "board", "industry")},
                "reasons": [
                    {
                        "metric": sort_spec[0] if sort_spec else "code",
                        "reason": "outside_limit",
                        "detail": f"结果仅保留前 {limit} 项",
                    }
                ],
            }
            for stock in overflow
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "run": {
            "as_of": as_of.isoformat(),
            "input_sha256": input_sha256,
            "universe": data["universe"],
            "criteria": [criterion.as_dict() for criterion in criteria],
            "sort": (
                {"metric": sort_spec[0], "direction": sort_spec[1]}
                if sort_spec
                else {"metric": "code", "direction": "asc"}
            ),
            "limit": limit,
        },
        "counts": {
            "input": len(stocks),
            "selected": len(selected),
            "excluded": len(excluded),
        },
        "warnings": warnings,
        "selected": selected,
        "excluded": excluded,
        "exclusion_summary": build_reason_summary(excluded),
        "missing_summary": build_reason_summary(
            excluded, {"missing_metric", "invalid_evidence"}
        ),
        "source_summary": build_source_summary(selected),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="可审计的 A 股候选股筛选器")
    parser.add_argument("--input", required=True, type=Path, help="规范化 JSON 输入")
    parser.add_argument("--as-of", required=True, help="点时截止日期 YYYY-MM-DD")
    parser.add_argument(
        "--criterion",
        action="append",
        required=True,
        help="可重复：metric:operator:value",
    )
    parser.add_argument("--sort", help="metric:asc 或 metric:desc")
    parser.add_argument("--limit", type=int, help="最多保留多少个候选")
    parser.add_argument("--output", type=Path, help="输出 JSON 文件；默认 stdout")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        as_of = parse_date(args.as_of, "as-of")
        criteria = [parse_criterion(raw) for raw in args.criterion]
        sort_spec = parse_sort(args.sort)
        if args.limit is not None and args.limit < 1:
            raise ScreeningError("limit 必须大于 0")
        data, digest = load_dataset(args.input)
        result = screen(data, digest, criteria, as_of, sort_spec, args.limit)
    except ScreeningError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    output = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        try:
            args.output.write_text(output, encoding="utf-8")
        except OSError as exc:
            print(f"错误：无法写入输出文件：{exc}", file=sys.stderr)
            return 2
    else:
        sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
