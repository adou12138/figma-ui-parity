/*
 * 漏报维度补充检测（页面内执行，输出 findings 列表）
 *
 * 覆盖维度：7.24 图片与插画适配、7.25 暗色模式、7.27 多行截断、7.28 表单控件细节、
 *           7.29 焦点可见性、7.30 国际化细节、7.31 滚动 UX、7.20 加载残留
 *
 * 用法：与 collect_page_inventory.js 相同，通过 browser_evaluate 传入或由 driver 注入。
 * 约束：全文不出现反斜杠转义（字符范围用 String.fromCharCode 构造），
 *       避免 MCP 传参吃掉一层反斜杠导致静默改语义。
 *
 * 返回：{ url, findings[], summary{} }，每条 finding 可直接喂给 normalize_evidence。
 */
(() => {
  const NL = String.fromCharCode(10);
  const findings = [];

  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    if (el.getBoundingClientRect().width === 0 && el.getBoundingClientRect().height === 0) return false;
    const style = getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden' && parseFloat(style.opacity) !== 0;
  };

  const selectorOf = (el) => {
    if (!el || !el.tagName) return '';
    if (el.id) return '#' + el.id;
    const cls = (el.className && typeof el.className === 'string')
      ? el.className.split(String.fromCharCode(32)).filter(Boolean).slice(0, 2).join('.')
      : '';
    return el.tagName.toLowerCase() + (cls ? '.' + cls : '');
  };

  const rectOf = (el) => {
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.left + window.scrollX), y: Math.round(r.top + window.scrollY), w: Math.round(r.width), h: Math.round(r.height) };
  };

  const parseColor = (value) => {
    if (!value) return null;
    const text = String(value).trim();
    if (text.indexOf('rgb') !== 0) return null;
    const open = text.indexOf('(');
    const close = text.lastIndexOf(')');
    if (open < 0 || close < 0) return null;
    const parts = text.slice(open + 1, close).split(',').map((p) => parseFloat(p));
    if (parts.length < 3) return null;
    const alpha = parts.length > 3 ? parts[3] : 1;
    return { r: parts[0], g: parts[1], b: parts[2], a: isNaN(alpha) ? 1 : alpha };
  };

  const luminance = (c) => {
    const f = (v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };

  const contrast = (a, b) => {
    if (!a || !b) return null;
    const l1 = luminance(a);
    const l2 = luminance(b);
    const hi = Math.max(l1, l2);
    const lo = Math.min(l1, l2);
    return Number(((hi + 0.05) / (lo + 0.05)).toFixed(2));
  };

  const effectiveBackground = (el) => {
    let node = el;
    while (node && node !== document.documentElement) {
      const bg = parseColor(getComputedStyle(node).backgroundColor);
      if (bg && bg.a > 0.05) return bg;
      node = node.parentElement;
    }
    return { r: 255, g: 255, b: 255, a: 1 };
  };

  const push = (dimension, symptom, expected, actual, el, extra) => {
    const severity = extra && extra.severityHint ? extra.severityHint : 'P2';
    findings.push(Object.assign({
      dimension,
      symptom,
      expected,
      actual,
      severityHint: severity,
      severity,
      confidence: extra && extra.confidence != null ? extra.confidence : 0.8,
      status: extra && extra.status ? extra.status : 'confirmed',
      element: el ? { selector: selectorOf(el), nth: 0, bbox: rectOf(el), anchor: (el.innerText || el.getAttribute('aria-label') || '').slice(0, 30) } : null,
      evidence: [{ type: extra && extra.evidenceType ? extra.evidenceType : 'in-page-check', result: 'mismatch' }],
      sources: ['extra-checks'],
      property: extra && extra.property ? extra.property : null,
    }, extra && extra.raw ? { raw: extra.raw } : {}));
  };

  /* ---------------- 7.24 图片与插画 ---------------- */
  Array.prototype.slice.call(document.querySelectorAll('img')).filter(visible).slice(0, 300).forEach((img) => {
    const r = img.getBoundingClientRect();
    if (!img.complete || img.naturalWidth === 0) {
      push('7.24', '图片加载失败，页面出现碎图或空白占位', '加载失败时有占位或兜底样式', 'naturalWidth=0，无 error 兜底样式', img,
        { severityHint: 'P1', evidenceType: 'image-load', property: 'loaded' });
      return;
    }
    if (r.height > 0 && img.naturalHeight > 0) {
      const rendered = Number((r.width / r.height).toFixed(3));
      const natural = Number((img.naturalWidth / img.naturalHeight).toFixed(3));
      const fit = getComputedStyle(img).objectFit;
      if (Math.abs(rendered - natural) > 0.05 && fit !== 'cover' && fit !== 'contain' && fit !== 'none') {
        push('7.24', '图片被拉伸变形，宽高比与原始比例不符',
          'object-fit 为 cover/contain 或渲染比例与原始比例一致',
          '渲染比例 ' + rendered + '，原始比例 ' + natural + '，object-fit=' + fit, img,
          { severityHint: 'P1', property: 'object-fit', raw: { rendered, natural, fit } });
      }
    }
  });

  /* ---------------- 7.25 暗色模式 ---------------- */
  let darkMediaCount = 0;
  let sheetAccessible = false;
  Array.prototype.slice.call(document.styleSheets).forEach((sheet) => {
    let rules = null;
    try { rules = sheet.cssRules; } catch (e) { return; }
    sheetAccessible = true;
    Array.prototype.slice.call(rules || []).forEach((rule) => {
      if (rule.cssText && rule.cssText.indexOf('prefers-color-scheme') >= 0 && rule.cssText.indexOf('dark') >= 0) darkMediaCount += 1;
    });
  });
  const hardcodedLight = Array.prototype.slice.call(document.querySelectorAll('*')).filter((el) => {
    if (!visible(el)) return false;
    const bg = parseColor(getComputedStyle(el).backgroundColor);
    if (!bg || bg.a < 0.9) return false;
    return bg.r >= 250 && bg.g >= 250 && bg.b >= 250;
  }).length;
  if (darkMediaCount === 0 && hardcodedLight > 0) {
    push('7.25', '页面未适配深色模式，浅色背景写死导致深色环境下刺眼或白底白字',
      '存在 prefers-color-scheme: dark 适配或使用主题变量',
      '同源样式表中未找到 dark 媒体查询，另有 ' + hardcodedLight + ' 个元素背景为纯浅色',
      null, { severityHint: 'P2', confidence: sheetAccessible ? 0.85 : 0.5, evidenceType: 'stylesheet-scan', property: 'prefers-color-scheme',
              raw: { darkMediaCount, hardcodedLight, sheetAccessible } });
  } else if (darkMediaCount > 0) {
    push('7.25', '页面有深色模式样式，是否与设计一致需切换主题实测',
      '深色模式下配色与设计稿深色稿一致', '检测到 ' + darkMediaCount + ' 条 dark 媒体查询，未在本轮切换实测',
      null, { severityHint: 'P3', status: 'pending', confidence: 0.4, evidenceType: 'stylesheet-scan', property: 'prefers-color-scheme',
              raw: { darkMediaCount } });
  }

  /* ---------------- 7.27 多行截断 ---------------- */
  Array.prototype.slice.call(document.querySelectorAll('*')).filter(visible).slice(0, 4000).forEach((el) => {
    if (!el.textContent || !el.textContent.trim()) return;
    if (el.children.length > 0) return;
    const style = getComputedStyle(el);
    const clamp = parseInt(style.webkitLineClamp, 10);
    const clipped = el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1;
    if (!clipped) return;
    if (!isNaN(clamp) && clamp > 0) {
      push('7.27', '多行文本被截断且未显示省略号或末行被裁掉',
        '按设计显示 N 行并以省略号结束', 'line-clamp=' + clamp + ' 但内容 ' + el.scrollHeight + 'px 超出 ' + el.clientHeight + 'px', el,
        { confidence: 0.7, property: 'line-clamp' });
    } else if (style.textOverflow === 'ellipsis' && !el.getAttribute('title') && el.scrollWidth > el.clientWidth + 1) {
      push('7.27', '单行省略号截断但缺少完整内容提示', '截断元素提供 title 或可展开查看全文',
        'text-overflow=ellipsis 且无 title 属性', el, { severityHint: 'P3', confidence: 0.5, property: 'text-overflow' });
    }
  });

  /* ---------------- 7.28 表单控件细节 ---------------- */
  Array.prototype.slice.call(document.querySelectorAll('input, textarea')).filter(visible).slice(0, 200).forEach((el) => {
    const style = getComputedStyle(el);
    const bg = effectiveBackground(el);
    // ::placeholder 是伪元素，必须用 getComputedStyle(el, '::placeholder') 取色，
    // 读 el.style.color 拿到的是输入文字色而不是占位色。
    let placeholderColor = null;
    try { placeholderColor = parseColor(getComputedStyle(el, '::placeholder').color); } catch (e) { placeholderColor = null; }
    if (placeholderColor && placeholderColor.a >= 0.5) {
      const ratio = contrast(placeholderColor, bg);
      if (ratio != null && ratio < 3) {
        push('7.28', '输入框占位提示文字与背景对比度过低，placeholder 几乎不可辨认', '占位文字对比度不低于 3',
          'placeholder 对比度 ' + ratio, el,
          { severityHint: 'P2', confidence: 0.7, property: 'placeholder-contrast', raw: { ratio } });
      }
    }
    const valueColor = parseColor(style.color);
    if (valueColor) {
      const ratio = contrast(valueColor, bg);
      if (ratio != null && ratio < 4.5) {
        push('7.28', '输入框文字与背景对比度过低，内容不易辨认', '正文对比度不低于 4.5',
          '文字对比度 ' + ratio, el,
          { severityHint: 'P1', confidence: 0.7, property: 'color-contrast', raw: { ratio } });
      }
    }
    const type = (el.getAttribute('type') || 'text').toLowerCase();
    if ((type === 'password' || type === 'number' || type === 'tel') && !el.getAttribute('autocomplete')) {
      push('7.28', '密码或数字字段未声明 autocomplete，浏览器填充行为不可控',
        '按语义声明 autocomplete（如 new-password / one-time-code）', '缺少 autocomplete 属性', el,
        { severityHint: 'P3', confidence: 0.6, property: 'autocomplete' });
    }
  });

  /* ---------------- 7.29 焦点可见性 ---------------- */
  const focusTargets = Array.prototype.slice.call(document.querySelectorAll('a[href], button, input, select, textarea, [tabindex]')).filter(visible).slice(0, 60);
  let focusMissing = 0;
  focusTargets.forEach((el) => {
    const before = getComputedStyle(el);
    const beforeOutline = before.outlineStyle + ' ' + before.outlineWidth;
    const beforeShadow = before.boxShadow;
    el.focus({ preventScroll: true });
    const after = getComputedStyle(el);
    const afterOutline = after.outlineStyle + ' ' + after.outlineWidth;
    const afterShadow = after.boxShadow;
    const changed = beforeOutline !== afterOutline || beforeShadow !== afterShadow;
    const outlineOff = after.outlineStyle === 'none' || parseFloat(after.outlineWidth) === 0;
    if (outlineOff && !changed) {
      focusMissing += 1;
      if (focusMissing <= 5) {
        // 程序化 focus() 不总触发 :focus-visible（键盘/鼠标语义不同），
        // 直接判 confirmed 会误报 focus-visible 方案的站点，故降为待确认。
        push('7.29', '程序化聚焦后控件无可见焦点样式（:focus-visible 方案需键盘 Tab 实测复核）', '焦点可见（outline 或等价 focus-visible 样式）',
          'outline 为 none 且 focus 前后无样式变化', el,
          { severityHint: 'P1', confidence: 0.5, status: 'pending', property: 'outline', evidenceType: 'focus-probe' });
      }
    }
    el.blur();
  });
  if (focusMissing > 5) {
    push('7.29', '多个可交互控件缺少可见焦点样式（程序化探测，待键盘 Tab 复核）', '全部可交互控件焦点可见',
      '共 ' + focusMissing + ' 个控件在聚焦后无可见变化（仅列出前 5 个）', null,
      { severityHint: 'P1', confidence: 0.5, status: 'pending', evidenceType: 'focus-probe', raw: { focusMissing } });
  }

  /* ---------------- 7.30 国际化细节 ---------------- */
  const RANGES = [
    [0x0590, 0x08FF, 'RTL'], [0xFB1D, 0xFDFF, 'RTL'], [0xFE70, 0xFEFF, 'RTL'],
    [0x1F300, 0x1FAFF, 'emoji'], [0xFF01, 0xFF60, 'fullwidth'],
  ];
  const classify = (ch) => {
    const code = ch.codePointAt(0);
    for (let i = 0; i < RANGES.length; i += 1) {
      if (code >= RANGES[i][0] && code <= RANGES[i][1]) return RANGES[i][2];
    }
    return null;
  };
  const textNodes = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
  let node = walker.nextNode();
  while (node && textNodes.length < 3000) {
    const t = (node.nodeValue || '').trim();
    if (t) textNodes.push(node);
    node = walker.nextNode();
  }
  let rtlHits = 0;
  let emojiHits = 0;
  textNodes.forEach((textNode) => {
    const parent = textNode.parentElement;
    if (!parent || !visible(parent)) return;
    for (let i = 0; i < textNode.nodeValue.length; i += 1) {
      const kind = classify(textNode.nodeValue[i]);
      if (kind === 'RTL') { rtlHits += 1; break; }
    }
    for (let i = 0; i < textNode.nodeValue.length; i += 1) {
      if (classify(textNode.nodeValue[i]) === 'emoji') {
        emojiHits += 1;
        const style = getComputedStyle(parent);
        if (parent.scrollHeight > parent.clientHeight + 2 && parseFloat(style.lineHeight) > 0 && parseFloat(style.lineHeight) < 24) {
          push('7.30', 'emoji 造成行高跳动或文字被裁切', 'emoji 与文字在同一行内对齐且不被裁切',
            'line-height=' + style.lineHeight + ' 但内容高度超出', parent, { confidence: 0.5, property: 'emoji-line-height' });
        }
        break;
      }
    }
  });
  if (rtlHits > 0) {
    push('7.30', '页面存在 RTL 文本但未声明书写方向，混排时容易错位', 'RTL 内容容器声明 dir 或 direction',
      '检测到 ' + rtlHits + ' 处 RTL 文本，页面 direction=' + getComputedStyle(document.body).direction, null,
      { severityHint: 'P2', confidence: 0.6, evidenceType: 'text-scan', raw: { rtlHits } });
  }
  if (emojiHits > 0) {
    findings.push({
      dimension: '7.30', symptom: '页面包含 emoji 文本，需确认与设计的字号行高一致',
      expected: 'emoji 渲染不影响行高与基线', actual: '检测到 ' + emojiHits + ' 处 emoji 文本',
      status: 'pending', severityHint: 'P3', confidence: 0.4,
      element: null, evidence: [{ type: 'text-scan', result: 'info' }], sources: ['extra-checks'], raw: { emojiHits },
    });
  }

  /* ---------------- 7.31 滚动 UX ---------------- */
  const fixedBars = Array.prototype.slice.call(document.querySelectorAll('*')).filter((el) => {
    if (!visible(el)) return false;
    const pos = getComputedStyle(el).position;
    if (pos !== 'fixed' && pos !== 'sticky') return false;
    const r = el.getBoundingClientRect();
    return r.height > 24 && r.height < 200 && r.width > window.innerWidth * 0.5;
  }).slice(0, 20);
  const scrollBottom = (window.scrollY || document.documentElement.scrollTop) + window.innerHeight;
  const docHeight = Math.max(document.body.scrollHeight, document.documentElement.scrollHeight);
  fixedBars.forEach((bar) => {
    const r = bar.getBoundingClientRect();
    const overlapsFooter = r.top < docHeight - scrollBottom + window.innerHeight && (r.bottom > window.innerHeight - 8);
    if (r.bottom >= window.innerHeight - 2 && docHeight > window.innerHeight + 40 && overlapsFooter) {
      push('7.31', '固定底栏可能遮挡页面底部内容，最后一行操作需要额外滚动才能看到',
        '底部内容可完整滚动到固定栏之上（预留底部内边距）',
        '固定栏高 ' + Math.round(r.height) + 'px，页面高 ' + docHeight + 'px，未检测到等值底部留白', bar,
        { severityHint: 'P1', confidence: 0.55, property: 'fixed-bottom-overlap' });
    }
  });
  const bodyOverflow = getComputedStyle(document.body).overflow;
  const openOverlay = Array.prototype.slice.call(document.querySelectorAll('[class*=modal], [class*=dialog], [class*=drawer], [role=dialog]'))
    .some((el) => visible(el));
  if (bodyOverflow === 'hidden' && !openOverlay) {
    push('7.31', '页面滚动被锁定但看不到任何弹层，用户无法滚动页面', '无弹层时 body 滚动应可用',
      'body overflow=hidden 且未检测到可见弹层', null, { severityHint: 'P1', confidence: 0.7, evidenceType: 'overflow-probe', property: 'scroll-lock' });
  }

  /* ---------------- 7.20 加载残留 ---------------- */
  const skeleton = Array.prototype.slice.call(document.querySelectorAll('[class*=skeleton], [class*=loading], [class*=spinner], [class*=shimmer]'))
    .filter(visible).slice(0, 20);
  if (skeleton.length > 0) {
    push('7.20', '页面稳定后仍显示加载占位，可能是加载态未正确结束', '数据就绪后加载占位消失',
      '稳定化之后仍有 ' + skeleton.length + ' 个加载占位可见', skeleton[0],
      { severityHint: 'P1', confidence: 0.6, evidenceType: 'skeleton-probe', property: 'loading-residue', raw: { count: skeleton.length } });
  }

  return {
    url: location.href,
    findings,
    summary: {
      total: findings.length,
      byDimension: findings.reduce((acc, f) => { acc[f.dimension] = (acc[f.dimension] || 0) + 1; return acc; }, {}),
      focusMissing, hardcodedLight, rtlHits, emojiHits, darkMediaCount, skeletonVisible: skeleton.length,
    },
    note: '本文件只做静态与无副作用探测（不点击、不提交）；7.26 打印视图与 7.34 角色差异需按场景驱动执行',
  };
})()
