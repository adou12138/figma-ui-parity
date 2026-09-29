# 有头浏览器登录兜底方案（Playwright MCP 无头时手动登录）

## 何时用本方案

满足以下全部条件时，走本方案而不走 SKILL.md 步骤 3.1 的「方式 B 手动登录」：

- 目标页**需要登录**，且你手头**没有可用的登录 Cookie / storage state**（方式 A 注入登录态不可用）；
- 必须让用户**手动登录**，但当前 `mcp__playwright` 是以 `--headless` 启动的——用户桌面上**没有可见窗口**，无法点击登录，方式 B 变成死路；
- 此时用 `playwright-core` 自己起一个**有头浏览器**让用户登录，登录后在同一进程里自动提取页面、截图。

> 若用户能提供 Cookie / storage state，优先用方式 A 注入，不要走本方案。

## 前提：先探测本机是否有显示器

`--headless` 往往是 setup 时"想当然"加的，实际可能误设。先确认本机是否真有桌面：

```bash
tasklist 2>/dev/null | grep -i explorer   # 看到 explorer.exe 在 Console 会话 → 有桌面
qwinsta 2>/dev/null                        # 看是否存在 Console / Active 会话
netstat -ano 2>/dev/null | grep LISTENING | grep -i chrome  # 可选：看 chrome 调试端口
```

- 有 `explorer.exe` 跑在 Console 会话 → 本机有桌面，**可起有头浏览器**；
- 纯服务器无显示器 → 此路不通，回退请用户**必须提供 Cookie**，否则无法继续。

## 定位本地 Chromium 二进制

Playwright 自带的 Chromium 在用户目录下，路径随版本号变化，先用 Glob / ls 找到确切位置：

```
# Windows 示例（版本号 1228 会随 playwright 升级变化，不要写死）
%LOCALAPPDATA%/ms-playwright/chromium-*/chrome-win64/chrome.exe
```

找到后作为 `executablePath` 传入启动参数。

## 启动有头浏览器（关键：必须加 `--no-sandbox`）

⚠️ **不加 `--no-sandbox` 时 DevTools / CDP 调试端口绑不上**（实测：9224 端口在加 `--no-sandbox` 后才进入 LISTENING，浏览器也常起不来）。这是本方案最容易踩的坑。

```js
// run_login.cjs  —— 需先 npm i playwright-core
const { chromium } = require('playwright-core');

(async () => {
  const browser = await chromium.launch({
    headless: false,   // 有头：用户可见窗口
    executablePath: process.env.PLAYWRIGHT_CHROME_PATH || undefined,
    args: ['--no-sandbox', '--window-size=1280,900']
  });
  const page = await browser.newPage();

  // 1) 先到登录页
  await page.goto('https://目标站点/Login.aspx?returnUrl=...', { waitUntil: 'domcontentloaded' });

  // 2) 注入醒目横幅，避免用户登录错窗口（桌面上可能还有其他残留空白窗口）
  await page.evaluate(() => {
    const bar = document.createElement('div');
    bar.textContent = '🤖 自动化对比测试窗口：请在此窗口登录…';
    bar.style.cssText = 'position:fixed;top:0;left:0;right:0;z-index:2147483647;background:#0095FF;color:#fff;padding:12px;font-size:15px;font-weight:bold;text-align:center;';
    document.body.appendChild(bar);
  }).catch(() => {});

  // 3) 轮询等登录（最长 15 分钟），每 5s 检查 URL 是否离开 Login.aspx
  const deadline = Date.now() + 15 * 60 * 1000;
  while (Date.now() < deadline) {
    await page.waitForTimeout(5000);
    if (!page.url().includes('Login.aspx')) break;
  }

  // 4) 登录成功后：跳目标页、用 scripts/extract_*.js 提取、截图、存 result.json
  await page.goto('https://目标站点/目标页', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  // page.evaluate(extract_containers) / extract_texts / extract_icons ...
  await page.screenshot({ path: 'target.png', fullPage: true });
  await browser.close();
})();
```

运行方式：用 Bash `run_in_background` 跑这一个脚本（见下方「关键纪律」）。

## 关键纪律：单一长驻进程

- **把"启动 → 轮询等登录 → 提取 → 截图"全部放在同一个 Node 进程里**，用 Bash 的后台模式（`run_in_background`）跑这一个脚本。
- ❌ 不要用 Bash 单独起一个 chrome 进程、再用别的工具跨调用重连 CDP 去控制它——实测外部浏览器进程会**跨工具调用崩溃**，调试端口也连不上，整条链路会断。
- 登录态打通后，后续的提取脚本（`scripts/extract_containers.js` 等）用 `page.evaluate` 内联执行即可，无需重新起浏览器。

## 回退判定矩阵

| 条件 | 走法 |
|------|------|
| 有 Cookie / storage state | 方式 A 注入，无需本方案 |
| 无 Cookie + 本机有桌面（explorer.exe 在 Console 会话） | 本方案：有头浏览器手动登录 |
| 无 Cookie + 纯无头服务器 | 请用户务必提供 Cookie，否则无法继续 |

## 其他实战陷阱（同源，顺带记此）

