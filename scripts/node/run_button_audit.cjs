#!/usr/bin/env node
/**
 * 7.22 / 7.23 按钮可用性与点击生效验证（+ 设计稿按钮双向配对）
 *
 * 设计原则：
 *   1. 静态盘点（button_audit.js）零风险，永远先跑；
 *   2. 点击按本次安全策略执行：safe 真点；mockWrites 下 caution 拦截后点；all 且明确确认测试环境时 caution/danger 允许真实执行；其他模式下 danger 只静态检查；
 *   3. 点击后必须还原（有副作用才 reload），否则前一个按钮的弹框会遮挡后续按钮，制造假阳性；
 *   4. dialog / 新标签页 / 下载三类必须预先接管，否则脚本挂起并被误判成"点击无响应"。
 *
 * 用法：
 *   node run_button_audit.cjs --url "https://目标页" [--profile "资料目录"] [--out "./parity-test/button-audit"]
 *     [--click] [--max 40] [--include-danger] [--no-restore] [--headed] [--wait-login]
 *     [--design-buttons "./parity-test/figma-xxx/design_buttons.json"]
 */
const fs = require('fs');
const path = require('path');
const { stabilize } = require('../stabilize.js');

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : def;
}
const URL_ = arg('url');
const PROFILE = arg('profile', null);
const OUT = arg('out', path.join(process.cwd(), 'button-audit'));
const CLICK = process.argv.includes('--click');
const MAX_CLICK = parseInt(arg('max', '40'), 10);
const INCLUDE_DANGER = process.argv.includes('--include-danger');
const INCLUDE_GENERIC = process.argv.includes('--include-generic');   // 连 [onclick] 泛匹配到的疑似可点元素一起点（默认不点）
const NO_RESTORE = process.argv.includes('--no-restore');
const HEADED = process.argv.includes('--headed');
const WAIT_LOGIN = process.argv.includes('--wait-login');
const SAFETY_POLICY = arg('safety-policy', 'safe'); // all | safe | mockWrites | staticOnly
const TEST_ENV_CONFIRMED = process.argv.includes('--test-environment-confirmed');
const WRITE_POLICY = arg('write-policy', SAFETY_POLICY === 'safe' ? 'abort' : SAFETY_POLICY === 'all' ? 'none' : 'mock');   // mock（mock 成功响应）| abort（直接中断）| none（all 模式，真实发送）
// 【F46】默认写策略随安全策略推导，与 start_test.py 的 write_interception 映射
// （safe→abort、mockWrites→mock、all→none）对齐；显式 --write-policy 仍优先。
const CHROME = arg('chrome', null);
const DESIGN_BUTTONS = arg('design-buttons', null);

if (!URL_ && require.main === module) { console.error('ERROR: --url is required'); process.exit(1); }

function resolvePlaywright() {
  const candidates = [
    'playwright-core',
    path.join(process.cwd(), 'node_modules', 'playwright-core'),
    ...(process.env.PLAYWRIGHT_CORE_PATH ? [process.env.PLAYWRIGHT_CORE_PATH] : []),
  ];
  for (const c of candidates) { try { return require(c); } catch (e) { /* next */ } }
  return null;
}
// 【F42b】复用跨平台解析（Win/Mac/Linux + 系统浏览器兜底），不再自带 Windows-only 版本。
const { resolveChrome: resolveChromeShared } = require('../stabilize.js');
function resolveChrome() {
  if (CHROME && fs.existsSync(CHROME)) return CHROME;
  return resolveChromeShared();
}
let pw = null;
let chromePath = null;
let auth = null;
if (require.main === module) {
  pw = resolvePlaywright();
  if (!pw) { console.error('ERROR: playwright-core not found. npm i playwright-core'); process.exit(1); }
  chromePath = resolveChrome();
  if (!chromePath) { console.error('ERROR: 找不到可用 Chromium/Chrome/Edge；设置 PLAYWRIGHT_CHROME_PATH 或安装 playwright 浏览器后重试'); process.exit(1); }
  try { auth = require('./auth.cjs'); } catch (e) { /* optional */ }
}

