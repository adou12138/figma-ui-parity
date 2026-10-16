# 真实缺陷反推的检查维度与断言（步骤 7.13–7.16 详细版）

本文件由**两批**真实走查缺陷反推而来（第一批 24 条 → 步骤 7.13–7.16；第二批 17 条 → 渲染层细节断言），每条缺陷映射到「检查维度 → 可执行断言 → 等级」。第一批新增维度对应 SKILL.md 步骤 7.13（复合元素内部对齐）、7.14（弹框走查）、7.15（控件完整性与多余文案）、7.16（长内容布局与状态显隐），由脚本 E（`scripts/alignment_modal_checks.js`）提供自动断言数据；第二批见文末「第二批实战缺陷反推」，含可直接执行的检测片段。

## 一、缺陷 → 维度映射总表

| # | 真实缺陷（现象） | 归属维度 | 断言 | 等级 |
|---|----------|----------|------|------|
| 1 | 修改名称图标需要替换 | 7.5 图标形状 | 形状指纹/字形比对 | 高 |
| 2 | 二维码应为蓝色 | 7.5 图标颜色 | computed 颜色精确一致 | 中 |
| 3 | 复制/访问图标替换 | 7.5 图标形状 | 同 #1 | 高 |
| 4 | 服务号提示重复 + 文案不统一 | 7.8 重复文案 | 相似度 ≥0.8 检出 + 用词一致性 | 建议项 |
| 5 | 同步记录图标更新 | 7.5 图标形状 | 同 #1 | 高 |
| 6 | 消息发送图标（按钮内） | 7.5 + container 全面对比 | 图标 + 按钮文字/背景色/圆角 | 高/中 |
| 7 | 付费设置/管理积分图标 | 7.5 图标形状 | 同 #1 | 高 |
| 8 | 隐藏部门/导出图标 | 7.5 图标形状 | 同 #1 | 高 |
| 9 | 截图处小图标样式 | 7.5 图标形状/尺寸 | 同 #1 | 中 |
| 10 | 二维码尺寸展示优化 | 7.1 尺寸 | 展示尺寸 == 设计值 ±0 | 中 |
| 11 | 【添加成员】必填标识未居中 | **7.13 对齐** | 星号与标签文本垂直中心差 ≤2px | 中 |
| 12 | 【批量导入成员】必填标识未居中 | **7.13 对齐** | 同 #11 | 中 |
| 13 | 用户ID描述文案未对齐 | **7.13 对齐** | hint 左边缘与输入框左边缘差 ≤2px | 中 |
| 14 | 复选框应为 16×16 | **7.15 控件尺寸** | 控件渲染尺寸 == 设计值 ±0 | 中 |
| 15 | 成员管理栏距上边框间距 | 7.1 间距 | 距容器上边框间距 == 设计值 ±0 | 中 |
| 16 | 管理积分图标不一致 | 7.5 图标形状 | 同 #1 | 高 |
| 17 | 下拉框文案被部分遮挡 | **7.15 控件完整性** | scrollWidth ≤ clientWidth+1 | 中 |
| 18 | "111111111" 多余文案 | **7.15 多余文案** | 设计稿 characters 全集之外 + 测试数据特征 | 中 |
| 19 | 【同步记录】"修改同步"文案未对齐 | **7.13+7.14** | 弹框内文案对齐断言 | 中 |
| 20 | 长标签时出现大量空白 | **7.16 长内容布局** | 内容末元素与容器底部异常空隙 ≤100px | 中 |
| 21 | 添加标签后"修改"图标替换 | 7.5 + 动态状态（7.16） | 状态变化后重跑图标比对 | 高 |
| 22 | 已设收款方式后文案应隐藏 | **7.16 状态显隐** | 状态变更后元素显隐符合设计意图 | 建议项/待确认 |
| 23 | 下拉框遮挡（勇哥环境正常） | 7.10 跨环境 | 以正常环境为基准，差异记中 | 中 |
| 24 | 同步记录对齐（集成也有） | 7.10 跨环境 | 跨环境共性问题合并跟踪 | 中 |

**覆盖结论**：#1–10、15、16 由基础样式与布局维度覆盖；#11–14、17–22 暴露 4 个扩展维度（7.13–7.16），#23–24 进一步说明跨环境交叉与共性问题处理；本节同时补充 7.17–7.21 的通用 UI 断言能力，作为后续页面专项检查的扩展底座。

## 二、新维度断言细则

### 7.13 复合元素内部对齐

| 断言 | 判定 | 等级 |
|------|------|------|
| 必填标识（`*`/`＊` 或 required 类元素）与所属标签文本的**垂直中心差** | `|astCenterY − labelCenterY| ≤ 2px` | >2px → 中 |
| 输入框下方描述/hint 文案与输入框**左边缘对齐** | `|hint.left − input.left| ≤ 2px` | >2px → 中 |
| 按钮内图标与文字**垂直居中**（配合 7.5 container） | `|iconCenterY − textCenterY| ≤ 2px` | >2px → 中 |
| 弹框内标题/文案**对齐方式**与设计稿一致 | text-align 比对 | 不一致 → 中 |
| 表单块内多行提示之间的基线一致 | 基线差 ≤2px | 超出 → 中 |

数据源：脚本 E `alignments` 段（`kind: required-mark / hint-left-align`，每条带 `sel` + 页面坐标 `box` + `pass`）。

### 7.14 弹框 / 浮层逐个走查

