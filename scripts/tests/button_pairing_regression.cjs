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
  const r = pairButtonsWithEvidence([design('确定')], [], [{ text: ' 确定 ', tag: 'li', selector: '.entry' }]);
  assert.strictEqual(r.paired.length, 1);
  assert.strictEqual(r.paired[0].matchedBy, 'fullText');
  assert.strictEqual(r.paired[0].nonStandardEntry, true);
  assert.strictEqual(r.missingInPage.length, 0);
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
