"""共享层测试：禁词 tier、令牌注入、品牌设计系统（外壳 + 组件）注入，
以及「防止回退到重复实现」的守卫。

AntiRegressionTests 是本次审计的关键护栏——它们会在有人重新把禁词表、:root 令牌
或品牌层（shell.css / components.css）内联回生成器时直接失败，避免复制粘贴漂移重长。

v2（2026-09-10 换装）：品牌层由 inject_brand_css() 插在 </head> 之前，
即排在各技能自带 <style> 之后；断言随之从「紧跟 :root」改为「在 </head> 前」。
"""

import json
import re
import sys
import unittest
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parents[2]
SHARED_DIR = SKILLS_DIR / "_shared"
sys.path.insert(0, str(SHARED_DIR))

from ashare_shared import (  # noqa: E402
    all_forbidden_hits,
    brand_css,
    components_css,
    design_tokens_css,
    find_forbidden,
    forbidden_terms,
    inject_brand_css,
    inject_design_tokens,
    inject_shared_css,
    inject_shell_css,
    minified_components_css,
    minified_design_tokens_css,
    minified_shell_css,
    selftest,
    shell_css,
    tier_for_skill,
)

# 报告里的每一个字都由脚本生成，因此必须挂禁词 tier 硬门禁。
FORBIDDEN_GATED_SKILLS = (
    "ashare-capital-environment-dashboard",
    "ashare-daily-market-review",
    "ashare-company-research",
    "ashare-news-investment-targets",
)

# 逐字引用用户当时冻结的研究原文（假设/催化剂/证伪条件），审查性引用不可改写，
# 因此无法对报告文字设禁词硬门禁——改用固定「报告性质」声明替代（见 SKILL.md 第五节）。
# 它仍然必须接入共享令牌与外壳，也要接受「不得体积回涨」的护栏。
FORBIDDEN_EXEMPT_SKILLS = ("ashare-research-journal",)

# 全部产出 HTML 报告、因而必须接入共享设计系统（令牌 + 外壳）的技能。
HTML_SKILLS = FORBIDDEN_GATED_SKILLS + FORBIDDEN_EXEMPT_SKILLS


def skill_sources(skill):
    """技能 scripts/ 下全部 .py 的 (路径, 文本)，按文件名排序。

    生成器已按审计 P2-5 拆分为多个同目录模块（schema/validate/derive/render…），
    只读入口脚本会漏检——漂移可能藏在任何一个模块里。
    """
    return [
        (path, path.read_text(encoding="utf-8"))
        for path in sorted((SKILLS_DIR / skill / "scripts").glob("*.py"))
    ]


# 单文件上限：拆分后任一模块都不该再长成巨型脚本（审计 P2-5 的回归护栏）。
# 当前最大的模块是 daily 的 validate.py（630 行）——它是内聚的一整套契约校验，
# 再往下切只会出现循环导入。上限留出余量，但仍能拦住「长回 1761 行」的倒退。
MAX_SCRIPT_LINES = 700


class ForbiddenTierTests(unittest.TestCase):
    def test_tiers_are_cumulative(self):
        for tier in ("no_price", "strict", "score_ok"):
            core = set(forbidden_terms("core"))
            self.assertTrue(core <= set(forbidden_terms(tier)), f"{tier} 必须包含 core")

    def test_score_ok_allows_score_aggregate_but_strict_does_not(self):
        """新闻脚本有 100 分评分模型（总分合法）；资本面板不产生评分（总分非法）。"""
        self.assertNotIn("总分", forbidden_terms("score_ok"))
        self.assertIn("总分", forbidden_terms("strict"))

    def test_price_anchors_are_banned_in_every_non_core_tier(self):
        for tier in ("no_price", "strict", "score_ok"):
            terms = forbidden_terms(tier)
            for term in ("止损", "止盈", "买入观察价", "目标价位", "数据为估算"):
                self.assertIn(term, terms, f"{tier} 必须禁止 {term}")

    def test_terms_sorted_longest_first(self):
        terms = forbidden_terms("strict")
        self.assertEqual(list(terms), sorted(terms, key=len, reverse=True))

    def test_unknown_tier_raises(self):
        with self.assertRaises(ValueError):
            forbidden_terms("not_a_tier")

    def test_find_forbidden_walks_nested_structures(self):
        payload = {"a": [{"b": "正常内容"}], "c": {"d": ["建议买入 某股"]}}
        self.assertEqual(find_forbidden(payload, "core"), "建议买入")
        self.assertIsNone(find_forbidden({"a": ["正常内容"]}, "strict"))

    def test_all_forbidden_hits_reports_every_term(self):
        hits = all_forbidden_hits({"x": "建议买入 且 保证收益"}, "core")
        self.assertIn("建议买入", hits)
        self.assertIn("保证收益", hits)

    def test_tier_map_covers_every_gated_generator_skill(self):
        for skill in FORBIDDEN_GATED_SKILLS:
            self.assertIn(tier_for_skill(skill), ("no_price", "strict", "score_ok"))
        # 豁免技能不应被登记进 tier_map：它不加载禁词，登记反而会误导后来者。
        for skill in FORBIDDEN_EXEMPT_SKILLS:
            self.assertEqual(tier_for_skill(skill), "core")
            self.assertNotIn(skill, selftest()["skills"])


