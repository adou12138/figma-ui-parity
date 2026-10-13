/*
 * runtime_observability.js 的可执行冒烟：用桩全局在 Node 里真跑两遍
 * （① install ② 触发错误后 collect），验证脚本能运行且能采到 7.35 异常。
 * 浏览器里才有的 API 全部用最小桩，避免"语法过了但一跑就炸"。
 * 退出码 0 = 全过。
 */
const fs = require('fs');
const path = require('path');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'runtime_observability.js'), 'utf8');

function makeEnv() {
  const listeners = {};
  const fakeConsole = { error: () => {} };
  const win = {
    addEventListener: (t, fn) => { (listeners[t] = listeners[t] || []).push(fn); },
    innerWidth: 1440,
    innerHeight: 900,
    scrollX: 0,
    scrollY: 0,
  };
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
    call: () => run(win, doc, location, getComputedStyle, fakeConsole),
  };
}

let pass = 0;
let fail = 0;
function check(name, ok, detail) {
  if (ok) { pass += 1; console.log('[PASS] ' + name); }
  else { fail += 1; console.log('[FAIL] ' + name + (detail ? ' — ' + detail : '')); }
}

// ① install
const env = makeEnv();
let out = JSON.parse(env.call());
check('安装钩子返回 mode=install', out.mode === 'install', JSON.stringify(out));

// ② 制造一次 console.error 与一次 window error
env.fakeConsole.error('boom-from-console');
(env.listeners['error'] || []).forEach((fn) => fn({ message: 'boom-from-onerror', filename: 'app.js' }));

// ③ collect
out = JSON.parse(env.call());
check('采集返回 mode=collect', out.mode === 'collect', JSON.stringify(out));
const dims = (out.findings || []).map((f) => f.dimension);
check('采到 7.35 运行期异常', dims.indexOf('7.35') >= 0, JSON.stringify(dims));
check('异常条数 >= 2（console + onerror）',
  (out.findings || []).filter((f) => f.dimension === '7.35').length >= 2, JSON.stringify(out.summary));
check('findings 契约齐全（severity/confidence/status/symptom）',
  (out.findings || []).every((f) => f.severity && f.confidence != null && f.status && f.symptom));

// ④ 空 DOM 下不崩：再次 collect 仍应是 collect 且不抛
let crashed = false;
try { JSON.parse(env.call()); } catch (e) { crashed = true; }
check('重复采集不崩溃', !crashed);

console.log('\n==== runtime_observability 冒烟：' + pass + ' 通过 / ' + fail + ' 失败 ====');
process.exit(fail ? 1 : 0);
