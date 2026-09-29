# 报告模板与格式定义（步骤 9 详细版）

本文件由 SKILL.md 步骤 9.1 / 9.2 / 9.3 与报告要求下沉而来。

#### 9.1 HTML 报告（含并排截图）

文件：`report.html`

**报告结构**：

```html
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>UI 一致性对比报告</title>
  <style>
    :root { --bg: #0b0d12; --panel: #151821; --muted: #9aa4b2; --text: #e8ecf3; --line: #232936; --good: #22c55e; --bad: #ef4444; --warn: #f59e0b; --accent: #60a5fa; }
    body { margin: 0; padding: 32px; background: var(--bg); color: var(--text); font: 14px/1.6 "PingFang SC", "Microsoft YaHei", sans-serif; }
    .summary { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 16px 0; }
    .stat { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 14px; }
    table { width: 100%; border-collapse: collapse; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }
    th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
    .ok { color: var(--good); font-weight: 700; }
    .bad { color: var(--bad); font-weight: 700; }
    .warn { color: var(--warn); font-weight: 700; }
    .screenshot-compare { display: flex; gap: 16px; margin: 16px 0; }
    .screenshot-compare img { width: 48%; border: 1px solid var(--line); border-radius: 8px; }
    .diff-image { width: 100%; border: 1px solid var(--bad); border-radius: 8px; margin: 8px 0; }
  </style>
</head>
<body>
  <h1>UI 一致性对比报告 - Figma 设计稿 vs 本地页面</h1>
  <p>参考: &lt;Figma URL&gt; · 候选: &lt;本地 URL&gt; · 生成日期: YYYY-MM-DD</p>

  <!-- 概览统计 -->
  <div class="summary">
    <div class="stat ok"><div class="num">N</div>一致项</div>
    <div class="stat bad"><div class="num">N</div>差异项</div>
    <div class="stat warn"><div class="num">N</div>缺失/新增</div>
    <div class="stat"><div class="num">N</div>总对比项</div>
  </div>

  <!-- 并排截图对比 -->
  <h2>〇、并排截图对比</h2>
  <div class="screenshot-compare">
    <div>
      <h3>Figma 设计稿</h3>
      <img src="figma_spec.png" alt="Figma 设计稿">
    </div>
    <div>
      <h3>本地页面</h3>
      <img src="actual_page.png" alt="本地页面">
    </div>
  </div>
  <h3>像素差异热力图</h3>
  <img class="diff-image" src="diff.png" alt="差异热力图">

  <!-- 各项对比表格 -->
  <h2>一、尺寸与间距</h2>
  <table>
    <thead><tr><th>元素</th><th>Figma</th><th>本地</th><th>结论</th></tr></thead>
    <tbody><tr><td>...</td><td>...</td><td>...</td><td class="ok">一致</td></tr></tbody>
  </table>

  <h2>二、排版样式</h2>
  <!-- 字体、字号、字重、行高、颜色对比表 -->

  <h2>三、视觉样式</h2>
  <!-- 背景色、边框、圆角、阴影对比表 -->

  <h2>四、交互状态</h2>
  <!-- Hover/Active/Disabled 样式变化对比表 -->

  <h2>五、内容适配与文案核对</h2>
  <!-- 文本溢出、换行规则、空状态、文案内容对比 -->

  <h2>六、图标与图片</h2>
  <!-- 图标尺寸、裁剪方式、颜色、SVG path 对比 -->

  <h2>七、关键差异汇总</h2>
  <!-- 每条先写「现象」、再列「指标」：<li>两张卡片右宽左窄、下边框横线不在同一水平线上（设计等宽 592:592，实际 426:758，底边 545 vs 555）</li> -->
  <div>
    <h3>高优先级差异（建议修复）</h3>
    <ul>...</ul>
  </div>
  <div>
    <h3>中优先级差异</h3>
    <ul>...</ul>
  </div>
  <div>
    <h3>低优先级差异（可忽略）</h3>
    <ul>...</ul>
  </div>

  <h2>八、修复建议</h2>
  <!-- 针对高/中优先级差异给出具体的 CSS 修复建议 -->

  <h2>九、待确认问题（需视觉核对 / 无法自动判定项）</h2>
  <table>
    <thead><tr><th>待确认项</th><th>类别</th><th>确认位置</th><th>页面元素</th><th>设计参考</th><th>确认建议</th></tr></thead>
    <tbody>
      <tr>
        <td>修改名称图标</td>
        <td>图标形状(异构需视觉核对)</td>
        <td>设计稿 PencilIcon 帧 ↔ 页面 i.comIcon @ (120,88,16,16) 修改名称图标</td>
        <td>i.comIcon（图标字体 font:e60a）</td>
        <td>Card / App / Button / PencilIcon</td>
        <td>对照设计稿实物确认图标语义是否一致</td>
      </tr>
      <!-- 每条待确认问题：确认位置 + 页面元素 必须明确，便于人工回查页面核实 -->
    </tbody>
  </table>
</body>
</html>
```

