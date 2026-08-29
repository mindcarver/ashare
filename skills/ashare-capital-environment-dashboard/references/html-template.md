# HTML 模板（资本环境仪表盘 · 图表化）

> 自包含 HTML 模板，保留 AGUHOT 的 4×7 字段与覆盖语义，视觉系统对齐 `ashare-daily-market-review` 的“市场脉搏”HTML：深墨绿背景、米白纸张卡、宋体研报正文、金色眉题与硬投影。全部 28 格用 ECharts 图表渲染。
>
> 使用方法：
> 1. 复制模板到新文件 `ashare-capital-environment-dashboard-{YYYY-MM-DD}.html`
> 2. 替换占位符：`{{AS_OF}}` `{{OVERVIEW}}` `{{DISCLAIMER}}` `{{CELLS_JSON}}`
> 3. `{{CELLS_JSON}}` 是唯一的数据入口（见第三节配置格式），28 格全部由它驱动
> 4. 跑节点语法检查 → present_files 交付

## 一、图表类型约定

| 图表 | 用途 | 适用场景 |
|---|---|---|
| `gauge` | 仪表盘 | 单点观测值 + 参考区间（增长/通胀/风险偏好/机构持仓） |
| `line` | 趋势折线 | 有历史序列（流动性/资金价格/通胀趋势） |
| `bar` | 条形 | 分布类（市场宽度涨跌家数/占比） |
| `unknown` | 灰色占位 | 无数据格（显示原因，不画图） |

每格 HTML 结构（图表区 180px 高 + 证据脚注）：

```
┌─────────────────────────────┐
│ 维度名              [徽章]   │
│ ┌─────────────────────────┐ │
│ │      ECharts 图表       │ │
│ │     (gauge/line/bar)    │ │
│ └─────────────────────────┘ │
│ 来源：xxx 观测日：xxx 发布日：xxx │
└─────────────────────────────┘
```

## 二、骨架模板

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>资本环境仪表盘 · {{AS_OF}}</title>
<meta name="description" content="全球、美国、中国、韩国资本环境的多维状态与证据（内部研究工具）" />
<meta name="robots" content="noindex, nofollow" />
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<style>
:root{
  --ink:#13211f;
  --paper:#f6f1e7;
  --paper-2:#eee6d7;
  --line:#d8cdbb;
  --red:#bf332d;
  --green:#19724b;
  --gold:#ba8a35;
  --muted:#756f66;
  --canvas:#18221f;
  --surface-base:var(--paper);
  --surface-raised:var(--paper);
  --surface-muted:var(--paper-2);
  --ink-primary:var(--ink);
  --ink-secondary:#5f584e;
  --ink-tertiary:var(--muted);
  --border-hairline:var(--line);
  --brand:var(--gold);
  --brand-foreground:#18221f;
  --market-up:var(--green);
  --market-up-soft:#d8eedf;
  --market-down:var(--red);
  --market-down-soft:#edd8d2;
}
*{box-sizing:border-box}
body{margin:0;background:#18221f;color:var(--ink);font-family:"Noto Serif SC","Songti SC",STSong,serif;overflow-x:hidden;-webkit-font-smoothing:antialiased;}
body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.15;background-image:linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.04) 1px,transparent 1px);background-size:24px 24px}
main{min-height:100vh}
.container{max-width:1180px;margin:0 auto;padding:32px 20px 56px}
.badge{display:inline-flex;align-items:center;border-radius:9999px;padding:0.125rem 0.5rem;
  font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:0.7rem;line-height:1rem;white-space:nowrap}