**为什么必须单独走查**：仅查主页面会漏掉全部弹框内缺陷——实测【添加成员】【批量导入成员】【同步记录】三个弹框各有独立缺陷（#11、12、19）。

流程：
1. 从主页面枚举所有弹框触发入口（按钮/链接），**逐个点击打开**；
2. 弹框打开态重跑脚本 A / B / E（弹框内容是动态渲染的，主页面跑的数据不包含弹框）；
3. 弹框内标题、必填标识、表单控件、按钮全部纳入 7.1–7.15 各维度；
4. 脚本 E `modals` 段记录发现的弹框（`sel` + `box` + 标题文本）；有入口但打不开/找不到入口的弹框，在报告标注"入口未找到"，不静默跳过。

### 7.15 控件内容完整显示与多余文案

| 断言 | 判定 | 等级 |
|------|------|------|
| 控件内容完整显示（select/input/button） | `scrollWidth ≤ clientWidth + 1` | 超出 → 中（文案被遮挡，如 #17 下拉框） |
| 控件宽度 vs 设计稿 | 控件渲染宽度 == 设计值 ±0 | 不一致 → 中（"下拉选项框再加长"） |
| 原生控件渲染尺寸（checkbox/radio） | == 设计稿尺寸（如 16×16）±0 | 不一致 → 中（#14） |
| 多余/垃圾文案 | 页面文本 ∉ 设计稿 characters 全集 **且** 形似测试数据：纯数字 ≥6 位 / 同字符重复 / `test` 类词 | 命中 → 新增(文案)（中，与产品确认，如 #18） |
| 内容宽度兜底 | 文字区域应有最小内边距，避免贴边或裁切 | 不符合 → 中 |

数据源：脚本 E `clippedControls` / `suspiciousText` 段。

### 7.16 长内容布局与状态相关显隐

| 断言 | 判定 | 等级 |
|------|------|------|
| 长内容异常空白 | 添加长标签/多条数据后，内容末元素底部与容器底部空隙 >100px 且中间无内容填充 | 中（#20） |
| 动态状态图标 | 状态变化后（如添加标签后）新出现的图标同样按 7.5 成对比对 | 形状不符 → 高（#21） |
| 状态相关显隐 | 状态变更后应隐藏的文案/元素仍显示（如已设收款方式后"付费一次即可作答全部问卷"） | 建议项/待确认（产品决策，#22） |
| 数据密度退化 | 数据增多后原本正常布局不应出现大块空白或错位 | 异常 → 中 |

**长内容空白检测方法**（脚本 E 未覆盖，人工/半自动）：

```js
// 在添加长内容后执行：找出容器底部与最后子元素底部之间的异常空隙
(() => {
  const res = [];
  document.querySelectorAll('div, ul, td').forEach(box => {
    const b = box.getBoundingClientRect();
    if (b.height < 100) return;
    const kids = Array.from(box.children).filter(k => {
      const r = k.getBoundingClientRect(); const cs = getComputedStyle(k);
      return r.height > 0 && cs.position !== 'absolute' && cs.display !== 'none';
    });
    if (kids.length < 2) return;
    const last = kids[kids.length - 1].getBoundingClientRect();
    const gap = b.bottom - last.bottom;
    if (gap > 100) res.push({ sel: box.tagName.toLowerCase() + (box.id ? '#' + box.id : ''),
      gapBottom: Math.round(gap), boxH: Math.round(b.height) });
  });
  return JSON.stringify(res);
})()
```

> 注意：仅对**非滚动列表容器**判缺陷；可滚动容器底部的自然留白不算（结合 7.9 可滚动性判断）。

### 与跨环境（7.10）的交叉

- 某缺陷**一个环境正常、另一个环境异常**（#23 下拉框遮挡）→ 以正常环境为基准，差异记**中**，并注明环境名；
- 多环境**共有**的缺陷（#24 同步记录对齐）→ 合并为一条缺陷跟踪，避免重复提单；
- 跨环境走查时 7.13–7.16 全部维度同样适用（对齐/遮挡/空白在不同环境可能表现不同）。

## 三、脚本 E 说明

`scripts/alignment_modal_checks.js`：反斜杠无关设计，https 页面直接内联 `browser_evaluate` 执行（同脚本 C 约定，结尾裸 `})()`）。输出四段：

| 段 | 内容 | 对应维度 |
|----|------|----------|
| `modals` | 当前打开的弹框（sel + box + 标题文本） | 7.14 |
| `alignments` | 必填标识居中 / hint 左对齐断言（`pass` 字段） | 7.13 |
| `clippedControls` | scrollWidth 溢出的控件 | 7.15 |
| `suspiciousText` | 形似测试数据的多余文案候选 | 7.15 |

限制：脚本只能检查**当前打开态**的弹框与**当前数据状态**下的内容；长内容/状态切换场景需按 7.16 人工构造数据后重跑。

**踩坑记录**：
1. **反向引用与字面反斜杠的反斜杠个数不同**：正则源码要一个**反向引用 `\1`**，字符串只需 `CH(92) + '1'`（一个反斜杠字符）；要匹配**字面反斜杠字符**才需要 `CH(92) + CH(92)`（两个反斜杠字符，见 icon-diff.md gotcha #7）。写反会变成"匹配字面反斜杠+数字"，静默匹配失败（实测 `aaaaaa` 重复检测因此漏检）。
2. **垃圾文案阈值**：文本长度 <4 的跳过（避免误伤"确定""取消"等短文案）；纯数字 ≥6 位才判可疑（避免误伤年份数量等正常数字）。
3. **对齐断言阈值 ±2px**：亚像素渲染误差约 ±0.5px，取 2px 为判定线；超出记缺陷但 `deltaCenterY`/`deltaLeft` 随结果输出，便于人工复核边界情况。

