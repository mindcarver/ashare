# AGUHOT 资本环境仪表盘设计规格

> 本文档是 AGUHOT `apps/web/app/(operator)/capital-environment/` 页面（Issue #58）的设计快照，用于让本技能 1:1 复现视觉、字段、覆盖语义。
>
> 源码参考（仅内部团队可见）：
> - `apps/web/app/(operator)/capital-environment/page.tsx`（force-dynamic RSC）
> - `apps/web/app/(operator)/capital-environment/_components.tsx`（UI 渲染）
> - `apps/web/lib/capital-conclusion.ts`（FR-009 证据约束结论）
> - `packages/core/src/modules/capital-environment/metric-catalog.ts`（指标目录）

## 一、页面骨架（自上而下）

> 本技能交付的离线 HTML 在字段语义上 1:1 复现 AGUHOT 页面，但在**展示形态上做了图表化升级**：28 格由 `<details>` 折叠文字改为 ECharts 图表网格（gauge/line/bar），并新增顶部覆盖矩阵热力图。字段定义（第二、三节）与覆盖语义（第六节）不变。

1. **顶部导航条**：返回运营台链接（`/console`）
2. **页面标题**：资本环境仪表盘（h1，2xl bold）
3. **回放日期**：`回放日期：YYYY-MM-DD`（次级文字）
4. **快速切换区**：标签"快速切换：" + 4 个链接/输入框
   - `最新`（指向 `?`）
   - `昨日`（`?asOf=YYYY-MM-DD`，date - 1）
   - `一周前`（`?asOf=YYYY-MM-DD`，date - 7）
   - 自选日期输入框 + `回放` 按钮（GET form，无 JS）
5. **顶部摘要卡**（浅底）：overview 一行 + disclaimer 一行
6. **覆盖矩阵**（图表化新增）：4 市场 × 7 维度色块热力图
   - 行 = 市场（全球/美国/中国/韩国），列 = 7 维度
   - 色块：可得=绿底/部分=灰底/未知失败无法还原=红底/待复核=浅灰
   - 底部附图例（可得/部分/未知失败）
7. **市场×维度图表网格**：
   - 每个市场一个 `<section>`，标题：市场名（h2，左）+ 覆盖徽章（右）
   - 3 列响应式网格（`md:grid-cols-3`），每格一个卡片：
     - 顶部：维度名 + 覆盖徽章
     - 中部：ECharts 图表（180px 高）——gauge / line / bar，无数据格显示灰色占位"无可得数值（非零值）" + reason
     - 底部：一行证据脚注（来源 / 观测日期 / 发布日期 / 处理版本）
8. **底部免责声明**（无，disclaimer 在顶部摘要卡里）

完全无数据时（allUnknown）：不渲染市场 section 与覆盖矩阵，显示"该日期无可得的资本环境数据。请选择一个有可靠数据的日期。"（居中浅灰文字）。

## 二、字段定义

### 2.1 顶部摘要卡

| 字段 | 句式 | 必带 |
|---|---|---|
| overview | `截至 {YYYY-MM-DD} 的资本环境：{覆盖等级}。以下为各市场维度的可观测状态，区分已观测事实与未知。` | ✅ |
| disclaimer | `以上为证据约束下的环境解释与研究辅助，不代表未来收益、因果关系或投资建议。` | ✅ |

**覆盖等级**（按 markets 中 `可得` 或 `部分` 的数量决定）：

| marketsWithAvailable | 文本 |
|---|---|
| = 0 | `无可得数据` |
| = markets.length | `完全覆盖` |
| 其他 | `部分覆盖，N/M 市场有可得数据` |

### 2.2 市场 section

| 字段 | 内容 |
|---|---|
| 标题 | 市场名：`全球` / `美国` / `中国` / `韩国` |
| 覆盖徽章 | 见 2.4 |

**market.availability** 取自该市场 7 个维度的聚合：
- 7 维全为 `可得` → `可得`
- 至少 1 维为降级（未知/失败/待复核/无法还原） → `部分`
- 7 维全为 `未知`（或同质降级） → `未知`

### 2.3 维度格（折叠卡）

**summary 区**（默认显示）：
```
维度名                                          [覆盖徽章]
```

**展开区**（点开后显示）：

当存在观测值（`valueRecord.value !== null` 且 `availability === available`）时：

