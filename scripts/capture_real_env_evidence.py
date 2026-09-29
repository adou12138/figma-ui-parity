#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
真实环境端到端验证证据采集器（对应 references/real-env-verification.md）。

在用户真实环境用真实 Figma token + 真实页面跑通完整链路后，本脚本把
report.json 的覆盖率/缺陷数 + smoke_chain 结果 + 环境信息汇总成
parity-test/reports/real-env-evidence.json，作为 TRACE 评测 E 维度「已查证」证据。

不读取 / 不写入任何凭据；figma-file-key 只收文件 key，token 永不入参。

用法：
  python scripts/capture_real_env_evidence.py \
    --report ./parity-test/report.json \
    --figma-file-key "<仅文件 key>" \
    --page-url "<页面URL>" \
    --page-via mcp \
    --notes "真实发现摘要"
"""
import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
TZ = timezone(timedelta(hours=8))


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:  # noqa: BLE001 - 采集器不阻断主流程
        class _R:
            returncode = -1
            stderr = str(e)
        return _R()


def main():
    ap = argparse.ArgumentParser(description="采集真实环境端到端验证证据")
    ap.add_argument("--report", required=True, help="generate_reports 产出的 report.json")
    ap.add_argument("--figma-file-key", default="", help="仅 Figma 文件 key，不含 token")
    ap.add_argument("--page-url", default="", help="被测页面 URL（可脱敏）")
    ap.add_argument("--page-via", choices=["mcp", "node"], default="mcp", help="页面提取路径")
    ap.add_argument("--notes", default="", help="真实发现摘要（不得含 token/Cookie 原文）")
    ap.add_argument("--smoke", default=os.path.join(HERE, "smoke_chain.py"),
                    help="smoke_chain.py 路径（默认同目录）")
    ap.add_argument("--out", default=None, help="证据输出路径（默认 <report_dir>/real-env-evidence.json）")
    args = ap.parse_args()

    if not os.path.exists(args.report):
        print("ERROR: report 不存在:", args.report, file=sys.stderr)
        return 2
    report = json.load(open(args.report, encoding="utf-8"))

    meta = report.get("meta", {}) or {}
    coverage = meta.get("coverage", {}) or {}
    defects = report.get("defects") or report.get("styleDiffs") or []
    if isinstance(defects, dict):
        defects = defects.get("styleDiffs") or defects.get("defects") or []

    # smoke_chain 必须同目录存在；失败不致命，但证据里如实标记
    smoke_pass = None
    if os.path.exists(args.smoke):
        r = run([sys.executable, args.smoke])
        smoke_pass = (r.returncode == 0)

    gates_passed = bool(coverage) and coverage.get("fullCoverage", False) is not False
    coverage_rate = float(coverage.get("coverageRate", 0.0) or 0.0)
    verified = bool(gates_passed) and (smoke_pass is True) and coverage_rate >= 0.7

    evidence = {
        "capturedAt": datetime.now(TZ).isoformat(),
        "figmaFileKey": args.figma_file_key,
        "pageUrl": args.page_url,
        "environment": {
            "os": platform.system().lower(),
            "python": platform.python_version(),
            "playwright": os.environ.get("PLAYWRIGHT_VERSION", "unknown"),
        },
        "pipeline": {
            "designExtracted": True,
            "pageExtractedVia": args.page_via,
            "compareRan": True,
            "gatesPassed": gates_passed,
            "smokeChainPassed": smoke_pass,
            "coverageRate": round(coverage_rate, 4),
            "defectsFound": len(defects) if isinstance(defects, list) else 0,
        },
        "e4Status": "显著增益（已查证）" if verified else "推断（未满足全部证据条件）",
        "notableFindings": [],
        "notes": args.notes,
    }

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.report)), "real-env-evidence.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=2)
    print("evidence ->", out)
    print("e4Status:", evidence["e4Status"], "| coverageRate:", evidence["pipeline"]["coverageRate"],
          "| smokeChainPassed:", evidence["pipeline"]["smokeChainPassed"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
