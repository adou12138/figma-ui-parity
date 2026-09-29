# 登录态多信号检测（步骤 3.2 详细版）

本文件由 SKILL.md 步骤 3.2 下沉而来。

#### 3.2 跳转到测试页面 & 多信号登录态检测

1. **导航到测试页面**：使用 `browser_navigate` 打开用户提供的本地/远程页面 URL。

2. **多信号登录态检测**（增强版，避免误判）：

```javascript
(() => {
  const url = window.location.href;
  const urlLower = url.toLowerCase();

  // 信号 1：URL 关键词检测（扩展匹配范围）
  const loginUrlPatterns = /\/(login|signin|sign-in|auth|sso|oauth|callback|account\/login)\b/i;
  const isLoginUrl = loginUrlPatterns.test(urlLower) || urlLower.includes('login');

  // 信号 2：DOM 结构检测（查找登录表单特征元素）
  const loginFormSignals = [
    'input[type="password"]',           // 密码输入框
    'input[name*="password" i]',
    'input[name*="passwd" i]',
    'button[type="submit"][formaction*="login" i]',
    '[class*="login-form" i]',
    '[class*="signin" i]',
    '[id*="login-form" i]',
    'form[action*="login" i]',
    '[class*="qrcode" i]',              // 扫码登录
    '[class*="captcha" i]'              // 验证码
  ];
  const hasLoginForm = loginFormSignals.some(sel => document.querySelector(sel));

  // 信号 3：body 文本检测（更严格，避免"修改密码"等误判）
  const bodyText = document.body ? document.body.innerText.substring(0, 500) : '';
  const loginTextPatterns = /^(请登录|用户登录|扫码登录|请输入账号|请输入密码|忘记密码|登录注册)/m;
  const hasLoginText = loginTextPatterns.test(bodyText);

  // 信号 4：业务内容检测（确认页面有实际业务内容）
  const businessSignals = ['main', '#app', '.app', '[class*="content"]', '[class*="dashboard"]', '[class*="page"]'];
  const hasBusinessContent = businessSignals.some(sel => {
    const el = document.querySelector(sel);
    return el && el.children.length > 0;
  });

  // 综合判定
  const isRedirectedToLogin = (isLoginUrl && !hasBusinessContent) || (hasLoginForm && !hasBusinessContent) || (hasLoginText && !hasBusinessContent);

  return JSON.stringify({
    url,
    isLoginUrl,
    hasLoginForm,
    hasLoginText,
    hasBusinessContent,
    isRedirectedToLogin,
    bodyPreview: bodyText.substring(0, 200)
  });
})()
```

3. **处理结果**：
   - `isRedirectedToLogin === true`：登录态未生效，返回步骤 3.1 重新登录。
   - `isRedirectedToLogin === false`：登录态有效，继续步骤 3.3。
   - 边界情况（如 `hasLoginForm` 和 `hasBusinessContent` 都为 true）：可能是页面内嵌了登录入口，按业务页面处理，继续提取。

4. **等待页面完全加载**：

```javascript
(() => {
  const main = document.querySelector('main, .app, #app, .container, [class*="content"]');
  if (!main) return 'loading';
  // 检查是否有异步加载的占位符
  const hasSkeleton = document.querySelector('[class*="skeleton" i], [class*="loading" i], [class*="spinner" i]');
  return hasSkeleton ? 'loading' : 'ready';
})()
```

   - 若返回 `loading`，等待 2 秒后再次检查；最多重试 5 次（共约 10 秒）。
   - 10 秒后仍未加载：提示用户"页面加载较慢"，继续提取（部分元素可能缺失）。

