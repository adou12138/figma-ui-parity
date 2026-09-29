# 按钮可用性与双向盘点（步骤 7.22 / 7.23 详细版）

**为什么必须单独查**：视觉一致 ≠ 能点。按钮尺寸、颜色、图标全部对得上，仍可能点不动——被透明遮罩盖住、`pointer-events:none`、事件绑定丢失、`disabled` 没随状态更新、点了毫无反应。这类问题截图对比与像素 diff 都发现不了，只能靠真实交互验证。

---

## 一、7.22 按钮可用性与点击生效

### 1.1 三层判定

| 层 | 断言 | 判定 | 等级 |
|---|---|---|---|
| **可点击性**（静态） | `disabled` / `aria-disabled=true` / class 含 disabled | 存在即为不可点【注 1】 | 中 |
| | `pointer-events:none` | 存在 → 不可点 | 高 |
| | `visibility:hidden` / `display:none` / `opacity:0` | 存在 → 不可点 | 高 |
| | 渲染尺寸为 0（w 或 h < 1px） | 存在 → 不可点 | 高 |
| | **命中测试**：中心与 4 个内缩采样点 `elementFromPoint` 是否命中自身或其子元素 | 全部未命中 → **被遮挡**，记 `blocker` | 高 |
| | `cursor` 不是 `pointer`（原生 button 除外） | 不一致 → 低（观察项） | 低 |
| **生效性**（动态） | 点击后限时窗口内是否出现任一信号（见 1.3） | 全无信号 → **点击无响应** | 高 |
| **还原** | 点击后页面状态是否回到点击前 | 未还原 → 脚本缺陷，必须修 | — |

> 【注 1】`disabled` 本身不一定是缺陷——若设计稿此处就应为禁用态（如未填必填项时的提交按钮），则属正确实现；**只有"设计为可点、实际不可点"才记缺陷**。判定前必须先与设计稿该按钮的状态比对。

### 1.2 风险分级与安全策略（核心）

点击会改数据的按钮必须按风险分级处理，**禁止无差别真点**。在开始任何点击审计前，必须读取本次 `run-manifest.json` 的 `safetyPolicy`；未记录或值为 `unselected` 时停止本节并将 7.22、7.14、7.17、7.18、7.19 中依赖交互的子项标记为 `notRun:未获得本次安全策略授权`。不得继承任何历史会话的选择。若值为 `all`，还必须读取 `testEnvironmentConfirmed=true`；缺少该确认时拒绝执行 caution/danger 操作。

| 级别 | 识别关键词（按钮文本 / title / aria-label） | 处理方式 |
|---|---|---|
| **safe** | 查询、搜索、筛选、展开、收起、上一页、下一页、分页、查看、详情、刷新、全部、切换、取消、关闭、导出、下载、复制 | **真点击** + 观察信号，点后 `goto(url)` 还原 |
| **caution** | 保存、提交、确定、确认、创建、新建、添加、新增、导入、上传、发送、同步、发布、启用、开启、绑定、购买、续费、修改、编辑、更新、应用、分配、授权、合并、移动、转移、设为、重置 | 默认拦截写请求并 mock 成功后点击，只看前端反应，不真正落库；`all + testEnvironmentConfirmed=true` 时按用户授权允许真实执行 |
| **danger** | 删除、移除、移出、清空、退出、注销、停用、禁用、解散、撤销、解绑、退款、支付、结算、批量删除、下线、作废 | 默认不点击，只做静态可点击性检查；仅 `all + testEnvironmentConfirmed=true` 时允许真实执行，并记录操作前后证据及不可逆风险 |

**用户策略对分级的覆盖规则**：

0. `all`：仅在 `testEnvironmentConfirmed=true` 时执行 safe、caution、danger；危险操作必须保留操作前状态、目标元素、请求/响应摘要、操作后状态、恢复性和风险说明，不得在未确认测试环境时降级默认为可执行；
1. `staticOnly`：所有级别均不点击，仅输出静态可点击性；
2. `safe`：只执行 safe；caution/danger 均不点击；
3. `mockWrites`：safe 真点击；caution 仅在非 GET/HEAD/OPTIONS 请求被 mock 或 abort 后点击；danger 不点击；
4. `all` 且 `testEnvironmentConfirmed=true` 时，允许执行 danger；必须在 `clickResults` 和报告中记录操作前状态、目标选择器与 `nth`、请求/响应摘要、操作后状态、是否可恢复及风险说明。其他策略下 danger 均不得点击，只做静态检查并标记未执行原因。