.badge-up{background:var(--market-up-soft);color:var(--market-up)}
.badge-down{background:var(--market-down-soft);color:var(--market-down)}
.badge-mid{background:var(--surface-muted);color:var(--ink-secondary)}
.badge-muted{background:var(--surface-muted);color:var(--ink-tertiary)}
/* 覆盖矩阵 */
.matrix-wrap{display:grid;grid-template-columns:auto repeat(7,1fr);gap:4px;margin-top:10px;padding:20px;background:var(--paper);border:1px solid var(--line);box-shadow:5px 5px 0 rgba(12,18,16,.25);font-family:"SFMono-Regular",Consolas,monospace;font-size:0.68rem;color:var(--ink-secondary)}
.matrix-cell{display:flex;align-items:center;justify-content:center;padding:4px 2px;border-radius:4px;min-height:1.4rem;text-align:center}
.matrix-cell.a{background:var(--market-up-soft);color:var(--market-up)}
.matrix-cell.p{background:var(--surface-muted);color:var(--ink-secondary)}
.matrix-cell.u{background:var(--market-down-soft);color:var(--market-down)}
.matrix-cell.lbl{background:transparent;justify-content:flex-start;padding-left:2px;color:var(--ink-primary);font-weight:600}
.matrix-legend{display:flex;gap:0.75rem;margin:0.75rem 0 0;font-size:0.7rem;color:#cfc5b4}
.matrix-legend span{display:inline-flex;align-items:center;gap:4px}
.swatch{width:10px;height:10px;border-radius:2px;display:inline-block}
/* 摘要卡 */
.summary-box{background:#e3d4bc;border:1px solid var(--line);border-left:5px solid var(--gold);padding:20px;margin-top:10px;box-shadow:5px 5px 0 rgba(12,18,16,.25)}
.summary-box p{margin:0}
.summary-box .overview{font-size:0.875rem;color:var(--ink-secondary)}
.summary-box .disclaimer{margin-top:0.375rem;font-size:0.7rem;color:var(--ink-tertiary)}
/* 市场 section */
section.market{margin-top:2rem}
.market-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:0.75rem;padding-bottom:12px;border-bottom:1px solid rgba(248,242,230,.25)}
.market-head h2{font-size:1.25rem;font-weight:700;margin:0;color:#f8f2e6}
.market-grid{display:grid;gap:0.625rem}
@media (min-width:640px){.market-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media (min-width:1024px){.market-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
/* 维度格 */
.cell{border:1px solid var(--line);padding:14px;background:var(--paper);box-shadow:5px 5px 0 rgba(12,18,16,.25)}
.cell-head{display:flex;align-items:center;justify-content:space-between;gap:0.5rem;margin-bottom:0.25rem}
.cell-name{font-size:0.8rem;font-weight:500;color:var(--ink-primary)}
.chart-box{width:100%;height:180px}
.chart-box .unknown-msg{display:flex;align-items:center;justify-content:center;height:100%;color:var(--ink-tertiary);
  font-size:0.75rem;text-align:center;padding:0 0.5rem}
.cell-evidence{margin-top:0.25rem;padding-top:0.25rem;border-top:1px dashed var(--border-hairline);
  font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace;font-size:0.62rem;color:var(--ink-tertiary);line-height:1.3}
/* 与每日盘面复盘一致的页首 */
.masthead{color:#f8f2e6;border-bottom:1px solid rgba(248,242,230,.25);padding:0 0 24px;display:flex;justify-content:space-between;gap:24px;align-items:end}
.eyebrow{font:700 11px/1 "SFMono-Regular",Consolas,monospace;letter-spacing:.18em;color:#e3bc70;margin:0 0 12px}
.masthead h1{font-size:clamp(34px,6vw,68px);line-height:.95;letter-spacing:-.06em;margin:0}
.masthead .asof{font-size:14px;color:#cfc5b4;line-height:1.65;text-align:right;margin:0}
.snapshot-note{color:#cfc5b4;font-size:12px;line-height:1.7;margin:16px 0 24px}
@media(max-width:760px){.container{padding:22px 14px 40px}.masthead{display:block}.masthead .asof{text-align:left;margin-top:16px}.matrix-wrap{overflow-x:auto;padding:14px}.market-grid{grid-template-columns:1fr}.cell{padding:12px}}
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

  <!-- 覆盖矩阵：4市场 × 7维度 色块总览 -->
  <div class="matrix-wrap">
    <div class="matrix-cell lbl">市场/维度</div>
    <div class="matrix-cell lbl">增长</div>
    <div class="matrix-cell lbl">通胀</div>
    <div class="matrix-cell lbl">流动性</div>
    <div class="matrix-cell lbl">资金价格</div>
    <div class="matrix-cell lbl">风险偏好与信用</div>
    <div class="matrix-cell lbl">市场宽度</div>
    <div class="matrix-cell lbl">机构持仓与拥挤度</div>
    <div class="matrix-cell lbl">全球</div>
    <div class="matrix-cell {{GLOBAL|GROWTH_CLASS}}">▲</div>
    <div class="matrix-cell {{GLOBAL|INFLATION_CLASS}}">▲</div>
    <div class="matrix-cell {{GLOBAL|LIQUIDITY_CLASS}}">▲</div>
    <div class="matrix-cell {{GLOBAL|FUNDING_CLASS}}">▲</div>
    <div class="matrix-cell {{GLOBAL|RISK_CLASS}}">▲</div>
    <div class="matrix-cell {{GLOBAL|BREADTH_CLASS}}">▲</div>
    <div class="matrix-cell {{GLOBAL|POSITIONING_CLASS}}">▲</div>
    <div class="matrix-cell lbl">美国</div>
    <div class="matrix-cell {{US|GROWTH_CLASS}}">●</div>
    <div class="matrix-cell {{US|INFLATION_CLASS}}">●</div>
    <div class="matrix-cell {{US|LIQUIDITY_CLASS}}">●</div>
    <div class="matrix-cell {{US|FUNDING_CLASS}}">●</div>
    <div class="matrix-cell {{US|RISK_CLASS}}">●</div>
    <div class="matrix-cell {{US|BREADTH_CLASS}}">●</div>
    <div class="matrix-cell {{US|POSITIONING_CLASS}}">●</div>
    <div class="matrix-cell lbl">中国</div>
    <div class="matrix-cell {{CN|GROWTH_CLASS}}">●</div>
    <div class="matrix-cell {{CN|INFLATION_CLASS}}">●</div>
    <div class="matrix-cell {{CN|LIQUIDITY_CLASS}}">●</div>
    <div class="matrix-cell {{CN|FUNDING_CLASS}}">●</div>
    <div class="matrix-cell {{CN|RISK_CLASS}}">●</div>
    <div class="matrix-cell {{CN|BREADTH_CLASS}}">●</div>
    <div class="matrix-cell {{CN|POSITIONING_CLASS}}">●</div>
    <div class="matrix-cell lbl">韩国</div>
    <div class="matrix-cell {{KR|GROWTH_CLASS}}">●</div>
    <div class="matrix-cell {{KR|INFLATION_CLASS}}">●</div>
    <div class="matrix-cell {{KR|LIQUIDITY_CLASS}}">●</div>
    <div class="matrix-cell {{KR|FUNDING_CLASS}}">●</div>
    <div class="matrix-cell {{KR|RISK_CLASS}}">●</div>
    <div class="matrix-cell {{KR|BREADTH_CLASS}}">●</div>
    <div class="matrix-cell {{KR|POSITIONING_CLASS}}">●</div>
  </div>
  <div class="matrix-legend">
    <span><i class="swatch" style="background:var(--market-up-soft)"></i>可得</span>
    <span><i class="swatch" style="background:var(--surface-muted)"></i>部分</span>
    <span><i class="swatch" style="background:var(--market-down-soft)"></i>未知/失败/无法还原</span>
  </div>

  <!-- 各市场 section：每格一个 ECharts 容器 -->
  <div id="markets">
    <section class="market" data-market="global" aria-label="全球资本环境">
      <div class="market-head"><h2>全球</h2><span class="badge {{GLOBAL_MKT_CLASS}}">{{GLOBAL_MKT_LABEL}}</span></div>
      <div class="market-grid">
        <div class="cell" data-key="global|growth"><div class="cell-head"><span class="cell-name">增长</span><span class="badge {{CELL_CLASS}}">{{CELL_LABEL}}</span></div><div class="chart-box" id="ch-global-growth"></div><div class="cell-evidence" id="ev-global-growth"></div></div>
        <div class="cell" data-key="global|inflation"><div class="cell-head"><span class="cell-name">通胀</span><span class="badge {{CELL_CLASS}}">{{CELL_LABEL}}</span></div><div class="chart-box" id="ch-global-inflation"></div><div class="cell-evidence" id="ev-global-inflation"></div></div>
        <div class="cell" data-key="global|liquidity"><div class="cell-head"><span class="cell-name">流动性</span><span class="badge {{CELL_CLASS}}">{{CELL_LABEL}}</span></div><div class="chart-box" id="ch-global-liquidity"></div><div class="cell-evidence" id="ev-global-liquidity"></div></div>
        <div class="cell" data-key="global|funding-price"><div class="cell-head"><span class="cell-name">资金价格</span><span class="badge {{CELL_CLASS}}">{{CELL_LABEL}}</span></div><div class="chart-box" id="ch-global-funding-price"></div><div class="cell-evidence" id="ev-global-funding-price"></div></div>
        <div class="cell" data-key="global|risk-credit"><div class="cell-head"><span class="cell-name">风险偏好与信用</span><span class="badge {{CELL_CLASS}}">{{CELL_LABEL}}</span></div><div class="chart-box" id="ch-global-risk-credit"></div><div class="cell-evidence" id="ev-global-risk-credit"></div></div>
        <div class="cell" data-key="global|market-breadth"><div class="cell-head"><span class="cell-name">市场宽度</span><span class="badge {{CELL_CLASS}}">{{CELL_LABEL}}</span></div><div class="chart-box" id="ch-global-market-breadth"></div><div class="cell-evidence" id="ev-global-market-breadth"></div></div>
        <div class="cell" data-key="global|institutional-positioning"><div class="cell-head"><span class="cell-name">机构持仓与拥挤度</span><span class="badge {{CELL_CLASS}}">{{CELL_LABEL}}</span></div><div class="chart-box" id="ch-global-institutional-positioning"></div><div class="cell-evidence" id="ev-global-institutional-positioning"></div></div>
      </div>
    </section>
    <!-- 美国/中国/韩国 section 结构同上，id 前缀分别为 us- / cn- / kr- -->
  </div>
</div>
</main>
<script>
// ========== 数据入口：{{CELLS_JSON}} ==========
const CELLS = {{CELLS_JSON}};

// ========== 渲染引擎 ==========
const DIM_SHORT = {
  'global': 'global','us':'us','cn':'cn','kr':'kr'
};
const upColor = '#19724b', downColor = '#bf332d', inkColor = '#13211f',
      secColor = '#5f584e', terColor = '#756f66', lineColor = '#ba8a35';

function evid(cfg){
  const ev = document.getElementById(cfg.evId);
  if (!ev) return;
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
          color: (cfg.sections || [
            [0.3, upColor], [0.7, secColor], [1, downColor]
          ]).map(function(s){
            const span = s[1];
            const end = s[0];
            return [end, span];
          })
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
        color: inkColor, fontSize: 16, fontWeight: 600, offsetCenter: [0, '40%']
      },
      data: [{ value: value, name: cfg.name || '' }]
    }],
    graphic: (cfg.markers || []).map(function(m){
      const pct = (m.value - (cfg.min||0)) / ((cfg.max||10) - (cfg.min||0));
      const angle = (210 + (1 - pct) * 240) * Math.PI / 180;
      const cx = el.clientWidth / 2, cy = el.clientHeight * 0.58;
      const r = Math.min(el.clientWidth, el.clientHeight * 1.15) / 2 * 0.86;
      return {
        type: 'text',
        left: (cx + r * Math.sin(angle)) + 'px',
        top: (cy - r * Math.cos(angle)) + 'px',
        style: { text: m.label, fontSize: 9, fill: secColor },
        position: [0, -14]
      };
    })
  });
  window.addEventListener('resize', function(){ chart.resize(); });
}

function renderLine(el, cfg){
  if (!el) return;
  const chart = echarts.init(el);
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 40, right: 14, top: 18, bottom: 22 },
    xAxis: {
      type: 'category',
      data: cfg.dates || [],
      axisLine: { lineStyle: { color: secColor } },
      axisLabel: { color: terColor, fontSize: 8 },
      axisTick: { show: false }
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: terColor, fontSize: 8 },
      splitLine: { lineStyle: { color: '#e5dac7' } }
    },
    series: [{
      type: 'line', data: cfg.values || [], smooth: true, symbol: 'circle', symbolSize: 5,
      lineStyle: { color: lineColor, width: 2 },
      itemStyle: { color: lineColor },
      areaStyle: { color: { type: 'linear', x:0,y:0,x2:0,y2:1,
        colorStops: [{offset:0,color:'rgba(186,138,53,0.2)'},{offset:1,color:'rgba(186,138,53,0)'}] } },
      markLine: (cfg.markLines || []).map(function(m){
        return { name: m.label, yAxis: m.value, lineStyle: { color: downColor, type: 'dashed', width: 1 },
                 label: { formatter: m.label, color: downColor, fontSize: 8, position: 'insideEndTop' } };
      })
    }]
  });
  window.addEventListener('resize', function(){ chart.resize(); });
}

