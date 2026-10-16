/*
 * state_probes.js 的可执行冒烟：
 *   ① node require 直接测纯判定函数（darkFindings / printFindings / failureFindings）；
 *   ② 用桩 window/document 跑页内采集路径（暗色模式 end-to-end），防止"语法过了但一跑就炸"；
 *   ③ 静态纪律：全文无反斜杠（页内脚本约定，MCP 传参会吃掉一层反斜杠）。
 * 退出码 0 = 全过。
 */
const fs = require('fs');
const path = require('path');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'state_probes.js'), 'utf8');
const api = require(path.join(__dirname, '..', 'state_probes.js'));

let pass = 0;
let fail = 0;
function check(name, ok, detail) {
  if (ok) { pass += 1; console.log('[PASS] ' + name); }
  else { fail += 1; console.log('[FAIL] ' + name + (detail ? ' — ' + detail : '')); }
}

/* ---------------- ① 纯判定函数 ---------------- */

// 7.25 暗色：背景仍近白 → confirmed
let f = api.darkFindings([{ sel: 'div.a', text: '标题', color: 'rgb(0,0,0)', bg: 'rgb(255,255,255)' }]);
check('7.25 近白背景记 confirmed', f.length === 1 && f[0].status === 'confirmed' && f[0].dimension === '7.25', JSON.stringify(f));

// 7.25 暗色：深底浅字对比不足 → confirmed
f = api.darkFindings([{ sel: 'div.b', text: '正文', color: 'rgb(60,60,60)', bg: 'rgb(30,30,30)' }]);
check('7.25 低对比度记 confirmed', f.length === 1 && f[0].property === 'dark-contrast', JSON.stringify(f));

// 7.25 暗色：健康页面（深底深字? 不——深底白字对比高）→ 无声
f = api.darkFindings([{ sel: 'div.c', text: '正文', color: 'rgb(255,255,255)', bg: 'rgb(24,24,28)' }]);
check('7.25 健康深色配色不误报', f.length === 0, JSON.stringify(f));

// 7.25 防御：空输入不炸
f = api.darkFindings([]);
check('7.25 空输入无 findings', f.length === 0);

// 7.26 打印：操作按钮可见 → pending（设计决策不擅自判）
f = api.printFindings([{ sel: 'button.save', tag: 'button', text: '保存', isAction: true, visible: true }]);
check('7.26 操作按钮入打印稿记 pending', f.length === 1 && f[0].status === 'pending' && f[0].dimension === '7.26', JSON.stringify(f));

// 7.26 打印：表格裁切 → confirmed
f = api.printFindings([{ sel: 'table.t', tag: 'table', tableOverflow: true }]);
check('7.26 打印态表格裁切记 confirmed', f.length === 1 && f[0].property === 'print-table-clip', JSON.stringify(f));

// 7.26 打印：白字白底 → confirmed
f = api.printFindings([{ sel: 'span.x', tag: 'span', color: 'rgb(255,255,255)', bg: 'rgb(255,255,255)' }]);
check('7.26 打印态白字白底记 confirmed', f.length === 1 && f[0].property === 'print-invisible-text', JSON.stringify(f));

// 7.26 防御：干净页面不误报
f = api.printFindings([{ sel: 'a.link', tag: 'a', text: '查看详情', isAction: false }]);
check('7.26 非操作链接不误报', f.length === 0, JSON.stringify(f));

// 7.33 白屏 → confirmed P1
f = api.failureFindings({ visibleChars: 12, skeletonCount: 0, errorText: '' });
check('7.33 白屏记 confirmed P1', f.length === 1 && f[0].status === 'confirmed' && f[0].severityHint === 'P1', JSON.stringify(f));

// 7.33 内容少但有错误提示 → 【F13 反转】白屏证据独立成条，错误提示只降级不取消：
// 旧断言"不判白屏"恰是 F13 假通过链（[class*=message] 子串抓到成功提示旧节点 →
// hasError 抵消白屏 → 7.33 假通过）。现在产出 pending 白屏 finding 交人工确认。
f = api.failureFindings({ visibleChars: 8, skeletonCount: 0, errorText: '加载失败，请重试' });
check('7.33 短错误提示页白屏降级 pending（F13: 提示不抵消白屏）',
  f.length === 1 && f[0].status === 'pending' && f[0].property === 'failure-white-screen', JSON.stringify(f));

