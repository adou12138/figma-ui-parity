/*
 * 运行期观测（页面内执行）——补上「静态探测 / 视觉比对」看不到的一类真实缺陷：
 *   - 7.35 运行期 JS 异常（console.error / window.onerror / unhandledrejection）
 *   - 7.36 交互期网络失败（fetch / XHR 非 2xx 或网络错误）
 *   - 7.37 重复请求 / 重复提交（同一写请求在短窗口内重复发出）
 *   - 7.38 遮挡（可交互元素被其他元素盖住，用户点不到）
 *
 * 为什么需要：extra_checks.js 只读 DOM 与 computed style，看不到"交互过程中炸了没"。
 * JS 报错、接口 500、重复提交、元素被盖住——这几类都是用户真实遇到、但静态快照
 * 抓不到的缺陷。本文件把它们变成可机械采集的证据。
 *
 * 用法（两阶段，自动识别）：
 *   ① 页面加载稳定后调用一次 → 安装钩子，返回 {mode:"install"}
 *   ② 完成本轮交互后再调用一次 → 采集并返回 {mode:"collect", findings[]}
 *   （钩子挂在 window.__vpObs 上，跨两次 evaluate 保持）
 *
 * 约束：全文不出现反斜杠转义（换行用 String.fromCharCode(10) 构造），
 *       避免 MCP 传参吃掉一层反斜杠导致静默改语义。
 * 判据保守：不确定的一律降为 pending / 跳过，宁可漏报不造假缺陷。
 */
