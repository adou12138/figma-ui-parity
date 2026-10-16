#!/usr/bin/env node
/**
 * 多页用户旅程驱动（维度 7.39）：跨页流程走查
 *
 * 为什么需要：figma-ui-parity 一直是**逐页面**走查，跨页流程（导航 → 操作 → 回读）
 * 是真 bug 的高发区却没人覆盖——404/500 落地页、点击链接没反应、返回后白屏、
 * 中途被弹登录页（会话丢失），这些只有把页面串起来走才会暴露。
 *
 * 设计纪律（sound 边界）：
 *   1. **只走真实存在的链接**：候选链接从当页 DOM 实时提取，不猜业务路径；
 *   2. **只做 GET 导航**：点击 a[href]，不含危险词（删除/退出/注销/解绑…），
 *      不追新标签页与下载（记录但不跟随）；
 *   3. **有界**：--max-hops 控制每条旅程深度、--max-links-per-page 控制每页展开、
 *      --max-visits 控制总访问数，防链接图爆炸；
 *   4. **只硬判确定缺陷**：文档响应 4xx/5xx、落地页空白、返回后白屏 → confirmed P1；
 *      链接点击无反应 / 中途跳登录 → pending（可能是 SPA 路由需更多等待，或设计使然）；
 *   5. 运行期观测（7.35–7.38）经 addInitScript 在每个文档自动装钩，每步采集——
 *      旅程中炸的 JS 异常与失败请求归它们自己的维度，不混入 7.39。
 *
 * 安全：全程 GET 导航 + 同源（默认），不提交任何表单；staticOnly 策略短路不启动浏览器。
 *
 * 用法：
 *   node run_journeys.cjs --url "https://起始页" [--out "./parity-test/journeys"]
 *     [--profile 资料目录] [--safety-policy safe] [--max-hops 2] [--max-visits 30]
 *     [--max-links-per-page 12] [--allow-cross-origin] [--headed] [--chrome 路径]
 *
 * 产物：
 *   <out>/journeys.json          —— 旅程步骤、状态与 findings 汇总
 *   <out>/journey_findings.json  —— findings 平面清单（normalize_evidence 可直接消费）
 */
const fs = require('fs');
const path = require('path');
const { stabilize, resolveChrome } = require('../stabilize.js');

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : def;
}
const URL_ = arg('url');
const OUT = arg('out', path.join(process.cwd(), 'journeys'));
const PROFILE = arg('profile', null);
const CHROME = arg('chrome', null);
const HEADED = process.argv.includes('--headed');
const SAFETY_POLICY = arg('safety-policy', 'safe');
const MAX_HOPS = Math.max(1, parseInt(arg('max-hops', '2'), 10));
const MAX_VISITS = Math.max(1, parseInt(arg('max-visits', '30'), 10));
const MAX_LINKS = Math.max(1, parseInt(arg('max-links-per-page', '12'), 10));
const ALLOW_CROSS = process.argv.includes('--allow-cross-origin');

const OBS_SRC = fs.readFileSync(path.join(__dirname, '..', 'runtime_observability.js'), 'utf8');

if (!URL_ && require.main === module) { console.error('ERROR: --url is required'); process.exit(1); }

/** 同步解析 Playwright（不用 stabilize 的 async 版本，原因同 run_state_scenarios.cjs） */
function resolvePlaywright() {
  const candidates = ['playwright-core', 'playwright',
    path.join(process.cwd(), 'node_modules', 'playwright-core'),
    path.join(process.cwd(), 'node_modules', 'playwright')];
  if (process.env.PLAYWRIGHT_CORE_PATH) candidates.push(process.env.PLAYWRIGHT_CORE_PATH);
  for (const c of candidates) { try { return require(c); } catch (e) { /* next */ } }
  return null;
}
function loadAuth() {
  try { return require('./auth.cjs'); } catch (e) { return null; }
}

/* ================= 纯函数（node 可测） ================= */

