#!/usr/bin/env node
/**
 * 保存/刷新登录态（供后续多轮浏览器免重复登录）。
 *
 * 用法：
 *   node save_auth.cjs --url "https://目标站/受保护页" [--profile "./.vp_profile"] [--headed] [--max-min 20]
 *
 * 行为：启动浏览器 → 先尝试恢复已存登录态 → 打开受保护页校验 → 若未登录则等待手动登录 → 保存。
 * 无头（默认）时若需要手动登录会失败；加 `--headed` 可显示窗口手动登录。
 */
const fs = require('fs');
const path = require('path');
let pw = null;
const candidates = [
  'playwright-core',
  path.join(process.cwd(), 'node_modules', 'playwright-core'),
  path.resolve(__dirname, '..', '..', '..', '..', 'cdp_driver', 'node_modules', 'playwright-core')
];
if (process.env.PLAYWRIGHT_CORE_PATH) candidates.push(process.env.PLAYWRIGHT_CORE_PATH);
for (const c of candidates) { try { pw = require(c); break; } catch (e) { } }
if (!pw) { console.error('ERROR: playwright-core not found. npm i playwright-core'); process.exit(1); }
function resolveChrome() {
  const candidates = [];
  if (process.env.PLAYWRIGHT_CHROME_PATH) candidates.push(process.env.PLAYWRIGHT_CHROME_PATH);
  const base = process.env.PLAYWRIGHT_BROWSERS_PATH && process.env.PLAYWRIGHT_BROWSERS_PATH !== '0'
    ? process.env.PLAYWRIGHT_BROWSERS_PATH
    : path.join(require('os').homedir(), 'AppData', 'Local', 'ms-playwright');
  if (fs.existsSync(base)) {
    for (const d of fs.readdirSync(base).filter(d => /^chromium-/.test(d)).sort().reverse()) {
      candidates.push(path.join(base, d, 'chrome-win64', 'chrome.exe'));
    }
  }
  candidates.push(
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
  );
  return candidates.find(p => fs.existsSync(p)) || null;
}
const { restoreAuth, saveAuth, isLoginPage, DIR } = require('./auth.cjs');
function arg(n, def) { const i = process.argv.indexOf('--' + n); return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : def; }

const URL_ = arg('url');
if (!URL_) { console.error('ERROR: --url required'); process.exit(1); }
const PROFILE = arg('profile', path.join(process.cwd(), 'parity-test', '.vp_profile'));
const HEADED = process.argv.includes('--headed');
const MAXMIN = parseInt(arg('max-min', '20'), 10);

(async () => {
  const executablePath = resolveChrome();
  if (!executablePath) { console.error('[x] 找不到可用 Chromium/Chrome/Edge；设置 PLAYWRIGHT_CHROME_PATH 后重试'); process.exit(1); }
  const launchOpts = { headless: !HEADED, executablePath, args: ['--no-sandbox'], viewport: { width: 1440, height: 900 } };
  console.log('[i] browser =', executablePath, '| headed =', HEADED);
  const ctx = await pw.chromium.launchPersistentContext(PROFILE, launchOpts);
  const page = ctx.pages()[0] || await ctx.newPage();
  console.log('[i] restoreAuth:', JSON.stringify(await restoreAuth(ctx)));
  await page.goto(URL_, { waitUntil: 'domcontentloaded', timeout: 40000 }).catch(() => { });
  await page.waitForTimeout(4500);
  let need = await isLoginPage(page);
  console.log('[i] needLogin =', need, '| title =', await page.title().catch(() => ''));
  if (need) {
    if (!HEADED) { console.error('[x] 未登录且为无头模式，请加 --headed 手动登录一次'); await ctx.close(); process.exit(2); }
    console.log('[i] 请在有头窗口内登录（最多 ' + MAXMIN + ' 分钟）...');
    const dl = Date.now() + MAXMIN * 60000;
    while (Date.now() < dl) { await page.waitForTimeout(5000); if (!(await isLoginPage(page))) { need = false; break; } }
    if (need) { console.error('[x] 登录超时'); await ctx.close(); process.exit(2); }
  }
  await page.goto(URL_, { waitUntil: 'networkidle', timeout: 45000 }).catch(() => { });
  await page.waitForTimeout(3500);
  if (await isLoginPage(page)) { console.error('[x] 仍未登录，放弃保存'); await ctx.close(); process.exit(3); }
  const info = await saveAuth(ctx, 'default');
  console.log('[i] SAVED ->', DIR);
  console.log(JSON.stringify(info, null, 2));
  await ctx.close();
  process.exit(0);
})().catch(e => { console.error('FATAL', String(e)); process.exit(1); });
