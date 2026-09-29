# 设计稿字段提取与可比性（步骤 2 详细版）

本文件由 SKILL.md 步骤 2 下沉而来：完整字段表、字段映射与可比性、尺寸提取脚本。

#### 页面级 Frame 与局部节点判定

设计文件常同时包含页面 Frame、组件、实例和局部图层。`node-id` 可能指向任意层级，不能仅凭 URL 参数认定它是页面设计稿。页面级对照的最小输入必须是：`type=FRAME`、可识别的页面名称、页面级宽高，以及能覆盖 Header/主体等主要区块的子树。组件或局部 Frame 只能作为局部字段参考；若 URL 节点不是页面级 Frame，应先读取文件浅层结构并枚举同一 Page 下的顶层 Frame，再按 `page-design-match-check.md` 的映射规则选择页面节点。

#### 设计稿 ↔ 页面字段映射与可比性

**回答"会不会对比设计稿上的所有信息"**：**不会，也不可能**——Figma 节点数据里有一部分是设计工具特有的元信息，页面 DOM 里根本没有对应物。执行时按本表分三类处理，**不要把"不可比"的项判成缺陷**。

**① 可直接比对（字段一一对应，直接比数值）**

| 维度 | Figma 字段 | 页面侧取值（computed style） |
|------|-----------|---------------------------|
| 尺寸 | `absoluteBoundingBox.width` / `height` | `getBoundingClientRect().width` / `.height` |
| 位置 | `absoluteBoundingBox.x` / `y`（减去父节点 x/y 得相对偏移） | `getBoundingClientRect().x` / `.y`（减去父元素 rect 得相对偏移） |
| 背景色 | `fills[0].color` × 255 + `fills[].opacity` | `backgroundColor`（`rgba()` 形式，直接解析） |
| 文字色 | 文本节点 `fills[0].color` × 255 | `color` |
| 字号 | `style.fontSize` | `fontSize`（`px` 字符串，去单位比数值） |
| 字重 | `style.fontWeight` | `fontWeight` |
| 行高 | `style.lineHeightPx` | `lineHeight`（`normal` 需按字号 ×1.2 估算后比对） |
| 字间距 | `style.letterSpacing`（`unit=PIXELS` 时为 px） | `letterSpacing`（`normal` 视为 0） |
| 字体族 | `style.fontFamily` | `fontFamily`（取首个字体名比对） |
| 文本对齐 | `style.textAlignHorizontal` | `textAlign`（`start`≈`LEFT`） |
| 内边距 | `paddingLeft/Right/Top/Bottom` | `paddingLeft/Right/Top/Bottom` |
| 间距 | `itemSpacing` | `gap` / `columnGap` / `rowGap` |
| 圆角 | `cornerRadius` 或四个 `rectangle*CornerRadius` | `borderRadius`（或四角 `borderTopLeftRadius` 等） |
| 边框 | `strokeWeight` + `strokes[0].color` | `borderTopWidth` + `borderTopColor` |
| 透明度 | `opacity`（0–1） | `opacity`（0–1 字符串） |
| 阴影 | `effects[DROP_SHADOW]` → `offset` / `radius` / `spread` / `color` | 解析 `boxShadow`（`inset` 关键字对应 `INNER_SHADOW`） |
| 溢出 | `clipsContent` | `overflow`（`hidden` / `visible`） |
| **文案** | `characters` | 元素 `textContent`（需 `.trim()` 并合并空白） |

**② 需换算后才能比对**

