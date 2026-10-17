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
// 跨平台解析 Chromium/Chrome/Edge（与 check_environment.py 的 browser_candidates 同口径）。
function resolveChrome() {
  const plat = os.platform();
  const candidates = [];
  if (process.env.PLAYWRIGHT_CHROME_PATH) candidates.push(process.env.PLAYWRIGHT_CHROME_PATH);
  const bases = [];
  if (process.env.PLAYWRIGHT_BROWSERS_PATH && process.env.PLAYWRIGHT_BROWSERS_PATH !== '0') {
    bases.push(process.env.PLAYWRIGHT_BROWSERS_PATH);
  }
  const home = os.homedir();
  if (plat === 'win32') bases.push(path.join(home, 'AppData', 'Local', 'ms-playwright'));
  else if (plat === 'darwin') bases.push(path.join(home, 'Library', 'Caches', 'ms-playwright'));
  else bases.push(path.join(home, '.cache', 'ms-playwright'));
  const relByPlat = plat === 'win32'
    ? ['chrome-win64/chrome.exe', 'chrome-win/chrome.exe']
    : plat === 'darwin'
      ? ['chrome-mac/Chromium.app/Contents/MacOS/Chromium', 'chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium']
      : ['chrome-linux/chrome'];
  for (const base of bases) {
    if (!fs.existsSync(base)) continue;
    const dirs = fs.readdirSync(base).filter(d => /^chromium-/.test(d)).sort().reverse();
    for (const d of dirs) {
      for (const r of relByPlat) {
        const p = path.join(base, d, r);
        if (fs.existsSync(p)) candidates.push(p);
      }
    }
  }
  // 【F42b】系统级浏览器兜底：ms-playwright 目录缺失时不再直接判「找不到浏览器」，
  // mac/linux 也能命中系统 Chrome/Edge（旧版三处解析全 Windows-only）。
  if (plat === 'win32') candidates.push(
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe');
  else if (plat === 'darwin') candidates.push(
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/Applications/Chromium.app/Contents/MacOS/Chromium');
  else candidates.push(
    '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable',
    '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/microsoft-edge');
  return candidates.find(p => fs.existsSync(p)) || null;
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
  // 【F6】懒加载重校验：滚动回来后，视口内图片若仍未加载（懒加载失败/被拦截），
  // 立即截图会把「破图占位」当真实渲染比对——尺寸/位置全错，diff 全页假缺陷。
  // 这里给视口内未完成图片一次短重试窗口，仍失败则显式上抛（由调用方决定
  // 是否按数据质量闸降级本轮），不再静默产出脏截图。
  try {
    const pending = await page.evaluate(() => {
      const vh = window.innerHeight || 0;
      return Array.prototype.filter.call(document.images, (img) => {
        const r = img.getBoundingClientRect();
        const inViewport = r.top < vh && r.bottom > 0;
        return inViewport && !(img.complete && img.naturalWidth > 0);
      }).length;
    });
    if (pending > 0) {
      await page.waitForLoadState('networkidle').catch(() => {});
      await page.waitForTimeout(800);
      const stillPending = await page.evaluate(() => {
        const vh = window.innerHeight || 0;
        return Array.prototype.filter.call(document.images, (img) => {
          const r = img.getBoundingClientRect();
          return r.top < vh && r.bottom > 0 && !(img.complete && img.naturalWidth > 0);
        }).length;
      });
      if (stillPending > 0) {
        throw new Error('[stabilize] 视口内仍有 ' + stillPending + ' 张图片未加载（懒加载失败），'
          + '此时截图会比对破图占位——请检查页面资源或对本轮标记数据质量降级');
      }
    }
  } catch (e) {
    if (String(e && e.message || '').indexOf('[stabilize]') === 0) throw e;
    // 评估过程自身出错（页面上下文销毁等）不阻塞既有流程
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
