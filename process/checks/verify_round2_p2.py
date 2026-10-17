#!/usr/bin/env python3
"""P2-17 start_test 语义误触发 / P2-18 journey variants 数字型实证。"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

S = Path(r"E:\skills\figma-ui-parity\scripts")
sys.path.insert(0, str(S))

# P2-17: should_start 对"历史陈述 + 否定意图"的判定
import start_test as ST
cases = [
    ("上个版本走查过了，这次不用再走查", "历史陈述+拒绝意图"),
    ("不用做 UI 对比测试", "纯拒绝"),
    ("开始 UI 一致性检查", "纯启动"),
]
print("=== P2-17 should_start ===")
for text, label in cases:
    started, reason = ST.should_start(text, None, [])
    print("%-22s started=%-5s reason=%s | %r" % (label, started, reason, text))

# P2-18: journey_coverage variants 数字型
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    journey = td / "journey.json"
    cov = td / "coverage.json"
    journey.write_text(json.dumps({
        "journeys": [{"name": "j1", "states": ["s1"]}],
        "variants": {"s1": [1440, 768]},
    }), encoding="utf-8")
    cov.write_text(json.dumps({
        "states": [{"id": "s1", "status": "done"}],
        "breakpoints": [1440, 768],
    }), encoding="utf-8")
    r = subprocess.run(["node", str(S / "journey_coverage.cjs"),
                        "--journey", str(journey), "--coverage", str(cov)],
                       capture_output=True, text=True)
    out = r.stdout or ""
    print("\n=== P2-18 journey_coverage（数字型 variants）===")
    print("rc=%d" % r.returncode)
    print(out.strip()[-400:])