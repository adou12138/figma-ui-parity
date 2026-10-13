/*
 * run_state_scenarios.cjs 纯函数冒烟：statusOfFindings / residueFindings。
 * 这两个函数决定维度状态与缺陷判定，必须在无浏览器环境下锁死：
 *   - statusOfFindings：无 findings → pass；有 confirmed → fail；仅 pending → pending；
 *   - residueFindings：只硬判"返回后白屏"（confirmed P1），锚点/滚动/筛选项差异一律
 *     pending（保留还是重置是设计决策，不擅自判缺陷——与 wjx E04 状态矩阵同一纪律）。
 * 退出码 0 = 全过。
 */
const driver = require('../node/run_state_scenarios.cjs');

let pass = 0;
let fail = 0;
function check(name, ok, detail) {
  if (ok) { pass += 1; console.log('[PASS] ' + name); }
  else { fail += 1; console.log('[FAIL] ' + name + (detail ? ' — ' + detail : '')); }
}

const { statusOfFindings, residueFindings } = driver;

/* ---- statusOfFindings ---- */
check('无 findings → pass', statusOfFindings([]) === 'pass');
check('有 confirmed → fail', statusOfFindings([{ status: 'confirmed' }]) === 'fail');
check('confirmed+pending 混合 → fail（先到先得看最重）',
  statusOfFindings([{ status: 'pending' }, { status: 'confirmed' }]) === 'fail');
check('仅 pending → pending', statusOfFindings([{ status: 'pending' }]) === 'pending');

/* ---- residueFindings：返回后白屏 → confirmed P1 ---- */
let f = residueFindings(
  { url: 'https://e.test/p', hash: '', scrollY: 0, chips: [], visibleChars: 800 },
  { url: 'https://e.test/p', hash: '', scrollY: 0, chips: [], visibleChars: 5 }
);
check('返回后白屏 → confirmed P1 且只此一条',
  f.length === 1 && f[0].status === 'confirmed' && f[0].severityHint === 'P1' && f[0].dimension === '7.32',
  JSON.stringify(f).slice(0, 200));

/* ---- residueFindings：锚点不一致 → pending（设计决策） ---- */
f = residueFindings(
  { url: 'https://e.test/p', hash: '#a', scrollY: 0, chips: [], visibleChars: 800 },
  { url: 'https://e.test/p', hash: '#b', scrollY: 0, chips: [], visibleChars: 800 }
);
check('返回后锚点不一致 → pending', f.length === 1 && f[0].status === 'pending' && f[0].property === 'route-back-hash',
  JSON.stringify(f).slice(0, 200));

/* ---- residueFindings：滚动差异 > 100 → pending ---- */
f = residueFindings(
  { url: 'https://e.test/p', hash: '', scrollY: 0, chips: [], visibleChars: 800 },
  { url: 'https://e.test/p', hash: '', scrollY: 640, chips: [], visibleChars: 800 }
);
check('返回后滚动差异大 → pending', f.length === 1 && f[0].property === 'route-back-scroll',
  JSON.stringify(f).slice(0, 200));

/* ---- residueFindings：筛选项差异 → pending ---- */
f = residueFindings(
  { url: 'https://e.test/p', hash: '', scrollY: 0, chips: ['进行中'], visibleChars: 800 },
  { url: 'https://e.test/p', hash: '', scrollY: 0, chips: ['已结束'], visibleChars: 800 }
);
check('返回后筛选项不一致 → pending', f.length === 1 && f[0].property === 'route-back-filter',
  JSON.stringify(f).slice(0, 200));

/* ---- residueFindings：状态一致 → 无声（不误报） ---- */
f = residueFindings(
  { url: 'https://e.test/p', hash: '', scrollY: 120, chips: ['进行中'], visibleChars: 800 },
  { url: 'https://e.test/p', hash: '', scrollY: 130, chips: ['进行中'], visibleChars: 800 }
);
check('状态基本一致 → 不误报', f.length === 0, JSON.stringify(f).slice(0, 200));

console.log('----');
console.log('pass=' + pass + ' fail=' + fail);
process.exit(fail ? 1 : 0);
