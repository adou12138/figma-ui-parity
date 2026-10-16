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
    # ---- 变体补齐：以下形态旧口径全部漏检（已实测坐实）----
    # ① 元组形式 `except (A, B):`——旧 py-except-pass 的 `(\w+...)?` 组吃不下左括号，
    #    extract_design_fields.py:150 的 `except (TypeError, ValueError): pass` 长期不被报。
    ("py-except-tuple-pass", r"except\s*\([^)]*\)\s*:\s*\n\s*pass"),
    ("py-except-tuple-continue", r"except\s*\([^)]*\)\s*:\s*\n\s*continue"),
    # ② `except X as e:`——旧式的 `\s*:` 同样匹配不上 ` as e:`。
    ("py-except-as-pass", r"except\s+[\w.]+\s+as\s+\w+\s*:\s*\n\s*pass"),
    ("py-except-as-continue", r"except\s+[\w.]+\s+as\s+\w+\s*:\s*\n\s*continue"),
    # ③ 采集/解析函数里的 `return None` / `return []` 形态：缺陷被折成空值返回给
    #    上游，上游拿到 None 与「真的没有」不可区分——与 pass/continue 同级的静默失败。
    ("py-except-return-empty", r"except[^:\n]*:\s*\n\s*return\s*(?:None|\[\]|\{\})"),
]

# 【邻近性修复】留痕证据必须**紧邻**命中点：命中点之后若干行内、且落在 except 块
# 自身的缩进范围内。旧口径取命中点**之前** 400 字符，且 TRACE_MARKERS 含
# `append`/`write`/`console.` 等高频词——上方一处无关的 `out.append(...)` 就能让真正的
# `except: continue` 判成「已留痕」而不报（实测坐实）。
#
# 强标记：本身就构成留痕语义（warn/error/显式降级标记），邻近出现即可采信。
STRONG_TRACE_MARKERS = ("console.warn", "console.error", "stderr", "留痕",
                        "add_observation", "dataQuality", "degraded",
                        "notRun", "process.exitCode")
# 弱/高频标记：`append`/`write`/`console.` 在本仓出现频率极高（每个数组初始化、
# 每处 warn 日志都算），只在**except 块自身缩进范围内**才承认——出了块就是别人的日志。
WEAK_TRACE_MARKERS = ("append", "write", "console.", "pending", "skipped")
# 强标记的前瞻窗口（行）：留痕必须紧随其后，超过即视为「别处的日志」。
TRACE_LOOKAHEAD_LINES = 3
# 弱标记的块内扫描上限（行）：防止块体超长时把深处的无关 append 算作留痕。
OWN_BLOCK_MAX_LINES = 6
BASELINE = Path(__file__).resolve().parent / "silent_failure_audit_baseline.json"


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip())


def has_trace(src_lines: list, hit_idx: int) -> bool:
    """hit_idx 为命中行下标（0-based）。返回该命中点是否**邻近**留痕。"""
    hit_indent = _indent_of(src_lines[hit_idx]) if 0 <= hit_idx < len(src_lines) else 0
    # ① except 块自身的缩进范围：命中行剩余部分 + 之后缩进更深的行（上限 OWN_BLOCK_MAX_LINES）。
    own = [src_lines[hit_idx]]
    for k in range(hit_idx + 1, min(len(src_lines), hit_idx + 1 + OWN_BLOCK_MAX_LINES)):
        line = src_lines[k]
        if not line.strip():
            own.append(line)
            continue
        if _indent_of(line) > hit_indent:
            own.append(line)
        else:
            break
    own_text = "\n".join(own)
    if any(k in own_text for k in WEAK_TRACE_MARKERS):
        return True
    # ② 命中点之后的强标记，前瞻窗口收窄到 TRACE_LOOKAHEAD_LINES 行。
    ahead = src_lines[hit_idx + 1: hit_idx + 1 + TRACE_LOOKAHEAD_LINES]
    return any(k in "\n".join(ahead) for k in STRONG_TRACE_MARKERS)


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
        src_lines = src.split("\n")
        for name, pat in PATTERNS:
            for m in re.finditer(pat, src):
                line = src[:m.start()].count("\n") + 1
                has_trace_flag = has_trace(src_lines, line - 1)
                hits.append({"file": p.name, "line": line, "pattern": name,
                             "traceNearby": has_trace_flag})
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enforce", action="store_true")
    args = ap.parse_args()
    hits = scan()
    no_trace = [h for h in hits if not h["traceNearby"]]
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {"noTraceNearby": 0, "total": 0}
    baseline_n = int(baseline.get("noTraceNearby", 0))
    baseline_total = int(baseline.get("total", 0))
    total = len(hits)
    print("静默失败命中：%d（其中无留痕 %d；基线无留痕 %d、总命中 %d）"
          % (total, len(no_trace), baseline_n, baseline_total))
    # 【双重门禁修复】旧口径只比 noTraceNearby 个数：「修 1 处（留痕数 -1）+ 新增 1 处
    # （无留痕 +1）」相抵后 noTrace 不变 → 放行，但总命中涨了，静默失败在总量上净增。
    # 现在两个口径都必须不上升：任一上升即判失败。
    no_trace_up = len(no_trace) > baseline_n
    total_up = total > baseline_total
    if no_trace_up or total_up:
        if no_trace_up:
            print("无留痕命中数超过基线（%d > %d），新增条目："
                  % (len(no_trace), baseline_n), file=sys.stderr)
        if total_up:
            print("静默失败总命中数超过基线（%d > %d）——「修 1 处 + 新增 1 处」相抵不再放行："
                  "存量只允许降不允许升" % (total, baseline_total), file=sys.stderr)
        known = {(h["file"], h["pattern"]) for h in baseline.get("hits", []) if not h.get("traceNearby", True)}
        for h in no_trace:
            if (h["file"], h["pattern"]) not in known:
                print("  - %s:%s %s" % (h["file"], h["line"], h["pattern"]), file=sys.stderr)
        if args.enforce:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
