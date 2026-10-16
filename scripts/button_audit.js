/**
 * 7.22 / 7.23 页面侧按钮盘点（静态、只读、零风险）
 *
 * 作为 IIFE 注入，返回 JSON 字符串：
 *   - mcp__playwright 的 browser_evaluate：直接传本文件全文
 *   - node：page.evaluate(fs.readFileSync('button_audit.js','utf8'))
 *
 * 只读：不点击、不提交、不改状态。
 *
 * 关键判定（均来自实测修正，勿轻易放宽）：
 *   1. **可见性**用 `checkVisibility()` + 非空 bbox。隐藏容器（弹框/抽屉未打开）内的按钮
 *      与尺寸为 0 的元素（自定义样式替代下的原生 checkbox）都不可交互，归「不可观测」，
 *      **不是可点击性缺陷**；它们由 7.14 弹框走查覆盖。
 *   2. **定位必须带 nth**：同一选择器常匹配多个元素（列表每行的按钮），只记 `sel` 会让
 *      点击落到错误的元素上（实测曾因此把「字段值」点到并触发下载）。
 *   3. **`source` 分级**：`button` / `[role=button]` / `input[type=submit|button|reset]` /
 *      含 btn 类名 → 标准按钮；`[onclick]` 泛匹配到的 `li` / `span` / 无 btn 类的 `a`
 *      （如字段 chip）→ `generic`「疑似可点元素」，**单独成表、默认不点击、不参与按钮配对**。
 *   4. **重复按钮按组归并**（列表每行一个「编辑」），只保留代表并记 `duplicateCount`。
 *   5. **遮挡判定要分强弱**：被 1–2 个采样点挡住多为滚动/边缘伪影（`low`，记待确认），
 *      被 ≥3 点挡住才判 `high`（真遮挡）。
 */
