#!/usr/bin/env node
/**
 * 7.23 设计稿侧按钮提取（从 Figma file.json 提取按钮清单，供与页面配对）
 *
 * 用法：
 *   node extract_design_buttons.cjs --file "parity-test/figma-<key>/file.json" \
 *     [--frame "1:3"] [--out "parity-test/figma-<key>/design_buttons.json"]
 *
 * 输出 { count, strong, weak, frames, buttons: [{nodeId,name,text,confidence,x,y,w,h,frame}] }
 *
 * 置信度：
 *   strong —— 节点名含 btn / button / 按钮（几乎一定是按钮）
 *   weak   —— 仅靠几何特征推断（小尺寸 + 含居中文本 + 有圆角/填充），噪声较多
 * 配对时：strong 未配对 → 「设计有、页面无」；weak 未配对 → 记待确认，不直接判缺失。
 */
const fs = require('fs');
const path = require('path');

function arg(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : def;
}
const FILE = arg('file');
const FRAME = arg('frame', null);
const OUT = arg('out', null);
if (!FILE || !fs.existsSync(FILE)) { console.error('ERROR: --file <figma file.json> not found: ' + FILE); process.exit(1); }

const RE_NAME = /btn|button|按钮/i;
const RE_SKIP_NAME = /btn-?group|button-?group|按钮组|iconfont|iconset/i;
// 几何推断（weak）的噪声过滤：纯数字、含 / 的字段名列表不是按钮；
// 但分页符（« ‹ › »）是真实按钮，**不能**过滤掉。
const RE_NOISE = /^[\s\d+\-—·.、]+$/;
const isNoiseText = t => !t || RE_NOISE.test(t) || t.indexOf('/') >= 0;

const doc = JSON.parse(fs.readFileSync(FILE, 'utf8'));
const root = doc.document || doc;
const buttons = [], frames = [];

function textsOf(n) {
  const out = [];
  (function walk(x) { if (x.type === 'TEXT' && x.characters) out.push(String(x.characters).trim()); for (const c of (x.children || [])) walk(c); })(n);
  return out.join(' ').replace(/\s+/g, ' ').trim();
}
function cornered(n) {
  if (typeof n.cornerRadius === 'number' && n.cornerRadius > 0) return true;
  if (Array.isArray(n.rectangleCornerRadii) && n.rectangleCornerRadii.some(v => v > 0)) return true;
  return !!(n.fills || []).some(f => f && f.visible !== false && f.type === 'SOLID');
}

(function walk(n, frameId, frameName) {
  const b = n.absoluteBoundingBox || {};
  let curFrame = frameId, curName = frameName;
  if (n.type === 'FRAME' && (!frameId || (n.parent && n.parent.type === 'CANVAS'))) { curFrame = n.id; curName = n.name; frames.push({ id: n.id, name: n.name }); }

  const nameHit = RE_NAME.test(n.name || '') && !RE_SKIP_NAME.test(n.name || '');
  const t0 = textsOf(n);
  const smallEnough = b.width > 0 && b.width < 420 && b.height > 0 && b.height < 96 && t0.length > 0 && t0.length <= 10 && !isNoiseText(t0);
  const geometric = smallEnough && cornered(n) && /FRAME|COMPONENT|INSTANCE|GROUP/.test(n.type);

  if (nameHit || geometric) {
    const t = t0.slice(0, 40);
    buttons.push({
      nodeId: n.id, name: n.name, type: n.type,
      text: t, confidence: nameHit ? 'strong' : 'weak',
      x: Math.round(b.x || 0), y: Math.round(b.y || 0), w: Math.round(b.width || 0), h: Math.round(b.height || 0),
      frame: curFrame, frameName: curName
    });
  }
  for (const c of (n.children || [])) walk(c, curFrame, curName);
})(root, null, null);

const scoped = FRAME ? buttons.filter(b => b.frame === FRAME) : buttons;
const res = {
  source: path.basename(FILE), generatedAt: new Date().toISOString(),
  frames, count: scoped.length,
  strong: scoped.filter(b => b.confidence === 'strong').length,
  weak: scoped.filter(b => b.confidence === 'weak').length,
  buttons: scoped
};
const outPath = OUT || path.join(path.dirname(FILE), 'design_buttons.json');
fs.writeFileSync(outPath, JSON.stringify(res, null, 2));
console.log('[i] 设计稿按钮 ' + res.count + '（strong ' + res.strong + ' / weak ' + res.weak + '）-> ' + outPath);
console.log('[i] 画板: ' + frames.map(f => f.id + ' ' + f.name).join(' | '));
