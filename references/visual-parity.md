# visual-parity 像素级与区块级对比（步骤 5-6 详细版）

本文件由 SKILL.md 步骤 5 / 6 下沉而来。

## 阶段三：对比分析（三层对比）

### 步骤 5：visual-parity 整页像素级对比（宏观）

#### 降级模式（visual-parity 不可用时）

如步骤 1.1 检测到 `mcp_visual-parity` 不可用，**跳过步骤 5-6**，仅使用 Playwright 提取的元素样式 + LLM 逐项对比。在报告中标注"未使用 visual-parity，缺少像素级对比数据"。

#### 5.1 visual-parity 登录态处理

**关键问题**：`mcp__playwright` 不支持 `persistentContextDir`，与 visual-parity 是独立浏览器实例。visual-parity 需要单独处理登录态。

**处理方案**：

1. 首次调用 visual-parity 时，使用 `persistentContextDir: "VP_PROFILE_DIR"`（默认 `./.workbuddy/.vp_chrome_profile`，相对当前工作目录）。
2. 调用 `compare_pages` 后检查 `softPageHealth` 结果：
   - 若检测到候选页被重定向到登录页 → 提示用户"visual-parity 需要单独登录，请在弹出的浏览器窗口中完成登录"。
   - 用户登录后，后续所有 visual-parity 调用复用同一个 `VP_PROFILE_DIR`，无需重复登录。
3. 如用户已在步骤 3.1 登录过，可尝试导出 cookies 到 VP_PROFILE_DIR（高级操作，非必需）。

#### 5.2 调用 compare_pages

使用 `mcp_visual-parity.compare_pages` 做整页像素级 + 样式级对比。

**关键参数配置**：

| 参数 | 值 | 说明 |
|------|-----|------|
| `referenceUrl` | `http://localhost:8765/figma_spec.png`（或包装 HTML） | 步骤 4.1 托管的 Figma 设计稿 |
| `candidateUrl` | 用户提供的本地/远程页面 URL | 如 `http://localhost:3000/xxx` |
| `viewport` | `{width: <设计稿宽度>, height: <设计稿高度>, deviceScaleFactor: 2}` | 从步骤 2 提取的设计稿尺寸 |
| `fullPage` | `true` | 截取整页 |
| `persistentContextDir` | `VP_PROFILE_DIR` | 复用 visual-parity 登录态 |
| `outputDir` | `REPORT_DIR\<run-name>` | 输出目录 |
| `name` | `figma-vs-local-<YYYYMMDD>` | 运行名称 |
| `threshold` | `0.1` | 像素差异阈值 |
| `maxDiffPercent` | `1` | 最大允许差异百分比 |
| `compareStyles` | `true` | 启用样式级 diff |
| `waitUntil` | `domcontentloaded` | 适配本地 HMR/websocket |
| `waitMs` | `2000` | 额外等待异步加载 |
| `softPageHealth` | `true` | 返回警告而非失败 |

**容忍度对接（acceptedDeviations）**：

```json
[
  {"selector": "*", "property": "x", "kind": "rect", "reason": "坐标偏移在 ±1px 内属浏览器渲染正常差异"},
  {"selector": "*", "property": "y", "kind": "rect", "reason": "坐标偏移在 ±1px 内属浏览器渲染正常差异"}
]
```

**输出解读**：
- `diffPercent`：像素差异百分比，<1% 视为基本一致
- `diffImage`：差异热力图，保存到 outputDir，用于报告插图
- `styleDiffs`：样式差异列表，每项含 selector、property、reference 值、candidate 值
- `status`：`pass` / `fail` / `warning`

## 两套阈值不是一回事（必须声明口径）

| 口径 | 归属 | 默认值 | 含义 |
|---|---|---|---|
| 像素噪声阈值 | `scripts/diff_score.js --threshold` | `16`（每通道 /255） | 单像素色差小于它就不算"变"，用于滤掉抗锯齿与压缩噪声 |
| 区域差异百分比 | `mcp_visual-parity` `maxDiffPercent` | `1`（%） | 整页或区块中"变了的像素占比"上限 |
| `threshold` 参数 | `mcp_visual-parity` | `0.1` | 该工具内部的敏感度参数，与上面两个都不同名同义 |

**禁止混用**：`node scripts/diff_score.js --threshold 1` 不会得到"1% 差异"，它只是把噪声门槛降到 1/255，结果是噪声全被算成差异。

