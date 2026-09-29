# 响应式 / 多视口实测（步骤 7.4 详细版）

本文件由 SKILL.md 步骤 7.4 下沉而来。

#### 7.4 响应式 / 多视口实测对比（使用 `mcp__playwright`）

**⚠️ 这一步不能省**：仅在一个视口下比对，会漏掉真实的破版缺陷。Figma 的 `constraints` 虽在 DOM 里没有同名字段，但其**行为可以实测**——用 `browser_resize` 切换视口，把 `constraints` 翻译成"跨视口断言"，再逐断点跑出来核对。

**7.4.1 确定断点**

1. 先看设计稿有没有多断点 frame：从步骤 2 取到的文件结构里，查找同级或同页面下名称含尺寸/断点关键词的 frame（如 `1440`、`1280`、`768`、`Mobile`、`响应式`）。
   - **有** → 逐断点导出 PNG 并逐一比对，与设计稿逐一对齐。
   - **无** → 只做页面侧的「响应式健康检查」，**不判还原度**，只报破版类问题（溢出/重叠/截断/触控区过小），并在报告中注明"设计稿未提供多断点稿，本节仅做响应式健康检查"。
2. 断点列表取 `RESPONSIVE_BREAKPOINTS`（默认 `1440,1280,1024,768,414,375`）；若设计稿 frame 已给出断点，以设计稿为准。**必须包含设计稿原始宽度**（作为基准断点，用于校验缩放是否等比）。

**7.4.2 逐断点执行**

对每个断点 `W`：

```text
1. browser_resize  →  width=W, height=<设计稿高度或 900>
2. browser_evaluate → 等待布局稳定（等字体/图片加载完）：
     await document.fonts.ready;
     await new Promise(r => setTimeout(r, 300));
3. browser_evaluate → 跑「响应式健康检查脚本」（见下）
4. browser_take_screenshot → 保存为 screenshot_<W>.png
5. browser_evaluate → 跑脚本 A（容器）与脚本 B（文本），保存为 elements_<W>.json / texts_<W>.json
```

**关键点**：
- 每切换一个断点都要**重新提取**，不要用上一个断点的坐标去推断（绝对坐标会变）。
- 截图统一用 `fullPage: false`（视口内），便于逐断点横向对比；需要整页时另存一份 `fullPage` 图。
- 断点切换后若页面发生重定向或登录态丢失（跳转到登录页），记录该断点为"无法验证"，回到步骤 3.1 重新注入登录态。

**响应式健康检查脚本**（在每个断点下执行）：