#### 9.2 JSON 结构化报告（便于程序化处理）

文件：`report.json`

> **缺陷记录的「元素定位」`element` 对象（所有缺陷数组通用）**：`diffs` / `iconDiffs` / `sections[].items` / `responsive.perViewport[].issues` / `suggestions` 每一条都必须带 `element`，结构为 `{ "selector": <可被 document.querySelector 唯一命中的 CSS 选择器>, "bbox": { "x","y","w","h" } (页面坐标，含滚动偏移), "anchor": <人类可读锚定文本>, "frame": "main"(可选) }`。`selector` 优先 `#id` / `[data-component]` / 稳定 class；`bbox` 用页面坐标（= `getBoundingClientRect()` + `scrollX/scrollY`），不要用视口坐标。提取脚本已产出每个元素的 `sel` / `x` / `y` / `w` / `h`，记录缺陷时直接复用。后续定位用法：`document.querySelector(selector).scrollIntoView()` + 高亮 outline。

> **缺陷记录的「问题现象」`symptom` 字段（所有缺陷数组通用）**：`diffs` / `iconDiffs` / `orderChecks` / `crossEnv[].items` / `sections[].items` / `responsive.perViewport[].issues` / `suggestions` / `pendingChecks` 每一条都必须带 `symptom`，值为**一句话的用户可见症状**（哪里、怎么不对劲：错位 / 换行 / 留白 / 看不见 / 数值空缺 / 被遮挡 / 颜色不符 / 顺序颠倒 / 缺失 / 多出）。指标（设计值与实际值）继续放 `reference` / `candidate`。**只有指标没有 `symptom` 的记录视为不合格**——开发看不出用户会遇到什么（见 SKILL.md 步骤 7.11）。

