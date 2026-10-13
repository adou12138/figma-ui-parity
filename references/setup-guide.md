# 配置与环境检查

本指南覆盖 `figma-source`、`playwright`、`visual-parity`、`python-runtime` 和 `report-export` 五项依赖。

## 必需输入

- Figma 设计稿 URL。
- 页面 URL。
- 访问受保护页面时使用已有 storage state、Cookie 或人工登录；不提供密码给 Skill。
- **本次交互安全策略选择**：测试开始前必须询问并获得用户选择，不得继承历史运行。选项为：`全部操作`（用户确认是隔离测试环境，所有分级均执行）、`安全操作`（只执行 safe）、`写操作拦截`（safe 真执行，caution 拦截写请求后执行）或 `仅静态检查`（不执行交互）。

### 交互安全策略确认

在环境初始化完成、访问页面或生成场景前，用 `AskUserQuestion` 询问：

> 本次 UI 测试采用哪种交互安全策略？

| 选择 | manifest 值 | 可执行范围 | 必须标记 notRun 的范围 |
|---|---|---|---|
| 全部操作 | `all` | safe、caution、danger 全部分级，允许真实写入、删除、清空、支付、退款、解绑和下线 | 无；但必须记录 `testEnvironmentConfirmed=true`、动作前后证据和不可逆风险 |
| 安全操作 | `safe` | safe 分级点击及页面还原 | caution 与 danger 操作 |
| 写操作拦截 | `mockWrites` | safe 点击；caution 先拦截非 GET/HEAD/OPTIONS 请求再点击 | danger 操作 |
| 仅静态检查 | `staticOnly` | DOM、截图、样式、ARIA、无副作用探测 | 全部点击、键盘输入、表单校验、路由往返与浮层打开 |

将用户原始答复、规范化模式、写请求策略和由此受影响的维度写入 `run-manifest.json`。选择 `全部操作` 时还必须写入 `testEnvironmentConfirmed=true`，表示用户确认当前页面属于隔离测试环境；确认后允许执行包括不可逆动作在内的全部分级操作，并必须记录每个高风险动作的操作前后证据、请求/响应摘要和恢复性。未确认不得启用 `all`。用户未选择时不得启动交互测试，也不得把 `safe` 当作默认值。

### 最小可行跑法

| 手上有什么 | 能跑到哪一步 | 必须标注的未覆盖 |
|---|---|---|
| 只有页面 URL | 页面盘点、按钮可用性、响应式、可访问性、资源与偏好维度、运行期观测（7.19–7.38 中不需设计稿的部分） | 7.1–7.8、7.23 全部 `notRun:未提供设计稿`；不得产出"还原度"结论 |
| 只有设计稿导出（PNG/JSON） | 设计侧模型、字段换算、像素 diff 准备 | 无页面数据 → 除设计侧检查外全部 `notRun` |
| 设计稿 + 页面 | 全流程 | 按实际执行情况填覆盖率 |
| 设计稿 + 页面 + 多角色凭据 | 全流程 + 7.34 | — |

去掉 Figma URL 时，报告标题不得写"还原度对比"，只能写"页面 UI 走查"。

## 测试启动门禁

环境检查不是 Skill 加载动作。只有用户明确启动 UI parity 测试，或同一轮同时提供 Figma URL 与页面 URL 时，才调用 `scripts/start_test.py`。单纯咨询依赖、查看配置或只提供单个 URL 不触发。

启动前由编排层使用 `AskUserQuestion` 取得本轮安全策略，再传给门禁；门禁缺少策略时阻断，不默认使用 `safe`：

```bash
python scripts/start_test.py --instruction "<原始指令>" \
  --figma-url "<Figma URL>" --page-url "<页面 URL>" \
  --safety-policy <all|safe|mockWrites|staticOnly> \
  --user-safety-selection "<原始选择>" [--test-environment-confirmed]
```

门禁成功后才可访问页面、恢复登录态或执行交互，并将环境检查和安全策略写入 `parity-test/run-manifest.json`。

## 凭据与工作目录（先做这一步）

```bash
python scripts/init_workdir.py --root .
```

- 建立 `parity-test/{reports,baselines,shots,extract,button-audit,baseline/runs}` 与 `parity-test/.auth/`。
- 向工作区 `.gitignore` 追加 `parity-test/`、`.auth/`、`*.storage.json`、`*.cookies.json`、`auth_info.json`、`.vp_profile*/`。**只追加缺失行，不改写已有内容**。
- 凭据只落 `parity-test/.auth/`，报告、日志与对话均不得出现 Cookie 或 token 原文；失败重登时删除旧文件再登录。

