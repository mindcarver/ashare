#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""研究日志报告的整页模板（沿用 P2-5/P2-6 纪律，模板与渲染逻辑分离）。

本文件只放字符串常量，不放逻辑。设计令牌、页面骨架与组件层都是空占位（:root{} 与
零散的布局声明）：渲染末尾由 ashare_shared.inject_shared_css() 注入
_shared/design-tokens.css + shell.css + components.css。

**品牌系统 v2（2026-09-10）起，组件样式一律不放这里。** 品牌层插在 </head> 之前、
即排在本模板的 <style> 之后，对同名选择器有最终解释权；本文件里再写一份只会变成
永远不生效的死代码。这里只保留「复盘页独有、且品牌层不该知道」的两条：
冻结原文块与成功标准块。

配色口径提醒（易混）：A 股「红涨绿跌」——正收益/上涨用 --gain（红），负收益/下跌用
--loss（绿）。「可得/通过」等状态语义走 --state-ok/--state-bad，与涨跌是两条轴。
"""

# ============ 两个报告共用的布局（仅页面容器，组件与排版都在品牌层） ============
COMMON_CSS = """
main{max-width:1180px;margin:auto;padding:32px 20px 56px}
@media(max-width:760px){main{padding:22px 14px 40px}}
"""

# ============ 单条复盘专属：冻结原文块 ============
RECORD_CSS = """
.judge{font-family:var(--font-body);font-size:14px;line-height:1.8;color:var(--ink);margin:0}
.crit{display:inline-block;background:var(--paper-2);border:var(--hair) solid var(--rule);padding:5px 9px;
  font-family:var(--font-mono);font-size:12px;color:var(--ink);margin-top:5px}
"""

# ============ 统计看板专属：暂无独有样式 ============
# 命中率仪表 / 超额分布 / Brier 校准散点的容器都走品牌层的 .chart / .chart-grid.two，
# 指标卡走 .tiles / .tile。若将来需要看板专属样式，加在这里并同步 components.css 的保留项清单。
STATS_CSS = """
"""

# ============ 整页骨架 ============
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{{PAGE_TITLE}}</title>
<meta name="description" content="{{PAGE_DESC}}" />
<meta name="robots" content="noindex, nofollow" />
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
:root{}
{{COMMON_CSS}}
{{REPORT_CSS}}
</style>
</head>
<body>
<main>
<div class="container">
  <header class="masthead">
    <div><p class="eyebrow">{{EYEBROW}}</p><h1>{{H1}}</h1></div>
    <p class="asof">{{ASOF_LINE}}</p>
  </header>

  <p class="lede">{{LEDE}}</p>

{{BODY}}

  <p class="foot">{{FOOT}}</p>
</div>
</main>
<script>
{{SCRIPT}}
</script>
</body>
</html>
"""
