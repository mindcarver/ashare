#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成图表化资本环境仪表盘 HTML —— ashare-capital-environment-dashboard 的 CLI 入口。

本脚本已按审计 P2-5 拆分，本文件只负责 CLI 参数、编排与写盘：
  - schema.py    契约常量（市场/维度/标签/可用性）与日期解析
  - validate.py  输入读取、契约校验、点时筛选
  - derive.py    可用性映射、市场聚合、概览与研判清单
  - render.py    片段与整页渲染（末尾注入 _shared 设计令牌 + 报告外壳）

用法：
  1. 运行 --as-of YYYY-MM-DD 指定回放日期
  2. 可选 --cells cells.json 输入 28 格数据；每格可为单条记录或历史记录数组
     缺省时不使用内置数据，而是读取 examples/sample-cells.json（演示样例，非生产数据）
     - market: global | us | cn | kr
     - dimension: growth | inflation | liquidity | funding-price | risk-credit | market-breadth | institutional-positioning
     - type: gauge | line | bar | unknown（配置格式见 references/html-template.md 第三节）
  3. 运行：python3 scripts/gen_dashboard.py --cells cells.json --as-of YYYY-MM-DD --out report.html
  4. 自检（SKILL.md 第五节）：node --check + CELLS JSON 校验 + 禁词扫描
  5. present_files 交付

仅选择 publishedAt <= asOf 的记录；无合格记录会诚实降级为未知。
覆盖矩阵、市场聚合徽章、overview 覆盖等级全部自动生成，无需手改。
"""
import argparse
import sys
from datetime import date
from pathlib import Path

import _paths  # noqa: F401  确保 skills/_shared 在 sys.path 上
from ashare_shared import forbidden_terms

import render
from derive import avail_label, market_summary, overview
from schema import MARKETS, MKT_LABEL, parse_date
from validate import load_records, select_cells, validate_cells, validate_record_catalog

# 本技能完全不产生聚合评分，因此用一个禁用裸买卖词与评分词的 tier（strict）。
# 禁词表唯一真源：skills/_shared/forbidden-terms.json
FORBIDDEN_TERMS = forbidden_terms("strict")


def parse_args():
    parser = argparse.ArgumentParser(description="生成按发布日期截止筛选的资本环境快照 HTML")
    parser.add_argument("--as-of", default=date.today().isoformat(), help="回放截止日（YYYY-MM-DD，默认今天）")
    parser.add_argument("--cells", type=Path, help="可选 JSON 输入；每个  market|dimension 可为单条记录或按发布日期排序的记录数组")
    parser.add_argument("--out", type=Path, help="HTML 输出路径（默认 research/capital-environment/ 下按日期命名）")
    parser.add_argument("--check", action="store_true", help="只验证输入和点时选择，不写 HTML")
    return parser.parse_args()


def main():
    args = parse_args()
    as_of_date = parse_date(args.as_of, "--as-of")
    as_of = as_of_date.isoformat()

    records, sector_advice = load_records(args.cells)
    validate_record_catalog(records)
    cells = select_cells(records, as_of_date)
    validate_cells(cells, as_of_date)

    overview_text, all_unknown = overview(cells, as_of)
    html = render.build_html(cells, as_of, sector_advice, overview_text, all_unknown)

    if "{{" in html:
        raise RuntimeError("HTML 模板仍有未替换占位符")
    for term in FORBIDDEN_TERMS:
        if term in html:
            raise ValueError(f"生成内容命中禁词：{term}")

    if args.check:
        print(f"✅ 点时数据验证通过：asOf={as_of}，{len(cells)} 格，allUnknown={all_unknown}")
        return 0

    default_out = Path(__file__).resolve().parents[3] / "research" / "capital-environment" / f"ashare-capital-environment-dashboard-{as_of}.html"
    out = args.out or default_out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    print(f"✅ 已生成 {out}")
    print(f"   大小: {len(html)} 字节")
    print(f"   overview: {overview_text}")
    summary = market_summary(cells)
    for m in MARKETS:
        print(f"   {MKT_LABEL[m]}: {avail_label(summary[m])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
