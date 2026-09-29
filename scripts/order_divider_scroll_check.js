// 脚本 D：排列顺序 / 分隔线 / 免滚动可达性（步骤 7.6 / 7.7 / 7.9 用）
// 在 mcp__playwright 的 browser_evaluate 中执行，返回 JSON 字符串
// 同上：刻意不含反斜杠字面量，可直接内联执行（兼容 https 页面 + 规避 mcp 转义陷阱）。
(() => {
  const CH = c => String.fromCharCode(c);
  const WS = new RegExp(CH(0x20) + CH(0x09) + CH(0x0A) + CH(0x0D) + CH(0x0C) + CH(0x0B) + CH(0x00A0) + '+', 'g');
  const vh = window.innerHeight;
  const vw = window.innerWidth;
  const sx = window.scrollX, sy = window.scrollY; // 页面坐标偏移，步骤 7.11 要求 bbox 用页面坐标
  const res = { viewportH: vh, viewportW: vw, order: [], dividers: [], scrollable: [], needScrollActions: [] };

  const visible = el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width >= 1 && r.height >= 1;
  };
  const clsOf = el => (String(el.className).trim().split(WS)[0] || '');
  const sel = el => el.tagName.toLowerCase() +
    (el.id ? '#' + el.id : '') +
    (el.className ? '.' + String(el.className).trim().split(WS).slice(0, 2).join('.') : '');

  // ---------- 1) 排列顺序：容器内子元素的 DOM 顺序 + 视觉坐标 ----------
  const containers = Array.from(document.querySelectorAll('div, ul, ol, section, form'))
    .filter(el => visible(el))
    .filter(el => {
      const r = el.getBoundingClientRect();
      if (r.width < 80 || r.height < 30) return false;
      const kids = Array.from(el.children).filter(k => visible(k) && k.getBoundingClientRect().height > 10);
      return kids.length >= 2;
    })
    .slice(0, 15);

  for (const c of containers) {
    const kids = Array.from(c.children)
      .filter(k => visible(k))
      .slice(0, 20)
      .map((k, i) => {
        const r = k.getBoundingClientRect();
        return {
          domIndex: i,
          tag: k.tagName.toLowerCase(),
          cls: clsOf(k),
          x: Math.round(r.left + sx), y: Math.round(r.top + sy), // 页面坐标
          w: Math.round(r.width), h: Math.round(r.height),
          text: (k.textContent || '').replace(WS, ' ').trim().slice(0, 30)
        };
      });
    if (kids.length >= 2) res.order.push({ container: sel(c), kids });
  }

  // ---------- 2) 分隔线：hr / border-bottom / ::after 细线 ----------
  const isThin = w => { const v = parseFloat(w); return v >= 1 && v <= 2; };

  document.querySelectorAll('hr').forEach(el => {
    if (!visible(el)) return;
    const r = el.getBoundingClientRect();
    res.dividers.push({ kind: 'hr', sel: sel(el), y: Math.round(r.top + sy), w: Math.round(r.width) });
  });

  const all = Array.from(document.querySelectorAll('body *'));
  for (const el of all) {
    if (!visible(el)) continue;
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    if (r.width < 40) continue;
    // 排除按钮等控件自身的边框，那不是分隔线（否则每个 button 都会被误报成一条线）
    const isControl = el.matches('button, a, input, select, textarea, [role="button"], [onclick]');
    if (isThin(cs.borderBottomWidth) && cs.borderBottomStyle !== 'none' && !isControl) {
      res.dividers.push({
        kind: 'border-bottom', sel: sel(el), y: Math.round(r.bottom + sy),
        w: Math.round(r.width), color: cs.borderBottomColor
      });
    }
    const af = getComputedStyle(el, '::after');
    if (af.content && af.content !== 'none' && isThin(af.height) && parseFloat(af.width) > 40) {
      res.dividers.push({
        kind: 'after', sel: sel(el), y: Math.round(r.bottom + sy),
        w: Math.round(parseFloat(af.width)), color: af.backgroundColor
      });
    }
  }

  // ---------- 3) 可滚动容器 ----------
  for (const el of all) {
    if (!visible(el)) continue;
    const cs = getComputedStyle(el);
    if (cs.overflowY !== 'auto' && cs.overflowY !== 'scroll') continue;
    if (el.scrollHeight > el.clientHeight + 1) {
      res.scrollable.push({
        sel: sel(el), clientH: el.clientHeight, scrollH: el.scrollHeight,
        overflowPx: el.scrollHeight - el.clientHeight,
        hasHorizontal: el.scrollWidth > el.clientWidth + 1
      });
    }
  }

  // ---------- 4) 主操作是否需要滚动才可见 ----------
  const ACTION_RE = /编辑|修改|保存|提交|确定|新增|添加|去编辑|管理|设置|查看/;
  for (const el of all) {
    if (!visible(el)) continue;
    if (!el.matches('button, a, [role="button"], [onclick], input[type="button"], input[type="submit"]')) continue;
    const txt = (el.textContent || '').replace(WS, ' ').trim();
    if (!txt || txt.length > 20) continue;
    if (!ACTION_RE.test(txt)) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 20 || r.height < 12) continue;
    const inFold = r.top >= 0 && r.bottom <= vh && r.left >= 0 && r.right <= vw;
    if (!inFold) {
      res.needScrollActions.push({
        sel: sel(el), text: txt,
        top: Math.round(r.top + sy), bottom: Math.round(r.bottom + sy),
        reason: r.bottom > vh ? 'below_fold' : (r.top < 0 ? 'above_fold' : 'horizontal')
      });
    }
  }

  res.dividers = res.dividers.slice(0, 120);
  res.scrollable = res.scrollable.slice(0, 40);
  res.needScrollActions = res.needScrollActions.slice(0, 40);
  return JSON.stringify(res);
})();
