---
name: "figma-ui-parity"
description: "以 Figma 设计稿为基准，对本地或远程页面执行智能 UI 还原、响应式、交互可用性、可访问性、异常数据和视觉回归检查。自动生成元素级场景，双向盘点设计与页面元素，验证按钮及浮层真实行为，统一去重缺陷并输出 HTML、JSON、CSV 报告。含运行期观测（JS 异常 / 交互期网络失败 / 重复提交 / 元素遮挡）与组合场景（`--combo-depth`：加深异常数据与逐断点展开）及缺陷模式池。当用户要求 Figma 对比、UI 走查、视觉回归、响应式检查、设计还原度或尽可能发现页面 bug 时调用。"
version: 4.26.0
author: TestCase
agent_created: true
category: ui-testing
platforms: [windows, macos, linux]
---

# Figma UI Parity

## 目标与边界

把 Figma 设计稿和实际页面作为两个有证据的数据源，完成五类检查：对象是否对应、静态样式是否一致、交互是否生效、异常状态是否稳定、回归是否变化。每个结论必须标注 `verified`、`partial`、`inferred`、`pending` 或 `notRun`。不得凭截图猜测；不得自动填充账号密码；默认不得在未确认环境的情况下执行危险写操作；仅当用户在本次运行中明确选择“全部操作”并确认当前为隔离测试环境时，才允许按本策略执行全部 safe、caution、danger 操作。不得把 token 或 Cookie 原文写入日志、报告或对话。

不做：修改页面代码、替用户确认产品决策、把 Figma 不可比字段判为缺陷、把未执行伪装成通过。核心设计数据、权限或对象对应性无法确认时停止受影响阶段。

**不适用场景**（应直接说明而不是硬跑）：移动端原生 App 与小程序（无 DOM，提取手段不成立）、非 Figma 设计源且用户没有导出物、页面不可访问且无授权态。缺少设计稿时只能做页面 UI 走查，报告标题与结论**不得**写"还原度"。

## 术语：流程步骤与检查维度

- **流程步骤 1–9**：本文件定义的执行顺序（见「标准工作流」）。
- **检查维度 7.x**：稳定命名空间，权威定义在 `references/check-dimensions.md`，机器可读版在 `schemas/check-dimensions.json`。覆盖率按维度统计。

references 里的 `7.x` 一律指检查维度，不指流程步骤。

## 参考规则按需加载

正文只做路由。执行到对应阶段必须读取下列 references，禁止凭记忆跳过：

| 阶段 | 必读 reference |
|---|---|
| 维度定义与覆盖率口径 | `references/check-dimensions.md` |
| 工具与依赖、凭据落地 | `references/tooling.md`、`references/setup-guide.md` |
| 设计字段提取 | `references/figma-fields.md` |
| 页面提取 | `references/extraction.md` |
| 输入产出契约 | `references/scenario-contract.md` |
| 登录态 | `references/login-detect.md`、`references/headed-login-fallback.md` |
| 对象对应性 | `references/page-design-match-check.md` |
| 像素 diff | `references/visual-parity.md`、`references/diff-scoring.md`、`references/stabilization.md`、`references/ignore-regions.md` |
| 图标 | `references/icon-diff.md` |
| 响应式 | `references/responsive.md` |
| 行为、健壮性与资源偏好维度 | `references/bug-driven-checks.md`、`references/button-audit.md`、`references/aria-diff.md` |
| 状态覆盖 | `references/state-journey.md` |
| 运行期观测（异常/网络/重复提交/遮挡） | `references/runtime-observability.md` |
| 回归 | `references/baseline-regression.md` |
| 报告与门禁 | `references/report-templates.md`、`references/gates.md` |
| 脚本命令与执行顺序 | `references/script-orchestration.md` |
| 失败恢复 | `references/error-handling.md` |
| 机器可读契约与缺陷模式池 | `schemas/check-dimensions.json`、`schemas/scenario-coverage.schema.json`、`schemas/defect.schema.json`、`assets/defect_patterns.json` |

## 触发后的输入确认

必须由用户提供：

