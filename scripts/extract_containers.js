(() => {
  const els = Array.from(document.querySelectorAll('div, span, img, i, svg, button, label, a, input, select'));
  const result = [];
  const seen = new Set();
  const MAX = 200; // 单次最大元素数，对应 MAX_ELEMENTS_PER_BATCH

  // 稳定选择器构造：优先 #id，否则 tag.cls1.cls2（最多两级稳定 class），再否则 tag
  // 用于步骤 7.11「缺陷记录必须携带元素定位」——记录缺陷时直接复用为 element.selector
  const buildSel = (el) => {
    const t = el.tagName.toLowerCase();
    if (el.id) return '#' + el.id;
    const cls = (el.getAttribute && el.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean);
    if (cls.length) return t + '.' + cls.slice(0, 2).join('.');
    return t;
  };

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

    // 页面坐标（含滚动偏移）：步骤 7.11 要求 bbox 用页面坐标，否则滚动后定位失效
    const sx = window.scrollX, sy = window.scrollY;
    const pageX = Math.round(rect.left + sx);
    const pageY = Math.round(rect.top + sy);
    const bbox = { x: pageX, y: pageY, w: Math.round(rect.width), h: Math.round(rect.height) };
    const anchor = (el.id ? '#' + el.id : '') + (el.className ? ' ' + String(el.className).trim().split(/\s+/)[0] : '') || el.tagName.toLowerCase();

    // 提取伪元素样式（复选框、单选框等可能使用伪元素）
    const beforeCs = getComputedStyle(el, '::before');
    const afterCs = getComputedStyle(el, '::after');
    const hasPseudoContent = beforeCs.content !== 'none' || afterCs.content !== 'none';

    result.push({
      tag: el.tagName.toLowerCase(),
      type: el.type || '',
      className: (el.className || '').toString().substring(0, 100),
      id: el.id || '',
      sel: buildSel(el),                 // 稳定 CSS 选择器，供 document.querySelector 命中
      anchor: anchor.trim(),             // 人类可读锚定（id / 首 class / 标签）
      bbox: bbox,                        // 页面坐标 bbox，供滚动定位与高亮
      x: pageX,                          // 页面坐标 x（兼容旧字段名）
      y: pageY,                          // 页面坐标 y（兼容旧字段名）
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
