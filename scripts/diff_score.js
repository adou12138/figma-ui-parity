#!/usr/bin/env node
/**
 * B1（借鉴 Argos 量化 diff-score + diff mask）：纯 Node 实现的确定性像素 diff。
 * 无外部依赖（内置 zlib 解码 / 编码 PNG），node --check 即可通过。
 *
 * 用途：
 *  1) 回归场景（本次截图 vs 上次截图）：确定性像素 diff，输出 0–100 的 diffScore。
 *  2) 配合 ignore-regions（B2）：diff 前把忽略区清零，避免头像随机图 / 时间戳 / 第三方挂件刷噪声。
 *
 * 重要边界：Figma 设计稿 vs 实时页面的「跨域」像素对比意义有限（不同渲染引擎、
 * 矢量与光栅不可直接逐像素比），本脚本主要用于「同一页面两次运行的回归 diff」
 * 以及报告里的差异热力图（差异遮罩）。
 *
 * 用法（CLI）：
 *  node diff_score.js --a figma.png --b page.png [--out mask.png] [--threshold 16] [--ignore ignoredRegions.json]
 *
 * 库用法（被 driver 集成）：
 *  const { diff } = require('./diff_score.js');
 *  const r = diff(aBuf, bBuf, { threshold: 16, ignore: regionsJsonObj });
 */
const fs = require('fs');
const zlib = require('zlib');

// 【F21】平坦区均值漂移阈值：全图平均通道差 ≥ 该值且无像素越线时标记 flatRegionDrift。
// 3/255 约等于「肉眼刚可辨认的整片色偏」，比逐像素判定线（默认 16）低一个量级——
// 正是「主题色改浅 delta=5」这类回归的落点。
const FLAT_DRIFT_MEAN = 3;

// ---------------- PNG 解码（8-bit，colorType 0/2/4/6） ----------------
function readPNG(buf) {
  if (buf.readUInt32BE(0) !== 0x89504e47) throw new Error('not a PNG file');
  let off = 8;
  let width = 0, height = 0, bitDepth = 0, colorType = 0, interlace = 0;
  const idat = [];
  while (off < buf.length) {
    const len = buf.readUInt32BE(off);
    const type = buf.toString('ascii', off + 4, off + 8);
    const data = buf.subarray(off + 8, off + 8 + len);
    if (type === 'IHDR') {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
      interlace = data[12];
    } else if (type === 'IDAT') {
      idat.push(data);
    } else if (type === 'IEND') {
      break;
    }
    off += 12 + len;
  }
  // 【F22】交错（Adam7）PNG 的 IDAT 不是逐行扫描线，本实现按行 unfilter 会**静默
  // 产出错误分数**（不报错、只是数字全错）。显式拒比，避免拿假分数做回归判定。
  if (interlace !== 0) throw new Error('interlaced PNG (Adam7) not supported: interlace=' + interlace);
  if (bitDepth !== 8) throw new Error('only 8-bit PNG supported (got ' + bitDepth + ')');
  const bpp = { 0: 1, 2: 3, 4: 2, 6: 4 }[colorType];
  if (!bpp) throw new Error('unsupported colorType ' + colorType + ' (palette/16-bit not supported)');
  const raw = zlib.inflateSync(Buffer.concat(idat));
  const stride = width * bpp;
  const out = Buffer.alloc(width * height * 4);
  const prev = Buffer.alloc(stride);
  let pos = 0;
  for (let y = 0; y < height; y++) {
    const ft = raw[pos++];
    const line = raw.subarray(pos, pos + stride);
    pos += stride;
    const cur = Buffer.alloc(stride);
    for (let x = 0; x < stride; x++) {
      const a = x >= bpp ? cur[x - bpp] : 0;
      const b = prev[x];
      const c = x >= bpp ? prev[x - bpp] : 0;
      let v = line[x];
      if (ft === 1) v = (v + a) & 255;
      else if (ft === 2) v = (v + b) & 255;
      else if (ft === 3) v = (v + ((a + b) >> 1)) & 255;
      else if (ft === 4) {
        const p = a + b - c;
        const pa = Math.abs(p - a), pb = Math.abs(p - b), pc = Math.abs(p - c);
        v = (v + (pa <= pb && pa <= pc ? a : pb <= pc ? b : c)) & 255;
      }
      cur[x] = v;
    }
    for (let x = 0; x < width; x++) {
      const si = x * bpp, di = (y * width + x) * 4;
      if (colorType === 0) { out[di] = cur[si]; out[di + 1] = cur[si]; out[di + 2] = cur[si]; out[di + 3] = 255; }
      else if (colorType === 2) { out[di] = cur[si]; out[di + 1] = cur[si + 1]; out[di + 2] = cur[si + 2]; out[di + 3] = 255; }
      else if (colorType === 4) { out[di] = cur[si]; out[di + 1] = cur[si]; out[di + 2] = cur[si]; out[di + 3] = cur[si + 1]; }
      else { out[di] = cur[si]; out[di + 1] = cur[si + 1]; out[di + 2] = cur[si + 2]; out[di + 3] = cur[si + 3]; }
    }
    cur.copy(prev);
  }
  return { width, height, data: out };
}