```json
{
  "meta": {
    "generatedAt": "2026-07-28T12:00:00+08:00",
    "referenceUrl": "Figma URL",
    "candidateUrl": "本地 URL",
    "designSize": { "width": 1438, "height": 1127 },
    "designSource": "figma",
    "textExtracted": true,
    "toolsUsed": ["mcp__figma", "mcp__playwright", "mcp_visual-parity"]
  },
  "summary": {
    "total": 50,
    "consistent": 30,
    "diff": 15,
    "missing": 3,
    "added": 2
  },
  "pixelDiff": {
    "diffPercent": 2.3,
    "diffScore": 2.3,
    "diffImage": "diff.png",
    "maskImage": "diff_mask.png",
    "ignoredRegions": 0,
    "status": "warning"
  },
  "iconDiffs": [
    {
      "name": "修改名称图标",
      "element": { "selector": "i.comIcon", "bbox": { "x": 120, "y": 88, "w": 16, "h": 16 }, "anchor": "修改名称图标" },
      "designIcon": "PencilIcon",
      "pageIcon": "i.iconfont (font:e60a)",
      "designPath": "Card / App / Button / PencilIcon",
      "nearText": "修改名称",
      "shape": { "verdict": "diff", "note": "设计稿为铅笔形状，页面沿用旧图标码点" },
      "color": { "design": "rgb(0, 149, 255)", "page": "rgb(0, 0, 0)", "verdict": "diff" },
      "size": { "design": "16x16", "page": "16x16", "verdict": "consistent" },
      "verdict": "diff",
      "priority": "high",
      "suggestion": "按设计稿替换图标资源"
    },
    {
      "name": "消息发送图标",
      "element": { "selector": "button.send-btn", "bbox": { "x": 980, "y": 520, "w": 112, "h": 36 }, "anchor": "图标位于「消息发送」按钮内" },
      "designIcon": "SendIcon",
      "pageIcon": "i.iconfont (font:e6a2)",
      "designPath": "Card / CardBody / SendBtn / SendIcon",
      "nearText": "消息发送",
      "shape": { "verdict": "diff", "note": "设计稿为纸飞机形状，页面沿用旧图标码点" },
      "color": { "design": "rgb(255,255,255)", "page": "rgb(255,255,255)", "verdict": "consistent" },
      "size": { "design": "16x16", "page": "16x16", "verdict": "consistent" },
      "container": {
        "sel": "button.send-btn",
        "text": { "design": "消息发送", "page": "消息发送", "verdict": "consistent" },
        "bg": { "design": "rgb(0,149,255)", "page": "rgb(153,153,153)", "verdict": "diff" },
        "radius": { "design": "4px", "page": "2px", "verdict": "diff" },
        "border": { "design": "none", "page": "none", "verdict": "consistent" }
      },
      "verdict": "diff",
      "priority": "high",
      "suggestion": "按设计稿替换 SendIcon 图标资源，并修正按钮背景色 rgb(0,149,255)、圆角 4px"
    }
  ],
  "orderChecks": [
    {
      "container": "Card / CardBody",
      "designOrder": ["字段A", "字段B", "字段C"],
      "pageOrder": ["字段A", "字段C", "字段B"],
      "verdict": "diff",
      "priority": "medium",
      "note": "字段B 与 字段C 顺序颠倒"
    }
  ],
  "crossEnv": [
    {
      "module": "积分管理",
      "baseEnv": "集成环境",
      "cmpEnv": "开发环境",
      "items": [
        { "item": "去编辑入口是否免滚动可见", "base": "首屏直接可见", "cmp": "需滚动 616px", "verdict": "diff", "priority": "medium" }
      ]
    }
  ],
  "sections": [
    {
      "category": "尺寸与间距",
      "items": [
        {
          "element": { "selector": "button.save-btn", "bbox": { "x": 24, "y": 320, "w": 108, "h": 32 }, "anchor": "保存按钮" },
          "reference": { "width": 108, "height": 32 },
          "candidate": { "width": 108, "height": 32 },
          "verdict": "consistent",
          "priority": null,
          "note": ""
        }
      ]
    },
    {
      "category": "文案与排版",
      "items": [
        {
          "element": { "selector": "h2.page-title", "bbox": { "x": 24, "y": 16, "w": 200, "h": 24 }, "anchor": "标题文本" },
          "reference": { "characters": "通讯录名称", "fontSize": 16, "fontWeight": 500, "letterSpacing": 0, "color": "rgb(51,51,51)" },
          "candidate": { "text": "通讯录名称", "fontSize": "16px", "fontWeight": "500", "letterSpacing": "normal", "color": "rgb(51, 51, 51)" },
          "verdict": "consistent",
          "priority": null,
          "note": "letterSpacing=normal 视为 0"
        }
      ]
    }
  ],
  "diffs": {
    "high": [],
    "medium": [],
    "low": []
  },
  "responsive": {
    "breakpoints": [1440, 1280, 1024, 768, 414, 375],
    "hasDesignBreakpoints": false,
    "perViewport": [
      { "viewport": 1440, "issues": [] },
      { "viewport": 768, "issues": [
        { "type": "overflow_right", "severity": "high", "detail": "右边界 812 超出视口 768", "element": { "selector": "div.sidebar", "bbox": { "x": 812, "y": 0, "w": 40, "h": 600 }, "anchor": "侧边栏" } }
      ] },
      { "viewport": 375, "issues": [
        { "type": "text_clipped", "severity": "medium", "detail": "内容被裁剪：保存并发布", "element": { "selector": "button.publish", "bbox": { "x": 120, "y": 1180, "w": 120, "h": 36 }, "anchor": "保存并发布按钮" } },
        { "type": "touch_target_small", "severity": "medium", "detail": "触控目标 36×36 小于 44×44", "element": { "selector": "a.icon-link", "bbox": { "x": 300, "y": 200, "w": 36, "h": 36 }, "anchor": "图标链接" } }
      ] }
    ],
    "constraintsAssertions": [
      { "element": "顶部导航", "constraint": "LEFT_RIGHT", "from": 1440, "to": 768, "verdict": "pass", "note": "左右边距固定，宽度随容器拉伸" }
    ]
  },
  "suggestions": [
    {
      "element": { "selector": "button.save-btn", "bbox": { "x": 24, "y": 320, "w": 108, "h": 32 }, "anchor": "保存按钮" },
      "issue": "背景色不一致",
      "fix": "将 .save-btn 的 background-color 改为 rgb(0,149,255)"
    }
  ],
  "pendingChecks": [
    {
      "name": "修改名称图标",
      "category": "图标形状(异构需视觉核对)",
      "verdict": "需视觉核对",
      "reason": "设计稿 SVG 与页面图标字体异构，形状指纹不可直接比，需人工对照实物确认是否同一语义图标",
      "element": { "selector": "i.comIcon", "bbox": { "x": 120, "y": 88, "w": 16, "h": 16 }, "anchor": "修改名称图标" },
      "designRef": "Card / App / Button / PencilIcon",
      "confirmLocation": "设计稿 PencilIcon 帧 ↔ 页面 i.comIcon @ (120,88,16,16) 修改名称图标",
      "pageElement": "i.comIcon（图标字体 font:e60a）",
      "suggestion": "对照设计稿实物确认图标语义是否一致；若不一致按设计稿替换"
    }
  ]
}
```