1. Figma URL（提取 `fileKey` 和 `node-id`；API 使用时把 `-` 转成 `:`）。
2. 页面 URL（本地或远程）。
3. 如有登录，提供已授权的 Cookie/storage state 文件路径或选择人工登录；不索取密码。
4. **交互安全策略（每次测试开始前必问）**：必须用 `AskUserQuestion` 让用户选择「全部操作」「安全操作」「写操作拦截」或「仅静态检查」。未获得本次明确选择前，不得执行任何点击、键盘输入、表单校验、路由往返或可能触发请求的交互；不得沿用上一次运行或历史对话中的选择。
5. 可选：目标断点、环境 URL、基线目录、重点流程、需要走查的角色列表。

安全策略选项与执行边界：

| 用户选择 | 允许执行 | 禁止或限制 |
|---|---|---|
| `全部操作` | 仅在用户明确确认当前为隔离/测试环境后，执行 safe、caution、danger 全部分级操作，包含真实写入、删除、清空、同步、支付、退款、解绑、下线等动作 | 必须在报告记录用户原始选择、`testEnvironmentConfirmed=true`、每个高风险动作的前后证据；若无法确认环境，拒绝启用本模式，不得用于生产环境 |
| `安全操作` | safe 分级操作：查询、筛选、展开、收起、分页、查看、取消、关闭、下载、复制；每次操作后还原页面 | caution/danger 操作不触发；在报告标注未执行原因 |
| `写操作拦截` | safe 操作真实执行；caution 操作必须在拦截所有非 GET/HEAD/OPTIONS 请求并 mock 或 abort 后执行，仅观察前端信号 | danger 操作永不点击；不得绕过拦截或真实落库 |
| `仅静态检查` | 截图、DOM/样式/ARIA 盘点、无副作用探测、视口与媒体模拟 | 不执行点击、键盘输入、提交、路由往返、下拉/浮层打开、表单校验 |

将用户的原始选择、解析后的模式、拦截策略与受影响的未执行维度写入 `run-manifest.json` 和报告。缺少任一必需 URL 时，用 `AskUserQuestion` 只询问缺失项，不猜历史地址。用户只提供部分输入时，按 `references/setup-guide.md` 的「最小可行跑法」说明能覆盖到哪一步、哪些维度必须记 `notRun`，不因缺料整体拒答。

## 环境路由

只有明确启动 UI parity 测试时才进入环境路由。启动信号满足其一即可：

- 用户明确说“开始/重新执行 UI parity、Figma 对照、视觉还原或 UI 走查”，或提出**响应式 / 断点适配 / 自适应**类检查诉求（如“看看这个页面的响应式有没有问题”“检查下各断点的适配”）；
- 同一轮输入同时提供 Figma URL 和页面 URL。

单纯咨询依赖、解释 Playwright/MCP、查看 Skill 或只提供单个 URL 时，不得执行环境检查、访问页面或询问安全策略（只说“响应式是什么”这类无检查意图的话题也不触发）。

正式启动必须先由编排层调用 `AskUserQuestion` 取得本轮安全策略，再调用启动门禁：

```bash
python scripts/start_test.py \
  --instruction "<用户原始指令>" \
  --figma-url "<Figma URL>" \
  --page-url "<页面 URL>" \
  --safety-policy <all|safe|mockWrites|staticOnly> \
  --user-safety-selection "<用户原始选择>" \
  [--test-environment-confirmed]
```

`start_test.py` 只在识别到正式测试启动后执行 `init_workdir.py` 与 `check_environment.py`，写入 `parity-test/run-manifest.json`；缺少安全策略或 `all` 未确认隔离测试环境时以非零状态阻断，不得开始页面交互。咨询类输入直接返回 `started=false`，不产生环境检查副作用。

`init_workdir.py` 负责建目录并把凭据相关忽略规则写进工作区 `.gitignore`（只追加缺失行）。`check_environment.py` 只输出脱敏状态——**其 8 项依赖检查硬编码在脚本内（`check_environment.py:27-52`），并不读取仓库根的 `skill-dependencies.json`**；改那份清单不会改变检查结果，要改检查项必须改脚本。另：脚本内 `VERSION` 与 SKILL.md 版本号各自维护，历史上出现过不同步。

