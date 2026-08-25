#!/usr/bin/env python3
"""Generate an auditable A-share daily market review from normalized evidence."""

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA_VERSION = "1.0"
SECTION_NAMES = (
    "indices",
    "breadth",
    "turnover",
    "sectors",
    "funds",
    "style",
    "events",
)
AVAILABILITY = {"available", "partial", "unknown"}
FORBIDDEN = (
    "建议买入",
    "建议卖出",
    "目标价",
    "目标仓位",
    "确定牛市",
    "确定熊市",
    "必然上涨",
    "必然下跌",
)


class ReviewError(ValueError):
    """Raised when market evidence violates the daily review contract."""


def load_input(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ReviewError(f"无法读取输入：{exc}") from exc
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReviewError(f"输入不是有效JSON：{exc}") from exc
    if not isinstance(value, dict):
        raise ReviewError("输入顶层必须是object")
    return value, hashlib.sha256(raw).hexdigest()


def parse_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ReviewError(f"{field} 必须是YYYY-MM-DD") from exc


def require_text(value: dict[str, Any], field: str, prefix: str = "") -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        name = f"{prefix}.{field}" if prefix else field
        raise ReviewError(f"{name} 必须是非空字符串")
    return result


def validate_source(source: Any, field: str) -> None:
    if not isinstance(source, dict):
        raise ReviewError(f"{field}.source 必须是object")
    for key in ("id", "name", "url"):
        if not isinstance(source.get(key), str) or not source[key].strip():
            raise ReviewError(f"{field}.source.{key} 必须是非空字符串")
    parsed = urlparse(source["url"])
    is_web = parsed.scheme in {"http", "https"} and parsed.netloc
    is_file = parsed.scheme == "file" and parsed.path.startswith("/")
    if not (is_web or is_file):
        raise ReviewError(f"{field}.source.url 必须是http(s)或绝对file URL")


def validate_evidence(
    evidence: Any,
    field: str,
    as_of: date,
    expected_unit: str | None = None,
    value_constraint: str = "any",
) -> None:
    if not isinstance(evidence, dict):
        raise ReviewError(f"{field} 必须是object")
    raw_value = evidence.get("value")
    if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
        raise ReviewError(f"{field}.value 必须是数值")
    number = float(raw_value)
    if not math.isfinite(number):
        raise ReviewError(f"{field}.value 必须是有限数值")
    if expected_unit == "count" and not number.is_integer():
        raise ReviewError(f"{field}.value 使用count时必须是整数")
    if value_constraint == "positive" and number <= 0:
        raise ReviewError(f"{field}.value 必须是正的有限数值")
    if value_constraint == "nonnegative" and number < 0:
        raise ReviewError(f"{field}.value 必须是非负的有限数值")
    unit = require_text(evidence, "unit", field)
    if expected_unit and unit != expected_unit:
        raise ReviewError(f"{field}.unit 必须是{expected_unit}")
    observed_at = parse_date(evidence.get("observed_at"), f"{field}.observed_at")
    published_at = parse_date(evidence.get("published_at"), f"{field}.published_at")
    if observed_at > as_of:
        raise ReviewError(f"{field}.observed_at 晚于 as-of")
    if published_at > as_of:
        raise ReviewError(f"{field}.published_at 晚于 as-of")
    try:
        datetime.fromisoformat(evidence.get("fetched_at"))
    except (TypeError, ValueError) as exc:
        raise ReviewError(f"{field}.fetched_at 必须是ISO-8601 datetime") from exc
    validate_source(evidence.get("source"), field)


def validate_event(item: Any, field: str, as_of: date, allow_future_event: bool) -> None:
    if not isinstance(item, dict):
        raise ReviewError(f"{field} 必须是object")
    require_text(item, "title", field)
    event_date = parse_date(item.get("event_date"), f"{field}.event_date")
    published_at = parse_date(item.get("published_at"), f"{field}.published_at")
    if not allow_future_event and event_date > as_of:
        raise ReviewError(f"{field}.event_date 晚于 as-of")
    if published_at > as_of:
        raise ReviewError(f"{field}.published_at 晚于 as-of")
    try:
        datetime.fromisoformat(item.get("fetched_at"))
    except (TypeError, ValueError) as exc:
        raise ReviewError(f"{field}.fetched_at 必须是ISO-8601 datetime") from exc
    validate_source(item.get("source"), field)


def normalized_sections(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_sections = data.get("sections")
    if not isinstance(raw_sections, dict):
        raise ReviewError("sections 必须是object")
    sections = {}
    for name in SECTION_NAMES:
        section = raw_sections.get(name)
        if section is None:
            section = {"availability": "unknown", "status_reason": "输入未提供该章节"}
        if not isinstance(section, dict):
            raise ReviewError(f"sections.{name} 必须是object")
        availability = section.get("availability")
        if availability not in AVAILABILITY:
            raise ReviewError(f"sections.{name}.availability 不受支持")
        require_text(section, "status_reason", f"sections.{name}")
        if availability == "unknown" and (
            section.get("items") or section.get("metrics")
        ):
            raise ReviewError(f"sections.{name} 标记unknown时不能携带数值数据")
        sections[name] = section
    return sections


def require_market_date(evidence: dict[str, Any], field: str, market_date: date) -> None:
    observed_at = parse_date(evidence.get("observed_at"), f"{field}.observed_at")
    if observed_at != market_date:
        raise ReviewError(f"{field} 标记available时observed_at必须等于market_date")


def validate_sections(
    sections: dict[str, dict[str, Any]], as_of: date, market_date: date
) -> None:
    indices = sections["indices"]
    if indices["availability"] != "unknown":
        items = indices.get("items")
        if not isinstance(items, list) or not items:
            raise ReviewError("sections.indices.items 必须是非空数组")
        primary_count = 0
        for index, item in enumerate(items):
            field = f"sections.indices.items[{index}]"
            if not isinstance(item, dict):
                raise ReviewError(f"{field} 必须是object")
            require_text(item, "id", field)
            require_text(item, "name", field)
            if not isinstance(item.get("primary"), bool):
                raise ReviewError(f"{field}.primary 必须是boolean")
            primary_count += int(item["primary"])
            validate_evidence(
                item.get("close"),
                f"{field}.close",
                as_of,
                "index_points",
                "positive",
            )
            validate_evidence(item.get("change_pct"), f"{field}.change_pct", as_of, "percent")
            if indices["availability"] == "available":
                require_market_date(item["close"], f"{field}.close", market_date)
                require_market_date(
                    item["change_pct"], f"{field}.change_pct", market_date
                )
        if primary_count != 1:
            raise ReviewError("indices 必须且只能有一个primary指数")

    breadth = sections["breadth"]
    if breadth["availability"] != "unknown":
        metrics = breadth.get("metrics")
        if not isinstance(metrics, dict):
            raise ReviewError("sections.breadth.metrics 必须是object")
        required = ("advancers", "decliners", "unchanged", "limit_up", "limit_down")
        if breadth["availability"] == "available" and any(name not in metrics for name in required):
            raise ReviewError("available breadth 缺少必需指标")
        for name, evidence in metrics.items():
            validate_evidence(
                evidence,
                f"sections.breadth.metrics.{name}",
                as_of,
                "count",
                "nonnegative",
            )
            if breadth["availability"] == "available":
                require_market_date(
                    evidence, f"sections.breadth.metrics.{name}", market_date
                )

    turnover = sections["turnover"]
    if turnover["availability"] != "unknown":
        metrics = turnover.get("metrics")
        if not isinstance(metrics, dict):
            raise ReviewError("sections.turnover.metrics 必须是object")
        if turnover["availability"] == "available" and any(
            name not in metrics for name in ("amount", "previous_amount")
        ):
            raise ReviewError("available turnover 缺少amount或previous_amount")
        for name, evidence in metrics.items():
            validate_evidence(
                evidence,
                f"sections.turnover.metrics.{name}",
                as_of,
                "CNY",
                "positive",
            )
        if turnover["availability"] == "available":
            require_market_date(
                metrics["amount"], "sections.turnover.metrics.amount", market_date
            )

    sectors = sections["sectors"]
    if sectors["availability"] != "unknown":
        require_text(sectors, "classification", "sections.sectors")
        items = sectors.get("items")
        if not isinstance(items, list) or not items:
            raise ReviewError("sections.sectors.items 必须是非空数组")
        for index, item in enumerate(items):
            field = f"sections.sectors.items[{index}]"
            if not isinstance(item, dict):
                raise ReviewError(f"{field} 必须是object")
            require_text(item, "id", field)
            require_text(item, "name", field)
            validate_evidence(item.get("change_pct"), f"{field}.change_pct", as_of, "percent")
            if sectors["availability"] == "available":
                require_market_date(item["change_pct"], f"{field}.change_pct", market_date)

    for section_name in ("funds", "style"):
        section = sections[section_name]
        if section["availability"] == "unknown":
            continue
        items = section.get("items")
        if not isinstance(items, list) or not items:
            raise ReviewError(f"sections.{section_name}.items 必须是非空数组")
        for index, item in enumerate(items):
            field = f"sections.{section_name}.items[{index}]"
            if not isinstance(item, dict):
                raise ReviewError(f"{field} 必须是object")
            require_text(item, "name", field)
            explanation_field = "methodology" if section_name == "funds" else "interpretation"
            require_text(item, explanation_field, field)
            validate_evidence(item.get("metric"), f"{field}.metric", as_of)
            if section_name == "style" and section["availability"] == "available":
                require_market_date(item["metric"], f"{field}.metric", market_date)

    events = sections["events"]
    if events["availability"] != "unknown":
        items = events.get("items")
        if not isinstance(items, list) or not items:
            raise ReviewError("sections.events.items 必须是非空数组")
        for index, item in enumerate(items):
            validate_event(item, f"sections.events.items[{index}]", as_of, False)


def validate_input(
    data: dict[str, Any], requested_as_of: date
) -> dict[str, dict[str, Any]]:
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ReviewError(f"schema_version 必须是{SCHEMA_VERSION}")
    market_date = parse_date(data.get("market_date"), "market_date")
    input_as_of = parse_date(data.get("as_of"), "as_of")
    if input_as_of != requested_as_of:
        raise ReviewError("输入as_of与命令行as-of不一致")
    if market_date > requested_as_of:
        raise ReviewError("market_date 不能晚于 as-of")
    sections = normalized_sections(data)
    validate_sections(sections, requested_as_of, market_date)
    verification_points = data.get("verification_points", [])
    if not isinstance(verification_points, list):
        raise ReviewError("verification_points 必须是数组")
    for index, item in enumerate(verification_points):
        validate_event(item, f"verification_points[{index}]", requested_as_of, True)
    return sections


def value(section: dict[str, Any], metric: str) -> float | None:
    evidence = section.get("metrics", {}).get(metric)
    return float(evidence["value"]) if evidence else None


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

    turnover = sections["turnover"]
    amount = value(turnover, "amount")
    previous = value(turnover, "previous_amount")
    average_5d = value(turnover, "avg_5d_amount")
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
    return derived, signals


def coverage(sections: dict[str, dict[str, Any]]) -> dict[str, int]:
    return {
        status: sum(section["availability"] == status for section in sections.values())
        for status in ("available", "partial", "unknown")
    }


def iter_sources(data: Any):
    if isinstance(data, dict):
        if {"id", "name", "url"} <= set(data):
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
            {"id": source["id"], "name": source["name"], "url": source["url"], "count": 0},
        )
        if (current["name"], current["url"]) != (source["name"], source["url"]):
            raise ReviewError(f"source.id存在冲突：{source['id']}")
        current["count"] += 1
    return [sources[key] for key in sorted(sources)]


def fmt_evidence(evidence: dict[str, Any]) -> str:
    number = float(evidence["value"])
    unit = evidence["unit"]
    if unit == "percent":
        return f"{number:+.2f}%"
    if unit == "CNY":
        return f"{number / 1e8:,.2f}亿元"
    if unit == "count":
        return f"{number:,.0f}"
    if unit == "index_points":
        return f"{number:,.2f}"
    return f"{number:g} {unit}"


def unknown_line(section: dict[str, Any]) -> str:
    return f"> {section['availability'].upper()}：{section['status_reason']}"


def build_markdown(
    data: dict[str, Any],
    sections: dict[str, dict[str, Any]],
    input_sha256: str,
    derived: dict[str, Any],
    signals: list[dict[str, str]],
    coverage_counts: dict[str, int],
    sources: list[dict[str, Any]],
) -> str:
    lines = [
        f"# A股每日盘面复盘｜{data['market_date']}",
        "",
        f"- 截止日期：{data['as_of']}",
        f"- 输入SHA-256：`{input_sha256}`",
        f"- 覆盖：可得{coverage_counts['available']} / 部分{coverage_counts['partial']} / 未知{coverage_counts['unknown']}",
        "- 结论属性：盘面证据与结构观察，不构成投资建议",
        "",
    ]
    if coverage_counts["unknown"] == len(SECTION_NAMES):
        lines.extend(["## 无可得盘面数据", "", "本次七个盘面章节均为unknown，不能形成全市场强弱结论。", ""])

    lines.extend(["## 一、主要指数", ""])
    indices = sections["indices"]
    if indices["availability"] == "unknown":
        lines.extend([unknown_line(indices), ""])
    else:
        lines.extend(["| 指数 | 收盘 | 涨跌幅 | 观察日 | 来源 |", "|---|---:|---:|---|---|"])
        for item in indices["items"]:
            evidence = item["change_pct"]
            lines.append(
                f"| {item['name']} | {fmt_evidence(item['close'])} | {fmt_evidence(evidence)} | {evidence['observed_at']} | {evidence['source']['name']} |"
            )
        lines.append("")

    lines.extend(["## 二、市场宽度", ""])
    breadth = sections["breadth"]
    if breadth["availability"] == "unknown":
        lines.extend([unknown_line(breadth), ""])
    else:
        lines.extend(["| 指标 | 数值 | 观察日 | 来源 |", "|---|---:|---|---|"])
        for name, label in (
            ("advancers", "上涨家数"),
            ("decliners", "下跌家数"),
            ("unchanged", "平盘家数"),
            ("limit_up", "涨停家数"),
            ("limit_down", "跌停家数"),
        ):
            evidence = breadth.get("metrics", {}).get(name)
            if evidence:
                lines.append(
                    f"| {label} | {fmt_evidence(evidence)} | {evidence['observed_at']} | {evidence['source']['name']} |"
                )
        if "advancer_share_pct" in derived:
            lines.append("")
            lines.append(f"上涨家数占比：{derived['advancer_share_pct']:.2f}%")
            ratio = derived.get("advance_decline_ratio")
            lines.append(f"涨跌家数比：{ratio:.2f}" if ratio is not None else "涨跌家数比：无法计算（下跌家数为0）")
        lines.append("")

    lines.extend(["## 三、成交与流动性", ""])
    turnover = sections["turnover"]
    if turnover["availability"] == "unknown":
        lines.extend([unknown_line(turnover), ""])
    else:
        amount = turnover["metrics"].get("amount")
        if amount:
            lines.append(f"- 当日成交额：{fmt_evidence(amount)}")
        if "turnover_vs_previous_pct" in derived:
            lines.append(f"- 较前值：{derived['turnover_vs_previous_pct']:+.2f}%")
        if "turnover_vs_5d_avg_pct" in derived:
            lines.append(f"- 较5日均值：{derived['turnover_vs_5d_avg_pct']:+.2f}%")
        lines.extend([f"- 覆盖说明：{turnover['status_reason']}", ""])

    lines.extend(["## 四、板块表现", ""])
    sectors = sections["sectors"]
    if sectors["availability"] == "unknown":
        lines.extend([unknown_line(sectors), ""])
    else:
        ordered = sorted(sectors["items"], key=lambda item: (-float(item["change_pct"]["value"]), item["id"]))
        lines.extend([
            f"分类体系：{sectors['classification']}；覆盖状态：{sectors['availability']}。",
            "",
            "| 板块 | 涨跌幅 | 观察日 | 来源 |",
            "|---|---:|---|---|",
        ])
        for item in ordered:
            evidence = item["change_pct"]
            lines.append(
                f"| {item['name']} | {fmt_evidence(evidence)} | {evidence['observed_at']} | {evidence['source']['name']} |"
            )
        lines.append("")

    for section_name, heading, explanation in (
        ("funds", "五、资金证据", "methodology"),
        ("style", "六、风格结构", "interpretation"),
    ):
        section = sections[section_name]
        lines.extend([f"## {heading}", ""])
        if section["availability"] == "unknown":
            lines.extend([unknown_line(section), ""])
            continue
        lines.extend(["| 项目 | 数值 | 方法/解释 | 观察日 | 来源 |", "|---|---:|---|---|---|"])
        for item in section["items"]:
            evidence = item["metric"]
            lines.append(
                f"| {item['name']} | {fmt_evidence(evidence)} | {item[explanation]} | {evidence['observed_at']} | {evidence['source']['name']} |"
            )
        lines.append("")

    lines.extend(["## 七、事件与验证点", ""])
    events = sections["events"]
    if events["availability"] == "unknown":
        lines.extend([unknown_line(events), ""])
    else:
        for item in events["items"]:
            lines.append(f"- {item['event_date']}｜{item['title']}｜{item['source']['name']}")
        lines.append("")
    if data.get("verification_points"):
        lines.append("后续验证点：")
        lines.append("")
        for item in data["verification_points"]:
            lines.append(f"- {item['event_date']}｜{item['title']}｜{item['source']['name']}")
        lines.append("")

    lines.extend(["## 八、结构信号与限制", ""])
    if signals:
        for signal in signals:
            lines.append(f"- {signal['label']}：{signal['evidence']}；规则：`{signal['rule']}`。")
    else:
        lines.append("- 当前输入未触发预定义的指数—宽度背离规则。")
    lines.append("")
    for name in SECTION_NAMES:
        section = sections[name]
        if section["availability"] != "available":
            lines.append(f"- {name}：{section['availability']}，{section['status_reason']}")
    lines.extend(["", "## 九、来源汇总", "", "| 来源 | URL | 使用次数 |", "|---|---|---:|"])
    for source in sources:
        lines.append(f"| {source['name']} | {source['url']} | {source['count']} |")
    lines.extend(["", "---", "", "本报告只描述输入证据和显式规则，不构成投资建议。", ""])
    report = "\n".join(lines)
    for phrase in FORBIDDEN:
        if phrase in report:
            raise ReviewError(f"输出包含禁止的投资指令：{phrase}")
    return report


def generate(data: dict[str, Any], input_sha256: str, requested_as_of: date):
    sections = validate_input(data, requested_as_of)
    derived, signals = derive(sections)
    coverage_counts = coverage(sections)
    sources = source_summary(data)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "run": {
            "market_date": data["market_date"],
            "as_of": requested_as_of.isoformat(),
            "input_sha256": input_sha256,
        },
        "coverage": coverage_counts,
        "derived": derived,
        "signals": signals,
        "sections": {
            name: {
                "availability": section["availability"],
                "status_reason": section["status_reason"],
            }
            for name, section in sections.items()
        },
        "source_summary": sources,
    }
    markdown = build_markdown(
        data, sections, input_sha256, derived, signals, coverage_counts, sources
    )
    return markdown, summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="可审计的A股每日盘面复盘生成器")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        requested_as_of = parse_date(args.as_of, "as-of")
        data, input_sha256 = load_input(args.input)
        markdown, summary = generate(data, input_sha256, requested_as_of)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(
            json.dumps(
                {"output": str(args.output), "summary": str(args.summary_out)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (ReviewError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