class DesignTokenTests(unittest.TestCase):
    def test_minified_tokens_are_comment_free_and_compact(self):
        css = minified_design_tokens_css()
        self.assertNotIn("/*", css)
        self.assertNotIn("\n", css)
        self.assertNotIn(": ", css.split(":root")[1] if ":root" in css else css)
        self.assertTrue(css.startswith(":root{"))

    def test_minified_keeps_compact_declaration_format(self):
        """注入产物必须与生成器内联格式逐字节同构，测试里已有断言依赖「冒号后无空格」。"""
        css = minified_design_tokens_css()
        for token in ("--ink:#111417", "--paper:#ffffff", "--line:#c9c6c0", "--accent:#1b39d8"):
            self.assertIn(token, css)

    def test_generators_do_not_inline_token_definitions(self):
        """护栏：模板里只允许留空的 :root{} 占位，不得再内联具体色值。

        拆分后模板可能落在任一模块（如 capital 的 page_template.py），故按技能聚合检查：
        全技能至少有一处 :root{} 占位，且没有任何一处 :root{--…}。
        """
        for skill in HTML_SKILLS:
            empty_root = 0
            for path, src in skill_sources(skill):
                # f-string 模板里花括号是双写的，取窗口还原后再匹配
                window = src.replace("{{", "{").replace("}}", "}")
                self.assertNotIn(
                    ":root{--",
                    window,
                    f"{skill}/{path.name} 又内联了令牌定义；真源是 skills/_shared/design-tokens.css",
                )
                empty_root += len(re.findall(r":root\s*\{\s*\}", window))
            self.assertGreaterEqual(
                empty_root, 1, f"{skill} 缺少 :root{{}} 占位，共享令牌注入会失败"
            )

    def test_shared_tokens_define_the_v2_palette(self):
        """共享令牌必须提供 ASHARE EDITORIAL 的浅色瑞士色板（白纸黑字 + 三轴语义色）。"""
        shared = dict(re.findall(r"(--[a-z0-9-]+):([^;}]+)", minified_design_tokens_css()))
        expected = {
            "--canvas": "#e9e6e0",
            "--paper": "#ffffff",
            "--paper-2": "#f3f1ed",
            "--ink": "#111417",
            "--ink-secondary": "#4b5158",
            "--ink-tertiary": "#7d838a",
            "--line": "#c9c6c0",
            "--rule": "#111417",
            "--red": "#d2231b",
            "--green": "#0e7a45",
            "--gain": "var(--red)",
            "--loss": "var(--green)",
            "--accent": "#1b39d8",
            "--gold": "#a9761a",
            "--state-ok": "#0e7a45",
            "--state-warn": "var(--gold)",
            "--state-bad": "var(--red)",
            "--font-body": '"Noto Serif SC","Songti SC",STSong,serif',
            "--rule-w": "2px",
            "--shadow-off": "7px",
            "--grid": "32px",
        }
        for name, value in expected.items():
            self.assertIn(name, shared, f"{name} 丢失")
            self.assertEqual(shared[name], value, f"{name} 取值被改动")

    def test_tokens_drop_market_word_aliases(self):
        """护栏：旧版把「可得」命名为 --market-up（取绿色），与红涨绿跌相反。

        v2 起该别名必须保持删除状态——一旦有人重新引入，状态色与涨跌色就会再次串轴。
        """
        css = minified_design_tokens_css()
        for banned in ("--market-up", "--market-down"):
            self.assertNotIn(banned, css, f"令牌层又出现了行情词别名 {banned}")

    def test_raw_tokens_keep_maintainer_notes_that_injection_strips(self):
        """原始令牌文件保留维护者注释（解释为何删掉 --market-up）；注入时剥除。"""
        self.assertIn("/*", design_tokens_css())
        self.assertNotIn("/*", minified_design_tokens_css())

    def test_inject_replaces_root_block(self):
        html = "<html><head><style>:root{--ink:#000000}body{color:red}</style></head></html>"
        out = inject_design_tokens(html)
        self.assertIn("--ink:#111417", out)
        self.assertNotIn("--ink:#000000", out)
        self.assertIn("body{color:red}", out)

    def test_inject_raises_when_no_root(self):
        with self.assertRaises(RuntimeError):
            inject_design_tokens("<html><head></head></html>")

    def test_selftest_reports_all_assets_present(self):
        report = selftest()
        self.assertTrue(report["design_tokens_available"])
        self.assertTrue(report["shell_available"])
        self.assertTrue(report["components_available"])
        self.assertTrue(report["technical_analysis_available"])
        self.assertGreater(report["brand_css_chars"], 0)
        # tier_map 只登记需要禁词硬门禁的技能；research-journal 是豁免者，不在此列。
        self.assertEqual(len(report["skills"]), len(FORBIDDEN_GATED_SKILLS))


