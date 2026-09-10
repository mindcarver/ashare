# HTML 模板（资本环境仪表盘 · 图表化）

> **本文件是参考说明，不是模板真源。** 模板真源是 `scripts/page_template.py`（渲染逻辑在 `scripts/render.py`），
> 视觉令牌 / 外壳 / 组件来自 `skills/_shared/`（设计系统说明见 `skills/_shared/README.md`）。
> **不要复制本文件的片段去拼模板**——那样会绕过品牌层，并触发 `make audit` / `make test` 的漂移检查。
>
> 使用方法：
> 1. 直接跑 `python3 scripts/gen_dashboard.py --cells cells.json --as-of YYYY-MM-DD --out file.html`
>    （不传 `--cells` 时读取 `examples/sample-cells.json` 的演示样例，**非生产数据**）
> 2. `{{CELLS_JSON}}` 是唯一的数据入口（见第三节配置格式），28 格全部由它驱动
> 3. 跑节点语法检查 → `present_files` 交付

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

## 二、骨架与视觉层来源

模板（`scripts/page_template.py`）只保留三样东西：

1. 一个空的 `:root{}` 占位——`ashare_shared.inject_design_tokens()` 的注入锚点，缺失会抛 `RuntimeError`。
2. 页面宽度 `.container` 与 `main` 的最小高度。
3. 资本环境独有的内部结构：`.tw-*`（AI 研判 / 风险清单）、`.sa-*`（板块倾向建议）、`.an-*`（每格 AI 分析摘要）、`.cell-head` / `.cell-name` / `.cell-evidence`，以及 `.market-grid .cell{padding:14px}` 这类靠提高特异性生效的紧凑化覆盖。

其余全部来自品牌层，由 `inject_shared_css()` 在 `</head>` 之前注入：

| 层 | 真源 | 提供 |
|---|---|---|
| 令牌 | `skills/_shared/design-tokens.css` | 颜色 / 字体 / 版面常量（浅色瑞士色板） |
| 外壳 | `skills/_shared/shell.css` | `body` 与 32px 网格底纹、`.masthead`、`.eyebrow`、`.badge` 基座、页脚 |
| 组件 | `skills/_shared/components.css` | `.panel` / `.cell` / `.matrix-*` / `.metric-card` / 徽章 / 表格 / 栅格 / `.chart-box` |

**注入顺序（v2 关键点）**：品牌层排在模板自带 `<style>` **之后**，对同名选择器有最终解释权。想在技能里做例外，只能提高一级特异性（例如 `.panel.market{…}`、`.market-grid .cell{padding:14px}`）；同特异性的 `border-top` / `background` 写法会被品牌层压掉，等于死代码。

每格由渲染器（`render.py` 的 `cell_html()`）发出的 HTML 结构：

```html
<div class="cell" data-key="cn|growth">
  <div class="cell-head">
    <span class="cell-name">增长<span class="risk-dot rk-high" title="高风险"></span></span>
    <span class="badge badge-available">可得</span>
  </div>
  <div class="chart-box" id="ch-cn-growth"></div>
  <div class="cell-analysis">
    <div class="an-head">AI 分析</div>
    <ul class="an-list">
      <li><span class="an-lens">透镜名</span><span class="an-txt">一句话</span></li>
    </ul>
  </div>
  <div class="cell-evidence" id="ev-cn-growth"></div>
</div>
```

```

┌──────────────────────────────────┐
│ 维度名  [风险点]          [徽章]  │
│ ┌──────────────────────────────┐ │
│ │        ECharts 图表           │ │
│ │       (gauge/line/bar)        │ │
│ └──────────────────────────────┘ │
│ AI 分析（透镜式一句话）            │
│ 来源：xxx 观测：xxx 发布：xxx      │
└──────────────────────────────────┘

```

> 图表用色在模板内联 JS 里定义，与令牌对齐：`okColor=#0e7a45`（state-ok）、`badColor=#d2231b`（state-bad）、`accentColor=#1b39d8`、`gridColor=#c9c6c0`。注意 `ok/bad` 是**可得性**语义（绿=可得、红=缺失），与 A 股红涨绿跌不是同一根轴。

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
    "sections": [[0.33, "#0e7a45"], [0.67, "#a9761a"], [1, "#d2231b"]],
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
    "colors": ["#d2231b", "#0e7a45", "#7d838a", "#c9c6c0"],
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
| `sections` | array | gauge 分段颜色 `[[0.33,"#0e7a45"],...]`（0-1 比例） |
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

