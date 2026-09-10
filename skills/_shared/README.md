# `_shared` —— A 股技能库共享层

本目录存放多个技能共用的**唯一真源**。它不是一个技能（没有 `SKILL.md`，不会被 `install.sh` 挂载为技能），而是被各技能脚本引用的公共模块。

## 为什么存在

2026-09-10 审计发现：6 个技能里本该共享的东西被复制成了多份，并且已经漂移——

- 4 个 HTML 生成器各内嵌一整套「市场脉搏」CSS（合计约 2.6 万字符）。配色令牌层确实漂了（语义令牌数从 22 掉到 8），禁词清单有 4 套不同版本，技术面分析框架在两个技能里各写一份且**结论相反**。

本目录把这些内容收敛成单一真源。禁词、技术面口径各自独立；视觉部分见下面的「品牌设计系统」。

## 内容

| 文件 | 作用 | 谁引用 |
|---|---|---|
| `forbidden-terms.json` | 禁词唯一真源，按 tier 分组 | 4 个 HTML 生成器（research-journal 豁免，见下） |
| `technical-analysis.md` | 技术面证据边界（含价位硬禁令） | company-research、news-investment-targets |
| `design-tokens.css` | 设计令牌：浅色瑞士色板 + 三轴语义色 + 字体 + 版面常量 | 5 个 HTML 报告生成器 |
| `shell.css` | 品牌层之一：页面骨架与报头（网格底纹 / 报头 / 眉题 / 方角徽章基座 / 页脚） | 5 个 HTML 报告生成器 |
| `components.css` | 品牌层之二：报告族共用组件词汇（主卡 / 提示框 / 磁贴 / 徽章 / 矩阵 / 表格 / 列表 / 栅格 / 图表框 / 行式组件） | 5 个 HTML 报告生成器 |
| `ashare_shared.py` | 零依赖加载器：读禁词、读令牌、读品牌层、自检 | 同上 |

> 「5 个 HTML 报告生成器」= capital / daily / company / news + **research-journal**。
> research-journal 从审计 P2-6 起产出 HTML 复盘报告与统计看板，因此接入令牌与品牌层；
> 但它**不加载禁词 tier**（下节说明）。

## 品牌设计系统（v2，2026-09-10 换装）

视觉身份：**新瑞士平面设计 / 现代科技编辑系统 / 柔和粗野主义**——白纸黑字最高对比 + 可见 32px 网格 + 纯黑 2px 结构线 + 零圆角 + 7px 硬投影（实色、零模糊）+ grotesk 标题与等宽数据 + 宋体长文。

### 三层结构

```
design-tokens.css   ← 只放变量（颜色 / 字体 / 版面常量），不含任何选择器
shell.css           ← 品牌层 A：页面骨架（body / 网格底纹 / .masthead / .eyebrow / .badge 基座 / 页脚）
components.css      ← 品牌层 B：组件词汇（.panel / .metric-card / .badge-* / .matrix-* / 表格 / 栅格 / 图表框 / 行式组件）
```

改配色只改 `design-tokens.css`；改组件观感改 `components.css`；两者都不要碰各技能的模板。

### 注入顺序（v2 的关键变更）

品牌层由 `inject_brand_css()` 插在 **`</head>` 之前**，也就是**排在各技能自带的 `<style>` 之后**：

```python
inject_shared_css(html) == inject_brand_css(inject_design_tokens(html))
#   inject_design_tokens：把模板里的空 :root{} 换成 design-tokens.css
#   inject_brand_css    ：把 shell.css + components.css 包成 <style id="ashare-brand"> 插在 </head> 前
```

这是有意为之：品牌层要能覆盖技能模板里**遗留的旧组件样式**，只有后写才生效。v1 曾插在 `:root` 之后（技能之前），那时品牌层只能放技能绝不重定义的东西；v2 反过来。

**因此：技能模板里不要再重复 `shell.css` / `components.css` 的任何规则。** 写了也是死代码（会被品牌层覆盖），还会让 `make audit` / `make test` 报漂移。各技能只保留自己独有的布局与内部结构，见文末「技能保留项」。

