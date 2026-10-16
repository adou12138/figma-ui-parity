#!/usr/bin/env node
/**
 * 闸 B：Node / playwright-core 路径下复用 skill 官方提取脚本。
 *
 * 背景：skill 官方脚本原本设计为用 mcp__playwright 的 browser_evaluate 执行。
 * 但「用户必须手动登录」场景下需要可见浏览器，走的是 playwright-core + 有头 Chromium
 * （见 references/headed-login-fallback.md）。以前在这条路径上会自己重写一份简化提取，
 * 导致数据维度不足、7.1-7.21 清单大面积无法执行 —— 本脚本就是为了杜绝这种重写。
 *
 * 官方脚本本身是 IIFE 形式（`(...)()` 返回 JSON 字符串），可直接 page.evaluate 注入。
 *
 * 用法：
 *   node run_official_extraction.cjs --url "https://目标页" \
 *     [--profile "./parity-test/.vp_profile"] [--out "./parity-test/extract"] \
 *     [--headed] [--responsive] [--wait-login] [--stabilize]
 */
const fs = require('fs');
const path = require('path');
const os = require('os');   // 【F4】resolveChrome 用 os.platform()/os.homedir()，顶部未 require 时 ReferenceError
const { stabilize } = require('../stabilize.js');

// ---- 参数 ----
function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : def;
}
const URL_ = arg('url');
const PROFILE = arg('profile', null);
const OUT = arg('out', path.join(process.cwd(), 'extract'));
const HEADED = process.argv.includes('--headed');
const RESPONSIVE = process.argv.includes('--responsive');
const WAIT_LOGIN = process.argv.includes('--wait-login');
const STABILIZE = process.argv.includes('--stabilize');
const CHROME = arg('chrome', null);
const BREAKPOINTS = (arg('breakpoints', '1920,1440,1280,768') || '').split(',').map(n => parseInt(n, 10)).filter(Boolean);

if (!URL_) { console.error('ERROR: --url is required'); process.exit(1); }

// ---- 依赖解析 ----
function resolvePlaywright() {
  const candidates = [
    'playwright-core',
    path.join(process.cwd(), 'node_modules', 'playwright-core'),
    ...(process.env.PLAYWRIGHT_CORE_PATH ? [process.env.PLAYWRIGHT_CORE_PATH] : []),
  ];
  for (const c of candidates) { try { return require(c); } catch (e) { /* next */ } }
  return null;
}
// 跨平台解析 Playwright 自带的 Chromium 可执行文件。
// 默认浏览器目录随 OS 不同：Win=AppData\Local\ms-playwright；macOS=~/Library/Caches/ms-playwright；Linux=~/.cache/ms-playwright。
// 各 OS 内部可执行文件相对路径也不同（chrome-win / chrome-mac(arm64) / chrome-linux）。
function resolveChrome() {
  if (CHROME && fs.existsSync(CHROME)) return CHROME;
  const plat = os.platform();
  const bases = [];
  if (process.env.PLAYWRIGHT_BROWSERS_PATH && process.env.PLAYWRIGHT_BROWSERS_PATH !== '0') {
    bases.push(process.env.PLAYWRIGHT_BROWSERS_PATH);
  }
  const home = os.homedir();
  if (plat === 'win32') bases.push(path.join(home, 'AppData', 'Local', 'ms-playwright'));
  else if (plat === 'darwin') bases.push(path.join(home, 'Library', 'Caches', 'ms-playwright'));
  else bases.push(path.join(home, '.cache', 'ms-playwright')); // linux 及其他类 Unix
  const relByPlat = plat === 'win32'
    ? ['chrome-win/chrome.exe', 'chrome-win64/chrome.exe']
    : plat === 'darwin'
      ? ['chrome-mac/Chromium.app/Contents/MacOS/Chromium', 'chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium']
      : ['chrome-linux/chrome'];
  for (const base of bases) {
    if (!fs.existsSync(base)) continue;
    const dirs = fs.readdirSync(base).filter(d => /^chromium-/.test(d)).sort().reverse();
    for (const d of dirs) {
      for (const r of relByPlat) {
        const p = path.join(base, d, r);
        if (fs.existsSync(p)) return p;
      }
    }
  }
  return null;
}

