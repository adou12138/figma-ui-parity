#!/usr/bin/env python3
"""场景执行率度量与门禁（计划 vs 实际）。

为什么需要：
  `discover_scenarios.py` 最多生成 300 条场景，但**场景 ID 从未进入任何产物**——
  `coverage_gate.py` 只统计「维度是否 executed」。于是"生成 300 条、实际跑了 20 条"
  在报告里完全看不出来：维度被跑过一次就算覆盖，生成的一大半场景静默消失。
  这正是本skill 反复警惕的"撑高覆盖率"老问题，只是发生在场景层而不是维度层。

本脚本补上这一层的闭环：
  输入
    --plan         discover_scenarios.py 的 scenarios.json（计划）
    --results      显式执行结果 JSON（agent/驱动回填，见下方形状）
    --from-report  report.json / *_report_full.json：从缺陷项里的 `scenario` 字段自动回收
  输出
    --out          覆盖率 JSON，形状可直接放进报告 payload 的 `scenarios` 段
    --enforce      门禁：① 有 notRun 却没写原因 → 失败；② 执行率低于 --min-rate → 失败
                   （沿用 coverage_gate 的"未执行必须写明原因"纪律，不静默放过）

状态词表与 coverage_gate.py 严格一致：
  pass / fail / warn / pending  -> 已执行
  notRun / dataMissing          -> 未执行（原因必填）

结果文件形状：
  {"results": [{"scenarioId": "S-0007", "status": "pass"},
               {"scenarioId": "S-0012", "status": "notRun",
                "reason": "安全策略 mockWrites 下 caution 场景不执行"}]}

豁免：`--exempt-dimensions 7.25,7.33` 把本轮结构性不适用的维度从分母剔除并**单列**
（不进分子也不进分母，但报告里可见——豁免必须显式且可查，不许静默）。

只读本地文件，不与网络交互。
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

EXECUTED = {"pass", "fail", "warn", "pending"}
NOT_EXECUTED = {"notRun", "dataMissing"}
VALID = EXECUTED | NOT_EXECUTED
RESULT_KEYS = ("results", "scenarios", "findings", "defects", "issues")


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("无法读取/解析 {}：{}".format(path, e), file=sys.stderr)
        return None


def plan_items(plan: dict) -> list:
    items = plan.get("scenarios") if isinstance(plan, dict) else None
    return [s for s in (items or []) if isinstance(s, dict) and s.get("id")]


def results_from_file(data) -> list:
    """显式结果文件 → [{scenarioId, status, reason}]"""
    out = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = None
        for key in RESULT_KEYS:
            if isinstance(data.get(key), list):
                rows = data[key]
                break
        rows = rows or []
    else:
        rows = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        sid = str(r.get("scenarioId") or r.get("id") or r.get("scenario") or "").strip()
        if not sid:
            continue
        status = str(r.get("status") or "").strip()
        if not status and r.get("outcome"):
            status = str(r.get("outcome"))
        out.append({"scenarioId": sid, "status": status,
                    "reason": r.get("reason") or r.get("note"), "implicit": False})
    return out


def results_from_report(report: dict) -> list:
    """从报告的缺陷项里回收带 `scenario` / `scenarioId` 的执行痕迹。

    有缺陷产出 ⇒ 该场景确实跑过（跑过并发现问题才算 executed）。
    """
    found = []
    seen = set()

    def walk(node):
        if isinstance(node, dict):
            sid = str(node.get("scenarioId") or node.get("scenario") or "").strip()
            if sid and sid not in seen:
                seen.add(sid)
                found.append({"scenarioId": sid, "status": "fail",
                              "reason": node.get("symptom") or "报告中有该场景产出的缺陷",
                              "implicit": True})
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(report)
    return found


def compute(plan: dict, results: list, exempt_dimensions) -> dict:
    items = plan_items(plan)
    total = len(items)
    exempt = set(exempt_dimensions or [])
    by_id = {s["id"]: s for s in items}

    executed, not_run, unexplained, unknown = 0, 0, [], []
    exec_by_dim, notrun_by_dim, exec_by_safety = {}, {}, {}

    # 索引结果。同一场景可能有多条记录（重跑 / 多轮回填并进），排序规则：
    #   ① 显式结果优先于从报告隐式回收的痕迹（隐式只知道"跑过并有缺陷"）；
    #   ② 同为显式时，**已执行优先于未执行** —— 只要有一条 pass/fail 就说明真跑过，
    #      不能因为首条是 notRun 就判它没跑（那会静默低估执行率：首条写了 reason
    #      时还不落 unexplained，等于完全看不见）。
    merged = {}
    multi = {}
    for r in results:
        sid = r["scenarioId"]
        multi.setdefault(sid, []).append(r)
        prev = merged.get(sid)
        if prev is None:
            merged[sid] = r
            continue
        prev_impl = bool(prev.get("implicit"))
        cur_impl = bool(r.get("implicit"))
        if prev_impl and not cur_impl:
            merged[sid] = r
        elif prev_impl == cur_impl:
            prev_exec = prev.get("status") in EXECUTED
            cur_exec = r.get("status") in EXECUTED
            if cur_exec and not prev_exec:
                merged[sid] = r
    multi_ids = sorted(sid for sid, rs in multi.items() if len(rs) > 1)
    flaky = sorted(sid for sid in multi_ids
                   if len({r.get("status") for r in multi[sid]}) > 1)

    counted = 0
    for sid, scene in by_id.items():
        dim = str(scene.get("dimension") or "")
        safety = str(scene.get("safety") or "safe")
        if dim in exempt:
            continue
        counted += 1
        rec = merged.get(sid)
        if rec is None:
            not_run += 1
            notrun_by_dim[dim] = notrun_by_dim.get(dim, 0) + 1
            unexplained.append("{} 计划内但无任何执行记录".format(sid))
            continue
        status = rec.get("status") or ""
        if status not in VALID:
            not_run += 1
            notrun_by_dim[dim] = notrun_by_dim.get(dim, 0) + 1
            unexplained.append("{} 状态值非法：{}".format(sid, status or "(空)"))
            continue
        if status in EXECUTED:
            executed += 1
            exec_by_dim[dim] = exec_by_dim.get(dim, 0) + 1
            exec_by_safety[safety] = exec_by_safety.get(safety, 0) + 1
        else:
            not_run += 1
            notrun_by_dim[dim] = notrun_by_dim.get(dim, 0) + 1
            if not rec.get("reason"):
                unexplained.append("{} 标记 {} 但未写明原因".format(sid, status))

    for sid in merged:
        if sid not in by_id:
            unknown.append(sid)

    rate = round(executed / counted, 4) if counted else 0.0
    trunc = plan.get("truncation") if isinstance(plan, dict) else None
    dropped = (trunc or {}).get("dropped", 0) if isinstance(trunc, dict) else 0
    # 【F26 反虚高】截断丢弃的场景此前单列但不进分母——生成 300 截到 30 后执行率
    # 仍可按 30 算到 100%，绝大多数意图场景被静默丢掉。rate 按原口径呈现，
    # 但新增保守口径 rateIncludingTruncated（分母 = counted + dropped），
    # 截断虚高从此有数可查。
    rate_with_trunc = round(executed / (counted + dropped), 4) if (counted + dropped) else 0.0
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "planned": {
            "total": total,
            "counted": counted,
            "exemptDimensions": sorted(exempt),
            "byDimension": _count_by(items, "dimension"),
            "bySafety": _count_by(items, "safety"),
            "truncated": dropped,
        },
        "executed": {
            "total": executed,
            "rate": rate,
            "rateIncludingTruncated": rate_with_trunc,
            "byDimension": dict(sorted(exec_by_dim.items())),
            "bySafety": dict(sorted(exec_by_safety.items())),
        },
        "notExecuted": {
            "total": not_run,
            "byDimension": dict(sorted(notrun_by_dim.items(), key=lambda kv: -kv[1])),
            "unexplained": unexplained,
        },
        "multipleRecords": {
            "scenarioIds": multi_ids,
            "flakyScenarioIds": flaky,
            "note": "同一场景在结果里出现多条记录（重跑/多轮并进）。本模块按"
                    "「显式优先 + 已执行优先」取状态；终态不一致的即不稳定。",
        },
        "unknownResults": unknown,
        "note": "场景执行率＝已执行 /（计划总数 − 显式豁免维度）。"
                "rateIncludingTruncated 把截断丢弃的场景计入分母（保守口径，F26）："
                "两者差距大说明大量意图场景被截断静默丢弃，覆盖率是虚的。"
                "维度被跑过一次即视为该维度已覆盖——**逐条场景是否真的跑了，只能看这里**。"
                "未执行项必须写明原因；豁免维度从分母剔除但在本段单列，不静默。",
    }


def _count_by(items, key) -> dict:
    out = {}
    for s in items:
        k = str(s.get(key) or "")
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def main() -> int:
    ap = argparse.ArgumentParser(description="场景执行率度量与门禁（计划 vs 实际）")
    ap.add_argument("--plan", required=True, type=Path, help="discover_scenarios.py 的 scenarios.json")
    ap.add_argument("--results", type=Path, help="显式执行结果 JSON")
    ap.add_argument("--from-report", type=Path, help="report.json / *_report_full.json（从缺陷的 scenario 字段回收）")
    ap.add_argument("--out", type=Path, help="覆盖率 JSON 输出（可直接放进报告 payload 的 scenarios 段）")
    ap.add_argument("--min-rate", type=float, default=None, help="执行率下限，低于则 --enforce 失败（默认不设限）")
    ap.add_argument("--exempt-dimensions", default="", help="本轮结构性不适用的维度，逗号分隔（从分母剔除并单列）")
    ap.add_argument("--enforce", action="store_true", help="门禁模式")
    args = ap.parse_args()

    plan = load_json(args.plan)
    if plan is None:
        return 2
    results = []
    if args.results:
        data = load_json(args.results)
        if data is None:
            return 2
        results.extend(results_from_file(data))
    if args.from_report:
        report = load_json(args.from_report)
        if report is None:
            return 2
        results.extend(results_from_report(report))

    exempt = [x.strip() for x in str(args.exempt_dimensions or "").split(",") if x.strip()]
    cov = compute(plan, results, exempt)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(cov, ensure_ascii=False, indent=2), encoding="utf-8")
    cov["output"] = str(args.out) if args.out else None
    print(json.dumps(cov, ensure_ascii=False, indent=2))

    if not args.enforce:
        return 0
    # 【审查修复·P2-13】计划为空（scenarios.json 缺失/为空/全部维度被豁免）时，
    # counted=0、rate=0.0——旧版落入裸比较，报「执行率 0% 低于下限」，把
    # 「根本没产出计划」误导成「有计划没执行」。空计划是更上游的故障，
    # 单独拦截并说清根因；此时 min-rate/unexplained 都没有意义。
    if cov["planned"]["counted"] == 0:
        print("错误：计划为空——无场景进入分母（scenarios.json 缺失、为空或全部维度被豁免），"
              "无场景可度量，门禁不放行", file=sys.stderr)
        return 1
    problems = []
    if cov["notExecuted"]["unexplained"]:
        problems.append("存在未写明原因的未执行场景 {} 条（如 {}）".format(
            len(cov["notExecuted"]["unexplained"]), "、".join(cov["notExecuted"]["unexplained"][:5])))
    # 【审查修复·P2-13】门禁比较前判 rate 非 None：rate 当前由 compute 兜底为 0.0，
    # 但下游（如未来把空计划改为 rate=None）不该靠裸比较 TypeError 崩掉门禁。
    rate_val = cov["executed"].get("rate")
    if args.min_rate is not None and rate_val is not None and rate_val < args.min_rate:
        problems.append("场景执行率 {:.0%} 低于下限 {:.0%}，未执行分布：{}".format(
            cov["executed"]["rate"], args.min_rate,
            json.dumps(cov["notExecuted"]["byDimension"], ensure_ascii=False)))
    if problems:
        print("错误：" + "；".join(problems), file=sys.stderr)
        return 1
    if cov["unknownResults"]:
        print("警告：回填了计划外的场景 ID {} 个（可能来自旧计划），不阻塞门禁".format(len(cov["unknownResults"])),
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())