#!/usr/bin/env python3
"""A 股研究技能库测试运行器。

在仓库根目录运行：

    python3 tools/run_skill_tests.py              # 全部技能 + 共享层
    python3 tools/run_skill_tests.py --list       # 只列出会跑哪些套件
    python3 tools/run_skill_tests.py ashare-daily-market-review
    python3 tools/run_skill_tests.py --stop-on-failure

每个套件在「自己所属目录」下以子进程运行，因为技能测试依赖相对路径上的
tests/fixtures 与 scripts/，且脚本会按 __file__ 推导 skills/_shared。
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
SHARED_DIR = SKILLS_DIR / "_shared"
UNIT = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"]


def suites() -> list[tuple[str, Path]]:
    """返回 (显示名, 运行目录) 列表。共享层排在最前。"""
    found: list[tuple[str, Path]] = []
    if (SHARED_DIR / "tests").is_dir():
        found.append(("_shared", SHARED_DIR))
    for path in sorted(SKILLS_DIR.iterdir()):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        if (path / "SKILL.md").is_file() and (path / "tests").is_dir():
            found.append((path.name, path))
    return found


def run(name: str, cwd: Path) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            UNIT, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False
        )
    except OSError as exc:
        return False, f"无法启动测试：{exc}"
    return proc.returncode == 0, proc.stdout


def summarize(output: str) -> str:
    match = re.search(r"^Ran (\d+) tests? in ([\d.]+)s", output, re.M)
    if not match:
        return "未产生测试结果"
    return f"Ran {match.group(1)} tests in {match.group(2)}s"


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 A 股技能库全部测试套件")
    parser.add_argument("skill", nargs="*", help="只跑指定技能目录名（默认全部）")
    parser.add_argument("--list", action="store_true", help="只列出套件，不执行")
    parser.add_argument("--stop-on-failure", action="store_true", help="遇到失败立即停止")
    args = parser.parse_args()

    selected = suites()
    if args.skill:
        wanted = set(args.skill)
        unknown = wanted - {name for name, _ in selected}
        if unknown:
            print(f"未知技能：{', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        selected = [(name, path) for name, path in selected if name in wanted]

    if args.list:
        for name, path in selected:
            print(f"{name:40s} {path.relative_to(REPO_ROOT)}")
        return 0

    if not selected:
        print("没有找到任何测试套件。", file=sys.stderr)
        return 2

    total = 0
    failed: list[str] = []
    for name, path in selected:
        ok, output = run(name, path)
        detail = summarize(output)
        number = re.search(r"Ran (\d+) tests?", detail)
        if number:
            total += int(number.group(1))
        print(f"{'PASS' if ok else 'FAIL'}  {name:40s} {detail}")
        if not ok:
            failed.append(name)
            print(output.rstrip())
            if args.stop_on_failure:
                break

    print()
    if failed:
        print(f"失败 {len(failed)} / {len(selected)} 个套件：{', '.join(failed)}", file=sys.stderr)
        return 1
    print(f"全部通过：{len(selected)} 个套件，{total} 个测试。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
