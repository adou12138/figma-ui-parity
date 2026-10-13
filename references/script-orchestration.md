# 确定性脚本一览、输入产出与执行顺序

`scripts/` 下每个脚本只负责一件事，`run_parity_pipeline.py` 负责按序串起来并记录每个阶段的实际状态。禁止凭记忆写命令，按本文件核对参数。

## 一、数据流总览

```text
Figma 文件/节点 dump ─ enumerate_page_frames ─▶ frame_map.json ─▶ extract_design_fields.py（按页面 Frame 分片） ─▶ design_model.json ─┐
真实页面        ─ collect_page_inventory.js ▶ page.json ─────────┼─▶ discover_scenarios.py ▶ scenarios.json
                 extract_containers.js 等   ▶ containers/texts/图标 ─┘        │
                                    compare_fields.py ▶ styleDiffs.json ─────┴─▶ normalize_evidence.py
                                    extra_checks.js   ▶ findings.json ─────────┘        │
                          runtime_observability.js ▶ findings.json（运行期）─────────────┘
                                                                                        ▼
                     coverage_gate.py ◀ report.json ◀ validate_defects.py ◀────────────────┘
                                                                                        │
                     baseline_regression.cjs ─▶ regression.json ────────────────────────┤
                                                                                        ▼
                                                              generate_reports.py ▶ report.html / report.json / defects.csv
```

## 二、统一入口

正式测试先经过启动门禁；环境检查和安全策略记录完成后，才进入确定性管线：

```bash
python scripts/start_test.py \
  --instruction "<原始测试指令>" \
  --figma-url "<Figma URL>" \
  --page-url "<页面 URL>" \
  --safety-policy <all|safe|mockWrites|staticOnly> \
  --user-safety-selection "<用户原始选择>" \
  [--test-environment-confirmed]
python scripts/run_parity_pipeline.py \
  --workdir ./parity-test \
  --page-url "<页面URL>" \
  --design-json ./parity-test/design_model.json \
  --page-json ./parity-test/page.json \
  --figma-png ./parity-test/shots/figma.png \
  --page-png ./parity-test/shots/page.png \
  --report ./parity-test/report.json \
  --outdir ./parity-test/reports
```

约定：

- 缺哪个输入就跳过对应阶段，并在 `pipeline-log.json` 里写 `notRun` + 原因，不伪造成功。
- 同时提供 `--design-json` 与 `--page-json` 时，管线自动串 `compare_fields` 与 `discover_scenarios`；`--report` 存在时先跑 `validate_defects` → `coverage_gate` → `ignore_regions`（存在时）门禁，再回归与出报告。
- 加 `--dry-run` 只打印将要执行的命令。
- 单个脚本失败不阻断其余阶段，但必须在报告里体现。

## 三、脚本清单（含输入产出）

