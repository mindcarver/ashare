#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成可审计的 A 股每日盘面复盘 —— ashare-daily-market-review 的 CLI 入口。

已按审计 P2-5 拆分，本文件只负责编排、参数解析与写盘：
  - schema.py    错误类型、Schema 常量、日期/文本断言、value()
  - validate.py  输入读取、Schema 1.0 归一化、契约校验
  - derive.py    判读派生、历史序列、验证点
  - render.py    Markdown 与 HTML 渲染
"""

import argparse
import json
import sys

from datetime import date
from pathlib import Path
from typing import Any

import _paths  # noqa: F401  确保 skills/_shared 在 sys.path 上
from ashare_shared import inject_shared_css

from derive import coverage, derive, derive_history, load_history_entries, persist_snapshot, resolve_verification_points, source_summary
from deep_analysis import deep_signals, derive_deep_analysis
from four_axis import deep_coverage, derive_four_axis, four_axis_signals
from render import build_html, build_markdown
from schema import ReviewError, SCHEMA_VERSION, parse_date
from validate import load_input, validate_input


def generate(
    data: dict[str, Any],
    input_sha256: str,
    requested_as_of: date,
    history_entries: list[dict[str, Any]] | None = None,
):
    history_entries = history_entries or []
    sections = validate_input(data, requested_as_of)
    derived, signals = derive(sections)
    deep = derive_deep_analysis(data, sections, derived)
    if deep is not None:
        derived["deep_analysis"] = deep
        signals.extend(deep_signals(deep))
    history = derive_history(history_entries, data, sections, derived)
    resolved_verifications = resolve_verification_points(
        history_entries, data, sections, derived
    )
    four_axis = derive_four_axis(data, derived, history, resolved_verifications)
    derived["four_axis"] = four_axis
    signals.extend(four_axis_signals(four_axis))
    coverage_counts = coverage(sections)
    deep_coverage_counts = deep_coverage(data)
    sources = source_summary(data)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "run": {
            "market_date": data["market_date"],
            "as_of": requested_as_of.isoformat(),
            "input_sha256": input_sha256,
            "snapshot": data["snapshot"],
        },
        "coverage": coverage_counts,
        "analysis_mode": data["analysis_mode"],
        "deep_coverage": deep_coverage_counts,
        "derived": derived,
        "signals": signals,
        "history": history,
        "resolved_verifications": resolved_verifications,
        "legacy_migration": data.get("legacy_migration"),
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
        data,
        sections,
        input_sha256,
        derived,
        signals,
        coverage_counts,
        sources,
        history,
        resolved_verifications,
    )
    html = build_html(
        data,
        sections,
        input_sha256,
        derived,
        signals,
        coverage_counts,
        sources,
        history,
        resolved_verifications,
    )
    html = inject_shared_css(html)
    return markdown, summary, html


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="可审计的A股每日盘面复盘生成器")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary-out", type=Path, required=True)
    parser.add_argument("--html-out", type=Path, help="可选静态 HTML 可视化输出路径")
    parser.add_argument("--history-dir", type=Path, help="可选版本化历史快照目录")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        requested_as_of = parse_date(args.as_of, "as-of")
        data, input_sha256 = load_input(args.input)
        history_entries = load_history_entries(args.history_dir) if args.history_dir else []
        markdown, summary, html = generate(
            data, input_sha256, requested_as_of, history_entries
        )
        history_path = None
        history_appended = None
        if args.history_dir:
            history_path, history_appended = persist_snapshot(
                args.history_dir, data, input_sha256, history_entries
            )
            summary["run"]["history_path"] = str(history_path)
            summary["run"]["history_appended"] = history_appended
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.summary_out.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        args.summary_out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if args.html_out:
            args.html_out.parent.mkdir(parents=True, exist_ok=True)
            args.html_out.write_text(html, encoding="utf-8")
        result = {"output": str(args.output), "summary": str(args.summary_out)}
        if args.html_out:
            result["html"] = str(args.html_out)
        if history_path:
            result["history"] = str(history_path)
            result["history_appended"] = history_appended
        print(
            json.dumps(result, ensure_ascii=False, sort_keys=True)
        )
        return 0
    except (ReviewError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
