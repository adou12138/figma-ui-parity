# 页面元素样式提取与专项对比（步骤 4.2 / 7.2 / 7.3 详细版）

本文件由 SKILL.md 步骤 4（托管与提取）与步骤 7.2 / 7.3 下沉而来。

### 步骤 4：托管 Figma 设计稿 + 提取本地页面元素样式

#### 4.1 托管 Figma 设计稿为 HTTP URL

`mcp_visual-parity` 需通过 URL 访问参考页面。Figma 设计稿用步骤 2 的 `get_images` 导出的 PNG。

1. **确认设计稿 PNG**：
   - **通道 A**：用 `get_images` 导出，下载到本地 `PARITY_WORK_DIR\figma_spec.png`；若无下载能力，直接用返回的 PNG URL 作为 `referenceUrl`（需可公网访问）。
   - **通道 B**：按步骤 2.B 第 4 步，先取 `/v1/images` 的 S3 URL 再 curl 下载到 `PARITY_WORK_DIR\figma_spec.png`。**已实测**：1438×1127 的设计稿，`scale=2` 导出为 **2876×2254** PNG，约 287KB，可直接用。
   - 两条通道都拿不到 PNG：退化为用节点数据（`get_file_nodes` 或 `/v1/files`、`/v1/files/.../nodes`）做**样式级对比**，跳过像素级对比，并在报告中明确标注。

2. **启动本地静态服务器**（`blocking=false`）：

```powershell
python -m http.server 8765 --directory "./parity-test"   # 相对当前工作目录，勿写死盘符
```

   - 端口冲突时顺延：8765 → 8766 → 8767。
   - 服务器启动后，设计稿可通过 `http://localhost:8765/figma_spec.png` 访问。

3. **尺寸对齐处理**：如设计稿尺寸（如 390×1436）与本地页面视口（如 375×844）不一致，创建包装 HTML：

```html
<!doctype html>
<html><head><meta charset="utf-8"><style>
  body { margin: 0; }
  img { display: block; width: {{DESIGN_WIDTH}}px; height: {{DESIGN_HEIGHT}}px; }
</style></head>
<body><img src="figma_spec.png" alt="reference"></body></html>
```

   - 将 `{{DESIGN_WIDTH}}` / `{{DESIGN_HEIGHT}}` 替换为步骤 2 提取的设计稿尺寸。
   - visual-parity 对比时，参考 URL 指向此包装 HTML。

4. **验证可访问性**：用 `browser_navigate` 打开 `http://localhost:8765/figma_spec.png` 确认正常加载。

#### 4.2 提取本地页面元素样式（含性能保护）

执行 JavaScript 提取所有可见元素的 computed style。

**⚠️ 性能保护**：
- 单次提取最多 `MAX_ELEMENTS_PER_BATCH`（默认 200）个元素
- 超过限制时按 `y` 坐标分批提取（如 y<480、480≤y<800、y≥800）
- 每批提取后立即保存，避免内存堆积

**⚠️ 必须跑两个脚本**：脚本 A 提取容器/控件，脚本 B 提取文本元素。**只跑脚本 A 会漏掉全部文本元素，文案核对与字体对比将没有数据源**——这是必须补齐的关键步骤。

**提取脚本 A —— 容器与控件元素**：

