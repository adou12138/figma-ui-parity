#!/usr/bin/env python3
"""Compute and enforce checklist coverage for a parity report.

Reads the canonical dimension list and the report's per-dimension results,
then writes `meta.coverage` back into the report. No network, no page access.

Status vocabulary (strictly distinct, do not blur):
  pass / fail / warn / pending  -> executed
  notRun                        -> never ran
  dataMissing                   -> wanted to run but data was unusable
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

EXECUTED = {"pass", "fail", "warn", "pending"}
NOT_EXECUTED = {"notRun", "dataMissing"}
VALID = EXECUTED | NOT_EXECUTED


def load_dimensions(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [d for d in data.get("dimensions", []) if d.get("id")]


def extract_checks(report: dict) -> dict:
    """Accept meta.checks / checks / dimensionResults, keyed by dimension id."""
    for container in (report.get("meta"), report):
        if not isinstance(container, dict):
            continue
        for key in ("checks", "dimensionResults", "checklist"):
            value = container.get(key)
            if isinstance(value, dict):
                return {str(k): v for k, v in value.items()}
            if isinstance(value, list):
                out = {}
                for entry in value:
                    if isinstance(entry, dict) and entry.get("id"):
                        out[str(entry["id"])] = entry
                if out:
                    return out
    return {}


def status_of(entry) -> tuple:
    if isinstance(entry, dict):
        return str(entry.get("status", "")), entry.get("reason") or entry.get("note")
    return str(entry), None


def main() -> int:
    ap = argparse.ArgumentParser(description="按检查维度表计算覆盖率并执行门禁")
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--dimensions", type=Path, default=Path(__file__).resolve().parent.parent / "schemas" / "check-dimensions.json")
    ap.add_argument("--threshold", type=float, default=0.70)
    ap.add_argument("--enforce", action="store_true", help="覆盖率低于阈值时以非零码退出")
    ap.add_argument("--write", action="store_true", help="把 meta.coverage 写回报告")
    args = ap.parse_args()

    report = json.loads(args.report.read_text(encoding="utf-8"))
    dims = load_dimensions(args.dimensions)
    if not dims:
        print("维度表为空: {}".format(args.dimensions), file=sys.stderr)
        return 3
    checks = extract_checks(report)

    executed, not_run, data_missing = 0, 0, 0
    unexplained, missing_ids, invalid = [], [], []
    for dim in dims:
        dim_id = dim["id"]
        if dim_id not in checks:
            missing_ids.append(dim_id)
            not_run += 1
            # 【F23 反门禁绕过】维度**整体缺失**是最严重的未说明——删掉一行 checks
            # 就能让该维度逃过「notRun 必须写原因」的检查（实测删 7.34 → exit 0、
            # coverageRate 0.974）。缺失视同 notRun 未写原因，计入 unexplained。
            unexplained.append("{} 维度整体缺失（未出现在 checks 中，缺维度=最严重的未说明）".format(dim_id))
            continue
        status, reason = status_of(checks[dim_id])
        if status not in VALID:
            invalid.append({"id": dim_id, "status": status})
            continue
        if status in EXECUTED:
            executed += 1
        elif status == "notRun":
            not_run += 1
            if not reason:
                unexplained.append("{} 标记 notRun 但未写明原因".format(dim_id))
        else:
            data_missing += 1
            if not reason:
                unexplained.append("{} 标记 dataMissing 但未写明原因".format(dim_id))

    total = len(dims)
    rate = round(executed / total, 4) if total else 0.0
    coverage = {
        "total": total,
        "executed": executed,
        "notRun": not_run,
        "dataMissing": data_missing,
        "coverageRate": rate,
        "fullCoverage": (not_run + data_missing) == 0,
        "belowThreshold": rate < args.threshold,
        "threshold": args.threshold,
        "missingDimensions": missing_ids,
        "unexplained": unexplained,
        "invalidStatus": invalid,
        "notExecutedDimensions": [d["id"] for d in dims if d["id"] in checks and status_of(checks[d["id"]])[0] in NOT_EXECUTED],
    }

    report.setdefault("meta", {})
    if isinstance(report["meta"], dict):
        report["meta"]["checks"] = checks
        report["meta"]["coverage"] = coverage
    if args.write:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(coverage, ensure_ascii=False, indent=2))

    if invalid:
        print("错误：存在非法状态值（只允许 pass/fail/warn/pending/notRun/dataMissing）", file=sys.stderr)
        return 4
    if unexplained:
        print("错误：存在未写明原因的未执行项：{}".format("；".join(unexplained)), file=sys.stderr)
        return 5
    if args.enforce and rate < args.threshold:
        print("门禁未通过：覆盖率 {:.0%} 低于阈值 {:.0%}，未覆盖 {}".format(
            rate, args.threshold, "、".join(coverage["notExecutedDimensions"] + coverage["missingDimensions"])), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