const pw = resolvePlaywright();
if (!pw) { console.error('ERROR: playwright-core not found. npm i playwright-core'); process.exit(1); }
const chromePath = resolveChrome();
if (!chromePath) { console.error('ERROR: chrome.exe not found under ms-playwright'); process.exit(1); }
console.log('[i] chrome:', chromePath);

// 登录态持久化（跨轮次免重复登录）：可选，缺 auth.cjs 时自动跳过
let auth = null;
try { auth = require('./auth.cjs'); } catch (e) { /* optional */ }

// 官方脚本目录（本文件在 scripts/node/ 下）
const SKILL_SCRIPTS = path.join(__dirname, '..');
const OFFICIAL = {
  containers: path.join(SKILL_SCRIPTS, 'extract_containers.js'),
  texts: path.join(SKILL_SCRIPTS, 'extract_texts.js'),
  icons: path.join(SKILL_SCRIPTS, 'extract_icons.js'),
  alignment: path.join(SKILL_SCRIPTS, 'alignment_modal_checks.js'),
  responsive: path.join(SKILL_SCRIPTS, 'responsive_check.js'),
  inventory: path.join(SKILL_SCRIPTS, 'collect_page_inventory.js'),  // 【F4】:233 用到却缺声明 → path.join(SKILL_SCRIPTS, undefined) TypeError
};
for (const [k, p] of Object.entries(OFFICIAL)) {
  if (!fs.existsSync(p)) console.warn('[warn] missing official script:', k, p);
}

// ---- 登录页判定（多信号；密码框只是弱信号，不可单独判定）----
// 教训：设置页的「成员字段管理」含密码字段（type=password），仅凭密码框会把已登录页面误判为登录页。
// 用户服务协议 之类词会出现在普通页脚，也不能作为登录页特征。
async function isLoginPage(page) {
  return await page.evaluate(() => {
    const body = document.body ? document.body.innerText : '';
    const url = location.href || '';
    const urlLogin = /login|signin/i.test(url);                    // 最强信号
    const notLoggedIn = /未登录|您还未登录|请先登录|请登录/.test(body);
    const markers = /立即注册|忘记用户名|验证码登录|账号登录/.test(body);
    return urlLogin || notLoggedIn || markers;
  }).catch(() => true);
}
async function waitForLogin(page, maxMin = 15) {
  console.log('[i] waiting for manual login (max ' + maxMin + ' min)...');
  const deadline = Date.now() + maxMin * 60 * 1000;
  while (Date.now() < deadline) {
    await page.waitForTimeout(5000);
    if (!(await isLoginPage(page))) { console.log('[i] login detected ->', page.url()); return true; }
  }
  console.error('[x] login timeout');
  return false;
}

