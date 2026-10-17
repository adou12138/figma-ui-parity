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
// 【F10 配套】参数校验必须排在依赖校验之前：先告诉用户「缺 --url」，再谈 playwright。
function arg(n, def) { const i = process.argv.indexOf('--' + n); return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : def; }
const URL_ = arg('url');
if (!URL_) { console.error('ERROR: --url required'); process.exit(1); }

let pw = null;
const candidates = [
  'playwright-core',
  path.join(process.cwd(), 'node_modules', 'playwright-core'),
  path.resolve(__dirname, '..', '..', '..', '..', 'cdp_driver', 'node_modules', 'playwright-core')
];
if (process.env.PLAYWRIGHT_CORE_PATH) candidates.push(process.env.PLAYWRIGHT_CORE_PATH);
for (const c of candidates) { try { pw = require(c); break; } catch (e) { } }
if (!pw) { console.error('ERROR: playwright-core not found. npm i playwright-core'); process.exit(1); }
// 【F42b】复用 scripts/stabilize.js 的跨平台 resolveChrome（Win/Mac/Linux + 系统浏览器兜底），
// 不再自行维护一份 Windows-only 解析（旧版 mac/linux 恒找不到浏览器）。
const { resolveChrome: resolveChromeShared } = require('../stabilize.js');
function resolveChrome() {
  const envPath = process.env.PLAYWRIGHT_CHROME_PATH;
  if (envPath && fs.existsSync(envPath)) return envPath;
  return resolveChromeShared();
}
const { restoreAuth, saveAuth, isLoginPage, DIR } = require('./auth.cjs');
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
  // 【F10】goto 失败不得吞错继续：about:blank 上 isLoginPage 对空 body 返回 false，
  // 会一路走到「保存空 cookie 集 + SAVED + exit 0」，后续脚本注入垃圾登录态。
  try {
    await page.goto(URL_, { waitUntil: 'domcontentloaded', timeout: 40000 });
  } catch (e) {
    console.error('[x] 受保护页打不开，无法校验登录态:', String(e).slice(0, 160));
    await ctx.close(); process.exit(4);
  }
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
  // 【F10 保存前断言】当前 URL 必须是 http(s)（不在 about:blank/error 页），
  // 且上下文里必须真有 cookie——两者任一不满足就说明「登录态校验」建立在假象上，
  // 保存出去的空登录态会让后续所有脚本把受保护页静默弹回登录。
  const finalUrl = page.url();
  const cookieCount = (await ctx.cookies()).length;
  if (!/^https?:\/\//i.test(finalUrl)) {
    console.error('[x] 当前不在 http(s) 页面（' + finalUrl + '），拒绝保存登录态');
    await ctx.close(); process.exit(5);
  }
  if (cookieCount === 0) {
    console.error('[x] 上下文 cookie 数为 0——这不是有效的登录态，拒绝保存'
      + '（页面可能无需登录，或登录态存在 localStorage 而非 cookie，请人工确认后改用 --profile 持久化目录）');
    await ctx.close(); process.exit(5);
  }
  const info = await saveAuth(ctx, 'default');
  console.log('[i] SAVED ->', DIR, '| url =', finalUrl, '| cookies =', cookieCount);
  console.log(JSON.stringify(Object.assign({ finalUrl, cookieCount }, info), null, 2));
  await ctx.close();
  process.exit(0);
})().catch(e => { console.error('FATAL', String(e)); process.exit(1); });
