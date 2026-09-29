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

// ---------------- PNG 解码（8-bit，colorType 0/2/4/6） ----------------
function readPNG(buf) {
  if (buf.readUInt32BE(0) !== 0x89504e47) throw new Error('not a PNG file');
  let off = 8;
  let width = 0, height = 0, bitDepth = 0, colorType = 0;
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
    } else if (type === 'IDAT') {
      idat.push(data);
    } else if (type === 'IEND') {
      break;
    }
    off += 12 + len;
  }
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

// ---------------- 核心 diff ----------------
function diff(aIn, bIn, opts) {
  opts = opts || {};
  const A = Buffer.isBuffer(aIn) ? readPNG(aIn) : readPNG(fs.readFileSync(aIn));
  const B = Buffer.isBuffer(bIn) ? readPNG(bIn) : readPNG(fs.readFileSync(bIn));
  if (A.width !== B.width || A.height !== B.height) {
    return { ok: false, error: 'size mismatch', a: [A.width, A.height], b: [B.width, B.height] };
  }
  let regions = [];
  if (opts.ignore) {
    try {
      const j = typeof opts.ignore === 'string' ? JSON.parse(fs.readFileSync(opts.ignore, 'utf8')) : opts.ignore;
      regions = j && j.regions ? j.regions : [];
    } catch (e) { /* 忽略文件损坏，继续不屏蔽 */ }
  }
  const ignoredCount = applyIgnore(A, regions) + applyIgnore(B, regions);
  const th = opts.threshold == null ? 16 : opts.threshold;
  const total = A.width * A.height;
  let changed = 0;
  const mask = Buffer.alloc(total * 4);
  for (let i = 0; i < total; i++) {
    const di = i * 4;
    const d = Math.max(
      Math.abs(A.data[di] - B.data[di]),
      Math.abs(A.data[di + 1] - B.data[di + 1]),
      Math.abs(A.data[di + 2] - B.data[di + 2]),
      Math.abs(A.data[di + 3] - B.data[di + 3]),
    );
    if (d > th) {
      changed++;
      mask[di] = 239; mask[di + 1] = 68; mask[di + 2] = 68; mask[di + 3] = 180; // 红，半透明
    } else {
      mask[di + 3] = 0;
    }
  }
  const score = +(changed / total * 100).toFixed(2);
  let maskImage = null;
  if (opts.out) { fs.writeFileSync(opts.out, writePNG(mask, A.width, A.height)); maskImage = opts.out; }
  return {
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
  };
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
  const r = diff(a, b, {
    out,
    threshold: threshold == null ? undefined : parseInt(threshold, 10),
    ignore,
  });
  console.log(JSON.stringify(r, null, 2));
  process.exit(r.ok ? 0 : 2);
}

module.exports = { readPNG, writePNG, diff, applyIgnore };