(() => {
  // 作用域：由 run_button_audit.cjs 通过 window.__AUDIT_SCOPE 注入，用于盘点「点击后弹出的弹窗」内部按钮。
  // 未注入时盘点整页。定位仍用全局选择器（selOf 判断唯一性时按 document 计）。
  const SCOPE = (typeof window !== 'undefined' && window.__AUDIT_SCOPE) ? window.__AUDIT_SCOPE : null;
  const root = SCOPE ? (document.querySelector(String(SCOPE)) || document) : document;
  const norm = s => String(s == null ? '' : s)
    .replace(/[\u200b-\u200f\u2028-\u202f\ufeff]/g, '')
    .replace(/\s+/g, '')
    .trim();
  const esc = s => String(s).replace(/([^\w-])/g, '\\$1');

  function selOf(el) {
    if (el.id) return '#' + el.id;
    if (el.dataset) {
      const k = Object.keys(el.dataset)[0];
      if (k) { const s = el.tagName.toLowerCase() + '[data-' + k.replace(/[A-Z]/g, m => '-' + m.toLowerCase()) + ']'; try { if (document.querySelectorAll(s).length === 1) return s; } catch (e) {} }
    }
    const cs = String(el.className || '').split(/\s+/)
      .filter(c => c && !/\d{4,}/.test(c) && !/^(ng|css|sc|jsx|v)-/.test(c));
    if (cs.length) {
      const s = el.tagName.toLowerCase() + '.' + cs.slice(0, 2).map(esc).join('.');
      try { if (document.querySelectorAll(s).length === 1) return s; } catch (e) {}
    }
    const parts = [];
    let cur = el;
    for (let i = 0; i < 4 && cur && cur.nodeType === 1; i++) {
      let p = cur.tagName.toLowerCase();
      const c0 = String(cur.className || '').trim().split(/\s+/).filter(Boolean)[0];
      if (c0) p += '.' + esc(c0);
      parts.unshift(p);
      const s = parts.join(' > ');
      try { if (document.querySelectorAll(s).length === 1) return s; } catch (e) {}
      cur = cur.parentElement;
    }
    return parts.join(' > ') || el.tagName.toLowerCase();
  }

  // 记录 (sel, nth)：选择器可能命中多个元素，点击时必须按 nth 精确定位
  function locOf(el) {
    const sel = selOf(el);
    let nth = 0;
    try { const list = document.querySelectorAll(sel); const i = Array.prototype.indexOf.call(list, el); if (i > 0) nth = i; } catch (e) {}
    return { sel, nth };
  }

  function visibility(el, cs) {
    if (cs.display === 'none') return 'display:none';
    if (cs.visibility === 'hidden') return 'visibility:hidden';
    if (parseFloat(cs.opacity) === 0) return 'opacity:0';
    if (typeof el.checkVisibility === 'function') {
      try { if (!el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return 'not-rendered(隐藏容器)'; } catch (e) {}
    } else if (el.offsetParent === null && cs.position !== 'fixed') return 'offsetParent:null(隐藏容器)';
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return 'zero-size(不可交互,如自定义样式替代的原生控件)';
    return 'visible';
  }

  const RE_BTN_CLASS = /btn|button/i;
  function sourceOf(el) {
    if (/^button$/i.test(el.tagName)) return 'button';
    if (el.getAttribute('role') === 'button') return 'button';
    if (/^input$/i.test(el.tagName) && /submit|button|reset/i.test(el.getAttribute('type') || '')) return 'button';
    if (RE_BTN_CLASS.test(String(el.className || ''))) return 'button';
    return 'generic';
  }

  // 【F30】风险词表单源化：与 scripts/node/risk_words.cjs 的 DANGER_WORDS 同源
  // （此前纯中文，英文 Delete/Remove 按钮落 safe 被真点——安全问题）。
  // 词表改动须同步 risk_words.cjs 与 discover_scenarios.py，parity 测试守住。
  //
  // 【F30 词边界修复】英文危险词此前用**裸子串**匹配：F30 新增的 `drop` 让
  // Dropdown / dropdown / Drag and drop / Drop files here 全被判 danger，这些按钮在
  // safe 策略下永不被点击——7.23 的覆盖被静默丢失（不报错、不留痕，只是少跑一堆用例）。
  // 现给英文危险词加 `\b` 词边界，只在「整词即危险动作」时才判 danger。
  // 注意 `sign-out` 含连字符：\b 在连字符两侧成立，故与 signout 等价，无需特判。
  // `drop` 额外加 `(?!-)`：`\b` 在连字符处成立，光靠 \b 仍会把 drop-down 这类
  // 复合词判成 danger（与 Dropdown 同族的误伤）。drop 单独列出以挂这个后视否定。
  const RE_DANGER = /删除|移除|移出|清空|退出|注销|停用|禁用|解散|撤销|解绑|退款|支付|结算|批量删|下线|作废|销毁|\b(delete|remove|logout|signout|sign-out|unbind|destroy|purge|terminate)\b|\bdrop\b(?!-)/i;
  // 【F30 caution 归位修复】`reset`/「重置」此前同时出现在 RE_DANGER 与 RE_CAUTION，
  // 而 riskOf 先判 danger —— 「重置」表单按钮被判 danger，在 safe 策略下被拒绝点击。
  // 「重置」不丢数据（表单回默认值，可逆），归 caution 才是正解：从 RE_DANGER 移除
  // 重置与 \breset\b（消除与 CAUTION 的重复），保留在 RE_CAUTION 里按caution 处理。
  const RE_CAUTION = /保存|提交|确定|确认|创建|新建|添加|新增|导入|上传|发送|同步|发布|启用|开启|绑定|购买|续费|修改|编辑|更新|应用|分配|授权|合并|移动|转移|设为|重置|\breset\b/i;
  function riskOf(label) {
    const t = norm(label);
    if (!t) return 'caution';                             // 无文本图标按钮：不知是关闭还是删除 → 保守
    if (RE_DANGER.test(t)) return 'danger';
    if (RE_CAUTION.test(t)) return 'caution';
    return 'safe';
  }

  function hitTest(el, r) {
    if (r.width < 1 || r.height < 1) return { ok: null, hit: 0, blocked: 0, blocker: null, severity: null, reason: 'zero-size' };
    if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth)
      return { ok: null, hit: 0, blocked: 0, blocker: null, severity: null, reason: 'out-of-viewport(需先 scrollIntoView)' };
    const pts = [[0.5, 0.5], [0.25, 0.5], [0.75, 0.5], [0.5, 0.25], [0.5, 0.75]];
    let hit = 0, blocked = 0, blocker = null;
    for (const [fx, fy] of pts) {
      const x = Math.round(r.left + r.width * fx), y = Math.round(r.top + r.height * fy);
      if (x < 0 || y < 0 || x > innerWidth - 1 || y > innerHeight - 1) continue;
      const got = document.elementFromPoint(x, y);
      if (!got) continue;
      if (got === el || el.contains(got)) hit++;
      else { blocked++; if (!blocker) blocker = { sel: selOf(got), tag: got.tagName.toLowerCase(), text: norm(got.textContent).slice(0, 24), cls: String(got.className || '').split(/\s+/)[0] || '' }; }
    }
    const severity = blocked >= 3 ? 'high' : (blocked > 0 ? 'low' : null);
    return { ok: hit > 0, hit, blocked, blocker, severity, reason: blocked ? (severity === 'high' ? '被遮挡' : '疑似被遮挡(少数采样点)') : (hit === 0 ? '采样点均未命中自身' : null) };
  }

  const SEL = 'button,[role=button],input[type=submit],input[type=button],input[type=reset],a[class*=btn],a[class*=Btn],a[class*=button],input[class*=btn],[class*=comBtn],[onclick]';
  const all = Array.prototype.slice.call(root.querySelectorAll(SEL));
  const btns = [], hidden = [], containers = [];

  for (const el of all) {
    const cs = getComputedStyle(el);
    if (!/^(button|input)$/i.test(el.tagName) && !el.getAttribute('role')) {
      const inner = el.querySelectorAll('button,[role=button],a[class*=btn],a[class*=Btn],input[type=submit]').length;
      if (inner >= 2) { containers.push({ sel: selOf(el), inner }); continue; }
    }
    const vis = visibility(el, cs);
    if (vis !== 'visible') { hidden.push({ sel: selOf(el), text: norm(el.textContent || el.getAttribute('title') || '').slice(0, 24), reason: vis }); continue; }

    const r = el.getBoundingClientRect();
    const rawText = norm(el.innerText || el.textContent);
    const label = rawText || String(el.getAttribute('title') || el.getAttribute('aria-label') || '').trim();
    const iconOnly = !rawText && !!el.querySelector('svg,i,img,[class*=icon]');
    const hit = hitTest(el, r);
    const loc = locOf(el);

    let near = '';
    const box = el.closest('td,li,[class*=card],[class*=item],[class*=row],div');
    if (box && box.textContent) near = norm(box.textContent).replace(rawText, '').slice(0, 24);

    const state = {
      disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
      disabledClass: /(^|[\s_])(is-)?disabled([\s_-]|$)/i.test(String(el.className || '')),
      pointerEvents: cs.pointerEvents,
      cursor: cs.cursor,
      type: el.getAttribute('type') || null,
      inForm: !!el.closest('form'),
    };

    const blocks = [];
    if (state.disabled) blocks.push('disabled');
    if (state.disabledClass) blocks.push('disabled-class');
    if (state.pointerEvents === 'none') blocks.push('pointer-events:none');
    if (r.width < 1 || r.height < 1) blocks.push('zero-size');
    if (hit.severity === 'high') blocks.push('被遮挡(' + hit.blocked + '点)');
    else if (hit.severity === 'low') blocks.push('疑似被遮挡(' + hit.blocked + '点,待确认)');

    btns.push({
      sel: loc.sel, nth: loc.nth, tag: el.tagName.toLowerCase(), source: sourceOf(el),
      text: (el.innerText || el.textContent || '').trim().slice(0, 40),
      normText: rawText.slice(0, 40),
      title: String(el.getAttribute('title') || '').slice(0, 40),
      ariaLabel: String(el.getAttribute('aria-label') || '').slice(0, 40),
      iconOnly, near, risk: riskOf(label),
      bbox: { x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) },
      state, hit,
      clickable: { ok: blocks.length === 0, blocks }
    });
  }

  // 重复按钮归并（同 文本+风险+标签+可点击性）
  const groups = {}, unique = [];
  for (const b of btns) {
    const k = (b.normText || b.title || b.ariaLabel || 'icon') + '|' + b.risk + '|' + b.tag + '|' + (b.clickable.ok ? 'ok' : b.clickable.blocks.join(','));
    if (groups[k]) { groups[k].duplicateCount++; continue; }
    b.duplicateCount = 1; groups[k] = b; unique.push(b);
  }

  const std = unique.filter(b => b.source === 'button');
  const generic = unique.filter(b => b.source === 'generic');
  return JSON.stringify({
    generatedAt: new Date().toISOString(),
    url: location.href,
    scope: SCOPE || 'document',
    scopeFound: !SCOPE || !!document.querySelector(String(SCOPE)),
    viewport: { w: innerWidth, h: innerHeight },
    count: btns.length,
    uniqueCount: std.length,                    // 标准按钮种类（配对与判定以此为准）
    genericCount: generic.length,               // 疑似可点元素（[onclick] 泛匹配，默认不点击）
    hiddenCount: hidden.length,                  // 隐藏容器内 / 不可交互 → 不可观测，非缺陷
    containerCount: containers.length,
    riskSummary: std.reduce((a, b) => { a[b.risk] = (a[b.risk] || 0) + 1; return a; }, {}),
    notClickableCount: std.filter(b => !b.clickable.ok).length,
    hidden, containers,
    buttons: std,
    genericClickables: generic
  });
})()
