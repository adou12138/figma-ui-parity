# 出报告前的两道硬门禁

本文件是**防呆机制**。起因：某次对比只跑了 11 个自编检查项、对 7.1–7.21 清单里的 10 项只字未提，却照样生成了名为"UI 一致性对比报告"的产物——**"做少了"不会报错，只会静默产出一份看起来完整的报告**，这比测不出问题更危险。

维度清单的权威定义在 `references/check-dimensions.md`（7.1–7.39），机器可读版在 `schemas/check-dimensions.json`。覆盖率由 `scripts/coverage_gate.py` 计算，**禁止手填**。

## 闸 A：清单完成度自检（不可跳过）

### 规则

1. **报告必须逐项输出维度表全部维度的结论**，一项都不能省略。未出现在报告里的维度按 `notRun` 计入，覆盖率随之下降。
2. 每项结论只能是以下六种之一，**语义严格区分**：

| 结论 | 含义 | 何时用 |
|---|---|---|
| `pass` | 已核对且一致 | 有数据支撑 |
| `fail` | 已核对且不一致 | 有数据支撑 |
| `warn` | 已核对，存在偏差但不确定是否缺陷 | 有数据支撑 |
| `pending` | **已执行**，但需人工视觉确认 | 自动无法判定（如颜色需取色器） |
| `notRun` | **根本没跑** | 没做该项检查 |
| `dataMissing` | **想跑但数据不足** | 如 rect 全 0 无法量尺寸 |

> ⚠️ **禁止把 `notRun` 写成 `pending`**。`pending` 是"做了但要人眼看"，`notRun` 是"压根没做"。混用会让覆盖率看起来虚高。

3. **`notRun` / `dataMissing` 必须写明原因**（如"未触发 hover 态""rect 全为 0 无法量取"）。
4. **`meta` 必须带 `coverage` 字段**：

```json
"coverage": {
  "total": 21,
  "executed": 14,        // pass+fail+warn+pending
  "notRun": 5,
  "dataMissing": 2,
  "coverageRate": 0.67,  // executed / total
  "fullCoverage": false
}
```

5. **阈值告警**：当 `(notRun + dataMissing) / total > 0.30`（即覆盖率 < 70%）时，报告**顶部必须显示红字警示**：

> ⚠️ **本报告非全量覆盖**：仅完成 14/21 项（覆盖率 67%），未覆盖项：7.4、7.6、7.19…。本报告不能作为"UI 无问题"的结论使用。

### 对账表模板（照抄进报告，逐项填）

ID 用 `references/check-dimensions.md` 的维度号；维度名以该表为准，下表只列常用项，**不得因为"表里没写"就跳过**。

| ID | 检查项 | 结论 | 说明/原因 |
|---|---|---|---|
| 7.1 | 静态样式检查清单 | | |
| 7.2 | 交互状态对比 | | |
| 7.3 | 图标与图片对比 | | |
| 7.4 | 响应式 / 多视口实测 | | |
| 7.5 | 图标成对精确比对 | | |
| 7.6 | 排列顺序比对 | | |
| 7.7 | 装饰元素（分隔线）比对 | | |
| 7.8 | 重复文案与文案一致性 | | |
| 7.9 | 免滚动可达性 | | |
| 7.10 | 跨环境对比（无多环境填 `notRun:无多环境URL`） | | |
| 7.11 | 缺陷记录携带现象与元素定位 | | |
| 7.12 | 待确认问题记录 | | |
| 7.13 | 复合元素内部对齐 | | |
| 7.14 | 弹框 / 浮层逐个走查 | | |
| 7.15 | 控件内容完整显示与多余文案 | | |
| 7.16 | 长内容布局与状态相关显隐 | | |
| 7.17 | 表单校验与错误态 | | |
| 7.18 | 浮层 / 下拉 / 弹框交互与层级 | | |
| 7.19 | 可访问性与键盘可用性 | | |
| 7.20 | 加载 / 空态 / 禁用态 | | |
| 7.21 | 长文本 / 多语言 / 密集数据适配 | | |
| 7.22 | 按钮可用性与点击生效 | | |
| 7.23 | 元素双向盘点 | | |
| 7.24–7.34 | 资源与用户偏好维度（见维度表与本文件对应章节） | | |
| 7.35–7.38 | 运行期观测（JS 异常 / 网络失败 / 重复提交 / 遮挡） | | |

### 覆盖率计算与门禁

```bash
python scripts/assemble_report.py --report ./parity-test/report.json --write   # 先汇维度结论
python scripts/coverage_gate.py --report ./parity-test/report.json --enforce --write
```

