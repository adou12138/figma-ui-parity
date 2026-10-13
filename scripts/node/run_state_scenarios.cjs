#!/usr/bin/env node
/**
 * 状态场景驱动：7.25 暗色模式 / 7.26 打印视图 / 7.32 页面级状态残留 / 7.33 接口异常
 *
 * 为什么需要这个驱动：discover_scenarios.py 早已生成这四个维度的场景（action 为
 * theme / media / route-back / network），scenario-contract.md 也定义了这些 action，
 * 但执行侧没有对应驱动——这些场景在实际走查里普遍没被执行， report 里只能填 notRun。
 * 本驱动把四类场景变成可执行、可判定、可复现的显式步骤，每个场景产出
 * { dimension, status, findings[] }，status 取值与 coverage_gate.py 的门禁词表一致
 * （pass / fail / pending / notRun）。
 *
 * 安全边界（为什么默认 safe 策略下也能跑）：
 *   - 7.25 / 7.26 只是 page.emulateMedia 切换渲染模式，纯客户端，零副作用；
 *   - 7.32 只做 hash 导航 + history 返回，不提交任何表单；
 *   - 7.33 用 page.route **拦载** XHR/fetch 并直接 fulfill 500——请求根本不到服务端，
 *     不可能产生真实写操作；文档类资源（html/css/img）放行，保证页面能渲染。
 *   - staticOnly 策略下不做任何页面交互，四类场景全部 notRun 并写明原因。
 *
 * 用法：
 *   node run_state_scenarios.cjs --url "https://目标页" [--out "./parity-test/state-scenarios"]
 *     [--profile "资料目录"] [--safety-policy safe] [--only 7.25,7.33] [--headed] [--chrome 路径]
 *
 * 产物：
 *   <out>/state_scenarios.json  —— 场景结果（含 findings 与 status）
 *   <out>/shots/<dimension>.png —— 各场景截图（暗色/打印/异常态）
 */
const fs = require('fs');
const path = require('path');
const { stabilize, resolveChrome } = require('../stabilize.js');

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : def;
}
const URL_ = arg('url');
const OUT = arg('out', path.join(process.cwd(), 'state-scenarios'));
const PROFILE = arg('profile', null);
const CHROME = arg('chrome', null);
const HEADED = process.argv.includes('--headed');
const SAFETY_POLICY = arg('safety-policy', 'safe'); // all | safe | mockWrites | staticOnly
const ONLY = new Set(String(arg('only', '') || '').split(',').map(s => s.trim()).filter(Boolean));
const SHOTS = path.join(OUT, 'shots');

const PROBE_SRC = fs.readFileSync(path.join(__dirname, '..', 'state_probes.js'), 'utf8');

if (!URL_ && require.main === module) { console.error('ERROR: --url is required'); process.exit(1); }

/**
 * 同步解析 Playwright（对齐 run_button_audit.cjs 的驱动模式）。
 * 不用 stabilize.js 的 resolvePlaywright——那个是 async 函数返回 Promise，
 * 漏 await 会拿到 Promise 当模块用（pw.chromium 为 undefined）。
 * 候选取 playwright-core 与 playwright（完整包）两种，兼容只装其一的环境。
 */
function resolvePlaywright() {
  const candidates = [
    'playwright-core',
    'playwright',
    path.join(process.cwd(), 'node_modules', 'playwright-core'),
    path.join(process.cwd(), 'node_modules', 'playwright'),
  ];
  if (process.env.PLAYWRIGHT_CORE_PATH) candidates.push(process.env.PLAYWRIGHT_CORE_PATH);
  for (const c of candidates) { try { return require(c); } catch (e) { /* next */ } }
  return null;
}

/** 解析登录态（可选）：与 run_button_audit.cjs 共用 auth.cjs */
function loadAuth() {
  try { return require('./auth.cjs'); } catch (e) { return null; }
}

async function probe(page, mode) {
  await page.evaluate((m) => { window.__vpProbe = { mode: m }; }, mode);
  const raw = await page.evaluate(PROBE_SRC);
  const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
  return (parsed && parsed.findings) || [];
}

function statusOfFindings(findings) {
  if (!findings.length) return 'pass';
  if (findings.some(f => f.status === 'confirmed')) return 'fail';
  return 'pending';
}