| 项 | 换算规则 |
|----|---------|
| 颜色 | Figma `r/g/b` 是 **0–1 小数**，必须 ×255 再取整；透明度取 `fills[].opacity`，缺省为 1 |
| 渐变 | `gradientStops[]` 按 `position` 排序 → 拼 `linear-gradient(角度, color1 pos1%, color2 pos2%)`；角度由 `gradientHandlePositions` 两点算出，与 CSS 角度定义不同（Figma 0° 指向右且顺时针，CSS `linear-gradient` 0° 指向上），**需 +90° 换算** |
| 行高 | `lineHeightUnit=FONT_SIZE_%` → `lineHeightPercentFontSize/100 × fontSize`；`=INTRINSIC_%` → 记为 `normal`（约 1.2×字号） |
| 字间距 | `letterSpacingUnit=PERCENT` → `letterSpacing/100 × fontSize` 得 px |
| 旋转元素 | 有旋转时 `absoluteBoundingBox` 是轴对齐外接框，须改用 `absoluteRenderBounds`，或从 `relativeTransform` 解出角度 |
| 描边对齐 | `strokeAlign=INSIDE` 时 CSS `border` 等价；`=OUTSIDE` 时 CSS 无原生对应，页面侧实际渲染尺寸会更大，比对时按 `INSIDE` 语义折算或标注不可比 |
| 自动布局 | `layoutMode=HORIZONTAL/VERTICAL` → `flex-direction: row/column`；`primaryAxisAlignItems` → `justify-content`（`MIN`→`flex-start`、`CENTER`→`center`、`MAX`→`flex-end`、`SPACE_BETWEEN`→`space-between`）；`counterAxisAlignItems` → `align-items` |
| 图片填充 | `scaleMode=FILL` → `background-size: cover`；`=FIT` → `contain`；`=TILE` → `repeat` |

**③ 需多视口实测验证（不是"不可比"，必须跑步骤 7.4）**

| 项 | 说明 |
|----|------|
| `constraints`（响应式约束） | Figma 的 `constraints` 描述图层随容器缩放的行为，页面 DOM 虽无同名字段，但其**行为可用 `browser_resize` 在多个断点下实测验证**——把 `constraints` 翻译成"跨视口断言"（见步骤 7.4），再逐断点跑出来核对。**不要因为 DOM 无对应字段就跳过响应式检查**，否则会漏掉真实的破版缺陷 |

**④ 不可比对（设计稿特有，页面无对应物，禁止判为缺陷）**

| 项 | 说明 |
|----|------|
| `componentId` / `componentProperties`（组件实例与变体） | 除非页面 DOM 埋了 `data-component` 等约定属性，否则无从比对 |
| `cornerSmoothing`（圆角平滑） | Figma 特有算法，CSS 不支持 |
| `layoutMode=NONE` 时的自由摆放 | 设计稿可能是随意摆放，页面用 flex/absolute 实现，结果一致即可，不必要求机制一致 |
| 图层命名与分组结构 | Figma 图层名（`name`）、GROUP 层级与页面 DOM 结构天然不同，只比渲染结果 |
| 原型交互与动画 | 不在节点数据里（需另调 `/v1/files/{key}?plugin_data` 或 prototype API），且页面侧无法自动验证 |
| 字体渲染差异 | Windows/macOS 抗锯齿、字体 fallback 不同导致的观感差异属噪声，不判缺陷；仅当 `fontFamily` 实际回退到不同字体家族时才记录 |

**文案比对的特别说明**：设计稿的 `characters` 是**原始文本**，若 `style.textCase=UPPER`，视觉上是大写但实际值可能是小写。比对时：
- 先比 `characters` 原始值 ↔ 页面 `textContent`；
- 若不一致，再检查是否因 `textCase` 变换导致——是则判"通过（大小写由样式控制）"，否则判"文案不一致缺陷"。

#### 设计稿尺寸提取脚本（从 `get_file_nodes` 结果中读取）：

```javascript
// 假设 node 是 get_file_nodes 返回的节点对象
const bb = node.absoluteBoundingBox || {};
const designWidth = Math.round(bb.width || 390);
const designHeight = Math.round(bb.height || 1436);
const fill = (node.fills && node.fills[0] && node.fills[0].color) || node.backgroundColor || null;
const bgColor = fill
  ? `rgba(${Math.round(fill.r*255)},${Math.round(fill.g*255)},${Math.round(fill.b*255)},${fill.a ?? 1})`
  : 'rgb(243,243,243)';
return JSON.stringify({ designWidth, designHeight, bgColor });
```

