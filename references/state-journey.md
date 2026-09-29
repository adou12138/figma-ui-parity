# B6 状态旅程 / variantKey（借鉴 Argos）

## 为什么需要

旧流程手工走 7.14 弹框 / 7.17 错误态 / 7.20 空态，但彼此割裂；7.4 各断点是独立行。曾出现"只跑了 11 个自编检查项、对 7.1–7.21 中 10 项只字未提"的事故（闸 A 已防"做少了"静默出报告）。但**状态 × 断点的覆盖仍是隐式的**——agent 凭自觉决定跑哪些。Argos 用 `capture.index` 把截图串成 journey、用 `variantKey` 把同逻辑屏的各视口折叠成一条，本 skill 取其"显式、可计数"精神。

## 结构

`$WORK_DIR/journey.json`（一次测试前定义，描述"这次要覆盖哪些状态 × 哪些断点"）：

```json
{
  "states": [
    { "id": "default", "label": "默认态" },
    { "id": "modal-add", "label": "添加成员弹框", "trigger": "click .add-member" },
    { "id": "modal-import", "label": "批量导入弹框" },
    { "id": "error", "label": "表单错误态", "trigger": "submit empty form" },
    { "id": "empty", "label": "空态", "trigger": "clear data" },
    { "id": "loading", "label": "加载态" }
  ],
  "breakpoints": [1440, 1280, 768, 375],
  "variants": { "modal-add": ["1440", "768"] }
}
```

- `states`：本次要覆盖的交互/数据状态（含触发方式 `trigger`）。
- `breakpoints`：响应式断点（含设计稿原始宽度基准）。
- `variants`：**variantKey 折叠**——某状态只需在指定断点覆盖（如弹框只验桌面+窄屏），其余断点自动视为已覆盖（同逻辑屏）。

## 引擎

`scripts/journey_coverage.cjs`：

```bash
# 测试完成后，把"实际覆盖到的 (state@breakpoint)"写入 coverage.json
echo '{ "covered": ["default@1440","modal-add@1440","modal-add@768","error@1440"] }' > coverage.json

node scripts/journey_coverage.cjs --journey journey.json --coverage coverage.json
# 输出：{ expectedTotal, coveredCount, missingCount, coverageRate, missingSteps, stateCoverage, summary }
```

- 展开矩阵 `state × breakpoint`（尊重 `variants` 折叠），与 `covered` 比对。
- `missingSteps` 列出未覆盖的 (状态×断点)，`coverageRate` 量化。
- `stateCoverage` 给出"状态级"覆盖（任一断点覆盖即算该状态已覆盖）。

## 集成到报告

- 建议把 `journey.json` 作为测试计划的一部分，步骤 3.5 之后、步骤 4 之前定义。
- 测试过程中，每覆盖一个 (state@breakpoint) 就追加进 `coverage.json`。
- 步骤 8.5 闸 A 的 `coverage` 之外，额外在 `meta` 写入 `statesCovered` / `statesTotal` / `journeyCoverageRate`；HTML 报告「覆盖度」章节展示 missingSteps，让"只跑了 11 项"无处藏身——覆盖是**显式计数**，不是自觉。
- 与闸 A 互补：闸 A 保证"7.1–7.21 都给了结论"；B6 保证"状态 × 断点都跑到了"。
