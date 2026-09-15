#!/usr/bin/env python3
"""共享层漂移检查。

回答两个问题：
1. 共享层本身是否完整（禁词表、令牌、技术面口径）？
2. 有没有技能又把共享内容复制回自己的目录/脚本？

发现漂移时以非零码退出，可放进 CI 或 pre-commit。

    python3 tools/audit_shared_layer.py
    python3 tools/audit_shared_layer.py --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
SHARED_DIR = SKILLS_DIR / "_shared"

sys.path.insert(0, str(SHARED_DIR))

GENERATOR_SKILLS = (
    "ashare-capital-environment-dashboard",
    "ashare-daily-market-review",
    "ashare-company-research",
    "ashare-news-investment-targets",
    "ashare-stock-personality",
)

# 报告逐字引用用户当时冻结的研究原文（假设/催化剂/证伪条件），审查性引用不可改写，
# 因此无法对报告文字设禁词硬门禁——改用固定「报告性质」声明替代（见 SKILL.md 第五节）。
# 这些技能仍然必须接入共享令牌与外壳（inject_shared_css），也接受「不得体积回涨」的检查。
FORBIDDEN_EXEMPT_SKILLS = ("ashare-research-journal",)

# 全部产出 HTML 报告、因而必须接入共享设计系统的技能。
HTML_REPORT_SKILLS = GENERATOR_SKILLS + FORBIDDEN_EXEMPT_SKILLS

# 豁免技能必须在脚本里保留的固定声明（替代禁词硬门禁）。
EXEMPT_DISCLAIMER = "不构成投资建议"

# 单文件上限：P2-5 拆分后任一模块都不该再长成巨型脚本。
MAX_SCRIPT_LINES = 700


def skill_scripts(skill: str) -> list[Path]:
    """技能 scripts/ 下全部 .py（按名排序）。

    生成器已按审计 P2-5 拆分为 schema/validate/derive/render 等同目录模块，
    只检查入口脚本会漏掉藏在其它模块里的漂移。
    """
    return sorted((SKILLS_DIR / skill / "scripts").glob("*.py"))

SKILLS_WITH_TECHNICAL_ANALYSIS = ("ashare-company-research", "ashare-news-investment-targets")

REQUIRED_ASSETS = (
    "forbidden-terms.json",
    "design-tokens.css",
    "shell.css",
    "components.css",
    "technical-analysis.md",
    "ashare_shared.py",
)

# 页面骨架规则：只允许存在于 _shared/shell.css，出现回生成器即为漂移。
SHELL_NEEDLES = (
    "box-sizing:border-box",
    ".masthead{",
    ".eyebrow{",
    ".asof{",
    ".lede{",
    "body:before{",
    "footer{",
)

# 组件骨架规则：只允许存在于 _shared/components.css。v2 起品牌层排在技能 <style>
# 之后，技能模板若重写这些规则会先被品牌层覆盖，等于隐藏的死代码。
COMPONENT_NEEDLES = (
    ".panel-head{",
    ".metric-card{",
    ".matrix-cell.a{",
    ".badge-available{",
    ".tone-rise",
    ".bar-track{",
    ".donut{",
    ".verify-strip,",
    ".sentiment-kpis{",
)


def strip_css_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


_STYLE_CONST_RE = re.compile(
    r"^(?P<name>STYLE|[A-Z][A-Z0-9_]*STYLE[A-Z0-9_]*)\s*=\s*(?:\"\"\"|''')(?P<body>.*?)(?:\"\"\"|''')",
    re.S | re.M,
)


def inline_css_chars(src: str) -> int:
    """估算脚本里内联的 CSS 体量。

    有的生成器把 CSS 直接写在 <style>…</style> 的 f-string 里，有的（company）把
    它放进 `STYLE = \"\"\"…\"\"\"` 常量——两者都属于内联，都要计入，否则 company
    会显示一个毫无意义的 7 字符（即占位符 {STYLE}）。
    """
    total = sum(len(block) for block in re.findall(r"<style>(.*?)</style>", src, re.S))
    total += sum(len(match.group("body")) for match in _STYLE_CONST_RE.finditer(src))
    return total


def check() -> tuple[list[str], dict]:
    problems: list[str] = []
    report: dict = {}

    missing = [name for name in REQUIRED_ASSETS if not (SHARED_DIR / name).is_file()]
    if missing:
        problems.append(f"共享层缺少文件：{', '.join(missing)}")
    if (SHARED_DIR / "SKILL.md").exists():
        problems.append("_shared 目录下出现 SKILL.md —— 它不是技能，不应被 install.sh 当作技能挂载")

    try:
        from ashare_shared import (
            brand_css,
            components_css,
            design_tokens_css,
            minified_components_css,
            minified_design_tokens_css,
            minified_shell_css,
            selftest,
            shell_css,
            tier_for_skill,
        )
    except Exception as exc:  # noqa: BLE001 - 审计工具需要报告任何加载失败
        problems.append(f"共享层无法加载：{exc}")
        return problems, report

    report["shared_selftest"] = selftest()
    shared_tokens = dict(re.findall(r"(--[a-z0-9-]+):([^;}]+)", minified_design_tokens_css()))
    report["shell_css_chars"] = len(minified_shell_css())
    report["components_css_chars"] = len(minified_components_css())
    report["brand_css_chars"] = len(brand_css())

    # 身份硬约束：方角 + 单一硬投影 + 无行情词徽章别名。
    brand_mini = brand_css()
    if "border-radius:9999px" in brand_mini:
        problems.append("品牌层出现胶囊圆角（border-radius:9999px），与「方角」身份冲突")
    if re.search(r"box-shadow:\s*\d+px\s+\d+px\s+[1-9]\d*px", brand_mini):
        problems.append("品牌层出现带模糊的柔和阴影；硬投影只允许「偏移 + 实色 + 零模糊」")
    for alias in (".badge-up{", ".badge-down{", ".badge-mid{", ".badge.b-up", ".badge.b-down"):
        if alias in brand_mini:
            problems.append(f"品牌层又出现行情词徽章别名 {alias}（状态色与涨跌色会串轴）")
    if "--market-up" in minified_design_tokens_css() or "--market-down" in minified_design_tokens_css():
        problems.append("令牌层又出现 --market-up/--market-down 行情词别名")

    generator_report = {}
    for skill in HTML_REPORT_SKILLS:
        scripts = skill_scripts(skill)
        exempt = skill in FORBIDDEN_EXEMPT_SKILLS
        entry: dict = {"tier": "豁免" if exempt else tier_for_skill(skill), "forbidden_gate": not exempt}
        if not scripts:
            problems.append(f"{skill} 在 scripts/ 下找不到任何生成脚本")
            continue
        texts = [(path, path.read_text(encoding="utf-8")) for path in scripts]
        entry["modules"] = [path.name for path, _ in texts]
        entry["largest_module"] = max(
            ((path.name, len(src.splitlines())) for path, src in texts), key=lambda item: item[1]
        )

        entry["uses_shared_forbidden"] = any(
            re.search(r'^FORBIDDEN(?:_TERMS)?\s*=\s*forbidden_terms\("\w+"\)', src, re.M)
            for _, src in texts
        )
        entry["uses_shared_css"] = any("inject_shared_css" in src for _, src in texts)
        entry["inlines_forbidden_literal"] = any(
            re.search(r"^FORBIDDEN(?:_TERMS)?\s*=\s*\(", src, re.M) for _, src in texts
        )
        entry["reinlines_shell"] = sorted(
            {needle for _, src in texts for needle in SHELL_NEEDLES if needle in src}
        )
        entry["reinlines_components"] = sorted(
            {needle for _, src in texts for needle in COMPONENT_NEEDLES if needle in src}
        )

        inline_tokens: list[str] = []
        found_root = False
        for _, src in texts:
            # f-string 模板里花括号是双写的，取窗口还原后再匹配
            window = src.replace("{{", "{").replace("}}", "}")
            for match in re.finditer(r":root\s*\{([^}]*)\}", window, re.S):
                found_root = True
                inline_tokens.extend(re.findall(r"--[a-z0-9-]+", strip_css_comments(match.group(1))))
        if not found_root:
            problems.append(f"{skill} 模板里找不到 :root 占位，令牌注入会失败")
        entry["inline_token_count"] = len(inline_tokens)

        if exempt:
            # 豁免技能：不得声称使用禁词门禁（扫描冻结原文只会命中不可避免的引用），
            # 但必须在脚本里保留固定的「报告性质」声明。
            if entry["uses_shared_forbidden"]:
                problems.append(f"{skill} 是禁词豁免技能，不应加载禁词 tier（报告逐字引用冻结原文）")
            entry["has_disclaimer"] = any(EXEMPT_DISCLAIMER in src for _, src in texts)
            if not entry["has_disclaimer"]:
                problems.append(
                    f"{skill} 缺少固定声明「{EXEMPT_DISCLAIMER}」——它替代禁词硬门禁，必须留在脚本里"
                )
        else:
            entry["has_disclaimer"] = any(EXEMPT_DISCLAIMER in src for _, src in texts)
            if not entry["uses_shared_forbidden"]:
                problems.append(f"{skill} 未从共享层加载禁词 tier")
        if entry["inlines_forbidden_literal"]:
            problems.append(f"{skill} 把禁词表内联回脚本了")
        if not entry["uses_shared_css"]:
            problems.append(f"{skill} 未接入共享注入入口 inject_shared_css（令牌 + 外壳）")
        if inline_tokens:
            problems.append(f"{skill} 模板里又内联了 {len(inline_tokens)} 个令牌定义")
        if entry["reinlines_shell"]:
            problems.append(
                f"{skill} 又把页面骨架内联回脚本了：{', '.join(entry['reinlines_shell'])}"
            )
        if entry["reinlines_components"]:
            problems.append(
                f"{skill} 又把组件层内联回脚本了：{', '.join(entry['reinlines_components'])}"
            )
        oversize = [
            (name, lines) for name, lines in
            ((path.name, len(src.splitlines())) for path, src in texts)
            if lines > MAX_SCRIPT_LINES
        ]
        if oversize:
            problems.append(
                f"{skill} 有模块超过 {MAX_SCRIPT_LINES} 行，疑似重新长回巨型单文件："
                + ", ".join(f"{name}={lines}" for name, lines in oversize)
            )

        entry["inline_css_chars"] = sum(inline_css_chars(src) for _, src in texts)
        generator_report[skill] = entry

    report["generators"] = generator_report

    canonical = SHARED_DIR / "technical-analysis.md"
    for skill in SKILLS_WITH_TECHNICAL_ANALYSIS:
        local = SKILLS_DIR / skill / "references" / "technical-analysis.md"
        if not local.is_file():
            continue
        text = local.read_text(encoding="utf-8")
        if "_shared/technical-analysis.md" not in text:
            problems.append(f"{skill} 的本地技术面文件没有指向共享层，可能是完整副本")
        elif canonical.is_file() and len(text) >= len(canonical.read_text(encoding="utf-8")):
            problems.append(f"{skill} 的本地技术面文件与共享层等长，疑似未收敛为指路文件")

    report["skill_md_lines"] = {
        path.parent.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in sorted(SKILLS_DIR.glob("*/SKILL.md"))
    }
    report["design_tokens_chars"] = len(design_tokens_css())
    return problems, report


def main() -> int:
    parser = argparse.ArgumentParser(description="共享层漂移检查")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出完整报告")
    args = parser.parse_args()

    problems, report = check()

    if args.json:
        print(json.dumps({"problems": problems, "report": report}, ensure_ascii=False, indent=2))
        return 1 if problems else 0

    print("共享层漂移检查")
    print("=" * 62)
    selftest_data = report.get("shared_selftest", {})
    tiers = selftest_data.get("tiers", {})
    if tiers:
        print("禁词 tier 词条数：" + "  ".join(f"{name}={count}" for name, count in tiers.items()))
    print(f"设计令牌文件：{report.get('design_tokens_chars', 0)} 字符（注入时压缩）")
    print(f"报告外壳文件：{report.get('shell_css_chars', 0)} 字符（注入时压缩）")
    print(f"组件层文件：  {report.get('components_css_chars', 0)} 字符（注入时压缩）")
    print(f"品牌层合计：  {report.get('brand_css_chars', 0)} 字符（外壳 + 组件）")
    print()

    print(f"{'技能':38s} {'tier':9s} {'禁词':4s} {'共享CSS':8s} {'内联CSS':>8s} {'模块':>4s} {'最大模块':>16s}")
    print("-" * 92)
    for skill, entry in report.get("generators", {}).items():
        name, lines = entry.get("largest_module", ("-", 0))
        print(
            f"{skill:38s} {entry['tier']:9s} "
            f"{'是' if entry['uses_shared_forbidden'] else ('豁免' if not entry.get('forbidden_gate', True) else '否'):4s} "
            f"{'是' if entry['uses_shared_css'] else '否':8s} "
            f"{entry['inline_css_chars']:8d} "
            f"{len(entry.get('modules', [])):4d} "
            f"{f'{name}={lines}':>16s}"
        )
    print()
    exempt = [s for s in report.get("generators", {}) if not report["generators"][s].get("forbidden_gate", True)]
    if exempt:
        print("禁词豁免技能（报告逐字引用冻结原文，改用固定「报告性质」声明）：" + "、".join(exempt))
        print()

    sizes = report.get("skill_md_lines", {})
    if sizes:
        print("SKILL.md 行数（用于观察 changelog 是否膨胀）：")
        for name, lines in sizes.items():
            flag = "  ← 偏长，考虑把实测经验移入 references/" if lines > 200 else ""
            print(f"  {name:40s} {lines:4d}{flag}")
        print()

    if problems:
        print("发现漂移：")
        for item in problems:
            print(f"  ✗ {item}")
        return 1

    print("✓ 未发现漂移：禁词、设计令牌、页面骨架、技术面口径均来自 skills/_shared/。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