- `ready`：直接执行。
- `partial`：核心流程继续，报告受影响能力。
- `needs_setup`：只提示本次缺少的必需依赖。
- `unavailable`：说明认证、权限、版本、额度或服务故障，给出降级和恢复路径。

依赖能力与降级：

| 能力 | 依赖 | 降级 | 停止条件 |
|---|---|---|---|
| 设计数据 | Figma MCP 或 REST + 已配置 token | 仅处理用户提供的导出 JSON/PNG | 没有可信设计数据 |
| 页面提取 | Playwright MCP 或受控 Playwright | 仅做静态文件检查，标记未验证 | 没有页面访问能力 |
| 像素 diff | visual-parity | 用 `diff_score.js` 做确定性差异量化 | 不得声称像素级通过 |
| 报告导出 | Python | 输出 JSON/HTML，表格走 `gen_excel_fallback.py` | 不得声称表格已生成 |
| 登录 | 用户提供 storage state/Cookie 或人工登录 | 公共页面继续 | 受保护页面无授权状态 |

## 标准工作流

### 1. 建立运行清单

创建 `run-manifest.json`，记录输入 URL（脱敏）、时间、版本、视口、依赖状态、执行阶段、脚本哈希和未运行原因。**必须额外记录** `safetyPolicy`（`all` / `safe` / `mockWrites` / `staticOnly`）、`userSafetySelection`、`writeInterception`（`none` / `mock` / `abort`）、`testEnvironmentConfirmed`（选择 `all` 时必须为 `true`）及由安全策略导致的未执行维度；报告从该清单读取并展示这些字段。路径相对当前 workspace：

```text
PARITY_WORK_DIR=./parity-test
REPORT_DIR=./parity-test/reports
BASELINE_DIR=./parity-test/baselines
AUTH_DIR=./parity-test/.auth
```

### 2. 设计侧建模

Figma URL 必须优先路由到已连接的 Figma MCP，调用设计数据接口获取 file/node 数据；禁止先用普通网页抓取替代设计数据。解析 `node-id` 时先读取节点类型、名称、尺寸和父级关系：若 URL 节点是 COMPONENT、INSTANCE、子 FRAME 或尺寸明显小于页面，不得直接当作页面设计稿；先对文件做浅层枚举（`depth=1/2`），收集 Page 下的顶层页面 FRAME，再按页面名称、URL 路径和页面指纹建立映射。只有确认节点是页面级 FRAME，或唯一映射到页面级 FRAME 后，才进入逐字段对照。文件响应过大时必须采用“浅层枚举 → 按页面 FRAME 分片读取”，不得退回单个子节点并判定设计稿缺失。只有在 MCP 不可用时，才可使用用户提供的导出 JSON/PNG，并将受影响阶段标记为 `partial` 或 `dataMissing`。按 `references/figma-fields.md` 判定字段可比性，用 `scripts/extract_design_fields.py` 把节点 dump 转成设计模型：坐标统一为相对 frame 原点；颜色、圆角、边框、阴影、渐变换算为 CSS 可比单位；`fontWeight` 由名称映射为数值；`lineHeight` / `letterSpacing` 的 `PERCENT` 换算成 px；多阴影保留顺序与内外类型不合并；文本以 `characters` 为准；`constraints` 保留用于多视口断言。

### 3. 页面盘点与对应性预检

登录态按 `references/login-detect.md` 多信号检测。若页面需要登录且没有有效 storage state，必须直接执行 `scripts/node/save_auth.cjs --url "<受保护页面>" --profile "<workdir>/parity-test/.vp_profile" --headed` 启动可见浏览器，等待用户手动登录；不得把无头 MCP 的登录页当作终点，也不得要求用户复制密码、验证码或 Cookie。登录成功后保存 `.auth/auth.storage.json`，再使用同一 profile 和认证目录执行提取。若有头脚本启动失败，记录明确缺失项并停止受保护页面阶段。用 `scripts/collect_page_inventory.js` 盘点页面资产（按钮、输入、图片、浮层、滚动容器、交互种类），**宽高同时为 0** 的元素不入库（`collect_page_inventory.js:18` 判据是 `width === 0 && height === 0`；单边为 0 的元素仍会入库），每个元素记录 `nth`。

