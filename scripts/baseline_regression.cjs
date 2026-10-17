#!/usr/bin/env node
/**
 * 跨跑基线回归：按 (figmaKey, nodeId, pageUrl) 存指标快照，
 * 重跑时 diff "本次 vs 已确认基线"，标出新增回归（added）与已修复（fixed）。
 *
 * 基线纪律：
 *  - 默认只读基线。本次结果写入 baseline/runs/，不覆盖基线文件。
 *  - 首次运行建立的基线标记为 provisional（临时），需人工确认后转正。
 *  - 只有显式传 --update-baseline 才把本次提升为正式基线。
 *    这样"本轮页面本身就是错的"不会被固化成基准，从而避免把后续修复误报成新增回归。
 *
 * 用法：
 *  node baseline_regression.cjs --current report.json \
 *    [--figmaKey ... --nodeId ... --pageUrl ...] \
 *    [--baseline-dir ./parity-test/baseline] [--out regression.json] \
 *    [--update-baseline]
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

function arg(n, def) {
  const i = process.argv.indexOf('--' + n);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : def;
}

/** 从 report.json 抽取可比对的关键指标快照 */
function snapshot(report) {
  const meta = report.meta || {};
  const summary = report.summary || {};
  const cov = meta.coverage || {};
  // 扁平化各清单项的 verdict 计数
  const verdictCounts = {};
  const inc = (v) => { v && (verdictCounts[v] = (verdictCounts[v] || 0) + 1); };
  for (const s of (report.sections || [])) for (const it of (s.items || [])) inc(it.verdict);
  for (const v of (report.responsive && report.responsive.perViewport || [])) for (const iss of (v.issues || [])) inc(iss.verdict || 'fail');
  for (const d of (report.iconDiffs || [])) inc(d.verdict);
  const diffs = report.diffs || {};
  const diffCounts = {
    high: (diffs.high || []).length,
    medium: (diffs.medium || []).length,
    low: (diffs.low || []).length,
  };
  return {
    generatedAt: meta.generatedAt || '',
    figmaKey: meta.figmaKey || '',
    nodeId: meta.nodeId || '',
    pageUrl: meta.candidateUrl || meta.pageUrl || '',
    coverageRate: cov.coverageRate != null ? cov.coverageRate : null,
    fullCoverage: !!cov.fullCoverage,
    totalDiffs: diffCounts.high + diffCounts.medium + diffCounts.low,
    diffCounts,
    verdictCounts,
    summary,
    pendingChecks: (report.pendingChecks || []).length,
  };
}

// 【审查修复·P1】越高越好的指标：这些字段下降才是回归、上升是改善——
// 与 diff 数/未覆盖数（越低越好）方向相反。此前一律"cur<prev=fixed"，
// 覆盖率 0.9→0.5 被标"已修复"、pass 计数下降被藏进 fixed，added 清单
// 反而漏掉最典型的回归信号。
const HIGHER_IS_BETTER = new Set(['coverageRate', 'verdictCounts.pass']);

function classifyField(key, cur, prev) {
  if (prev == null) return 'new';
  if (cur === prev) return 'unchanged';
  if (typeof cur === 'number' && typeof prev === 'number') {
    const up = cur > prev;
    if (HIGHER_IS_BETTER.has(key)) return up ? 'fixed' : 'regressed';
    // 数值越低越好（diff 数、未覆盖）-> 减少=修复，增加=回归
    return up ? 'regressed' : 'fixed';
  }
  return cur > prev ? 'regressed' : 'fixed';
}

