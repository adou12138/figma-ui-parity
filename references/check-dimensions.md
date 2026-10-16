# 检查维度编号表（7.x 稳定命名空间）

**正文流程步骤是 1–9，本表的 7.x 是检查维度编号，两者正交。** references 里出现的 `7.x` 一律指向本表，不再指向正文步骤。机器可读版本在 `schemas/check-dimensions.json`，`scripts/coverage_gate.py` 按它计算覆盖率。

## 一、为什么需要这张表

历史引用里 `7.1–7.23` 被写成「步骤 7.x」，正文压缩重构后步骤只剩 1–9，导致所有对账表、Excel 类型映射表都定位不到。解决办法不是重编号正文，而是把 7.x 升格为**稳定的维度命名空间**：维度只增不改，正文步骤可以自由重构。

## 二、维度总表

| ID | 维度 | 承载文档 | 自动化 |
|---|---|---|---|
| 7.1 | 静态样式检查清单（尺寸/间距/排版/视觉/内容适配） | `extraction.md`、`figma-fields.md` | `compare_fields.py` |
| 7.2 | 交互状态对比（hover / active / disabled） | `extraction.md` | 部分 |
| 7.3 | 图标与图片对比（区块级） | `extraction.md` | 部分 |
| 7.4 | 响应式 / 多视口实测（含 constraints 断言） | `responsive.md` | `responsive_check.js` |
| 7.5 | 图标成对精确比对 | `icon-diff.md` | `extract_icons.js` |
| 7.6 | 排列顺序比对 | `extraction.md` | `order_divider_scroll_check.js` |
| 7.7 | 装饰元素（分隔线）比对 | `extraction.md` | `order_divider_scroll_check.js` |
| 7.8 | 重复文案与文案一致性 | `extraction.md` | `compare_fields.py` |
| 7.9 | 免滚动可达性 | `extraction.md` | `order_divider_scroll_check.js` |
| 7.10 | 跨环境对比（无多环境时 `notRun`） | `bug-driven-checks.md` | 无 |
| 7.11 | 缺陷记录携带现象与元素定位 | `report-templates.md` | `validate_defects.py` |
| 7.12 | 待确认问题记录 | `report-templates.md` | 部分 |
| 7.13 | 复合元素内部对齐 | `bug-driven-checks.md` | `alignment_modal_checks.js` |
| 7.14 | 弹框 / 浮层逐个走查 | `bug-driven-checks.md` | `alignment_modal_checks.js` |
| 7.15 | 控件内容完整显示与多余文案 | `bug-driven-checks.md` | 部分 |
| 7.16 | 长内容布局与状态相关显隐 | `bug-driven-checks.md` | 部分 |
| 7.17 | 表单校验与错误态 | `bug-driven-checks.md` | `discover_scenarios.py` |
| 7.18 | 浮层 / 下拉 / 弹框交互与层级 | `button-audit.md` | 部分 |
| 7.19 | 可访问性与键盘可用性 | `aria-diff.md` | `capture_aria.js` |
| 7.20 | 加载 / 空态 / 禁用态 | `state-journey.md` | `discover_scenarios.py` |
| 7.21 | 长文本 / 多语言 / 密集数据适配 | `bug-driven-checks.md` | `discover_scenarios.py` |
| 7.22 | 按钮可用性与点击生效 | `button-audit.md` | `run_button_audit.cjs` |
| 7.23 | 元素双向盘点（设计稿有页面无 / 页面有设计稿无） | `button-audit.md` | `compare_fields.py` |
| 7.24 | 图片与插画适配（比例失真 / 裁剪 / 加载失败） | `bug-driven-checks.md` | `extra_checks.js` |
| 7.25 | 暗色模式与主题切换 | `bug-driven-checks.md` | `extra_checks.js` |
| 7.26 | 打印与导出视图 | `bug-driven-checks.md` | `run_state_scenarios.cjs` |
| 7.27 | 多行文本截断与省略 | `bug-driven-checks.md` | `extra_checks.js` |
| 7.28 | 表单控件细节（placeholder / caret / autocomplete） | `bug-driven-checks.md` | `extra_checks.js` |
| 7.29 | 焦点可见性与键盘细节 | `bug-driven-checks.md` | `extra_checks.js` |
| 7.30 | 国际化细节（RTL / emoji / 全角半角） | `bug-driven-checks.md` | `extra_checks.js` |
| 7.31 | 滚动 UX（滚动条 / 固定底栏 / sticky / 滚动锁定） | `bug-driven-checks.md` | `extra_checks.js` |
| 7.32 | 页面级状态残留（SPA 路由 / 多标签页 / 返回刷新） | `bug-driven-checks.md` | `discover_scenarios.py`（**需识别到 tabs / table / pagination，或缺陷池命中 7.32**；两者都不满足时该维度无场景，应填 `notRun:页面无路由类元素`，**不是漏跑**） |
| 7.33 | 接口异常与慢网络下的界面 | `bug-driven-checks.md` | `run_state_scenarios.cjs` |
| 7.34 | 角色与权限态视图差异 | `bug-driven-checks.md` | 无 |
| 7.35 | 运行期 JS 异常（console.error / onerror / unhandledrejection） | `runtime-observability.md` | `runtime_observability.js` |
| 7.36 | 交互期网络失败（fetch/XHR 非 2xx） | `runtime-observability.md` | `runtime_observability.js` |
| 7.37 | 重复请求 / 重复提交 | `runtime-observability.md` | `runtime_observability.js` |
| 7.38 | 可交互元素遮挡（点击落不到） | `runtime-observability.md` | `runtime_observability.js` |
| 7.39 | 多页用户旅程（跨页导航：404/500、落地空白、返回中断、中途弹登录） | `journeys.md` | `run_journeys.cjs` |

## 三、使用规则

1. 报告必须逐项输出本表全部维度的结论，状态只能是 `pass` / `fail` / `warn` / `pending` / `notRun` / `dataMissing`。
2. 覆盖率 = (`pass+fail+warn+pending`) / 维度总数，由 `scripts/coverage_gate.py` 计算，禁止手填。
3. 新增能力时给新维度分配**新编号**（当前下一个是 7.40），不得复用或改写已发布编号的含义。
4. 缺陷记录里的 `dimension` 字段必须填本表 ID，跨层（像素层 / 样式层 / 清单层）同维度同元素才能正确合并去重。
