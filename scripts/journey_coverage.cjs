#!/usr/bin/env node
/**
 * B6（借鉴 Argos 状态旅程 / variantKey）：把弹框 / 错误 / 空 / 加载态与各响应式断点
 * 串成可计数旅程，用 variantKey 把同逻辑屏的各视口折叠成一条，覆盖度可核查。
 *
 * 这正是「只跑 11 项」漏洞的对症药：让「状态 × 断点」覆盖变成可计数的显式清单，
 * 而不是靠 agent 自觉。建议在 report.json 的 meta 里写入 statesCovered / statesTotal。
 *
 * 用法：
 *  node journey_coverage.cjs --journey journey.json --coverage coverage.json
 *
 * journey.json:
 *  {
 *    "states": [
 *      { "id": "default", "label": "默认态" },
 *      { "id": "modal-add", "label": "添加成员弹框", "trigger": "click .add-member" },
 *      { "id": "modal-import", "label": "批量导入弹框" },
 *      { "id": "error", "label": "表单错误态" },
 *      { "id": "empty", "label": "空态" },
 *      { "id": "loading", "label": "加载态" }
 *    ],
 *    "breakpoints": [1440, 1280, 768, 375],
 *    "variants": { "modal-add": ["1440", "768"] }   // 可选：仅这些断点需覆盖
 *  }
 *
 * coverage.json: { "covered": ["default@1440", "modal-add@1440", "modal-add@768", ...] }
 */
const fs = require('fs');

function arg(n, def) {
  const i = process.argv.indexOf('--' + n);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : def;
}

const journeyPath = arg('journey');
const coveragePath = arg('coverage');
if (!journeyPath || !coveragePath) { console.error('ERROR: --journey and --coverage required'); process.exit(1); }

const journey = JSON.parse(fs.readFileSync(journeyPath, 'utf8'));
const coverage = JSON.parse(fs.readFileSync(coveragePath, 'utf8'));
const coveredSet = new Set((coverage.covered || []).map(s => String(s)));

// 展开期望覆盖矩阵（state × breakpoint，尊重 variants 折叠）
const expected = [];
for (const st of (journey.states || [])) {
  let bps = journey.breakpoints || [];
  const variant = journey.variants && journey.variants[st.id];
  // 【审查修复·P2】variants 值按直觉写数字（[1440,768]）时 String(b) 匹配恒
  // false——该状态所有断点被过滤、expected 缺项、覆盖率虚高。两侧都归一为
  // 字符串再比较（文档示例是字符串 "1440"，数字笔误常见）。
  if (variant) bps = bps.filter(b => variant.map(String).includes(String(b)));
  for (const b of bps) expected.push(st.id + '@' + b);
}

const covered = expected.filter(e => coveredSet.has(e));
const missing = expected.filter(e => !coveredSet.has(e));
// 【审查修复·P2】expected 为空（journey 定义空/断点全被过滤）时此前恒
// rate=100 + fullCoverage=true——"没有可覆盖项"被报告成"全覆盖"，掩盖
// journey 配置错误。改为 0% 且 summary 点名，让空配置显式可见。
const rate = expected.length ? +(covered.length / expected.length * 100).toFixed(1) : 0;

// 状态级覆盖（任一断点覆盖即算该状态已覆盖）
const stateIds = (journey.states || []).map(s => s.id);
const stateCovered = stateIds.filter(id => expected.some(e => e.startsWith(id + '@') && coveredSet.has(e)));
const stateMissing = stateIds.filter(id => !stateCovered.includes(id));

const result = {
  expectedTotal: expected.length,
  coveredCount: covered.length,
  missingCount: missing.length,
  coverageRate: rate,
  // 【审查修复·P2】空矩阵不得判全覆盖（与上方 rate=0 同源）。
  fullCoverage: expected.length > 0 && missing.length === 0,
  missingSteps: missing,
  stateCoverage: { total: stateIds.length, covered: stateCovered.length, missing: stateMissing },
  summary: expected.length === 0 ? '期望覆盖矩阵为空（states/breakpoints 缺失或 variants 过滤掉了全部断点），请检查 journey.json'
    : (missing.length === 0 ? '状态旅程全覆盖' : ('缺失 ' + missing.length + ' 个 (状态×断点) 步骤：' + missing.join(', '))),
};

console.log(JSON.stringify(result, null, 2));
process.exit(0);