// ---------------- PNG 编码（RGBA, 8-bit） ----------------
const CRC_TABLE = (() => {
  const t = new Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 255] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length, 0);
  const t = Buffer.from(type, 'ascii');
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(Buffer.concat([t, data])), 0);
  return Buffer.concat([len, t, data, crc]);
}
function writePNG(rgba, w, h) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  const stride = w * 4;
  const raw = Buffer.alloc((stride + 1) * h);
  for (let y = 0; y < h; y++) {
    raw[y * (stride + 1)] = 0; // filter: None
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, y * stride + stride);
  }
  const idat = zlib.deflateSync(raw);
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', idat), chunk('IEND', Buffer.alloc(0)),
  ]);
}

// ---------------- 忽略区清零 ----------------
function applyIgnore(img, regions) {
  let n = 0;
  for (const r of (regions || [])) {
    const b = r && r.bbox;
    if (!b || b.x == null) continue;
    const x0 = Math.max(0, b.x | 0), y0 = Math.max(0, b.y | 0);
    const x1 = Math.min(img.width, (b.x | 0) + (b.w | 0));
    const y1 = Math.min(img.height, (b.y | 0) + (b.h | 0));
    for (let yy = y0; yy < y1; yy++) {
      for (let xx = x0; xx < x1; xx++) {
        const di = (yy * img.width + xx) * 4;
        img.data[di] = img.data[di + 1] = img.data[di + 2] = img.data[di + 3] = 0;
      }
    }
    n++;
  }
  return n;
}

// ---------------- 增强模式：抗锯齿与孤立噪点抑制（v4.16.0） ----------------
/**
 * 默认**关闭**（不传 --enhanced 时行为与引入前逐像素一致，保历史基线可比）。
 * 开启后只做两件"只降噪、不压真缺陷"的事，并把抑制量写进结果：
 *
 * 1. 边缘自适应阈值：抗锯齿/几何偏移只发生在**梯度大的边缘像素**上，两侧都是边缘时
 *    把阈值放大 edgeFactor 倍。平坦区域（整块背景、按钮底色、文字块）阈值不变——
 *    "整块变色"这类真缺陷都发生在平坦区，不会被这个机制压掉。
 * 2. 孤立差异像素过滤：8 邻域内没有任何其它差异像素的单点差异按噪点抑制；成片差异
 *    （≥2 连通）全部保留——真实缺陷一定是成片的。
 *
 * 两项抑制量都写进 suppressed.{edgeNoise,isolated}，报告可见，不静默吞掉。
 */
