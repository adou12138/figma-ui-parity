#!/usr/bin/env node
/**
 * B3（借鉴 Argos stabilization-first）：拍摄前先「稳定化」页面，从源头降低 flaky 截图。
 *
 * 在步骤 4 截图 / 步骤 5 像素对比之前调用：关动画、等字体与网络空闲、滚动触发懒加载，
 * 直接喂给闸 C（数据质量闸），减少"渲染未稳 → 零尺寸 rect / 抖动 diff"误报。
 *
 * 库用法（被 run_official_extraction.cjs / driver 集成）：
 *  const { STABILIZE_CSS, stabilize } = require('./stabilize.js');
 *  await stabilize(page, { freezeDynamic: false });
 *
 * CLI 自测（需要 playwright-core + 已装 chromium）：
 *  node stabilize.js --url <页面URL> [--profile <持久profile>] [--headed]
 */
const fs = require('fs');
const path = require('path');
const os = require('os');

// 注入页面的 CSS：彻底关掉过渡/动画，并强制渲染确定性。
// 目的（对应 TRACE 评测 P2-6，缩小跨运行像素波动）：
//  - color-scheme: light 避免系统深色模式默认值导致的背景/文字差异；
//  - text-rendering + 字体平滑一致性：避免不同平台字体光栅化亚像素差异；
//  - backface-visibility: hidden：避免带 transform 的元素在不同运行出现亚像素抗锯齿抖动。
const STABILIZE_CSS = `
*, *::before, *::after {
  animation-duration: 0s !important;
  animation-delay: 0s !important;
  transition-duration: 0s !important;
  transition-delay: 0s !important;
  scroll-behavior: auto !important;
  color-scheme: light !important;
  text-rendering: optimizeLegibility !important;
  -webkit-font-smoothing: antialiased !important;
  -moz-osx-font-smoothing: grayscale !important;
  backface-visibility: hidden !important;
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}
`;

// 在页面里执行：等字体就绪、等图片加载、等网络空闲、滚动触发懒加载再回到顶部。
function STABILIZE_IN_PAGE(scrollSteps) {
  return `(async () => {
    try { if (document.fonts && document.fonts.ready) await document.fonts.ready; } catch (e) {}
    try {
      await Promise.all(Array.prototype.slice.call(document.images).map(function (img) {
        return (img.complete && img.naturalWidth > 0) ? 0 : new Promise(function (res) {
          img.onload = img.onerror = function () { res(); };
          setTimeout(res, 3000);
        });
      }));
    } catch (e) {}
    if (window.__STAB_DONE) return;
    const steps = ${scrollSteps || 6};
    const h = document.documentElement.scrollHeight || 0;
    for (let i = 1; i <= steps; i++) {
      window.scrollTo(0, (h * i) / steps);
      await new Promise(r => setTimeout(r, 120));
    }
    window.scrollTo(0, 0);
    await new Promise(r => setTimeout(r, 200));
    window.__STAB_DONE = true;
  })()`;
}

async function resolvePlaywright() {
  const candidates = ['playwright-core', path.join(process.cwd(), 'node_modules', 'playwright-core')];
  if (process.env.PLAYWRIGHT_CORE_PATH) candidates.push(process.env.PLAYWRIGHT_CORE_PATH);
  for (const c of candidates) { try { return require(c); } catch (e) { /* next */ } }
  return null;
}
// 跨平台解析 Playwright 自带的 Chromium（与 run_official_extraction.cjs 一致）。
function resolveChrome() {
  const plat = os.platform();
  const bases = [];
  if (process.env.PLAYWRIGHT_BROWSERS_PATH && process.env.PLAYWRIGHT_BROWSERS_PATH !== '0') {
    bases.push(process.env.PLAYWRIGHT_BROWSERS_PATH);
  }
  const home = os.homedir();
  if (plat === 'win32') bases.push(path.join(home, 'AppData', 'Local', 'ms-playwright'));
  else if (plat === 'darwin') bases.push(path.join(home, 'Library', 'Caches', 'ms-playwright'));
  else bases.push(path.join(home, '.cache', 'ms-playwright'));
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

/**
 * 稳定化一个已打开并登录的页面。
 * @param {import('playwright-core').Page} page
 * @param {{freezeDynamic?:boolean, scrollSteps?:number, waitNetworkIdle?:boolean}} opts
 */
async function stabilize(page, opts) {
  opts = opts || {};
  await page.addStyleTag({ content: STABILIZE_CSS }).catch(() => {});
  await page.evaluate(STABILIZE_IN_PAGE(opts.scrollSteps || 6)).catch(() => {});
  if (opts.waitNetworkIdle !== false) {
    await page.waitForLoadState('networkidle').catch(() => {});
  }
  // 再次确保回到顶部
  await page.evaluate(() => window.scrollTo(0, 0)).catch(() => {});
  await page.waitForTimeout(300);
  return true;
}

// CLI 自测
if (require.main === module) {
  (async () => {
    const url = process.argv.includes('--url') ? process.argv[process.argv.indexOf('--url') + 1] : null;
    if (!url) { console.error('ERROR: --url required'); process.exit(1); }
    const pw = await resolvePlaywright();   // resolvePlaywright 是 async，必须 await
    if (!pw) { console.error('ERROR: playwright-core not found'); process.exit(1); }
    const chrome = resolveChrome();
    const headed = process.argv.includes('--headed');
    const profileIdx = process.argv.indexOf('--profile');
    const profile = profileIdx >= 0 ? process.argv[profileIdx + 1] : null;
    let context;
    if (profile) context = await pw.chromium.launchPersistentContext(profile, { headless: !headed, executablePath: chrome, args: ['--no-sandbox'], viewport: { width: 1440, height: 900 } });
    else { const b = await pw.chromium.launch({ headless: !headed, executablePath: chrome, args: ['--no-sandbox'] }); context = await b.newContext({ viewport: { width: 1440, height: 900 } }); }
    const page = context.pages()[0] || await context.newPage();
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(e => console.warn('[warn]', e));
    await stabilize(page, {});
    console.log('[i] stabilized; title =', await page.title().catch(() => ''));
    await context.close();
    process.exit(0);
  })().catch(e => { console.error('FATAL', String(e)); process.exit(1); });
}

module.exports = { STABILIZE_CSS, STABILIZE_IN_PAGE, stabilize, resolvePlaywright, resolveChrome };
