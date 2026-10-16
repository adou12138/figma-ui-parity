/*
 * F21 / F22 回归（diff_score.js）。
 *
 * F21：diffScore 对「整页系统性轻微变色」不敏感（≤th*weakRatio 的像素旧版直接蒸发）。
 *      现在这些像素计入 weakPixels/weakPercent，并且「无像素越线但全图平均通道差 ≥3」
 *      必须显式标 flatRegionDrift。**反向断言**：changedPixels/diffScore 口径不能变，
 *      否则阈值判定会被悄悄改松。
 * F22：尺寸不一致默认仍拒比（references/visual-parity.md 的有意设计），
 *      `--crop-to-common` 才裁剪；dpr 不一致直接拒比；交错 PNG 报错；
 *      ignoredRegions 只计一次（旧版两边相加 → 恒为两倍）。
 * 退出码 0 = 全过。
 */
const path = require('path');
const { writePNG, diff, readPNG } = require(path.join(__dirname, '..', 'diff_score.js'));

let pass = 0, fail = 0;
function check(name, ok, detail) {
  if (ok) { pass += 1; console.log('[PASS] ' + name); }
  else { fail += 1; console.log('[FAIL] ' + name + (detail ? ' — ' + detail : '')); }
}

/** 纯色 PNG（RGBA）。 */
function solid(w, h, v) {
  const buf = Buffer.alloc(w * h * 4);
  for (let i = 0; i < w * h; i++) {
    buf[i * 4] = v; buf[i * 4 + 1] = v; buf[i * 4 + 2] = v; buf[i * 4 + 3] = 255;
  }
  return writePNG(buf, w, h);
}

/* ---- 1) F21：整页轻微变色（delta=5 < 阈值 16）必须可见 ---- */
{
  const r = diff(solid(10, 10, 255), solid(10, 10, 250), { threshold: 16 });
  check('F21 基础模式：未越线差异计入 weakPixels',
    r.weakPixels === 100 && r.weakPercent === 100, JSON.stringify({ w: r.weakPixels, pct: r.weakPercent }));
  check('F21 基础模式：全图平均漂移可见',
    r.meanChannelDelta === 5, JSON.stringify({ mean: r.meanChannelDelta }));
  check('F21 平坦区均值漂移被标记',
    r.flatRegionDrift === true && !!r.flatRegionDriftNote, JSON.stringify({ f: r.flatRegionDrift }));
}

/* ---- 2) F21 反向断言：越线像素口径不变 ---- */
{
  const r = diff(solid(10, 10, 255), solid(10, 10, 200), { threshold: 16 });
  check('F21 反向：越线像素仍按原口径计入 changed/diffScore',
    r.changedPixels === 100 && r.diffScore === 100 && r.flatRegionDrift === false,
    JSON.stringify({ c: r.changedPixels, s: r.diffScore, f: r.flatRegionDrift }));
  const same = diff(solid(10, 10, 255), solid(10, 10, 255), { threshold: 16 });
  check('F21 反向：完全相同不误报漂移',
    same.changedPixels === 0 && same.weakPixels === 0 && same.flatRegionDrift === false,
    JSON.stringify({ w: same.weakPixels, f: same.flatRegionDrift }));
}

/* ---- 3) F22：尺寸不一致默认拒比（有意设计，不得改成静默裁剪） ---- */
{
  const r = diff(solid(8, 8, 255), solid(10, 12, 255), {});
  check('F22 尺寸不一致默认拒比且给出可操作原因',
    r.ok === false && r.error === 'size mismatch' && /修正倍率|视口/.test(r.reason || ''),
    JSON.stringify({ ok: r.ok, e: r.error }));
  check('F22 拒比时不得产出分数',
    r.diffScore === undefined, JSON.stringify({ s: r.diffScore }));
}

/* ---- 4) F22：显式 --crop-to-common 才裁剪，且记录未比对区域 ---- */
{
  const r = diff(solid(8, 8, 255), solid(10, 12, 255), { cropToCommon: true });
  check('F22 opt-in 裁剪后可比对公共区',
    r.ok === true && r.sizeMismatch && r.sizeMismatch.comparedRegion.join('x') === '8x8',
    JSON.stringify({ ok: r.ok, m: r.sizeMismatch && r.sizeMismatch.comparedRegion }));
  check('F22 裁剪事实进产物（含未比对说明）',
    !!(r.sizeMismatch && r.sizeMismatch.note && r.sizeMismatch.a && r.sizeMismatch.b));
}

/* ---- 5) F22：dpr 不一致拒比 ---- */
{
  const r = diff(solid(8, 8, 255), solid(8, 8, 255), { dprA: 2, dprB: 1 });
  check('F22 dpr 不一致拒比',
    r.ok === false && r.error === 'dpr mismatch', JSON.stringify({ ok: r.ok, e: r.error }));
  const ok = diff(solid(8, 8, 255), solid(8, 8, 255), { dprA: 2, dprB: 2 });
  check('F22 dpr 一致不拦', ok.ok === true);
}

/* ---- 6) F22：交错 PNG 报错而非静默产假分数 ---- */
{
  const buf = solid(8, 8, 255);
  // IHDR 的 interlace 字节位于 8(PNG 签名) + 8(长度+类型) + 12 = 第 28 字节
  const interlaceOff = 8 + 8 + 12;
  buf[interlaceOff] = 1;
  let threw = null;
  try { readPNG(buf); } catch (e) { threw = String(e.message); }
  check('F22 交错 PNG 显式报错', !!threw && /interlac/i.test(threw), String(threw));
}

/* ---- 7) F22：ignoredRegions 只计一次 ---- */
{
  const regions = { regions: [{ bbox: { x: 0, y: 0, w: 4, h: 4 } }, { bbox: { x: 4, y: 4, w: 2, h: 2 } }] };
  const r = diff(solid(8, 8, 255), solid(8, 8, 255), { ignore: regions });
  check('F22 ignoredRegions 计区域数且不重复相加',
    r.ignoredRegions === 2, JSON.stringify({ n: r.ignoredRegions }));
}

console.log('----');
console.log('pass=' + pass + ' fail=' + fail);
process.exit(fail === 0 ? 0 : 1);