需要技能级例外时（例如某页的卡片要更紧凑），用**提高一级特异性**的写法，例如 `.panel.market{…}`、`.signal-grid .signal{…}`、`.market-grid .cell{padding:14px}`——品牌层后写，同特异性的 `border-top` / `background` 会被它压掉。

### 三组语义色（轴不同，不得串用）

| 轴 | 令牌 | 只用于 |
|---|---|---|
| 涨跌 | `--gain` / `--loss`（A 股口径：红涨绿跌） | 收益、涨跌幅、超额 |
| 状态 | `--state-ok` / `--state-warn` / `--state-bad` / `--state-unknown` | 可得性、覆盖度、通过与否、风险等级 |
| 品牌 | `--accent`（钴蓝） | 眉题、规线、链接、编号——**不承载语义** |

等级 / 优先级刻意走「黑→灰」明度阶梯（`--rule` / `--ink-secondary` / `--line`），避免与涨跌或状态色互相污染。

> **事故源已删除**：旧版把「可得」命名为 `--market-up`（取绿色），与 A 股红涨绿跌正好相反。v2 删除该别名，状态一律用 `--state-*`；徽章同理，只用 `badge-available` / `badge-partial` / `badge-unknown`，**不提供** `badge-up` / `badge-down`。`make audit` 与共享层测试都会拦下回潮。

### 三条硬约束

1. 任何组件都不得出现 `border-radius`（方角是这套身份的一部分；唯一例外是环形图 `.donut` 的几何圆）。
2. 边框只用两档：`--hair` 发丝线（1px，`--line`）与 `--rule-w` 结构线（2px，`--rule`）。组件之间的分隔用发丝线，组件自身的轮廓用结构线。
3. 投影只用一种：`box-shadow: var(--shadow-off) var(--shadow-off) 0 var(--shadow)`（实色、零模糊）。不要写柔和阴影。

## 禁词 tier

任一 tier 都**隐含包含 `core`**：

| tier | 追加禁止 | 用于 |
|---|---|---|
| `core` | —（交易指令 / 目标价 / 收益承诺 / 绝对化断言） | 兜底默认 |
| `no_price` | 止损、止盈、目标价位等价格锚点；「数据为估算」 | daily-market-review、company-research |
| `strict` | 裸「买入/卖出」、聚合评分词（总分、牛熊分数） | capital-environment-dashboard |
| `score_ok` | 同 `no_price`，但允许「总分」等评分词 | news-investment-targets |

`score_ok` 与 `strict` 的区别是有意的：新闻标的技能有 100 分评分模型，「总分」是合法字段；资本环境面板完全不产生聚合评分，所以连「总分」都不许出现。

### 唯一的豁免者：research-journal

`ashare-research-journal` **不适用**禁词硬门禁，也不登记进 `tier_map`。原因：它的报告逐字引用
用户当时**冻结**的研究原文（假设、催化剂、证伪条件），审查性引用不可改写——扫描只会命中不可避免
的引用（例如用户自己写的「止损」「目标价」），拦下来等于逼人篡改历史。

替代方案是固定的「报告性质」声明（`不构成投资建议…`），必须留在脚本里。护栏见
`tools/audit_shared_layer.py` 与 `tests/test_ashare_shared.py` 的 `FORBIDDEN_EXEMPT_SKILLS`：
豁免技能若反过来加载禁词 tier，或弄丢了声明，`make audit` / `make test` 都会失败。它仍需通过
令牌、品牌层、`_paths` 与「不得体积回涨」的全部检查。

## 如何在脚本里引用

单文件生成器（company / news）沿用内联路径推导：

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))
from ashare_shared import forbidden_terms, find_forbidden, inject_shared_css