```javascript
(() => {
  const els = Array.from(document.querySelectorAll('div, span, img, i, svg, button, label, a, input, select'));
  const result = [];
  const seen = new Set();
  const MAX = 200; // 单次最大元素数，对应 MAX_ELEMENTS_PER_BATCH

  for (const el of els) {
    if (result.length >= MAX) break;
    const cs = getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    // 整页容器过滤：相对视口判断（桌面端 1438 宽下旧硬编码 380/1400 会双向出错）
    const vw = document.documentElement.clientWidth, vh = document.documentElement.clientHeight;
    if (rect.width > vw * 0.9 && rect.height > vh * 1.5) continue; // 宽占满 90%+ 且高超视口 150% 才算整页容器
    // 注意：不要在这里跳过文字元素，文字统一由脚本 B 提取
    const hasBorder = cs.borderTopWidth !== '0px';
    const hasRadius = cs.borderRadius !== '0px';
    const hasBg = cs.backgroundColor !== 'rgba(0, 0, 0, 0)';
    if (!hasBorder && !hasRadius && !hasBg) continue;
    if (rect.width < 5 || rect.height < 5) continue;
    const y = Math.round(rect.y);
    const key = Math.round(rect.x) + '_' + y + '_' + Math.round(rect.width) + '_' + Math.round(rect.height);
    if (seen.has(key)) continue;
    seen.add(key);

    // 提取伪元素样式（复选框、单选框等可能使用伪元素）
    const beforeCs = getComputedStyle(el, '::before');
    const afterCs = getComputedStyle(el, '::after');
    const hasPseudoContent = beforeCs.content !== 'none' || afterCs.content !== 'none';

    result.push({
      tag: el.tagName.toLowerCase(),
      type: el.type || '',
      className: (el.className || '').toString().substring(0, 100),
      id: el.id || '',
      x: Math.round(rect.x),
      y: y,
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      // —— 填充与背景 ——
      backgroundColor: cs.backgroundColor,
      backgroundImage: cs.backgroundImage,        // 渐变/背景图，对应 Figma fills[].type
      backgroundSize: cs.backgroundSize,          // 对应 Figma scaleMode
      opacity: cs.opacity,                        // 对应 Figma 节点 opacity
      mixBlendMode: cs.mixBlendMode,              // 对应 Figma blendMode
      // —— 排版 ——
      color: cs.color,
      fontSize: cs.fontSize,
      fontFamily: cs.fontFamily,
      fontWeight: cs.fontWeight,
      lineHeight: cs.lineHeight,
      letterSpacing: cs.letterSpacing,            // 对应 style.letterSpacing
      textAlign: cs.textAlign,                    // 对应 style.textAlignHorizontal
      textDecorationLine: cs.textDecorationLine,  // 对应 style.textDecoration
      textTransform: cs.textTransform,            // 对应 style.textCase
      textOverflow: cs.textOverflow,              // 对应 style.textTruncation
      whiteSpace: cs.whiteSpace,
      // —— 盒模型 ——
      boxSizing: cs.boxSizing,
      borderRadius: cs.borderRadius,
      borderTopLeftRadius: cs.borderTopLeftRadius,     // 对应 rectangleTopLeftCornerRadius
      borderTopRightRadius: cs.borderTopRightRadius,
      borderBottomLeftRadius: cs.borderBottomLeftRadius,
      borderBottomRightRadius: cs.borderBottomRightRadius,
      border: `${cs.borderTopWidth} ${cs.borderTopStyle} ${cs.borderTopColor}`,
      padding: `${cs.paddingTop} ${cs.paddingRight} ${cs.paddingBottom} ${cs.paddingLeft}`,
      margin: `${cs.marginTop} ${cs.marginRight} ${cs.marginBottom} ${cs.marginLeft}`,
      boxShadow: cs.boxShadow,
      filter: cs.filter,                          // 对应 LAYER_BLUR
      backdropFilter: cs.backdropFilter,          // 对应 BACKGROUND_BLUR
      // —— 布局 ——
      display: cs.display,
      flexDirection: cs.flexDirection,            // 对应 layoutMode
      justifyContent: cs.justifyContent,          // 对应 primaryAxisAlignItems
      alignItems: cs.alignItems,                  // 对应 counterAxisAlignItems
      gap: cs.gap,                                // 对应 itemSpacing
      overflow: cs.overflow,                      // 对应 clipsContent
      position: cs.position,
      zIndex: cs.zIndex,                          // 对应 children 数组顺序
      transform: cs.transform,                    // 对应 relativeTransform
      // —— 伪元素 ——
      hasPseudoContent: hasPseudoContent,
      pseudoBeforeBg: beforeCs.backgroundColor,
      pseudoBeforeRadius: beforeCs.borderRadius,
      pseudoBeforeContent: beforeCs.content,
      pseudoAfterBg: afterCs.backgroundColor,
      pseudoAfterRadius: afterCs.borderRadius,
      pseudoAfterContent: afterCs.content
    });
  }
  return JSON.stringify({ count: result.length, truncated: result.length >= MAX, elements: result });
})()
```

**提取脚本 B —— 文本元素（文案 + 字体核对的数据源，必跑）**：