function isEdgePixel(img, x, y, edgeGradient) {
  const lum = (xx, yy) => {
    if (xx < 0 || yy < 0 || xx >= img.width || yy >= img.height) return null;
    const di = (yy * img.width + xx) * 4;
    return 0.299 * img.data[di] + 0.587 * img.data[di + 1] + 0.114 * img.data[di + 2];
  };
  const c = lum(x, y);
  if (c == null) return false;
  let lo = c, hi = c;
  for (const v of [lum(x - 1, y), lum(x + 1, y), lum(x, y - 1), lum(x, y + 1)]) {
    if (v == null) continue;
    if (v < lo) lo = v;
    if (v > hi) hi = v;
  }
  return (hi - lo) >= edgeGradient;
}

function maxChannelDelta(A, B, i) {
  const di = i * 4;
  return Math.max(
    Math.abs(A.data[di] - B.data[di]),
    Math.abs(A.data[di + 1] - B.data[di + 1]),
    Math.abs(A.data[di + 2] - B.data[di + 2]),
    Math.abs(A.data[di + 3] - B.data[di + 3]),
  );
}

// ---------------- 核心 diff ----------------
// 【F22】按左上对齐裁剪到最小公共区（不缩放）：尺寸不等时旧版直接拒比，而管线
// `--a figma.png --b page.png` 几乎不可能等尺寸 → 像素层永久空转。缩放会把整体错位
// 算成无数局部差异（原设计的顾虑仍在），故只裁剪不缩放，裁剪掉的区域显式上报。
function cropToCommon(A, B) {
  const w = Math.min(A.width, B.width), h = Math.min(A.height, B.height);
  const take = (img) => {
    if (img.width === w && img.height === h) return img;
    const out = Buffer.alloc(w * h * 4);
    for (let y = 0; y < h; y++) {
      img.data.copy(out, y * w * 4, y * img.width * 4, y * img.width * 4 + w * 4);
    }
    return { width: w, height: h, data: out };
  };
  return [take(A), take(B)];
}

