import importlib.util
import sys
import unittest

from pathlib import Path
from types import SimpleNamespace


TOOL = Path(__file__).resolve().parents[1] / "tools" / "render_reader_report.py"
spec = importlib.util.spec_from_file_location("render_reader_report", TOOL)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class ReaderLanguageGateTests(unittest.TestCase):
    def test_audit_vocabulary_is_rejected(self):
        for word in ("六轴", "象限", "审计", "验证链", "催化链", "交汇"):
            with self.assertRaises(ValueError, msg=word):
                reader.assert_reader_language(f"这段话里出现了{word}一词")

    def test_plain_market_language_passes(self):
        reader.assert_reader_language("涨停 47 家，晋级率 10.1%，资金转向汽车链。")


class PageCssScopingTests(unittest.TestCase):
    """共享品牌层有意注入在技能样式之后（ashare_shared v2 注释），其中的基础复位
    （h1,h2,h3,p{margin:0} 与 table/th/td 复位）会压掉任何裸元素选择器——读者版
    样式必须锚在 main 下以特异性取胜，否则整页段落/标题间距塌陷、表头变小字距体。
    """

    def test_page_local_css_is_main_scoped_and_late_layer_safe(self):
        sys.path.insert(0, str(TOOL.parent))
        try:
            html = reader.render_html(
                SimpleNamespace(md="2026-09-17", prev_md="2026-09-16"),
                "## 一、小节\n\n正文一段。\n\n| 甲 | 乙 |\n|---|---:|\n| x | 1 |\n",
            )
        finally:
            sys.path.remove(str(TOOL.parent))
        local = html.split("<style>", 1)[1].split("</style>", 1)[0]
        self.assertIn("main h2{", local)
        self.assertIn("main img{max-width:100%", local)
        for bare in ("h2{", "p{", "table{", "th{", "td{", "td:nth-child"):
            self.assertNotIn("\n" + bare, local, f"裸元素选择器会被品牌层压掉：{bare}")
        self.assertGreater(
            html.index('id="ashare-brand"'),
            html.index("</style>"),
            "品牌层应注入在页面样式之后（共享层 v2 契约）",
        )


class LhbAggregateTests(unittest.TestCase):
    def test_multi_list_stock_takes_max_abs_row_not_sum(self):
        rows = [
            {"SECURITY_CODE": "0001", "SECURITY_NAME_ABBR": "甲", "CHANGE_RATE": -9.3,
             "BILLBOARD_NET_AMT": -6.4e7, "EXPLANATION": "日跌幅偏离"},
            {"SECURITY_CODE": "0001", "SECURITY_NAME_ABBR": "甲", "CHANGE_RATE": -9.3,
             "BILLBOARD_NET_AMT": -6.4e7, "EXPLANATION": "日换手率达20%"},
            {"SECURITY_CODE": "0002", "SECURITY_NAME_ABBR": "乙", "CHANGE_RATE": 9.9,
             "BILLBOARD_NET_AMT": 3.9e8, "EXPLANATION": "日涨幅偏离"},
        ]
        ranked = reader.lhb_aggregate(rows)
        jia = next(a for a in ranked if a["name"] == "甲")
        self.assertAlmostEqual(jia["net"], -6.4e7)  # 不能把两行加成 -1.28e7
        self.assertEqual(ranked[-1]["name"], "乙")



if __name__ == "__main__":
    unittest.main()