class ShellTests(unittest.TestCase):
    """共享报告外壳（页面骨架）的注入行为与内容护栏。"""

    def test_shell_loadable_and_comment_free_when_minified(self):
        raw = shell_css()
        self.assertIn(".masthead{", raw)
        self.assertIn("box-sizing:border-box", raw)
        mini = minified_shell_css()
        self.assertNotIn("/*", mini)
        self.assertNotIn("\n", mini)

    def test_shell_contains_every_shared_skeleton_rule(self):
        mini = minified_shell_css()
        for rule in (
            "*{box-sizing:border-box}",
            "body:before{",
            ".masthead{",
            ".eyebrow{",
            ".badge{",
            "@media(max-width:760px){.masthead{display:block}",
        ):
            self.assertIn(rule, mini, f"共享外壳缺少 {rule}")

    def test_shell_has_no_forbidden_terms(self):
        """外壳会注入每一份报告，自身不得含禁词（最严 tier 兜底检查）。"""
        self.assertIsNone(find_forbidden(shell_css(), "strict"))

    def test_inject_shell_lands_before_head_end(self):
        """v2：品牌层插在 </head> 之前，也就是**排在技能自带 <style> 之后**。

        这是有意为之——品牌层要能覆盖技能模板里遗留的旧组件样式，只有后写才生效。
        """
        html = "<html><head><style>:root{}main{x:1}</style></head><body>hi</body></html>"
        out = inject_shell_css(html)
        self.assertIn("*{box-sizing:border-box}", out)
        self.assertLess(
            out.index("main{x:1}"), out.index("*{box-sizing:border-box}"),
            "外壳必须排在模板自有规则之后，否则压不住遗留的旧组件样式",
        )
        self.assertLess(
            out.index("*{box-sizing:border-box}"), out.index("</head>"),
            "外壳必须在 </head> 之前闭合，否则不生效",
        )
        self.assertLess(out.index("</head>"), out.index("<body>"))

    def test_inject_shell_raises_without_head(self):
        with self.assertRaises(RuntimeError):
            inject_shell_css("<html><head><style>:root{}</style></html>")

    def test_inject_shared_css_does_tokens_then_brand(self):
        html = "<html><head><style>:root{}body{color:red}</style></head></html>"
        out = inject_shared_css(html)
        self.assertIn("--ink:#111417", out)
        self.assertIn("*{box-sizing:border-box}", out)
        self.assertIn(".matrix-cell.a{", out)
        self.assertLess(
            out.index("--ink:#111417"), out.index("<style id=\"ashare-brand\">"),
            "令牌必须先于品牌层注入",
        )
        self.assertIn("body{color:red}", out)

    def test_selftest_reports_shell_present(self):
        self.assertTrue(selftest()["shell_available"])