function compare(cur, prev) {
  const fields = [
    'totalDiffs', 'coverageRate', 'pendingChecks',
    'diffCounts.high', 'diffCounts.medium', 'diffCounts.low',
  ];
  const changes = [];
  for (const f of fields) {
    const cv = f.split('.').reduce((o, k) => (o == null ? o : o[k]), cur);
    const pv = f.split('.').reduce((o, k) => (o == null ? o : o[k]), prev);
    const cls = classifyField(f, cv, pv);
    if (cls !== 'unchanged' && cls !== 'new') {
      changes.push({ field: f, from: pv, to: cv, status: cls });
    }
  }
  // verdictCounts 维度差异
  const allKeys = new Set([...Object.keys(cur.verdictCounts || {}), ...Object.keys(prev.verdictCounts || {})]);
  for (const k of allKeys) {
    const cv = (cur.verdictCounts || {})[k] || 0;
    const pv = (prev.verdictCounts || {})[k] || 0;
    if (cv !== pv) changes.push({ field: 'verdictCounts.' + k, from: pv, to: cv,
      // 【审查修复·P1】pass 计数越高越好（与 HIGHER_IS_BETTER 同源）：
      // 此前 cv<pv 恒标 fixed——pass 下降（最典型回归信号）被藏进已修复清单。
      status: (k === 'pass' ? (cv > pv ? 'fixed' : 'regressed')
                            : (cv < pv ? 'fixed' : 'regressed')) });
  }
  const added = changes.filter(c => c.status === 'regressed');
  const fixed = changes.filter(c => c.status === 'fixed');
  return {
    key: cur._key,
    baselineCreated: false,
    baselinePromoted: false,
    baselineProvisional: !!prev._provisional,
    added, fixed,
    summary: added.length === 0 && fixed.length === 0 ? '相比基线无变化' : ('新增回归 ' + added.length + ' 项，已修复 ' + fixed.length + ' 项'),
  };
}

// ---- main ----
const currentPath = arg('current');
if (!currentPath) { console.error('ERROR: --current report.json required'); process.exit(1); }
const report = JSON.parse(fs.readFileSync(currentPath, 'utf8'));
const meta = report.meta || {};
const figKey = arg('figmaKey', meta.figmaKey || '');
const nodeId = arg('nodeId', meta.nodeId || '');
const pageUrl = arg('pageUrl', meta.candidateUrl || meta.pageUrl || '');
const baseDir = arg('baseline-dir', path.join(process.cwd(), 'parity-test', 'baseline'));
const outPath = arg('out', path.join(path.dirname(currentPath), 'regression.json'));
const shouldUpdate = process.argv.includes('--update-baseline');
const runLabel = arg('run-label', new Date().toISOString().replace(/[:.]/g, '-'));

const key = [figKey, nodeId, pageUrl].filter(Boolean).join('|');
const safeKey = crypto.createHash('md5').update(key).digest('hex').slice(0, 16);
const runsDir = path.join(baseDir, 'runs');
fs.mkdirSync(baseDir, { recursive: true });
fs.mkdirSync(runsDir, { recursive: true });
const baseFile = path.join(baseDir, safeKey + '.json');

const cur = Object.assign(snapshot(report), { _key: key, _run: runLabel, _provisional: false });

// 每次运行都留一份快照，供趋势与波动项分析使用，且不覆盖基线
const runFile = path.join(runsDir, safeKey + '.' + runLabel + '.json');
fs.writeFileSync(runFile, JSON.stringify(cur, null, 2));

let result;
if (!fs.existsSync(baseFile)) {
  const provisional = Object.assign({}, cur, { _provisional: true });
  fs.writeFileSync(baseFile, JSON.stringify(provisional, null, 2));
  result = {
    key, baselineCreated: true, baselinePromoted: false, baselineProvisional: true,
    runSnapshot: runFile, added: [], fixed: [],
    summary: '首次运行，已建立临时基线（provisional），确认该次结果可信后传 --update-baseline 转正；转正前不据此判定回归方向',
  };
} else {
  const prev = JSON.parse(fs.readFileSync(baseFile, 'utf8'));
  result = compare(cur, prev);
  result.runSnapshot = runFile;
  if (shouldUpdate) {
    fs.writeFileSync(baseFile, JSON.stringify(Object.assign({}, cur, { _promotedAt: new Date().toISOString() }), null, 2));
    result.baselinePromoted = true;
    result.summary += '；本次已提升为正式基线';
  } else if (prev._provisional) {
    result.summary += '；基线仍为 provisional，未自动提升';
  }
}

fs.writeFileSync(outPath, JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
process.exit(0);
