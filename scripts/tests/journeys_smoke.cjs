/*
 * run_journeys.cjs 纯函数冒烟：链接候选判定 / 有界规划 / 步骤判定。
 * 这些函数决定"走哪些链接"与"记什么缺陷"，必须在无浏览器环境下锁死。
 * 退出码 0 = 全过。
 */
const driver = require('../node/run_journeys.cjs');

let pass = 0;
let fail = 0;
function check(name, ok, detail) {
  if (ok) { pass += 1; console.log('[PASS] ' + name); }
  else { fail += 1; console.log('[FAIL] ' + name + (detail ? ' — ' + detail : '')); }
}

const { isCandidateLink, planVisits, stepFinding, looksLikeLogin, resolveUrl } = driver;
const BASE = 'https://example.test/list?tab=all';

/* ---- isCandidateLink ---- */
let r = isCandidateLink('/detail/1', BASE, {});
check('同源相对链接通过', r.ok === true && r.url === 'https://example.test/detail/1', JSON.stringify(r));

r = isCandidateLink('https://other.test/x', BASE, {});
check('跨源链接默认跳过', r.ok === false && r.reason.indexOf('跨源') !== -1, JSON.stringify(r));

r = isCandidateLink('https://other.test/x', BASE, { allowCrossOrigin: true });
check('allowCrossOrigin 时跨源放行', r.ok === true, JSON.stringify(r));

r = isCandidateLink('javascript:void(0)', BASE, {});
check('javascript: 协议跳过', r.ok === false, JSON.stringify(r));

r = isCandidateLink('mailto:a@b.c', BASE, {});
check('mailto: 跳过', r.ok === false, JSON.stringify(r));

r = isCandidateLink('/user/delete?id=1', BASE, {});
check('危险词链接跳过（delete）', r.ok === false && r.reason.indexOf('危险词') !== -1, JSON.stringify(r));

r = isCandidateLink('/account/logout', BASE, {});
check('危险词链接跳过（logout）', r.ok === false, JSON.stringify(r));

r = isCandidateLink('/files/report.pdf', BASE, {});
check('下载类资源跳过（.pdf）', r.ok === false && r.reason.indexOf('下载') !== -1, JSON.stringify(r));

r = isCandidateLink('/files/report.pdf?token=1', BASE, {});
check('带 query 的下载资源也跳过', r.ok === false, JSON.stringify(r));

r = isCandidateLink('#section-2', BASE, {});
check('同页锚点跳过', r.ok === false && r.reason.indexOf('锚点') !== -1, JSON.stringify(r));

r = isCandidateLink('/list?tab=done', BASE, {});
check('同页不同 query 算跨页（放行）', r.ok === true, JSON.stringify(r));

r = isCandidateLink('', BASE, {});
check('空 href 跳过', r.ok === false, JSON.stringify(r));

/* ---- planVisits ---- */
const links = [
  { ok: true, url: 'https://example.test/a' },
  { ok: true, url: 'https://example.test/a' },   // 重复
  { ok: false, url: 'https://example.test/b' },  // 不合格
  { ok: true, url: 'https://example.test/c' },
  { ok: true, url: 'https://example.test/d' },
];
let plan = planVisits(links, 10);
check('planVisits 去重+滤掉不合格',
  plan.length === 3 && plan[0].url.endsWith('/a') && plan[1].url.endsWith('/c') && plan[2].url.endsWith('/d'),
  JSON.stringify(plan.map(x => x.url)));
plan = planVisits(links, 1);
check('planVisits 受 maxLinks 约束', plan.length === 1);
plan = planVisits(null, 5);
check('planVisits 空输入不炸', plan.length === 0);

