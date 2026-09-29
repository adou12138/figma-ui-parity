# B4 可访问性树 diff（借鉴 Argos）

## 为什么需要

清单 7.19 把"可访问性"当手检项，但像素 diff 抓不出**语义层**回归：缺 `aria-label`、role 错、焦点顺序乱、只读控件无 name。Argos 把可访问性树当文本快照做 diff，能确定性地发现这类问题。

## 引擎

`scripts/capture_aria.js`（复用 `playwright-core` 解析，走有头/持久 profile 同 `run_official_extraction.cjs`）：

```bash
# 抓取当前页可访问性快照
node scripts/capture_aria.js --url "https://目标页" \
  --profile "./.vp_profile_devtest" --out "./parity-test/aria.json"

# 两次运行结构 diff（role + name 树）
node scripts/capture_aria.js --diff ./parity-test/aria_last.json ./parity-test/aria_this.json
```

输出：`{ aCount, bCount, added[], removed[], summary }`。`added` = 本次多出（或 name 变了）的可访问节点；`removed` = 上次有本次无。

## 集成到清单 7.19

- 每次运行在步骤 7.19 之前抓一次 `aria.json`，存入工作目录。
- 若上次要跑过（有 `aria_last.json`），自动 `--diff` 产出 a11y 结构变化，写入报告「可访问性」章节。
- 首次运行无 baseline → 仅存快照、标注"首次，无对比基线"。
- 具体断言（icon-only 按钮命名、Tab 顺序、焦点可见性）仍由清单 7.19 的规则判定，`capture_aria` 负责"结构是否变了"的确定性结论。

## 边界

- `accessibility.snapshot()` 对隐藏/disabled 节点有自身规则（部分不计入），与清单口径一致即可，不必强求完全一致。
- 纯装饰性节点（纯 `<img alt="">`、分隔）的变化通常无害，落入 `added/removed` 后由人工在报告中确认是否需跟踪。
