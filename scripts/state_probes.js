/*
 * 状态场景页内探测（暗色模式 / 打印视图 / 接口异常后的界面）
 *
 * 覆盖维度：7.25 暗色模式与主题切换、7.26 打印与导出视图、7.33 接口异常与慢网络下的界面
 * （7.32 页面级状态残留由驱动在页面外比对状态快照，不走本脚本）
 *
 * 为什么单独一个脚本：这三个维度都要求**先改变页面所处状态**（emulate colorScheme=dark /
 * emulate media=print / 拦截接口返回 500），再重新探测。extra_checks.js 跑在默认状态下，
 * 覆盖不了"切换后"的渲染。判定逻辑与采集逻辑分离：
 *   - darkFindings / printFindings / failureFindings 是纯函数（输入快照数组，输出 findings），
 *     node 侧可直接单测（见 scripts/tests/state_probes_smoke.cjs）；
 *   - 文件尾部是页内采集器：读 window.__vpProbe.mode 决定采哪一路，由驱动
 *     scripts/node/run_state_scenarios.cjs 在切换状态后调用。
 *
 * 约束（同仓内其它页内脚本）：全文不出现反斜杠字面量——正则字符类一律用
 * String.fromCharCode 构造，字符串匹配用 indexOf/includes，避免 MCP 传参吃掉一层
 * 反斜杠导致静默改语义。结尾是裸 })() 的 IIFE，可直接内联或整体 evaluate。
 *
 * 判定口径（保守，防假缺陷）：
 *   - 暗色：对比度 < 4.5 记 confirmed（渲染事实，确定性测量）；背景仍近白的记 confirmed
 *     （未适配）。有 dark 样式但个别元素对比不足同样出声。
 *   - 打印：操作按钮误入打印稿记 pending（是否保留是设计决策，不擅自判缺陷）；
 *     表格内容在打印下载体内被裁、白字白底记 confirmed（事实性截断/不可读）。
 *   - 接口异常：内容区近空白（白屏）或骨架屏残留记 confirmed（P1）；
 *     无错误提示且无重试入口记 pending（提示文案是否合格需人工看）。
 */