再按 `references/page-design-match-check.md` 生成设计指纹与页面指纹：标题、路由、导航、区块、字段、表头、弹窗标题、关键按钮。设计稿存在多个顶层 Frame 时，必须先输出 Frame 清单，再依据名称和 URL 路径自动配对；例如“通讯录”↔`addressbook.aspx`、“管理员·管理”↔`qywxusermanage.aspx`、“成员·作答”↔`contactsanswer.aspx`、“其他设置”↔`addressbooksetting.aspx`。输出 `matched`、`suspected` 或 `mismatch`。仅当自动映射无法唯一确定时，才用 `AskUserQuestion` 请求选择；不得因为 URL 的 `node-id` 指向子组件就直接判定设计稿不足。`mismatch` 必须询问用户后才能继续；`suspected` 顶部警告；对象不匹配时不得产生正式缺陷结论。设计稿与页面尺寸不一致时，优先把浏览器调整到设计 Frame 的宽高做一比一对照，再补充用户指定的实际视口；不得在不同宽度下直接作页面级尺寸/位置结论。

### 4. 逐字段比对与双向盘点

用 `scripts/compare_fields.py` 比对设计模型与页面提取结果，配对顺序为：显式 mapping → 精确文本锚点 → 名称提示（文本节点只与带文本的页面项配对，避免与同名容器错配）。

- **坐标基准必须先归一**：设计坐标相对 frame，页面坐标相对文档。脚本按配对元素的中位偏移自动归一（或由 `--frame-origin` 显式给出），并在结果里输出 `positionBasis`。
- **可比性检查**：页面视口宽与设计稿宽比例偏差 > 2% 时，**该次比对的所有属性统一标记 `notComparable`**——`comparable` 是 `compare_fields.py` 的比对级全局参数，颜色、字体、行高、阴影、透明度等一并受影响，**不只是尺寸与位置**；必须写明原因，不得当成缺陷。
- **属性级容差**：颜色用 ΔE（≤3）、尺寸 ±1px、位置 ±2px、字距 ±0.5px、圆角 ±1px、阴影模糊 ±2px。容差内记 `withinTolerance`，不生成缺陷。
- **透明背景不参与比对**：`rgba(0,0,0,0)` 不是黑色，必须跳过，否则会把每个无背景元素误报为颜色不符。
- 输出 `unmatched.designOnly` 与 `unmatched.pageOnly`，作为双向盘点（7.23）输入。
- 按钮缺失判定必须采用双通道证据：先查页面按钮盘点，再查可见完整文本。设计按钮命中按钮盘点时记录 `matchedBy=buttonInventory`；仅命中完整文本时记录 `matchedBy=fullText` 并标记 `nonStandardEntry=true`；只有两个来源都未命中时才记录 `matchedBy=none` 并进入 `missingInPage`。**该双通道判定落地在 `scripts/node/run_button_audit.cjs`（`matchedBy=buttonInventory` 见 `:170`、`fullText`+`nonStandardEntry` 见 `:175`、`none`→`missingInPage` 见 `:177-179`），不在 `compare_fields.py`。**

`constraints` 断言用 `scripts/assert_constraints.py` 执行：LEFT/TOP 位置不变、RIGHT/BOTTOM 边距不变、CENTER 中心不变、SCALE 比例不变（±2%）、FIXED 宽度不变。

### 5. 场景生成与执行

用 `scripts/discover_scenarios.py` 生成元素级场景矩阵（契约见 `references/scenario-contract.md`）：

- 场景必须绑定到具体元素、动作、预期与断言，禁止只输出泛化状态列表。
- 覆盖：默认态、Hover、Focus、Disabled、Loading、空态、错误态、成功态、弹窗、下拉、Tooltip、滚动、刷新、路由往返、窄屏、长文本、多语言、密集数据、暗色模式、打印、接口异常、角色态。
- 每个输入框生成异常数据场景：空值、单字符、超长中文、超长英文、中英混排、数字符号、emoji、全角、多行、长链接、标签字符、极端数值。
- 页面多出的元素仍必须验证可用性，不得因设计稿未画而跳过。
- 元素级与数据级场景有数量上限，被截断时必须在报告里写明，不得静默丢弃。