// 回归（v4.15.0 e2e 抓到）：extractLinks 产出的链接没有 ok 字段，只有 url——
// planVisits 曾因要求 l.ok 把真实链接全滤掉（生产/消费字段契约错配，旅程 steps 全空）。
const extractShaped = [
  { url: 'https://example.test/x', href: 'x.html', visible: true, text: 'X', target: '' },
  { url: 'https://example.test/y', href: 'y.html', visible: true, text: 'Y', target: '' },
];
plan = planVisits(extractShaped, 10);
check('planVisits 吃 extractLinks 形状（无 ok 字段）', plan.length === 2, JSON.stringify(plan.map(x => x.url)));

plan = planVisits([{ ok: false, url: 'https://example.test/z' }], 10);
check('planVisits 显式 ok=false 仍跳过', plan.length === 0);

/* ---- stepFinding ---- */
let f = stepFinding({ docStatus: 500, landedChars: 300, url: 'https://example.test/x' });
check('落地 5xx → confirmed P1', f.length === 1 && f[0].status === 'confirmed' && f[0].severityHint === 'P1' && f[0].dimension === '7.39', JSON.stringify(f).slice(0, 160));

f = stepFinding({ docStatus: 404, landedChars: 300, url: 'https://example.test/x' });
check('落地 404 → confirmed P1', f.length === 1 && f[0].property === 'journey-doc-error', JSON.stringify(f).slice(0, 160));

f = stepFinding({ docStatus: 200, landedChars: 8, url: 'https://example.test/x' });
check('落地近空白 → confirmed P1', f.length === 1 && f[0].property === 'journey-landing-blank', JSON.stringify(f).slice(0, 160));

f = stepFinding({ noop: true, fromUrl: 'https://example.test/list', href: '/detail/9' });
check('链接点击无反应 → pending', f.length === 1 && f[0].status === 'pending' && f[0].property === 'journey-link-noop', JSON.stringify(f).slice(0, 160));

f = stepFinding({ loginRedirect: true, fromUrl: 'https://example.test/list', url: 'https://example.test/login?next=/list' });
check('中途弹登录 → pending', f.length === 1 && f[0].status === 'pending' && f[0].property === 'journey-login-redirect', JSON.stringify(f).slice(0, 160));

f = stepFinding({ backBroken: true, backUrl: 'https://example.test/list', backChars: 5 });
check('返回后空白 → confirmed P1', f.length === 1 && f[0].property === 'journey-back-broken', JSON.stringify(f).slice(0, 160));

f = stepFinding({ docStatus: 200, landedChars: 680, url: 'https://example.test/ok' });
check('健康步骤不误报', f.length === 0, JSON.stringify(f).slice(0, 160));

f = stepFinding({});
check('空步骤不炸不误报', f.length === 0);

/* ---- looksLikeLogin ---- */
check('login URL 识别', looksLikeLogin('https://example.test/login?next=/x') === true);
check('passport URL 识别', looksLikeLogin('https://passport.example.test/') === true);
check('正常 URL 不误判', looksLikeLogin('https://example.test/list') === false);

// 回归（v4.17.0 审查抓到）：原先按子串找 '/auth'，把 /author/list、/authors 这类
// 正常业务页判成登录页 → 用户在自己的作者管理页被报"登录态丢失"（假阳性）。
check('/author/list 不判登录页（回归）', looksLikeLogin('https://example.test/author/list') === false);
check('/authors 不判登录页（回归）', looksLikeLogin('https://example.test/authors') === false);
check('/authorize 段仍判登录（OAuth 授权页）', looksLikeLogin('https://example.test/authorize') === true);
check('OAuth 回调不判登录页', looksLikeLogin('https://example.test/oauth/callback') === false);
check('sso 子域判登录', looksLikeLogin('https://sso.example.test/x') === true);
check('相对地址 login 也识别', looksLikeLogin('/user/login') === true);

/* ---- resolveUrl ---- */
check('resolveUrl 解析相对路径', resolveUrl('/a/b', BASE) === 'https://example.test/a/b');
check('resolveUrl 拒绝 javascript:', resolveUrl('javascript:void(0)', BASE) === null);

console.log('----');
console.log('pass=' + pass + ' fail=' + fail);
process.exit(fail ? 1 : 0);