- **checks 段由 `assemble_report.py` 生产**：它把各驱动产物按维度汇总成 `meta.checks`，
  39 个维度一个都不能少。手工拼表既是重复劳动，也容易与驱动产物脱节。
- 覆盖率 = (`pass` + `fail` + `warn` + `pending`) / 维度总数；`notRun` 与 `dataMissing` 都不算完成。
- `notRun` / `dataMissing` 未写明原因 → 脚本返回非零码并列出问题项，**报告不得产出**。
- 出现非法状态值（如把 `notRun` 写进 `pending`）→ 直接拒绝。
- `--write` 会把 `meta.coverage` 写回报告，HTML 报告据此显示覆盖率横幅。
- 低于阈值（默认 70%）时，报告顶部必须显示「非全量覆盖」警示，并在给用户的总结里说明未覆盖哪些维度。

### 硬性要求

- 需要主动触发的维度（7.2 / 7.4 / 7.14 / 7.17–7.21 / 7.24–7.34 中标注"场景驱动"的项，以及 7.35–7.38 运行期观测）**必须真实触发**（hover、resize、打开弹框、触发校验、切主题、拦接口、安装运行期钩子）。若没触发就只能填 `notRun` 并说明，**不允许用静态数据蒙混填 `pass`**。
- 生成报告前先自检：若 `fullCoverage === false`，必须在给用户的总结里**主动说明覆盖了哪些、没覆盖哪些**，不得只报"通过 X 项"。

---

## 闸 C：数据质量闸（提取数据不合格不得出报告）

### 触发条件

提取结果出现以下任一情况，**先修数据，再继续**：

| 症状 | 判据 |
|---|---|
| 零尺寸元素过多 | `rect.w === 0 \|\| rect.h === 0` 的元素占比 **> 30%** |
| 元素数异常少 | 页面明显有内容，但提取到的容器 / 文本 **< 10 个** |
| 关键字段全空 | 所有元素的 `color` / `fontSize` / `backgroundColor` 均为空或默认值 |
| 脚本返回空 | 官方脚本返回 `count === 0` 或抛错 |

### 排查步骤（按顺序）

1. **等页面稳定**：`goto` 后 `waitForTimeout(4000+)`，或等 `networkidle`；SPA 需等数据请求完成。
2. **确认非隐藏态**：检查元素是否在 `display:none` / `visibility:hidden` 的容器内，或处于未激活的 tab。
3. **双路取尺寸**：`getBoundingClientRect()` 与 `offsetWidth/offsetHeight` 同时取，后者对未布局元素更稳。
4. **检查 iframe**：目标元素可能在 iframe 内，需 `frameLocator` 或切换 frame 再提取。
5. **分批滚动**：懒加载长列表需滚动触发渲染后再分批提取。
6. **过滤零尺寸**：官方 `extract_containers.js` 已内置 `if (rect.width === 0 || rect.height === 0) continue;`。**自写提取脚本必须同样过滤**，否则零尺寸元素会污染结果。

### 处置

- 排查后仍无法修复 → 该项填 `dataMissing` 并写明原因，**禁止**直接降级为 `pending`（"待视觉核对"）。
- 零尺寸占比高会直接废掉 7.1（尺寸间距）、7.13（对齐）、7.16（长内容布局）等项——这些必须如实标记为 `dataMissing`，不能假装测过。

---

## 闸 B：Node / playwright-core 执行官方脚本的路径

见 `scripts/node/run_official_extraction.cjs`。**在有头浏览器（用户手动登录）场景下，必须用它复用官方脚本，不要自己重写提取逻辑**——自己写的简化提取正是覆盖率崩塌的根源。

用法：

```bash
node scripts/node/run_official_extraction.cjs \
  --url "https://目标页" \
  --profile "./.vp_profile_devtest" \   # 持久化 profile（相对 workspace 根），可选
  --out   "./parity-test/extract" \
  --headed                                        # 有头，等待用户手动登录
  --responsive                                    # 额外跑多断点响应式
  --stabilize                                     # 截图前稳定化（B3，降低渲染抖动噪声）
```

产出：`containers.json` / `texts.json` / `icons.json` / `alignment.json` / `responsive.json`（可选）/ `page.json`（与 MCP 路径同一份 inventory 契约）/ `extraction_meta.json`（含数据质量校验结果）。

> **两条提取路径一致性**：node 兜底路径现已复用 `collect_page_inventory.js` 产出 `page.json`，与 MCP `browser_evaluate` 路径产出同构。可用 `scripts/verify_extraction_contract.py --mcp <mcp page.json> --node <node page.json>` 对比两份计数的漂移（阈值默认 0.3），防止两条路径字段漂移导致 `compare_fields.py` 行为不一致。任一份缺失或漂移超阈值 → 非零退出，相关维度标 `dataMissing`。