**分级规则**（脚本已实现，判定顺序不可颠倒）：
1. `danger` 优先于 `caution`（如"删除并保存"→ danger）；
2. 无文本的图标按钮：先取其 `title` / `aria-label` 分级；**两者都没有 → 按 caution**（不知道是"关闭"还是"删除"，保守处理）；
3. 关键词表可扩展，但**只允许往更保守的方向调**（把 safe 误判成 caution 的代价是慢，反过来是数据事故）。

**拦截写请求的实现**（caution 级必做，脚本默认 `--write-policy mock`）：

```js
// 点击前安装：非 GET 一律拦下，不让写请求真正到达后端
await context.route('**/*', async route => {
  const req = route.request();
  const m = req.method().toUpperCase();
  if (m === 'GET' || m === 'HEAD' || m === 'OPTIONS') return route.continue();
  intercepted.push({ method: m, url: req.url() });
  if (policy === 'abort') return route.abort();                     // 绝不发往后端
  return route.fulfill({ status: 200, contentType: 'application/json',   // 默认：mock 成功
    body: JSON.stringify({ code: 0, data: null, msg: 'parity-probe-mocked' }) });
});
```

> 拦截本身也是**证据**：`intercepted` 里有记录即说明"点击确实发出了请求"，是"生效"的强信号。
>
> **注意前端读类 POST**：部分后台用 POST 查询（列表刷新）。被 mock 后前端会拿到空数据，**表现为 DOM 变化 → 仍算生效信号，不会误判为"无响应"**；但若该按钮的验证结论需要依赖真实数据渲染，改用 `--write-policy abort` 或先记录后判断。被 mock/中断的 URL 全部写入 `button_audit.json` 的 `clickResults[].effect.intercepted`，便于事后核查。

### 1.3 生效信号（任一命中即判「生效」）

| 信号 | 采集方式 |
|---|---|
| URL / hash 变化 | 点击前后 `location.href` 比对 |
| DOM 变化 | 点击前后 `document.body.innerHTML.length` 或目标容器子节点数变化 |
| **可见元素数变化** | 点击前后统计"可见元素数量"（排除 `display:none` / `visibility:hidden` / `opacity:0`）——**预渲染弹窗靠 CSS 显隐切换时，innerHTML 长度与节点数都不变，只有这个信号会变**，缺它就必然把"点击后弹窗"误判成"点击无响应" |
| **浮层新增** | 按 class/id 关键词（`modal/dialog/popup/overlay/layer/mask/drawer/wjxui-`…）+ `position:fixed/absolute` + `z-index ≥ 100` + 尺寸占比，取点击前后的浮层签名**差集** |
| 发出请求 | `page.on('request')` + 上文的 `intercepted` |
| 写请求被拦 | `intercepted` 非空（既是安全机制，也是"生效"的强证据） |
| 弹窗 / 浮层出现 | 新增可见的 `[class*=modal],[class*=dialog],[role=dialog],[class*=popup]` |
| 提示出现 | 新增 `[class*=toast],[class*=tip],[class*=message],[class*=notice]` |
| JS 弹窗（alert / confirm） | `page.on('dialog')`（需预先接管，否则脚本挂起） |
| 选中态/展开态变化 | 目标元素自身 `class` / `aria-expanded` / `aria-selected` 变化 |
| 新标签页 | `context.on('page')`（需预先接管） |
| 下载 | `page.on('download')`（需预先接管并 cancel） |

**观察窗口 800–1500ms**：过短会漏掉异步请求，过长会让整轮耗时爆炸。发出请求但被 mock 拦截，同样算生效。

### 1.4 还原纪律

- 只要出现**任何可观测副作用（含弹窗/浮层的显隐、可见元素数变化）就必须 `page.goto(url)` 重新加载**再测下一个按钮——否则残留弹窗会遮挡后续按钮，把它们**连锁误判**成"不可点击"（实测踩过：一个信号漏检同时造成"点击无响应"和后续按钮"不可点击"两个假阳性）；
- 被判「被遮挡」的按钮**仍要实测点击一次**再下结论：点得动且生效 → 原判定过严、按正常处理；点不动 → 才记确认不可点击。**静态推断不作为最终结论**；
- `danger` 级跳过点击，无需还原；
- 单页按钮多时（>30），可只对"每组首个"做完整点击验证，其余做静态检查，并在报告中注明抽样比例（**不得静默减量**）。