静态探测用 `scripts/extra_checks.js`（只做无副作用探测，不点击不提交），其**实际覆盖的维度是 7.20 / 7.24 / 7.25 / 7.27 / 7.28 / 7.29 / 7.30 / 7.31**：图片比例与加载失败、暗色模式、多行截断、控件细节、焦点可见性、国际化、滚动 UX、加载残留。**7.26 打印视图、7.32 状态残留、7.33 接口异常、7.34 角色差异不在该脚本内**，须由场景驱动（`run_state_scenarios.cjs`）执行——不要把「7.24–7.34」整段默认为它已覆盖。

状态类场景（暗色模式 7.25、打印视图 7.26、状态残留 7.32、接口异常 7.33）由 `scripts/node/run_state_scenarios.cjs` 驱动执行：先用 `page.emulateMedia` 切换渲染模式或 `page.route` 拦载 XHR/fetch fulfill 500（请求不到服务端、零真实写），再用 `scripts/state_probes.js` 在切换后的状态里重新探测。产物为每个维度给出 `pass/fail/pending/notRun` 状态与 findings；`staticOnly` 策略下不做页面交互，相应维度填 `notRun` 并写明原因。判定口径（哪些记 confirmed、哪些记 pending）见 `references/bug-driven-checks.md` 对应维度节。

跨页用户旅程（7.39）由 `scripts/node/run_journeys.cjs` 驱动：从起始页实时提取同源候选链接（危险词、跨源、锚点、下载类、新标签页均被剔除，`isCandidateLink` 会给出跳过原因），BFS 有界点击走查，每步采集运行期观测并判定落地页缺陷（404/500、落地空白、链接无反应、返回中断、中途弹登录），判据与安全边界见 `references/journeys.md`。**已知留痕缺口：被剔除的链接是裸 `continue` 丢弃（`run_journeys.cjs:226-228`，`planVisits:131` 同），跳过原因没有落到产物里——报告体现不出"哪些链接因何未访问"。**

维度 7.35–7.38（运行期 JS 异常、交互期网络失败、重复提交、元素遮挡）用 `scripts/runtime_observability.js`：在交互前安装钩子、交互后采集，见 `references/runtime-observability.md`。仅当本轮做了交互并安装了钩子才算执行过，否则填 `notRun` 并写明原因。

场景数量与组合：`scripts/discover_scenarios.py` 默认按单点生成（`--combo-depth 1`）；`--combo-depth 2` 只加深**两类**组合：异常数据条数（`data_cases+3`）与逐断点展开（7.4 逐断点、异常输入 × 首尾断点，需 ≥2 个断点才生效）。另：`run_parity_pipeline.py` 当前不传递 `--combo-depth`，该参数只在手工调用 `discover_scenarios.py` 时生效。

**「state×viewport×异常数据」的说法不准确**：状态类场景里 7.25 暗色、7.26 打印、7.33 接口异常**无条件生成**（`discover_scenarios.py:214/218/221`），与 combo-depth 无关；**7.32 状态残留不是无条件**——仅当识别到 `tabs / table / pagination` 交互（`:226`）或缺陷池命中 `7.32`（`:230`）时才生成，页面无此类元素时该维度不出场景。元素级场景按风险排序（删除/写操作、无名称图标按钮优先）也**无条件执行**，`combo=1` 同样排序。

**缺陷模式池**（`--patterns assets/defect_patterns.json`）：历史高频翻车的维度即使被页面内容门槛挡住也会补出页面级场景（`source=pattern-deep`）、表单校验类高发时加深异常数据，产物 `patternFeedback` 写明加权依据；该模式只影响覆盖与深度，不自动生成断言。不传 `--patterns` 时**场景清单本身**与接入前逐条一致——产物里的 `patternFeedback` 字段恒在，未接入时 `applied=false` 并附说明，那是输出结构的差异、不是场景差异。

