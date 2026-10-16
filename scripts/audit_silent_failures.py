#!/usr/bin/env python3
"""【S2 静默失败零容忍】自检 lint：扫「裸 except pass/continue」「空 catch」，
命中点旁无留痕语句即报。基线见 silent_failure_audit_baseline.json——
存量命中数只允许降不允许升（新增静默失败=测试红），存量逐批清偿。

用法：python audit_silent_failures.py [--enforce]
退出码：0=不高于基线；1=高于基线（--enforce 时）
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

PATTERNS = [
    ("py-except-pass", r"except\s*(\w+(\.\w+)*(,\s*\w+)*)?\s*:\s*\n\s*pass"),
    ("py-except-continue", r"except[^:\n]*:\s*\n\s*continue"),
    ("js-empty-catch", r"\.catch\(\s*(\(\w*\)|\w*)?\s*=>\s*\{\s*\}\s*\)"),
]
TRACE_MARKERS = ("write", "stderr", "console.", "notRun", "pending", "留痕",
                 "add_observation", "append", "skipped")
BASELINE = Path(__file__).resolve().parent / "silent_failure_audit_baseline.json"


def scan():
    hits = []
    for p in Path(__file__).resolve().parent.rglob("*"):
        if p.suffix not in (".py", ".js", ".cjs") or "node_modules" in str(p) or "backup" in str(p):
            continue
        try:
            src = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if p.name == Path(__file__).name:
            continue
        for name, pat in PATTERNS:
            for m in re.finditer(pat, src):
                line = src[:m.start()].count("\n") + 1
                ctx = src[:m.start()][-400:]
                has_trace = any(k in ctx for k in TRACE_MARKERS)
                hits.append({"file": p.name, "line": line, "pattern": name,
                             "traceNearby": has_trace})
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enforce", action="store_true")
    args = ap.parse_args()
    hits = scan()
    no_trace = [h for h in hits if not h["traceNearby"]]
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {"noTraceNearby": 0}
    baseline_n = int(baseline.get("noTraceNearby", 0))
    print("静默失败命中：%d（其中无留痕 %d；基线无留痕 %d）" % (len(hits), len(no_trace), baseline_n))
    if len(no_trace) > baseline_n:
        print("新增无留痕命中（必须补留痕语句或修正基线）：", file=sys.stderr)
        known = {(h["file"], h["line"], h["pattern"]) for h in baseline.get("hits", [])}
        for h in no_trace:
            if (h["file"], h["line"], h["pattern"]) not in known:
                print("  - %s:%s %s" % (h["file"], h["line"], h["pattern"]), file=sys.stderr)
        if args.enforce:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