#### 9.3 Excel 缺陷报告（便于缺陷跟踪管理）

文件：`EXCEL_REPORT_NAME`（默认 `defects.xlsx`）

使用 `mcp_Excel` 工具生成结构化缺陷报告，便于导入缺陷管理系统（如 TAPD、Jira、禅道）或直接交付开发团队。

**Excel 表头格式**（严格按以下顺序，8 列）：

| 列 | 字段名 | 说明 | 示例 |
|----|--------|------|------|
| A | 序号 | 自增编号，从 1 开始 | `1` |
| B | 等级 | 缺陷优先级：高 / 中 / 低 | `高` |
| C | 缺陷类型 | UI 缺陷分类（见下方类型表） | `视觉样式` |
| D | 功能模块 | 缺陷所在的功能区块 | `保存按钮` |
| E | 问题描述 | **「问题现象 + 指标」双段**：先一句话写清用户可见的症状，再括注 Figma 值与实际值（不新增列，同列双段） | `按钮颜色偏淡、与设计稿深浅不符（Figma rgb(0,149,255)，实际 rgb(11,156,255)）` |
| F | 解决方案 | 具体可执行的修复建议 | `将 .save-btn 的 background-color 改为 rgb(0,149,255)` |
| G | 元素定位 | **页面上问题元素的定位信息**：`<selector> @ (x,y,w,h) <anchor>`，用于后续按元素定位问题位置 | `button.save-btn @ (24,320,108,32) 保存按钮` |
| H | 备注(附图) | 差异截图路径或说明，引用报告目录中的图片文件 | `见 diff.png 截图红框区域` |

**缺陷类型分类表**（填入 C 列"缺陷类型"）：

| 缺陷类型 | 对应检查清单 | 典型问题 |
|----------|-------------|----------|
| 尺寸与间距 | 步骤 7.1 第 1 项 | 宽高、padding、margin、对齐不一致 |
| 排版样式 | 步骤 7.1 第 2 项 | 字体、字号、字重、行高、文字颜色不一致 |
| 视觉样式 | 步骤 7.1 第 3 项 | 背景色、边框、圆角、阴影不一致 |
| 交互状态 | 步骤 7.2 | Hover/Active/Disabled 样式缺失或不一致 |
| 内容适配 | 步骤 7.1 第 4 项 | 文本溢出、换行异常、空状态缺失、文案错误 |
| 图标与图片 | 步骤 7.3 | 图标尺寸、颜色、裁剪方式、SVG path 不一致 |
| 响应式缺陷 | 步骤 7.4 | 横向溢出、元素跑出视口、文字截断、触控目标过小、重叠、违反 `constraints` 跨视口断言 |
| 对齐与居中 | 步骤 7.13 | 必填标识未居中、描述/hint 文案未对齐、按钮内图文未居中、弹框内文案对齐错误 |
| 布局与显隐 | 步骤 7.16 | 长内容异常空白、状态切换后文案/元素未按预期显隐、动态状态图标错误 |
| 表单错误态 | 步骤 7.17 | 必填/错误/成功/禁用态样式与交互不一致、输入边界校验缺失 |
| 浮层与层级 | 步骤 7.18 | 下拉/tooltip/modal 被裁切、层级不对、关闭行为异常、锚点跟随错位 |
| 可访问性 | 步骤 7.19 | 图标按钮无名称、Tab 顺序错乱、焦点不可见、键盘不可用 |
| 加载与空态 | 步骤 7.20 | skeleton、empty、disabled、loading、数据切换重置不一致 |
| 长文本与密集数据 | 步骤 7.21 | 长文案、混排、多条数据、列表密度导致的截断、拥挤、空白异常 |
| 实现差异 | 步骤 8 | 实现方式不同（如原生控件 vs 自定义组件）但视觉接近 |
| 缺失 | 步骤 4/7 | 设计稿有但实际页面缺失的元素 |
| 新增 | 步骤 4/7 | 实际页面有但设计稿没有的元素 |