---

# 第二批实战缺陷反推（通讯录 1036944，17 条）

来源：`tl.sojump.cn` 通讯录 4 页（通讯录 / 管理员·管理 / 成员·作答 / 其他设置）对比设计稿【1036944】时的实测反馈。本批暴露的新维度集中在**"渲染层细节"**：图标是否真的画出来、字符级文案是否干净、单行/换行、数值是否渲染、滚动留白、跨卡片对齐。

## 一、缺陷 → 维度映射总表

| # | 真实缺陷（现象） | 页面 | 归属维度 | 断言 | 等级 |
|---|----------|------|----------|------|------|
| 1 | 「新增管理员」的 `+` 图标未显示 + 文案未居中 | 管理员 | **7.5 图标渲染可用性** + 7.13 | 图标渲染尺寸 >0 且字形/path 存在；图标与文字垂直中心差 ≤2px | 高 |
| 2 | 页面提示条是否需要保留 | 管理员 | 7.12 待确认 | 设计无 / 页面有的提示 → 产品确认 | 待确认 |
| 3 | 用户ID列复选框后多出 `.` | 通讯录 | **7.15 多余标点** | 页面文本比设计稿多出标点类字符 | 中 |
| 4 | 用户ID列的值缩略显示（集成正常） | 通讯录 | 7.4 截断 + **7.10 跨环境** | 以正常环境为基准，差异记中 | 中 |
| 5 | 部门多时滑到底右侧大量空白；建议加滚动条 | 通讯录 | **7.16 滚动容器空白** + 7.9 | 滚动到底底部/右侧无异常空白；长列表应有滚动/分页 | 中 |
| 6 | 「已有数据量」与「需要更多」间隔不符 | 管理员 | **7.1 同行相邻间距** | 相邻内联元素间距 == 设计值 ±0 | 中 |
| 7 | 「管理员·管理」「成员·作答」中间 `·` 未加粗 | 全局 | **7.1 复合文案片段样式** | 文案内子串（含分隔符）字重/字号/颜色一致 | 中 |
| 8 | 有效期起止日期换行 | 管理员 | **7.1 字段单行性** | 设计为单行的字段不得换行 | 中 |
| 9 | 「已用 x 人」数值未显示 | 管理员 | **7.1 动态数值渲染** | 设计中的数值位页面必须有值（非空/非占位） | 高 |
| 10 | 设计有搜索功能、页面没有 | 管理员 | 步骤 7 缺失 | 设计有页面无的功能入口 → 高/待确认 | 高/待确认 |
| 11 | 列表与底部插件应横线分割、现为间隔 | 管理员 | 7.7 + **间距** | 分隔线位置与相邻区块间距 == 设计值 | 中 |
| 12 | 有效期换行（同 #8） | 管理员 | 7.1 字段单行性 | 同 #8 | 中 |
| 13 | 「修改名称」前小图标不一致 | 其他设置 | 7.5 | 图标形状/颜色逐个比对（含**内联小图标**） | 高 |
| 14 | 「导出」小图标不一致 | 其他设置 | 7.5 | 同 #13 | 高 |
| 15 | 主页系统语言 / 绑定自有服务号宽度不符 | 其他设置 | **7.15 选择控件宽度** | 选择控件渲染宽度 == 设计值 ±0 | 中 |
| 16 | 「同步记录」小图标不一致 | 其他设置 | 7.5 | 同 #13 | 高 |
| 17 | 成员字段管理 / 标签管理下边框横线未对齐 | 其他设置 | **7.13 跨卡片对齐** | 同行多卡片高度 / 底部分割线 y 差 ≤2px | 中 |

**覆盖结论**：#2、#4、#10、#12、#13、#14、#16 由已有维度覆盖（其中 #13/#14/#16 属"执行没扫全内联小图标"）；#1、#3、#5–#9、#11、#15、#17 共 10 条需新增断言。

## 二、新增断言细则（含可复制检测片段）

判定总原则：**间距 / 宽度 / 尺寸必须与设计值 ±0 一致**；渲染可用性异常（图标不出、数值为空）记**高**；字符级脏数据、换行、留白记**中**。所有检测片段均为只读，返回**候选列表**供人工与设计稿复核。

### 2.1 图标渲染可用性（配合 7.5）

图标"存在"不等于"画得出来"：iconfont 未加载 / svg 无 path / 尺寸被压成 0 都会表现为**图标消失**（#1 的 `+`）。

```js
(() => {
  const isEmptyGlyph = el => {
    const tag = el.tagName.toLowerCase();
    if (tag === 'svg') return !el.querySelector('path,use,circle,rect,polygon');
    if (tag === 'img') return !el.getAttribute('src');
    const clear = c => ['none', 'normal', '""', "''", ''].indexOf(c) >= 0;
    const pseudo = !clear(getComputedStyle(el, '::before').content) || !clear(getComputedStyle(el, '::after').content);
    return !(el.textContent || '').trim() && !pseudo && getComputedStyle(el).backgroundImage === 'none';
  };
  const bad = [];
  document.querySelectorAll('i[class*=icon], .comIcon, .iconfont, svg, img[class*=icon]').forEach(el => {
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;          // 隐藏/折叠（含 0 尺寸占位）不算缺陷
    if (!isEmptyGlyph(el)) return;                    // 有文字/伪元素字形/背景图/svg path → 正常
    bad.push({
      sel: el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(/\s+/)[0] : ''),
      x: Math.round(r.x + scrollX), y: Math.round(r.y + scrollY), w: Math.round(r.width), h: Math.round(r.height)
    });
  });
  return JSON.stringify(bad);
})()
```