| 脚本 | 输入 | 产出 | 说明 |
|---|---|---|---|
| `start_test.py` | 原始指令、Figma URL、页面 URL、安全策略 | `run-manifest.json`、环境状态 | 仅正式测试启动时运行；策略缺失或隔离环境未确认时阻断 |
| `init_workdir.py` | 工作区根目录 | `parity-test/` 目录树、`.gitignore` 规则 | 幂等；只追加缺失的忽略行 |
| `check_environment.py` | `skill-dependencies.json` | 就绪状态与缺失项 | 只输出脱敏状态；由启动门禁调用 |
| `enumerate_page_frames`（MCP 浅层读取，必要时按 Frame 分片） | Figma 文件/节点 JSON | `frame_map.json`（页面 Frame 清单与 URL 映射） | 识别页面级 FRAME，排除 COMPONENT/INSTANCE/局部子 Frame；文件过大时分片读取 |
| `extract_design_fields.py` | Figma 页面 Frame JSON | `design_model.json`（单位统一换算为 px） | 字重名称→数值、行高/字距 PERCENT→px、渐变角度、多阴影保留顺序；坐标相对选定 Frame 原点 |
| `collect_page_inventory.js` | 页面（`browser_evaluate`） | `page.json`（inventory 契约） | 零尺寸元素不入库；记录 `nth` |
| `compare_fields.py` | `design_model.json` + 页面提取 + 可选 mapping | `styleDiffs.json`（含 `defects`、`unmatched`） | 坐标基准归一（中位归一需 ≥3 对配对，偏移超阈值输出告警）；属性级容差表；文本/容器分开配对，文本子节点配对成功时其父容器记 `matchedIndirect` 不算 designOnly；透明背景与半透明填充不参与比对；rotation 非零的节点不比位置尺寸；缺陷直接带 `severity`/`confidence`/`reproduction`/`suggestion` |
| `assert_constraints.py` | `design_model.json` + 多视口测量 | `constraints.json` | LEFT/RIGHT/CENTER/SCALE/FIXED 断言数学，位置 ±2px、比例 ±2% |
| `extra_checks.js` | 页面（`browser_evaluate`） | `findings.json` | 7.24–7.31 无副作用探测：图片比例、暗色、多行截断、控件细节、焦点可见性、国际化、滚动 UX、加载残留 |
| `runtime_observability.js` | 页面（`browser_evaluate`，**两阶段**） | `findings.json`（运行期） | 7.35–7.38 运行期观测：先调用一次安装钩子、交互后再次调用采集；见 `runtime-observability.md` |
| `discover_scenarios.py` | `design_model.json` + `page.json` + 可选 `styleDiffs.json` | `scenarios.json` | 元素级场景 + 异常数据 + 角色态；`--roles`、`--max-elements`、`--max-data-cases`、`--combo-depth`、`--breakpoints`、`--patterns`（缺陷模式池反哺，见 `bug-driven-checks.md`） |
| `run_state_scenarios.cjs` | 页面 URL + 安全策略 | `state_scenarios.json` + 截图 | 7.25/7.26/7.32/7.33 状态场景驱动（emulateMedia 切暗色/打印、route 拦载 fulfill 500、hash 导航+返回）；`--only` 挑维度、`staticOnly` 短路不启动浏览器；见 `bug-driven-checks.md` |
| `run_journeys.cjs` | 页面 URL + 安全策略 | `journeys.json` + `journey_findings.json` | 7.39 多页用户旅程：BFS 有界点击站内链接；`--max-hops`/`--max-links-per-page`/`--max-visits`；同缺陷多路径到达按维度+属性+页面去重记 occurrences；见 `journeys.md` |
| `state_probes.js` | 页面（切换状态后 `browser_evaluate`） | `findings`（暗色/打印/接口异常后界面） | 状态切换后的页内探测；判定与采集分离（纯函数 node 可测）；全文无反斜杠 |
| `scenario_coverage.py` | `scenarios.json`（计划） + 可选执行结果 JSON / `report.json` | 场景执行率 JSON（可直接放进报告 payload 的 `scenarios` 段） | **计划 vs 实际**：`--results`/`--from-report` 回填执行痕迹，`--enforce` 拦截"未执行且未写原因"与低于 `--min-rate`，`--exempt-dimensions` 显式豁免并单列；见 `scenario-contract.md` |
| `pattern_pool.py` | 缺陷产物 JSON（`diffs`/`styleDiffs`/`defects`/`findings`/`violations`） | 池更新（`--merge`）/ 风险排序 Top（`--rank`） | 缺陷模式池 `assets/defect_patterns.json`；`--merge` 幂等、`--rank --top N` 出 Top 列表；见 `bug-driven-checks.md` |
| `normalize_evidence.py` | 各来源差异 JSON | 去重后的差异集合 | 按 `fingerprint` 合并，保留 `sources` 与 `evidence` |
| `stabilize.js` | 页面 URL | 稳定化后的页面会话 | 截图前必须跑 |
| `diff_score.js` | 两张 PNG | `diffScore` + 遮罩图 | `--threshold` 是像素噪声门槛，非百分比 |
| `extract_containers.js` / `extract_texts.js` / `extract_icons.js` / `order_divider_scroll_check.js` | 页面 | 容器/文本/图标/分隔线数据（脚本 A–D） | 见 `extraction.md`；注意 MCP 传参吃反斜杠 |
| `capture_aria.js` | 页面 | 可访问性树快照与 diff | 见 `aria-diff.md` |
| `alignment_modal_checks.js` | 页面 | 对齐与弹框走查结果 | 见 `bug-driven-checks.md` |
| `responsive_check.js` | 页面 | 多断点健康检查 | 布局断言部分交给 `assert_constraints.py` |
| `button_audit.js` / `node/run_button_audit.cjs` | 页面 | 按钮可用性与双向盘点 | 见 `button-audit.md`；默认 caution 拦写请求、danger 不点击；`all + testEnvironmentConfirmed=true` 时按授权执行 caution/danger |
| `extract_design_buttons.cjs` | 设计节点 | 设计侧按钮清单 | 双向盘点输入 |
| `gen_button_report.cjs` | 按钮审计目录 | 按钮报告 | `--dir` 必填 |
| `journey_coverage.cjs` | `journey.json` + `coverage.json` | 状态×断点覆盖率 | 与维度覆盖率是两套口径 |
| `coverage_gate.py` | `report.json` + `schemas/check-dimensions.json` | `meta.coverage` | 覆盖率与 70% 门禁；未写原因的 `notRun`/`dataMissing` 直接拒绝 |
| `validate_defects.py` | `report.json` + `schemas/defect.schema.json` | 校验结论 | 缺 `symptom`/`element` 即失败；`--strict` 还要求证据与复现非空 |
| `ignore_regions.py` | `ignoredRegions.json` | 生效/过期/宽泛/字段缺失清单 | 有 `--enforce` 时过期、字段缺失或宽泛/缺到期信息均非零码 |
| `baseline_regression.cjs` | `report.json` | `regression.json` | 默认只读基线；`--update-baseline` 才提升；每次运行留 `baseline/runs/` 快照 |
| `generate_reports.py` | 汇总后的 `report.json` | `report.html` / `report.json` / `defects.csv` | 15 个区块，CSV 严格 8 列；上游只带 `severityHint` 时兜底映射为 `severity` |
| `smoke_chain.py` | 内置 fixture | 串链冒烟结论（exit 0/1） | 用真实脚本产物端到端串联 extract→compare→validate→normalize→reports 及各门禁；改任何脚本字段契约后必须先跑它，全绿才允许交付 |
| `gen_excel_fallback.py` | 缺陷列表 | 无 `openpyxl` 时的表格兜底 | 见脚本头部说明 |

