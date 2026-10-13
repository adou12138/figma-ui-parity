# B1 量化 diff-score + 差异遮罩（借鉴 Argos）

## 为什么需要

旧流程里 `mcp_visual-parity` 只给整页 diff 率（百分比 / 布尔），清单项又是规则判定（"颜色 ≤3/255 → 基本一致"），缺一个**每个元素 / 每次运行差多少**的量化分。报告无法按严重度排序，也无法跨运行比较。

Argos 的核心做法：用 odiff 做像素级 diff，输出 **diff mask（哪些像素变了）+ diff score（变化比例 0–100）**，再据此排序与卡阈值。本 skill 复刻其「确定性、可量化、可排序」精神，但限定在**有意义**的场景：

- **回归 diff**（同一页面两次运行截图）→ 最有用，确定性像素 diff。
- **差异热力图** → 喂给 HTML 报告的 diff mask 图，让"差异在哪里"一目了然。
- **清单项严重度** → 把规则判定转成 0–100 的 `diffScore`，报告可按严重度排序。

> ⚠️ 边界：Figma 设计稿（矢量）vs 实时页面（光栅）**不宜**直接逐像素 diff——不同渲染引擎、字体抗锯齿会让整页 diff 率虚高，淹没真问题。Figma↔页面仍走步骤 2 字段映射 + 清单 7.1–7.21。**diff_score.js 主要用于「同页面回归」与「报告差异热力图」**。

## 引擎

`scripts/diff_score.js`（纯 Node，无外部依赖，内置 zlib 编解码 PNG）：

```bash
# 回归 diff：上次截图 vs 本次截图，输出 diffScore 与差异遮罩
node scripts/diff_score.js \
  --a last_run.png --b this_run.png \
  --out diff_mask.png --threshold 16
# 输出：{ diffScore, changedPixels, totalPixels, maskImage, ... }
```

- `threshold`（默认 16/255）：单像素四通道最大差超过即判定为"变化"。**这是像素噪声门槛，不是百分比**——调它是为了滤掉抗锯齿与压缩噪声，不是调"允许多少差异"。百分比口径见 [visual-parity.md](visual-parity.md) 的「两套阈值不是一回事」。
- `diffScore` = 变化像素数 / 总像素数 × 100，四舍五入到 2 位小数。0 = 完全一致，100 = 全变。

## 增强模式（抗锯齿与孤立噪点抑制）

`--enhanced` **默认关闭**：不传该参数时逐像素口径与引入前完全一致，历史基线与旧报告继续可比。

```bash
# 同一页两次截图的回归 diff，开启降噪
node scripts/diff_score.js --a last.png --b this.png --out mask.png --threshold 16 --enhanced
# 串进流水线：run_parity_pipeline.py --enhanced-diff
```

开启后只做两件"只降噪、不压真缺陷"的事：

| 机制 | 判据 | 为什么不会漏真缺陷 |
|---|---|---|
| **边缘自适应阈值** | 两侧都是梯度 ≥12 的边缘像素时，阈值放大 2.5 倍（`--edge-factor` 可调） | 抗锯齿/几何偏移只发生在边缘；"整块变色"发生在平坦区，阈值不变，边界像素差值远超放大后的阈值也不会被压 |
| **孤立差异像素过滤** | 8 邻域内没有任何其它差异像素的单点差异按噪点抑制 | 真实缺陷一定是**成片**的（≥2 连通），单点差异才是噪点 |

两种抑制量都写进结果并**在遮罩里可见**，不静默吞掉：

```json
{ "mode": "enhanced", "diffScore": 0.31, "changedPixels": 1480,
  "weakPixels": 260,
  "suppressed": { "edgeNoise": 5120, "isolated": 37 } }
```

- `suppressed.edgeNoise` / `suppressed.isolated`：被抑制的噪点像素数（遮罩里画成**淡黄**，方便一眼看出"这里被降噪了"）；
- `weakPixels`：差值超过噪点门槛（`threshold × 0.5`）但未过判定线的像素，单列统计**不计入** `changedPixels`——用于区分"差一点点"与"差很多"；
- ⚠️ **跨模式比较前先确认基线同模式**：基础模式与增强模式的 `diffScore` 口径不同，混用会得出错误的回归结论。历史基线是在基础模式下建立的，开增强前建议重建基线。

## 集成到报告

1. **pixelDiff 增加 `diffScore` 字段**：步骤 5 拿到 visual-parity 整页 diff 后，用 `diff_score.js` 复算一次（或以其为准），写入 `report.json` 的 `pixelDiff.diffScore`，HTML 报告顶部概览显示。
2. **差异热力图**：`diff_score.js --out diff_mask.png` 产出的遮罩图，作为 `report.html`「像素差异热力图」实图（替换纯文字 diff 率）。
3. **清单项严重度量化**：把步骤 8 容忍度规则映射为 `diffScore`：
   - 颜色差 ≤3/255 → `diffScore` 赋 5（低，标"基本一致"）
   - 3–10/255 → 30（中）
   - >10/255 → 70+（高/中，按维度）
   - 图标形状不符 → 90（高）
   
   每条 `diffs[]` / `iconDiffs[]` 增加 `diffScore` 字段，HTML 报告按 `diffScore` 降序排列高优先级差异，便于开发先修最显眼的。
4. **配合 B2 ignore-regions**：`diff_score.js --ignore ignoredRegions.json` 在 diff 前清零忽略区，详见 [ignore-regions.md](ignore-regions.md)。

## 与「AI 判 diff」的边界

Argos 明确拒绝用 AI 判定"是否可接受"（会吞小变更、不可审计）。本 skill 同样：**diff 权威必须是确定性的**（像素 diff / 字段映射 / 清单规则）；LLM 只做辅助文字描述，不参与"是否算缺陷"的裁决。
