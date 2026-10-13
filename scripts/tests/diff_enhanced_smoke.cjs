/*
 * diff_score.js 增强模式冒烟（v4.16.0）。
 * 重点不是"能降噪"，而是**降噪不压真缺陷**——所以每条抑制机制都配一条反向断言：
 * 边缘噪点被抑制的同时，平坦区的整块变色必须仍然计入 changedPixels。
 * 退出码 0 = 全过。
 */
const path = require('path');
const { writePNG, diff } = require(path.join(__dirname, '..', 'diff_score.js'));

let pass = 0;
let fail = 0;
function check(name, ok, detail) {
  if (ok) { pass += 1; console.log('[PASS] ' + name); }
  else { fail += 1; console.log('[FAIL] ' + name + (detail ? ' — ' + detail : '')); }
}

/** 造 PNG：fill 可为 [r,g,b,a] 或 (x,y)=>[r,g,b,a] */
function makeImg(w, h, fill) {
  const buf = Buffer.alloc(w * h * 4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const c = typeof fill === 'function' ? fill(x, y) : fill;
      const di = (y * w + x) * 4;
      buf[di] = c[0]; buf[di + 1] = c[1]; buf[di + 2] = c[2]; buf[di + 3] = c[3];
    }
  }
  return writePNG(buf, w, h);
}

/* ---- 1) 相同图：两种模式都 0 ---- */
{
  const a = makeImg(20, 20, [255, 255, 255, 255]);
  const p = diff(a, a, {});
  const e = diff(a, a, { enhanced: true });
  check('相同图基础模式 0', p.diffScore === 0 && p.changedPixels === 0, JSON.stringify(p));
  check('相同图增强模式 0 且无抑制项', e.diffScore === 0 && e.suppressed.edgeNoise === 0 && e.suppressed.isolated === 0, JSON.stringify(e));
}

/* ---- 2) 默认关闭：基础模式无 suppressed 字段（口径与引入前一致） ---- */
{
  const a = makeImg(20, 20, [255, 255, 255, 255]);
  const b = makeImg(20, 20, (x, y) => (x === 10 && y === 10) ? [0, 0, 0, 255] : [255, 255, 255, 255]);
  const p = diff(a, b, {});
  check('基础模式保留孤立像素（未默认开启抑制）', p.changedPixels === 1 && p.suppressed === undefined, JSON.stringify(p));
}

/* ---- 3) 孤立差异像素：增强模式抑制、基础模式保留 ---- */
{
  const a = makeImg(20, 20, [255, 255, 255, 255]);
  const b = makeImg(20, 20, (x, y) => (x === 10 && y === 10) ? [0, 0, 0, 255] : [255, 255, 255, 255]);
  const e = diff(a, b, { enhanced: true });
  check('孤立像素被抑制且计数留痕',
    e.changedPixels === 0 && e.suppressed.isolated === 1, JSON.stringify(e.suppressed));
}

/* ---- 4) 成片差异必须保留（真实缺陷都是成片的） ---- */
{
  const a = makeImg(20, 20, [255, 255, 255, 255]);
  const b = makeImg(20, 20, (x, y) => (x >= 8 && x < 11 && y >= 8 && y < 11) ? [0, 0, 0, 255] : [255, 255, 255, 255]);
  const e = diff(a, b, { enhanced: true });
  check('3x3 成片差异全部保留',
    e.changedPixels === 9 && e.suppressed.isolated === 0, JSON.stringify({ c: e.changedPixels, s: e.suppressed }));
}

/* ---- 5) 边缘抗锯齿噪点被抑制 ---- */
{
  // 中缝一列是"边缘"：左右分别是暗/亮，梯度远大于 edgeGradient；只有边缘像素值不同
  const edge = (v) => makeImg(20, 20, (x, y) => (x === 10 ? [v, v, v, 255] : (x < 10 ? [20, 20, 20, 255] : [240, 240, 240, 255])));
  const a = edge(180), b = edge(210);   // 差 30：th=16 < 30 <= th*edgeFactor=40
  const p = diff(a, b, {});
  const e = diff(a, b, { enhanced: true });
  check('边缘噪点：基础模式计为差异', p.changedPixels === 20, JSON.stringify({ c: p.changedPixels }));
  check('边缘噪点：增强模式抑制且留痕',
    e.changedPixels === 0 && e.suppressed.edgeNoise === 20, JSON.stringify({ c: e.changedPixels, s: e.suppressed }));
}

