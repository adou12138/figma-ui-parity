#!/usr/bin/env python3
"""把各驱动产物的维度级证据汇总成 report 的 checks 段。

## 为什么需要它

`coverage_gate.py` 要求 39 个维度**每一个**都出现在 `meta.checks` / `checks` /
`dimensionResults` 里，且 `notRun` / `dataMissing` 必须写明原因，否则以非零码退出。
在此之前，这份 39 行的「维度 → 状态 → 原因」表**没有任何生产脚本**——每轮都要由 agent
手工拼装，漏填即被门禁打回，而且手工拼的产物与驱动脚本的真实产出是两张皮。

本脚本把各驱动产物（样式差异 / 探测发现 / 状态场景 / 旅程发现 / 场景执行率）按维度
汇总成 checks，让门禁消费的是**机器产出**而不是手写表。

## 边界纪律（最重要，改代码前先读）

1. **无证据的维度只能填 `notRun`，严禁推断 `pass`。** 「没跑」和「跑了没发现问题」
   是两件事，混为一谈会让覆盖率数字从"诚实记录"变成"装饰"。
2. `notRun` / `dataMissing` **必须带 reason**，且 reason 要能回答"为什么没跑"。
3. 产物里已有的手写 checks **不会被覆盖**：本脚本只补产物能证明的维度，report 里
   已有但产物未覆盖的条目原样保留（人填的比机器猜的优先级高）。
4. 状态优先级（同一维度多份证据时取最严重）：
   `fail`(confirmed) > `pending` > `dataMissing`(notComparable) > `pass`(withinTolerance) > `notRun`
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 与 coverage_gate.py 的词表严格一致
EXECUTED = {"pass", "fail", "warn", "pending"}
NOT_EXECUTED = {"notRun", "dataMissing"}
VALID = EXECUTED | NOT_EXECUTED

# 证据严重度排序：越靠前越严重，同维多份证据取最严重
SEVERITY_ORDER = ["fail", "pending", "dataMissing", "pass", "notRun"]


def load_dimensions(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [d for d in data.get("dimensions", []) if d.get("id")]


def _read_json(path: Path):
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print("[warn] 跳过无法解析的产物 {}: {}".format(path, exc), file=sys.stderr)
        return None


def _findings_list(payload) -> list:
    """findings 类产物兼容两种形状：{findings:[...]} 或直接 [...]。"""
    if isinstance(payload, dict):
        items = payload.get("findings")
        return items if isinstance(items, list) else []
    return payload if isinstance(payload, list) else []


def collect_style_diffs(path: Path, evidence: dict) -> None:
    """compare_fields 产物：status 是 confirmed/withinTolerance/notComparable，需映射。"""
    payload = _read_json(path)
    diffs = payload if isinstance(payload, list) else (payload or {}).get("diffs") \
        if isinstance(payload, dict) else []
    if not isinstance(diffs, list):
        return
    for d in diffs:
        if not isinstance(d, dict):
            continue
        dim = str(d.get("dimension") or "")
        raw = str(d.get("status") or "")
        if not dim:
            continue
        # 映射到门禁词表：容差内=通过、超容差=失败、不可比=数据不可用
        mapped = {"confirmed": "fail", "withinTolerance": "pass",
                  "notComparable": "dataMissing"}.get(raw)
        if mapped is None:
            continue
        evidence.setdefault(dim, []).append({
            "status": mapped, "source": path.name,
            "detail": "{} 差异 {}".format(d.get("property"), d.get("delta")),
        })


# defect 词表 → 门禁词表。findings 类产物（extra_checks / runtime_observability /
# journeys）里的 status 是缺陷判定词（confirmed/pending/dataMissing），与
# coverage_gate 的 EXECUTED/NOT_EXECUTED 词表**不是一套**，必须映射后才能进 checks。
DEFECT_TO_GATE = {"confirmed": "fail", "pending": "pending", "dataMissing": "dataMissing"}


def collect_findings(path: Path, evidence: dict) -> None:
    """extra_checks / runtime_observability / journeys 的 findings 产物。"""
    payload = _read_json(path)
    for f in _findings_list(payload):
        if not isinstance(f, dict):
            continue
        dim = str(f.get("dimension") or "")
        status = DEFECT_TO_GATE.get(str(f.get("status") or ""))
        if not dim or status is None:
            continue
        evidence.setdefault(dim, []).append({
            "status": status, "source": path.name,
            "detail": str(f.get("symptom") or "")[:60],
        })


def collect_state_scenarios(path: Path, evidence: dict) -> None:
    """run_state_scenarios 产物：元素本身就是 {dimension,status,reason?}，直接采用。"""
    payload = _read_json(path)
    items = payload if isinstance(payload, list) else (payload or {}).get("results") \
        if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return
    for s in items:
        if not isinstance(s, dict):
            continue
        dim = str(s.get("dimension") or "")
        status = str(s.get("status") or "")
        if not dim or status not in VALID:
            continue
        evidence.setdefault(dim, []).append({
            "status": status, "source": path.name,
            "reason": s.get("reason"), "detail": "状态场景驱动",
        })


def collect_scenario_coverage(path: Path, evidence: dict) -> None:
    """scenario_coverage 产物：只用来回答「这个维度有场景但没跑」，不产生 pass。"""
    payload = _read_json(path)
    if not isinstance(payload, dict):
        return
    executed_by_dim = ((payload.get("executed") or {}).get("byDimension") or {})
    notrun_by_dim = ((payload.get("notExecuted") or {}).get("byDimension") or {})
    for dim, cnt in notrun_by_dim.items():
        if executed_by_dim.get(dim):
            continue  # 该维度有场景也跑过，交给别的证据说话
        evidence.setdefault(str(dim), []).append({
            "status": "notRun", "source": path.name,
            "reason": "该维度有 {} 条场景但未执行（场景执行率见 scenario_coverage.json）".format(cnt),
            "detail": "场景未执行",
        })


def summarize(dim_evidence: list) -> dict:
    """同维多份证据取最严重状态，并带上来源与原因。"""
    best = min(dim_evidence, key=lambda e: SEVERITY_ORDER.index(e["status"])
               if e["status"] in SEVERITY_ORDER else len(SEVERITY_ORDER))
    entry = {"status": best["status"]}
    reason = best.get("reason")
    if reason:
        entry["reason"] = reason
    sources = sorted({e["source"] for e in dim_evidence})
    entry["evidence"] = {"sources": sources, "count": len(dim_evidence)}
    if best.get("detail"):
        entry["note"] = best["detail"]
    return entry


def main() -> int:
    ap = argparse.ArgumentParser(description="把驱动产物的维度证据汇总成 report 的 checks 段")
    ap.add_argument("--report", required=True, type=Path, help="主 report.json（读写）")
    ap.add_argument("--style-diffs", type=Path, default=None, help="compare_fields 产物")
    ap.add_argument("--findings", type=Path, action="append", default=None,
                    help="findings 类产物（extra_checks / runtime_observability / journeys），可多份")
    ap.add_argument("--state-scenarios", type=Path, default=None, help="run_state_scenarios 产物")
    ap.add_argument("--scenario-coverage", type=Path, default=None, help="scenario_coverage 产物")
    ap.add_argument("--dimensions", type=Path,
                    default=Path(__file__).resolve().parent.parent / "schemas" / "check-dimensions.json")
    ap.add_argument("--write", action="store_true", help="把 checks 写回 report")
    args = ap.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    dims = load_dimensions(args.dimensions)
    if not dims:
        print("维度表为空: {}".format(args.dimensions), file=sys.stderr)
        return 3

    evidence: dict = {}
    if args.style_diffs:
        collect_style_diffs(args.style_diffs, evidence)
    for f in (args.findings or []):
        collect_findings(f, evidence)
    if args.state_scenarios:
        collect_state_scenarios(args.state_scenarios, evidence)
    if args.scenario_coverage:
        collect_scenario_coverage(args.scenario_coverage, evidence)

    # 已有手写 checks 原样保留：人填的比机器猜的优先级高
    existing = {}
    for container in (report.get("meta"), report):
        if not isinstance(container, dict):
            continue
        for key in ("checks", "dimensionResults", "checklist"):
            value = container.get(key)
            if isinstance(value, dict):
                existing = {str(k): v for k, v in value.items()}
            elif isinstance(value, list):
                existing = {str(e["id"]): e for e in value
                            if isinstance(e, dict) and e.get("id")}
        if existing:
            break

    checks = dict(existing)
    produced, kept_manual, not_run = 0, 0, 0
    for dim in dims:
        dim_id = str(dim["id"])
        if dim_id in checks:
            kept_manual += 1
            continue
        if dim_id in evidence:
            checks[dim_id] = summarize(evidence[dim_id])
            produced += 1
            if checks[dim_id]["status"] in NOT_EXECUTED:
                not_run += 1
        else:
            # 边界纪律：无证据 → notRun + 可回答「为什么没跑」的原因
            checks[dim_id] = {
                "status": "notRun",
                "reason": "无产物覆盖该维度（未提供对应驱动产物，或该维度无适用场景）",
                "evidence": {"sources": [], "count": 0},
            }
            produced += 1
            not_run += 1

    report.setdefault("meta", {})
    if isinstance(report["meta"], dict):
        report["meta"]["checks"] = checks
    if args.write:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "dimensions": len(dims),
        "producedByArtifacts": produced,
        "keptManual": kept_manual,
        "notRunTotal": not_run,
        "evidenceDimensions": sorted(evidence.keys()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