**管线默认已接入模式池**：`run_parity_pipeline.py` 现在默认把 `--patterns` 指向 `assets/defect_patterns.json`（`--no-patterns` 可关），并在 `generate_reports` 之后追加 `pattern_pool --merge` 阶段，把本轮缺陷按指纹并回池（幂等，无新模式不写盘）。因此**走管线时模式池加权默认生效**——池里现有 35 条 DP-* 模式，会按历史缺陷维度补场景（如 7.31 滚动 UX）。手工逐个调 `discover_scenarios.py` 仍是不传则不生效，两条路径的口径差异就在这。`--combo-depth` / `--roles` / `--breakpoints` 也可由管线透传。

元素级与数据级场景有数量上限，被截断时必须在报告写明。

**场景执行率（计划 vs 实际）**：覆盖率门禁统计的是「维度是否跑过」，**逐条场景有没有跑只能看 `scripts/scenario_coverage.py`**——把 `scenarios.json`（计划）与执行结果（显式 `--results` 文件，或从缺陷项的 `scenario` 字段 `--from-report` 自动回收）合成执行率，未执行项必须显式写明原因，`--enforce` 拦截"未写原因的未执行"与低于 `--min-rate` 的执行率，`--exempt-dimensions` 显式豁免并单列。产出形状见 `schemas/scenario-coverage.schema.json`，用法见 `references/scenario-contract.md` 第五节。

### 6. 六层检查

1. **像素层**：整页与区块 screenshot diff，按 `references/visual-parity.md`；截图前先跑 `scripts/stabilize.js`（`references/stabilization.md`）；差异量化用 `scripts/diff_score.js`（`references/diff-scoring.md`）。设计稿导出倍率与页面截图 `deviceScaleFactor` 应保持一致——**尺寸不等时 `diff_score.js:189-190` 直接返回 `size mismatch` 拒比**（CLI 侧以 `exit 2` 结束），既不缩放后硬比、也不标记 `notComparable`。因此倍率不一致的表现是"这次像素比对没跑成"，而不是"比出一大堆差异"。回归 diff 噪声偏高时可加 `--enhanced`（`run_parity_pipeline.py --enhanced-diff`）：抑制抗锯齿与孤立噪点，抑制量写进 `suppressed` 留痕、遮罩画淡黄；**该模式口径与基础模式不同，跨模式比基线前先确认基线同模式**。
2. **样式层**：逐字段比对结果按 `references/extraction.md` 与 `references/figma-fields.md` 复核；图标成对精确比对按 `references/icon-diff.md`。
3. **行为层**：按 `references/button-audit.md` 做三层判定（静态可见 / 可交互 / 结果生效）；弹层打开后必须补充盘点。落地脚本 `scripts/button_audit.js`、`scripts/node/run_button_audit.cjs`、`scripts/gen_button_report.cjs`。
4. **健壮性层**：响应式按 `references/responsive.md` 与 `assert_constraints.py`；溢出、遮挡、层级、键盘、焦点、ARIA 按 `references/aria-diff.md` 与 `references/bug-driven-checks.md`；长文本与异常数据按该文件的断言细则执行。
5. **运行期层**：交互前安装 `scripts/runtime_observability.js` 钩子、交互后采集——7.35 运行期 JS 异常、7.36 交互期网络失败、7.37 重复提交、7.38 元素遮挡，判据与安全边界见 `references/runtime-observability.md`。未安装钩子或本轮无交互时，相应维度填 `notRun` 并写明原因。
6. **回归层**：按 `references/baseline-regression.md` 与**已确认基线**比较，输出新增、已修复、持续、波动和无法比较项。未确认的临时基线只作参考，不据此判定方向。

### 7. 交互安全策略

分级细节与误报防线见 `references/button-audit.md`。本阶段只能执行第 0 步已取得的用户选择，不得默认启用任何交互：