**生成流程**：

1. **创建 Excel 文件并写入表头**（使用 `excel_write_to_sheet`）：

```
run_mcp:
  server_name: mcp_Excel
  tool_name: excel_write_to_sheet
  args:
    fileAbsolutePath: "d:\\TestCase\\parity-test\\reports\\figma-vs-local-YYYYMMDD\\defects.xlsx"
    sheetName: "UI缺陷清单"
    newSheet: true
    range: "A1:H1"
    values:
      - ["序号", "等级", "缺陷类型", "功能模块", "问题描述", "解决方案", "元素定位", "备注(附图)"]
```

2. **写入缺陷数据**（每行一个缺陷，从步骤 7-8 的对比结果中提取）：

```
run_mcp:
  server_name: mcp_Excel
  tool_name: excel_write_to_sheet
  args:
    fileAbsolutePath: "d:\\TestCase\\parity-test\\reports\\figma-vs-local-YYYYMMDD\\defects.xlsx"
    sheetName: "UI缺陷清单"
    newSheet: false
    range: "A2:H{{N+1}}"  # N 为缺陷数量
    values:
      - [1, "高", "视觉样式", "保存按钮", "按钮颜色偏淡、与设计稿深浅不符（Figma rgb(0,149,255)，实际 rgb(11,156,255)）", "将 .save-btn 的 background-color 改为 rgb(0,149,255)", "button.save-btn @ (24,320,108,32) 保存按钮", "见 diff.png 红框区域"]
      - [2, "高", "实现差异", "复选框", "勾选框样式与设计稿不同：设计为蓝色圆角方块，实际是系统原生方框、未选中时发灰（设计背景 rgb(0,94,255) 圆角 2px，实际为原生 input[type=checkbox]）", "替换为自定义组件，背景色 rgb(0,94,255)，圆角 2px", "input[type=checkbox].agree @ (60,540,20,20) 同意复选框", "见 sections/checkbox/diff.png"]
      - [3, "中", "尺寸与间距", "常用人群标签", "标签明显偏长、右侧位置被挤占（设计 104×28，实际 149×30，宽度多 45px）", "调整 .tag 的 width 为 104px，height 为 28px", "span.tag @ (300,210,149,30) 常用人群标签", ""]
      # ... 更多缺陷行（元素定位列取各提取脚本产出的 sel + 页面坐标 bbox + anchor）
```

3. **格式化表头**（加粗 + 背景色填充，使用 `excel_format_range`）：

```
run_mcp:
  server_name: mcp_Excel
  tool_name: excel_format_range
  args:
    fileAbsolutePath: "d:\\TestCase\\parity-test\\reports\\figma-vs-local-YYYYMMDD\\defects.xlsx"
    sheetName: "UI缺陷清单"
    range: "A1:H1"
    styles:
      - # A1 序号
        - font: {bold: true, color: "#FFFFFF", size: 12}
          fill: {type: "pattern", pattern: "solid", color: ["#4472C4"]}
      - # B1 等级
        - font: {bold: true, color: "#FFFFFF", size: 12}
          fill: {type: "pattern", pattern: "solid", color: ["#4472C4"]}
      - # C1 缺陷类型
        - font: {bold: true, color: "#FFFFFF", size: 12}
          fill: {type: "pattern", pattern: "solid", color: ["#4472C4"]}
      - # D1 功能模块
        - font: {bold: true, color: "#FFFFFF", size: 12}
          fill: {type: "pattern", pattern: "solid", color: ["#4472C4"]}
      - # E1 问题描述
        - font: {bold: true, color: "#FFFFFF", size: 12}
          fill: {type: "pattern", pattern: "solid", color: ["#4472C4"]}
      - # F1 解决方案
        - font: {bold: true, color: "#FFFFFF", size: 12}
          fill: {type: "pattern", pattern: "solid", color: ["#4472C4"]}
      - # G1 元素定位
        - font: {bold: true, color: "#FFFFFF", size: 12}
          fill: {type: "pattern", pattern: "solid", color: ["#4472C4"]}
      - # H1 备注(附图)
        - font: {bold: true, color: "#FFFFFF", size: 12}
          fill: {type: "pattern", pattern: "solid", color: ["#4472C4"]}
```

