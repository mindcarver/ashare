#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公开语言门禁：面向读者的报告绝不出现英文字段码/枚举/ID（2026-09-17 用户规则）。

覆盖三类泄漏：
1. 蛇形字段码（open_board_rate_pct 这类内部指标名）；
2. 短横线ID（pcb-outflow、verify-xxx-0918、all-a-non-st 这类内部ID）；
3. 裸英文枚举词（deep/clear/passed/hypothesis/…）与英文单位词（CNY/count/percent/ratio）。

HTML 侧先剥离 <style>/<script> 与全部标签、实体，只扫描读者可见文本。
命中即抛 ReviewError 并列出词与次数，生成器拒出报告。
"""

import re

from schema import ReviewError


_ENUM_WORDS = (
    "deep core close inflow outflow passed failed supported contradicted "
    "available partial unknown none clear flagged hypothesis schema "
    "ice euphoria divergence repair neutral market stock theme sector benchmark "
    "count percent ratio and not"
    # 自由英文短语兜底：中文报告不应出现这些小写英文词
    " group change positive share declared threshold must window pool board "
    " fund flow seal break turnover streak quadrant scope subject condition "
    " observation metric operator value unit previous current days min max "
)
ENUM_WORDS = frozenset(_ENUM_WORDS.split()) | {"CNY", "UNKNOWN", "False", "True", "Schema"}

SNAKE_CODE = re.compile(r"(?<![A-Za-z0-9_])[a-z][a-z0-9]*(?:_[a-z0-9]+)+")
KEBAB_ID = re.compile(r"(?<![A-Za-z0-9_])[a-z][a-z0-9]*(?:-[a-z0-9]+)+")

# 少数读者可接受的英文专有成分（全部为大写专名或中英混排惯用词），不在枚举词表内。


def _strip_html(html: str) -> str:
    text = re.sub(r"<(style|script)\b[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    return text


def public_language_violations(text: str) -> dict[str, int]:
    violations: dict[str, int] = {}

    def record(match: re.Match) -> None:
        token = match.group(0)
        violations[token] = violations.get(token, 0) + 1

    for match in SNAKE_CODE.finditer(text):
        record(match)
    for match in KEBAB_ID.finditer(text):
        record(match)
    for word in ENUM_WORDS:
        count = len(
            re.findall(r"(?<![A-Za-z0-9_])" + re.escape(word) + r"(?![A-Za-z0-9_])", text)
        )
        if count:
            violations[word] = violations.get(word, 0) + count
    return violations


def assert_public_language(markdown: str, html: str | None = None) -> None:
    """生成器出口调用：任一公开产物含英文码即拒绝输出。"""
    problems: list[str] = []
    for label, text in (("Markdown", markdown), ("HTML", _strip_html(html) if html else "")):
        if not text:
            continue
        violations = public_language_violations(text)
        if violations:
            detail = "、".join(
                f"{word}×{count}" for word, count in sorted(violations.items(), key=lambda x: -x[1])
            )
            problems.append(f"{label}: {detail}")
    if problems:
        raise ReviewError(
            "公开报告不允许英文字段码/枚举/ID（读者语言门禁）——" + "；".join(problems)
        )