### 1.5 弹窗钻取（点击触发弹窗后必须补盘）

弹窗内按钮在弹窗**未打开**时尺寸为 0、属「不可观测」，主盘点根本拿不到它们。凡点击后有弹窗 / 浮层出现，必须补一轮：

1. 取当前可见浮层（`position:fixed|absolute` + `z-index ≥ 100` + 尺寸 ≥ 20% 视口），按 z-index 降序、同层取小面积者，最多 3 个；
2. 以该浮层元素为**作用域根**重跑一次按钮盘点（脚本通过 `window.__AUDIT_SCOPE` 注入作用域），结果记入 `modalButtons`（作用域选择器 + 尺寸 + 弹窗内按钮清单 + 各按钮可点击性）；
3. 弹窗内按钮的**可点击性**照常判定；是否点击其中按钮按与主盘点相同的风险分级决定；
4. 盘点完必须关闭弹窗（ESC / 点遮罩 / 关闭按钮）并 reload 兜底。

> 不钻取的后果：弹窗内按钮全部落进「隐藏容器内」被记为不可观测，等于**这批按钮从未被验证**——而它们往往正是关键操作（确定 / 保存 / 提交）。

### 1.6 误报防线（实测踩坑）

1. **命中测试必须多点采样**：圆角按钮的四角在 bbox 内但落在圆角外部；带图标按钮的几何中心可能正好落在图标上——单点判定会大量误报。脚本默认 5 点采样（中心 + 四向内缩 25%）。
2. **视口外元素先 `scrollIntoView`**：未滚动到的元素 `elementFromPoint` 必然返回 `null`，会被误判为"不可点击"。脚本对 `out-of-viewport` 返回 `ok:null` 并说明需先滚动，**不直接判缺陷**。
3. **点击前必须接管 dialog / 新标签页 / 下载**：`js confirm`、`target=_blank`、`Content-Disposition` 三类会让脚本挂起或超时，表现为"点击无响应"的假阳性。
4. **小心 `label`/`span` 套在按钮里**：`[onclick]` 选择器可能命中按钮内的子节点，需按 1.1 的容器排除规则去掉重复项（脚本已按"含 ≥2 个按钮类子元素即视为容器"过滤）。
5. **点击超时不等于不可点击**：`locator.click()` 超时可能因为元素被遮挡、也可能因为元素在动画中。需先跑静态命中测试；静态通过而点击超时 → 记为"疑似被遮挡"，人工复核后再定性。
6. **隐藏容器内的按钮不是"不可点击"**：弹框 / 抽屉未打开时，其内部按钮 `display:none` 或尺寸为 0，会被误判成"不可点击"。必须用 `checkVisibility()` 判定真实可见性，把这类归为**「不可观测」并从可点击性统计中剔除**——它们的验证由 7.14 弹框走查覆盖。实测某页 114 个按钮里 88 个属此类，若不剔除就会得出"92/114 不可点击"的荒谬结论。
7. **重复按钮必须按组归并**：列表每行一个「编辑」，实测 27 个按钮里 20 个是行内重复项。按 (归一化文本 + 风险 + 标签 + 可点击性) 归并，只点每组的代表并记 `duplicateCount`，否则既浪费时间又让统计虚高。
8. **「设计有页面无」必须做双通道证据回查**：先查页面按钮盘点，再查可见完整文本。页头 tab 常用 `a` / `li` 实现、不在按钮枚举选择器内，会被误报成「按钮缺失」。设计稿按钮命中页面按钮清单时记录 `matchedBy=buttonInventory`；仅命中完整文本时记录 `matchedBy=fullText`、`nonStandardEntry=true`，记为「以非按钮形式存在」交人工确认，**不得直接判缺失**；只有按钮清单和完整文本都未命中时，才记录 `matchedBy=none` 并进入 `missingInPage`。底部或弹窗按钮即使叶子文本提取遗漏，只要页面按钮盘点命中，也必须判定为存在。
9. **`[onclick]` 泛匹配必须分级**：它能捞到真实按钮，也会把字段 chip、可点行、`li` 项一并捞进来（实测某设置页 44 个"按钮"里 33 个是字段 chip）。按 `source` 分级——`button` / `[role=button]` / `input[type=submit|button|reset]` / 含 btn 类名 = **标准按钮**（进判定与配对）；其余 = `generic` **疑似可点元素**，单独成表、默认不点击、不参与按钮配对。
10. **点击必须用 `sel` + `nth`**：同一选择器常命中多个元素（列表每行的按钮），只记 `sel` 会让点击落到错误的元素上——实测曾因此把字段值点到并触发下载，得出完全错误的结论。
11. **判定用语要区分三件事**：「点击抛错」（Playwright 超时/不可交互）、「点击成功但无任何反应」（无信号）、「静态即不可点击」。三者根因与等级都不同，报告里不可混为一谈。

