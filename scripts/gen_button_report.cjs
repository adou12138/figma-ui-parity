#!/usr/bin/env node
/**
 * 7.22 / 7.23 按钮审计汇总报告（CSV + HTML）
 *
 * 读入若干 button_audit.json（run_button_audit.cjs 的产物），汇总为：
 *   - button-audit.csv ：逐按钮明细（页面/按钮/风险/定位/可点击性/点击结果/生效信号/结论/等级）
 *   - button-audit.html：人看的总览（各页统计 + 缺陷清单 + 设计遗漏清单）
 *
 * 用法： node gen_button_report.cjs --dir "./parity-test/button-audit" [--out "./parity-test/reports/xxx"]
 */
const fs = require('fs');
const path = require('path');

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : def;
}
const DIR = arg('dir');
const OUT = arg('out', path.join(DIR, 'report'));
if (!DIR || !fs.existsSync(DIR)) { console.error('ERROR: --dir <button-audit 目录> 不存在: ' + DIR); process.exit(1); }

const PAGE_LABEL = { contacts: '通讯录', permissions: '管理员·管理', answer: '成员·作答', settings: '其他设置' };
const pages = [];
for (const name of fs.readdirSync(DIR)) {
  const f = path.join(DIR, name, 'button_audit.json');
  if (fs.existsSync(f)) pages.push({ name, label: PAGE_LABEL[name] || name, data: JSON.parse(fs.readFileSync(f, 'utf8')) });
}
if (!pages.length) { console.error('ERROR: 目录下没有 <page>/button_audit.json'); process.exit(1); }

// ---- 结论判定 ----
function verdictOf(b, clicked) {
  // 「被遮挡」是静态推断，实测点击才是结论：点了能生效说明原判定过严
  if (clicked && clicked.staticNotClickable) {
    return clicked.clicked === false
      ? { verdict: '不可点击', level: '高', note: '静态判被遮挡且实测点击失败（确认不可点击）：' + clicked.staticNotClickable }
      : { verdict: '正常', level: '', note: '静态判被遮挡但实测可点并生效（原判定过严，已在报告中降级）：' + clicked.staticNotClickable };
  }
  if (!b.clickable.ok) {
    const blocks = b.clickable.blocks.join(' / ');
    const strong = /被遮挡\((\d+)点\)|pointer-events|zero-size/.test(blocks);
    const onlySuspicious = /疑似被遮挡/.test(blocks) && !/被遮挡\(\d+点\)/.test(blocks);
    return { verdict: '不可点击', level: onlySuspicious ? '待确认' : (strong ? '高' : '中'), note: blocks + (b.hit && b.hit.blocker ? '；遮挡元素 ' + (b.hit.blocker.sel || b.hit.blocker.cls || b.hit.blocker.tag) : '') };
  }
  if (!clicked) return { verdict: '未验证', level: '待确认', note: '静态判定可点击，但未进入点击队列（danger 级或超出抽样上限）' };
  if (clicked.clicked === false) return { verdict: '点击抛错', level: '待确认', note: 'Playwright 点击失败：' + (clicked.clickError || '') + '（可能是被遮挡或元素不可交互，需人工复核）' };
  if (!clicked.effect || !clicked.effect.effective) return { verdict: '点击无响应', level: '高', note: '点击成功但无任何信号：URL / DOM / 请求 / 弹框 / 提示均无变化' };
  return { verdict: '正常', level: '', note: (clicked.effect.signals || []).join(',') };
}