> 命中即**高**：图标未渲染与"图标用错"同级——用户看不到就是缺陷。

### 2.2 多余标点 / 分隔符（配合 7.15）

页面文本比设计稿 `characters` 全集**多出标点类字符**（#3 复选框后多出的 `.`），含零宽字符。

```js
(() => {
  const ZERO = /[\u200b-\u200f\u2028-\u202f\ufeff]/;      // 零宽/不可见字符
  const PUNCT_ONLY = /^[.·,、;:]+$/;                      // 整个元素只有标点
  const SPACE_DOT_TAIL = /[\s\u3000][.·,、]$/;             // 以「空格 + 句点」结尾（如复选框后多出的 .）
  const out = [];
  document.querySelectorAll('td,span,div,a,label,p,li,em').forEach(el => {
    if (el.children.length) return;
    const t = (el.textContent || '').trim(); if (!t || t.length > 40) return;
    if (ZERO.test(t) || PUNCT_ONLY.test(t) || SPACE_DOT_TAIL.test(t))
      out.push({ sel: el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(/\s+/)[0] : ''), text: JSON.stringify(t) });
  });
  return JSON.stringify(out);
})()
```

### 2.3 复合文案片段样式（配合 7.1）

同一文案内的**分隔符/子串**字重需与设计一致（#7 中间的 `·` 未加粗）。

```js
(() => {
  const out = [];
  document.querySelectorAll('span,div,a,label').forEach(el => {
    const t = (el.textContent || '').trim();
    // 只取「A·B」式短标签（单个分隔符），排除导航容器等多分隔符文本
    if (!/^[^·•|/]{1,10}[·•|/][^·•|/]{1,10}$/.test(t)) return;
    const kids = [...el.children];
    if (kids.length < 2) return;   // 分隔符必须是独立元素才可自动判
    const styles = new Set(kids.map(k => { const cs = getComputedStyle(k); return cs.fontWeight + '/' + cs.fontSize + '/' + cs.color; }));
    if (styles.size > 1) out.push({ sel: el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(/\s+/)[0] : ''), text: t, variants: [...styles] });
  });
  return JSON.stringify(out);
})()
```

> 若设计稿把分隔符做成独立文本节点/加粗，而页面写成单一文本节点——**DOM 判不了**，记为 `pendingChecks`（需视觉核对）；反之若页面拆分而字重不一，直接记**中**。

### 2.4 字段值单行性（配合 7.1）

设计为**单行**的字段（如有效期 `起—止`）不得换行（#8/#12）。

```js
(() => {
  const SKIP = /desc|tip|note|help|hint|title|paragraph|content|placeholder/i;  // 说明性长文允许换行，不算
  const lineCount = el => { const r = document.createRange(); r.selectNodeContents(el); return r.getClientRects().length; };
  const out = [];
  document.querySelectorAll('td,span,div,strong,label,b').forEach(el => {
    if (el.children.length) return;
    const cls = String(el.className || ''); if (SKIP.test(cls)) return;
    const cs = getComputedStyle(el);
    if (cs.whiteSpace === 'nowrap' || cs.textOverflow === 'ellipsis') return;
    const t = (el.textContent || '').trim(); if (!t || t.length > 40) return;   // 长文本多半本就该换行
    const n = lineCount(el);
    if (n > 1) { const r = el.getBoundingClientRect(); out.push({ sel: el.tagName.toLowerCase() + (cls ? '.' + cls.split(/\s+/)[0] : ''), text: t.slice(0, 30), lines: n, x: Math.round(r.x + scrollX), y: Math.round(r.y + scrollY) }); }
  });
  return JSON.stringify(out);
})()
```

> 与设计稿逐字段比：设计单行、页面多行 → **中**；建议加 `white-space:nowrap` 或收窄字号/列宽。

### 2.5 动态数值渲染（配合 7.1 / 7.15）

设计中的**数值占位**（已用 N 个 / 共 N 条）在页面必须渲染出值（#9 "已用 x 人"为空）。

```js
(() => {
  const MISSING_NUM = /(已用|可用|共|剩余|已选|已导入|已同步|已添加|已发送)\s*(个|人|条|项|位|次)/;
  const out = [];
  document.querySelectorAll('*').forEach(el => {
    if (el.children.length) return;
    const t = (el.textContent || '').trim(); if (!t || t.length > 60) return;
    if (MISSING_NUM.test(t)) out.push({ sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : (el.className ? '.' + String(el.className).split(/\s+/)[0] : '')), text: t });
  });
  return JSON.stringify(out);
})()
```

> 命中即**高**：数值没渲染，用户拿不到信息。同时排查是否接口未返回（数据缺失）还是前端未绑定。

### 2.6 滚动容器空白与长列表（配合 7.16 / 7.9）

数据多时滚动到底，**底部/右侧不应出现大块空白**；长列表本身应有滚动或分页手段（#5）。