function renderBar(el, cfg){
  if (!el) return;
  const chart = echarts.init(el);
  chart.setOption({
    grid: { left: 44, right: 14, top: 16, bottom: 24 },
    xAxis: { type: 'category', data: cfg.categories || [],
      axisLabel: { color: terColor, fontSize: 9 }, axisTick: { show: false },
      axisLine: { lineStyle: { color: secColor } } },
    yAxis: { type: 'value', axisLabel: { color: terColor, fontSize: 8 },
      splitLine: { lineStyle: { color: '#e5dac7' } } },
    series: [{
      type: 'bar', data: (cfg.values || []).map(function(v, i){
        return { value: v, itemStyle: { color: (cfg.colors || [])[i] || secColor, borderRadius: [3,3,0,0] } };
      }), barWidth: '46%',
      label: { show: true, position: 'top', color: inkColor, fontSize: 9, fontWeight: 600 }
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
```

## 三、{{CELLS_JSON}} 配置格式（唯一数据入口）

```json
{
  "global|growth": {
    "type": "unknown",
    "reason": "全球参考系列待选定并核验历史覆盖，首版未纳入可审计来源。",
    "availability": "pending_review"
  },
  "us|growth": {
    "type": "gauge",
    "value": 1.5,
    "unit": "%",
    "min": 0,
    "max": 6,
    "name": "Q2 GDP年化",
    "sections": [[0.33, "#19724b"], [0.67, "#ba8a35"], [1, "#bf332d"]],
    "markers": [{ "value": 2.1, "label": "Q1 2.1%" }],
    "source": "us-bea（U.S. BEA, 二季度实际GDP年化季率）",
    "observedAt": "2026-06-30",
    "publishedAt": "2026-07-30",
    "processingVersion": "v1.0",
    "availability": "available"
  },
  "cn|liquidity": {
    "type": "line",
    "dates": ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"],
    "values": [9.0, 9.0, 8.5, 8.6, 8.6, 8.0],
    "unit": "%",
    "source": "cn-pbc（中国人民银行, M2同比）",
    "observedAt": "2026-06-30",
    "publishedAt": "2026-07-15",
    "processingVersion": "v1.0",
    "availability": "available"
  },
  "cn|market-breadth": {
    "type": "bar",
    "categories": ["上涨", "下跌", "平盘", "停牌"],
    "values": [4691, 728, 115, 6],
    "colors": ["#bf332d", "#19724b", "#756f66", "#d8cdbb"],
    "source": "cn-akshare-breadth（AkShare, 7/31收盘）",
    "observedAt": "2026-07-31",
    "publishedAt": "2026-07-31",
    "processingVersion": "v1.0",
    "availability": "available"
  }
}
```

字段说明：

| 字段 | 类型 | 说明 |
|---|---|---|
| `type` | string | `gauge` / `line` / `bar` / `unknown` |
| `value` | number | gauge 的指针值 |
| `unit` | string | 单位（% / 点 / x / 亿元） |
| `min`/`max` | number | gauge 量程 |
| `sections` | array | gauge 分段颜色 `[[0.33,"#19724b"],...]`（0-1 比例） |
| `markers` | array | gauge 参考标记 `[{value,label}]`（如历史均值/前值） |
| `dates`/`values` | array | line 的 x/y 数据 |
| `markLines` | array | line 参考线 `[{value,label}]`（如荣枯线 50） |
| `categories`/`values`/`colors` | array | bar 的分类/数值/颜色 |
| `reason` | string | unknown 格的展示原因 |
| `source` | string | 来源 id + 名称（必填） |
| `observedAt` / `publishedAt` | string | 观测日期 / 发布日期（ISO 或 YYYY-MM-DD） |
| `processingVersion` | string | 处理版本 |
| `availability` | string | `available`/`partial`/`unknown`/`failed`/`pending_review`/`incomplete_reconstruction` |
| `analysis` | array | **AI 分析摘要**（可选）：`[[透镜名, 一句话], ...]` 3-4 条，渲染为每格虚线框"AI 分析"区 |
| `takeaways` | array | **综合研判**（可选）：`[[标签, 一句话], ...]` 1 条/格，汇总进顶部"AI 综合研判"卡 |
| `risk` | object | **风险信号**（可选）：`{"level": "high"|"medium"|"low", "label": "标签", "text": "描述"}`，渲染为顶部"风险信号清单"卡三分层 + 每格维度名旁风险点（红/橙/绿） |

**analysis 写法纪律**（2026-08-02 实测）：
- 透镜名用 8 通用透镜（水平/趋势/结构/相对/预期差/政策含义/逆向/波动/局限）或维度特有视角
- 每条 = 判断 + 证据；代理口径必须说明；**禁止在字符串内用 ASCII 双引号**（会破坏生成脚本语法，用「」代替）

## 三·五、板块倾向建议层（sectorAdvice，2026-08-03 新增）

> 可选输出：仅当用户明确要求"投资建议/板块建议"时生成。渲染为"AI 综合研判卡"与覆盖矩阵之间的**板块倾向建议卡**（橙左边框）。

**数据位置**：`cells.json` 顶层与 28 格并列（`load_records` 会自动拆出 `sectorAdvice`，不参与 28 格校验）。支持两种包装：
- `{"cells": {...28格...}, "sectorAdvice": {...}}`
- `{...28格..., "sectorAdvice": {...}}`

**配置格式**：

```json
"sectorAdvice": {
  "disclaimer": "以下为基于资本环境证据的板块方向性研究参考，仅为建议，不构成投资建议或买卖指令，不保证未来表现。",
  "markets": [
    {"market": "中国", "date": "2026-08-03",
     "items": [
       {"sector": "核电/电网设备（政策+开工链）", "stance": "关注",
        "evidence": "国常会 8/3 核准 4 个核电项目、总投资超 1700 亿（中金岭南期货早班车）；8/3 核电、可控核聚变、电网设备领涨（界面新闻）",
        "trigger": "若新订单指数持续走弱、项目开工不及预期则降为中性"},
       {"sector": "存储芯片/半导体", "stance": "回避",
        "evidence": "8/3 存储芯片、HBM、玻纤领跌，科创50 -5.08%（金融界）；7 月费城半导体指数单月 -21%（智通财经）",
        "trigger": "若 AI 资本开支财报验证转好、半导体宽度回升则转中性"}
     ]}
  ]
}
```

**字段约束**：
| 字段 | 必填 | 说明 |
|---|---|---|
| `disclaimer` | 否 | 卡头固定免责声明；缺省用内置默认句 |
| `market` | 是 | 市场名（全球/美国/中国/韩国） |
| `date` | 否 | 板块观测日期 |
| `sector` | 是 | 板块/主题名（禁止个股） |
| `stance` | 是 | `关注` / `中性` / `回避` 三选一 |
| `evidence` | 是 | 证据 + 来源（禁止编造板块数据） |
| `trigger` | 是 | 证伪条件（什么证据会推翻该倾向） |

**渲染颜色**：关注=绿、中性=灰、回避=红（这是倾向色，与 A股红涨绿跌行情色无关）。

## 四、覆盖矩阵色块类映射

| availability | class | 符号 |
|---|---|---|
| `available` | `a` | ●（绿底） |
| `partial` | `p` | ●（灰底） |
| `unknown`/`failed`/`incomplete_reconstruction` | `u` | ●（红底） |
| `pending_review` | `p` | ●（灰底） |

生成时 `{{GLOBAL|GROWTH_CLASS}}` 等 28 个占位符按上表填 `a`/`p`/`u`；`{{GLOBAL_MKT_CLASS}}`/`{{GLOBAL_MKT_LABEL}}` 填市场级聚合徽章。

## 五、图表类型选择建议（28 格通用）

| 维度 | 推荐图表 | 备注 |
|---|---|---|
| 增长 | gauge | 指针 = 最新同比，marker = 前值/荣枯线 |
| 通胀 | gauge 或 line | 有历史序列用 line + 2% 目标参考线 |
| 流动性 | line | M2 同比历史趋势 |
| 资金价格 | line | 10Y 国债近 N 日 |
| 风险偏好与信用 | gauge | VIX（低=风险偏好高）或 HY OAS |
| 市场宽度 | bar | 涨跌家数分布（红涨绿跌） |
| 机构持仓与拥挤度 | gauge | PE 分位 / 两融水平 / 拥挤度 |

> 注意：**同一市场的同一维度在跨市场对比时，图表类型保持一致**（如 4 个市场的"增长"都用 gauge），便于扫读对比。

## 六、交付前自检

```bash
# 1. 节点语法检查（ECharts 配置对象必须是合法 JS）
awk '/^<script>$/{f=1;next}/^<\/script>$/{f=0}f' \
  ashare-capital-environment-dashboard-{YYYY-MM-DD}.html > /tmp/_check.js && \
  node --check /tmp/_check.js

# 2. JSON 有效性（{{CELLS_JSON}} 填完后）
grep -o 'const CELLS = .*' file.html | sed 's/const CELLS = //' > /tmp/_cells.json && \
  python3 -c "import json;json.load(open('/tmp/_cells.json'));print('JSON OK')"

# 3. 禁词扫描（overview + disclaimer + source 拼接文本）
```

## 七、已知渲染陷阱

1. **ECharts 容器必须先有宽度**：图表容器 `.chart-box` 必须有固定高度（180px），否则初始化为 0 高度空白。
2. **gauge 的 sections 颜色顺序**：数组索引即从 min 到 max 的区间顺序，**A股口径：低区绿（改善）、高区红（恶化）**，与西方相反。
3. **line 参考线用 markLine**：PMI 荣枯线 50、CPI 目标 2% 等用 dashed 参考线标出。
4. **HTML 转义**：source、reason 等动态内容用 `textContent` 写入（`evid()` 已用 textContent）。
5. **resize 监听**：每个 chart 都要挂 `window.addEventListener('resize', ...)`，避免缩放后空白。
6. **无数据格必须渲染 unknown 占位**：不能空着 div，必须显示"无可得数值" + reason。