```
观测值：{value} {unit}
来源：{source.id}（{source.name}）
观测日期：{observedAt.slice(0,10)}
发布日期：{publishedAt?.slice(0,10) ?? "未知"}
处理版本：{processingVersion}
覆盖状态：{availabilityLabel}
```

当无观测值时（`availability` 为降级状态）：

```
无可得数值（非零值）
原因：{statusReason}（如有）
```

### 2.4 覆盖徽章（availability badge）

| availability | 文本 | 颜色类 |
|---|---|---|
| `available` | 可得 | `bg-market-up-soft text-market-up` |
| `partial` | 部分 | `bg-surface-muted text-ink-secondary` |
| `unknown` | 未知 | `bg-market-down-soft text-market-down` |
| `failed` | 失败 | `bg-market-down-soft text-market-down` |
| `pending_review` | 待复核 | `bg-surface-muted text-ink-tertiary` |
| `incomplete_reconstruction` | 无法还原 | `bg-market-down-soft text-market-down` |

颜色说明：
- `bg-market-up-soft` / `text-market-up`：A股口径，**绿**=涨=可得（与西方惯例相反）
- `bg-market-down-soft` / `text-market-down`：**红**=跌=缺失
- `bg-surface-muted` / `text-ink-secondary`：中性灰
- `bg-surface-muted` / `text-ink-tertiary`：更浅灰（待复核）

## 三、颜色变量（Tailwind 自定义令牌）

```css
--canvas: #f8fafc;          /* 页面背景 */
--surface-base: #ffffff;     /* 卡片背景 */
--surface-raised: #fafbfc;   /* details 折叠卡背景 */
--surface-muted: #f1f5f9;    /* 摘要卡背景 */
--ink-primary: #0f172a;      /* 主要文字 */
--ink-secondary: #475569;    /* 次要文字 */
--ink-tertiary: #94a3b8;     /* 浅文字 */
--border-hairline: #e2e8f0;  /* 边框 */
--brand: #2563eb;            /* 主色（链接/按钮） */
--brand-foreground: #ffffff; /* 主色文字 */
--market-up: #16a34a;        /* 涨/可得（A股口径=绿） */
--market-up-soft: #dcfce7;   /* 涨/可得 浅底 */
--market-down: #dc2626;      /* 跌/缺失（A股口径=红） */
--market-down-soft: #fee2e2; /* 跌/缺失 浅底 */
```

## 四、视觉规范

- **容器**：`mx-auto max-w-4xl px-6 py-12`
- **章节间距**：`space-y-8`
- **市场标题**：`flex items-center justify-between`，标题 h2 `text-lg font-semibold`
- **维度网格**：`grid gap-2 sm:grid-cols-2`
- **折叠卡**：
  - 闭合态：`rounded-lg border border-border-hairline bg-surface-raised px-4 py-3`
  - 展开态：`open:bg-surface-base`（添加 Tailwind 变体）
  - summary：`flex cursor-pointer items-center justify-between gap-2 list-none`（去掉默认三角）
  - 维度名：`text-sm font-medium text-ink-primary`
  - 徽章：`rounded-full px-2 py-0.5 font-mono text-xs`
- **展开内容**：`mt-3 space-y-2 font-mono text-xs text-ink-secondary`

## 五、键盘与可达性

- `<details>` 默认支持键盘 Enter/Space 展开
- summary `list-none` 隐藏原生三角
- 颜色对比度 ≥ 4.5:1（黑字白底 / 白字深底）
- ARIA：`section aria-label="${市场}资本环境"`

## 六、必须遵守的不变量

1. **4×7 = 28 格永不裁剪**：任何一格缺失只能显示降级状态徽章 + 状态原因，不能省略整格。
2. **观测值非零值才显示**：`value === null` 显式标记"无可得数值（非零值）"，绝不输出 0。
3. **观测值必带单位**：缺单位的指标不能标 `可得`，最多 `部分`。
4. **来源必带 name**：仅有 id 不够，必须有可读来源名。
5. **观测日期 ≤ 发布日期**：物理上观测日期应在发布日期之前或同日，不一致视为数据错误，降级为 `待复核`。
6. **跨市场不串味**：中国市场的宽度数据不能用美国 S&P 500 数据冒充，必须明确归属。
7. **历史回放必须遵守 asOf 截止**：任何 published_at > asOf 的数据不能出现在该次回放里（点时回放语义）。