4. **按等级着色缺陷行**（高=红、中=黄、低=灰，使用 `excel_format_range`）：

```
run_mcp:
  server_name: mcp_Excel
  tool_name: excel_format_range
  args:
    fileAbsolutePath: "d:\\TestCase\\parity-test\\reports\\figma-vs-local-YYYYMMDD\\defects.xlsx"
    sheetName: "UI缺陷清单"
    range: "B2:B{{N+1}}"  # 仅格式化"等级"列
    styles:
      # 每行一个样式对象，根据等级设置颜色
      - [{font: {bold: true, color: "#FF0000"}}]  # 高 - 红色加粗
      - [{font: {color: "#FFC000"}}]               # 中 - 橙色
      - [{font: {color: "#808080"}}]               # 低 - 灰色
      # ... 对应每个缺陷行
```

5. **创建表格（可选，便于筛选排序）**（使用 `excel_create_table`）：

```
run_mcp:
  server_name: mcp_Excel
  tool_name: excel_create_table
  args:
    fileAbsolutePath: "d:\\TestCase\\parity-test\\reports\\figma-vs-local-YYYYMMDD\\defects.xlsx"
    sheetName: "UI缺陷清单"
    tableName: "UIDefectsTable"
    range: "A1:H{{N+1}}"
```

6. **待确认问题 sheet（需视觉核对 / 无法自动判定项）**：除「UI缺陷清单」外，另建一个名为「待确认问题」的工作表，逐条列出所有 `pendingChecks`（见步骤 7.12），每条必须带**确认位置**与**页面元素**，便于人工回查页面核实。

**表头格式**（8 列）：

| 列 | 字段名 | 说明 | 示例 |
|----|--------|------|------|
| A | 序号 | 自增编号 | `1` |
| B | 待确认项 | `pendingChecks[].name` | `修改名称图标` |
| C | 类别 | `pendingChecks[].category` | `图标形状(异构需视觉核对)` |
| D | 确认位置 | `pendingChecks[].confirmLocation`：设计稿帧 ↔ 页面 `selector @ (x,y,w,h) anchor` | `设计稿 PencilIcon 帧 ↔ 页面 i.comIcon @ (120,88,16,16) 修改名称图标` |
| E | 页面元素 | `pendingChecks[].pageElement`：元素类型 + 字体码点等 | `i.comIcon（图标字体 font:e60a）` |
| F | 设计参考 | `pendingChecks[].designRef` | `Card / App / Button / PencilIcon` |
| G | 无法自动判定原因 | `pendingChecks[].reason` | `设计稿 SVG 与页面图标字体异构，形状指纹不可直接比` |
| H | 确认建议 | `pendingChecks[].suggestion` | `对照设计稿实物确认图标语义是否一致` |

**生成流程**（同「UI缺陷清单」，sheetName 改为「待确认问题」）：

```
run_mcp:
  server_name: mcp_Excel
  tool_name: excel_write_to_sheet
  args:
    fileAbsolutePath: "d:\\TestCase\\parity-test\\reports\\figma-vs-local-YYYYMMDD\\defects.xlsx"
    sheetName: "待确认问题"
    newSheet: true
    range: "A1:H1"
    values:
      - ["序号", "待确认项", "类别", "确认位置", "页面元素", "设计参考", "无法自动判定原因", "确认建议"]
```

```
run_mcp:
  server_name: mcp_Excel
  tool_name: excel_write_to_sheet
  args:
    fileAbsolutePath: "d:\\TestCase\\parity-test\\reports\\figma-vs-local-YYYYMMDD\\defects.xlsx"
    sheetName: "待确认问题"
    newSheet: false
    range: "A2:H{{M+1}}"  # M 为待确认项数量
    values:
      - [1, "修改名称图标", "图标形状(异构需视觉核对)", "设计稿 PencilIcon 帧 ↔ 页面 i.comIcon @ (120,88,16,16) 修改名称图标", "i.comIcon（图标字体 font:e60a）", "Card / App / Button / PencilIcon", "设计稿 SVG 与页面图标字体异构，形状指纹不可直接比", "对照设计稿实物确认图标语义是否一致；若不一致按设计稿替换"]
      # ... 更多待确认行（确认位置 / 页面元素 取 pendingChecks 对应字段）
```