// 7.33 骨架残留 → confirmed P1（与白屏可同时出）
f = api.failureFindings({ visibleChars: 12, skeletonCount: 3, errorText: '' });
check('7.33 白屏+骨架残留两条都出', f.length === 2, JSON.stringify(f));

// 7.33 有错误提示 → 不报（UI 合格）
f = api.failureFindings({ visibleChars: 380, skeletonCount: 0, errorText: '网络开小差了，请稍后重试' });
check('7.33 有错误提示不误报', f.length === 0, JSON.stringify(f));

// 7.33 有内容但无提示 → pending（不擅自判）
f = api.failureFindings({ visibleChars: 380, skeletonCount: 0, errorText: '' });
check('7.33 无提示有内容记 pending', f.length === 1 && f[0].status === 'pending', JSON.stringify(f));

/* ---------------- ② 页内采集路径（桩环境） ---------------- */

const styleMap = new WeakMap();
function setStyle(el, s) { styleMap.set(el, s); }
function makeEl(tag, opts) {
  opts = opts || {};
  return {
    tagName: String(tag).toUpperCase(),
    id: opts.id || '',
    className: opts.className || '',
    childNodes: opts.text ? [{ nodeType: 3, nodeValue: opts.text }] : [],
    getBoundingClientRect: () => ({ width: opts.w == null ? 100 : opts.w, height: opts.h == null ? 20 : opts.h, left: 0, top: 0 }),
    parentElement: opts.parent || null,
    innerText: opts.text || '',
    value: opts.value || '',
    getAttribute: (n) => (n === 'aria-label' ? (opts.ariaLabel || null) : null),
    scrollWidth: opts.scrollWidth || 0,
    clientWidth: opts.clientWidth || 0,
  };
}
const BASE_STYLE = { display: 'block', visibility: 'visible', opacity: '1', backgroundColor: 'rgba(0,0,0,0)' };
function getComputedStyle(el) {
  return Object.assign({}, BASE_STYLE, styleMap.get(el) || {});
}

function makeEnv(mode, docSpec) {
  const win = { __vpProbe: { mode: mode } };
  // 真实的 DOM 链：el → body → html → null。effectiveBg 上溯依赖它，必须建模。
  const html = makeEl('html', {});
  html.parentElement = null;
  if (docSpec.htmlStyle) setStyle(html, docSpec.htmlStyle);
  const body = makeEl('body', {});
  body.parentElement = html;
  body.innerText = docSpec.bodyText || '';
  if (docSpec.bodyStyle) setStyle(body, docSpec.bodyStyle);
  const bucket = (name) => (docSpec[name] || []).map((el) => {
    if (!el.parentElement) el.parentElement = body;   // 未显式指定父节点的一律挂到 body
    return el;
  });
  const doc = {
    querySelectorAll: (sel) => {
      if (sel === '*') return bucket('all');
      if (sel.indexOf('button') !== -1 || sel.indexOf('role=button') !== -1 || sel.indexOf('a[href]') !== -1 || sel.indexOf('submit') !== -1) return bucket('buttons');
      if (sel.indexOf('table') !== -1) return bucket('tables');
      if (sel.indexOf('skeleton') !== -1 || sel.indexOf('loading') !== -1 || sel.indexOf('spinner') !== -1 || sel.indexOf('shimmer') !== -1) return bucket('skeleton');
      if (sel.indexOf('error') !== -1 || sel.indexOf('empty') !== -1 || sel.indexOf('role=alert') !== -1 || sel.indexOf('toast') !== -1 || sel.indexOf('message') !== -1) return bucket('error');
      return [];
    },
    documentElement: html,
    body: body,
  };
  const location = { href: 'https://example.test/page' };
  // 括号包裹：SRC 以多行注释开头，裸 return 会触发 ASI（同 runtime 冒烟踩坑）
  const run = new Function('window', 'document', 'location', 'getComputedStyle', 'console', 'return (' + SRC + '\n)');
  return { call: () => run(win, doc, location, getComputedStyle, { error: () => {} }) };
}