```js
(() => {
  const out = [];
  document.querySelectorAll('*').forEach(el => {
    const cs = getComputedStyle(el); const r = el.getBoundingClientRect();
    if (!/(auto|scroll)/.test(cs.overflowY + cs.overflowX) || r.height < 120) return;
    const kids = [...el.children].filter(k => k.getBoundingClientRect().height > 0);
    if (!kids.length) return;
    const rs = kids.map(k => k.getBoundingClientRect());
    const gapBottom = Math.round(r.bottom - Math.max(...rs.map(x => x.bottom)));
    const rightMost = Math.max(...rs.map(x => x.right));
    const gapRight = Math.round(r.right - rightMost);
    if (gapBottom > 80 || gapRight > 80) out.push({
      sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : (el.className ? '.' + String(el.className).split(/\s+/)[0] : '')),
      scrollW: el.scrollWidth, clientW: el.clientWidth, gapBottom, gapRight
    });
  });
  return JSON.stringify(out);
})()
```

> 横向留白判定前先确认是否**本就纵向滚动**的容器（横向空白可能来自列宽不足）；结合 7.9 判断"数据量大但无滚动/分页手段" → 建议项（中）。

### 2.7 同行相邻元素间距（配合 7.1）

同一行内**相邻内联元素**（如"已有数据量"与"需要更多"链路）间距需与设计一致（#6）。

```js
(() => {
  const out = [];
  document.querySelectorAll('div,span,p,li').forEach(row => {
    const kids = [...row.children].filter(k => { const r = k.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
    if (kids.length < 2 || kids.length > 12) return;
    const groups = {};
    kids.forEach(k => { const r = k.getBoundingClientRect(); const key = Math.round(r.top / 5); (groups[key] = groups[key] || []).push(r); });
    for (const key in groups) {
      const arr = groups[key].sort((a, b) => a.left - b.left);
      for (let i = 1; i < arr.length; i++) {
        const gap = Math.round(arr[i].left - arr[i - 1].right);
        if (gap > 0) out.push({ row: row.tagName.toLowerCase() + (row.className ? '.' + String(row.className).split(/\s+/)[0] : ''), gap, y: Math.round(arr[i].top + scrollY) });
      }
    }
  });
  return JSON.stringify(out.slice(0, 60));
})()
```

> 把候选 `gap` 与设计稿对应相邻元素间距逐条比对；不一致 → **中**。

### 2.8 分隔线位置与间距（配合 7.7）

列表与底部插件之间应是**贴合的横线分割**，而不是大间隔（#11）。

```js
(() => {
  const out = [];
  document.querySelectorAll('*').forEach(el => {
    const r = el.getBoundingClientRect(); const cs = getComputedStyle(el);
    const bw = parseFloat(cs.borderBottomWidth) || 0;
    const isLine = (r.height <= 2 && r.width > 40) || (bw >= 1 && bw <= 2 && r.width > 40);
    if (!isLine) return;
    out.push({ sel: el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(/\s+/)[0] : ''), y: Math.round(r.top + scrollY), w: Math.round(r.width), color: cs.borderBottomColor || cs.backgroundColor });
  });
  return JSON.stringify(out.slice(0, 40));
})()
```

> 设计稿该处有分隔线而页面只有空白间隔 → **中**（补 `border-bottom`）；页面多出分隔线 → 低。

### 2.9 选择控件宽度（配合 7.15）

下拉 / 选择类控件（如"主页系统语言""绑定自有服务号"）宽度需与设计值一致（#15）。

```js
(() => {
  const out = [];
  document.querySelectorAll('select,[class*=select],[class*=dropdown],[role=combobox]').forEach(el => {
    const r = el.getBoundingClientRect(); if (r.width < 20 || r.height < 10) return;
    out.push({ sel: el.tagName.toLowerCase() + (el.id ? '#' + el.id : (el.className ? '.' + String(el.className).split(/\s+/)[0] : '')), w: Math.round(r.width), h: Math.round(r.height) });
  });
  return JSON.stringify(out);
})()
```

### 2.10 跨卡片对齐（配合 7.13）

同一行两张卡片（成员字段管理 / 成员标签管理）**高度与底部分割线的 y 必须对齐**（#17）。

```js
(() => {
  const cards = [...document.querySelectorAll('[class*=card],[class*=panel]')].filter(el => { const r = el.getBoundingClientRect(); return r.width > 150 && r.height > 80; });
  const byRow = {};
  cards.forEach(el => { const r = el.getBoundingClientRect(); const key = Math.round(r.top / 20); (byRow[key] = byRow[key] || []).push({ cls: String(el.className).split(/\s+/)[0], top: Math.round(r.top + scrollY), bottom: Math.round(r.bottom + scrollY) }); });
  const out = [];
  for (const key in byRow) {
    const g = byRow[key]; if (g.length < 2) continue;
    const bottoms = g.map(x => x.bottom);
    const spread = Math.max(...bottoms) - Math.min(...bottoms);
    if (spread > 2) out.push({ rowY: key, cards: g, spreadBottom: spread });
  }
  return JSON.stringify(out);
})()
```

> `spreadBottom > 2px` → **中**（两卡片下边框/底部分割线不齐）。

## 三、已有维度的执行强化

- **7.5 图标成对比对要扫全"内联小图标"**（#13/#14/#16）：不只比按钮内图标——**修改名称 / 导出 / 同步记录 / 复制 / 访问 / 二维码** 这类内联小图标都要与设计稿 VECTOR 节点配成对逐个比形状与颜色。漏扫是这批里最多的漏报来源。
- **7.10 跨环境**（#4）：同一元素"一个环境正常、另一个环境缩略/异常" → 以正常环境为基准记**中**，并写明环境名。
- **缺失与取舍**（#10 / #2）：设计有、页面无的功能入口（如"输入用户名搜索"）记**高**或转 `pendingChecks`；设计无、页面有的提示条（#2）属产品决策 → `pendingChecks` 交产品确认，不直接判缺陷。