- `all`：用户已明确确认当前为隔离测试环境；允许执行 safe、caution、danger 全部操作，包含真实写入、删除、清空、支付、退款、解绑和下线。每个 caution/danger 动作必须记录操作前状态、目标元素、请求/响应摘要、操作后状态及是否可恢复；若页面不是隔离测试环境，必须拒绝该模式并回到安全策略选择。
- `safe`：仅允许 safe 分级操作（查询、查看、展开、收起、分页、取消、下载、复制），真实点击后必须还原。
- `mockWrites`：允许 safe 分级操作；caution 操作必须先拦截所有非 GET/HEAD/OPTIONS 请求并 mock 或 abort，只观察前端反应。
- `staticOnly`：不执行任何交互，仅做静态可点击性、样式、DOM、ARIA、截图和无副作用探测。
- `danger`：在 `all` 且 `testEnvironmentConfirmed=true` 时允许点击和执行；必须保留操作前后证据并记录不可逆风险。其他策略下不点击，只做静态检查并标记人工或隔离测试环境验证。

若用户未选择，安全策略为 `unselected`，所有交互相关维度必须标记 `notRun:未获得本次安全策略授权`，不得以默认安全模式代替确认。选择 `all` 但未记录 `testEnvironmentConfirmed=true` 时，必须拒绝执行 caution/danger 操作并将其标记为 `notRun:未确认隔离测试环境`。命中测试须多点采样，记录 `selector + nth`，处理 dialog/下载/新页，点击后清理副作用。隐藏容器内尺寸为 0 的按钮记为 **`zero-size`**（`button_audit.js:76/100/154`，归入 `hidden` 列表，产物输出 `hidden` / `hiddenCount`；`notObservable` 一词当前不在产品代码里使用），重复列表按钮按组抽样并记录 `duplicateCount`。

### 8. 缺陷归一、去重与校验

每条缺陷必须携带维度号（7.x）、现象、设计值、实际值、复现步骤、页面定位、证据来源与验证状态，结构遵循 `schemas/defect.schema.json`：

```json
{
  "fingerprint": "page|scenario|element|dimension|viewport",
  "dimension": "7.1",
  "severity": "P0|P1|P2|P3",
  "confidence": 0.0,
  "status": "confirmed|pending|notRun|dataMissing",
  "symptom": "用户可观察到的现象",
  "expected": "设计或交互预期",
  "actual": "实际结果",
  "module": "保存按钮",
  "category": "7.1|color",
  "suggestion": "可执行的修复建议",
  "element": {"selector": "…", "nth": 0, "bbox": {"x":0,"y":0,"w":0,"h":0}, "anchor": "…", "frame": "main"},
  "designRef": {"nodeId": "…", "path": "…"},
  "evidence": [],
  "reproduction": [],
  "sources": []
}
```

- 同一 `fingerprint` 只保留一条，合并 `sources` 与 `evidence`；维度号与元素一致时，像素层、样式层、清单层的同一问题必须合并。
- 用 `scripts/normalize_evidence.py` 做归一，用 `scripts/validate_defects.py` 做结构校验；校验不通过不得出报告。
- 风险按影响范围、核心流程、稳定复现、差异程度、是否阻断操作排序。`pending`（待确认）与确定缺陷必须分离。

### 9. 覆盖率门禁、报告与交付

先汇维度结论，再过门禁，再出报告：

```bash
python scripts/assemble_report.py --report ./parity-test/report.json \
  --style-diffs ./parity-test/styleDiffs.json \
  --findings ./parity-test/findings.json \
  --state-scenarios ./parity-test/state_scenarios.json \
  --scenario-coverage ./parity-test/scenario_coverage.json --write
python scripts/validate_defects.py --report ./parity-test/report.json --strict
python scripts/ignore_regions.py --file ./parity-test/ignoredRegions.json --enforce
python scripts/coverage_gate.py --report ./parity-test/report.json --enforce --write
```

`assemble_report.py` 把各驱动产物（样式差异 / 探测发现 / 状态场景 / 旅程发现 / 场景执行率）按维度汇总成 `meta.checks`——**39 个维度一个都不能少**，否则 `coverage_gate.py` 会直接判「维度缺失」。它的边界纪律：**无证据的维度只能填 `notRun` + 原因，严禁推断 `pass`**（「没跑」和「跑了没发现问题」是两件事）；report 里已有的手写 checks 原样保留，人填的比机器猜的优先级高。产物路径按实际存在的传，缺的就不传（对应维度落到 `notRun`）。

