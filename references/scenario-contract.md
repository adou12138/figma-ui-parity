# 场景契约（design / page / scenarios 三份结构）

场景生成的输入必须由提取脚本真实产出，禁止手写占位。三个文件的关系：

```text
Figma 节点 dump ──extract_design_fields.py──▶ design_model.json ─┐
真实页面 ──collect_page_inventory.js──▶ page.json ────────────────┼─▶ discover_scenarios.py ─▶ scenarios.json
比对结果 ──compare_fields.py──▶ styleDiffs.json ──────────────────┘
```

## 一、design_model.json（`scripts/extract_design_fields.py`）

顶层：`source` / `rootId` / `frame{w,h}` / `stats{nodes,textNodes,withFills}` / `tree` / `flat[]`。

`flat[]` 每个节点已换算为可比单位：

| 字段 | 含义 | 换算要求 |
|---|---|---|
| `rect{x,y,w,h}` | 相对 frame 原点的坐标与尺寸 | 已减去 frame 的 `absoluteBoundingBox` 原点 |
| `constraints{horizontal,vertical}` | 布局约束 | 必须转成多视口断言，见 `responsive.md` |
| `layout{itemSpacing,padding,primaryAxisAlign,counterAxisAlign}` | 自动布局 | `itemSpacing` 对应 CSS `gap` |
| `fills[]` | 颜色/渐变 | `color.css` 为 rgba；渐变带 `angle`（CSS 角度）与 `stops` |
| `strokes[]` | 描边 | 含 `align` 与盒模型说明，`INSIDE` 等价 `box-sizing:border-box` |
| `radius{uniform,corners,perCorner}` | 圆角 | 四角不同时必须用 `corners` |
| `effects[]` | 阴影列表 | 保留顺序，`INNER_SHADOW` 输出 `inset ...`，多阴影不合并 |
| `text{characters,fontFamily,fontWeight,fontSize,lineHeight,letterSpacing,textCase,...}` | 文本 | `fontWeight` 已由名称映射为数值；`lineHeight.px`、`letterSpacing.px` 已按 `PERCENT` 换算 |

## 二、page.json（`scripts/collect_page_inventory.js`，页面内执行）

```json
{
  "url": "https://目标页",
  "title": "页面标题",
  "viewport": {"w": 1440, "h": 900, "dpr": 2},
  "interactionKinds": ["dialog", "dropdown", "tabs", "table", "upload", "pagination", "toast", "tooltip"],
  "forms": 1,
  "buttons": [{"selector": "button.save-btn", "nth": 0, "text": "保存", "rect": {"x":0,"y":0,"w":96,"h":36}, "disabled": false, "inModal": false, "title": "", "href": ""}],
  "inputs": [{"selector": "#name", "nth": 0, "type": "text", "placeholder": "请输入名称", "autocomplete": "", "labelled": false, "required": false, "rect": {}}],
  "images": [{"selector": "img.hero", "nth": 0, "rect": {}, "natural": {"w":1920,"h":1080}, "objectFit": "fill", "loaded": true, "ratio": 1.0, "naturalRatio": 1.778}],
  "modals": [{"selector": "div.modal", "rect": {}, "visible": false, "display": "none"}],
  "emptyStateCandidates": [{"selector": "div.empty", "text": "暂无数据", "visible": false}],
  "scrollables": [{"selector": "div.scrollbox", "clientH": 118, "scrollH": 734, "overflowY": "auto"}],
  "stickyOrFixed": [{"selector": "div.footer-bar", "position": "fixed", "rect": {}, "bottom": 900}],
  "counts": {"buttons": 0, "inputs": 0, "images": 0, "overlays": 0, "scrollables": 0, "zeroSizeExcluded": 0}
}
```

硬性要求：

- 零尺寸元素不进 `buttons` / `inputs` / `images`（`rect.w === 0 && rect.h === 0` 直接跳过），否则会把隐藏容器内的元素误报为不可点击。
- `nth` 必须记录：同一选择器命中多个元素时，`nth` 是唯一定位依据，缺了会点错元素。
- 页面内脚本禁止出现反斜杠转义（正则用 `String.fromCharCode` 构造），避免 MCP 传参吃掉一层。

## 三、scenarios.json（`scripts/discover_scenarios.py`）

```json
{
  "version": "2.0",
  "page": "https://目标页",
  "inputStats": {"buttons": 0, "inputs": 0, "images": 0, "overlays": 0, "interactionKinds": [], "roles": []},
  "dimensions": ["7.1", "7.17"],
  "scenarios": [
    {
      "id": "S-0001",
      "name": "点击『保存』生效判定",
      "dimension": "7.22",
      "level": "element",
      "element": {"selector": "button.save-btn", "nth": 0, "anchor": "保存", "bbox": {"x":0,"y":0,"w":96,"h":36}},
      "action": {"type": "click"},
      "precondition": [],
      "expected": "点击后产生可观察结果（DOM/URL/请求/Toast/弹窗任一）",
      "assertions": ["命中测试 elementFromPoint 命中自身", "点击后至少一个生效信号变化"],
      "data": null,
      "safety": "caution",
      "source": "element-inventory",
      "viewport": null,
      "page": "https://目标页",
      "runner": null
    }
  ]
}
```

字段约束：