```javascript
(() => {
  // 只取"叶子文本节点"：自身有非空文本，且没有同样含文本的子元素，避免整段容器重复计入
  const all = Array.from(document.querySelectorAll('body *'));
  const result = [];
  const seen = new Set();
  const MAX = 200;

  for (const el of all) {
    if (result.length >= MAX) break;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (parseFloat(cs.opacity) === 0) continue;

    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;

    // 图标字体字符（Unicode 私有区 \uE000-\uF8FF）不是真实文案，先剔除——否则"图标i+文字"按钮会被 childHasText 误跳过（实战踩坑）
    const ICON_CHARS = /[\uE000-\uF8FF\u200B-\u200F\uFEFF]/g;
    const realText = s => (s || '').replace(ICON_CHARS, '').replace(/\s+/g, '').length > 0;
    // 直接子节点中的文本片段
    const ownText = Array.from(el.childNodes)
      .filter(n => n.nodeType === 3)
      .map(n => n.textContent)
      .join('')
      .replace(ICON_CHARS, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (!ownText) continue;

    // 若子元素里已有文本，说明当前元素是容器，跳过（只保留最内层）
    const childHasText = Array.from(el.children).some(c => realText(c.textContent));
    if (childHasText) continue;

    const key = ownText + '_' + Math.round(rect.x) + '_' + Math.round(rect.y);
    if (seen.has(key)) continue;
    seen.add(key);

    result.push({
      tag: el.tagName.toLowerCase(),
      className: (el.className || '').toString().substring(0, 100),
      id: el.id || '',
      // —— 文本内容：对应 Figma characters，是文案核对的核心 ——
      text: ownText,
      fullText: (el.textContent || '').replace(/\s+/g, ' ').trim(),
      x: Math.round(rect.x),
      y: Math.round(rect.y),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      // —— 排版：与 Figma style.* 逐项对应 ——
      fontFamily: cs.fontFamily,
      fontSize: cs.fontSize,
      fontWeight: cs.fontWeight,
      lineHeight: cs.lineHeight,
      letterSpacing: cs.letterSpacing,
      color: cs.color,
      textAlign: cs.textAlign,
      textDecorationLine: cs.textDecorationLine,
      textTransform: cs.textTransform,
      textOverflow: cs.textOverflow,
      whiteSpace: cs.whiteSpace,
      webkitLineClamp: cs.webkitLineClamp,
      opacity: cs.opacity
    });
  }
  return JSON.stringify({ count: result.length, truncated: result.length >= MAX, elements: result });
})()
```

**脚本 B 与 Figma 的比对要点**：
- `text` ↔ 设计稿 `characters`，先比原始值；不一致时再检查设计稿 `style.textCase` 是否做了大小写变换（变换导致则判通过）。
- `fontFamily` 只比第一个字体名（设计稿通常只有一种），注意页面可能带引号（如 `"PingFang SC"`），比对前需去引号。
- `lineHeight` 为 `normal` 时按 `fontSize × 1.2` 估算再比，避免误报。
- `letterSpacing` 为 `normal` 时视为 `0`。

3. **分批提取策略**：如返回 `truncated: true`，调整提取脚本的 `y` 范围分批提取：

```javascript
// 第二批：y >= 480 的元素
// 在 for 循环开头增加过滤
if (rect.y < 480) continue; // 第一批提取 y < 480 的
```

4. `browser_take_screenshot` — 截取实际页面全屏图，用于像素级对比和报告并排展示。

---


---

#### 7.2 交互状态对比

使用 `mcp__playwright` 触发交互状态并提取样式变化。

**Hover 状态提取**：

```javascript
// 1. 先用 browser_hover 悬停在目标元素上
// 2. 然后用 browser_evaluate 提取 hover 状态的样式
(() => {
  const el = document.querySelector('button.primary-btn'); // 替换为实际选择器
  if (!el) return JSON.stringify({ error: 'element not found' });
  const cs = getComputedStyle(el);
  return JSON.stringify({
    backgroundColor: cs.backgroundColor,
    color: cs.color,
    boxShadow: cs.boxShadow,
    transform: cs.transform,
    cursor: cs.cursor,
    opacity: cs.opacity
  });
})()
```

**操作流程**：
1. 用 `browser_evaluate` 提取元素**默认状态**样式并记录
2. 用 `browser_hover` 悬停在元素上
3. 用 `browser_evaluate` 提取 **hover 状态**样式
4. 对比默认态和 hover 态的差异
5. 将实际页面的 hover 变化与设计稿的 hover 规格对比（如设计稿有 hover 标注）

**Active / Disabled 状态**：
- Active：用 `browser_click` 点击元素后立即提取样式（需注意不要触发页面跳转）
- Disabled：检查元素是否有 `disabled` 属性，提取 `:disabled` 状态样式
- 如设计稿未标注交互状态，在报告中注明"设计稿未提供交互状态规格，建议补充"

#### 7.3 图标与图片对比

**图标对比策略**（按优先级选择）：

| 对比方式 | 适用场景 | 操作 |
|----------|----------|------|
| **像素级 diff**（优先） | Figma `get_images` 切图 + 本地 img 标签 / CSS 背景图 | 用 visual-parity 的 `compare_section` 对图标区域做像素对比 |
| **SVG path 比对** | 双方都是 SVG | 提取 SVG 的 `path d` 属性，比对路径数据 |
| **base64 比对** | 双方都是 base64 内联 | 比对 base64 字符串是否一致 |
| **尺寸 + 颜色比对**（兜底） | 切图无法获取或格式不兼容 | 仅比对图标的 width/height 和主色调 |

**SVG path 提取脚本**：

```javascript
(() => {
  const svgs = Array.from(document.querySelectorAll('svg'));
  return JSON.stringify(svgs.map(svg => {
    const paths = Array.from(svg.querySelectorAll('path')).map(p => ({
      d: p.getAttribute('d'),
      fill: p.getAttribute('fill') || getComputedStyle(p).fill
    }));
    const rect = svg.getBoundingClientRect();
    return {
      viewBox: svg.getAttribute('viewBox'),
      width: Math.round(rect.width),
      height: Math.round(rect.height),
      paths: paths
    };
  }));
})()
```