```javascript
(() => {
  const vw = document.documentElement.clientWidth;
  const issues = [];

  // 1) 横向溢出：页面出现水平滚动条
  const docEl = document.documentElement;
  if (docEl.scrollWidth > docEl.clientWidth + 1) {
    issues.push({
      type: 'horizontal_overflow',
      severity: 'high',
      detail: `文档横向溢出 ${docEl.scrollWidth} > ${docEl.clientWidth}`,
      element: 'document'
    });
  }

  const all = Array.from(document.querySelectorAll('body *'));

  for (const el of all) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (cs.position === 'fixed') continue; // 固定定位元素不参与溢出判定
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;

    // 2) 元素跑出视口右侧 / 左侧
    if (rect.right > vw + 1) {
      issues.push({
        type: 'overflow_right',
        severity: 'high',
        detail: `右边界 ${Math.round(rect.right)} 超出视口 ${vw}`,
        element: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '.' + String(el.className).split(' ')[0])
      });
    }
    if (rect.left < -1) {
      issues.push({
        type: 'overflow_left',
        severity: 'medium',
        detail: `左边界 ${Math.round(rect.left)} 为负`,
        element: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '.' + String(el.className).split(' ')[0])
      });
    }

    // 3) 内容被裁剪（文字截断）：有溢出但容器 hidden/ellipsis
    const clipped = el.scrollWidth > el.clientWidth + 1;
    if (clipped && (cs.overflowX === 'hidden' || cs.textOverflow === 'ellipsis')) {
      const txt = (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 40);
      issues.push({
        type: 'text_clipped',
        severity: 'medium',
        detail: `内容被裁剪 ${el.scrollWidth} > ${el.clientWidth}：${txt}`,
        element: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '.' + String(el.className).split(' ')[0])
      });
    }

    // 4) 触控目标过小（仅窄屏断点，vw <= 480 时检查）
    if (vw <= 480) {
      const interactive = el.matches('button, a, input, select, textarea, [role="button"], [onclick]');
      if (interactive && (rect.height < 44 || rect.width < 44)) {
        issues.push({
          type: 'touch_target_small',
          severity: 'medium',
          detail: `触控目标 ${Math.round(rect.width)}×${Math.round(rect.height)} 小于 44×44`,
          element: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '.' + String(el.className).split(' ')[0])
        });
      }
    }
  }

  // 5) 相邻关键元素重叠（同层、面积相交超过 30%）
  const boxes = all
    .map(el => ({ el, r: el.getBoundingClientRect() }))
    .filter(o => o.r.width > 20 && o.r.height > 20)
    .slice(0, 300); // 控制计算量
  for (let i = 0; i < boxes.length; i++) {
    for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const ox = Math.max(0, Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left));
      const oy = Math.max(0, Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top));
      const area = ox * oy;
      const minArea = Math.min(a.r.width * a.r.height, b.r.width * b.r.height);
      if (minArea > 0 && area / minArea > 0.3) {
        issues.push({
          type: 'overlap',
          severity: 'medium',
          detail: `元素重叠 ${Math.round(area / minArea * 100)}%`,
          element: a.el.tagName.toLowerCase() + ' × ' + b.el.tagName.toLowerCase()
        });
      }
    }
  }

  return JSON.stringify({ viewport: vw, issueCount: issues.length, issues: issues.slice(0, 50) });
})()
```

**7.4.3 跨视口断言（把 `constraints` 翻译成可验证的规则）**

对设计稿中标注了 `constraints` 的关键元素，用两个断点（如基准断点 `W0` 和窄断点 `W1`）的实测数据核对下表：

| `constraints.horizontal` | 预期行为 | 断言方式 |
|--------------------------|---------|---------|
| `LEFT` | 左边界相对容器固定，宽度不变 | `x - 容器x` 在两断点相等；`width` 相等 |
| `RIGHT` | 右边界相对容器固定，宽度不变 | `容器右边 - right` 两断点相等；`width` 相等 |
| `LEFT_RIGHT` | 左右边距固定，宽度随容器拉伸 | `left` 与 `右边距` 两断点相等；`width` 差 = 容器宽度差 |
| `CENTER` | 保持水平居中，宽度不变 | `元素中心x - 容器中心x` 两断点都 ≈ 0；`width` 相等 |
| `SCALE` | 按比例缩放 | `width_1 / width_0` ≈ `容器宽_1 / 容器宽_0`（容差 2%） |

`constraints.vertical` 同规则，作用于 `y` / `height` / 上下边距。

**判定**：
- 断言成立 → 记"响应式行为符合设计约束"。
- 断言不成立 → **判为缺陷**，等级按影响面定：窄屏下破版/不可点击 → 高；仅位置偏移 → 中；仅比例微差（<5%）→ 低。
- 设计稿未标注 `constraints`（缺省为 `LEFT`/`TOP`）→ 默认按"位置固定、尺寸不变"断言；若页面实际表现为拉伸，需与产品确认后再判，先记"观察项"。

**7.4.4 输出**

每个断点产出三项：健康检查 issue 列表、元素样式 JSON、截图。汇总为一张跨断点矩阵：

| 元素 | 1440 | 1280 | 1024 | 768 | 414 | 375 | 结论 |
|------|------|------|------|-----|-----|-----|------|
| 顶部导航 | ✅ | ✅ | ⚠️ 溢出 | ❌ 重叠 | ❌ 破版 | ❌ 破版 | 中风险：≤1024 需修复 |

并在报告（HTML / JSON / Excel）中新增「响应式」章节，缺陷类型统一填 `响应式缺陷`。

