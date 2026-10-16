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
  // 短设计名（btn/a）禁子串：页面任意长文本包含它不算命中。
  const r = pairButtonsWithEvidence([design('确定')], [],
    [{ text: '我们提供确定性的交付承诺', tag: 'div', selector: '.doc', interactive: true }]);
  assert.strictEqual(r.missingInPage.length === 1 || r.paired.length === 0,
    true, '跨词巧合子串不得配对');
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