const SKIP_SCHEMES = ['javascript:', 'mailto:', 'tel:', 'data:', 'blob:', 'about:'];
// 风险词表单源在 risk_words.cjs（与 discover_scenarios.py 对拍，见 test_risk_words_parity.py）
const { DANGER_WORDS } = require('./risk_words.cjs');
const DOWNLOAD_EXT = ['.pdf', '.zip', '.rar', '.7z', '.tar', '.gz', '.xlsx', '.xls', '.docx', '.doc', '.csv', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.mp4'];

/** 解析为 URL 对象；无法解析（javascript: 等）返回 null */
function parseUrl(href, baseUrl) {
  const h = String(href || '').trim();
  if (!h) return null;
  const lower = h.toLowerCase();
  for (const s of SKIP_SCHEMES) { if (lower.startsWith(s)) return null; }
  try { return new URL(h, baseUrl); } catch (e) { return null; }
}

/** 解析为绝对 URL 字符串（对外契约：字符串，不是 URL 对象） */
function resolveUrl(href, baseUrl) {
  const u = parseUrl(href, baseUrl);
  return u ? u.href : null;
}

/**
 * 候选链接判定。返回 { ok, url, reason }：
 *   ok=false 时 reason 说明跳过原因（供报告留痕，不静默丢）。
 */
function isCandidateLink(href, baseUrl, opts) {
  opts = opts || {};
  const u = parseUrl(href, baseUrl);
  if (!u) return { ok: false, reason: '不可解析或非 http(s) 协议' };
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return { ok: false, reason: '非 http(s) 协议' };
  if (u.origin === 'null') return { ok: false, reason: 'file:// 等无源地址' };
  if (!opts.allowCrossOrigin) {
    let base;
    try { base = new URL(baseUrl); } catch (e) { base = null; }
    if (base && base.origin !== u.origin) return { ok: false, reason: '跨源链接（默认不走）' };
  }
  const lower = u.href.toLowerCase();
  for (const w of DANGER_WORDS) {
    if (lower.indexOf(w) !== -1) return { ok: false, reason: '含危险词：' + w };
  }
  for (const ext of DOWNLOAD_EXT) {
    if (lower.split('?')[0].endsWith(ext)) return { ok: false, reason: '下载类资源（不跟随）' };
  }
  // 纯锚点（同页跳转）不构成跨页旅程
  try {
    const base = new URL(baseUrl);
    if (u.origin === base.origin && u.pathname === base.pathname && u.search === base.search && u.hash) {
      return { ok: false, reason: '同页锚点' };
    }
  } catch (e) { /* base 不可解析时放行，由导航结果说话 */ }
  return { ok: true, url: u.href, reason: null };
}

/**
 * 从链接清单规划有界访问序列：去重、按序、受 maxLinks 约束。
 * 输入兼容两种形状：isCandidateLink 的判定结果（带 ok）与 extractLinks 的产出（只有 url，
 * 无 ok）——只要求 url 存在，显式 ok===false 才跳过。字段契约以消费方为准，别再各写各的。
 */
function planVisits(links, maxLinks) {
  const out = [];
  const seen = {};
  for (const l of (links || [])) {
    if (!l || !l.url) continue;
    if (l.ok === false) continue;
    if (seen[l.url]) continue;
    seen[l.url] = 1;
    out.push(l);
    if (out.length >= maxLinks) break;
  }
  return out;
}

/** 跳过链接汇总：按 reason 计数 + Top N 明细。**只留痕不阻断**——目的是让报告
 *  体现「哪些链接因何未访问」，否则 7.39 的覆盖质量（上限砍掉了什么）无从判断。 */
function summarizeSkipped(skipped) {
  const list = skipped || [];
  const byReason = {};
  list.forEach(s => { byReason[s.reason] = (byReason[s.reason] || 0) + 1; });
  return {
    total: list.length,
    byReason,
    sample: list.slice(0, 10).map(s => ({ href: s.href, reason: s.reason })),
  };
}

/** 7.39 步骤判定：只硬判确定缺陷，其余 pending（见文件头纪律 4） */
function stepFinding(step) {
  const out = [];
  const push = (symptom, expected, actual, sev, conf, status, property, raw) => {
    out.push({
      dimension: '7.39', symptom, expected, actual,
      severityHint: sev, severity: sev, confidence: conf, status,
      element: null, evidence: [{ type: 'journey-step', result: status === 'pending' ? 'info' : 'mismatch' }],
      sources: ['journeys'], property: property || null, raw: raw || null,
    });
  };
  if (step.docStatus && step.docStatus >= 400) {
    push('点击链接后落地页返回 ' + step.docStatus + '，用户看到错误页',
      '站内链接应导航到正常页面（2xx）',
      '文档响应状态 ' + step.docStatus + '，URL=' + step.url,
      'P1', 0.85, 'confirmed', 'journey-doc-error', { docStatus: step.docStatus, url: step.url });
  }
  if (step.landedChars < 20 && step.docStatus !== 404) {
    push('点击链接后落地页近乎空白，用户看不到任何内容',
      '落地页应渲染出内容', '落地后可见文本仅 ' + step.landedChars + ' 字符，URL=' + step.url,
      'P1', 0.75, 'confirmed', 'journey-landing-blank', { landedChars: step.landedChars, url: step.url });
  }
  if (step.noop) {
    push('点击链接后页面无任何变化（未导航、无内容更新），链接可能失效',
      '站内链接点击后应产生可观察的结果',
      'URL 仍为 ' + step.fromUrl + '，DOM 无变化',
      'P2', 0.5, 'pending', 'journey-link-noop', { href: step.href, fromUrl: step.fromUrl });
  }
  if (step.loginRedirect) {
    push('旅程中途被重定向到登录页，登录态可能意外丢失',
      '已登录状态下站内导航不应被弹回登录页',
      '从 ' + step.fromUrl + ' 点击后落到 ' + step.url,
      'P1', 0.5, 'pending', 'journey-login-redirect', { fromUrl: step.fromUrl, url: step.url });
  }
  if (step.backBroken) {
    push('从子页面返回上级页面失败或返回后空白，旅程中断',
      '浏览器返回应恢复到进入时的页面',
      'goBack 后 URL=' + step.backUrl + '，可见文本 ' + step.backChars + ' 字符',
      'P1', 0.8, 'confirmed', 'journey-back-broken', { backUrl: step.backUrl, backChars: step.backChars });
  }
  return out;
}

/* ================= 驱动 ================= */

const WS = new RegExp('[' + String.fromCharCode(32, 9, 10, 13, 12, 11, 0xA0, 0x3000) + ']+', 'g');

async function collectRuntime(page) {
  try {
    const raw = await page.evaluate(OBS_SRC);
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return (parsed && parsed.findings) || [];
  } catch (e) { return []; }
}

async function pageState(page) {
  return page.evaluate(() => {
    const WS = new RegExp('[' + String.fromCharCode(32, 9, 10, 13, 12, 11, 0xA0, 0x3000) + ']+', 'g');
    return {
      url: location.href,
      title: document.title || '',
      chars: ((document.body && document.body.innerText) || '').replace(WS, '').length,
      hash: location.hash,
    };
  });
}

/** 提取当前页候选链接（实时 DOM）。skippedOut 可选：收集被剔除的链接及原因（留痕用）。 */
async function extractLinks(page, baseUrl, skippedOut) {
  const raw = await page.evaluate(() => {
    const out = [];
    Array.prototype.slice.call(document.querySelectorAll('a[href]')).slice(0, 300).forEach((el) => {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      const vis = cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0;
      out.push({ href: el.getAttribute('href') || '', visible: vis,
                 text: (el.innerText || '').trim().slice(0, 30),
                 isDownload: el.hasAttribute('download'),
                 target: el.getAttribute('target') || '' });
    });
    return out;
  });
  const links = [];
  const seen = {};
  for (const l of raw) {
    const judge = isCandidateLink(l.href, baseUrl, { allowCrossOrigin: ALLOW_CROSS });
    if (!judge.ok) {
      if (skippedOut) skippedOut.push({ href: l.href, reason: judge.reason || 'not_candidate' });
      continue;
    }
    if (l.isDownload) {
      if (skippedOut) skippedOut.push({ href: l.href, reason: 'download' });
      continue;
    }
    if (l.target === '_blank') {
      if (skippedOut) skippedOut.push({ href: l.href, reason: 'new_tab' });
      continue;
    }
    if (seen[judge.url]) continue;
    seen[judge.url] = 1;
    links.push({ url: judge.url, href: l.href, visible: l.visible, text: l.text, target: l.target });
  }
  return links;
}

/**
 * 是否像"被弹回登录页"。**必须按路径段精确匹配**：原先用子串找 '/auth'，会把
 * '/author/list'、'/authors' 这类正常业务页判成登录页 → 假阳性（用户在自己的
 * 作者管理页被告知"登录态丢失"）。OAuth 回调（/oauth/callback）也不算登录页。
 */
function looksLikeLogin(url) {
  const raw = String(url || '').trim();
  if (!raw) return false;
  let parsed = null;
  try { parsed = new URL(raw); } catch (e) {
    // 相对/非绝对地址退回按 / 切段判断
    parsed = { pathname: raw.split('?')[0].split('#')[0], hostname: '' };
  }
  const host = String(parsed.hostname || '').toLowerCase();
  if (host.indexOf('passport') !== -1 || host.indexOf('sso') !== -1) return true;
  const segments = String(parsed.pathname || '').toLowerCase().split('/').filter(Boolean);
  const LOGIN_SEGMENTS = ['login', 'signin', 'sign-in', 'logon', 'auth', 'authenticate', 'authorize'];
  for (const seg of segments) {
    if (LOGIN_SEGMENTS.indexOf(seg) !== -1) return true;
  }
  // 兼容 '?redirect=login' 这类查询参数提示（段里没有 login 但参数里有）
  const q = raw.indexOf('?') !== -1 ? raw.slice(raw.indexOf('?') + 1).toLowerCase() : '';
  return q.indexOf('redirect=login') !== -1 || q.indexOf('returnurl=login') !== -1;
}

async function clickLink(page, link) {
  /** 点击链接并等待导航/变化。返回步骤事实（不判缺陷）。 */
  const before = await pageState(page);
  const esc = link.href.replace(/"/g, String.fromCharCode(92) + '"');
  const loc = page.locator('a[href="' + esc + '"]').first();
  // 文档响应在**点击前**就监听：waitForResponse 若在 click 之后注册，导航快的页面
  // 响应已先到，会永远等不到（既漏状态码又白等一个超时）。
  let docStatus = null;
  const onResp = (r) => {
    try { if (r.request().resourceType() === 'document') docStatus = r.status(); } catch (e) { /* ignore */ }
  };
  page.on('response', onResp);
  // 点击前先在候选里挑**可见**的那一个：移动端/桌面端常把同一链接在 DOM 里放两份，
  // .first() 可能命中隐藏那份 → 点击超时 → 误判"链接无反应"。
  let clicked = false;
  try {
    const all = page.locator('a[href="' + esc + '"]');
    const n = await all.count();
    for (let i = 0; i < n && !clicked; i += 1) {
      const cand = all.nth(i);
      if (!(await cand.isVisible().catch(() => false))) continue;
      await cand.click({ timeout: 5000 });
      clicked = true;
    }
  } catch (e) { clicked = false; }
  if (!clicked) {
    page.off('response', onResp);
    return { ...before, href: link.href, fromUrl: before.url, clicked: false, noop: true,
             landedChars: before.chars, url: before.url };
  }
  await page.waitForTimeout(1200); // 等导航落定 / SPA 渲染
  page.off('response', onResp);
  const after = await pageState(page);
  const noop = after.url === before.url && after.hash === before.hash && after.chars === before.chars;
  return {
    href: link.href, fromUrl: before.url, clicked: true,
    url: after.url, landedChars: after.chars, docStatus, noop,
    loginRedirect: looksLikeLogin(after.url) && !looksLikeLogin(before.url),
    newTab: link.target === '_blank',
  };
}

async function main() {
  if (!URL_) { console.error('ERROR: --url is required'); process.exit(1); }
  fs.mkdirSync(OUT, { recursive: true });

  if (SAFETY_POLICY === 'staticOnly') {
    const payload = {
      url: URL_, safetyPolicy: SAFETY_POLICY, startedAt: new Date().toISOString(),
      journeys: [], summary: { status: 'notRun', reason: 'staticOnly 策略：不做任何页面交互（含链接点击与导航）' },
    };
    fs.writeFileSync(path.join(OUT, 'journeys.json'), JSON.stringify(payload, null, 2), 'utf8');
    fs.writeFileSync(path.join(OUT, 'journey_findings.json'),
      JSON.stringify({ url: URL_, findings: [] }, null, 2), 'utf8');
    console.log(JSON.stringify({ out: path.join(OUT, 'journeys.json'), status: 'notRun', reason: payload.summary.reason }, null, 2));
    return;
  }

  const pw = resolvePlaywright();
  if (!pw) { console.error('ERROR: playwright-core not found. npm i playwright-core'); process.exit(1); }
  const chrome = CHROME && fs.existsSync(CHROME) ? CHROME : resolveChrome();
  if (!chrome) { console.error('ERROR: chrome.exe not found under ms-playwright'); process.exit(1); }
  const auth = loadAuth();

  let context;
  if (PROFILE) context = await pw.chromium.launchPersistentContext(PROFILE, { headless: !HEADED, executablePath: chrome, args: ['--no-sandbox'], viewport: { width: 1440, height: 900 } });
  else { const b = await pw.chromium.launch({ headless: !HEADED, executablePath: chrome, args: ['--no-sandbox'] }); context = await b.newContext({ viewport: { width: 1440, height: 900 } }); }
  try {
    if (auth && auth.restoreAuth) await auth.restoreAuth(context).catch(() => {});
    const page = context.pages()[0] || await context.newPage();
    // 运行期钩子随每个文档自动安装（旅程每步都能采到 7.35–7.38）
    await page.addInitScript(OBS_SRC);
    // 【F9 反假通过】起始页 goto 失败（DNS/超时/拒绝连接）时不得继续：在 about:blank
    // 上跑完旅程会产出「0 缺陷 + 各维度 pass」的假绿报告。起始页不可达 = 7.25/7.26/7.39
    // 全部无法验证，必须以非零码退出并把原因写明。
    try {
      await page.goto(URL_, { waitUntil: 'domcontentloaded', timeout: 45000 });
    } catch (e) {
      console.error('[fatal] 起始页不可达，旅程无法执行（不得在空白页产出假通过报告）:',
        String(e).slice(0, 200));
      const out = path.join(OUT, 'journey_findings.json');
      fs.mkdirSync(OUT, { recursive: true });
      fs.writeFileSync(out, JSON.stringify({
        error: 'start-url-unreachable',
        url: URL_,
        reason: String(e).slice(0, 300),
        findings: [],
        dimensionEvidence: { '7.25': { status: 'notRun', reason: '起始页不可达' },
                             '7.26': { status: 'notRun', reason: '起始页不可达' },
                             '7.39': { status: 'notRun', reason: '起始页不可达' } },
      }, null, 2));
      process.exit(2);
    }
    await stabilize(page, {});

    const journeys = [];
    // 被剔除的链接（非候选 / 下载 / 新标签页）汇总到这里：跳过原因必须落产物，
    // 否则报告体现不出「哪些链接因何未访问」，7.39 的覆盖质量无法判断。
    const skippedLinks = [];
    const allFindings = [];
    let visits = 0;
    // BFS：queue 元素 { url, hops, path }
    const queue = [{ url: page.url(), hops: 0, path: [] }];
    const visited = {};

    while (queue.length && visits < MAX_VISITS) {
      const node = queue.shift();
      if (visited[node.url] || node.hops > MAX_HOPS) continue;
      visited[node.url] = 1;
      visits += 1;

      // 关键：队列里的子节点必须**真的导航过去**再展开它的链接。
      // 少了这一步，每个队列节点都会在当前页（回退后的起始页）重复走一遍，
      // 同一缺陷被重复报 N 次——既失真又浪费预算。
      const curUrl = page.url();
      if (curUrl !== node.url) {
        await page.goto(node.url, { waitUntil: 'domcontentloaded', timeout: 45000 })
          .catch(e => console.warn('[warn] goto journey node:', String(e).slice(0, 100)));
        await stabilize(page, {});
      }

      const startState = await pageState(page);
      const runtimeFindings = await collectRuntime(page);
      // 基准用**页面实际 URL**而不是 node.url：发生重定向（/page → /page?tab=2）时，
      // 按 node.url 解析相对链接会得到错误的绝对地址。
      const links = node.hops < MAX_HOPS ? await extractLinks(page, startState.url, skippedLinks) : [];
      const plan = planVisits(links, MAX_LINKS);
      const steps = [];

      for (const link of plan) {
        if (visits >= MAX_VISITS) break;
        const step = await clickLink(page, link);
        const stepFindings = stepFinding(step);
        // 落地页的运行期观测（7.35–7.38 归其自身维度）
        const landedRuntime = step.noop ? [] : await collectRuntime(page);
        steps.push({
          href: link.href, text: link.text, fromUrl: step.fromUrl, url: step.url,
          docStatus: step.docStatus, landedChars: step.landedChars,
          status: stepFindings.some(f => f.status === 'confirmed') ? 'fail'
            : (stepFindings.length || landedRuntime.length ? 'pending' : 'pass'),
          findings: stepFindings, runtimeFindings: landedRuntime,
        });
        stepFindings.forEach(f => allFindings.push(f));
        landedRuntime.forEach(f => allFindings.push(f));
        // 成功落地且未访问过的页面入队继续展开（多跳旅程）。
        // 不入队：空操作（没导航）、仍是当前页、已访问过。
        if (step.clicked && !step.noop && step.url && !visited[step.url] && step.url !== node.url) {
          queue.push({ url: step.url, hops: node.hops + 1, path: node.path.concat(step.url) });
        }
        // 返回上级页面继续（同时实测 7.32 相关的返回行为）
        const back = await page.goBack({ waitUntil: 'domcontentloaded' }).catch(() => null);
        if (back === null) {
          const f = stepFinding({ backBroken: true, backUrl: await pageState(page).then(s => s.url), backChars: 0 });
          // goBack 返回 null 只说明无历史，不一定坏；仅在当前页空白时才判缺陷
          const st = await pageState(page);
          if (st.chars < 20) {
            steps[steps.length - 1].findings.push(...f);
            allFindings.push(...f);
          }
        } else {
          await page.waitForTimeout(500);
          const st = await pageState(page);
          if (st.chars < 20) {
            const f = stepFinding({ backBroken: true, backUrl: st.url, backChars: st.chars });
            steps[steps.length - 1].findings.push(...f);
            allFindings.push(...f);
          }
        }
        if (queue.length && visits >= MAX_VISITS) break;
      }

      journeys.push({
        id: 'J-' + String(journeys.length + 1).padStart(3, '0'),
        startUrl: startState.url, hops: node.hops,
        runtimeFindings,
        steps,
        status: steps.some(s => s.status === 'fail') ? 'fail'
          : (steps.some(s => s.status === 'pending') ? 'pending' : (steps.length ? 'pass' : 'notRun')),
      });
    }

    // 同一缺陷经不同路径到达只报一次（多跳旅程会把同一个坏页面从不同入口走到）。
    // 按「维度 + 属性 + 页面」去重，次数记在 occurrences 上——既不重复提单，也不丢"几条路径都能踩到"的信息。
    const deduped = [];
    const byKey = {};
    for (const f of allFindings) {
      const key = f.dimension + '|' + (f.property || '') + '|' + ((f.raw && (f.raw.url || f.raw.backUrl)) || '');
      if (byKey[key]) { byKey[key].occurrences = (byKey[key].occurrences || 1) + 1; continue; }
      f.occurrences = 1;
      byKey[key] = f;
      deduped.push(f);
    }

    const byStatus = {};
    deduped.forEach(f => { byStatus[f.dimension] = (byStatus[f.dimension] || 0) + 1; });
    const payload = {
      url: URL_, safetyPolicy: SAFETY_POLICY, startedAt: new Date().toISOString(),
      bounds: { maxHops: MAX_HOPS, maxVisits: MAX_VISITS, maxLinksPerPage: MAX_LINKS },
      journeys,
      summary: { journeys: journeys.length, visits, findingsTotal: deduped.length,
                 findingsRaw: allFindings.length, byDimension: byStatus,
                 skippedLinks: summarizeSkipped(skippedLinks) },
    };
    fs.writeFileSync(path.join(OUT, 'journeys.json'), JSON.stringify(payload, null, 2), 'utf8');
    fs.writeFileSync(path.join(OUT, 'journey_findings.json'),
      JSON.stringify({ url: URL_, findings: deduped }, null, 2), 'utf8');
    console.log(JSON.stringify({ out: path.join(OUT, 'journeys.json'), ...payload.summary }, null, 2));
  } finally {
    await context.close().catch(() => {});
  }
}

if (require.main === module) {
  main().catch(e => { console.error('FATAL', String(e)); process.exit(1); });
}

module.exports = { parseUrl, resolveUrl, isCandidateLink, planVisits, stepFinding, looksLikeLogin };
