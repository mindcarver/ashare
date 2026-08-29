# 资本环境仪表盘字段与视觉规格

> 字段、4×7 网格和覆盖语义沿用 AGUHOT `apps/web/app/(operator)/capital-environment/` 页面（Issue #58）；HTML 视觉系统按用户要求对齐 `ashare-daily-market-review` 的“市场脉搏”报告，不再 1:1 复现 AGUHOT 浅色后台页面。
>
> 源码参考（仅内部团队可见）：
> - `apps/web/app/(operator)/capital-environment/page.tsx`（force-dynamic RSC）
> - `apps/web/app/(operator)/capital-environment/_components.tsx`（UI 渲染）
> - `apps/web/lib/capital-conclusion.ts`（FR-009 证据约束结论）
> - `packages/core/src/modules/capital-environment/metric-catalog.ts`（指标目录）

## 一、页面骨架（自上而下）

> 本技能交付的离线 HTML 在字段语义上复现 AGUHOT 页面，但展示形态使用每日盘面复盘的研报式壳层，并把 28 格图表化为 ECharts 网格（gauge/line/bar）。字段定义与覆盖语义不变。

1. **研报式页首**：金色英文眉题 `GLOBAL / CAPITAL ENVIRONMENT` + 中文标题“资本环境”
2. **点时信息**：右侧显示回放日期、静态点时快照和 `4 市场 × 7 维度`
3. **静态快照说明**：其他日期必须重新运行生成器 `--as-of`，不提供会伪装回放的 URL 控件
4. **顶部摘要卡**：米白纸张底、金色左边线，overview 一行 + disclaimer 一行
5. **覆盖矩阵**（图表化新增）：4 市场 × 7 维度色块热力图
   - 行 = 市场（全球/美国/中国/韩国），列 = 7 维度
   - 色块：可得=绿底/部分=灰底/未知失败无法还原=红底/待复核=浅灰
   - 底部附图例（可得/部分/未知失败）
6. **市场×维度图表网格**：
   - 每个市场一个 `<section>`，标题：市场名（h2，左）+ 覆盖徽章（右）
   - 3 列响应式网格（`md:grid-cols-3`），每格一个卡片：
     - 顶部：维度名 + 覆盖徽章
     - 中部：ECharts 图表（180px 高）——gauge / line / bar，无数据格显示灰色占位"无可得数值（非零值）" + reason
     - 底部：一行证据脚注（来源 / 观测日期 / 发布日期 / 处理版本）
7. **底部免责声明**（无，disclaimer 在顶部摘要卡里）

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
- `bg-market-up-soft` / `text-market-up`：**绿**只表示覆盖“可得”，不是涨跌方向
- `bg-market-down-soft` / `text-market-down`：**红**表示未知/失败/无法还原
- `bg-surface-muted` / `text-ink-secondary`：中性灰
- `bg-surface-muted` / `text-ink-tertiary`：更浅灰（待复核）
- 行情与市场表现图仍使用 A 股口径：**红涨、绿跌**；不要把覆盖状态色解释为行情方向。

## 三、视觉令牌（与每日盘面复盘一致）

```css
--ink: #13211f;       /* 米白卡片上的正文 */
--paper: #f6f1e7;     /* 主卡片背景 */
--paper-2: #eee6d7;   /* 次级证据区 */
--line: #d8cdbb;      /* 卡片与表格边框 */
--red: #bf332d;       /* A股上涨/高风险 */
--green: #19724b;     /* A股下跌/可得覆盖 */
--gold: #ba8a35;      /* 眉题、重点与中性强调 */
--muted: #756f66;     /* 次级文字 */
--canvas: #18221f;    /* 深墨绿网格背景 */
--market-up-soft: #d8eedf;
--market-down-soft: #edd8d2;
```

## 四、视觉规范

- **页面壳层**：深墨绿 `#18221f` + 24px 网格纹理；内容最大宽度 1180px。
- **字体**：正文使用 `Noto Serif SC / Songti SC / STSong`；数字、时间、状态和来源使用等宽字体。
- **页首**：金色英文眉题、超大中文标题、右侧点时信息，结构与每日复盘 `.masthead` 相同。
- **卡片**：米白纸张底、细棕边、`5px 5px` 深色硬投影，不使用后台式圆角浮层。
- **重点区**：摘要/研判用金色左边线，风险用红色左边线，次级证据区使用 `paper-2`。
- **市场标题**：深色背景上的浅色标题与分隔线；维度卡保持 3/2/1 列响应式网格。
- **徽章**：沿用 available/partial/unknown 语义，但颜色值改为每日复盘的绿/金/红纸张色。
- **图表**：轴线与文字使用纸张体系色，主趋势线用金色；A股涨跌仍保持红涨绿跌。

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
