#!/usr/bin/env node
/**
 * B4（借鉴 Argos ARIA 树 diff）：可访问性树快照 + 结构 diff。
 * 让 a11y 回归变成确定性、可解释的结论——像素看不出的 role / name / 焦点序问题可被抓出，
 * 对应清单 7.19（可访问性与键盘可用性）。
 *
 * 用法：
 *  node capture_aria.js --url <页面URL> --out aria.json [--profile <持久profile>] [--headed] [--wait-login]
 *  node capture_aria.js --diff a.json b.json        # 结构 diff（role + name 树）
 */
const fs = require('fs');
const path = require('path');

function resolvePlaywright() {
  const candidates = ['playwright-core', path.join(process.cwd(), 'node_modules', 'playwright-core')];
  if (process.env.PLAYWRIGHT_CORE_PATH) candidates.push(process.env.PLAYWRIGHT_CORE_PATH);
  for (const c of candidates) { try { return require(c); } catch (e) { /* next */ } }
  return null;
}
function resolveChrome() {
  const base = process.env.PLAYWRIGHT_BROWSERS_PATH && process.env.PLAYWRIGHT_BROWSERS_PATH !== '0'
    ? process.env.PLAYWRIGHT_BROWSERS_PATH
    : path.join(require('os').homedir(), 'AppData', 'Local', 'ms-playwright');
  if (fs.existsSync(base)) {
    const dirs = fs.readdirSync(base).filter(d => /^chromium-/.test(d)).sort().reverse();
    for (const d of dirs) { const p = path.join(base, d, 'chrome-win64', 'chrome.exe'); if (fs.existsSync(p)) return p; }
  }
  return null;
}

async function isLoginPage(page) {
  return page.evaluate(() => {
    const body = document.body ? document.body.innerText : '';
    const url = location.href || '';
    return /login|signin/i.test(url) || /未登录|您还未登录|请先登录|请登录/.test(body) || /立即注册|忘记用户名|验证码登录|账号登录/.test(body);
  }).catch(() => true);
}
async function waitLogin(page, maxMin = 15) {
  const deadline = Date.now() + maxMin * 60000;
  while (Date.now() < deadline) {
    await page.waitForTimeout(5000);
    if (!(await isLoginPage(page))) return true;
  }
  return false;
}

/** 抓取可访问性快照（role + name 树） */
async function captureAria(page) {
  return await page.accessibility.snapshot();
}

/** 把树拍平成 {role, name, depth, path} 列表，便于 diff */
function flatten(node, depth, out, parentPath) {
  if (!node) return;
  const path = (parentPath ? parentPath + ' > ' : '') + (node.role || '?') + (node.name ? ':' + node.name : '');
  out.push({ role: node.role, name: node.name || '', depth, path });
  if (Array.isArray(node.children)) for (const c of node.children) flatten(c, depth + 1, out, path);
}

/** 结构 diff：比较两份快照的 role+name 树 */
function diffAria(a, b) {
  const fa = [], fb = [];
  flatten(a, 0, fa, '');
  flatten(b, 0, fb, '');
  const setB = new Set(fb.map(x => x.path));
  const setA = new Set(fa.map(x => x.path));
  const added = fb.filter(x => !setA.has(x.path)).map(x => ({ role: x.role, name: x.name, path: x.path }));
  const removed = fa.filter(x => !setB.has(x.path)).map(x => ({ role: x.role, name: x.name, path: x.path }));
  return {
    ok: true,
    aCount: fa.length,
    bCount: fb.length,
    addedCount: added.length,
    removedCount: removed.length,
    added, removed,
    summary: added.length === 0 && removed.length === 0 ? '无结构变化' : (added.length + removed.length) + ' 处可访问性结构变化',
  };
}

// ---- CLI ----
function cliArg(n, def) {
  const i = process.argv.indexOf('--' + n);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : def;
}
if (require.main === module) {
  if (process.argv.includes('--diff')) {
    const ai = process.argv.indexOf('--diff') + 1;
    const bi = process.argv.indexOf('--diff') + 2;
    const a = JSON.parse(fs.readFileSync(process.argv[ai], 'utf8'));
    const b = JSON.parse(fs.readFileSync(process.argv[bi], 'utf8'));
    console.log(JSON.stringify(diffAria(a, b), null, 2));
    process.exit(0);
  }
  (async () => {
    const url = cliArg('url');
    const out = cliArg('out', 'aria.json');
    if (!url) { console.error('ERROR: --url required (or use --diff a.json b.json)'); process.exit(1); }
    const pw = resolvePlaywright();
    if (!pw) { console.error('ERROR: playwright-core not found'); process.exit(1); }
    const chrome = resolveChrome();
    const headed = process.argv.includes('--headed');
    const waitLogin = process.argv.includes('--wait-login');
    const profileIdx = process.argv.indexOf('--profile');
    const profile = profileIdx >= 0 ? process.argv[profileIdx + 1] : null;
    let context;
    if (profile) context = await pw.chromium.launchPersistentContext(profile, { headless: !headed, executablePath: chrome, args: ['--no-sandbox'], viewport: { width: 1440, height: 900 } });
    else { const b = await pw.chromium.launch({ headless: !headed, executablePath: chrome, args: ['--no-sandbox'] }); context = await b.newContext({ viewport: { width: 1440, height: 900 } }); }
    const page = context.pages()[0] || await context.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(e => console.warn('[warn]', e));
    await page.waitForTimeout(4000);
    if (await isLoginPage(page)) {
      if (!headed && !waitLogin) { console.error('[x] login required (use --headed/--wait-login)'); await context.close(); process.exit(2); }
      if (!(await waitLogin(page))) { await context.close(); process.exit(2); }
    }
    const snap = await captureAria(page);
    fs.writeFileSync(out, JSON.stringify(snap, null, 2));
    console.log('[i] aria snapshot ->', out, '(nodes:', JSON.stringify(snap).length, 'bytes)');
    await context.close();
    process.exit(0);
  })().catch(e => { console.error('FATAL', String(e)); process.exit(1); });
}

module.exports = { captureAria, diffAria, flatten };