- `dimension` 必须取自 `schemas/check-dimensions.json`，用于覆盖率统计。
- `level=element` 的场景必须带 `element.selector`（设计侧独有元素可为空并用 `anchor` 说明）。
- `action.type` 取值：`none` / `click` / `hover` / `focus` / `input` / `keyboard` / `resize` / `navigate` / `route-back` / `refresh` / `network` / `theme` / `media` / `upload` / `role`。
- `runner`（可空）：该场景的**推荐执行驱动**（相对 `scripts/` 的路径，如 `node/run_state_scenarios.cjs`）。标注了 runner 的场景有对应的可执行脚本，不再依赖 agent 临场发挥；为 `null` 表示按通用步骤人工/agent 执行。状态类场景（theme / media / network / route-back）均由 `node/run_state_scenarios.cjs` 执行，其安全边界见该文件头注释与 `bug-driven-checks.md` 对应维度节。
- `safety` 必须按风险分级：`danger` 场景默认只允许静态检查；仅当本次 `run-manifest.json` 明确为 `safetyPolicy=all` 且 `testEnvironmentConfirmed=true` 时，才允许真实点击或执行，具体遵循 `button-audit.md`。
- 元素级场景上限由 `--max-elements` 控制，异常数据场景上限由 `--max-data-cases` 控制；被截断时必须在报告里写明，不得静默丢场景。

组合深度（`--combo-depth`）：

- `--combo-depth 1`（默认）：单点场景，输出与不放宽时一致。
- `--combo-depth 2`：只加深**两类**组合——异常数据条数（表单密集页即「有 `forms` 且输入 ≥3」时 `data_cases+3`）与逐断点展开（多视口展开成逐断点 `source=combo` 并带 `viewport`、高风险输入追加「异常数据 × 首尾断点」，需 ≥2 个断点才生效）。**它不引入状态类组合**：7.25 暗色、7.26 打印、7.33 接口异常是无条件生成的，与 combo-depth 无关。产物新增 `comboDepth` 与 `breakpoints` 两个顶层字段。
- 元素级场景一律**按风险排序后取用**（危险/写操作、无名称图标按钮、缺 label 的输入靠前），让有限的 `--max-elements` 预算先打高价值目标；这只改选择先后，不改上限、不增总数。
- `--breakpoints`（默认 `1440,1280,768,375`）控制组合用的断点集合。

## 四、缺失输入时的行为

| 缺失 | 后果 | 必须怎么做 |
|---|---|---|
| 无 `--page` | 只能生成页面级泛化场景 | 报告标注「元素级场景未生成」，并检查是否该先补页面盘点 |
| 无 `--design` | 无法做设计↔页面比对与双向盘点 | 相关维度填 `notRun` 并写明原因 |
| 无 `--pairs` | 双向盘点（7.23）退化 | 7.23 填 `notRun:未做元素配对` |
| 无 `--roles` | 角色态（7.34）不生成 | 7.34 填 `notRun:未提供角色` |

## 五、执行结果回填与执行率门禁

**为什么需要这一节**：`coverage_gate.py` 统计的是「维度是否 executed」——某维度被跑过一次，
该维度就算覆盖。但计划里最多有 300 条**场景**，生成的一大半场景没跑时报告完全看不出来，
覆盖数字因此虚高。**逐条场景是否真的跑了，只能看 `scenario_coverage.py` 的产出。**

### 回填两种方式（可同时用，显式优先）

```bash
# ① 显式结果文件：agent/驱动把每条场景的执行结论写下来
#    {"results": [{"scenarioId": "S-0007", "status": "pass"},
#                 {"scenarioId": "S-0012", "status": "notRun", "reason": "安全策略下 caution 场景不执行"}]}
python scripts/scenario_coverage.py --plan scenarios.json --results scenario_results.json --out scenario_coverage.json

# ② 从报告自动回收：缺陷项里带 scenario / scenarioId 字段的 ⇒ 该场景确实跑过
python scripts/scenario_coverage.py --plan scenarios.json --from-report report.json --out scenario_coverage.json

# 门禁：未执行且没写原因 → 失败；执行率低于下限 → 失败；豁免维度从分母剔除但单列
python scripts/scenario_coverage.py --plan scenarios.json --results scenario_results.json \
  --enforce --min-rate 0.6 --exempt-dimensions 7.25,7.33
```

### 纪律

- `status` 词表与 `coverage_gate.py` 严格一致：`pass/fail/warn/pending` = 已执行；`notRun/dataMissing` = 未执行，**原因必填**（`--enforce` 会拦截）；
- **豁免必须显式**：`--exempt-dimensions` 列出的维度不进分母也不进分子，但在产出的 `planned.exemptDimensions` 里单列可见——不许静默；
- 计划外的场景 ID（旧计划残留）只告警不阻塞门禁；
- **同一场景多条记录（重跑 / 多轮回填并进）**：按「显式优先 + 已执行优先」取状态——
  只要有一条 `pass/fail` 就算真跑过，不能因首条是 `notRun` 就判它没跑（首条写了 reason
  时还不进 `unexplained`，等于静默低估执行率）。多记录落进 `multipleRecords`
  （`scenarioIds` + 终态不一致的 `flakyScenarioIds`），不静默；
- **从报告隐式回收只认计划内 ID**：回收不上的（自由文本场景名、旧计划的 ID）会落进
  `unknownResults` 只告警，不会被误算成"已执行"或凭空制造覆盖率；
- `scenario_coverage.py --out` 的产物形状可直接放进 `report.json` 的 `scenarios` 段，
  由 `generate_reports.py` 渲染成报告的「场景覆盖」区块（键值表）；
- 形状定义见 `schemas/scenario-coverage.schema.json`。
