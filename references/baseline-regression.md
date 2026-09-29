# B5 跨跑 baseline 回归（借鉴 Argos）

## 为什么需要

旧流程只做 Figma↔页面一次性比对；注释 7 提到"看看历史报告能否复用"——是复用不是 diff。同一批 wjx 页面会被反复测（addressbook / addressbooksetting …），但每次都从零开始，**无法知道"相比上次，哪里新坏了 / 哪里修好了"**。Argos 每次跑都对照选定 baseline 并据此决定是否卡合并——本 skill 取其"跨跑 diff"精神，但用本地文件实现（不起服务、不建平台）。

## 键与快照

按 **`(figmaKey, nodeId, pageUrl)`** 三元组做键（MD5 取前 16 位作文件名），在 `$WORK_DIR/baseline/<safeKey>.json` 存一份指标快照：

- `coverageRate` / `fullCoverage`
- `totalDiffs` 与 `diffCounts.{high,medium,low}`
- `verdictCounts`：各清单项 verdict（pass/fail/warn/...）计数
- `pendingChecks` 数量
- `summary` 关键计数

## 引擎

`scripts/baseline_regression.cjs`：

```bash
node scripts/baseline_regression.cjs \
  --current "./parity-test/reports/figma-vs-local-YYYYMMDD/report.json" \
  --baseline-dir "./parity-test/baseline" \
  --out "./parity-test/reports/figma-vs-local-YYYYMMDD/regression.json"
```

行为：

- **无 baseline 文件** → 仅创建 baseline，输出 `baselineCreated:true`，**不报错、不阻塞**（首次运行自动建基线）。
- **有 baseline** → 与本次 `report.json` 比对，输出 `added`（回归项）/ `fixed`（修复项）/ `summary`，并刷新 baseline 为本次。
- 比对维度：总 diff 数、覆盖率、高/中/低 diff 数、各 verdict 计数、待确认数。其中 diff 数、未覆盖数等"越低越好"的指标减少记为 `fixed`、增加记为 `regressed`。

## 集成到报告

- 步骤 9 生成报告后，自动跑一次 baseline 比对，结果写入 `regression.json` 并在 HTML 报告新增「跨跑回归」章节：
  - 新增回归（红色，优先跟进）
  - 已修复（绿色，确认验收）
  - 无变化（灰，稳定）
- 让用户每次重测同一页面时，一眼看到"自上次起的净变化"，而不是一份孤立的新报告。

## 与「复用历史报告」的关系

注释 7 的"复用"指少跑提取；B5 的"baseline"指对比结论。两者互补：B5 不替代 Figma↔页面的当次核对，只在多次运行间叠加一层"趋势"视角。