/** 7.32 状态快照：URL / 滚动 / 可见筛选项 / 内容量 */
async function captureState(page) {
  return page.evaluate(() => {
    const WS = new RegExp('[' + String.fromCharCode(32, 9, 10, 13, 12, 11, 0xA0, 0x3000) + ']+', 'g');
    const chips = Array.prototype.slice.call(
      document.querySelectorAll('[class*=filter] [class*=active], [class*=tag] [class*=active], [class*=selected], [aria-selected=true]')
    ).map(el => (el.innerText || '').trim()).filter(Boolean).slice(0, 10);
    return {
      url: location.href,
      hash: location.hash,
      scrollY: Math.round(window.scrollY || 0),
      chips,
      visibleChars: ((document.body && document.body.innerText) || '').replace(WS, '').length,
    };
  });
}

/** 7.32 状态残留比对：只硬判"返回后白屏"这一确定缺陷，其余（保留/重置）是设计决策 → pending */
function residueFindings(before, after) {
  const out = [];
  if (after.visibleChars < 20) {
    out.push({
      dimension: '7.32', symptom: '从其它路由返回后页面近乎空白，内容没有恢复',
      expected: '返回后页面内容恢复正常渲染', actual: '返回后可见文本仅 ' + after.visibleChars + ' 字符',
      severityHint: 'P1', severity: 'P1', confidence: 0.8, status: 'confirmed',
      element: null, evidence: [{ type: 'state-compare', result: 'mismatch' }],
      sources: ['state-scenarios'], property: 'route-back-blank', raw: { after },
    });
    return out;
  }
  if (after.hash !== before.hash) {
    out.push({
      dimension: '7.32', symptom: '从其它路由返回后 URL/锚点与进入时不一致',
      expected: '返回后回到进入时的路由', actual: '进入 hash=' + before.hash + '，返回后 hash=' + after.hash,
      severityHint: 'P3', severity: 'P3', confidence: 0.5, status: 'pending',
      element: null, evidence: [{ type: 'state-compare', result: 'info' }],
      sources: ['state-scenarios'], property: 'route-back-hash', raw: { before: before.hash, after: after.hash },
    });
  }
  if (Math.abs(after.scrollY - before.scrollY) > 100) {
    out.push({
      dimension: '7.32', symptom: '返回后滚动位置与进入时差异较大，可能状态残留或意外重置',
      expected: '滚动位置按设计保留或重置（二者皆可，但不应随机）',
      actual: '进入 scrollY=' + before.scrollY + '，返回后 scrollY=' + after.scrollY,
      severityHint: 'P3', severity: 'P3', confidence: 0.5, status: 'pending',
      element: null, evidence: [{ type: 'state-compare', result: 'info' }],
      sources: ['state-scenarios'], property: 'route-back-scroll', raw: { before: before.scrollY, after: after.scrollY },
    });
  }
  if (before.chips.join('|') !== after.chips.join('|')) {
    out.push({
      dimension: '7.32', symptom: '返回后可见筛选项与进入时不一致，筛选状态可能残留',
      expected: '筛选态按设计保留或重置', actual: '进入=[' + before.chips.join(',') + ']，返回后=[' + after.chips.join(',') + ']',
      severityHint: 'P3', severity: 'P3', confidence: 0.5, status: 'pending',
      element: null, evidence: [{ type: 'state-compare', result: 'info' }],
      sources: ['state-scenarios'], property: 'route-back-filter', raw: { before: before.chips, after: after.chips },
    });
  }
  return out;
}

async function runDark(page) {
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.waitForTimeout(400);
  const shot = path.join(SHOTS, '7.25-dark.png');
  await page.screenshot({ path: shot }).catch(() => {});
  const findings = await probe(page, 'dark');
  await page.emulateMedia({ colorScheme: 'light' });
  return { dimension: '7.25', status: statusOfFindings(findings), findings, screenshot: shot };
}

async function runPrint(page) {
  await page.emulateMedia({ media: 'print' });
  await page.waitForTimeout(400);
  const shot = path.join(SHOTS, '7.26-print.png');
  await page.screenshot({ path: shot }).catch(() => {});
  const findings = await probe(page, 'print');
  await page.emulateMedia({ media: 'screen' });
  return { dimension: '7.26', status: statusOfFindings(findings), findings, screenshot: shot };
}