## 四、判定与记录要求

- 每条命中都要带 **`symptom` 问题现象**与 **`element` 元素定位**（selector + 页面坐标 bbox + anchor），结构遵循 `schemas/defect.schema.json`，维度号取 `references/check-dimensions.md` 的 7.11。**现象与定位缺一不可**：现象让开发知道用户看到什么，定位让问题能在页面上被找到。
- 现象写在前、指标写在后：`<一句话症状>（设计 <设计值>，实际 <实际值>）`。映射表的「真实缺陷（现象）」列即按此写——如 #17「两张卡片右宽左窄、**下边框横线不在同一水平线上**（设计等宽 592:592，实际 426:758，底边差 10px）」，而不是只写"宽度不符"。
- 禁止用「XX 不一致」「XX 与设计稿不符」充当问题描述：这类写法等于没描述，开发看不出用户会遇到什么，也无法验收。
- 检测片段返回的是**候选**，必须与设计稿对应元素比对后落等级；不得直接把候选当缺陷数量。
- 渲染可用性（图标不出、数值为空）= **高**；字符脏数据 / 换行 / 留白 / 间距偏差 = **中**；分隔线多出 = 低。

## 五、资源与用户偏好维度（7.24–7.34）与运行期观测（7.35–7.38）

这一组是历史上被反复漏掉的维度：**样式一致但用户实际用不了或看不到**。检测片段集中在 `scripts/extra_checks.js`（无副作用探测，不点击不提交），场景驱动部分由 `scripts/discover_scenarios.py` 生成。

### 7.24 图片与插画适配（配合 7.3）

**要查**：宽高比失真、`object-fit` 缺失导致拉伸、加载失败无兜底、图片撑破卡片。

**判据**：`|渲染比例 − 固有比例| / 固有比例 > 5%` 且 `object-fit` 为 `fill` 或默认 → **高**（视觉上明显变形）；`naturalWidth === 0`（404 / 跨域失败）且无占位样式 → **高**（碎图撑破布局）。

```js
(() => {
  const out = [];
  document.querySelectorAll('img').forEach(el => {
    const r = el.getBoundingClientRect(); if (r.width < 2 || r.height < 2) return;
    const fit = getComputedStyle(el).objectFit;
    const loaded = el.complete && el.naturalWidth > 0;
    const rendered = r.width / r.height;
    const natural = el.naturalHeight ? el.naturalWidth / el.naturalHeight : null;
    if (!loaded) { out.push({ sel: el.className || el.src, issue: 'not-loaded' }); return; }
    if (natural && Math.abs(rendered - natural) > 0.05 * natural && fit !== 'cover' && fit !== 'contain') {
      out.push({ sel: el.className || el.src, issue: 'stretched', rendered: +rendered.toFixed(3), natural: +natural.toFixed(3), fit });
    }
  });
  return JSON.stringify(out);
})()
```

> 设计稿里的插画多为固定比例，被 `width:100%` 拉长后肉眼可见；截图比对只能看到"这块不一样"，必须用比例判据才能说清是失真。

### 7.25 暗色模式与主题切换

**要查**：是否存在深色适配；写死浅色背景；切换主题后图标与边框未跟随。

**判据**：同源样式表中无 `prefers-color-scheme: dark` 且存在纯浅色背景元素 → **中**（深色环境下刺眼）；有适配但未实测 → 记 `pending`，不得直接判通过。

- 主题切换属于状态场景：切换前后各截一次图、各提一次色值，逐项比对；切换后未刷新的元素按 7.16 处理。

**执行方式**（状态场景驱动，可自动跑）：

```
node scripts/node/run_state_scenarios.cjs --url "<页面>" --out ./parity-test/state-scenarios
```

驱动用 `page.emulateMedia({ colorScheme: 'dark' })` 真切换后重新探测（`scripts/state_probes.js` 的 `dark` 模式）：emulate 后背景仍近白的元素 → **confirmed 中**；文字与背景对比度 < 4.5 → **confirmed 中**。相比 `extra_checks.js` 的样式表扫描，这是**渲染事实**而非存在性推断。静态扫描（未切换时）仍由 `extra_checks.js` 提供，两者互补。

### 7.26 打印与导出视图

**要查**：`@media print` 下内容丢失、表格截断、操作按钮（保存/删除）误入打印稿、分页处文字被切断。

**执行方式**：`page.emulateMedia({ media: 'print' })` 后截图与设计稿的打印稿比对；无打印稿时只记录「未提供打印设计稿」→ `dataMissing`。**不得**因为"用户不打印"跳过而不声明。

状态场景驱动把这一步变成可执行项：

```
node scripts/node/run_state_scenarios.cjs --url "<页面>" --out ./parity-test/state-scenarios
```

`scripts/state_probes.js` 的 `print` 模式在 emulate 后探测：操作按钮仍可见 → **P3 pending**（打印稿是否保留按钮是设计决策，不擅自判缺陷）；表格 `scrollWidth` 超出 `clientWidth`（打印态内容被裁）→ **confirmed 中**；近白文字叠近白背景（打印出来看不见）→ **confirmed 中**。与打印稿的逐项比对仍需人工（缺打印设计稿时该部分记 `dataMissing` 并写明）。

### 7.27 多行文本截断与省略（配合 7.15）

