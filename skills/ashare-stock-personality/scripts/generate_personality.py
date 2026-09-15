#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""个股股性画像生成器 —— ashare-stock-personality 的 CLI 入口。

模块分工（沿用 daily-review 的拆分纪律，单文件不得超过审计上限）：
  - schema.py     契约常量（维度、原型、象限、阈值必填键）与最小断言
  - metrics.py    观测事实 → 原始特征 → 池内百分位 → 六维分
  - archetypes.py 原型分类与象限划分
  - validate.py   输入契约校验与派生结果自洽校验
  - derive.py     六维 → 综合分 → 原型 → 象限 → 板块×原型矩阵 → 股性地图 → 信号
  - render.py     Markdown 与 HTML 渲染

本文件只负责：参数解析、编排、禁词门、共享层注入、写盘。

禁词门 tier：score_ok。
  本技能有自有的「综合股性分」，因此允许出现「总分」这类评分聚合词；
  但仍禁止一切价位锚点（止损/止盈/买入观察价/目标价位）。
  禁词表唯一真源：skills/_shared/forbidden-terms.json。
"""

import argparse
import json
import sys

from pathlib import Path
from typing import Any

import _paths  # noqa: F401  确保 skills/_shared 在 sys.path 上
from ashare_shared import assert_clean, forbidden_terms, inject_shared_css

from derive import derive
from render import build_html, build_markdown
from schema import PersonalityError, SCHEMA_VERSION
from validate import load_input, validate_derived, validate_input

# 允许评分聚合词、禁止价位：与 A-SHARE/NEWS TARGETS 同级。
FORBIDDEN = forbidden_terms("score_ok")


def generate(data: dict[str, Any], input_sha256: str) -> tuple[str, dict[str, Any], str]:
    sections = validate_input(data)
    derived, signals = derive(sections)
    validate_derived(derived, sections["thresholds"])

    markdown = build_markdown(sections, derived, signals, input_sha256)
    html = build_html(sections, derived, signals, input_sha256)

    # 禁词门：输入原文与两份渲染件都要过（HTML 注入共享 CSS 之前先查，避免共享层噪声）。
    assert_clean(sections, "score_ok", label="输入")
    assert_clean(markdown, "score_ok", label="Markdown")
    assert_clean(html, "score_ok", label="HTML")

    html = inject_shared_css(html)

    overview = derived["overview"]
    summary = {
        "schema_version": SCHEMA_VERSION,
        "run": {
            "as_of": sections["as_of"],
            "input_sha256": input_sha256,
            "window": sections["window"],
            "capacity_metric": sections["capacity_metric"],
            "universe": sections["universe"],
        },
        "overview": overview,
        "archetype_table": derived["archetype_table"],
        "quadrant_counts": derived["map"]["quadrant_counts"],
        "signals": signals,
        "caveats": derived["caveats"],
    }
    return markdown, summary, html


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="个股股性画像生成器（六维 + 原型 + 地图）")
    parser.add_argument("--input", type=Path, required=True, help="personality_input.json")
    parser.add_argument("--out", type=Path, help="输出 Markdown 路径")
    parser.add_argument("--html-out", type=Path, help="输出自包含 HTML 路径")
    parser.add_argument("--summary-out", type=Path, help="输出派生摘要 JSON 路径")
    parser.add_argument("--check", action="store_true", help="只校验输入契约，不写盘")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        data, input_sha256 = load_input(args.input)
        markdown, summary, html = generate(data, input_sha256)

        if args.check:
            print(
                "✅ 输入契约与禁词门通过："
                f"{summary['overview']['total']} 只，"
                f"有综合分 {summary['overview']['scored']} 只，"
                f"容量口径 {summary['run']['capacity_metric']}"
            )
            return 0

        if not (args.out or args.html_out):
            raise PersonalityError("至少需要 --out 或 --html-out 之一")

        written: dict[str, str] = {}
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(markdown, encoding="utf-8")
            written["markdown"] = str(args.out)
        if args.html_out:
            args.html_out.parent.mkdir(parents=True, exist_ok=True)
            args.html_out.write_text(html, encoding="utf-8")
            written["html"] = str(args.html_out)
        if args.summary_out:
            args.summary_out.parent.mkdir(parents=True, exist_ok=True)
            args.summary_out.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            written["summary"] = str(args.summary_out)

        print(json.dumps(written, ensure_ascii=False, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        # PersonalityError 是 ValueError 的子类；assert_clean 抛的也是 ValueError。
        print(f"错误：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
