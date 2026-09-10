"""A 股技能库共享层。

5 个 HTML 报告生成器共用同一份禁词真源与同一套品牌设计系统（令牌 + 外壳 + 组件），
避免各写一份导致漂移。本模块零依赖，只用标准库。

用法（在各技能的 scripts/*.py 内）::

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
    from ashare_shared import forbidden_terms, find_forbidden, inject_shared_css

    FORBIDDEN = forbidden_terms("no_price")
    hit = find_forbidden(data, "no_price")
    html = inject_shared_css(html)   # 注入设计令牌 + 品牌设计系统

tier 取值见 forbidden-terms.json 的 _tiers 字段。
若 _shared 目录不存在（例如把单个技能目录单独拷走），本模块会抛出明确的
RuntimeError，提示改从仓库根运行或重新执行 ./install.sh —— 不做静默降级。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable, Iterator

SHARED_DIR = Path(__file__).resolve().parent
FORBIDDEN_PATH = SHARED_DIR / "forbidden-terms.json"
DESIGN_TOKENS_PATH = SHARED_DIR / "design-tokens.css"
SHELL_PATH = SHARED_DIR / "shell.css"
COMPONENTS_PATH = SHARED_DIR / "components.css"
TECHNICAL_ANALYSIS_PATH = SHARED_DIR / "technical-analysis.md"

_HEAD_END = "</head>"

_KNOWN_TIERS = ("core", "no_price", "strict", "score_ok")
_cache: dict[str, Any] = {}


def _load_manifest() -> dict[str, Any]:
    if "manifest" not in _cache:
        if not FORBIDDEN_PATH.is_file():
            raise RuntimeError(
                f"共享层缺失：找不到 {FORBIDDEN_PATH}。"
                "请在仓库根目录执行 ./install.sh 重新挂载技能，或从仓库内运行脚本。"
            )
        _cache["manifest"] = json.loads(FORBIDDEN_PATH.read_text(encoding="utf-8"))
    return _cache["manifest"]


def _flatten(group: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for value in group.values():
        if isinstance(value, dict):
            out.extend(_flatten(value))
        elif isinstance(value, list):
            out.extend(str(item) for item in value)
    return out


def forbidden_terms(tier: str = "core", extra: Iterable[str] = ()) -> tuple[str, ...]:
    """返回该 tier 的完整禁词表（隐含包含 core），按长度降序以便优先命中最具体的词。"""
    if tier not in _KNOWN_TIERS:
        raise ValueError(f"未知 tier: {tier!r}，可选 {_KNOWN_TIERS}")
    manifest = _load_manifest()
    terms = list(_flatten(manifest["core"]))
    if tier in ("no_price", "strict", "score_ok"):
        terms.extend(_flatten(manifest["no_price"]))
    if tier == "strict":
        terms.extend(_flatten(manifest["strict"]))
    terms.extend(str(t) for t in extra)
    seen: dict[str, None] = {}
    for term in terms:
        if term:
            seen.setdefault(term, None)
    return tuple(sorted(seen, key=len, reverse=True))


def tier_for_skill(skill_name: str, default: str = "core") -> str:
    """按技能名从 tier_map 取 tier。"""
    return str(_load_manifest().get("tier_map", {}).get(skill_name, default))


def _iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _iter_strings(item)


def find_forbidden(value: Any, tier: str = "core", extra: Iterable[str] = ()) -> str | None:
    """在任意嵌套结构里找第一个命中的禁词，返回该词；没有则返回 None。"""
    terms = forbidden_terms(tier, extra)
    for text in _iter_strings(value):
        for term in terms:
            if term in text:
                return term
    return None


def all_forbidden_hits(value: Any, tier: str = "core", extra: Iterable[str] = ()) -> list[str]:
    """返回命中的全部禁词（去重，保持首次出现顺序）。"""
    terms = forbidden_terms(tier, extra)
    hits: list[str] = []
    for text in _iter_strings(value):
        for term in terms:
            if term in text and term not in hits:
                hits.append(term)
    return hits


def assert_clean(value: Any, tier: str = "core", extra: Iterable[str] = (), label: str = "内容") -> None:
    """命中禁词即抛 ValueError，用于生成器的硬门禁。"""
    hit = find_forbidden(value, tier, extra)
    if hit:
        raise ValueError(f"{label}命中禁词：{hit}")


def design_tokens_css() -> str:
    """返回共享设计令牌的原始 CSS（含维护者注释，供人阅读）。"""
    if not DESIGN_TOKENS_PATH.is_file():
        raise RuntimeError(f"共享层缺失：找不到 {DESIGN_TOKENS_PATH}。")
    return DESIGN_TOKENS_PATH.read_text(encoding="utf-8")


def _strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _minify(css: str) -> str:
    """剥注释 + 压空白。只做空白级压缩，不改动声明格式。

    冒号与分号两侧空白本来就为零，因此压缩后与各生成器内联写法逐字节同构。
    缩进/换行在注释之后处理，顺序不能反（注释里含示例花括号）。
    """
    css = _strip_css_comments(css)
    css = re.sub(r"\s+", " ", css).strip()
    return re.sub(r"\s*([{};])\s*", r"\1", css)


def minified_design_tokens_css() -> str:
    """返回注入用版本（剥注释、压空白）。"""
    return _minify(design_tokens_css())


_ROOT_BLOCK_RE = re.compile(r":root\s*\{[^}]*\}")


def inject_design_tokens(html: str) -> str:
    """把 HTML 里第一个 :root{...} 令牌块替换为共享令牌（已剥注释）。

    在最终 HTML 字符串上做替换（而非在模板源码上），因此不受 f-string 花括号
    转义影响。注入的共享令牌是全库并集且取值一致，未引用的额外令牌不产生任何
    渲染效果。
    """
    tokens = minified_design_tokens_css()
    replaced, count = _ROOT_BLOCK_RE.subn(lambda _match: tokens, html, count=1)
    if count != 1:
        raise RuntimeError(
            "未在 HTML 中找到 :root 设计令牌块，无法注入共享令牌。"
            "请确认模板仍保留 :root 声明，或检查共享层是否被改动。"
        )
    return replaced


def shell_css() -> str:
    """返回共享报告外壳的原始 CSS（含维护者注释，供人阅读）。"""
    if not SHELL_PATH.is_file():
        raise RuntimeError(f"共享层缺失：找不到 {SHELL_PATH}。")
    return SHELL_PATH.read_text(encoding="utf-8")


def components_css() -> str:
    """返回共享组件层的原始 CSS（含维护者注释，供人阅读）。"""
    if not COMPONENTS_PATH.is_file():
        raise RuntimeError(f"共享层缺失：找不到 {COMPONENTS_PATH}。")
    return COMPONENTS_PATH.read_text(encoding="utf-8")


def minified_shell_css() -> str:
    """返回注入用版本（剥注释、压空白）。"""
    return _minify(shell_css())


def minified_components_css() -> str:
    """返回注入用版本（剥注释、压空白）。"""
    return _minify(components_css())


def brand_css() -> str:
    """品牌设计系统的完整 CSS（外壳 + 组件层），已剥注释压空白。"""
    return minified_shell_css() + minified_components_css()


def _insert_before_head(html: str, css: str, label: str) -> str:
    """把一段 CSS 包成 <style id="ashare-brand"> 插在 </head> 之前。

    v2 起品牌层改在 </head> 前注入，也就是**排在各技能自带的 <style> 之后**。
    这是有意为之：品牌层需要覆盖技能模板里遗留的旧组件样式，只有后写才生效。
    v1 曾插在 :root 之后（技能之前），那时外壳只能放技能绝不重定义的东西。
    """
    if _HEAD_END not in html:
        raise RuntimeError(
            f"未在 HTML 中找到 {_HEAD_END}，无法注入{label}。请确认模板含完整的 head 段。"
        )
    style = f'<style id="ashare-brand">{css}</style>'
    return html.replace(_HEAD_END, style + _HEAD_END, 1)


def inject_shell_css(html: str) -> str:
    """只注入页面骨架（外壳），仍插在 </head> 之前。

    生成器通常直接用 inject_shared_css() 一步到位；本函数保留给需要单独
    调整外壳的场景（如测试）。
    """
    return _insert_before_head(html, minified_shell_css(), "共享报告外壳")


def inject_brand_css(html: str) -> str:
    """注入完整的品牌设计系统（外壳 + 组件层）。"""
    return _insert_before_head(html, brand_css(), "品牌设计系统")


def inject_shared_css(html: str) -> str:
    """生成器推荐入口：先注入设计令牌，再注入品牌设计系统（外壳 + 组件）。

    等价于::

        inject_shared_css(html) == inject_brand_css(inject_design_tokens(html))
    """
    return inject_brand_css(inject_design_tokens(html))


def technical_analysis_path() -> Path:
    """返回共享技术面证据边界文档路径。"""
    return TECHNICAL_ANALYSIS_PATH


def selftest() -> dict[str, Any]:
    """自检：确认共享层可加载，返回各 tier 的词条数与资产就位情况。"""
    manifest = _load_manifest()
    return {
        "tiers": {t: len(forbidden_terms(t)) for t in _KNOWN_TIERS},
        "skills": manifest.get("tier_map", {}),
        "design_tokens_available": DESIGN_TOKENS_PATH.is_file(),
        "shell_available": SHELL_PATH.is_file(),
        "components_available": COMPONENTS_PATH.is_file(),
        "technical_analysis_available": TECHNICAL_ANALYSIS_PATH.is_file(),
        "brand_css_chars": len(brand_css()),
    }


if __name__ == "__main__":
    print(json.dumps(selftest(), ensure_ascii=False, indent=2))