## 四、推荐执行顺序

```text
init_workdir            → 目录与忽略规则
check_environment       → 决定哪些阶段能跑
enumerate_page_frames   → 文件浅层枚举、页面 Frame 清单与 URL 映射
extract_design_fields   → 按页面 Frame 分片生成设计侧模型（含单位换算）
collect_page_inventory  → 页面资产盘点
compare_fields          → 设计↔页面逐字段比对 + 双向盘点
assert_constraints      → constraints 多视口断言
extra_checks            → 资源与偏好维度探测
runtime_observability   → 运行期观测（交互前安装钩子、交互后采集）
discover_scenarios      → 元素级场景矩阵（--combo-depth 组合）
stabilize               → 页面稳定化（截图前）
extract_* / capture_aria→ 样式与可访问性提取
diff_score              → 像素差异与遮罩
button_audit            → 按钮可用性与点击生效
gen_button_report       → 按钮结果落盘
journey_coverage        → 状态旅程覆盖率
normalize_evidence      → 缺陷归一与去重
pattern_pool            → 缺陷模式池累积 + 风险排序 Top（可选）
validate_defects        → 缺陷结构校验（不通过不得出报告）
coverage_gate           → 维度覆盖率与门禁
ignore_regions          → 忽略区到期审计
baseline_regression     → 与已确认基线对比
generate_reports        → HTML / JSON / CSV
smoke_chain             → 交付前串链冒烟（全绿才交付）
```

## 五、报告一致性要求

`generate_reports.py` 输出的 HTML、JSON、CSV 必须同源：

- 三者缺陷条数一致；HTML 摘要的 `defectTotal` 与 JSON 一致；CSV 严格 8 列且只含缺陷、不含忽略项与被忽略变更。
- 覆盖率必须来自 `coverage_gate.py` 的 `meta.coverage`，禁止手填。
- HTML 的「阈值与忽略项声明」章节必须写出本次像素阈值、区域百分比、容差表与生效忽略项。
- 任一不一致必须回到 `normalize_evidence.py` 重跑，不得手工改报告文件。