---

## 二、7.23 按钮双向盘点（设计稿 ↔ 页面）

**目的**：不只验页面上的按钮，还要确认**设计稿里的按钮一个都没少**、**页面多出的按钮也已验证**——两侧都要盘。

### 2.1 设计稿侧提取

从 Figma `file.json` 遍历，识别按钮语义节点（名称含 `btn`/`button`/`按钮`，或"小尺寸帧 + 内含居中文本 + 有圆角/填充"）：

```js
// node 片段：从已下载的 file.json 提取设计稿按钮清单
const fs = require('fs');
const d = JSON.parse(fs.readFileSync('parity-test/figma-<key>/file.json', 'utf8'));
const RE_NAME = /btn|button|按钮/i;
const out = [];
(function walk(n, frame) {
  const b = n.absoluteBoundingBox || {};
  const isBtnName = RE_NAME.test(n.name || '');
  const hasText = (n.children || []).some(c => c.type === 'TEXT' && c.characters);
  const smallEnough = b.width > 0 && b.width < 420 && b.height > 0 && b.height < 96;
  const rounded = !!n.cornerRadius || (Array.isArray(n.rectangleCornerRadii) && n.rectangleCornerRadii.some(v => v > 0));
  if (isBtnName || (smallEnough && hasText && rounded && /FRAME|COMPONENT|INSTANCE/.test(n.type))) {
    const t = (n.children || []).filter(c => c.type === 'TEXT').map(c => c.characters).join(' ');
    out.push({ nodeId: n.id, name: n.name, text: String(t).trim().slice(0, 40),
      x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height), frame });
  }
  for (const c of (n.children || [])) walk(c, frame || n.id);
})(d.document, null);
fs.writeFileSync('design_buttons.json', JSON.stringify({ count: out.length, buttons: out }, null, 2));
```

> 设计稿按钮提取会带噪声（把"标签胶囊""输入框"误当按钮）。**噪声无害**：配对阶段找不到页面对象时会落入"设计有、页面无"，报告里必须逐条人工确认是"真缺失"还是"设计稿对象识别偏差"后再定级。

### 2.2 页面侧盘点

用 `scripts/button_audit.js` 产出 `buttons[]`（含 `normText` / `near` / `bbox` / `risk` / `clickable`）。

### 2.3 配对规则

1. **文本为主键**：`normText` 归一化（去空白、零宽字符、图标字符）后精确匹配；
2. **位置为辅**：文本匹配到多个时，取 y 轴距离最小的；同 y 带（±40px）内 x 距离最小者优先；
3. **图标按钮**：无文本时用 `title` / `aria-label` 与设计稿节点名比对；仍无法配对 → 记 `pendingChecks`（异构不可自动判）。

### 2.4 三种结论与处理

| 结论 | 判定 | 等级 | 是否跑 7.22 |
|---|---|---|---|
| **成对** | 文本 + 位置匹配成功 | 逐项比对视觉（7.1 / 7.5 按钮 container） | ✅ **必须跑** |
| **设计有、页面无** | 设计稿按钮在页面找不到配对 | 高（按钮缺失）；若属"隐藏态"则降为观察项 | —（先查是否仅当前状态隐藏） |
| **页面有、设计无** | 页面按钮在设计稿找不到配对 | 待确认（`pendingChecks` 交产品/设计确认），**不直接判缺陷** | ✅ **必须跑** |

