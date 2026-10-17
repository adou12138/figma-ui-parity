#!/usr/bin/env python3
"""P0-1 / P1-4 补充实证（需 openpyxl + 双跑基线）。"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

S = Path(r"E:\skills\figma-ui-parity\scripts")

# P0-1: openpyxl 就位后 main() 的 PatternFill NameError
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    (td / "report.json").write_text(json.dumps({"defects": [], "pendingChecks": []}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(S / "gen_excel_fallback.py"), str(td / "report.json")],
                       capture_output=True, text=True)
    hit = "NameError" in (r.stderr or "") and "PatternFill" in (r.stderr or "")
    print("[%s] P0-1 PatternFill NameError | rc=%d | %s" % (
        "确认" if hit else "未复现", r.returncode, (r.stderr or "").strip()[-160:]))

# P1-4: baseline_regression 双跑（第一次建基线，第二次对比方向）
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    # 第一次：coverageRate 0.9（建正式基线）
    args = ["node", str(S / "baseline_regression.cjs"), "--baseline-dir", str(td),
            "--current", "-", "--update-baseline"]
    def run_cur(summary):
        return subprocess.run(
            ["node", str(S / "baseline_regression.cjs"), "--baseline-dir", str(td),
             "--current", "-", "--update-baseline"],
            input=json.dumps({"summary": summary}), capture_output=True, text=True)
    r1 = run_cur({"coverageRate": 0.9})
    r2 = run_cur({"coverageRate": 0.5})
    out = r2.stdout or ""
    hit = "coverageRate" in out and "fixed" in out
    print("[%s] P1-4 覆盖率降 0.9→0.5 被标 fixed | %s" % (
        "确认" if hit else "未复现", out.strip()[-240:]))