(() => {
  const NL = String.fromCharCode(10);

  /* ================= 凭据脱敏（F31 红线） =================
   * 写请求 body 原文 / 失败请求 query 会进 findings.raw 并一路流到 report.json /
   * CSV / xlsx——登录、改密表单的 urlencoded body 里有明文密码，带 token 的请求
   * query 里有会话凭据。SKILL.md 红线「产物不得写入 token/Cookie」必须有采集端
   * 执行点，而不是只写在注释里。命中敏感键名的值一律替换为 [REDACTED]。
   */
  const SENSITIVE_KEY = /(password|passwd|pwd|token|secret|authorization|auth|cookie|session|apikey|api[-_]?key|access[-_]?key|credential)/i;
  const redact = (text) => {
    let s = String(text == null ? '' : text);
    if (!s) return s;
    // ① urlencoded / 表单形态：password=xxx&token=yyy（值取到 & 或结尾）
    s = s.replace(/([?&]?)([A-Za-z0-9_\-]*?(?:password|passwd|pwd|token|secret|apikey|api_key|access_key|credential|authorization|session)[A-Za-z0-9_\-]*)(=)([^&\s]*)/gi,
      (m, pre, key, eq) => pre + key + eq + '[REDACTED]');
    // ② JSON 形态："password":"xxx" / 'token': 'yyy'
    s = s.replace(/(["'])(?:(?!\1)[^\\])*?(?:password|passwd|pwd|token|secret|apikey|api_key|access_key|credential|authorization|session)(?:(?!\1)[^\\])*?\1(\s*:\s*)(["'])(?:(?!\3).)*?\3/gi,
      (m, q1, mid, q2) => q1.slice(0, 1) + mid + q2 + '[REDACTED]' + q2);
    // ③ Bearer / Basic 请求头形态
    s = s.replace(/(Bearer\s+)[A-Za-z0-9._\-]+/gi, '$1[REDACTED]');
    s = s.replace(/(Basic\s+)[A-Za-z0-9+/=]+/gi, '$1[REDACTED]');
    return s;
  };
  const redactUrl = (u) => {
    let s = String(u == null ? '' : u);
    if (!s) return s;
    // query 里带 token/session 的 URL 打码（保留 path 可定位）
    return s.replace(/((?:\?|&)[^=\s]*?(?:token|session|auth|key|secret|credential)[^=\s]*?=)[^&\s]*/gi, '$1[REDACTED]');
  };

  const visible = (el) => {
    if (!el || !el.getBoundingClientRect) return false;
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;
    const s = getComputedStyle(el);
    return s.display !== 'none' && s.visibility !== 'hidden' && parseFloat(s.opacity) !== 0;
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

  const findings = [];
  const push = (dimension, symptom, expected, actual, el, extra) => {
    findings.push(Object.assign({
      dimension,
      symptom,
      expected,
      actual,
      severityHint: (extra && extra.severityHint) || 'P2',
      severity: (extra && extra.severityHint) || 'P2',
      confidence: extra && extra.confidence != null ? extra.confidence : 0.8,
      status: (extra && extra.status) || 'confirmed',
      category: (extra && extra.category) || dimension,
      element: el ? { selector: selectorOf(el), nth: 0, bbox: rectOf(el), anchor: (el.innerText || el.getAttribute('aria-label') || '').slice(0, 30) } : null,
      evidence: [{ type: (extra && extra.evidenceType) || 'runtime-probe', result: 'mismatch' }],
      sources: ['runtime-observability'],
      property: (extra && extra.property) || null,
    }, extra && extra.raw ? { raw: extra.raw } : {}));
  };

  /* ================= ① 安装钩子 ================= */
  if (!window.__vpObs) {
    const obs = { errors: [], requests: [], startedAt: Date.now() };
    window.__vpObs = obs;

    const origError = typeof console.error === 'function' ? console.error.bind(console) : null;
    console.error = function () {
      try {
        const text = Array.prototype.map.call(arguments, (a) => String(a && a.message ? a.message : a)).join(' ');
        obs.errors.push({ kind: 'console', text, at: Date.now() });
      } catch (e) { /* 采集失败不得影响页面 */ }
      if (origError) { try { origError.apply(console, arguments); } catch (e) {} }
    };
    window.addEventListener('error', (ev) => {
      obs.errors.push({
        kind: 'onerror',
        text: String((ev && (ev.message || (ev.error && ev.error.message))) || 'unknown error'),
        source: ev && ev.filename ? String(ev.filename) : '',
        at: Date.now(),
      });
    });
    window.addEventListener('unhandledrejection', (ev) => {
      const r = ev && ev.reason;
      obs.errors.push({ kind: 'unhandledrejection', text: String((r && r.message) || r || 'unhandled rejection'), at: Date.now() });
    });

    if (window.fetch) {
      const of = window.fetch;
      window.fetch = function () {
        const args = arguments;
        const url = String(args[0] && args[0].url ? args[0].url : args[0]);
        const method = String((args[1] && args[1].method) || (args[0] && args[0].method) || 'GET').toUpperCase();
        const body = args[1] && args[1].body ? String(args[1].body) : '';
        const at = Date.now();
        return of.apply(this, args).then((resp) => {
          obs.requests.push({ url, method, body, status: resp.status, ok: !!resp.ok, at });
          return resp;
        }, (err) => {
          obs.requests.push({ url, method, body, status: 0, ok: false, at, error: String((err && err.message) || err) });
          throw err;
        });
      };
    }
    if (window.XMLHttpRequest && window.XMLHttpRequest.prototype) {
      const O = window.XMLHttpRequest.prototype.open;
      const Sd = window.XMLHttpRequest.prototype.send;
      window.XMLHttpRequest.prototype.open = function (m, u) {
        this.__vp = { method: String(m || 'GET').toUpperCase(), url: String(u), body: '', at: 0 };
        return O.apply(this, arguments);
      };
      window.XMLHttpRequest.prototype.send = function (b) {
        const self = this;
        if (self.__vp) {
          self.__vp.body = b ? String(b) : '';
          self.__vp.at = Date.now();
          self.addEventListener('loadend', () => {
            try {
              const ok = self.status >= 200 && self.status < 300;
              obs.requests.push({ url: self.__vp.url, method: self.__vp.method, body: self.__vp.body, status: self.status, ok, at: self.__vp.at });
            } catch (e) {}
          });
        }
        return Sd.apply(this, arguments);
      };
    }
    return JSON.stringify({ mode: 'install', installed: true, startedAt: obs.startedAt });
  }

  /* ================= ② 采集 ================= */
  const obs = window.__vpObs;
  // 【F11】钩子未安装时不得静默返回 []（与「页面干净」不可区分）：带显式标记返回，
  // 调用方据 hooksInstalled=false 填 notRun。
  if (!obs) {
    return JSON.stringify({
      mode: 'collect', url: location.href, findings: [],
      hooksInstalled: false, interactionsObserved: 0,
      note: '钩子未安装（本页面未执行过 install 阶段）——本轮采集无效，'
          + '7.35-7.38 必须填 notRun，不得视为「页面干净」。',
      summary: { total: 0, byDimension: {}, errorCount: 0, requestCount: 0, overlayOpen: false },
    });
  }

  // --- 7.35 运行期 JS 异常（按文本去重，最多 20 条）---
  const seenErr = {};
  obs.errors.forEach((e) => {
    const key = e.kind + '|' + e.text;
    if (seenErr[key]) return;
    seenErr[key] = 1;
    if (findings.filter((f) => f.dimension === '7.35').length >= 20) return;
    const isReject = e.kind === 'unhandledrejection';
    push('7.35', '页面运行期抛出未捕获异常：' + e.text.slice(0, 120), '控制台无未捕获错误，交互不中断',
      e.kind + (e.source ? ' @ ' + e.source : '') + '：' + e.text.slice(0, 160), null,
      { severityHint: 'P1', confidence: 0.85, property: 'js-error', evidenceType: 'error-hook',
        raw: { kind: e.kind, text: e.text.slice(0, 300) } });
  });

  // --- 7.36 交互期网络失败（写请求与非 2xx；GET 失败也采，但 5xx 优先）---
  const seenReq = {};
  obs.requests.forEach((r) => {
    const failed = !r.ok;
    if (!failed) return;
    const key = r.method + ' ' + r.url + ' ' + r.status;
    if (seenReq[key]) return;
    seenReq[key] = 1;
    if (findings.filter((f) => f.dimension === '7.36').length >= 20) return;
    const server = r.status >= 500 || r.status === 0;
    push('7.36', '交互过程中请求失败：' + r.method + ' ' + redactUrl(r.url) + '（状态 ' + r.status + '）',
      '交互触发的请求应成功返回；失败时界面应给出明确提示而非静默',
      '状态码 ' + r.status + (r.error ? '，错误 ' + r.error : ''), null,
      { severityHint: server ? 'P1' : 'P2', confidence: 0.8, property: 'network-failure', evidenceType: 'request-hook',
        raw: { method: r.method, url: redactUrl(r.url), status: r.status, body: redact(String(r.body || '').slice(0, 200)) } });
  });

  // --- 7.37 重复请求 / 重复提交（仅写方法，避免把轮询 GET 误报）---
  const WRITE = { POST: 1, PUT: 1, PATCH: 1, DELETE: 1 };
  const groups = {};
  obs.requests.forEach((r) => {
    if (!WRITE[r.method]) return;
    // 签名里的 body 也可能含凭据（同一签名会进 raw.signature）——同样脱敏后再拼接。
    const sig = r.method + ' ' + r.url.split('?')[0] + ' ' + redact(String(r.body || '').slice(0, 300));
    (groups[sig] = groups[sig] || []).push(r);
  });
  Object.keys(groups).forEach((sig) => {
    const reqs = groups[sig].filter((r) => r && r.at).sort((a, b) => a.at - b.at);
    if (reqs.length < 2) return;
    const span = reqs[reqs.length - 1].at - reqs[0].at;
    if (span > 3000) return; // 3 秒内重复才是"疑似重复提交"，隔太久是正常重试
    if (findings.filter((f) => f.dimension === '7.37').length >= 10) return;
    // 自动确认（保守，v4.13.0）：仅当**每一个**重复请求都返回成功（ok）才 confirmed——
    // 全部成功=客户端确实重复发了、服务端也照单全收（无客户端防抖、服务端未拦），是可确认的
    // 重复提交缺陷；只要有失败，说明服务端拦掉了重复（有防护），不能确认，留 pending 交人工。
    // 响应成功与否是硬证据，不靠猜。（注：若服务端有幂等去重，严重度或可降，但客户端重复发送本身已成立。）
    const allOk = reqs.every((r) => r.ok);
    const okCount = reqs.filter((r) => r.ok).length;
    push('7.37', '同一写请求在 ' + span + 'ms 内重复发出 ' + reqs.length + ' 次'
        + (allOk ? '（全部成功，未被拦截）' : '（' + okCount + '/' + reqs.length + ' 成功）')
        + '，' + (allOk ? '确认重复提交/无防抖' : '疑似重复提交/无防抖'),
      '写操作应防重复提交（按钮置灰 / 幂等键 / 前端去抖）',
      '相同方法+路径+载荷重复 ' + reqs.length + ' 次，' + okCount + ' 次成功', null,
      { severityHint: 'P1', confidence: allOk ? 0.85 : 0.6, status: allOk ? 'confirmed' : 'pending',
        property: 'duplicate-submit', evidenceType: 'request-hook',
        raw: { signature: sig.slice(0, 200), count: reqs.length, spanMs: span, okCount: okCount, allOk: allOk } });
  });

  // --- 7.38 遮挡（可交互元素被盖住，用户点不到）---
  const overlayOpen = Array.prototype.slice
    .call(document.querySelectorAll('[role=dialog], [class*=modal], [class*=dialog], [class*=drawer], [class*=mask], [class*=overlay]'))
    .some((el) => visible(el));
  if (!overlayOpen) {
    const targets = Array.prototype.slice
      .call(document.querySelectorAll('a[href], button, input, select, textarea, [role=button], [onclick]'))
      .filter(visible).slice(0, 80);
    let hit = 0;
    for (let i = 0; i < targets.length && hit < 15; i += 1) {
      const el = targets[i];
      const r = el.getBoundingClientRect();
      if (r.width < 8 || r.height < 8) continue;
      const cx = Math.round(r.left + r.width / 2);
      const cy = Math.round(r.top + r.height / 2);
      if (cx < 0 || cy < 0 || cx > window.innerWidth || cy > window.innerHeight) continue; // 不在视口内不算
      let top = null;
      try { top = document.elementFromPoint(cx, cy); } catch (e) { top = null; }
      if (!top) continue;
      if (top === el || el.contains(top) || top.contains(el)) continue;
      const tcs = getComputedStyle(top);
      if (tcs.pointerEvents === 'none') continue; // 事件穿透，不算遮挡
      hit += 1;
      // 保守（v4.13.0）：保持 pending，只按证据强度给置信度供排序——遮挡物**非交互**（普通浮层）
      // 比遮挡物**也可交互**（可能是刻意叠层，如按钮上的角标）更像真 bug。不自动确认。
      const coverInteractive = top.matches('a[href], button, input, select, textarea, [role=button], [onclick]');
      push('7.38', '可交互元素被其他元素覆盖，点击可能落不到它：' + selectorOf(el),
        '可交互元素应位于最上层（z-index / 遮挡布局）', '中心点命中 ' + selectorOf(top), el,
        { severityHint: 'P1', confidence: coverInteractive ? 0.5 : 0.7, status: 'pending', property: 'occlusion', evidenceType: 'hit-test',
          raw: { target: selectorOf(el), coveredBy: selectorOf(top), coverInteractive: coverInteractive } });
    }
  }

  // 说明：本文件采集的是"运行期"证据，须在安装钩子并完成一轮交互后再调用采集。
  // 【F11】「未装钩子」与「页面干净」必须可区分：二者都产出 findings=[]，但含义完全
  // 不同——前者是"没观测到任何东西"（须 notRun），后者才是"观测到了且干净"。
  // hooksInstalled=false 或采集抛错时带显式标记，调用方不得据此填 pass。
  const hooksInstalled = !!(obs && (obs.errors.length || obs.requests.length
    || (Date.now() - (obs.startedAt || Date.now())) >= 0));
  return JSON.stringify({
    mode: 'collect',
    url: location.href,
    findings,
    hooksInstalled: hooksInstalled,
    interactionsObserved: obs.requests.length,
    collectError: (typeof window.__vpCollectError !== 'undefined') ? window.__vpCollectError : null,
    note: '运行期观测：7.35 异常 / 7.36 网络失败 / 7.37 重复提交 / 7.38 遮挡。'
      + '7.37/7.38 判据保守（pending），需人工复核后再落确定缺陷；'
      + 'hooksInstalled=false 或 interactionsObserved=0 时该轮采集无效，'
      + '相关维度必须填 notRun（未证明执行=未执行），不得凭空填 pass。未触发交互则相应维度填 notRun。',
    summary: {
      total: findings.length,
      byDimension: findings.reduce((acc, f) => { acc[f.dimension] = (acc[f.dimension] || 0) + 1; return acc; }, {}),
      errorCount: obs.errors.length,
      requestCount: obs.requests.length,
      overlayOpen,
    },
  });
})()