**要查**：`-webkit-line-clamp` 生效但末行被裁掉、省略号缺失、`line-clamp` 行数与设计不符、截断后高度跳动。

**判据**：`scrollHeight > clientHeight + 1` 且 `line-clamp > 0` 且无 `text-overflow: ellipsis` 生效 → **中**；单行 `ellipsis` 且无 `title` → **低**（用户无法查看全文）。

### 7.28 表单控件细节

**要查**：placeholder 颜色对比度过低、`caret` 颜色、原生控件（`number` / `date` / `password` / `search`）样式破坏布局、`autocomplete` 缺失导致浏览器填充遮挡。

**判据**：文字与背景对比度 < 3 → **高**（内容不可辨）；`password` / `number` / `tel` 无 `autocomplete` → **低**（提示性，不阻断）。

### 7.29 焦点可见性与键盘细节（配合 7.19）

**要查**：全局 `outline: none` 无替代样式、`:focus` 与 `:focus-visible` 行为不一致、焦点陷阱缺失、快捷键冲突。

**判据**：逐个 `el.focus()` 前后比较 `outline` 与 `box-shadow`，无任何变化且 `outlineWidth === 0` → **高**（键盘用户完全丢失位置）。

```js
(() => {
  const out = [];
  const list = [...document.querySelectorAll('a[href],button,input,select,textarea,[tabindex]')].slice(0, 60);
  list.forEach(el => {
    const b = getComputedStyle(el), before = b.outlineStyle + b.outlineWidth + b.boxShadow;
    el.focus({ preventScroll: true });
    const a = getComputedStyle(el), after = a.outlineStyle + a.outlineWidth + a.boxShadow;
    if (before === after && (a.outlineStyle === 'none' || parseFloat(a.outlineWidth) === 0)) {
      out.push({ sel: el.className || el.tagName, tag: el.tagName, text: (el.innerText || '').slice(0, 20) });
    }
  });
  return JSON.stringify(out);
})()
```

> 弹窗打开后必须检查焦点是否进入弹窗、关闭后是否回到触发按钮，这两条属 7.14 与 7.29 交叉，容易漏。

### 7.30 国际化细节

**要查**：RTL 内容未声明 `dir`、emoji 导致行高跳动、全角与半角混排错位、英文长文案截断方式与设计不符。

**判据**：RTL 字符（`0x0590–0x08FF`、`0xFB1D–0xFDFF`）出现在 `direction: ltr` 容器 → **中**；emoji 所在行 `scrollHeight > clientHeight` → **低**；长英文撑宽按钮 → **中**（配合 7.21）。

### 7.31 滚动 UX

**要查**：固定底栏遮挡最后一行内容、sticky 头部与锚点重叠、无弹层时 `body` 滚动被锁死、滚动条样式与设计不一致。

**判据**：`position: fixed` 且 `bottom ≈ innerHeight` 的横条 + 页面可滚动 + 无等值底部留白 → **高**（底部操作点不到）；无可见弹层而 `body { overflow: hidden }` → **高**（页面锁死）。

### 7.32 页面级状态残留

**要查**：SPA 路由切换后筛选/滚动/展开态残留、返回后数据未刷新、多标签页互相影响。

**执行方式**：进入列表 → 设置筛选与滚动 → 跳详情 → 返回 → 比对筛选与滚动位置是否符合设计（重置或保留）；两个标签页各改一处数据，观察是否互相覆盖。属于必须主动触发项，静态快照覆盖不到 → 没做就填 `notRun`。

**触发条件（重要，避免误判成漏跑）**：`discover_scenarios.py` 只有在页面识别到 `tabs / table / pagination` 交互、或缺陷池命中 7.32 时才生成该维度场景。两者都不满足时**该维度没有场景**——这不是漏跑，应填 `notRun:页面无路由类元素` 并说明依据。若要强制覆盖，手工传 `--patterns`（池里放一条 7.32 历史缺陷）即可补出页面级往返场景。

状态场景驱动自动执行其中**零写风险**的一段：

```
node scripts/node/run_state_scenarios.cjs --url "<页面>" --out ./parity-test/state-scenarios
```

驱动记录进入时状态快照（URL/锚点/滚动位置/可见筛选项/内容量）→ hash 导航 → `history` 返回 → 复拍快照比对。**只硬判"返回后白屏"这一确定缺陷**（confirmed P1）；锚点/滚动/筛选项的保留还是重置是设计决策，一律记 `pending` 交人工，不擅自判缺陷（与 E04 状态矩阵同一纪律：跑成事实表，合法性不猜）。多标签页互相影响仍需人工。

### 7.33 接口异常与慢网络下的界面

**要查**：5xx / 超时 / 慢网下白屏、骨架屏永久残留、错误提示缺失或不可重试、重复提交。

**执行方式**：`page.route` 拦截目标接口返回 500 / 延迟 10s，观察界面；**只看界面表现，不制造真实写操作**。

**判据**：白屏且无任何提示 → **高**；有提示但无重试入口 → **中**；骨架屏不消失 → **高**（用户永远看不到内容）。

状态场景驱动自动执行：

```
node scripts/node/run_state_scenarios.cjs --url "<页面>" --out ./parity-test/state-scenarios
```

驱动 `page.route` **拦载** XHR/fetch 并直接 fulfill 500（请求根本不到服务端，不可能产生真实写操作；html/css/img 放行保证页面能渲染），reload 后探测：内容区可见文本 < 50 字符（白屏）→ **confirmed 高**；骨架屏/加载占位仍可见 → **confirmed 高**；无错误提示且无重试入口 → **pending 中**（提示文案是否合格需人工看）。