function diff(aIn, bIn, opts) {
  opts = opts || {};
  let A = Buffer.isBuffer(aIn) ? readPNG(aIn) : readPNG(fs.readFileSync(aIn));
  let B = Buffer.isBuffer(bIn) ? readPNG(bIn) : readPNG(fs.readFileSync(bIn));
  // 【F22】deviceScaleFactor 一致性：同页在不同 dpr 下像素密度不同，直接比会得到
  // 无意义分数（也无从报错）。两值都显式给出且不等时拒比；缺省不校验，保持兼容。
  if (opts.dprA != null && opts.dprB != null && Number(opts.dprA) !== Number(opts.dprB)) {
    return { ok: false, error: 'dpr mismatch', dprA: Number(opts.dprA), dprB: Number(opts.dprB),
             reason: 'deviceScaleFactor 不一致（' + opts.dprA + ' vs ' + opts.dprB + '）：像素密度不同，diffScore 无意义' };
  }
  let sizeMismatch = null;
  if (A.width !== B.width || A.height !== B.height) {
    // 【F22】尺寸不一致：**默认仍拒比**（references/visual-parity.md 明确定为有意设计——
    // 尺寸不同通常意味着截图倍率/视口配错，自动裁剪会把「配置错误」变成「公共区内无差异」
    // 的假通过）。需要继续比对公共区时显式传 `--crop-to-common`，裁剪事实会进产物。
    if (!opts.cropToCommon) {
      return { ok: false, error: 'size mismatch', a: [A.width, A.height], b: [B.width, B.height],
               reason: '尺寸不一致：请回到截图环节修正倍率/视口宽度（references/visual-parity.md）。'
                     + '确需比对公共区时显式加 --crop-to-common，产物会记录未比对区域' };
    }
    sizeMismatch = {
      a: [A.width, A.height], b: [B.width, B.height],
      comparedRegion: [Math.min(A.width, B.width), Math.min(A.height, B.height)],
      note: '尺寸不一致且已按 --crop-to-common 裁剪：仅左上对齐的最小公共区参与比对（不缩放），'
          + '公共区以外未比对；若差异源于尺寸本身（视口/倍率/整页高度不同），本结论不成立',
    };
    [A, B] = cropToCommon(A, B);
  }
  let regions = [];
  if (opts.ignore) {
    try {
      const j = typeof opts.ignore === 'string' ? JSON.parse(fs.readFileSync(opts.ignore, 'utf8')) : opts.ignore;
      regions = j && j.regions ? j.regions : [];
    } catch (e) { /* 忽略文件损坏，继续不屏蔽 */ }
  }
  // 【F22】忽略区域只计一次：同一次屏蔽对 A/B 各调一遍，旧版把两次计数相加
  // → ignoredRegions 恒为真实值的两倍（报告数字虚高一倍）。
  const ignoredCount = Math.max(applyIgnore(A, regions), applyIgnore(B, regions));
  const th = opts.threshold == null ? 16 : opts.threshold;
  const enhanced = !!opts.enhanced;
  const edgeFactor = opts.edgeFactor == null ? 2.5 : opts.edgeFactor;
  const edgeGradient = opts.edgeGradient == null ? 12 : opts.edgeGradient;
  const weakRatio = opts.weakRatio == null ? 0.5 : opts.weakRatio;
  const total = A.width * A.height;
  let changed = 0;
  let weak = 0;
  let edgeNoise = 0;
  let deltaSum = 0;
  const flags = enhanced ? new Uint8Array(total) : null;
  const mask = Buffer.alloc(total * 4);
  for (let i = 0; i < total; i++) {
    const di = i * 4;
    const d = maxChannelDelta(A, B, i);
    deltaSum += d;
    // 【F21】未越判定线的差异一律计入 weak（含旧版直接 continue 掉的 ≤th*weakRatio 段）：
    // 旧版 `if (d <= th * weakRatio) continue` 让 ≤8/255 的像素既不 changed 也不 weak、
    // 彻底蒸发——整页系统性轻微变色（主题色改浅 delta=5）会得到 diffScore=0 的
    // 「无变化」结论。changedPixels/diffScore 口径**不变**（仍只认 d > th）。
    if (d > 0 && d <= th * weakRatio) { weak++; continue; }
    if (d <= 0) continue;
    let hit = d > th;
    if (hit && enhanced) {
      const x = i % A.width, y = (i - x) / A.width;
      if (isEdgePixel(A, x, y, edgeGradient) && isEdgePixel(B, x, y, edgeGradient)
          && d <= th * edgeFactor) {
        edgeNoise++;                                   // 边缘噪点：按抗锯齿抑制
        hit = false;
      }
    }
    if (hit) {
      changed++;
      if (enhanced) flags[i] = 1;
      mask[di] = 239; mask[di + 1] = 68; mask[di + 2] = 68; mask[di + 3] = 180; // 红，半透明
    } else {
      // weak 只记"没越判定线"的：被边缘规则抑制的像素已越过 th，语义不同，不重复计入
      if (d <= th) weak++;
      mask[di + 3] = 0;
    }
  }
  // 孤立差异像素过滤（仅增强模式）：8 邻域无其它差异像素 → 按噪点抑制
  let isolated = 0;
  if (enhanced) {
    for (let i = 0; i < total; i++) {
      if (flags[i] !== 1) continue;
      const x = i % A.width, y = (i - x) / A.width;
      let neighbour = false;
      for (let dy = -1; dy <= 1 && !neighbour; dy++) {
        for (let dx = -1; dx <= 1 && !neighbour; dx++) {
          if (dx === 0 && dy === 0) continue;
          const xx = x + dx, yy = y + dy;
          if (xx < 0 || yy < 0 || xx >= A.width || yy >= A.height) continue;
          if (flags[yy * A.width + xx] === 1) neighbour = true;
        }
      }
      if (!neighbour) {
        flags[i] = 0;
        changed--;
        isolated++;
        const di = i * 4;
        mask[di] = 250; mask[di + 1] = 204; mask[di + 2] = 21; mask[di + 3] = 90; // 淡黄：被抑制的孤立噪点
      }
    }
  }
  const score = +(Math.max(0, changed) / total * 100).toFixed(2);
  const meanDelta = +(deltaSum / total).toFixed(2);
  // 【F21 平坦区均值漂移】没有像素越线、但全图平均通道差明显 >0 ⇒ 整页轻微偏移
  // （主题色改浅、蒙层、整体 gamma 漂移）。这类回归 diffScore=0 完全看不见，
  // 单独置标记让人能追问，而不是把「无变化」当结论。
  const flatRegionDrift = changed === 0 && meanDelta >= FLAT_DRIFT_MEAN;
  let maskImage = null;
  if (opts.out) { fs.writeFileSync(opts.out, writePNG(mask, A.width, A.height)); maskImage = opts.out; }
  const out = {
    ok: true,
    width: A.width, height: A.height,
    threshold: th,
    changedPixels: changed,
    unchangedPixels: total - changed,
    totalPixels: total,
    diffScore: score,
    diffPercent: score,
    maskImage,
    ignoredRegions: ignoredCount,
    // 【F21】弱差异与全图平均漂移**基础模式也报**：旧版 weakPixels 只在增强模式存在，
    // 基础模式的「≤阈值像素」直接蒸发，报告无从看出整页轻微变色。
    weakPixels: weak,
    weakPercent: +(weak / total * 100).toFixed(2),
    meanChannelDelta: meanDelta,
    flatRegionDrift,
  };
  // 【F22】尺寸不一致时把裁剪事实写进产物：读报告的人必须知道「只比了公共区」，
  // 否则会把「公共区内无差异」误读成「整页一致」。
  if (sizeMismatch) out.sizeMismatch = sizeMismatch;
  if (flatRegionDrift) {
    out.flatRegionDriftNote = '无像素越判定线（' + th + '），但全图平均通道差 ' + meanDelta
      + ' ≥ ' + FLAT_DRIFT_MEAN + '：疑似整页系统性轻微变色（主题色/蒙层/gamma 漂移），'
      + 'diffScore 对此不敏感，需人工核对像素之外的色值来源';
  }
  if (enhanced) {
    out.mode = 'enhanced';
    out.suppressed = { edgeNoise, isolated };
    out.note = '增强模式：边缘自适应阈值与孤立噪点已抑制（遮罩里淡黄=被抑制的噪点），'
      + '抑制量见 suppressed，弱差异见 weakPixels（不计入 changedPixels）。'
      + '增强模式与基础模式的 diffScore 口径不同，跨模式比较前先确认基线来自同一模式。';
  }
  return out;
}