- **URL 转写陷阱**：长对话被压缩成摘要时，测试页面 URL 可能被转抄错（例：把 `addressbooksetting.aspx` 写成 `addressbooksettingsettings.aspx`）。应以**用户原始消息**为准，实测返回 404 / 资源不存在即证伪，别被摘要带偏。
- **webReader 类服务端抓取器不适用登录页**：这类工具是服务端把 HTML 抓回来，不维持登录态、不执行需登录的交互，对登录页必然失败（500）。只能走真实浏览器，不要拿它取需登录的页面。
- **`input[type=password]` 不等于登录页（误报陷阱）**：业务页面本身就可能含密码输入框（实测：通讯录设置页的「成员字段管理」列出了"密码"字段，页面 `pwdCount=1`）。若把"存在密码框"单独当登录页判据，会把**已登录的真实页面**误判成登录页，导致脚本死等在"等待登录"、或把登录页当结果存下来。**正确做法**——登录页判定必须多信号组合，且密码框只是**弱信号**：
  1. URL 含 `login` / `signin`（最强信号，直接用）；
  2. 正文含"未登录 / 您还未登录 / 请先登录"；
  3. 登录页专属文案：立即注册、忘记用户名、验证码登录、账号登录；
  4. `input[type=password]`（仅作辅助，**不可单独使用**）。
  ⚠️ `用户服务协议` 这类词会出现在普通页面页脚，**不能**单独作为登录页特征。
- **判定时序：`goto` 后必须等重定向稳定再判**：`page.goto(目标页)` 后若立即判定，页面往往还没完成到 `Login.aspx` 的重定向，`document.body` 为空导致所有信号落空 → 误判"已登录"。做法：`goto` 后先 `waitForTimeout(4000)` 再判定；并且**在最终提取前再复核一次**，若仍是登录页就回到等待循环（重试上限 2 次），并加 `ABORT` 兜底——**绝不允许把登录页当作目标页存成结果**。
- **用持久化 profile + storageState 双保险避免重复登录**：`chromium.launchPersistentContext(userDataDir, {...})` 会保留**持久** cookie，但 **Chromium 的会话 cookie（session cookie）默认不落盘**——浏览器一关就丢，很多站点（实测 `tl.sojump.cn`）的登录 token 正是会话 cookie，所以**只靠 profile 仍会掉登录、卡在登录页**。必须叠加下面的「登录态持久化」。注意 profile 被占用时无法再启动，清理残留进程时需按 `--user-data-dir` 精准匹配，勿误杀用户自己的浏览器。

## 登录态持久化（多轮浏览器免重复登录）—— 必做

**症状**：重启浏览器后需要重新登录、脚本卡在登录页 / 拿到「系统提示」页，多轮测试反复失败。

**根因**：会话 cookie 不落盘（见上一节）。headless 与 headed 都受影响。

**做法**（`scripts/node/auth.cjs` + `save_auth.cjs`）：

1. 登录成功后保存：`await saveAuth(context, 'default')` → 写 `parity-test/.auth/auth.storage.json`（storageState：cookies + 各 origin 的 localStorage）、`auth.cookies.json`（**原始 cookies，保留 `expires=-1` 的会话 cookie**）、`auth_info.json`。
2. 每次启动**在首次导航前**恢复：`await restoreAuth(context)` → `context.addCookies(...)` 注入 cookies + `addInitScript` 注入 localStorage。
3. `scripts/node/run_official_extraction.cjs` 已内置：启动即 `restoreAuth`，登录校验通过后自动 `saveAuth` 刷新（保持 token 新鲜）。

```bash
# 首次/失效时手动登录并保存（需要窗口 → 加 --headed）
node scripts/node/save_auth.cjs --url "https://目标站/受保护页" --profile "./parity-test/.vp_profile" --headed

# 之后所有提取/截图脚本直接复用（无需登录）
node scripts/node/run_official_extraction.cjs --url "https://目标站/目标页" --profile "./parity-test/.vp_profile" --responsive --stabilize
```

**要点**
- 存放目录**按序探测**：`PARITY_AUTH_DIR` → `<cwd>/parity-test/.auth/` → `<cwd>/parity-test/*/.auth/` → `<cwd>/.auth/`，取首个已存在 `auth.storage.json` 的目录；都不存在时回落到 `<cwd>/parity-test/.auth/`。这样已存登录态无论落在哪个子目录都能被定位，避免"存了却找不到、又要重登"。随工作区走，勿写到用户主目录。
- `restoreAuth` 必须在首次 `goto` 之前调用；否则已发起的导航不会带上注入的 localStorage。
- token 会过期：`auth_info.json` 里的 `savedAt` 可用于判断是否需重新保存；每轮成功跑完会**自动刷新**。
- 无头也可用：只要 `auth.storage.json` 有效，`headless: true` 同样免登录（实测 4/4 页通过）。无头下若确实过期，会失败——此时用 `--headed` 跑一次 `save_auth.cjs` 重存即可。
- 安全：`auth.*.json` 含登录凭据，属敏感文件；不要提交到 git，工作目录清理时一并删除。

