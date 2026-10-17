#!/usr/bin/env python3
"""二审问题实证：P0-1 Excel 崩溃 / P1-2 violations 接线 / P1-3 checks 覆盖 / P1-6 除零 / P1-4 方向。"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

S = Path(r"E:\skills\figma-ui-parity\scripts")
sys.path.insert(0, str(S))
ok = []

# P0-1: gen_excel_fallback main() 的 PatternFill NameError
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    (td / "report.json").write_text(json.dumps({"defects": []}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(S / "gen_excel_fallback.py"), str(td / "report.json")],
                       capture_output=True, text=True)
    hit = "NameError" in (r.stderr or "") and "PatternFill" in (r.stderr or "")
    detail = (r.stderr or r.stdout).strip()[-200:]
    ok.append(("P0-1 PatternFill NameError", hit, detail))

# P1-2: _findings_list 只读 findings 键，assert_constraints 产出 violations
import assemble_report as AR
payload = {"violations": [{"id": "V1", "status": "confirmed", "dimension": "7.4"}],
           "findings": []}
got = AR._findings_list(payload)
ok.append(("P1-2 _findings_list 丢 violations", got == [],
           "violations 条目被丢，实得 %d 条" % len(got)))

# P1-3: checks/dimensionResults 并存时 assemble 后命中覆盖 vs gate 首命中
import coverage_gate as CG
report = {"meta": {"checks": {"7.1": {"verdict": "pass"}},
                   "dimensionResults": {"7.1": {"verdict": "fail"}}}}
cg = CG.extract_checks(report)
existing = {}
for key in ("checks", "dimensionResults", "checklist"):
    value = (report.get("meta") or {}).get(key)
    if isinstance(value, dict):
        existing = {str(k): v for k, v in value.items()}
ok.append(("P1-3 覆盖顺序相反",
           cg.get("7.1", {}).get("verdict") == "pass" and existing.get("7.1", {}).get("verdict") == "fail",
           "gate=%s assemble=%s" % (cg.get("7.1", {}).get("verdict"),
                                    existing.get("7.1", {}).get("verdict"))))

# P1-6: assert_constraints check_axis 基准帧宽 0
import assert_constraints as AC
try:
    r6 = AC.check_axis("SCALE", {"x": 10, "w": 50}, 1000, 800, {"x": 10, "w": 50}, {"w": 0, "h": 0}, "h")
    ok.append(("P1-6 SCALE 除零", False, "未抛异常，返回 %r" % (r6,)))
except ZeroDivisionError:
    ok.append(("P1-6 SCALE 除零", True, "ZeroDivisionError 复现"))

# P1-4: baseline_regression.cjs 方向（覆盖率降 0.9→0.5 应报 regressed，若报 fixed 则确认）
with tempfile.TemporaryDirectory() as td:
    base = Path(td) / "base.json"
    cur = Path(td) / "cur.json"
    base.write_text(json.dumps({"summary": {"coverageRate": 0.9}}), encoding="utf-8")
    cur.write_text(json.dumps({"summary": {"coverageRate": 0.5}}), encoding="utf-8")
    rn = subprocess.run(["node", str(S / "baseline_regression.cjs"), "--baseline", str(base),
                         "--current", str(cur)], capture_output=True, text=True)
    out = rn.stdout or ""
    hit = "coverageRate" in out and "fixed" in out
    ok.append(("P1-4 覆盖率降被标 fixed", hit, out.strip()[-200:]))

print("=== figma 二审实证 ===")
for name, hit, detail in ok:
    print("[%s] %s | %s" % ("确认" if hit else "未复现", name, detail))