(function () {
  var CH = function (c) { return String.fromCharCode(c); };

  /* ---------------- 纯工具 ---------------- */

  function parseColor(value) {
    if (!value) return null;
    var text = String(value).trim();
    if (text.indexOf('rgb') !== 0) return null;
    var open = text.indexOf('(');
    var close = text.lastIndexOf(')');
    if (open < 0 || close < 0) return null;
    var parts = text.slice(open + 1, close).split(',').map(function (p) { return parseFloat(p); });
    if (parts.length < 3 || parts.some(function (p) { return isNaN(p); })) return null;
    var alpha = parts.length > 3 ? parts[3] : 1;
    return { r: parts[0], g: parts[1], b: parts[2], a: isNaN(alpha) ? 1 : alpha };
  }

  function luminance(c) {
    var f = function (v) {
      var s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }

  function contrast(a, b) {
    if (!a || !b) return null;
    var l1 = luminance(a);
    var l2 = luminance(b);
    var hi = Math.max(l1, l2);
    var lo = Math.min(l1, l2);
    return Number(((hi + 0.05) / (lo + 0.05)).toFixed(2));
  }

  function isNearWhite(c) {
    return !!c && c.a >= 0.9 && c.r >= 250 && c.g >= 250 && c.b >= 250;
  }

  function hasAny(text, words) {
    var t = String(text || '').toLowerCase();
    for (var i = 0; i < words.length; i += 1) {
      if (t.indexOf(words[i]) !== -1) return true;
    }
    return false;
  }

  function finding(dimension, symptom, expected, actual, severityHint, confidence, status, property, raw) {
    return {
      dimension: dimension,
      symptom: symptom,
      expected: expected,
      actual: actual,
      severityHint: severityHint,
      severity: severityHint,
      confidence: confidence,
      status: status || 'confirmed',
      element: null,
      evidence: [{ type: 'state-probe', result: status === 'pending' ? 'info' : 'mismatch' }],
      sources: ['state-probes'],
      property: property || null,
      raw: raw || null,
    };
  }

  /* ---------------- 7.25 暗色模式判定 ----------------
   * items: [{ sel, text, color, bg }] —— 可见文本元素及其计算色与有效背景色
   * 判据：对比度 < 4.5 → confirmed（P2）；背景仍近白 → confirmed（P2，未适配）。
   */
  var DARK_MIN_CONTRAST = 4.5;

  function darkFindings(items) {
    var out = [];
    var lowContrast = 0;
    var hardWhite = 0;
    var firstLow = null;
    var firstWhite = null;
    (items || []).forEach(function (it) {
      var color = parseColor(it.color);
      var bg = parseColor(it.bg);
      if (isNearWhite(bg)) {
        hardWhite += 1;
        if (!firstWhite) firstWhite = it;
      }
      var ratio = contrast(color, bg);
      if (ratio != null && ratio < DARK_MIN_CONTRAST) {
        lowContrast += 1;
        if (!firstLow) firstLow = it;
      }
    });
    if (hardWhite > 0) {
      out.push(finding('7.25',
        '深色模式下仍有 ' + hardWhite + ' 个元素背景为近白色，页面未做深色适配，深色环境下刺眼',
        '深色模式下背景应跟随主题变暗，或使用主题变量',
        'emulate colorScheme=dark 后仍有近白背景元素（首个：' + (firstWhite && firstWhite.sel) + '）',
        'P2', 0.8, 'confirmed', 'dark-hardcoded-light',
        { hardWhite: hardWhite, firstSel: firstWhite && firstWhite.sel }));
    }
    if (lowContrast > 0) {
      out.push(finding('7.25',
        '深色模式下有 ' + lowContrast + ' 处文字与背景对比度低于 4.5，内容不易辨认',
        '文字与背景对比度不低于 4.5',
        '最低对比度出现在 ' + (firstLow && firstLow.sel) + '（文本：' + String(firstLow && firstLow.text || '').slice(0, 20) + '）',
        'P2', 0.75, 'confirmed', 'dark-contrast',
        { lowContrast: lowContrast, firstSel: firstLow && firstLow.sel }));
    }
    return out;
  }

  /* ---------------- 7.26 打印视图判定 ----------------
   * items: [{ sel, text, tag, color, bg, isAction, tableOverflow }]
   * 判据：操作按钮在打印态可见 → pending（设计决策）；
   *       表格内容打印态被裁 / 白字白底 → confirmed（事实性不可读）。
   */
  var PRINT_ACTION_WORDS = ['保存', '提交', '删除', '导出', '打印', '取消', '新建', '编辑',
    'save', 'submit', 'delete', 'export', 'print', 'cancel', 'create', 'edit'];

  function printFindings(items) {
    var out = [];
    var actionVisible = 0;
    var firstAction = null;
    var clipped = 0;
    var invisible = 0;
    (items || []).forEach(function (it) {
      if (it.isAction && it.visible !== false) {
        actionVisible += 1;
        if (!firstAction) firstAction = it;
      }
      if (it.tableOverflow) clipped += 1;
      var color = parseColor(it.color);
      var bg = parseColor(it.bg);
      if (isNearWhite(color) && isNearWhite(bg)) invisible += 1;
    });
    if (actionVisible > 0) {
      out.push(finding('7.26',
        '打印视图下仍有 ' + actionVisible + ' 个操作按钮可见，可能误入打印稿',
        '打印稿只保留内容，不保留保存/删除等操作按钮',
        'emulate media=print 后操作按钮仍可见（首个：' + (firstAction && firstAction.sel) + '）',
        'P3', 0.6, 'pending', 'print-action-buttons',
        { actionVisible: actionVisible, firstSel: firstAction && firstAction.sel }));
    }
    if (clipped > 0) {
      out.push(finding('7.26',
        '打印视图下有 ' + clipped + ' 处表格内容被裁切，打印出来不完整',
        '打印态表格内容完整可读，不出现横向裁切',
        'emulate media=print 后表格 scrollWidth 仍超出 clientWidth',
        'P2', 0.7, 'confirmed', 'print-table-clip',
        { clipped: clipped }));
    }
    if (invisible > 0) {
      out.push(finding('7.26',
        '打印视图下有 ' + invisible + ' 处文字与背景同为近白色，打印出来看不见',
        '打印态文字与背景对比清晰',
        'emulate media=print 后存在近白文字叠近白背景',
        'P2', 0.75, 'confirmed', 'print-invisible-text',
        { invisible: invisible }));
    }
    return out;
  }

  /* ---------------- 7.33 接口异常后界面判定 ----------------
   * snap: { visibleChars, skeletonCount, errorHint, retryHint }
   * 判据：内容区近空白 → confirmed P1（白屏）；骨架屏残留 → confirmed P1；
   *       无错误提示且无重试入口 → pending（提示文案是否合格需人工看）。
   */
  var FAILURE_ERROR_WORDS = ['错误', '失败', '异常', '重试', '稍后', '无法', '加载不',
    'error', 'fail', 'retry', 'try again', 'something went'];
  var FAILURE_MIN_CHARS = 50;

  function failureFindings(snap) {
    var out = [];
    var s = snap || {};
    var chars = s.visibleChars || 0;
    var skeleton = s.skeletonCount || 0;
    var hasError = s.errorHint || hasAny(s.errorText, FAILURE_ERROR_WORDS);
    var hasRetry = s.retryHint || hasAny(s.retryText, FAILURE_ERROR_WORDS);
    // 白屏判定必须叠加"无错误提示"：只显示一条短错误提示的页面是合法错误态，
    // 内容少不等于白屏（否则"加载失败，请重试"这种正确 UI 会被误判）。
    if (chars < FAILURE_MIN_CHARS && !hasError) {
      out.push(finding('7.33',
        '接口返回 500 后内容区近乎空白（白屏），用户看不到任何内容或提示',
        '接口失败时展示错误提示或兜底内容，不白屏',
        '拦截接口返回 500 并 reload 后，可见文本仅 ' + chars + ' 字符',
        'P1', 0.8, 'confirmed', 'failure-white-screen',
        { visibleChars: chars }));
    }
    if (skeleton > 0) {
      out.push(finding('7.33',
        '接口返回 500 后骨架屏/加载占位仍未消失，用户永远等不到内容',
        '接口失败时加载态应结束并给出错误提示',
        '拦截接口返回 500 并 reload 后仍有 ' + skeleton + ' 个加载占位可见',
        'P1', 0.75, 'confirmed', 'failure-skeleton-residue',
        { skeletonCount: skeleton }));
    }
    if (!hasError && !hasRetry && chars >= FAILURE_MIN_CHARS) {
      out.push(finding('7.33',
        '接口返回 500 后页面无错误提示也无重试入口，用户不知道发生了什么',
        '接口失败时给出明确错误提示与重试入口',
        '拦截接口返回 500 并 reload 后未检出错误/重试提示（可见文本 ' + chars + ' 字符）',
        'P2', 0.5, 'pending', 'failure-no-error-hint',
        { visibleChars: chars }));
    }
    return out;
  }

  /* ---------------- node 导出（单测入口） ---------------- */
  var api = {
    parseColor: parseColor,
    contrast: contrast,
    darkFindings: darkFindings,
    printFindings: printFindings,
    failureFindings: failureFindings,
  };
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = api;
    return;
  }

  /* ---------------- 页内采集（驱动调用） ----------------
   * 驱动先 page.evaluate 设置 window.__vpProbe = { mode }，再整体 evaluate 本文件。
   */
  var mode = (window.__vpProbe && window.__vpProbe.mode) || 'dark';
  var findings = [];

  function selectorOf(el) {
    if (!el || !el.tagName) return '';
    if (el.id) return '#' + el.id;
    var cls = (el.className && typeof el.className === 'string')
      ? el.className.split(CH(32)).filter(Boolean).slice(0, 2).join('.')
      : '';
    return el.tagName.toLowerCase() + (cls ? '.' + cls : '');
  }

  function visible(el) {
    if (!el || !el.getBoundingClientRect) return false;
    var r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;
    var cs = getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) !== 0;
  }

  function effectiveBg(el) {
    var node = el;
    while (node && node !== document.documentElement) {
      var bg = parseColor(getComputedStyle(node).backgroundColor);
      if (bg && bg.a > 0.05) return bg;
      node = node.parentElement;
    }
    return { r: 255, g: 255, b: 255, a: 1 };
  }

  function directText(el) {
    var t = '';
    for (var i = 0; i < el.childNodes.length; i += 1) {
      var n = el.childNodes[i];
      if (n.nodeType === 3) t += n.nodeValue;
    }
    return t.trim();
  }

  if (mode === 'dark') {
    var items = [];
    Array.prototype.slice.call(document.querySelectorAll('*')).filter(visible).slice(0, 3000).forEach(function (el) {
      var text = directText(el);
      if (!text) return;
      var cs = getComputedStyle(el);
      items.push({
        sel: selectorOf(el),
        text: text.slice(0, 20),
        color: cs.color,
        bg: (function () { var c = effectiveBg(el); return 'rgba(' + Math.round(c.r) + ',' + Math.round(c.g) + ',' + Math.round(c.b) + ',' + c.a + ')'; })(),
      });
    });
    findings = darkFindings(items);
  } else if (mode === 'print') {
    var pitems = [];
    Array.prototype.slice.call(document.querySelectorAll('button, [role=button], a[href], input[type=submit]'))
      .filter(visible).slice(0, 200).forEach(function (el) {
        pitems.push({
          sel: selectorOf(el),
          tag: el.tagName.toLowerCase(),
          text: (el.innerText || el.value || el.getAttribute('aria-label') || '').slice(0, 20),
          isAction: hasAny(el.innerText || el.value || el.getAttribute('aria-label') || '', PRINT_ACTION_WORDS),
          visible: true,
        });
      });
    Array.prototype.slice.call(document.querySelectorAll('table, [role=table]')).filter(visible).slice(0, 50).forEach(function (el) {
      pitems.push({
        sel: selectorOf(el),
        tag: 'table',
        tableOverflow: el.scrollWidth > el.clientWidth + 1,
      });
    });
    Array.prototype.slice.call(document.querySelectorAll('*')).filter(visible).slice(0, 2000).forEach(function (el) {
      var text = directText(el);
      if (!text) return;
      var cs = getComputedStyle(el);
      var c = parseColor(cs.color);
      var bg = effectiveBg(el);
      if (isNearWhite(c) && isNearWhite(bg)) {
        pitems.push({ sel: selectorOf(el), text: text.slice(0, 20), color: cs.color, bg: 'rgba(255,255,255,1)' });
      }
    });
    findings = printFindings(pitems);
  } else if (mode === 'failure') {
    // 空白字符集用 charCode 构造（全文无反斜杠约束）：空格/制表/换行/回车/换页/纵表/ NBSP / 全角空格
    var WS = new RegExp('[' + CH(32) + CH(9) + CH(10) + CH(13) + CH(0x0C) + CH(0x0B) + CH(0x00A0) + CH(0x3000) + ']+', 'g');
    var bodyText = (document.body && document.body.innerText) || '';
    var skel = Array.prototype.slice.call(
      document.querySelectorAll('[class*=skeleton], [class*=loading], [class*=spinner], [class*=shimmer]')
    ).filter(visible).length;
    var errText = '';
    Array.prototype.slice.call(document.querySelectorAll('[class*=error], [class*=empty], [role=alert], [class*=toast], [class*=message]'))
      .filter(visible).slice(0, 20).forEach(function (el) { errText += ' ' + (el.innerText || ''); });
    findings = failureFindings({
      visibleChars: bodyText.replace(WS, '').length,
      skeletonCount: skel,
      errorText: errText,
    });
  }

  findings.forEach(function (f) {
    if (f.dimension === '7.25' || f.dimension === '7.26') {
      // 带上首个命中元素定位，便于人工回页查找
      var sel = f.raw && (f.raw.firstSel || f.raw.firstTarget);
      if (sel) f.element = { selector: sel, nth: 0, anchor: f.property };
    }
  });

  return JSON.stringify({ mode: mode, url: location.href, findings: findings, total: findings.length });
})()
