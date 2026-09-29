/*
 * 页面交互资产盘点（页面内执行，产出 inventory 契约的 page.json）
 *
 * 用法：通过 mcp__playwright 的 browser_evaluate 传入，或由 run_official_extraction.cjs 注入。
 * 约束：本文件不出现任何反斜杠转义（正则一律用 String.fromCharCode 构造字符类），
 *       避免 MCP 传参吃掉一层反斜杠导致静默改语义。
 *
 * 返回：{ url, title, interactionKinds, forms, modals, dropdowns, tabs, tables, images,
 *        stickyOrFixed, scrollables, buttons[], inputs[], emptyStateCandidates[] }
 */
(() => {
  const CHAR_WS = String.fromCharCode(92) + 's';        // 反斜杠 s
  const CHAR_UP = String.fromCharCode(65) + '-' + String.fromCharCode(90);

  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 && rect.height === 0) return false;
    const style = getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) return false;
    return true;
  };

  const selectorOf = (el) => {
    if (!el || !el.tagName) return '';
    if (el.id) return '#' + el.id;
    const cls = (el.className && typeof el.className === 'string')
      ? el.className.split(CHAR_WS).filter(Boolean).slice(0, 2).join('.')
      : '';
    const base = el.tagName.toLowerCase() + (cls ? '.' + cls : '');
    const parent = el.parentElement;
    if (!parent) return base;
    const same = Array.prototype.filter.call(parent.children, (c) => c.tagName === el.tagName);
    if (same.length <= 1) return base;
    return base + ':nth-of-type(' + (same.indexOf(el) + 1) + ')';
  };

  const nthOf = (el) => {
    const sel = selectorOf(el);
    const list = Array.prototype.slice.call(document.querySelectorAll(sel));
    return Math.max(0, list.indexOf(el));
  };

  const rectOf = (el) => {
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.left + window.scrollX), y: Math.round(r.top + window.scrollY), w: Math.round(r.width), h: Math.round(r.height) };
  };

  const labelText = (el) => {
    const aria = el.getAttribute && el.getAttribute('aria-label');
    if (aria) return aria.trim();
    const txt = (el.innerText || el.textContent || '').trim();
    return txt.split(String.fromCharCode(10))[0].slice(0, 40);
  };

  const isOverlay = (el) => {
    const style = getComputedStyle(el);
    const z = parseInt(style.zIndex, 10);
    const rect = el.getBoundingClientRect();
    const positioned = style.position === 'fixed' || style.position === 'absolute';
    // z>=50 覆盖大量 z 50–99 的自定义弹层；与视口几乎同高的定位元素
    // 多为 fixed 侧栏/主布局容器，不算浮层，避免生成无意义的走查场景。
    const big = rect.width > 200;
    const tallPanel = rect.height >= window.innerHeight * 0.9;
    return positioned && big && !tallPanel && (!isNaN(z) && z >= 50);
  };

  const KIND_PATTERNS = {
    dialog: ['modal', 'dialog', 'popup', 'drawer', 'mask'],
    dropdown: ['dropdown', 'select', 'menu', 'cascader', 'picker'],
    tooltip: ['tooltip', 'popover', 'popper', 'tip'],
    tabs: ['tab', 'segment', 'nav-item'],
    table: ['table', 'grid', 'list-view'],
    upload: ['upload', 'file-input'],
    pagination: ['pagination', 'pager'],
    toast: ['toast', 'message', 'notification', 'alert'],
  };

  const domSignature = Array.prototype.slice.call(document.querySelectorAll('*')).slice(0, 4000)
    .map((el) => ((el.className && typeof el.className === 'string') ? el.className : '') + ' ' + (el.getAttribute('data-testid') || ''))
    .join(' ').toLowerCase();

  // 交互种类 = 类名签名 + 选择器定点存在性探测 的并集。
  // domSignature 只扫前 4000 个元素，超长页面会漏判，导致 tab/upload
  // 等场景不生成；定点查询不依赖扫描窗口。
  const KIND_PROBES = {
    dialog: '[role=dialog], [class*=modal], [class*=dialog], [class*=drawer], [class*=mask]',
    dropdown: 'select, [class*=dropdown], [class*=cascader], [class*=picker]',
    tooltip: '[class*=tooltip], [class*=popover], [class*=popper]',
    tabs: '[role=tab], [class*=tabs], [class*=segment]',
    table: 'table, [role=grid], [class*=table]',
    upload: 'input[type=file], [class*=upload]',
    pagination: '[class*=pagination], [class*=pager]',
    toast: '[class*=toast], [class*=notification]',
  };
  const signatureKinds = Object.keys(KIND_PATTERNS).filter((kind) =>
    KIND_PATTERNS[kind].some((kw) => domSignature.indexOf(kw) >= 0));
  const probeKinds = Object.keys(KIND_PROBES).filter((kind) => {
    try { return !!document.querySelector(KIND_PROBES[kind]); } catch (e) { return false; }
  });
  const interactionKinds = Array.from(new Set(signatureKinds.concat(probeKinds)));

  const buttons = Array.prototype.slice.call(document.querySelectorAll('button, a[role=button], [role=button], input[type=submit], input[type=button], a[href]'))
    .filter(visible).slice(0, 400)
    .map((el) => ({
      selector: selectorOf(el), nth: nthOf(el), text: labelText(el), rect: rectOf(el),
      tag: el.tagName.toLowerCase(), disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
      inModal: !!el.closest('[class*=modal], [role=dialog], [class*=drawer]'),
      title: el.getAttribute('title') || '', href: el.getAttribute('href') || '',
    }));

  const inputs = Array.prototype.slice.call(document.querySelectorAll('input, textarea, select, [contenteditable=true]'))
    .filter(visible).slice(0, 200)
    .map((el) => ({
      selector: selectorOf(el), nth: nthOf(el), tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '', placeholder: el.getAttribute('placeholder') || '',
      autocomplete: el.getAttribute('autocomplete') || '', required: !!el.required,
      maxlength: el.getAttribute('maxlength') || '', rect: rectOf(el),
      labelled: !!(el.id && document.querySelector('label[for="' + el.id + '"]')) || !!el.getAttribute('aria-label'),
    }));

  const images = Array.prototype.slice.call(document.querySelectorAll('img, svg, picture'))
    .filter(visible).slice(0, 200)
    .map((el) => {
      const r = el.getBoundingClientRect();
      const natural = el.tagName.toLowerCase() === 'img' ? { w: el.naturalWidth, h: el.naturalHeight } : null;
      return {
        selector: selectorOf(el), nth: nthOf(el), tag: el.tagName.toLowerCase(),
        rect: rectOf(el), natural,
        objectFit: getComputedStyle(el).objectFit,
        loaded: el.tagName.toLowerCase() === 'img' ? el.complete && el.naturalWidth > 0 : true,
        ratio: natural && natural.h ? Number((r.width / r.height).toFixed(3)) : null,
        naturalRatio: natural && natural.h ? Number((natural.w / natural.h).toFixed(3)) : null,
      };
    });

  const stickyOrFixed = Array.prototype.slice.call(document.querySelectorAll('*'))
    .filter((el) => {
      const pos = getComputedStyle(el).position;
      return pos === 'sticky' || pos === 'fixed';
    }).slice(0, 100)
    .map((el) => ({ selector: selectorOf(el), position: getComputedStyle(el).position, rect: rectOf(el), bottom: Math.round(el.getBoundingClientRect().bottom) }));

  const scrollables = Array.prototype.slice.call(document.querySelectorAll('*'))
    .filter((el) => el.scrollHeight - el.clientHeight > 4 && el.clientHeight > 0).slice(0, 100)
    .map((el) => ({ selector: selectorOf(el), clientH: el.clientHeight, scrollH: el.scrollHeight, overflowY: getComputedStyle(el).overflowY }));

  const overlays = Array.prototype.slice.call(document.querySelectorAll('*')).filter(isOverlay).slice(0, 60)
    .map((el) => ({ selector: selectorOf(el), rect: rectOf(el), visible: visible(el), display: getComputedStyle(el).display }));

  return {
    url: location.href,
    title: document.title,
    viewport: { w: window.innerWidth, h: window.innerHeight, dpr: window.devicePixelRatio },
    interactionKinds,
    forms: document.querySelectorAll('form').length,
    inputs,
    buttons,
    images,
    modals: overlays,
    dropdowns: interactionKinds.indexOf('dropdown') >= 0 ? [{ source: 'kind-detected' }] : [],
    tabs: interactionKinds.indexOf('tabs') >= 0 ? [{ source: 'kind-detected' }] : [],
    tables: document.querySelectorAll('table, [role=grid], [class*=table]').length,
    stickyOrFixed,
    scrollables,
    emptyStateCandidates: Array.prototype.slice.call(document.querySelectorAll('[class*=empty], [class*=no-data], [class*=placeholder]')).slice(0, 20)
      .map((el) => ({ selector: selectorOf(el), text: labelText(el), visible: visible(el) })),
    counts: {
      buttons: buttons.length, inputs: inputs.length, images: images.length,
      overlays: overlays.length, scrollables: scrollables.length,
      zeroSizeExcluded: document.querySelectorAll('*').length - Array.prototype.slice.call(document.querySelectorAll('*')).filter(visible).length,
    },
  };
})()