class ComponentsTests(unittest.TestCase):
    """共享组件层（品牌设计系统的主体）的内容与注入护栏。"""

    def test_components_loadable_and_comment_free_when_minified(self):
        raw = components_css()
        self.assertIn(".metric-card", raw)
        mini = minified_components_css()
        self.assertNotIn("/*", mini)
        self.assertNotIn("\n", mini)

    def test_components_carry_the_brutalist_identity(self):
        """柔和粗野主义的三条硬约束：方角、两档边框、单一硬投影。"""
        mini = minified_components_css()
        for needle in (
            ".panel,.card,.cell,.candidate-card,.signal,.empty-state,.no-data,.matrix-wrap,.source-box{",
            "border:var(--hair) solid var(--rule)",
            "box-shadow:var(--shadow-off) var(--shadow-off) 0 var(--shadow)",
            "border-radius:0",
            ".matrix-cell.a{background:var(--state-ok-soft)",
            ".matrix-cell.u{background:var(--state-bad-soft)",
            ".badge.b-ok,.badge-available,.badge-fact,.badge.b-pass{background:var(--state-ok-soft)",
            ".badge.b-warn,.badge-partial,.badge-inference{background:var(--state-warn-soft)",
            ".badge.b-bad,.badge-unknown,.badge-judgment,.badge.b-fail{background:var(--state-bad-soft)",
            ".summary-box,.takeaway-box,.risk-box,.sector-advice-box,.chain,.signal-area,.notice{",
        ):
            self.assertIn(needle, mini, f"组件层缺少 {needle}")

    def test_components_forbid_pill_badges_and_soft_shadows(self):
        """护栏：徽章必须是方角（不得退回胶囊），投影必须零模糊（不得退回柔和阴影）。"""
        mini = minified_components_css()
        self.assertNotIn("border-radius:9999px", mini)
        # 圆角只允许出现在环形图上（.donut 是几何需要，不是卡片/徽章）
        radius_rules = re.findall(r"[^{}]+?\{[^{}]*border-radius:50%[^{}]*\}", mini)
        self.assertTrue(radius_rules, "环形图圆角丢失")
        for rule in radius_rules:
            self.assertIn(".donut", rule, f"圆角只允许用于环形图，违规规则：{rule[:70]}")
        # 硬投影只有一种形态：偏移 + 实色 + 零模糊。带模糊的写法一律拦下。
        self.assertNotRegex(mini, r"box-shadow:\s*\d+px\s+\d+px\s+[1-9]\d*px")

    def test_components_have_no_market_word_aliases(self):
        """状态徽章只用 available/partial/unknown；行情词别名已下线。"""
        mini = minified_components_css()
        for banned in (".badge-up{", ".badge-down{", ".badge-mid{", ".badge.b-up", ".badge.b-down"):
            self.assertNotIn(banned, mini, f"组件层又出现了行情词徽章 {banned}")

    def test_components_have_no_forbidden_terms(self):
        self.assertIsNone(find_forbidden(components_css(), "strict"))

    def test_brand_css_is_shell_plus_components(self):
        self.assertEqual(brand_css(), minified_shell_css() + minified_components_css())

    def test_inject_brand_requires_head(self):
        with self.assertRaises(RuntimeError):
            inject_brand_css("<html><body>no head</body></html>")