## figma-source

官方主页：https://www.figma.com/；官方文档：https://www.figma.com/developers/api；登录：https://www.figma.com/login；设置入口：https://www.figma.com/settings。

优先使用已连接的 Figma MCP。MCP 不可用时，使用用户已配置的 Figma REST token。按“Account settings → Personal access tokens”创建最小只读 token，写入受信任 WorkBuddy MCP 配置。运行只读用户探测验证；token 失效时在官方设置中轮换或撤销。token 不得回显、写入报告或提交仓库。

## playwright

官方主页：https://playwright.dev/；官方文档：https://playwright.dev/docs；认证说明：https://playwright.dev/docs/auth。需要浏览器导航、调整视口、执行页面脚本、截图和存储态能力。登录优先恢复已有 storage state；无 storage state 时请用户在可见浏览器中完成登录。禁止自动填充密码、验证码或绕过登录。认证状态只保存在 workspace storage state，失效时删除后重新人工登录。

## visual-parity

官方参考：https://playwright.dev/docs/screenshots。可选连接，用于整页及区块像素/样式 diff；连接后运行 `compare_pages` 探测。不可用时降级为 Playwright 截图和 computed style，对报告标记 `partial`，不得声称像素级验证完成。

## python-runtime

官方下载：https://www.python.org/；官方文档：https://docs.python.org/3/。需要 Python 3.10+；运行 `python scripts/check_environment.py` 验证版本。用于环境检查、场景生成、证据归一化、基线和报告辅助。不读取凭据。

## report-export

CSV 官方参考：https://docs.python.org/3/library/csv.html。确认 `./parity-test/reports` 可写，执行只读创建/删除探测文件。报告只写 workspace 输出目录；写入失败时保留 JSON/HTML 或结构化标准输出，不伪称 CSV 已生成。

## 国内环境（代理与镜像）

大陆网络访问 Figma 官方服务与下载 Playwright 浏览器常不稳定，首次搭建容易卡在依赖。按下列顺序处理，仍不通再走离线降级（见各依赖段「不可用时降级」）。

### 1. Figma API / 页面访问

- Figma REST API（`api.figma.com`）与 `figma.com` 在大陆通常需要**代理或合规 VPN**；优先在公司网络或已配置代理的终端运行。
- 给运行环境设置代理（不影响 token 本身）：

```bash
# 仅对该会话生效；不要写进仓库或报告
export HTTPS_PROXY=http://<代理host>:<port>
export HTTP_PROXY=http://<代理host>:<port>
```

- 若使用 Figma MCP，确认 MCP 宿主进程继承了上述代理环境变量；MCP 不可用时，`run_official_extraction.cjs` 走 node 路径同样继承代理。

### 2. Playwright 浏览器下载（国内镜像源）

Playwright 默认从 `playwright.azureedge.net` 下载 Chromium，大陆常超时。改用国内镜像：

```bash
# 国内镜像（任选其一，推荐 npmmirror）
export PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright
# 或
export PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright

# 再安装浏览器
npx playwright install chromium          # 独立使用 playwright 时
# node 兜底路径（run_official_extraction.cjs）依赖 playwright-core：
npm i playwright-core && node -e "require('playwright-core')"   # 其浏览器仍走上面的 DOWNLOAD_HOST
```

> 若浏览器已装在非默认目录，用 `PLAYWRIGHT_BROWSERS_PATH` 指向它，`resolveChrome()` 会优先读取（Windows/macOS/Linux 路径均已支持）。

### 3. npm 镜像（安装 playwright-core / playwright 时）

```bash
npm config set registry https://registry.npmmirror.com
```

### 4. 仍不可用的兜底

- Figma 拿不到：用设计稿导出的 **PNG/JSON** 走「只有设计稿导出」最小可行跑法（见上文表格），相关还原度维度标 `notRun`。
- 浏览器装不上 / 页面打不开：放弃像素级对比，降级为 Playwright 截图 + computed style，报告标记 `partial`，不得声称像素级验证完成。

## 验证与恢复

先运行：

```bash
python scripts/check_environment.py
```

只读检查不安装、不修改 MCP、不登录。返回 `ready`、`partial`、`needs_setup` 或 `unavailable` 后按结果路由。服务超时最多有限重试；认证失败回到授权恢复；核心设计数据、页面权限或对象匹配缺失时停止受影响阶段。