**数据来源映射（待确认问题 sheet）**：

| Excel 字段 | 数据来源 |
|------------|----------|
| 待确认项 | `pendingChecks[].name` |
| 类别 | `pendingChecks[].category` |
| 确认位置 | `pendingChecks[].confirmLocation`（设计稿帧 ↔ 页面 `element.selector @ (bbox.x,bbox.y,bbox.w,bbox.h) anchor`） |
| 页面元素 | `pendingChecks[].pageElement`（元素类型 + 字体码点，源自提取脚本 `sel` / `type` / `fp`） |
| 设计参考 | `pendingChecks[].designRef` |
| 无法自动判定原因 | `pendingChecks[].reason` |
| 确认建议 | `pendingChecks[].suggestion` |

> 该 sheet 与「UI缺陷清单」平级，均为缺陷跟踪管理的一部分；待确认项经人工核实后，确认有问题的并入「UI缺陷清单」、确认无问题的关闭。

**数据来源映射**：

缺陷数据从步骤 7-8 的对比结果中提取，按以下规则转换为 Excel 行：

| 步骤 9.3 Excel 字段 | 数据来源 |
|---------------------|----------|
| 序号 | 自增编号 |
| 等级 | 步骤 8 的优先级分类（高/中/低） |
| 缺陷类型 | 根据差异所属检查清单项映射（见缺陷类型分类表） |
| 功能模块 | 步骤 7 对比时记录的元素 anchor（人类可读名称/区块名，取 `element.anchor`） |
| 问题描述 | 步骤 7 对比结果中的「问题现象 + 指标」双段描述：`<一句话症状>（Figma 值 vs 实际值）`（见步骤 7.11） |
| 解决方案 | 步骤 9.1 HTML 报告中的修复建议 |
| 元素定位 | **问题元素在网页上的定位信息**，取提取脚本产出的 `sel` + 页面坐标 `bbox` + `anchor`，格式为 `sel @ (x,y,w,h) anchor`；用于后续 `document.querySelector(sel)` 回查页面问题位置（详见步骤 7.11） |
| 备注(附图) | 步骤 5-6 生成的差异截图文件名（如 `diff.png`、`sections/save-btn/diff.png`） |

**只导出缺陷项**：
- 仅导出结论为"偏差"、"缺失"、"新增"的项
- "一致"项不写入 Excel（避免清单过长）
- 如用户明确要求导出全部对比项（含一致项），可增加一个 `all-items` 工作表

**Excel 报告要求**：
- 表头必须为：序号、等级、缺陷类型、功能模块、问题描述、解决方案、元素定位、备注(附图)
- 按等级排序：高 → 中 → 低
- 等级列用颜色区分：高=红色加粗、中=橙色、低=灰色
- 元素定位列记录问题元素的选择器 + 页面坐标 bbox + 锚定文本，便于后续按元素回查页面问题位置
- 备注列引用报告目录中的截图文件名，便于快速定位
- 创建为 Excel 表格（Table），支持筛选和排序

#### 9.4 增强视图（借鉴 Argos）

在 §9.1 的「并排截图对比」之外，增加**差异叠加**与**滑动对比**两种视图，并引入量化 `diffScore`，让"差异在哪、多严重"一目了然。

**A. 像素差异热力图（diff mask）**：用 `scripts/diff_score.js` 产出的 `diff_mask.png` 作为「像素差异热力图」实图（红=变化像素），替换 §9.1 的纯文字 diff 率；`pixelDiff.maskImage` 指向它，`pixelDiff.diffScore` 为 0–100 量化分。

**B. 洋葱皮 / 滑动对比（onion-skin & swipe）**：在「并排截图」章节下追加以下可交互组件，便于人工发现细微 diff：