// 回归（v4.17.0 审查抓到）：深色主题最常见的写法是 html{background:#121212} + body 透明。
// effectiveBg 的上溯循环原先不检查 documentElement 自身就返回白色兜底 → 正确适配深色的页面
// 被误判"未做深色适配"（假阳性，正是本 skill 最该避免的那类）。
{
  const el = makeEl('span', { text: '深色页面标题' });
  setStyle(el, { color: 'rgb(238,238,238)', backgroundColor: 'rgba(0,0,0,0)' });
  const env = makeEnv('dark', { all: [el], htmlStyle: { backgroundColor: 'rgb(18,18,18)' } });
  const out = JSON.parse(env.call());
  check('html 自带深色背景时不误判"未适配深色"',
    out.findings.length === 0, JSON.stringify(out.findings).slice(0, 200));
}

// 反向边界：html 仍是浅色（真没适配深色）时必须照常出声，别把修复做成漏报
{
  const el = makeEl('span', { text: '浅色页面标题' });
  setStyle(el, { color: 'rgb(17,17,17)', backgroundColor: 'rgba(0,0,0,0)' });
  const env = makeEnv('dark', { all: [el], htmlStyle: { backgroundColor: 'rgb(255,255,255)' } });
  const out = JSON.parse(env.call());
  check('html 仍是浅色时照常判未适配（修复未造成漏报）',
    out.findings.some(f => f.property === 'dark-hardcoded-light'), JSON.stringify(out.findings).slice(0, 160));
}

// 暗色采集：一个近白背景元素 → 应产出 7.25 confirmed
{
  const parent = makeEl('div', {});
  setStyle(parent, { backgroundColor: 'rgb(255,255,255)' });
  const el = makeEl('span', { text: '标题文字', parent: parent, id: 't1' });
  setStyle(el, { color: 'rgb(0,0,0)' });
  const env = makeEnv('dark', { all: [el] });
  const out = JSON.parse(env.call());
  check('页内采集 dark 产出 7.25 近白背景', out.mode === 'dark' && out.findings.length === 1 && out.findings[0].dimension === '7.25', JSON.stringify(out).slice(0, 200));
}

// 打印采集：保存按钮 + 裁切表格 → 一条 pending + 一条 confirmed
{
  const btn = makeEl('button', { text: '保存' });
  setStyle(btn, {});
  const table = makeEl('table', { scrollWidth: 900, clientWidth: 600 });
  setStyle(table, {});
  const env = makeEnv('print', { buttons: [btn], tables: [table], all: [] });
  const out = JSON.parse(env.call());
  const props = out.findings.map(x => x.property).sort();
  check('页内采集 print 产出按钮 pending + 裁切 confirmed',
    out.mode === 'print' && props.length === 2 && props.indexOf('print-action-buttons') !== -1 && props.indexOf('print-table-clip') !== -1,
    JSON.stringify(out).slice(0, 240));
}

// 失败采集：白屏 + 骨架残留 → 两条 confirmed
{
  const skel = makeEl('div', { className: 'skeleton-box' });
  setStyle(skel, {});
  const env = makeEnv('failure', { skeleton: [skel], all: [], bodyText: '  ' });
  const out = JSON.parse(env.call());
  check('页内采集 failure 产出白屏+骨架两条',
    out.mode === 'failure' && out.findings.length === 2 && out.findings.every(x => x.status === 'confirmed'),
    JSON.stringify(out).slice(0, 240));
}

// 失败采集：有错误提示 → 【F13 反转】白屏 finding 仍产出但降级 pending（提示不抵消白屏）
{
  const err = makeEl('div', { text: '加载失败，请重试' });
  setStyle(err, {});
  const env = makeEnv('failure', { error: [err], all: [], bodyText: '加载失败，请重试' });
  const out = JSON.parse(env.call());
  const ws = out.findings.filter(x => x.property === 'failure-white-screen');
  check('页内采集 failure 有提示时白屏降级 pending（F13）',
    ws.length === 1 && ws[0].status === 'pending', JSON.stringify(out).slice(0, 200));
}

/* ---------------- ③ 静态纪律：无反斜杠 ---------------- */
check('state_probes.js 全文无反斜杠', SRC.indexOf(String.fromCharCode(92)) === -1,
  '发现反斜杠，违反页内脚本约定（MCP 传参会吃掉一层）');

console.log('----');
console.log('pass=' + pass + ' fail=' + fail);
process.exit(fail ? 1 : 0);