> **关键纪律**：**无论是否与设计稿成对，页面上每个按钮都必须跑一遍 7.22**。设计稿没画的按钮（如"分组管理""同步记录"这类入口）同样是真实用户会点的，**不能因为"设计稿没有"就成为漏测盲区**——设计遗漏本身记一条"设计未提供参照"，而按钮的可用性照验不误。

### 2.5 与相邻检查项的边界

| 检查项 | 关注点 | 与本节关系 |
|---|---|---|
| 7.5 图标成对比对 | 按钮内图标的形状/颜色 + 按钮视觉（文字/背景/边框/圆角） | **视觉**；本节负责**功能**，两者都要跑 |
| 7.17 表单校验与错误态 | 未满足校验时提交按钮应禁用 | 属于"状态正确性"；本节验证"该禁用时真的禁用、该可点时真的可点" |
| 7.18 浮层与层级交互 | 弹框层级、关闭行为 | 本节"点击生效"会顺带覆盖弹框能否打开 |
| 7.19 可访问性 | 键盘可达、焦点可见、可读名称 | 本节只验鼠标点击路径，键盘路径归 7.19 |
| 7.20 禁用态 | disabled 的样式与点击行为 | 本节复核 disabled 的**实际拦截效果** |

---

## 三、脚本用法

```bash
# ① 页面侧静态盘点（只读，零风险）
node scripts/node/run_button_audit.cjs --url "https://目标页" \
  --profile "./parity-test/.vp_profile" --out "./parity-test/button-audit"

# ② 含点击生效验证（默认点 safe + caution，caution 自动拦截写请求）
node scripts/node/run_button_audit.cjs --url "https://目标页" \
  --profile "./parity-test/.vp_profile" --out "./parity-test/button-audit" --click

# 可选： --max 20（每页最多点 20 个，默认 40） · --include-danger（危险按钮也点，仅测试环境使用）
#       --headed（有头，需人工登录时） · --no-restore（点击后不 reload，默认 reload）
```

输出：`button_audit.json`（静态盘点 + 点击结果 + 设计稿配对）+ `button_audit.png`（截图留档）。

---

## 四、报告落点

**JSON**：`report.json` 增加 `buttonAudit`。设计按钮配对项必须包含 `matchedBy`（`buttonInventory` / `fullText` / `none`）；`fullText` 命中项必须包含 `nonStandardEntry=true`：

```json
{
  "buttonAudit": {
    "count": 32,
    "riskSummary": { "safe": 20, "caution": 9, "danger": 3 },
    "notClickable": 2,
    "clicked": 29, "skippedDanger": 3, "noEffect": 1,
    "missingInPage": [{ "name": "输入用户名搜索", "nodeId": "1:512", "symptom": "设计稿有搜索框按钮，页面找不到对应控件（页面改用「用户分组」下拉）" }],
    "extraInPage":  [{ "sel": "#btnGroupManage", "text": "分组管理", "symptom": "页面有「分组管理」按钮，设计稿未提供该入口（设计遗漏，待确认）" }],
    "noEffect": [{ "sel": ".comBtn-sync", "text": "立即同步", "symptom": "点击后无任何反馈：URL 未变、无请求、无提示、无 DOM 变化", "element": { "selector": ".comBtn-sync", "bbox": { "x": 980, "y": 512, "w": 88, "h": 32 }, "anchor": "立即同步" } }]
  }
}
```

**Excel**：新增两种缺陷类型——`按钮可用性`（不可点击 / 点击无响应 / 被遮挡）与 `按钮缺失`（设计有页面无）。页面多出的按钮记「待确认问题」sheet，**但它在 7.22 的验证结论照常写入 UI 缺陷清单**（功能问题不因设计缺失而免于记录）。

**HTML**：单列「按钮可用性与盘点」章节，列出：按钮总数 / 风险分布 / 不可点击清单（附遮挡元素）/ 点击无响应清单 / 设计有页面无 / 页面有设计无。

**缺陷描述写法**：遵循步骤 7.11 的「问题现象 + 指标」双段式——先写现象（如"「立即同步」点击后页面毫无反应"），再给指标（selector + bbox + 命中测试 / 请求 / DOM 变化结果）。