`coverage_gate.py` 按 `schemas/check-dimensions.json` 计算覆盖率 = (`pass`+`fail`+`warn`+`pending`) / 维度总数。`notRun` 与 `dataMissing` 必须写明原因，否则脚本拒绝；`pending` 与 `notRun` 语义不得混用。覆盖率低于 70% 时报告顶部显示「非全量覆盖」，并在给用户的总结里说明未覆盖维度。

报告模板与字段见 `references/report-templates.md`，门禁细则见 `references/gates.md`。统一出口：

```bash
python scripts/generate_reports.py --input ./parity-test/report.json --outdir ./parity-test/reports
```

输出三件套：

- `report.html`：检查维度完成度、执行摘要、对象匹配与坐标基准、场景覆盖（**计划 vs 实际**：`scenario_coverage.py` 产出的执行率、未执行分布与豁免维度）、并排截图、差异热力图、样式分组差异、图标与图片差异、关键差异汇总、缺陷清单、待确认、回归对比、降级能力、diffScore 趋势、阈值与忽略项声明。
- `report.json`：机器可读完整结果，含 `meta.coverage` 与 `meta.defectValidation`。
- `defects.csv`：UTF-8-SIG、逗号分隔、严格 8 列（序号、等级、缺陷类型、功能模块、问题描述、解决方案、元素定位、备注(附图)）。问题描述为「现象 + 指标」同列双段。

交付前核对：对象匹配状态；每个维度有结论；每条缺陷有现象与元素定位；所有 `notRun`/`dataMissing` 有原因；无明文 token 或 Cookie；无危险操作；HTML/JSON/CSV 同源一致；回归结论基于已确认基线；阈值与生效忽略项已声明。交付前必须跑一次串链冒烟并全绿：

```bash
python scripts/smoke_chain.py
```

该冒烟用真实脚本产物端到端串联提取→比对→校验→归一→报告及各门禁。任何脚本的字段契约改动后都必须重跑，全绿才允许交付；失败即停止交付并修复。

**真实环境验证（关闭 E 维度"推断"标注）**：smoke_chain 用离线 fixture 验证契约，不代表真实增益。需要用真实 Figma token + 真实页面跑通一次完整链路后，按 `references/real-env-verification.md` 流程执行 `scripts/capture_real_env_evidence.py` 生成 `real-env-evidence.json`，作为 E4「显著增益（已查证）」证据。该步骤必须在用户真实环境执行，自动化改造过程不得持有或使用真实凭据。

## 容忍度与不可比项

- 普适容差（`scripts/compare_fields.py` 的容差表）与具体元素的忽略区叠加使用：先排除忽略元素，再对剩余元素应用容差。
- 浏览器抗锯齿、±1px 渲染舍入、字体渲染差异不直接判缺陷；但必须由容差表或忽略区**机械抑制**，不能只写在文档里。
- 忽略项必须带 `expiresAt` 或 `reviewedAt`，过期项不得进入报告；每次运行后列出本次生效的忽略项。
- 无可信页面对应物的字段（组件 ID、圆角平滑、原型动画、跨平台字体渲染）只能记 `pending`，禁止进入确定缺陷。
- 响应式约束、可访问性、真实点击属于必须验证项，不得列为不可比。
- 坐标基准未归一，或页面与设计稿宽度比例偏差 > 2% 时，**该次比对所有属性的结论**必须标 `notComparable` 并写明原因（不止位置与尺寸，颜色、字体、行高、阴影等同样受影响）。

## 失败与恢复

按 `references/error-handling.md` 处理：单个工具最多重试 2 次并记录错误；401/403 进入认证恢复；429 使用退避；token 中途失效按其恢复步骤执行。部分数据失败继续非受影响阶段并标注缺失。核心设计数据、页面权限、对象对应性或元素定位无法可靠取得时停止相关结论。报告只能声明实际完成的范围。

## 交付总结

对话中输出：总场景数与已执行/未执行数、覆盖率与未覆盖维度、缺陷数量、P0/P1 Top 项、新增/修复/持续回归、降级能力、三个报告路径、本次阈值与生效忽略项。不得只说"通过"，必须给出证据覆盖范围。
