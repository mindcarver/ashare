#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资本环境仪表盘的整页 HTML 模板（拆分自 render.py，审计 P2-5）。

模板与渲染逻辑分离：本文件只放一个字符串常量，不放任何逻辑。
设计令牌与报告外壳是空占位（:root{}）：渲染末尾由 ashare_shared.inject_shared_css()
注入 _shared/design-tokens.css、shell.css 与 components.css，不要在模板里填回色值或骨架规则。

v2（2026-09-10）：品牌层改在 </head> 之前注入，即排在本模板 <style> **之后**，
因此 .cell / .badge / .matrix-* / callout 等组件骨架已全部收归共享层。
本模板只保留资本环境独有的内部结构：tw-*（研判/风险）、sa-*（板块建议）、
an-*（每格 AI 分析摘要）、cell-head/-name/-evidence，以及单元格的紧凑内边距。
"""

# ============ 整页模板 ============
PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>资本环境仪表盘 · {{AS_OF}}</title>
<meta name="description" content="全球、美国、中国、韩国资本环境的多维状态与证据（内部研究工具）" />
<meta name="robots" content="noindex, nofollow" />
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
:root{}
main{min-height:100vh}
.container{max-width:1180px;margin:0 auto;padding:32px 20px 56px}

/* 概览卡内文（.summary-box 骨架来自共享组件层） */
.summary-box .overview{font-family:var(--font-body);font-size:15px;color:var(--ink);margin:0}
.summary-box .disclaimer{margin-top:8px;font-family:var(--font-ui);font-size:11px;color:var(--ink-tertiary)}

/* —— AI 研判 / 风险 / 板块建议三卡的内部结构（卡骨架来自共享层） —— */
.tw-head{font-family:var(--font-display);font-size:13px;font-weight:700;letter-spacing:.01em;color:var(--ink);margin-bottom:10px}
.tw-list{display:flex;flex-direction:column;gap:8px}
.tw-item{display:flex;align-items:flex-start;gap:9px;font-family:var(--font-body);font-size:13px;line-height:1.65;color:var(--ink-secondary)}
.tw-tag{flex:0 0 auto;background:var(--rule);color:var(--paper);padding:3px 6px;font-family:var(--font-mono);font-size:10px;font-weight:700;letter-spacing:.08em;line-height:1;margin-top:2px}
.tw-txt{color:var(--ink-secondary)}

/* 风险清单：三档标题色由共享层 .risk-high/-medium/-low 提供，标签退成空心 */
.risk-section{margin-bottom:12px}
.risk-section:last-child{margin-bottom:0}
.risk-title{font-family:var(--font-display);font-size:12px;font-weight:700;margin-bottom:6px}
.risk-section .tw-item{font-size:12.5px}
.risk-section .tw-tag{background:transparent;border:var(--hair) solid var(--line);color:var(--ink-tertiary)}

/* 板块倾向建议：按市场分组，每条带证据与证伪条件 */
.sa-disclaimer{margin:0 0 10px;font-size:11px;color:var(--ink-tertiary);line-height:1.6}
.sa-mkt{margin-bottom:12px;border-top:var(--hair) dashed var(--line);padding-top:9px}
.sa-mkt:first-of-type{border-top:none;padding-top:0}
.sa-mkt-name{font-family:var(--font-display);font-size:13px;font-weight:700;color:var(--ink);display:inline-block;margin-right:8px}
.sa-mkt-date{font-family:var(--font-mono);font-size:11px;color:var(--ink-tertiary)}
.sa-list{display:flex;flex-direction:column;gap:8px;margin-top:6px}
.sa-item{border:var(--hair) solid var(--line);padding:9px 11px;background:var(--paper-2)}
.sa-item .sa-sector{font-family:var(--font-display);font-size:13px;font-weight:700;color:var(--ink)}
.sa-item .sa-stance{float:right;padding:3px 7px;font-family:var(--font-mono);font-size:10px;font-weight:700;letter-spacing:.06em;margin-left:8px;border:var(--hair) solid currentColor}
.sa-item .sa-stance.st-up{background:var(--gain-soft);color:var(--gain)}
.sa-item .sa-stance.st-mid{background:var(--paper);color:var(--ink-secondary)}
.sa-item .sa-stance.st-down{background:var(--loss-soft);color:var(--loss)}
.sa-item .sa-ev,.sa-item .sa-tr{font-family:var(--font-body);font-size:11.5px;line-height:1.6;color:var(--ink-secondary);margin-top:5px}
.sa-item .sa-tr{color:var(--ink-tertiary)}
.sa-item .sa-ev b,.sa-item .sa-tr b{font-family:var(--font-ui);color:var(--ink);font-weight:700}

/* 每格 AI 分析摘要（透镜式） */
.cell-analysis{margin-top:8px;padding:9px 11px;background:var(--paper-2);border-left:3px solid var(--accent)}
.cell-analysis .an-head{font-family:var(--font-mono);font-size:9.5px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin-bottom:6px}
.cell-analysis .an-list{margin:0;padding:0;list-style:none;display:flex;flex-direction:column;gap:4px}
.cell-analysis .an-list li{display:flex;gap:7px;font-family:var(--font-body);font-size:11.5px;line-height:1.55;color:var(--ink-secondary)}
.cell-analysis .an-lens{flex:0 0 auto;background:var(--rule);color:var(--paper);padding:1px 5px;font-family:var(--font-mono);font-size:9.5px;font-weight:700;line-height:1.4;margin-top:1px}
.cell-analysis .an-txt{color:var(--ink-secondary)}

/* 28 格：单元格头部 + 证据脚注（.cell 骨架来自共享层，这里只收紧内边距） */
.market-grid .cell{padding:14px}
.cell-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:4px}
.cell-name{font-family:var(--font-display);font-size:12.5px;font-weight:600;color:var(--ink)}
.cell-evidence{margin-top:6px;padding-top:6px;border-top:var(--hair) dashed var(--line);font-family:var(--font-mono);font-size:9.5px;color:var(--ink-tertiary);line-height:1.4}

@media(max-width:760px){
  .container{padding:22px 14px 40px}
  .market-grid .cell{padding:12px}
}
</style>
</head>
<body>
<main>
<div class="container">
  <header class="masthead">
    <div><p class="eyebrow">GLOBAL / CAPITAL ENVIRONMENT</p><h1>资本环境</h1></div>
    <p class="asof">回放日期 {{AS_OF}}<br />静态点时快照<br />4 市场 × 7 维度</p>
  </header>

  <p class="snapshot-note">请用生成器的 <code>--as-of YYYY-MM-DD</code> 生成其他日期，避免 URL 参数显示未筛选数据。</p>

  <div class="summary-box">
    <p class="overview">{{OVERVIEW}}</p>
    <p class="disclaimer">{{DISCLAIMER}}</p>
  </div>

  {{TAKEAWAYS_HTML}}

  {{SECTOR_ADVICE_HTML}}

  {{DASHBOARD_CONTENT}}
</div>
</main>
<script>
const CELLS = {{CELLS_JSON}};

// 图表用色与 design-tokens.css 对齐：ok=state-ok / bad=state-bad / accent=钴蓝 / 网格=线色。
// 注意 ok/bad 是「可得性」语义（绿=可得、红=缺失），与 A 股红涨绿跌不是同一根轴。
const okColor = '#0e7a45', badColor = '#d2231b', inkColor = '#111417',
      secColor = '#4b5158', terColor = '#7d838a', accentColor = '#1b39d8', gridColor = '#c9c6c0';

function evid(cfg){
  const ev = document.getElementById(cfg.evId);
  if (!ev) return;
  if (!cfg.source) {
    ev.textContent = cfg.reason ? '状态：' + cfg.reason : '';
    return;
  }
  let s = '来源：' + cfg.source;
  if (cfg.observedAt) s += ' · 观测：' + cfg.observedAt;
  if (cfg.publishedAt) s += ' · 发布：' + cfg.publishedAt;
  if (cfg.processingVersion) s += ' · ' + cfg.processingVersion;
  ev.textContent = s;
}

function renderUnknown(el, cfg){
  if (!el) return;
  el.innerHTML = '<div class="unknown-msg">' + (cfg.reason || '无可得数值（非零值）') + '</div>';
}

function renderGauge(el, cfg){
  if (!el) return;
  const chart = echarts.init(el);
  const value = Number(cfg.value);
  chart.setOption({
    series: [{
      type: 'gauge',
      startAngle: 210, endAngle: -30, min: cfg.min || 0, max: cfg.max || 10,
      radius: '92%', center: ['50%','58%'],
      axisLine: {
        lineStyle: {
          width: 12,
          color: (cfg.sections || [[0.3, okColor], [0.7, secColor], [1, badColor]]).map(function(s){ return [s[0], s[1]]; })
        }
      },
      pointer: { itemStyle: { color: inkColor }, length: '62%', width: 4 },
      axisTick: { distance: -12, length: 3, lineStyle: { color: '#fff', width: 1 } },
      splitLine: { distance: -14, length: 10, lineStyle: { color: '#fff', width: 2 } },
      axisLabel: { distance: 18, color: terColor, fontSize: 8 },
      title: { offsetCenter: [0, '68%'], fontSize: 9, color: terColor },
      detail: {
        valueAnimation: true,
        formatter: function(v){ return v + (cfg.unit ? ' ' + cfg.unit : ''); },
        color: inkColor, fontSize: 15, fontWeight: 600, offsetCenter: [0, '40%']
      },
      data: [{ value: value, name: cfg.name || '' }]
    }]
  });
  window.addEventListener('resize', function(){ chart.resize(); });
}

function renderLine(el, cfg){
  if (!el) return;
  const chart = echarts.init(el);
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 14, top: 18, bottom: 22 },
    xAxis: { type: 'category', data: cfg.dates || [],
      axisLine: { lineStyle: { color: secColor } }, axisLabel: { color: terColor, fontSize: 8 }, axisTick: { show: false } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: terColor, fontSize: 8 }, splitLine: { lineStyle: { color: gridColor } } },
    series: [{
      type: 'line', data: cfg.values || [], smooth: true, symbol: 'circle', symbolSize: 5,
      lineStyle: { color: accentColor, width: 2 }, itemStyle: { color: accentColor },
      areaStyle: { color: { type: 'linear', x:0,y:0,x2:0,y2:1,
        colorStops: [{offset:0,color:'rgba(27,57,216,0.18)'},{offset:1,color:'rgba(27,57,216,0)'}] } },
      markLine: (cfg.markLines || []).map(function(m){
        return { name: m.label, yAxis: m.value, lineStyle: { color: badColor, type: 'dashed', width: 1 },
                 label: { formatter: m.label, color: badColor, fontSize: 8, position: 'insideEndTop' } };
      })
    }]
  });
  window.addEventListener('resize', function(){ chart.resize(); });
}

function renderBar(el, cfg){
  if (!el) return;
  const chart = echarts.init(el);
  chart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 44, right: 14, top: 16, bottom: 24 },
    xAxis: { type: 'category', data: cfg.categories || [],
      axisLabel: { color: terColor, fontSize: 9 }, axisTick: { show: false },
      axisLine: { lineStyle: { color: secColor } } },
    yAxis: { type: 'value', axisLabel: { color: terColor, fontSize: 8 }, splitLine: { lineStyle: { color: gridColor } } },
    series: [{
      type: 'bar', data: (cfg.values || []).map(function(v, i){
        return { value: v, itemStyle: { color: (cfg.colors || [])[i] || secColor, borderRadius: 0 } };
      }), barWidth: '46%',
      label: { show: true, position: 'top', color: inkColor, fontSize: 9, fontWeight: 600,
               formatter: function(p){ return p.value + (cfg.unit ? ' ' + cfg.unit : ''); } }
    }]
  });
  window.addEventListener('resize', function(){ chart.resize(); });
}

function renderCell(key, cfg){
  const id = key.replace('|', '-');
  const el = document.getElementById('ch-' + id);
  const ev = document.getElementById('ev-' + id);
  if (!el) return;
  if (cfg.type === 'unknown' || cfg.type === undefined) {
    renderUnknown(el, cfg);
  } else if (cfg.type === 'gauge') {
    renderGauge(el, cfg);
  } else if (cfg.type === 'line') {
    renderLine(el, cfg);
  } else if (cfg.type === 'bar') {
    renderBar(el, cfg);
  }
  evid(Object.assign({ evId: 'ev-' + id }, cfg));
}

Object.keys(CELLS).forEach(function(key){ renderCell(key, CELLS[key]); });
</script>
</body>
</html>
"""