const rows = [];
for (const p of pages) {
  const clickMap = new Map((p.data.clickResults || []).map(r => [r.sel + '#' + (r.nth || 0), r]));
  for (const b of (p.data.static || [])) {
    const c = clickMap.get(b.sel + '#' + (b.nth || 0));
    const v = verdictOf(b, c);
    rows.push({
      page: p.label, text: (b.text || b.title || b.ariaLabel || '(无文本)').replace(/[\r\n]+/g, ' ').slice(0, 40),
      risk: b.risk, tag: b.tag, duplicate: b.duplicateCount || 1,
      locator: `${b.sel} @ (${b.bbox.x},${b.bbox.y},${b.bbox.w},${b.bbox.h})`,
      clickable: b.clickable.ok ? '可点击' : '不可点击',
      clickResult: c ? (c.skipped ? '跳过' : (c.clicked === false ? '抛错' : '成功')) : '未点击',
      signals: (c && c.effect && c.effect.signals || []).join(','),
      verdict: v.verdict, level: v.level, note: v.note
    });
  }
  // 弹窗内按钮：这些按钮在弹窗未打开时不可观测，只有点击触发后才能盘点
  for (const r of (p.data.clickResults || [])) {
    for (const m of (r.modalButtons || [])) {
      for (const b of (m.buttons || [])) {
        rows.push({
          page: p.label, text: (b.text || '(无文本，图标按钮)').slice(0, 40), risk: b.risk, tag: 'modal-btn', duplicate: 1,
          locator: (b.locator || '') + '  @弹窗 ' + m.scope + ' (' + m.size + ')',
          clickable: b.clickable ? '可点击' : '不可点击', clickResult: '未点击', signals: '',
          verdict: '弹窗内按钮', level: b.clickable ? '' : '中',
          note: '由「' + ((r.text || r.sel) + '').trim() + '」点击后弹出的弹窗内按钮；静态可点击性' + (b.clickable ? '正常' : '异常：' + (b.blocks || []).join(' / '))
        });
      }
    }
  }
  // 设计稿比对结论（缺失项单列）
  for (const d of ((p.data.pairing || {}).missingInPage || [])) {
    if (d.foundInPage) continue;
    rows.push({ page: p.label, text: (d.text || d.name || '').slice(0, 40), risk: '-', tag: d.type || '-', duplicate: 1,
      locator: 'nodeId ' + (d.nodeId || '-'), clickable: '—', clickResult: '—', signals: '',
      verdict: '设计有页面无', level: '高', note: '设计稿按钮在页面未找到配对（已回查同文本元素亦无）' });
  }
  for (const b of ((p.data.pairing || {}).extraInPage || [])) {
    const c = clickMap.get(b.sel + '#' + (b.nth || 0));
    const v = verdictOf(b, c);
    rows.push({ page: p.label, text: (b.text || '(无文本)').slice(0, 40), risk: b.risk, tag: b.tag, duplicate: b.duplicateCount || 1,
      locator: `${b.sel} @ (${b.bbox.x},${b.bbox.y},${b.bbox.w},${b.bbox.h})`, clickable: b.clickable.ok ? '可点击' : '不可点击',
      clickResult: c ? (c.skipped ? '跳过' : (c.clicked === false ? '抛错' : '成功')) : '未点击',
      signals: (c && c.effect && c.effect.signals || []).join(','),
      verdict: '页面有设计无', level: v.verdict === '不可点击' ? '中' : '待确认',
      note: '设计稿未提供该按钮（设计遗漏）；可用性验证：' + v.verdict + (v.note ? '（' + v.note + '）' : '') });
  }
}

// ---- CSV ----
const HEAD = ['页面', '按钮文案', '风险级', '标签', '重复数', '元素定位', '可点击性', '点击结果', '生效信号', '结论', '等级', '说明'];
const q = v => '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"';
const csv = '\ufeff' + [HEAD.map(q).join(',')].concat(rows.map(r => [r.page, r.text, r.risk, r.tag, r.duplicate, r.locator, r.clickable, r.clickResult, r.signals, r.verdict, r.level, r.note].map(q).join(','))).join('\r\n');

// ---- 统计 ----
const stats = pages.map(p => {
  const d = p.data;
  return { label: p.label, count: d.count, std: d.uniqueCount, generic: d.genericCount, hidden: d.hiddenCount,
    notClickable: d.notClickableCount, clicked: d.clicked, failed: d.clickFailed, noEffect: (d.noEffect || []).length,
    paired: d.pairing ? d.pairing.paired.length : '-',
    missing: d.pairing ? d.pairing.missingInPage.filter(x => !x.foundInPage).length : '-',
    nonButton: d.pairing ? d.pairing.missingInPage.filter(x => x.foundInPage).length : '-',
    extra: d.pairing ? d.pairing.extraInPage.length : '-' };
});
const problems = rows.filter(r => ['不可点击', '点击无响应', '点击抛错', '设计有页面无'].indexOf(r.verdict) >= 0);
const extras = rows.filter(r => r.verdict === '页面有设计无');
const modalRows = rows.filter(r => r.verdict === '弹窗内按钮');

fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(path.join(OUT, 'button-audit.csv'), csv, 'utf8');

const esc = s => String(s == null ? '' : s).replace(/[&<>]/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[m]));
const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>按钮可用性与双向盘点报告</title>
<style>
body{margin:0;padding:28px;background:#f6f7f9;color:#1f2329;font:14px/1.6 "PingFang SC","Microsoft YaHei",sans-serif}
h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:26px 0 10px}
.meta{color:#646a73;font-size:13px;margin-bottom:16px}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #dee0e3;border-radius:8px;overflow:hidden;margin-bottom:8px}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid #eff0f1;vertical-align:top;font-size:13px}
th{background:#f2f3f5;font-weight:600}
.ok{color:#0a8f4d}.bad{color:#d83931;font-weight:600}.warn{color:#b7791f}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:10px 0 4px}
.card{background:#fff;border:1px solid #dee0e3;border-radius:8px;padding:12px}
.card b{display:block;font-size:20px;margin-bottom:2px}
.muted{color:#8f959e;font-size:12px}
code{background:#f2f3f5;padding:1px 4px;border-radius:3px;font-size:12px}
</style></head><body>
<h1>按钮可用性与双向盘点报告（7.22 / 7.23）</h1>
<div class="meta">生成时间 ${new Date().toLocaleString('zh-CN')} · 来源 ${pages.map(p => p.label).join(' / ')}</div>

<h2>一、各页统计</h2>
<table><thead><tr><th>页面</th><th>按钮总数(含重复)</th><th>标准按钮</th><th>疑似可点元素</th><th>隐藏容器内(不可观测)</th><th>静态不可点击</th><th>已点击</th><th>点击抛错</th><th>点击无响应</th><th>设计↔页面成对</th><th>设计有页面无</th><th>非按钮形式存在</th><th>页面有设计无</th></tr></thead><tbody>
${stats.map(s => `<tr><td>${esc(s.label)}</td><td>${s.count}</td><td>${s.std}</td><td>${s.generic}</td><td>${s.hidden}</td><td class="${s.notClickable ? 'warn' : 'ok'}">${s.notClickable}</td><td>${s.clicked}</td><td class="${s.failed ? 'bad' : ''}">${s.failed}</td><td class="${s.noEffect ? 'bad' : 'ok'}">${s.noEffect}</td><td>${s.paired}</td><td class="${s.missing ? 'bad' : 'ok'}">${s.missing}</td><td>${s.nonButton}</td><td>${s.extra}</td></tr>`).join('')}
</tbody></table>
<div class="muted">「隐藏容器内」= 弹框/抽屉未打开时尺寸为 0 的按钮，属不可观测（由 7.14 弹框走查覆盖），**不计入缺陷**。「疑似可点元素」= <code>[onclick]</code> 泛匹配到的非标准按钮（字段 chip / 可点行），默认不点击、不参与配对。</div>

<h2>二、需要处理的按钮问题（${problems.length}）</h2>
${problems.length ? `<table><thead><tr><th>页面</th><th>按钮</th><th>风险级</th><th>结论</th><th>等级</th><th>元素定位</th><th>说明</th></tr></thead><tbody>
${problems.map(r => `<tr><td>${esc(r.page)}</td><td>${esc(r.text)}</td><td>${esc(r.risk)}</td><td class="bad">${esc(r.verdict)}</td><td>${esc(r.level)}</td><td><code>${esc(r.locator)}</code></td><td>${esc(r.note)}</td></tr>`).join('')}
</tbody></table>` : '<p class="ok">无</p>'}

<h2>三、弹窗内按钮（点击触发后才可观测，共 ${modalRows.length}）</h2>
${modalRows.length ? `<table><thead><tr><th>页面</th><th>弹窗内按钮</th><th>风险级</th><th>可点击性</th><th>定位</th></tr></thead><tbody>
${modalRows.map(r => `<tr><td>${esc(r.page)}</td><td>${esc(r.text)}</td><td>${esc(r.risk)}</td><td class="${r.clickable === '可点击' ? 'ok' : 'warn'}">${esc(r.clickable)}</td><td><code>${esc(r.locator)}</code></td></tr>`).join('')}
</tbody></table>` : '<p class="muted">本次未观测到「点击后弹窗」类按钮。</p>'}

<h2>四、设计稿未提供、但页面存在的按钮（${extras.length}）<span class="muted">— 已按 7.22 验证可用性</span></h2>
${extras.length ? `<table><thead><tr><th>页面</th><th>按钮</th><th>数量</th><th>风险级</th><th>可用性验证</th><th>元素定位</th></tr></thead><tbody>
${extras.map(r => `<tr><td>${esc(r.page)}</td><td>${esc(r.text)}</td><td>x${r.duplicate}</td><td>${esc(r.risk)}</td><td>${esc(r.clickResult)}${r.signals ? ' / ' + esc(r.signals) : ''}</td><td><code>${esc(r.locator)}</code></td></tr>`).join('')}
</tbody></table>` : '<p>无</p>'}

<h2>五、口径说明</h2>
<ul class="muted">
<li>「点击生效」信号集：URL / DOM / **可见元素数变化** / 请求 / 写请求被拦 / dialog / 下载 / 新标签页 / toast / 弹窗浮层。**预渲染弹窗靠 CSS 显隐切换时，innerHTML 与节点数都不变，只有「可见元素数」会变**——不采这个信号就会把"点击后弹窗"误判成"点击无响应"。</li>
<li>「点击结果」三态：<b>成功</b>（Playwright 点击成功）／<b>抛错</b>（超时或元素不可交互）／<b>跳过</b>（静态确定不可点击，或 danger 级按策略不点）。</li>
<li>被判「被遮挡」的按钮**仍会实测点击一次**：点得动且生效 → 原判定过严、按正常处理；点不动 → 确认不可点击。静态推断不作为最终结论。</li>
<li>每次点击**只要有可观测副作用（含弹窗显隐、可见元素数变化）就 reload 还原**，否则残留弹窗会遮住后续按钮，把它们连锁误判成「不可点击」。</li>
<li>caution 级（保存/提交/添加/同步…）点击时**已拦截写请求并 mock**，不会真正落库；被拦下的请求记录在 <code>clickResults[].effect.intercepted</code>。</li>
<li>danger 级默认不点击；仅在本次运行明确记录 <code>safetyPolicy=all</code> 且 <code>testEnvironmentConfirmed=true</code> 时允许执行，并展示操作前后证据及不可逆风险。</li>
<li>「隐藏容器内」= 弹窗/抽屉未打开时尺寸为 0 的按钮，属不可观测；其中**点击触发后的弹窗内按钮已单独盘点**（见第三节）。</li>
<li>设计稿侧按钮提取含噪声（标签胶囊、字段 chip 等弱候选），未配对时不直接判「缺失」，仅 strong 候选且回查无同文本元素才记「设计有页面无」。</li>
</ul>
</body></html>`;
fs.writeFileSync(path.join(OUT, 'button-audit.html'), html, 'utf8');

console.log('[i] 明细 ' + rows.length + ' 条；按钮问题 ' + problems.length + '；弹窗内按钮 ' + modalRows.length + '；设计遗漏 ' + extras.length);
console.log('  统计:'); stats.forEach(s => console.log('   ' + s.label + ' 标准按钮' + s.std + ' 隐藏' + s.hidden + ' 不可点击' + s.notClickable + ' 已点' + s.clicked + ' 抛错' + s.failed + ' 无响应' + s.noEffect + ' | 成对' + s.paired + ' 缺失' + s.missing + '（非按钮' + s.nonButton + '） 页面多出' + s.extra));
console.log('[i] 输出 -> ' + OUT);
