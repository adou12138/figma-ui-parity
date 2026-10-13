/*
 * runtime_observability.js 的可执行冒烟：用桩全局在 Node 里真跑
 * （① install ② 触发后 collect），验证脚本能运行且能采到 7.35 异常、7.37 自动确认。
 * 浏览器里才有的 API 全部用最小桩，避免"语法过了但一跑就炸"。
 * 退出码 0 = 全过。
 */
const fs = require('fs');
const path = require('path');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'runtime_observability.js'), 'utf8');

function makeEnv(fetchImpl) {
  const listeners = {};
  const fakeConsole = { error: () => {} };
  const win = {
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    innerWidth: 1440,
    innerHeight: 900,
    scrollX: 0,
    scrollY: 0,
  };
  if (fetchImpl) { win.fetch = function () { return fetchImpl.apply(this, arguments); }; }
  const doc = {
    querySelectorAll: () => [],
    elementFromPoint: () => null,
    documentElement: {},
    body: {},
  };
  const getComputedStyle = () => ({
    display: 'block', visibility: 'visible', opacity: '1',
    pointerEvents: 'auto', position: 'static',
  });
  const location = { href: 'https://example.test/p' };
  // 用括号包住表达式：SRC 以多行注释开头，"return 注释 (IIFE)" 会触发 ASI 变成
  // "return;"，导致返回 undefined。
  const run = new Function(
    'window', 'document', 'location', 'getComputedStyle', 'console',
    'return (' + SRC + '\n)'
  );
  return {
    listeners,
    fakeConsole,
    win,
    call: () => run(win, doc, location, getComputedStyle, fakeConsole),
  };
}

let pass = 0;
let fail = 0;
function check(name, ok, detail) {
  if (ok) { pass += 1; console.log('[PASS] ' + name); }
  else { fail += 1; console.log('[FAIL] ' + name + (detail ? ' — ' + detail : '')); }
}

// ① 7.35：install → 触发错误 → collect
const env = makeEnv();
let out = JSON.parse(env.call());
check('安装钩子返回 mode=install', out.mode === 'install', JSON.stringify(out));

env.fakeConsole.error('boom-from-console');
(env.listeners['error'] || []).forEach((fn) => fn({ message: 'boom-from-onerror', filename: 'app.js' }));

out = JSON.parse(env.call());
check('采集返回 mode=collect', out.mode === 'collect', JSON.stringify(out));
const dims = (out.findings || []).map((f) => f.dimension);
check('采到 7.35 运行期异常', dims.indexOf('7.35') >= 0, JSON.stringify(dims));
check('异常条数 >= 2（console + onerror）',
  (out.findings || []).filter((f) => f.dimension === '7.35').length >= 2, JSON.stringify(out.summary));
check('findings 契约齐全（severity/confidence/status/symptom）',
  (out.findings || []).every((f) => f.severity && f.confidence != null && f.status && f.symptom));

let crashed = false;
try { JSON.parse(env.call()); } catch (e) { crashed = true; }
check('重复采集不崩溃', !crashed);

// ② 7.37 自动确认（fetch 钩子在 .then 里记录，故须 await 后再 collect）
(async () => {
  const URL = 'https://example.test/api/create';
  const OPTS = { method: 'POST', body: 'title=x' };

  // 全部成功 → confirmed
  const okImpl = () => Promise.resolve({ status: 200, ok: true });
  const e1 = makeEnv(okImpl);
  e1.call();
  await e1.win.fetch(URL, OPTS);
  await e1.win.fetch(URL, OPTS);
  const o1 = JSON.parse(e1.call());
  const f1 = (o1.findings || []).filter((f) => f.dimension === '7.37');
  check('7.37 全部成功→confirmed', f1.length === 1 && f1[0].status === 'confirmed', JSON.stringify(f1));
  check('7.37 confirmed 置信度>=0.8', f1.length === 1 && f1[0].confidence >= 0.8,
    JSON.stringify((f1[0] || {}).confidence));

  // 有失败 → pending（服务端拦了重复，交人工）
  let n = 0;
  const mixedImpl = () => { n += 1; const ok = n === 1; return Promise.resolve({ status: ok ? 200 : 500, ok: ok }); };
  const e2 = makeEnv(mixedImpl);
  e2.call();
  await e2.win.fetch(URL, OPTS);
  await e2.win.fetch(URL, OPTS);
  const o2 = JSON.parse(e2.call());
  const f2 = (o2.findings || []).filter((f) => f.dimension === '7.37');
  check('7.37 有失败→pending', f2.length === 1 && f2[0].status === 'pending', JSON.stringify(f2));

  // 单次请求不报
  const e3 = makeEnv(okImpl);
  e3.call();
  await e3.win.fetch(URL, OPTS);
  const o3 = JSON.parse(e3.call());
  check('7.37 单次请求不报',
    (o3.findings || []).filter((f) => f.dimension === '7.37').length === 0, JSON.stringify(o3.summary));

  console.log('\n==== runtime_observability 冒烟：' + pass + ' 通过 / ' + fail + ' 失败 ====');
  process.exit(fail ? 1 : 0);
})();