## 四、覆盖矩阵与徽章色映射

矩阵格与徽章都用**状态语义**，不用行情词（旧版 `--market-up` 取绿色表示「可得」，与 A 股红涨绿跌正好相反，是明确事故源；v2 已删除该别名与 `badge-up`/`badge-down` 别名）：

| availability | 矩阵类 | 徽章类 | 语义色 |
|---|---|---|---|
| `available` | `matrix-cell a` | `badge-available` | `--state-ok`（绿） |
| `partial` | `matrix-cell p` | `badge-partial` | `--state-warn`（琥珀） |
| `pending_review` | `matrix-cell p` | `badge-muted` | 中性灰 |
| `unknown` / `failed` / `incomplete_reconstruction` | `matrix-cell u` | `badge-unknown` | `--state-bad`（红） |

映射真源在 `scripts/derive.py` 的 `AVAIL_CLASS` / `AVAIL_BADGE_CLASS`；矩阵行由 `render.py` 的 `matrix_rows_html()` 生成，市场级聚合徽章由 `mkt_aggregate()` → `avail_badge_class()` 决定。`.matrix-cell.a/.p/.u` 的底色在 `components.css` 中定义为 state-ok / state-warn / state-bad soft。

## 五、图表类型选择建议（28 格通用）

| 维度 | 推荐图表 | 备注 |
|---|---|---|
| 增长 | gauge | 指针 = 最新同比，marker = 前值/荣枯线 |
| 通胀 | gauge 或 line | 有历史序列用 line + 2% 目标参考线 |
| 流动性 | line | M2 同比历史趋势 |
| 资金价格 | line | 10Y 国债近 N 日 |
| 风险偏好与信用 | gauge | VIX（低=风险偏好高）或 HY OAS |
| 市场宽度 | bar | 涨跌家数分布（A 股口径：涨=红、跌=绿） |
| 机构持仓与拥挤度 | gauge | PE 分位 / 两融水平 / 拥挤度 |

> 注意：**同一市场的同一维度在跨市场对比时，图表类型保持一致**（如 4 个市场的“增长”都用 gauge），便于扫读对比。

## 六、交付前自检

```bash
# 1. 节点语法检查（ECharts 配置对象必须是合法 JS）
awk '/^<script>$/{f=1;next}/^<\/script>$/{f=0}f' file.html > /tmp/_check.js && node --check /tmp/_check.js

# 2. CELLS JSON 有效性（用 python 正则，grep 会贪婪匹配到后续 JS）
python3 -c "import re,json;json.loads(re.search(r'const CELLS = (\{.*?\});',open('file.html').read(),re.S).group(1));print('JSON OK')"

# 3. 禁词扫描
grep -oE "买入|卖出|建议买|建议卖|目标价|目标仓位|牛熊分数|总分|确定牛|确定熊|必然涨|必然跌" file.html
```

三条全过才交付。

## 七、已知渲染陷阱

1. **ECharts 容器必须先有宽度**：图表容器 `.chart-box` 必须有固定高度（180px，来自 `components.css`），否则初始化为 0 高度空白。
2. **gauge 的 sections 颜色顺序**：数组索引即从 min 到 max 的区间顺序。默认是 `[okColor, secColor, badColor]`——**绿（可得/良好）→ 灰（中性）→ 红（缺失/恶化）**，这是状态色而非涨跌色，不要与 A 股红涨绿跌混淆。
3. **line 参考线用 markLine**：PMI 荣枯线 50、CPI 目标 2% 等用 dashed 参考线标出。
4. **HTML 转义**：source、reason 等动态内容用 `textContent` 写入（`evid()` 已用 textContent）。
5. **resize 监听**：每个 chart 都要挂 `window.addEventListener('resize', ...)`，避免缩放后空白。
6. **无数据格必须渲染 unknown 占位**：不能空着 div，必须显示"无可得数值" + reason。
7. **不要自行往模板里加 CSS**：品牌层后写会覆盖它。确需例外时提高一级特异性，并跑 `make audit` 确认没被判为漂移。