const AUDIT_JS = path.join(__dirname, '..', 'button_audit.js');
const PAGE_JS = {
  toast: `(() => {
    const re = /toast|tip|message|notice/i;
    return Array.prototype.slice.call(document.querySelectorAll('div,span,p'))
      .filter(el => { const cs = getComputedStyle(el), r = el.getBoundingClientRect();
        const t = (el.textContent || '').trim();
        return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.1
          && re.test(String(el.className || '')) && t.length > 0 && t.length < 80; })
      .map(el => (el.textContent || '').trim().slice(0, 60)).slice(0, 5);
  })()`,
  modal: `(() => {
    const re = /modal|dialog|popup|overlay/i;
    return Array.prototype.slice.call(document.querySelectorAll('div,section'))
      .filter(el => { const cs = getComputedStyle(el), r = el.getBoundingClientRect();
        return r.width > 120 && r.height > 80 && cs.display !== 'none' && cs.visibility !== 'hidden' && parseFloat(cs.opacity) > 0.1
          && re.test(String(el.className || '')); })
      .map(el => String(el.className || '').split(/\\s+/)[0]).slice(0, 4);
  })()`,
  dom: `(() => ({ htmlLen: document.body ? document.body.innerHTML.length : 0, nodes: document.querySelectorAll('*').length }))()`,
  // 可见元素数：预渲染弹窗靠 CSS 显隐切换时，innerHTML 长度与节点数都不变，
  // 只有「可见元素数量」会变——这是识别这类弹窗最可靠的通用信号。
  visible: `(() => {
    const all = document.querySelectorAll('*');
    let n = 0;
    for (let i = 0; i < all.length; i++) {
      const cs = getComputedStyle(all[i]);
      if (cs.display === 'none' || cs.visibility === 'hidden' || cs.opacity === '0') continue;
      n++;
    }
    return n;
  })()`,
  // 浮层签名：class/id 关键词 + 定位 + z-index + 尺寸，用于判断「点击后是否新增了浮层」
  layer: `(() => {
    const re = /modal|dialog|popup|overlay|layer|mask|drawer|sheet|tips?|alert|cbox|lightbox|wjxui-|panel/i;
    const out = [], vw = innerWidth, vh = innerHeight;
    document.querySelectorAll('div,section,aside,form,ul').forEach(el => {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.1) return;
      const r = el.getBoundingClientRect();
      if (r.width < vw * 0.2 || r.height < vh * 0.12) return;
      const z = parseInt(cs.zIndex, 10) || 0;
      const named = re.test(String(el.className || '') + ' ' + String(el.id || ''));
      if (!((cs.position === 'fixed' || cs.position === 'absolute') && z >= 100) && !named) return;
      out.push((el.id ? '#' + el.id : '.' + String(el.className || '').trim().split(/\\s+/)[0]) + '|z' + z + '|' + Math.round(r.width) + 'x' + Math.round(r.height));
    });
    return out.slice(0, 8);
  })()`,
  // 取可作为盘点作用域的浮层（按 z-index 降序、同层取更小面积者），返回唯一选择器
  overlays: `(() => {
    const out = [], vw = innerWidth, vh = innerHeight;
    document.querySelectorAll('div,section,aside,form').forEach(el => {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.2) return;
      const r = el.getBoundingClientRect();
      if (r.width < vw * 0.2 || r.height < vh * 0.12) return;
      const z = parseInt(cs.zIndex, 10) || 0;
      if (!((cs.position === 'fixed' || cs.position === 'absolute') && z >= 100)) return;
      let sel = el.id ? '#' + el.id : (el.className ? el.tagName.toLowerCase() + '.' + String(el.className).trim().split(/\\s+/).slice(0, 2).join('.') : null);
      if (!sel) return;
      try { if (document.querySelectorAll(sel).length !== 1) sel = null; } catch (e) { sel = null; }
      if (!sel) return;
      out.push({ sel, z, area: r.width * r.height, w: Math.round(r.width), h: Math.round(r.height) });
    });
    out.sort((a, b) => (b.z - a.z) || (a.area - b.area));
    return out.slice(0, 3);
  })()`,
};

async function isLoginPage(page) {
  // 【F47】登录页判定统一到 auth.cjs（多信号，含「系统提示」标题信号），
  // 消除此前 run_button_audit 与 auth.cjs 两份分叉信号集导致的识别漂移。
  if (auth && typeof auth.isLoginPage === 'function') return auth.isLoginPage(page);
  return await page.evaluate(() => {
    const body = document.body ? document.body.innerText : '';
    return /login|signin/i.test(location.href || '') || /未登录|您还未登录|请先登录|请登录/.test(body) || /立即注册|忘记用户名|验证码登录|账号登录/.test(body);
  }).catch(() => true);
}

