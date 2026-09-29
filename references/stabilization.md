# B3 拍摄前稳定化 stabilization（借鉴 Argos）

## 为什么需要

旧流程的闸 C 只在**提取后**抓坏数据（零尺寸 rect），但**渲染本身没主动稳定**。动画未播完、字体未加载、懒加载未触发、动态文本在变——这些都会让截图抖动、元素尺寸为 0、diff 率虚高。Argos 把 flaky 当技术债，在拍摄前先「稳定化」页面。

## 例程（脚本 `scripts/stabilize.js`）

`stabilize(page, opts)` 做四件事：

1. **关动画/过渡**：注入 CSS `* { animation/transition: 0s !important }` + 强制 `prefers-reduced-motion: reduce`。
2. **等字体就绪**：`document.fonts.ready`（避免 web font 回退导致布局跳动）。
3. **等网络空闲**：`page.waitForLoadState('networkidle')`。
4. **触发懒加载**：分段滚动到页面底部再回到顶部（长列表/图片懒加载需先渲染），随后 `scrollTo(0,0)`。

`opts`：`{ freezeDynamic?:boolean, scrollSteps?:number, waitNetworkIdle?:boolean }`。`freezeDynamic` 预留接口（如需冻结实时时间戳，由 driver 注入替换文本，本 skill 默认不强制）。

## 集成位置

在**步骤 4 截图（3.3 节 `browser_take_screenshot`）之前**与**步骤 5 像素对比之前**各调一次：

- 走 `mcp__playwright`：`browser_evaluate` 注入 `STABILIZE_CSS`（从 `scripts/stabilize.js` 导出字符串）+ 执行滚动例程。
- 走 `scripts/node/run_official_extraction.cjs`（有头登录场景）：已加 `--stabilize` 开关，传参即在截图前自动稳定化。

```bash
node scripts/node/run_official_extraction.cjs \
  --url "https://目标页" --profile "./.vp_profile_devtest" \
  --headed --responsive --stabilize --out "./parity-test/extract"
```

## 收益

- 零尺寸 rect 占比下降 → 闸 C 更少误报、更少 `dataMissing`。
- 截图稳定 → B1 diff_score 的 `diffScore` 更能反映"真实回归"而非"渲染抖动"。
- 与 ignore-regions（B2）互补：稳定化解决"渲染未稳"，忽略区解决"内容本就随机"。
