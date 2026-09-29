(() => {
  // 只取"叶子文本节点"：自身有非空文本，且没有同样含文本的子元素，避免整段容器重复计入
  const all = Array.from(document.querySelectorAll('body *'));
  const result = [];
  const seen = new Set();
  const MAX = 200;

  // 稳定选择器构造：优先 #id，否则 tag.cls1.cls2，再否则 tag
  const buildSel = (el) => {
    const t = el.tagName.toLowerCase();
    if (el.id) return '#' + el.id;
    const cls = (el.getAttribute && el.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean);
    if (cls.length) return t + '.' + cls.slice(0, 2).join('.');
    return t;
  };

  for (const el of all) {
    if (result.length >= MAX) break;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    if (parseFloat(cs.opacity) === 0) continue;

    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;

    // 直接子节点中的文本片段
    // 图标字体字符（Unicode 私有区）不是真实文案，必须先剔除，否则按钮（图标i+文字）会被 childHasText 误跳过
    const ICON_CHARS = /[\uE000-\uF8FF\u200B-\u200F\uFEFF]/g;
    const realText = s => (s || '').replace(ICON_CHARS, '').replace(/\s+/g, '').length > 0;
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

    // 页面坐标（含滚动偏移）：步骤 7.11 要求 bbox 用页面坐标
    const sx = window.scrollX, sy = window.scrollY;
    const pageX = Math.round(rect.left + sx);
    const pageY = Math.round(rect.top + sy);
    const bbox = { x: pageX, y: pageY, w: Math.round(rect.width), h: Math.round(rect.height) };

    result.push({
      tag: el.tagName.toLowerCase(),
      className: (el.className || '').toString().substring(0, 100),
      id: el.id || '',
      sel: buildSel(el),                 // 稳定 CSS 选择器，供 document.querySelector 命中
      anchor: ownText.slice(0, 40),      // 锚定用文本（即文案本身）
      bbox: bbox,                        // 页面坐标 bbox，供滚动定位与高亮
      // —— 文本内容：对应 Figma characters，是文案核对的核心 ——
      text: ownText,
      fullText: (el.textContent || '').replace(/\s+/g, ' ').trim(),
      x: pageX,                          // 页面坐标 x（兼容旧字段名）
      y: pageY,                          // 页面坐标 y（兼容旧字段名）
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