```html
<!-- 洋葱皮：Figma 设计稿半透明叠加在页面截图之上，拖动滑块调透明度 -->
<div class="onion">
  <img class="base" src="actual_page.png" alt="页面">
  <img class="overlay" id="ov" src="figma_spec.png" alt="设计稿">
  <input type="range" id="op" min="0" max="100" value="50">
</div>
<!-- 滑动对比：拖动分隔条，左设计稿 / 右页面 -->
<div class="swipe" id="sw">
  <img class="left" src="figma_spec.png" alt="设计稿">
  <div class="clip"><img src="actual_page.png" alt="页面"></div>
  <input type="range" id="swr" min="0" max="100" value="50">
</div>
<style>
  .onion{position:relative;display:inline-block}
  .onion .overlay{position:absolute;inset:0;opacity:.5;mix-blend-mode:difference;pointer-events:none}
  .swipe{position:relative;display:inline-block;overflow:hidden}
  .swipe .clip{position:absolute;inset:0;width:50%;overflow:hidden}
  .swipe .clip img{width:100%}
</style>
<script>
  document.getElementById('op').oninput = e => document.getElementById('ov').style.opacity = e.target.value/100;
  document.getElementById('swr').oninput = e => document.querySelector('#sw .clip').style.width = e.target.value + '%';
</script>
```

**C. 量化排序**：`diffs[]` / `iconDiffs[]` 每条带 `diffScore`（0–100），HTML 报告高优先级差异区按 `diffScore` **降序**排列，先于开发修最显眼项。`diffScore` 映射见 [diff-scoring.md](diff-scoring.md)。

**D. 新增报告章节**（与 B1–B6 引擎对应，缺数据时标注"未启用"而非留空）：
- 「像素差异热力图」（`diff_mask.png` + `diffScore`）
- 「已忽略变更」（`ignoredRegions.json` 命中的项 + reason，防盲点，见 [ignore-regions.md](ignore-regions.md)）
- 「可访问性结构变化」（`capture_aria.js --diff` 结果，见 [aria-diff.md](aria-diff.md)）
- 「跨跑回归」（`baseline_regression.cjs` 的 added/fixed，见 [baseline-regression.md](baseline-regression.md)）
- 「状态旅程覆盖」（`journey_coverage.cjs` 的 `missingSteps` + `coverageRate`，见 [state-journey.md](state-journey.md)）

> 三种增强视图（A/B/C）仅改变"如何呈现"，不改变"差异判定权威"——判定仍以确定性像素 diff + 字段映射 + 清单规则为准（见 [diff-scoring.md](diff-scoring.md) 边界说明）。

#### 报告要求
- 每项对比必须给出明确结论：**一致 / 偏差 / 缺失 / 新增**
- 差异项必须列出 Figma 值和本地值
- **每条差异必须写清「问题现象」再给指标**：先用一句话描述用户可见的症状（错位 / 换行 / 大块留白 / 看不见 / 数值空缺 / 被遮挡 / 颜色不符 …），再括注 Figma 值与实际值。禁止「XX 不一致」「XX 与设计稿不符」这类无信息描述——只写指标，开发看不出问题长什么样；只写现象，开发无法定位与验收（见 SKILL.md 步骤 7.11）
- 按优先级分组：高（建议修复）/ 中 / 低（可忽略）
- 低优先级差异需注明"可忽略"原因
- 给出具体可执行的 CSS 修复建议
- HTML 报告必须包含并排截图和差异热力图
- Excel 报告表头必须为：序号、等级、缺陷类型、功能模块、问题描述、解决方案、元素定位、备注(附图)
- Excel 报告仅导出缺陷项（偏差/缺失/新增），不导出一致项
- **HTML 报告必须包含「图标差异」章节**：把设计稿图标与页面图标**并排陈列**（左设计稿 / 右页面），每条标注名称、邻近文本、形状/颜色/尺寸三项判定与建议动作，便于开发直接照图替换。数据源为 `iconDiffs`。**按钮内的图标（如消息发送图标）除图标本身外，还需展示其 `container` 全面对比结果**：按钮文字、按钮背景色、按钮边框/圆角（任一不符即记为该图标的子缺陷）。
- **新增 UI 维度对应 HTML 章节**：表单错误态、浮层与层级、可访问性、加载/空态/禁用态、长文本/多语言/密集数据，建议各自单列为独立章节，便于后续人工回查与产品确认。
- **图标缺陷必须单列，不得与样式缺陷混排**：图标问题（图标用错 / 图标缺失 / 图标颜色）在 Excel 中的"缺陷类型"统一填 `图标不一致` 系列，方便按类型统计
- 7.8 的重复文案与文案不统一**写入「建议项」而非缺陷清单**，并在报告中说明需产品确认

