# B2 指纹级忽略区 ignore-regions（借鉴 Argos）

## 为什么需要

头像随机图、实时时间戳、第三方挂件（统计/客服）、A/B 文案等，**每次运行都在变，但与"设计还原度"无关**。不处理它们会反复刷 noise：diff 率虚高、清单项误报、让人对报告失去信任。

Argos 的关键经验：**忽略必须绑定到「一个 test + 一个具体 change 指纹」，绝不能整页屏蔽**——否则会连同真正的回归一起藏掉，变成"忽略变盲点"。

## 结构（随工作目录存放）

`$WORK_DIR/ignoredRegions.json`：

```json
{
  "version": 1,
  "regions": [
    {
      "id": "avatar-random",
      "selector": ".user-avatar",
      "bbox": { "x": 100, "y": 200, "w": 40, "h": 40 },
      "changeFingerprint": "avatar|<selector>",
      "reason": "头像为随机图，每次不同，与还原度无关",
      "appliesTo": ["diff", "checklist"]
    },
    {
      "id": "live-clock",
      "selector": ".header-clock",
      "bbox": null,
      "changeFingerprint": "clock|text",
      "reason": "实时时钟，与还原度无关",
      "appliesTo": ["checklist"]
    }
  ]
}
```

字段说明：

| 字段 | 作用 |
|---|---|
| `id` | 忽略项唯一标识，便于「忽略管理」列出与 unignore |
| `selector` | CSS 选择器，driver 据此在页面里取 `bbox`（动态计算，不写死坐标） |
| `bbox` | 可选静态坐标；若省略，driver 用 `selector` 实时 `getBoundingClientRect()` 取 |
| `changeFingerprint` | **指纹级**绑定：只屏蔽"该选择器上的这类变更"，同截图上的其他变更不被屏蔽 |
| `reason` | 为何忽略，落报告备查 |
| `appliesTo` | `diff`（喂给 diff_score 清零）/ `checklist`（跳过匹配该 selector 的清单项） |

## 应用方式

1. **像素 diff（B1）**：`node scripts/diff_score.js --a A.png --b B.png --ignore ignoredRegions.json`。脚本读取 `regions`，把命中 `bbox` 的像素在两份图里都清零后再 diff，忽略区不计入 `diffScore`。
2. **清单项降噪**：driver 在记录缺陷时，若缺陷 `element.selector` 命中某 `region.selector` 且其 `changeFingerprint` 匹配，则该项不记缺陷，改记 `ignored`（落报告「已忽略变更」章节，含 reason），**不计入覆盖率缺失**。
3. **缺失文件自动降级**：`ignoredRegions.json` 不存在时，两项都不屏蔽，流程照常（不报错、不阻塞）。

## 忽略管理（防盲点）

- 每次运行后，在报告「已忽略变更」章节列出全部忽略项（id + reason）。
- 用户可随时用 `AskUserQuestion` / 编辑 JSON 移除某条（unignore），恢复对其的监控。
- **严禁**用 ignore-regions 屏蔽"整页"或"大块未知区域"——只能精确到具体元素 + 具体 change 指纹。这是审计红线。
- **忽略项必须带到期信息**：

| 字段 | 作用 |
|---|---|
| `reviewedAt` | 上次人工确认该忽略仍成立的日期 |
| `expiresAt` | 显式到期日；缺省时按 `reviewedAt + 90 天` 计算 |
| `owner` | 该忽略项的确认人，便于过期后找人 |

```json
{
  "id": "avatar-random",
  "selector": ".user-avatar",
  "changeFingerprint": "avatar|<selector>",
  "reason": "头像为随机图，每次不同，与还原度无关",
  "appliesTo": ["diff", "checklist"],
  "reviewedAt": "2026-09-22",
  "expiresAt": "2026-12-21",
  "owner": "test-owner"
}
```

## 到期审计

运行 `python scripts/ignore_regions.py --file ./parity-test/ignoredRegions.json --enforce`：

- 输出四类结论：**生效** / **过期** / **字段缺失**（缺 `id` / `selector` / `changeFingerprint` / `reason`）/ **宽泛或缺少到期信息**。
- 宽泛判定：选择器为 `*` `body` `html` `div` `#app` 等；或 `appliesTo` 含 `diff` 却既无 `selector` 也无 `bbox`。
- 有 `--enforce` 时，存在过期项或字段缺失项即返回非零码，**不得带着过期忽略项出报告**。
- 报告必须嵌入「本次生效忽略项」清单及其 `reason`，接受"已知差异"要留痕。

> 忽略区长期不清理 = 盲点长期存在。历史上就出现过"被遮挡"类误报被忽略项掩盖、直到重跑才暴露的情况。

## 与容忍度规则的关系

容忍度规则（属性级 ±1px、颜色 ΔE ≤ 3 等）是**普适**的，定义在 `scripts/compare_fields.py` 的容差表；ignore-regions 是**具体元素**的。二者叠加顺序：先按 ignore-regions 排除无关元素，再对剩余元素应用容差规则。