// ---- 设计稿 ↔ 页面配对（7.23）----
function normKey(s) { return String(s == null ? '' : s).replace(/[\u200b-\u200f\ufeff]/g, '').replace(/\s+/g, '').trim().toLowerCase(); }
function pairButtonsWithEvidence(design, pageBtns, fullTextElements) {
  const used = new Set(), paired = [], missing = [], unmatchedWeak = [];
  const textEvidence = Array.isArray(fullTextElements) ? fullTextElements : [];
  // 【F29 反漏判】旧 matches 是双向子串：设计按钮「确定」只要在帮助文字/表头出现过
  // 就判 paired(matchedBy:fullText)，真缺失被吞。收紧规则：
  //   - 等值命中仍算证据；子串只认「设计文本较长（>=3 字符）且页面文本以其为完整
  //     class/词段」——即命中段边界是标点/空白/标签边界，不认任意位置子串；
  //   - 且命中元素必须可交互（interactive=true）——纯文字节点不算按钮存在的证据。
  const WORD_BOUNDARY = /(^|[\s·、，,。;；:：/|()（）\[\]\-_])([^[\s·、，,。;；:：/|()（）\[\]\-_]+)$/; 
  const matches = (v, k) => {
    const n = normKey(v);
    if (!n || !k) return false;
    if (n === k) return true;
    // 单向且带边界：页面文本必须包含完整的设计文本段（不认反向子串——
    // 页面长文本包含短设计词是文案巧合，不是按钮实现）
    if (k.length < 3) return false;                     // 短设计名（btn/a/icon）禁子串
    let idx = n.indexOf(k);
    while (idx >= 0) {
      const before = idx === 0 ? '' : n[idx - 1];
      const after = idx + k.length >= n.length ? '' : n[idx + k.length];
      const isBoundary = (ch) => ch === '' || /[\s·、，,。;；:：/|()（）\[\]\-_]/.test(ch);
      if (isBoundary(before) && isBoundary(after)) return true;
      idx = n.indexOf(k, idx + 1);
    }
    return false;
  };
  for (const d of design) {
    const k = normKey(d.text) || normKey(d.name);
    let hit = null;
    if (k) {
      hit = pageBtns.find(b => !used.has(b.sel) && [b.normText, b.text, b.title, b.ariaLabel].some(v => normKey(v) === k));
      if (!hit) hit = pageBtns.find(b => !used.has(b.sel) && [b.normText, b.text, b.title, b.ariaLabel].some(v => matches(v, k)));
    }
    if (hit) {
      used.add(hit.sel);
      paired.push({ design: d, page: { sel: hit.sel, text: hit.text, risk: hit.risk, clickable: hit.clickable }, matchedBy: 'buttonInventory', nonStandardEntry: false });
      continue;
    }
    // fullText 通道：命中必须可交互；并降级为 pending 语义（matchedBy 保留但
    // nonStandardEntry=true 已有——消费方对 fullText 配对本来就要求人工确认）。
    const textHit = k && textEvidence.find(e =>
      matches(e.text || e.characters || e.value, k) && (e.interactive === true || e.clickable === true
        || /^(a|button)$/i.test(String(e.tag || ''))));
    if (textHit) {
      paired.push({ design: d, page: { sel: textHit.selector || textHit.sel || null, text: textHit.text || textHit.characters || textHit.value, tag: textHit.tag || null }, matchedBy: 'fullText', nonStandardEntry: true });
    } else if (d.confidence === 'weak') {
      unmatchedWeak.push({ ...d, matchedBy: 'none' });
    } else {
      missing.push({ ...d, matchedBy: 'none' });
    }
  }
  // 【F44b】icon-only（无文本）按钮不再被排除：`b.normText || b.text` 把图标按钮
  // 全滤掉——设计稿若只有图标（常见：关闭 ×、更多 …、设置齿轮），多余的图标按钮
  // 是 7.23「页面有设计无」的真命中，漏报即漏判。图标按钮单独入 extraIconOnly，
  // 消费方按文本匹配规则人工核对（图标无语义文本，机械配对不可靠）。
  const extra = pageBtns.filter(b => !used.has(b.sel) && (b.normText || b.text));
  const extraIconOnly = pageBtns.filter(b => !used.has(b.sel) && !(b.normText || b.text));
  return { paired, missingInPage: missing, designUnmatchedWeak: unmatchedWeak,
           extraInPage: extra, extraInPageIconOnly: extraIconOnly };
}

if (require.main !== module) module.exports = { normKey, pairButtonsWithEvidence };

if (require.main === module) (async () => {
  fs.mkdirSync(OUT, { recursive: true });
  if (!fs.existsSync(AUDIT_JS)) { console.error('ERROR: missing scripts/button_audit.js'); process.exit(1); }

  const launchOpts = { headless: !HEADED, executablePath: chromePath, args: ['--no-sandbox'] };
  // 【F45】视口参数化 + deviceScaleFactor：硬编码 1903x985 在与设计帧不一致的
  // 宽度下做 hitTest/遮挡判定会假失败/假通过；缺省 scale factor 会让 bbox 与
  // 设计坐标相差一个 DPR。--viewport WxH 与设计帧对齐（默认保持旧行为不破坏
  // 既有产物），--dsf 显式指定。
  const vpArg = arg('viewport', '');
  const dsf = parseFloat(arg('dsf', '1')) || 1;
  const vpMatch = /^(\d+)x(\d+)$/.exec(vpArg || '');
  const VIEWPORT = vpMatch
    ? { width: parseInt(vpMatch[1], 10), height: parseInt(vpMatch[2], 10) }
    : { width: 1903, height: 985 };
  let context, browser = null;
  if (PROFILE) context = await pw.chromium.launchPersistentContext(PROFILE, { ...launchOpts, viewport: VIEWPORT, deviceScaleFactor: dsf });
  else { browser = await pw.chromium.launch(launchOpts); context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: dsf }); }
  console.log('[i] viewport=' + VIEWPORT.width + 'x' + VIEWPORT.height + ' dsf=' + dsf
    + (vpMatch ? '' : '（默认值；与设计帧宽不一致时请加 --viewport WxH 对齐，F45）'));
  const page = context.pages()[0] || await context.newPage();
  if (auth) { try { console.log('[i] restoreAuth:', JSON.stringify(await auth.restoreAuth(context))); } catch (e) {} }
  if (HEADED) {
    await context.addInitScript(() => {
      const inject = () => {
        if (document.body && !document.getElementById('cdp-auto-banner')) {
          const b = document.createElement('div');
          b.id = 'cdp-auto-banner';
          b.textContent = '🤖 按钮盘点窗口：请在此窗口登录，登录后自动继续。请勿关闭。';
          b.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#0095FF;color:#fff;padding:14px;font-size:16px;font-weight:bold;text-align:center;';
          document.body.appendChild(b);
        }
      };
      inject(); document.addEventListener('DOMContentLoaded', inject);
    });
  }

  // ---- 观测通道：dialog / 新标签页 / 下载 / 请求 ----
  const obs = { dialogs: [], newPages: [], downloads: [], requests: [], intercepted: [] };
  // 【F6 上游留痕】本轮发生的降级事实。stabilize 的显式抛错（视口内图片未加载）
  // 若被静默吞掉，产物看不出截图是在破图占位状态下拍的——下游无从判断可比性。
  const degraded = [];
  page.on('dialog', d => { obs.dialogs.push({ type: d.type(), message: d.message().slice(0, 80) }); d.dismiss().catch(() => {}); });
  page.on('download', d => { obs.downloads.push(d.suggestedFilename()); d.cancel().catch(() => {}); });
  context.on('page', p => { if (p !== page) { obs.newPages.push(p.url()); p.close().catch(() => {}); } });

  // ---- 写请求拦截（caution 级按钮的安全网；safe 级也装，防止意外写）----
  if (!(SAFETY_POLICY === 'all' && TEST_ENV_CONFIRMED && WRITE_POLICY === 'none')) {
    await context.route('**/*', async route => {
      const req = route.request();
      const m = req.method().toUpperCase();
      if (m === 'GET' || m === 'HEAD' || m === 'OPTIONS') return route.continue();
      obs.intercepted.push({ method: m, url: req.url().slice(0, 160) });
      if (WRITE_POLICY === 'abort') return route.abort();
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ code: 0, data: null, msg: 'parity-probe-mocked' }) });
    }).catch(e => console.warn('[warn] route install failed:', String(e).slice(0, 120)));
  } else {
    console.log('[!] all 模式已确认测试环境：不拦截写请求，允许真实执行');
  }
  page.on('request', r => obs.requests.push({ method: r.method(), url: r.url().slice(0, 160) }));

  const load = async () => {
    await page.goto(URL_, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(e => console.warn('[warn] goto', String(e).slice(0, 100)));
    await page.waitForTimeout(3500);
    if (await isLoginPage(page)) {
      if (!HEADED && !WAIT_LOGIN) { console.error('[x] login required. 用 --headed 手动登录，或先跑 save_auth.cjs'); await context.close(); process.exit(2); }
      console.log('[i] waiting for manual login...');
      const deadline = Date.now() + 15 * 60 * 1000;
      while (Date.now() < deadline) { await page.waitForTimeout(5000); if (!(await isLoginPage(page))) break; }
      if (await isLoginPage(page)) { await context.close(); process.exit(2); }
      await load(); return;
    }
    // 【F6 上游留痕】stabilize.js 的懒加载重校验会**显式抛错**（视口内图片未加载），
    // 该异常以 `[stabilize]` 前缀区分自有异常。旧代码 `catch (e) {}` 把这个显式抛错
    // 完整丢弃：无 stderr、无降级标记——上游精心区分的异常语义在边界处被抹平，
    // 下游只看到「跑完了」，无法知道截图是在破图占位状态下拍的。现留痕 + 标降级。
    try {
      await stabilize(page, {});
    } catch (e) {
      const msg = String((e && e.message) || e).slice(0, 200);
      if (String(msg).indexOf('[stabilize]') !== -1) {
        console.warn('[warn] stabilize 显式抛错（视口内图片未加载），本轮截图降级：' + msg);
        degraded.push({ stage: 'stabilize', reason: 'explicit-throw', message: msg });
      } else {
        console.warn('[warn] stabilize 异常（继续执行）：' + msg);
        degraded.push({ stage: 'stabilize', reason: 'error', message: msg });
      }
    }
  };
  await load();
  if (auth) { try { const si = await auth.saveAuth(context, 'default'); console.log('[i] auth refreshed: ' + si.cookieCount + ' cookies'); } catch (e) {} }

  // ---- ① 静态盘点 ----
  const auditCode = fs.readFileSync(AUDIT_JS, 'utf8');
  let raw = await page.evaluate(auditCode);
  const audit = typeof raw === 'string' ? JSON.parse(raw) : raw;
  console.log('[i] 按钮总数 ' + audit.count + ' → 标准按钮 ' + audit.uniqueCount + ' 种 + 疑似可点元素 ' + audit.genericCount + ' 种；隐藏容器内 ' + audit.hiddenCount + ' 个（弹框未打开，不可观测，非缺陷）');
  console.log('[i] 风险分布 ' + JSON.stringify(audit.riskSummary) + '；可见但不可点击 ' + audit.notClickableCount);

  // ---- ② 点击验证（--click）----
  const results = [];
  if (CLICK) {
    const pool = INCLUDE_GENERIC ? audit.buttons.concat(audit.genericClickables || []) : audit.buttons;
    // 仅因「遮挡」被静态判不可点击的，仍要尝试点击一次实测确认——
    // 遮挡可能是采样伪影，只有真的点不动才算缺陷（disabled / pointer-events 属确定性阻断，不点）。
    const isBlockedOnly = b => !b.clickable.ok && b.clickable.blocks.every(x => /被遮挡/.test(x));
    const canRunDanger = SAFETY_POLICY === 'all' && TEST_ENV_CONFIRMED;
    if (SAFETY_POLICY === 'all' && !TEST_ENV_CONFIRMED) {
      console.error('[x] safety-policy=all 需要 --test-environment-confirmed；拒绝执行 danger 操作');
      process.exitCode = 2;
    }
    // 【F46】按安全策略分级放行点击，与 SKILL.md / run_state_scenarios.cjs / run_journeys.cjs 同口径：
    //   staticOnly → 任何点击都不执行；safe → 仅 safe 级；mockWrites → safe+caution（已装写拦截）；
    //   all+confirmed → 全部分级。旧版只挡 danger，staticOnly 下仍会点 safe/caution（违反 SKILL.md:196）。
    const policyAllowsRisk = (risk) => {
      if (SAFETY_POLICY === 'staticOnly') return false;
      if (risk === 'danger') return canRunDanger;
      if (risk === 'caution') return SAFETY_POLICY === 'all' || SAFETY_POLICY === 'mockWrites';
      return true;
    };
    const clickablePool = pool.filter(b => policyAllowsRisk(b.risk) && (b.clickable.ok || isBlockedOnly(b)));
    // 【F44a】超出 MAX_CLICK 的部分必须记 skipped——「既不点也不记」= 那批按钮的
    // 交互验证静默蒸发，报告却显示「审计完成」。
    const queue = clickablePool.slice(0, MAX_CLICK);
    const overBudget = clickablePool.slice(MAX_CLICK);
    overBudget.forEach(b => results.push({
      sel: b.sel, text: b.text, risk: b.risk, skipped: true,
      reason: '点击预算超限：pool ' + clickablePool.length + ' 超 MAX_CLICK ' + MAX_CLICK + '，未执行交互验证',
    }));
    const skippedPolicy = pool.filter(b => !policyAllowsRisk(b.risk) && (b.clickable.ok || isBlockedOnly(b)));
    skippedPolicy.forEach(b => {
      const reason = SAFETY_POLICY === 'staticOnly'
        ? 'staticOnly 策略：不做任何页面交互（含 safe/caution/danger）'
        : b.risk === 'danger'
          ? 'danger 级未点击：未取得 all + testEnvironmentConfirmed 授权'
          : b.risk + ' 级未点击：safety-policy=' + SAFETY_POLICY + ' 不允许交互';
      results.push({ sel: b.sel, text: b.text, risk: b.risk, skipped: true, reason });
    });
    if (overBudget.length) {
      console.warn('[warn] 点击预算超限：' + overBudget.length + ' 个按钮未交互验证（已记 skipped，'
        + '可用 --max 提高预算）');
    }
    console.log('[i] 待点击 ' + queue.length + ' 个（按策略跳过 ' + skippedPolicy.length
      + ' 个、预算外 ' + overBudget.length + ' 个）');

    for (const b of queue) {
      const rec = { sel: b.sel, text: b.text, normText: b.normText, risk: b.risk, iconOnly: b.iconOnly, clickable: b.clickable, hit: b.hit };
      if (!b.clickable.ok) {
        const blockedOnly = b.clickable.blocks.every(x => /被遮挡/.test(x));
        if (!blockedOnly) {
          rec.skipped = true; rec.reason = '静态判定不可点击：' + b.clickable.blocks.join(' / ');
          results.push(rec); console.log('  - 跳过(不可点击) ' + b.text + ' :: ' + rec.reason); continue;
        }
        rec.staticNotClickable = b.clickable.blocks.join(' / ');
      }

      obs.requests.length = 0; obs.intercepted.length = 0; obs.dialogs.length = 0; obs.downloads.length = 0; obs.newPages.length = 0;
      const before = { url: page.url(), dom: await page.evaluate(PAGE_JS.dom), toast: await page.evaluate(PAGE_JS.toast), modal: await page.evaluate(PAGE_JS.modal), visible: await page.evaluate(PAGE_JS.visible), layer: await page.evaluate(PAGE_JS.layer) };

      const loc = page.locator(b.sel).nth(b.nth || 0);
      try {
        await loc.scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
        await loc.click({ timeout: 6000 });
        rec.clicked = true;
      } catch (e) {
        rec.clicked = false;
        rec.clickError = String(e && e.message || e).split('\n')[0].slice(0, 140);
      }
      await page.waitForTimeout(1300);

      const after = { url: page.url(), dom: await page.evaluate(PAGE_JS.dom), toast: await page.evaluate(PAGE_JS.toast), modal: await page.evaluate(PAGE_JS.modal), visible: await page.evaluate(PAGE_JS.visible), layer: await page.evaluate(PAGE_JS.layer) };
      const layerAdded = after.layer.filter(x => before.layer.indexOf(x) < 0);
      const visibleDelta = after.visible - before.visible;
      const signals = [];
      if (after.url !== before.url) signals.push('url');
      if (after.dom.htmlLen !== before.dom.htmlLen || after.dom.nodes !== before.dom.nodes) signals.push('dom');
      if (visibleDelta !== 0) signals.push('visible' + (visibleDelta > 0 ? '+' : '') + visibleDelta);
      if (obs.requests.length) signals.push('request(' + obs.requests.length + ')');
      if (obs.intercepted.length) signals.push('writeRequest-blocked(' + obs.intercepted.length + ')');
      if (obs.dialogs.length) signals.push('dialog');
      if (obs.downloads.length) signals.push('download');
      if (obs.newPages.length) signals.push('newTab');
      if (after.toast.join('|') !== before.toast.join('|')) signals.push('toast');
      if (after.modal.join('|') !== before.modal.join('|')) signals.push('modal');
      if (layerAdded.length) signals.push('layer(+' + layerAdded.length + ')');

      rec.effect = { effective: signals.length > 0, signals, visibleDelta, layerAdded, requests: obs.requests.slice(0, 6), intercepted: obs.intercepted.slice(0, 6), dialogs: obs.dialogs, toast: after.toast, modalDelta: after.modal.filter(m => before.modal.indexOf(m) < 0) };
      if (rec.staticNotClickable) rec.confirmed = rec.clicked ? '静态判被遮挡，实测可点击（原判定过严）' : '静态判被遮挡，实测点击失败（确认不可点击）';
      results.push(rec);

      // 点击触发了弹窗/浮层 → 钻取盘点其内部按钮。
      // 这些按钮在弹窗未打开时尺寸为 0、属「不可观测」，只有此刻才能验其可用性。
      if (layerAdded.length || after.modal.join('|') !== before.modal.join('|')) {
        const overlays = await page.evaluate(PAGE_JS.overlays).catch(() => []);
        rec.modalButtons = [];
        for (const ov of overlays) {
          await page.evaluate(s => { window.__AUDIT_SCOPE = s; }, ov.sel).catch(() => {});
          let obj = null;
          try { const raw = await page.evaluate(auditCode); obj = typeof raw === 'string' ? JSON.parse(raw) : raw; } catch (e) {}
          await page.evaluate(() => { try { delete window.__AUDIT_SCOPE; } catch (e) {} }).catch(() => {});
          if (obj && obj.count) {
            rec.modalButtons.push({
              scope: ov.sel, size: ov.w + 'x' + ov.h, z: ov.z, count: obj.count, uniqueCount: obj.uniqueCount,
              hiddenCount: obj.hiddenCount,
              buttons: obj.buttons.concat(obj.genericClickables || []).map(b => ({ text: b.text, risk: b.risk, clickable: b.clickable.ok, blocks: b.clickable.blocks, locator: b.sel }))
            });
          }
        }
        if (rec.modalButtons.length) signals.push('modalButtons(' + rec.modalButtons.reduce((a, m) => a + m.count, 0) + ')');
      }
      const verdict = rec.clicked === false
        ? '【点击抛错】' + (rec.clickError || '')
        : (signals.length ? signals.join(',') : '【点击成功但无任何反应】');
      console.log('  - ' + (b.text || b.sel) + ' [' + b.risk + '] -> ' + verdict);

      // 还原纪律：只要有任何可观测副作用（含弹窗/浮层的显隐、可见元素数变化）就必须 reload，
      // 否则残留弹窗会遮住后续按钮，把它们误判成「不可点击」——这是实测踩过的连锁误报。
      const needRestore = !NO_RESTORE && (after.url !== before.url || after.dom.nodes !== before.dom.nodes ||
        visibleDelta !== 0 || layerAdded.length > 0 ||
        after.modal.join('|') !== before.modal.join('|') || after.toast.join('|') !== before.toast.join('|'));
      if (needRestore) { await load(); }
    }
  }

  // ---- ③ 设计稿配对（--design-buttons）----
  let pairing = null;
  if (DESIGN_BUTTONS && fs.existsSync(DESIGN_BUTTONS)) {
    const dj = JSON.parse(fs.readFileSync(DESIGN_BUTTONS, 'utf8'));
    const fullText = await page.evaluate(() => Array.from(document.querySelectorAll('a,li,span,div,button,[role=button],[class*=tab],[class*=Tab]')).filter(el => {
      const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
      return r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden' && (el.textContent || '').trim();
    }).map(el => ({ text: (el.textContent || '').trim(), tag: el.tagName.toLowerCase(), selector: el.id ? '#' + el.id : null })));
    pairing = pairButtonsWithEvidence(dj.buttons || [], audit.buttons, fullText);
    // 防误报：设计稿 strong 按钮未配对时，先回查页面是否以非按钮形式（tab/链接/li）存在该文本，
    // 避免把「枚举选择器没覆盖到」误报成「按钮缺失」。
    for (const d of pairing.missingInPage) {
      const txt = String(d.text || d.name || '').trim();
      if (!txt) continue;
      d.foundInPage = await page.evaluate((t) => {
        const n = String(t).replace(/\s+/g, '');
        const els = Array.prototype.slice.call(document.querySelectorAll('a,li,span,div,button,[class*=tab],[class*=Tab]'));
        const hit = els.find(el => el.children.length === 0 && String(el.textContent || '').replace(/\s+/g, '') === n);
        if (!hit) return null;
        const cs = getComputedStyle(hit), r = hit.getBoundingClientRect();
        return { sel: hit.tagName.toLowerCase() + (hit.className ? '.' + String(hit.className).split(/\s+/)[0] : ''),
          tag: hit.tagName.toLowerCase(), cls: String(hit.className || ''), cursor: cs.cursor,
          visible: r.width > 0 && r.height > 0, w: Math.round(r.width), h: Math.round(r.height) };
      }, txt).catch(() => null);
      if (d.foundInPage) d.note = '页面存在同文本元素但未被按钮枚举命中（疑似 tab / 链接实现），需人工确认是否真缺按钮';
    }
    const stillMissing = pairing.missingInPage.filter(d => !d.foundInPage);
    console.log('[i] 设计稿按钮 ' + (dj.count || (dj.buttons || []).length) + ' → 成对 ' + pairing.paired.length +
      ' / 设计有页面无 ' + stillMissing.length + '（另 ' + (pairing.missingInPage.length - stillMissing.length) + ' 个以非按钮形式存在）' +
      ' / 页面有设计无 ' + pairing.extraInPage.length + ' / 弱候选未配对 ' + pairing.designUnmatchedWeak.length);
  }

  // ---- 汇总输出 ----
  const res = {
    url: URL_, auditedAt: new Date().toISOString(),
    // dataQuality 让下游能直接读到「本轮结果是不是降级产物」，不必反推 stderr
    dataQuality: degraded.length ? 'degraded' : 'ok',
    degraded,
    count: audit.count, uniqueCount: audit.uniqueCount, hiddenCount: audit.hiddenCount,
    riskSummary: audit.riskSummary, notClickableCount: audit.notClickableCount,
    hidden: audit.hidden,
    containers: audit.containers,   // 【F44c】button_audit.js 的真实键名是 containers——旧读 skippedContainers 恒 undefined
    static: audit.buttons,
    genericClickables: audit.genericClickables || [],
    clicked: results.filter(r => r.clicked).length,
    clickFailed: results.filter(r => r.clicked === false).length,
    skipped: results.filter(r => r.skipped).length,
    noEffect: results.filter(r => r.clicked && r.effect && !r.effect.effective).map(r => ({ sel: r.sel, text: r.text, risk: r.risk })),
    clickResults: results,
    pairing
  };
  fs.writeFileSync(path.join(OUT, 'button_audit.json'), JSON.stringify(res, null, 2));
  await page.screenshot({ path: path.join(OUT, 'button_audit.png'), fullPage: false }).catch(() => {});

  console.log('\n[i] 点击 ' + res.clicked + ' / 点击失败 ' + res.clickFailed + ' / 跳过 ' + res.skipped + ' / 点击无反应 ' + res.noEffect.length);
  if (res.noEffect.length) console.log('[!] 点击无反应：' + res.noEffect.map(x => x.text || x.sel).join(' | '));
  console.log('[i] 输出 -> ' + OUT);

  await context.close();
  process.exit(0);
})().catch(e => { console.error('FATAL', String(e)); process.exit(1); });