/* ---- 6) 反向断言：平坦区整块变色（真缺陷）不被边缘机制压掉 ---- */
{
  const a = makeImg(40, 40, [255, 255, 255, 255]);
  const b = makeImg(40, 40, (x, y) => (x >= 10 && x < 30 && y >= 10 && y < 30) ? [200, 200, 200, 255] : [255, 255, 255, 255]);
  const e = diff(a, b, { enhanced: true });
  check('平坦区整块变色仍计入 changedPixels（真缺陷不被压掉）',
    e.changedPixels === 400 && e.suppressed.edgeNoise === 0, JSON.stringify({ c: e.changedPixels, s: e.suppressed }));
}

/* ---- 7) 弱差异单列，不计入 changedPixels ---- */
{
  const a = makeImg(20, 20, [255, 255, 255, 255]);
  const b = makeImg(20, 20, (x, y) => (x >= 5 && x < 8 && y >= 5 && y < 8) ? [240, 240, 240, 255] : [255, 255, 255, 255]);
  const e = diff(a, b, { enhanced: true });
  check('弱差异进 weakPixels 且不算 changed',
    e.changedPixels === 0 && e.weakPixels === 9, JSON.stringify({ c: e.changedPixels, w: e.weakPixels }));
}

/* ---- 8) 增强模式输出带口径说明（跨模式比较前必须知道） ---- */
{
  const a = makeImg(10, 10, [255, 255, 255, 255]);
  const b = makeImg(10, 10, [0, 0, 0, 255]);
  const e = diff(a, b, { enhanced: true });
  check('增强模式带 mode/weakPixels/suppressed/note',
    e.mode === 'enhanced' && e.weakPixels != null && e.suppressed != null && typeof e.note === 'string', JSON.stringify(Object.keys(e)));
}

/* ---- 9) 回归（v4.17.0 审查）：边缘抑制的像素不重复计入 weak ----
 * 边缘像素差 30：越过 th(16) 但被边缘规则（×2.5=40）容忍 → 只算 edgeNoise，
 * 不该同时算 weak（否则同一批像素被两种口径各数一遍，报告上"差一点点"被夸大）。
 */
{
  const edge = (v) => makeImg(20, 20, (x, y) => (x === 10 ? [v, v, v, 255] : (x < 10 ? [20, 20, 20, 255] : [240, 240, 240, 255])));
  const e = diff(edge(180), edge(210), { enhanced: true });
  check('边缘抑制像素不计入 weakPixels',
    e.suppressed.edgeNoise === 20 && e.weakPixels === 0, JSON.stringify({ edge: e.suppressed.edgeNoise, weak: e.weakPixels }));
}

/* ---- 10) 基础模式与增强模式的 changedPixels 在"无噪点"时必须一致 ---- */
{
  // 整块强变色（无边缘、无孤立）：两种模式都应数满，证明默认关闭时口径未变
  const a = makeImg(30, 30, [255, 255, 255, 255]);
  const b = makeImg(30, 30, (x, y) => (x >= 5 && x < 25 && y >= 5 && y < 25) ? [0, 0, 0, 255] : [255, 255, 255, 255]);
  const p = diff(a, b, {});
  const e = diff(a, b, { enhanced: true });
  check('无噪点场景两模式 changedPixels 一致', p.changedPixels === e.changedPixels && p.diffScore === e.diffScore,
    JSON.stringify({ plain: p.changedPixels, enhanced: e.changedPixels }));
}

console.log('----');
console.log('pass=' + pass + ' fail=' + fail);
process.exit(fail ? 1 : 0);