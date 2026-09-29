// 脚本 C：页面侧图标提取（步骤 7.5 图标成对精确比对用）
// 在 mcp__playwright 的 browser_evaluate 中执行，返回 JSON 字符串
// 注意：本脚本刻意不含任何反斜杠字面量（\s \uXXXX \( 等），因为 mcp 会把传入脚本
// 再包一层字符串字面量导致反斜杠被吃掉一层；同时 https 页面无法 fetch http 脚本
// （mixed-content），因此本脚本设计为可直接内联到 browser_evaluate 执行。
// 所有正则字符类均用 String.fromCharCode 构造，避免源码出现反斜杠。
(() => {
  const CH = c => String.fromCharCode(c);
  // 图标字体私有区 + 零宽字符，必须剔除，否则邻近文本会被污染
  const ICON_RANGE = CH(0xE000) + '-' + CH(0xF8FF) + CH(0x200B) + '-' + CH(0x200F) + CH(0xFEFF);
  const ICON_CHARS = new RegExp('[' + ICON_RANGE + ']', 'g');
  // 空白：空格 制表 换行 回车 换页 纵向制表 不间断空格
  const WS = new RegExp(CH(0x20) + CH(0x09) + CH(0x0A) + CH(0x0D) + CH(0x0C) + CH(0x0B) + CH(0x00A0) + '+', 'g');
  const clean = s => (s || '').replace(ICON_CHARS, '').replace(WS, ' ').trim();

  // 稳定选择器：tagName + #id + 前 2 个 class（避免过长 :nth-child 链，确保 document.querySelector 可命中）
  function cleanCls(c) {
    return (c || '').trim().split(WS).slice(0, 2).join('.');
  }
  function buildSel(el) {
    const tag = el.tagName.toLowerCase();
    const id = el.id ? '#' + el.id : '';
    const cls = cleanCls((el.getAttribute && el.getAttribute('class')) || '');
    return tag + id + (cls ? '.' + cls : '');
  }
  // 提取元素四边边框（仅 width>0 且 style!=none 的边）
  function borderOf(el) {
    const cs = getComputedStyle(el);
    const sides = ['top', 'right', 'bottom', 'left'];
    const parts = [];
    for (const side of sides) {
      const w = cs.getPropertyValue('border-' + side + '-width');
      const st = cs.getPropertyValue('border-' + side + '-style');
      const c = cs.getPropertyValue('border-' + side + '-color');
      if (parseFloat(w) > 0 && st && st !== 'none') parts.push(side + ':' + w + ' ' + st + ' ' + c);
    }
    return parts.join('; ') || 'none';
  }
  // 检测图标是否位于按钮/可点击容器内（按钮中的图标需全面对比：图标 + 按钮文字 + 背景色 + 边框 + 圆角）
  function buttonContainerOf(iconEl) {
    if (!iconEl.closest) return null;
    const btn = iconEl.closest('button, [role=button], [class*="btn"], [class*="Btn"]');
    if (!btn) return null;
    const br = btn.getBoundingClientRect();
    const bcs = getComputedStyle(btn);
    return {
      sel: buildSel(btn),
      tag: btn.tagName.toLowerCase(),
      text: clean(btn.textContent),           // 按钮文字（已剔除图标字体字符）
      bg: bcs.backgroundColor,                // 按钮背景色
      color: bcs.color,                       // 按钮文字颜色
      radius: bcs.borderRadius,               // 按钮圆角
      border: borderOf(btn),                  // 按钮边框
      x: Math.round(br.left + window.scrollX),
      y: Math.round(br.top + window.scrollY),
      w: Math.round(br.width * 100) / 100,
      h: Math.round(br.height * 100) / 100
    };
  }

  function hash(str) {
    let h = 5381;
    for (let i = 0; i < str.length; i++) h = ((h << 5) + h + str.charCodeAt(i)) >>> 0;
    return h.toString(16).padStart(8, '0');
  }

  // path 归一化：去空白 + 坐标保留 1 位小数（消除渲染亚像素误差）
  // 原正则 /(-?\d+\.\d{2,})/g 改写为显式 [0-9] 与字面点（CH(46)）
  const NUM_DOT = new RegExp('-?[0-9]+' + CH(46) + '[0-9][0-9]+', 'g');
  function normPath(d) {
    return (d || '')
      .replace(WS, '')
      .replace(NUM_DOT, m => String(Math.round(parseFloat(m) * 10) / 10));
  }

  // 图标字体码点：先用 content 的转义形式 "\e60a"（含字面反斜杠 CH(92)），
  // 否则看 content 是否已解析为实际私有区字符，再否则看元素自身文本。
  // 注意：正则里要匹配一个字面反斜杠需写成 \\ （两个反斜杠字符），故用 CH(92)+CH(92)
  const ESC_BSLASH = new RegExp(CH(92) + CH(92) + '([0-9a-fA-F]{4})');
  const RAW_ICON = new RegExp('[' + CH(0xE000) + '-' + CH(0xF8FF) + ']');

  // 背景图 url(...)：括号用 CH(40)/CH(41)，引号用 CH(39)
  const URL_RE = new RegExp('url' + CH(40) + '["' + CH(39) + ']?([^"' + CH(39) + ' )]+)["' + CH(39) + ']?' + CH(41));

  const sel = [
    'svg', 'i',
    '[class*="icon"]', '[class*="Icon"]',
    'img[src*="icon"]', 'img[src*="Icon"]',
    '[style*="background-image"]'
  ].join(', ');

  const out = [];
  for (const el of Array.from(document.querySelectorAll(sel))) {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;

    const tag = el.tagName.toLowerCase();
    let type = 'other', fp = '', color = '';

    if (tag === 'svg' || el.querySelector('svg')) {
      const svg = tag === 'svg' ? el : el.querySelector('svg');
      const ds = Array.from(svg.querySelectorAll('path'))
        .map(p => normPath(p.getAttribute('d')))
        .filter(Boolean);
      ds.sort();
      type = 'svg';
      fp = 'svg:' + hash(ds.join('|')) + ':n' + ds.length;
      const pathEl = svg.querySelector('path');
      color = pathEl ? getComputedStyle(pathEl).fill : cs.color;
    } else if (tag === 'i' || tag === 'span') {
      const before = getComputedStyle(el, '::before').content || '';
      let code = '';
      const mEsc = before.match(ESC_BSLASH);
      if (mEsc) {
        code = mEsc[1];
      } else {
        const mRaw = before.match(RAW_ICON);
        if (mRaw) code = mRaw[0].charCodeAt(0).toString(16);
        else {
          const own = (el.textContent || '').match(RAW_ICON);
          if (own) code = own[0].charCodeAt(0).toString(16);
        }
      }
      type = 'iconfont';
      fp = 'font:' + code;
      color = cs.color;
    } else if (tag === 'img') {
      const src = (el.getAttribute('src') || '').split('/').pop().split('?')[0];
      type = 'img';
      fp = 'img:' + src;
      color = '';
    } else {
      const bi = cs.backgroundImage || '';
      const m = bi.match(URL_RE);
      type = 'bg';
      fp = 'bg:' + (m ? m[1].split('/').pop().split('?')[0] : '');
      color = cs.color;
    }

    if (!color || color === 'none') color = cs.color;

    const p = el.parentElement;
    let near = '';
    if (p) {
      near = clean(p.textContent).slice(0, 40);
      if (!near) {
        const prev = el.previousElementSibling, next = el.nextElementSibling;
        near = clean((prev && prev.textContent) || (next && next.textContent) || '').slice(0, 40);
      }
    }

    const container = buttonContainerOf(el);

    out.push({
      sel: buildSel(el),
      type, fp, color,
      w: Math.round(r.width * 100) / 100,
      h: Math.round(r.height * 100) / 100,
      x: Math.round(r.left + window.scrollX),
      y: Math.round(r.top + window.scrollY),
      near,
      container
    });
  }

  return JSON.stringify({ count: out.length, icons: out.slice(0, 300) });
})();
