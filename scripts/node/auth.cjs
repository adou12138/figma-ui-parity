#!/usr/bin/env node
/**
 * 登录态持久化（跨浏览器重启免重复登录）。
 *
 * 为什么需要：Chromium 的**会话 cookie 默认不落盘**，`launchPersistentContext` 的 profile
 * 在浏览器关闭后也会丢掉会话 cookie；只靠持久 profile，多轮开启浏览器仍会掉登录、卡在登录页。
 * 做法：登录成功后把 `context.storageState()` + 原始 cookies（含 session cookie）导出成文件，
 * 之后每次启动在导航前注入（cookies + localStorage），即可免登录继续。
 *
 * 存放位置：按序探测，取首个「已存在 auth.storage.json」的目录；都不存在时回落到 `<cwd>/parity-test/.auth/`
 *   顺序：`PARITY_AUTH_DIR` → `<cwd>/parity-test/.auth/` → `<cwd>/parity-test/<子目录>/.auth/` → `<cwd>/.auth/`
 *   - auth.storage.json（storageState：cookies + origins localStorage）
 *   - auth.cookies.json（原始 cookies，保留 expires=-1 的会话 cookie）
 *   - auth_info.json（保存时间/条数/域名，便于排查）
 *
 * 集成用法：
 *   const { restoreAuth, saveAuth } = require('./auth.cjs');
 *   const context = await pw.chromium.launchPersistentContext(profile, {...});
 *   await restoreAuth(context);                 // 启动即恢复（须在首次导航前）
 *   ... 校验首页已登录 ...
 *   await saveAuth(context, 'default');         // 刷新保存，保持新鲜
 */
const fs = require('fs');
const path = require('path');

/** 解析登录态目录：取首个已存在 auth.storage.json 的候选目录，避免与历史存放位置分裂 */
function resolveAuthDir() {
  const cwd = process.cwd();
  const def = path.join(cwd, 'parity-test', '.auth');
  const cands = [];
  if (process.env.PARITY_AUTH_DIR) cands.push(process.env.PARITY_AUTH_DIR);
  cands.push(def);
  try {
    const pt = path.join(cwd, 'parity-test');
    if (fs.existsSync(pt)) for (const e of fs.readdirSync(pt, { withFileTypes: true })) if (e.isDirectory()) cands.push(path.join(pt, e.name, '.auth'));
  } catch (e) { }
  cands.push(path.join(cwd, '.auth'));
  for (const c of cands) { try { if (fs.existsSync(path.join(c, 'auth.storage.json'))) return c; } catch (e) { } }
  return process.env.PARITY_AUTH_DIR || def;
}
const DIR = resolveAuthDir();
const STORAGE = path.join(DIR, 'auth.storage.json');
const COOKIES = path.join(DIR, 'auth.cookies.json');
const INFO = path.join(DIR, 'auth_info.json');

function ensure() { fs.mkdirSync(DIR, { recursive: true }); }

/** 保存当前上下文登录态 → 三个文件 */
async function saveAuth(context, label) {
  ensure();
  await context.storageState({ path: STORAGE });
  const cookies = await context.cookies();
  fs.writeFileSync(COOKIES, JSON.stringify(cookies, null, 2));
  const state = JSON.parse(fs.readFileSync(STORAGE, 'utf8'));
  const info = {
    savedAt: new Date().toISOString(), label: label || '',
    cookieCount: cookies.length,
    sessionCookies: cookies.filter(c => !c.expires || c.expires === -1).length,
    cookieNames: [...new Set(cookies.map(c => c.name))],
    origins: (state.origins || []).map(o => o.origin),
    localStorageKeys: (state.origins || []).map(o => ({ origin: o.origin, keys: o.localStorage.map(x => x.name) })),
  };
  fs.writeFileSync(INFO, JSON.stringify(info, null, 2));
  return info;
}

/** 恢复登录态：注入 cookies（含 session）+ localStorage（addInitScript）。须在首次导航前调用。 */
async function restoreAuth(context) {
  if (!fs.existsSync(STORAGE)) return { ok: false, reason: 'no auth file: ' + STORAGE };
  let state;
  try { state = JSON.parse(fs.readFileSync(STORAGE, 'utf8')); } catch (e) { return { ok: false, reason: 'bad storage file' }; }
  let cookies = state.cookies || [];
  if (fs.existsSync(COOKIES)) { try { cookies = cookies.concat(JSON.parse(fs.readFileSync(COOKIES, 'utf8'))); } catch (e) { } }
  const seen = new Set(); const uniq = [];
  for (const c of cookies) { const k = c.name + '|' + c.domain + '|' + c.path; if (seen.has(k)) continue; seen.add(k); uniq.push(c); }
  if (uniq.length) await context.addCookies(uniq).catch(() => { });
  const origins = state.origins || [];
  if (origins.length) {
    await context.addInitScript((list) => {
      try {
        const hit = list.find(x => location.origin === x.origin);
        if (hit) for (const it of hit.localStorage) { try { localStorage.setItem(it.name, it.value); } catch (e) { } }
      } catch (e) { }
    }, origins).catch(() => { });
  }
  return { ok: true, cookies: uniq.length, origins: origins.map(o => o.origin) };
}

/** 多信号登录页判定（密码框只是弱信号，不可单独用） */
async function isLoginPage(page) {
  return await page.evaluate(() => {
    const body = document.body ? document.body.innerText : '';
    const url = location.href || '';
    return /login|signin/i.test(url) || /未登录|您还未登录|请先登录|请登录/.test(body) || /立即注册|忘记用户名|验证码登录|账号登录/.test(body) || /系统提示/.test(document.title || '');
  }).catch(() => true);
}

module.exports = { DIR, STORAGE, COOKIES, INFO, resolveAuthDir, saveAuth, restoreAuth, isLoginPage };