async function runResidue(page) {
  const before = await captureState(page);
  await page.evaluate(() => { location.hash = '#vp-state-probe'; });
  await page.waitForTimeout(600);
  const nav = await page.goBack({ waitUntil: 'domcontentloaded' }).catch(() => null);
  if (nav === null) {
    return { dimension: '7.32', status: 'notRun', reason: '无历史记录可返回（goBack 返回 null），状态残留无法实测',
             findings: [] };
  }
  await page.waitForTimeout(600);
  const after = await captureState(page);
  const findings = residueFindings(before, after);
  return { dimension: '7.32', status: statusOfFindings(findings), findings };
}

async function runFailure(page) {
  const handler = async (route) => {
    const type = route.request().resourceType();
    if (type === 'xhr' || type === 'fetch') {
      await route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ error: 'mocked-500' }) });
    } else {
      await route.continue();
    }
  };
  await page.route('**/*', handler);
  await page.reload({ waitUntil: 'domcontentloaded' }).catch(() => {});
  await page.waitForTimeout(2500); // 等骨架屏/错误提示渲染稳定
  const shot = path.join(SHOTS, '7.33-failure.png');
  await page.screenshot({ path: shot }).catch(() => {});
  const findings = await probe(page, 'failure');
  await page.unroute('**/*', handler);
  await page.reload({ waitUntil: 'domcontentloaded' }).catch(() => {}); // 恢复正常网络
  return { dimension: '7.33', status: statusOfFindings(findings), findings, screenshot: shot };
}

const RUNNERS = {
  '7.25': runDark,
  '7.26': runPrint,
  '7.32': runResidue,
  '7.33': runFailure,
};

async function main() {
  if (!URL_) { console.error('ERROR: --url is required'); process.exit(1); }
  fs.mkdirSync(SHOTS, { recursive: true });

  // staticOnly：四类场景全是页面交互（媒体仿真/路由拦截/导航往返），
  // 不启动浏览器，直接按维度产出 notRun 并写明原因（门禁要求原因必填）。
  if (SAFETY_POLICY === 'staticOnly') {
    const results = ['7.25', '7.26', '7.32', '7.33']
      .filter(d => !ONLY.size || ONLY.has(d))
      .map(d => ({ dimension: d, status: 'notRun',
                   reason: 'staticOnly 策略：不做任何页面交互（含媒体仿真与路由拦截）', findings: [] }));
    const payload = {
      url: URL_, safetyPolicy: SAFETY_POLICY,
      startedAt: new Date().toISOString(), results,
      summary: { byStatus: { notRun: results.length }, findingsTotal: 0 },
    };
    const outFile = path.join(OUT, 'state_scenarios.json');
    fs.writeFileSync(outFile, JSON.stringify(payload, null, 2), 'utf8');
    console.log(JSON.stringify({ out: outFile, ...payload.summary,
      detail: results.map(r => ({ dimension: r.dimension, status: r.status, findings: 0, reason: r.reason })) }, null, 2));
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
    await page.goto(URL_, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(e => console.warn('[warn] goto:', String(e).slice(0, 120)));
    await stabilize(page, {});

    const results = [];
    for (const dim of ['7.25', '7.26', '7.32', '7.33']) {
      if (ONLY.size && !ONLY.has(dim)) continue;
      try {
        results.push(await RUNNERS[dim](page));
      } catch (e) {
        results.push({ dimension: dim, status: 'notRun', reason: '执行异常：' + String(e).slice(0, 160), findings: [] });
      }
    }

    const byStatus = {};
    results.forEach(r => { byStatus[r.status] = (byStatus[r.status] || 0) + 1; });
    const payload = {
      url: URL_, safetyPolicy: SAFETY_POLICY,
      startedAt: new Date().toISOString(),
      results, summary: { byStatus, findingsTotal: results.reduce((n, r) => n + (r.findings ? r.findings.length : 0), 0) },
    };
    const outFile = path.join(OUT, 'state_scenarios.json');
    fs.writeFileSync(outFile, JSON.stringify(payload, null, 2), 'utf8');
    console.log(JSON.stringify({ out: outFile, ...payload.summary,
      detail: results.map(r => ({ dimension: r.dimension, status: r.status, findings: (r.findings || []).length, reason: r.reason })) }, null, 2));
  } finally {
    await context.close().catch(() => {});
  }
}

if (require.main === module) {
  main().catch(e => { console.error('FATAL', String(e)); process.exit(1); });
}

module.exports = { statusOfFindings, residueFindings, captureState, probe, RUNNERS };