// ---------------- CLI ----------------
function cliArg(n, def) {
  const i = process.argv.indexOf('--' + n);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : def;
}
if (require.main === module) {
  const a = cliArg('a'), b = cliArg('b');
  if (!a || !b) { console.error('ERROR: --a and --b required'); process.exit(1); }
  const out = cliArg('out');
  const threshold = cliArg('threshold');
  const ignore = cliArg('ignore');
  const enhanced = process.argv.includes('--enhanced');
  const cropToCommon = process.argv.includes('--crop-to-common');
  const edgeFactor = cliArg('edge-factor');
  const dprA = cliArg('dpr-a'), dprB = cliArg('dpr-b');
  const r = diff(a, b, {
    out,
    threshold: threshold == null ? undefined : parseInt(threshold, 10),
    ignore,
    enhanced,
    cropToCommon,
    edgeFactor: edgeFactor == null ? undefined : parseFloat(edgeFactor),
    dprA: dprA == null ? undefined : parseFloat(dprA),
    dprB: dprB == null ? undefined : parseFloat(dprB),
  });
  console.log(JSON.stringify(r, null, 2));
  process.exit(r.ok ? 0 : 2);
}

module.exports = { readPNG, writePNG, diff, applyIgnore, isEdgePixel, maxChannelDelta };
