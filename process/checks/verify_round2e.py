#!/usr/bin/env python3
"""P1-4 终版实证（snapshot 真实形状：meta.coverage.coverageRate + verdictCounts）。"""
import json
import subprocess
import tempfile
from pathlib import Path

S = Path(r"E:\skills\figma-ui-parity\scripts")

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    bdir = td / "baseline"
    cur = td / "report.json"

    def report(cov_rate, n_pass):
        return {
            "meta": {"coverage": {"coverageRate": cov_rate}},
            "sections": [{"items": [{"verdict": "pass"}] * n_pass}],
        }

    def run(rep, update):
        cur.write_text(json.dumps(rep), encoding="utf-8")
        args = ["node", str(S / "baseline_regression.cjs"),
                "--current", str(cur), "--baseline-dir", str(bdir),
                "--figmaKey", "k", "--nodeId", "n"]
        if update:
            args.append("--update-baseline")
        return subprocess.run(args, capture_output=True, text=True)

    run(report(0.9, 30), False)   # 1) 建 provisional
    run(report(0.9, 30), True)    # 2) 对比并转正
    r3 = run(report(0.5, 10), False)  # 3) 覆盖率 0.9→0.5、pass 30→10
    out = r3.stdout or ""
    hit_cov = '"field": "coverageRate"' in out and "fixed" in out
    hit_pass = "verdictCounts.pass" in out and "fixed" in out
    print("[%s] P1-4a coverageRate 降被标 fixed" % ("确认" if hit_cov else "未复现"))
    print("[%s] P1-4b verdictCounts.pass 降被标 fixed" % ("确认" if hit_pass else "未复现"))
    print(out.strip()[-600:])