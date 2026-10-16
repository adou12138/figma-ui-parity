# 真实环境端到端验证流程（E 维度已查证证据）

本文件用于消除 TRACE 评测中 E4「显著增益」的*推断*标注：用**真实 Figma token + 真实页面 + 真实浏览器**跑通一次完整链路，并把结果写入证据文件。评测时该证据文件即作为 E 维度已查证依据。

> ⚠️ 本流程必须在用户真实环境执行。自动化审计/改造过程**不得**替用户持有 token，也**不得**用真实凭据实跑。证据由用户侧产出后回填。

## 一、前置（凭据安全）

- Figma：按 `setup-guide.md` 创建**最小只读** Personal access token，只写入受信任 MCP 配置；token 不得回显、不得写入报告/日志/对话/仓库。
- 页面登录态：用 Playwright 的 storage state 或可见浏览器人工登录；**禁止**把密码交给 Skill，禁止自动填密/绕过登录。
- 所有凭据只落在 `parity-test/.auth/`（由 `init_workdir.py` 建立并写入 `.gitignore`）。

## 二、执行顺序

```bash
# 1. 建工作目录与凭据隔离
python scripts/init_workdir.py --root .

# 2. 设计侧：把真实 get_file_nodes 产物规整为 design_model.json
python scripts/extract_design_fields.py --input ./parity-test/figma_raw.json --output ./parity-test/design_model.json

# 3. 页面侧（二选一）
#    a) Playwright MCP 路径：用 browser_evaluate 注入 collect_page_inventory.js → page.json
#    b) Node 兜底路径（需人工登录的可见浏览器）：
node scripts/node/run_official_extraction.cjs --url "<页面URL>" \
  --profile "./parity-test/.vp_profile" --out ./parity-test/extract --headed --stabilize --responsive

# 4. 字段比对（坐标归一 + 容差）
python scripts/compare_fields.py --design ./parity-test/design_model.json \
  --page ./parity-test/page.json --page-url "<页面URL>" --output ./parity-test/styleDiffs.json

# 5. 三道硬门禁
python scripts/validate_defects.py --report ./parity-test/report.json --strict
python scripts/coverage_gate.py  --report ./parity-test/report.json --enforce --write
python scripts/ignore_regions.py --file ./parity-test/ignoredRegions.json --enforce

# 6. 出报告
python scripts/generate_reports.py --input ./parity-test/report.json --outdir ./parity-test/reports

# 7. 链路冒烟（防回归）
python scripts/smoke_chain.py

# 8. 采集证据（产出 real-env-evidence.json）
python scripts/capture_real_env_evidence.py \
  --report ./parity-test/report.json \
  --figma-file-key "<仅文件 key>" \
  --page-url "<页面URL>" \
  --page-via mcp \
  --notes "真实发现摘要……"
```

## 三、证据文件模板（real-env-evidence.json）

`capture_real_env_evidence.py` 会写出如下结构；评测时引用此文件即可把 E4 从推断转为已查证。

```json
{
  "capturedAt": "2026-09-22T15:00:00+08:00",
  "figmaFileKey": "<仅文件 key，不含 token>",
  "pageUrl": "<页面URL，若含敏感路径可脱敏>",
  "environment": {
    "os": "windows | macos | linux",
    "python": "3.12.9",
    "playwright": "1.x.x（node 路径时填写）"
  },
  "pipeline": {
    "designExtracted": true,
    "pageExtractedVia": "mcp | node",
    "compareRan": true,
    "gatesPassed": true,
    "smokeChainPassed": true,
    "coverageRate": 0.82,
    "defectsFound": 14
  },
  "notableFindings": [
    "坐标归一无假阳性（真实页面验证）",
    "extra_checks.js 在真实页面发现 3 处暗色模式对比度问题"
  ],
  "notes": "可附真实发现摘要，不得含 token / Cookie 原文"
}
```

## 四、判定口径

- `gatesPassed == true` 且 `smokeChainPassed == true` 且 `coverageRate >= 0.7`：E4 记为「显著增益（已查证）」。
- 任意一项为否：仍记为「推断」，并在备注写明未满足项。
- 本证据只证明"在真实环境跑通且产出可信"，不替代对更多样本/更多页面的重复验证。