### 7.34 角色与权限态视图差异

**要查**：不同角色可见字段/操作是否与设计一致、是否存在越权入口、只读角色是否仍可编辑。

**执行方式**：同一页面用不同角色的登录态各跑一遍，按元素集合做差集（`--roles admin,member` 生成场景）。缺角色凭据时填 `notRun:未提供角色凭据`，**不得**用单一角色结果推断其他角色。

### 7.35–7.38 运行期观测

静态探测只读 DOM 与 computed style，看不到"交互过程中炸了没"。这四项由
`scripts/runtime_observability.js` 采集（交互前安装钩子、交互后采集），
判据与安全边界见 `references/runtime-observability.md`：

| 维度 | 要查 | 判据 |
|---|---|---|
| 7.35 运行期 JS 异常 | console.error / window.onerror / unhandledrejection | 任一未捕获错误 → P1 |
| 7.36 交互期网络失败 | fetch / XHR 非 2xx | 5xx/网络错误 P1、4xx P2 |
| 7.37 重复请求/重复提交 | 同一写请求 3s 内重复 | 疑似重复提交 → P1（pending） |
| 7.38 可交互元素遮挡 | elementFromPoint 命中测试 | 中心点被非自身/祖先/后代覆盖 → P1（pending） |

**缺陷模式池**：以上断言与 7.1–7.38 的实战断言共同沉淀在 `assets/defect_patterns.json`，
由 `scripts/pattern_pool.py` 维护——`--merge` 把新确认的缺陷并入池（幂等）、
`--rank` 按严重度+置信度对报告缺陷做风险排序（输出 Top N）。新缺陷模式只增不改 id，
避免同一类问题下次再漏。

**模式池反哺场景生成（闭环）**：`discover_scenarios.py --patterns assets/defect_patterns.json`
让"历史翻车最多的维度"这一轮**一定被覆盖到**——权重 = Σ(等级权重 × 命中次数)，
被页面内容门槛挡住的高频维度会补出页面级场景（`source=pattern-deep`），表单校验类高发时
每个输入框的异常数据条数加深。产物里 `patternFeedback` 写明本轮加权了哪些维度、依据多少条
历史模式、加深了什么，报告可查。**边界同前：只影响覆盖与深度，不自动生成断言**（从一条历史
缺陷推不出修复后的正确行为）；场景顺序不变，保持 `S-xxxx` 编号稳定便于与已确认基线对照；
不传 `--patterns` 时输出与接入前完全一致。

### 7.39 多页用户旅程

逐页面走查看不到跨页流程里炸的问题。`scripts/node/run_journeys.cjs` 从起始页实时提取同源候选链接（排除危险词/下载/新标签页/锚点），BFS 有界点击走查（`--max-hops` / `--max-links-per-page` / `--max-visits` 防链接图爆炸），每步采集运行期观测（7.35–7.38 经 addInitScript 自动装钩）并判定落地页缺陷。判据：落地文档 4xx/5xx、落地页近空白、返回后近空白 → confirmed P1；链接点击无反应、已登录态被弹登录页 → pending（SPA 可能没渲染完/可能是设计使然，无确定证据不落缺陷）。完整边界见 `references/journeys.md`。

## 六、维度与检测手段对照

| 维度 | 静态探测（`extra_checks.js`） | 场景驱动 | 需要人工确认 |
|---|---|---|---|
| 7.24 图片适配 | 比例、加载失败、`object-fit` | 长图/缩略图切换 | 插画内容差异 |
| 7.25 暗色模式 | 媒体查询存在性、硬编码浅色 | emulate colorScheme=dark 后对比度复检（run_state_scenarios.cjs） | 深色稿配色 |
| 7.26 打印视图 | — | emulate media=print 后截断/按钮探测（run_state_scenarios.cjs） | 与打印稿比对 |
| 7.27 多行截断 | `line-clamp`、溢出高度 | 长文案注入 | 省略位置 |
| 7.28 控件细节 | 对比度、`autocomplete` | 边界值输入 | 原生控件外观 |
| 7.29 焦点可见性 | focus 前后样式差 | Tab 遍历 | 焦点顺序合理性 |
| 7.30 国际化 | RTL / emoji / 全角扫描 | 语言切换 | 译文长度合理性 |
| 7.31 滚动 UX | 固定栏遮挡、滚动锁 | 滚动到底、弹层开关 | 滚动条样式 |
| 7.32 状态残留 | — | hash 导航 + 返回后快照比对（run_state_scenarios.cjs） | 期望的保留/重置 |
| 7.33 接口异常 | — | 拦载 XHR fulfill 500 后探测（run_state_scenarios.cjs） | 提示文案 |
| 7.34 角色差异 | — | 多角色集合差集 | 权限设计意图 |
| 7.35 JS 异常 | 错误钩子（交互前后各一次） | 触发交互后采集 | 异常是否可忽略 |
| 7.36 网络失败 | 请求钩子（fetch/XHR） | 触发交互后采集 | 失败是否用户可感知 |
| 7.37 重复提交 | 请求时序分析 | 连续点击写按钮 | 是否本就有防抖设计 |
| 7.38 遮挡 | elementFromPoint 命中测试 | 无（静态即可） | 层级是否设计内 |

> 表中「—」表示必须靠场景驱动，不表示可以不查；未跑就填 `notRun` 并写明原因。

