#!/usr/bin/env node
const assert = require('assert');
const { pairButtonsWithEvidence } = require('../node/run_button_audit.cjs');

function design(text, confidence = 'strong') { return { text, name: text, confidence, nodeId: 'test:1' }; }
function page(text, tag = 'button', sel = '#x') {
  return { text, normText: text, title: '', ariaLabel: '', tag, sel, risk: 'caution', clickable: { ok: true } };
}

const cases = [];
function test(name, fn) { fn(); cases.push(name); }

test('inventory wins when leaf text omits bottom button', () => {
  const r = pairButtonsWithEvidence([design('确定')], [page('确定', 'button', '#bottom-confirm')], []);
  assert.strictEqual(r.paired.length, 1);
  assert.strictEqual(r.paired[0].matchedBy, 'buttonInventory');
  assert.strictEqual(r.missingInPage.length, 0);
});

test('full text matches non-standard visible entry', () => {
  // 【F29 反转】fullText 通道收紧：命中元素必须可交互（a/button 标签或
  // interactive/clickable 标记），li/div 纯文字不再是按钮存在的证据。
  const r = pairButtonsWithEvidence([design('确定')], [],
    [{ text: ' 确定 ', tag: 'li', selector: '.entry', interactive: true }]);
  assert.strictEqual(r.paired.length, 1);
  assert.strictEqual(r.paired[0].matchedBy, 'fullText');
  assert.strictEqual(r.paired[0].nonStandardEntry, true);
  assert.strictEqual(r.missingInPage.length, 0);
});

test('fullText non-interactive text is NOT evidence (F29)', () => {
  // 帮助文字/表头里出现过「确定」不再判配对——真缺失必须进 missing。
  const r = pairButtonsWithEvidence([design('确定')], [],
    [{ text: '确定订单后在下一步填写地址', tag: 'li', selector: '.help-text' }]);
  assert.strictEqual(r.paired.length, 0, '纯文字节点不得充当按钮证据');
  assert.strictEqual(r.missingInPage.length, 1);
});

test('fullText short design name rejects substring coincidence (F29)', () => {
  // 【审查修复·原测试恒真】「确定」2 字符走 k.length<3 短名禁子串分支，且旧断言
  // 是宽松或——即使恢复双向子串它也绿（'供确定' 非边界）。重写为两条精确锁定：
  // ① 3+ 字符设计名跨词巧合 → 禁子串生效，missing（锁词边界逻辑）；
  const r3 = pairButtonsWithEvidence([design('确认订单')], [],
    [{ text: '我们提供确认订单的承诺', tag: 'div', selector: '.doc', interactive: true }]);
  // '确认订单' 在长文本里完整出现但前后无边界（'供'/'的'）→ 词边界禁配对
  assert.strictEqual(r3.missingInPage.length, 1, '3+ 字符跨词巧合必须走词边界拒绝');
  // ② 2 字符设计名完整出现（词边界满足）→ 仍必须 missing（锁 k.length<3 禁子串；
  //    修复前双向子串会判 paired——这是 F29 反转点的真正回归锁）
  const r2 = pairButtonsWithEvidence([design('确定')], [],
    [{ text: '请点击 确定 按钮继续', tag: 'div', selector: '.doc', interactive: true }]);
  assert.strictEqual(r2.paired.length, 0, '2 字符短名即使词边界完整也禁 fullText 配对');
  assert.strictEqual(r2.missingInPage.length, 1);
});

test('zero-width and whitespace normalize', () => {
  const r = pairButtonsWithEvidence([design('管理员·管理')], [page('管理员 \u200b ·  管理', 'a', '#tab')], []);
  assert.strictEqual(r.paired.length, 1);
  assert.strictEqual(r.paired[0].matchedBy, 'buttonInventory');
});

test('missing only when both evidence channels fail', () => {
  const r = pairButtonsWithEvidence([design('不存在的入口')], [], []);
  assert.strictEqual(r.paired.length, 0);
  assert.strictEqual(r.missingInPage.length, 1);
  assert.strictEqual(r.missingInPage[0].matchedBy, 'none');
});

test('weak candidates are not hard missing defects', () => {
  const r = pairButtonsWithEvidence([design('标签胶囊', 'weak')], [], []);
  assert.strictEqual(r.missingInPage.length, 0);
  assert.strictEqual(r.designUnmatchedWeak.length, 1);
});

console.log(`button pairing regression: ${cases.length}/${cases.length} passed`);