class AntiRegressionTests(unittest.TestCase):
    """护栏：禁止把共享内容重新内联回生成器。"""

    def test_generators_do_not_reinline_forbidden_terms(self):
        for skill in FORBIDDEN_GATED_SKILLS:
            loaders = 0
            for path, src in skill_sources(skill):
                literal = re.search(r"^FORBIDDEN(?:_TERMS)?\s*=\s*\(", src, re.M)
                self.assertIsNone(
                    literal,
                    f"{skill}/{path.name} 又把禁词表内联回脚本了；必须改为 forbidden_terms(tier)，"
                    "真源是 skills/_shared/forbidden-terms.json",
                )
                loaders += len(re.findall(r'^FORBIDDEN(?:_TERMS)?\s*=\s*forbidden_terms\("\w+"\)', src, re.M))
            self.assertGreaterEqual(loaders, 1, f"{skill} 必须从共享层加载禁词 tier")

    def test_exempt_skill_declares_no_forbidden_gate_but_a_fixed_disclaimer(self):
        """豁免技能：不加载禁词 tier，但必须带固定的「报告性质」声明替代硬门禁。

        报告逐字引用冻结原文，扫描禁词只会命中不可避免的引用（例如用户自己写的
        「止损」），所以硬门禁在这里既不可行也无意义。替代方案是固定声明，
        且这条声明必须留在脚本里（而不是只在文档里），才拦得住后来者悄悄移除。
        """
        for skill in FORBIDDEN_EXEMPT_SKILLS:
            sources = skill_sources(skill)
            for path, src in sources:
                self.assertNotIn(
                    "forbidden_terms(",
                    src,
                    f"{skill}/{path.name} 引入了禁词门禁；豁免技能的报告逐字引用冻结原文，"
                    "应改用固定「报告性质」声明（见 SKILL.md 第五节）",
                )
                self.assertIsNone(
                    re.search(r"^FORBIDDEN(?:_TERMS)?\s*=\s*\(", src, re.M),
                    f"{skill}/{path.name} 内联了禁词表",
                )
            self.assertTrue(
                any("不构成投资建议" in src for _, src in sources),
                f"{skill} 缺少固定的「报告性质」声明（不构成投资建议）",
            )

    def test_generators_import_the_shared_layer(self):
        for skill in HTML_SKILLS:
            sources = skill_sources(skill)
            self.assertTrue(
                any("ashare_shared" in src for _, src in sources),
                f"{skill} 未引用共享层",
            )
            self.assertTrue(
                any("inject_shared_css" in src for _, src in sources),
                f"{skill} 未接入共享注入入口（inject_shared_css = 令牌 + 外壳）",
            )

    def test_generators_do_not_reinline_the_shared_shell(self):
        """护栏：页面骨架必须来自 shell.css，不得重新内联回任何模块。"""
        needles = (
            "box-sizing:border-box",
            ".masthead{",
            ".eyebrow{",
            ".asof{",
            ".lede{",
            "body:before{",
            "-webkit-font-smoothing:antialiased",
            "footer{",
        )
        for skill in HTML_SKILLS:
            for path, src in skill_sources(skill):
                for needle in needles:
                    self.assertNotIn(
                        needle,
                        src,
                        f"{skill}/{path.name} 又把共享外壳规则内联回脚本了（{needle}）；"
                        "真源是 skills/_shared/shell.css",
                    )

    def test_generators_do_not_reinline_the_component_layer(self):
        """护栏：组件词汇（面板/徽章/矩阵/磁贴/行式组件）必须来自 components.css。

        v2 起品牌层排在技能 <style> 之后，因此技能模板里**不应**再出现任何组件骨架；
        若重写回脚本，它会先于品牌层生效并被覆盖，等于隐藏的死代码。
        """
        needles = (
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
        for skill in HTML_SKILLS:
            for path, src in skill_sources(skill):
                for needle in needles:
                    self.assertNotIn(
                        needle,
                        src,
                        f"{skill}/{path.name} 又把组件层规则内联回脚本了（{needle}）；"
                        "真源是 skills/_shared/components.css",
                    )

    def test_no_skill_keeps_its_own_technical_analysis_copy(self):
        """技术面口径只允许存在一份：共享层。技能内只保留指路文件。"""
        canonical = SHARED_DIR / "technical-analysis.md"
        self.assertTrue(canonical.is_file())
        canonical_text = canonical.read_text(encoding="utf-8")
        for skill in ("ashare-company-research", "ashare-news-investment-targets"):
            local = SKILLS_DIR / skill / "references" / "technical-analysis.md"
            if local.is_file():
                text = local.read_text(encoding="utf-8")
                self.assertIn("_shared/technical-analysis.md", text, f"{skill} 的本地技术面文件必须是指路文件")
                self.assertLess(len(text), len(canonical_text), f"{skill} 不应再保留完整技术面规则副本")

    def test_no_generator_script_regrows_into_a_monolith(self):
        """护栏：P2-5 拆分后，任一脚本模块都不得再长回巨型单文件。

        校验、派生、渲染、CLI 已经各归其位；若某个模块逼近上限，说明新逻辑被塞回了
        错误的位置，应继续拆分而不是抬高上限。
        """
        for skill in HTML_SKILLS:
            sources = skill_sources(skill)
            self.assertTrue(sources, f"{skill} 未找到任何 scripts/*.py")
            for path, src in sources:
                lines = len(src.splitlines())
                self.assertLessEqual(
                    lines,
                    MAX_SCRIPT_LINES,
                    f"{skill}/{path.name} 已 {lines} 行（上限 {MAX_SCRIPT_LINES}）；"
                    "请按 schema/validate/derive/render 继续拆分，而不是扩容单文件",
                )

    def test_shared_layer_has_no_skill_md(self):
        """_shared 不是技能，不应被 install.sh 当作技能挂载。"""
        self.assertFalse((SHARED_DIR / "SKILL.md").exists())


if __name__ == "__main__":
    unittest.main()