**报告必须声明**：HTML 报告的「阈值与忽略项声明」章节要写出本次用的像素阈值、区域百分比、属性级容差表版本与生效忽略项，否则同一张图在两套口径下会得出相反结论。

## 截图倍率必须两边一致

- 设计稿按 `scale=2` 导出（见 `extraction.md`），页面截图必须同样用 `deviceScaleFactor: 2`。
- `diff_score.js` 在两边像素尺寸不一致时**不做缩放**，直接返回 `ok:false, error:'size mismatch'`——这是有意为之：缩放后比对会把整体错位算成无数局部差异。
- 尺寸不一致时正确做法是回到截图环节修正倍率或视口宽度，**不得**手工裁剪后硬比。

**容忍度对接（acceptedDeviations）**：

**错误处理**：
- `persistentContextDir` 无效导致登录态丢失 → `softPageHealth` 返回警告 → 提示用户在 visual-parity 浏览器中登录
- 参考 URL 不可访问 → 检查步骤 4.1 的静态服务器是否运行
- 超时 → 增大 `timeoutMs` 至 60000，或改用 `waitUntil: "domcontentloaded"`

### 步骤 6：visual-parity 区块级样式 diff（中观）

整页对比发现宏观差异后，对关键区块做精细样式 diff。

#### 6.1 发现页面区块（可选）

如不确定页面有哪些区块，先用 `discover_sections` 自动发现：

```
run_mcp:
  server_name: mcp_visual-parity
  tool_name: discover_sections
  args:
    referenceUrl: "http://localhost:8765/figma_spec.png"
    candidateUrl: "http://localhost:3000/xxx"
    viewport: {width: 390, height: 1436, deviceScaleFactor: 2}
    persistentContextDir: "d:\\TestCase\\.vp_chrome_profile"
```

#### 6.2 对关键区块逐一对比

对以下关键区块调用 `compare_section` 或批量调用 `compare_sections`：

| 区块类型 | 典型 selector | 对比重点 |
|----------|---------------|----------|
| 主按钮 | `button.primary-btn, .save-btn` | 背景色、圆角、尺寸、字号 |
| 表单输入框 | `input[type=text], select, textarea` | 边框、圆角、内边距 |
| 复选框/单选框 | `input[type=checkbox], input[type=radio]` | 尺寸、选中态颜色、圆角 |
| 卡片容器 | `.card, [class*="section"], [class*="block"]` | 背景色、内边距、圆角 |
| 标签/Tag | `.tag, [class*="label"], [class*="chip"]` | 背景色、边框、圆角、字号 |
| 图标 | `[class*="icon"], i, svg` | 尺寸、颜色、填充方式 |
| 导航/Tab | `.tab, [class*="nav"], [class*="tab"]` | 选中态样式、下划线、颜色 |

**批量对比示例**：

```
run_mcp:
  server_name: mcp_visual-parity
  tool_name: compare_sections
  args:
    referenceUrl: "http://localhost:8765/figma_spec.png"
    candidateUrl: "http://localhost:3000/xxx"
    sections:
      - {referenceSelector: ".save-btn", localSelector: "button.primary-btn", label: "保存按钮"}
      - {referenceSelector: ".checkbox", localSelector: "input[type=checkbox]", label: "复选框"}
      - {referenceSelector: ".card", localSelector: ".setting-block", label: "设置卡片"}
    viewport: {width: 390, height: 1436, deviceScaleFactor: 2}
    persistentContextDir: "d:\\TestCase\\.vp_chrome_profile"
    outputDir: "d:\\TestCase\\parity-test\\reports\\figma-vs-local-YYYYMMDD\\sections"
    compareStyles: true
```

#### 6.3 输出整合

- 每个 section 生成独立 crop 图和 styleDiff 列表，保存到 `outputDir/sections/<section-name>/`
- `styleDiffs` 含每个属性的 reference 值和 candidate 值，直接填入步骤 9 的报告表格
- 像素差异图作为报告插图
- **三层结果合并**：步骤 5 整页差异 + 步骤 6 区块差异 + 步骤 7 清单核对

#### 6.4 错误处理

| 错误情况 | 处理 |
|----------|------|
| selector 未命中 | 报告中标注"该区块在一侧不存在"，归入"缺失/新增" |
| 登录态失效 | 回退到步骤 5.1 的登录态处理 |
| 区块对比超时 | 跳过该区块，继续其他区块，报告中标注"对比超时" |
| 切图尺寸不一致 | 调整 viewport 或用步骤 4.1 的包装 HTML 对齐 |