**img / CSS 背景图提取**：

```javascript
(() => {
  const imgs = Array.from(document.querySelectorAll('img'));
  const bgImgs = Array.from(document.querySelectorAll('[style*="background-image"], [class*="icon"]'))
    .filter(el => getComputedStyle(el).backgroundImage !== 'none');
  return JSON.stringify({
    imgs: imgs.map(img => ({
      src: img.src.substring(0, 200),
      width: Math.round(img.getBoundingClientRect().width),
      height: Math.round(img.getBoundingClientRect().height),
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight
    })),
    bgImgs: bgImgs.map(el => ({
      backgroundImage: getComputedStyle(el).backgroundImage.substring(0, 200),
      backgroundSize: getComputedStyle(el).backgroundSize,
      width: Math.round(el.getBoundingClientRect().width),
      height: Math.round(el.getBoundingClientRect().height)
    }))
  });
})()
```

**图标对比结论判定**：
- 像素 diff < 2% → 一致
- 像素 diff 2-10% → 轻微差异（可能是抗锯齿或压缩导致），归入低优先级
- 像素 diff > 10% → 差异，归入高/中优先级
- SVG path 数据完全一致 → 一致
- SVG path 数据不同但视觉相似 → 实现差异，归入中优先级

> 以上为**整页/区块级**判定，只能发现"这块区域长得不一样"。**判定单个图标是否用错必须走 7.5 的成对精确比对**，规则见 [icon-diff.md](icon-diff.md)。

## 脚本清单与执行方式

| 脚本 | 用途 | 对应步骤 |
|------|------|----------|
| `scripts/extract_containers.js` | 脚本 A：容器与控件 | 4.2 |
| `scripts/extract_texts.js` | 脚本 B：文本元素 | 4.2 |
| `scripts/extract_icons.js` | 脚本 C：图标（形状指纹 / 颜色 / 邻近文本） | 7.5 |
| `scripts/order_divider_scroll_check.js` | 脚本 D：排列顺序 / 分隔线 / 可滚动性 / 免滚动可达性 | 7.6 / 7.7 / 7.9 |
| `scripts/responsive_check.js` | 响应式健康检查 | 7.4 |

### ⚠️ MCP 传参会吃掉一层反斜杠（实测踩坑）

通过 `mcp__playwright` 的 `browser_evaluate` 传脚本时，工具会把传入代码**再包一层 JS 字符串字面量**后交给 `page.evaluate('() => (...)')`。结果是脚本里的反斜杠被吃掉一层：

| 脚本里写的 | 实际到页面的 | 后果 |
|---|---|---|
| `\uE000` | 实际字符 / 或解析异常 | 正则字符类失效 |
| `\s` | `s` | `\s+` 变成 `s+`，静默改语义（最危险） |
| `\(` | `(` | 捕获组变成普通括号 |

含正则的脚本因此会**报错或静默出错**，且错误很难定位。

**推荐做法 —— 静态服务器 + `fetch` + `eval` 原样加载**（把这行传给 `browser_evaluate`，它本身不含反斜杠，可安全传入）：

```js
(async () => {
  const src = await (await fetch('http://127.0.0.1:<PORT>/extract_icons.js')).text();
  return eval(src);
})()
```

前提是把脚本复制到步骤 4.1 静态服务器的根目录（或任意可访问路径）。若无法托管，退而求其次：在脚本内**避免一切反斜杠转义**，用 `String.fromCharCode(0xE000)` 构造字符、用 `[0-9]` 代替 `\d` 等。

### 脚本 C / D 实测输出示例

脚本 C（图标）能区分不同图标字体码点，这是判定"图标用错"的基础：

```json
{"count":5,"icons":[
 {"sel":"svg.i","type":"svg","fp":"svg:02e18e4c:n2","color":"rgb(0, 149, 255)","w":16,"h":16,"near":"二维码"},
 {"sel":"i.iconfont","type":"iconfont","fp":"font:e60a","color":"rgb(0, 0, 0)","near":"修改名称"},
 {"sel":"i.iconfont2","type":"iconfont","fp":"font:e60b","color":"rgb(0, 0, 0)","near":"复制"}]}
```

脚本 D 能直接命中"主操作需滚动才可见"这类问题：

```json
{"scrollable":[{"sel":"div.scrollbox","clientH":118,"scrollH":734,"overflowPx":616}],
 "needScrollActions":[{"sel":"button#btnEdit","text":"去编辑","top":922,"bottom":956,"reason":"below_fold"}]}
```

**脚本 D 的 `dividers` 段会自动排除按钮等控件自身的边框**，否则每个 `button` 都会被误报成一条分隔线。

