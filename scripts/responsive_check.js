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