FORBIDDEN = forbidden_terms("no_price")          # 也可用 tier_for_skill(__name__)
hit = find_forbidden(payload, "no_price")        # 递归扫描任意嵌套结构
html = inject_shared_css(html)                   # 注入设计令牌 + 品牌层（外壳 + 组件）
```

已拆分为多模块的生成器（capital / daily / research-journal）不要在每个模块里重复这段路径拼接：同目录放一个
`_paths.py`，需要 `ashare_shared` 的模块顶部写 `import _paths  # noqa: F401` 即可，与导入顺序无关。

```python
# scripts/_paths.py
#   import sys; from pathlib import Path
#   SHARED_DIR = Path(__file__).resolve().parents[2] / "_shared"
#   if str(SHARED_DIR) not in sys.path: sys.path.insert(0, str(SHARED_DIR))

import _paths  # noqa: F401
from ashare_shared import inject_shared_css
```

路径推导说明：脚本位于 `skills/<skill>/scripts/x.py`，`parents[2]` 即 `skills/`，因此 `_shared` 与其同级。技能目录被软链到 `~/.workbuddy/skills/` 后，`Path(__file__).resolve()` 会跟随软链回到仓库真实路径，推导依然成立（`_paths.py` 同样位于 `scripts/` 下，推导不变）。

## 拆分后的模块布局（审计 P2-5 / P2-6）

capital、daily、research-journal 三个生成器已按 `schema / validate / derive / render (+ _paths)` 拆分，
`page_template.py` 单放整页模板（capital 与 research-journal），演示样例数据移到 `examples/`。CLI 调用方式不变。

**因此本层的护栏扫描的是技能 `scripts/` 下的全部 `.py`，不是入口脚本一个文件**
（`tools/audit_shared_layer.py` 与 `tests/test_ashare_shared.py`）。往任一模块里回填
禁词表、`:root` 色值、页面骨架规则、组件骨架规则，或把某个模块养到 700 行以上，
`make audit` / `make test` 都会失败。

## 模板里该留什么

只留两样东西：

1. 一个空的 `:root{}` 占位（品牌层注入的锚点，缺失会抛 `RuntimeError`）。
2. 该技能**独有的布局与内部结构**——见 `components.css` 文末的「技能保留项」：

| 技能 | 保留在模板里的独有部分 |
|---|---|
| capital | `.takeaway-box` / `.risk-box` / `.sector-advice-box` 的 `tw-*` 与 `sa-*` 内部结构、`.cell-head` / `.cell-name` / `.cell-evidence`、`.an-*` 分析摘要 |
| daily | `.state-ice/-euphoria/-divergence/-repair` 的情绪语义色、`.section-note` / `.evidence` 附注小字 |
| company | `.thesis` / `.signal` 的卡内排版、`.panel.market` / `.facts` / `.proof` 三档顶规 |
| news | `.candidate-head` / `.candidate-meta`、`.chain-grid` 内部排版 |
| journal | `.judge` / `.crit`（冻结原文块） |

**不要**再写 `*{box-sizing}` / `body{…}` / `.masthead{…}` / `.eyebrow{…}` / `.panel{…}` / `.metric-card{…}` / `.badge-available{…}` 这些骨架与组件规则——`make audit` 与共享层测试都会拦下。

## 自检

```bash
python3 skills/_shared/ashare_shared.py     # 或 make selftest
```

输出各 tier 词条数、技能 tier 映射、令牌 / 外壳 / 组件 / 技术面文件是否就位、品牌层合计字符数。

## 约束

- 本目录**不含业务逻辑**，不放数据采集、评分、渲染代码。
- 新增共享内容前先确认至少两个技能会用；只有一个技能用的东西留在该技能自己的 `references/`。
- 改动 `forbidden-terms.json`、`design-tokens.css`、`shell.css` 或 `components.css` 后必须跑 `make test`（禁词放宽会让生成器门禁失效；令牌与品牌层改动会影响五个报告的外观）。
- 令牌声明保持「冒号后不留空格」（如 `--ink:#111417`），压缩器与测试断言依赖该格式。
- 若把单个技能目录单独拷出仓库使用，`_shared` 会缺失，脚本会抛出明确的 `RuntimeError` 而不是静默降级；此时请从仓库重新执行 `./install.sh`。