// ---- 闸 C：数据质量校验 ----
// 各官方脚本返回结构不同：containers/texts -> {count,elements}；icons -> {count,icons}；
// alignment -> {modals,alignments,clippedControls,suspiciousText}；order -> {order,dividers,scrollable,needScrollActions}。
// 计数优先取 obj.count；结构化对象则合并已知数组键。两者都取不到 → 视为「有效空结果」，不误报。
const STRUCT_KEYS = ['modals', 'alignments', 'clippedControls', 'suspiciousText', 'order', 'dividers', 'scrollable', 'needScrollActions', 'issues'];
function collectList(obj) {
  if (!obj) return null;
  if (Array.isArray(obj)) return obj;
  for (const k of ['elements', 'items', 'icons']) if (Array.isArray(obj[k])) return obj[k];
  const merged = [];
  for (const k of STRUCT_KEYS) if (Array.isArray(obj[k])) merged.push.apply(merged, obj[k]);
  return merged.length ? merged : null;
}
function rectOf(e) { return e && (e.rect || e.bbox); }
function qualityCheck(name, obj) {
  const issues = [];
  if (!obj) { issues.push('empty/null result'); return { name, ok: false, issues }; }
  const list = collectList(obj);
  const declared = typeof obj.count === 'number' ? obj.count : null;
  const n = declared != null ? declared : (list ? list.length : null);
  if (n == null) return { name, ok: true, issues: [], count: 'n/a' };   // 结构化空结果 → 合格
  if (n === 0) issues.push('zero elements');
  if (n > 0 && n < 10 && ['containers', 'texts', 'icons'].indexOf(name) >= 0) issues.push('suspiciously few elements (' + n + ')');
  const withRect = (list || []).filter(rectOf);
  if (withRect.length > 0) {
    const zero = withRect.filter(e => { const r = rectOf(e); return !r || r.w === 0 || r.h === 0; }).length;
    const ratio = zero / withRect.length;
    if (ratio > 0.3) issues.push('zero-size rect ratio ' + (ratio * 100).toFixed(0) + '% (>30%)');
  }
  return { name, ok: issues.length === 0, issues, count: n };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const launchOpts = { headless: !HEADED, executablePath: chromePath, args: ['--no-sandbox'] };
  let context, browser = null;
  if (PROFILE) {
    console.log('[i] persistent profile:', PROFILE);
    context = await pw.chromium.launchPersistentContext(PROFILE, { ...launchOpts, viewport: { width: 1440, height: 900 } });
  } else {
    browser = await pw.chromium.launch(launchOpts);
    context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  }
  const page = context.pages()[0] || await context.newPage();
  if (auth) { try { console.log('[i] restoreAuth:', JSON.stringify(await auth.restoreAuth(context))); } catch (e) { } }
  if (HEADED) {
    await context.addInitScript(() => {
      const inject = () => {
        if (document.body && !document.getElementById('cdp-auto-banner')) {
          const b = document.createElement('div');
          b.id = 'cdp-auto-banner';
          b.textContent = '🤖 自动化对比测试窗口：请在此窗口登录，登录后测试自动继续。请勿关闭。';
          b.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#0095FF;color:#fff;padding:14px;font-size:16px;font-weight:bold;text-align:center;';
          document.body.appendChild(b);
        }
      };
      inject(); document.addEventListener('DOMContentLoaded', inject);
    });
  }

  console.log('[i] goto', URL_);
  await page.goto(URL_, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(e => console.warn('[warn] goto', e));
  await page.waitForTimeout(4000);   // 必须等重定向稳定再判定，否则 body 为空导致信号全落空

  if (await isLoginPage(page)) {
    if (!WAIT_LOGIN && !HEADED) { console.error('[x] login required but --wait-login/--headed not set'); await context.close(); process.exit(2); }
    if (!(await waitForLogin(page))) { await context.close(); process.exit(2); }
  }
  await page.goto(URL_, { waitUntil: 'networkidle', timeout: 45000 }).catch(e => console.warn('[warn] goto2', e));
  await page.waitForTimeout(4000);
  // 提取前复核，绝不允许把登录页当目标页
  let guard = 0;
  while ((await isLoginPage(page)) && guard < 2) {
    guard++;
    console.warn('[warn] still login page, re-waiting (' + guard + ')');
    if (!(await waitForLogin(page))) { await context.close(); process.exit(2); }
    await page.goto(URL_, { waitUntil: 'networkidle', timeout: 45000 }).catch(() => {});
    await page.waitForTimeout(4000);
  }
  if (await isLoginPage(page)) { console.error('[x] ABORT: still login page, not saving'); await context.close(); process.exit(3); }
  if (auth) { try { const si = await auth.saveAuth(context, 'default'); console.log('[i] auth refreshed: ' + si.cookieCount + ' cookies (session ' + si.sessionCookies + ')'); } catch (e) { } }

  // ---- 依次执行官方脚本 ----
  const results = {};
  const qc = [];
  async function runOfficial(key, file, outName) {
    if (!fs.existsSync(file)) { console.warn('[warn] skip missing', key); return null; }
    const code = fs.readFileSync(file, 'utf8');
    let raw;
    try { raw = await page.evaluate(code); }
    catch (e) { console.error('[x] eval failed', key, String(e).slice(0, 200)); return null; }
    let obj = raw;
    if (typeof raw === 'string') { try { obj = JSON.parse(raw); } catch (e) { obj = { raw }; } }
    fs.writeFileSync(path.join(OUT, outName), typeof raw === 'string' ? raw : JSON.stringify(obj, null, 2));
    const q = qualityCheck(key, obj);
    qc.push(q);
    console.log('[i] ' + key + ' -> ' + outName + ' (count=' + (q.count != null ? q.count : '?') + ')' + (q.ok ? ' OK' : ' ISSUES: ' + q.issues.join('; ')));
    results[key] = obj;
    return obj;
  }

  await runOfficial('containers', OFFICIAL.containers, 'containers.json');
  await runOfficial('texts', OFFICIAL.texts, 'texts.json');
  await runOfficial('icons', OFFICIAL.icons, 'icons.json');
  await runOfficial('alignment', OFFICIAL.alignment, 'alignment.json');
  // 统一 inventory：与 MCP 路径产出同一份 page.json 契约
  await runOfficial('inventory', OFFICIAL.inventory, 'page.json');

  // ---- 可选：多断点响应式（7.4）----
  if (RESPONSIVE && fs.existsSync(OFFICIAL.responsive)) {
    const code = fs.readFileSync(OFFICIAL.responsive, 'utf8');
    const resp = {};
    for (const w of BREAKPOINTS) {
      await page.setViewportSize({ width: w, height: 900 });
      await page.waitForTimeout(1500);
      let raw; try { raw = await page.evaluate(code); } catch (e) { raw = null; }
      let obj = raw; if (typeof raw === 'string') { try { obj = JSON.parse(raw); } catch (e) { obj = { raw }; } }
      resp[w] = obj;
      console.log('[i] responsive @' + w + ' done');
    }
    fs.writeFileSync(path.join(OUT, 'responsive.json'), JSON.stringify(resp, null, 2));
    results.responsive = resp;
  }

  if (STABILIZE) {
    try { await stabilize(page, {}); console.log('[i] stabilized before screenshot (animations off, fonts/network idle, lazy-load triggered)'); }
    catch (e) { console.warn('[warn] stabilize failed:', String(e).slice(0, 160)); }
  }

  await page.screenshot({ path: path.join(OUT, 'target.png'), fullPage: true }).catch(e => console.warn('[warn] screenshot', e));

  // ---- 闸 C 汇总 ----
  const failed = qc.filter(q => !q.ok);
  const meta = {
    url: URL_, title: await page.title().catch(() => ''),
    extractedAt: new Date().toISOString(),
    scripts: Object.keys(OFFICIAL).filter(k => fs.existsSync(OFFICIAL[k])),
    responsive: RESPONSIVE ? BREAKPOINTS : null,
    quality: qc,
    qualityPassed: failed.length === 0,
  };
  fs.writeFileSync(path.join(OUT, 'extraction_meta.json'), JSON.stringify(meta, null, 2));

  if (failed.length) {
    console.warn('\n[!] 数据质量闸未通过：');
    failed.forEach(f => console.warn('   - ' + f.name + ': ' + f.issues.join('; ')));
    console.warn('    按 references/gates.md 闸 C 排查后再出报告；相关清单项必须标 dataMissing，不得降级为 pending。');
  } else {
    console.log('\n[i] 数据质量闸通过');
  }
  console.log('[i] outputs ->', OUT);

  await context.close();
  process.exit(failed.length ? 4 : 0);
})().catch(e => { console.error('FATAL', String(e)); process.exit(1); });
