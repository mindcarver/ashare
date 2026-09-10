#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A股研究结论事后复盘 —— CLI 入口。

已按 P2-5 纪律拆分，本文件负责参数解析、编排与输出分发：
  - schema.py    常量、错误类型、摘要/日期工具
  - validate.py  输入读取与契约校验
  - derive.py    SQLite 存储与复核计算
  - render.py    单条复盘与统计看板的 HTML 渲染

输出分发（审计 P2-6）：
  - show / stats  → 自包含 HTML 报告（默认写 research/research-journal/，可 --out 覆盖），
                     stdout 只打印落盘路径与字节数
  - record / due / observe / export → 结构化 JSON（保持机器可读，供脚本与管道消费）
"""

import argparse
import json
import sqlite3
import sys

from pathlib import Path
from typing import Any

import render
from derive import connect, due, export_all, observe, record, show, stats
from schema import DEFAULT_DB, JournalError, parse_date
from validate import load_json

# 报告默认落盘目录：<repo>/research/research-journal/
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[3] / "research" / "research-journal"


def print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def write_html(html: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"✅ 已生成 {out}")
    print(f"   大小: {len(html)} 字节")
    return out


def default_record_out(research_id: str) -> Path:
    return DEFAULT_OUT_DIR / f"{research_id}.html"


def default_stats_out(as_of: str, code: str | None) -> Path:
    stem = f"research-journal-stats-{as_of}"
    if code:
        stem += f"-{code}"
    return DEFAULT_OUT_DIR / f"{stem}.html"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A股研究结论事后复盘")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="本地SQLite路径")
    sub = parser.add_subparsers(dest="command", required=True)

    record_parser = sub.add_parser("record", help="冻结研究快照")
    record_parser.add_argument("--input", type=Path, required=True)

    show_parser = sub.add_parser("show", help="查看快照和结果，输出HTML复盘报告")
    show_parser.add_argument("--id", required=True)
    show_parser.add_argument("--out", type=Path, help="HTML 输出路径（默认 research/research-journal/<id>.html）")

    due_parser = sub.add_parser("due", help="列出到期未复核记录")
    due_parser.add_argument("--as-of", required=True)

    observe_parser = sub.add_parser("observe", help="追加到期结果")
    observe_parser.add_argument("--id", required=True)
    observe_parser.add_argument("--input", type=Path, required=True)
    observe_parser.add_argument("--as-of", required=True)

    stats_parser = sub.add_parser("stats", help="统计成熟记录，输出HTML统计看板")
    stats_parser.add_argument("--as-of", required=True)
    stats_parser.add_argument("--code")
    stats_parser.add_argument("--out", type=Path, help="HTML 输出路径（默认 research/research-journal/research-journal-stats-<as_of>.html）")

    sub.add_parser("export", help="导出全部可复核JSON")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        with connect(args.db) as db:
            if args.command == "record":
                print_json(record(db, load_json(args.input)))
            elif args.command == "show":
                result = show(db, args.id)
                write_html(render.render_record(result), args.out or default_record_out(args.id))
            elif args.command == "due":
                print_json(due(db, parse_date(args.as_of, "as-of")))
            elif args.command == "observe":
                print_json(
                    observe(
                        db,
                        args.id,
                        load_json(args.input),
                        parse_date(args.as_of, "as-of"),
                    )
                )
            elif args.command == "stats":
                as_of = args.as_of
                result = stats(db, parse_date(as_of, "as-of"), args.code)
                write_html(render.render_stats(result), args.out or default_stats_out(as_of, args.code))
            else:
                print_json(export_all(db))
        return 0
    except JournalError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"错误：SQLite失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
