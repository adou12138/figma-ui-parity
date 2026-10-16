#!/usr/bin/env python3
"""Chain the deterministic parity scripts into one runnable pipeline.

This orchestrator only launches local scripts with explicit arguments. It does
not read credentials, does not touch the network itself, and never mutates the
page. Every stage records `ran` / `skipped` with a reason so reports can state
the real coverage.
"""
from __future__ import annotations
import argparse, json, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def resolve_node() -> str:
    return shutil.which("node") or "node"


def stage(name: str, command: list, dry_run: bool, log: dict) -> None:
    printable = " ".join(command)
    if dry_run:
        log[name] = {"status": "planned", "command": printable}
        print("[plan] {}".format(printable))
        return
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        log[name] = {"status": "notRun", "reason": "命令不存在", "command": printable}
        print("[skip] {} -> 命令不存在".format(name))
        return
    except subprocess.TimeoutExpired:
        log[name] = {"status": "notRun", "reason": "执行超时", "command": printable}
        print("[skip] {} -> 执行超时".format(name))
        return
    log[name] = {
        "status": "ran" if proc.returncode == 0 else "failed",
        "returncode": proc.returncode,
        "command": printable,
        "stdoutTail": (proc.stdout or "")[-400:],
        "stderrTail": (proc.stderr or "")[-400:],
    }
    print("[{}] {} (rc={})".format("ok" if proc.returncode == 0 else "fail", name, proc.returncode))


def main() -> int:
    ap = argparse.ArgumentParser(description="按序执行parity确定性脚本")
    ap.add_argument("--workdir", default="./parity-test", type=Path)
    ap.add_argument("--page-url", default=None, help="稳定化与提取阶段的目标页面 URL")
    ap.add_argument("--design-json", default=None, type=Path, help="extract_design_fields.py 产物；与 --page-json 同时提供时触发逐字段比对链路")
    ap.add_argument("--page-json", default=None, type=Path, help="collect_page_inventory.js 产物")
    ap.add_argument("--figma-png", default=None, type=Path)
    ap.add_argument("--page-png", default=None, type=Path)
    ap.add_argument("--enhanced-diff", action="store_true",
                    help="diff_score 用增强模式（抗锯齿/孤立噪点抑制）；口径与基础模式不同，跨模式比基线前先确认同模式")
    ap.add_argument("--report", default=None, type=Path, help="上游 report.json")
    ap.add_argument("--outdir", default=None, type=Path)
    ap.add_argument("--patterns", default=None, type=Path,
                    help="缺陷模式池 JSON；默认 assets/defect_patterns.json。"
                         "池为空时行为与不传完全一致（冷启动零影响）")
    ap.add_argument("--no-patterns", action="store_true", help="关掉模式池接入（不传 --patterns、不跑 merge）")
    ap.add_argument("--combo-depth", default=None, type=int,
                    help="透传给 discover_scenarios：1=单点（默认）；2=加深异常数据与逐断点展开")
    ap.add_argument("--roles", default=None, help="透传给 discover_scenarios：逗号分隔角色，用于 7.34")
    ap.add_argument("--breakpoints", default=None, help="透传给 discover_scenarios：组合用断点，逗号分隔")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    node = resolve_node()
    workdir: Path = args.workdir
    outdir: Path = args.outdir or workdir / "reports"
    log: dict = {"workdir": str(workdir), "dryRun": args.dry_run}
    # 【F2】pool 只在 compare_fields 分支里赋值，而尾部 pattern_pool_merge 在
    # `if args.report` 分支用它——「只重出报告」用法（--report 不带 --design-json/
    # --page-json，最常见）会 UnboundLocalError 崩溃，且崩溃发生在 pipeline-log
    # 写入之前，失败无痕。提到 main() 开头初始化。
    pool = None if args.no_patterns else (args.patterns or (HERE.parent / "assets" / "defect_patterns.json"))

    if args.page_url:
        stage("stabilize", [node, str(HERE / "stabilize.js"), "--url", args.page_url], args.dry_run, log)

    if args.figma_png and args.page_png:
        # --enhanced-diff 是 opt-in：开启后 diff_score 用抗锯齿/孤立噪点抑制，
        # diffScore 口径与基础模式不同，跨模式比基线前要先确认基线同模式。
        stage("diff_score", [node, str(HERE / "diff_score.js"), "--a", str(args.figma_png), "--b", str(args.page_png),
                             "--out", str(outdir / "mask.png")] + (["--enhanced"] if args.enhanced_diff else []),
              args.dry_run, log)
    else:
        log["diff_score"] = {"status": "notRun", "reason": "缺少 --figma-png 或 --page-png"}

    audit_dir = workdir / "button-audit"
    if audit_dir.exists():
        stage("button_report", [node, str(HERE / "gen_button_report.cjs"), "--dir", str(audit_dir), "--out", str(outdir)],
              args.dry_run, log)
    else:
        log["button_report"] = {"status": "notRun", "reason": "缺少 {}".format(audit_dir)}

    journey = workdir / "journey.json"
    coverage = workdir / "coverage.json"
    if journey.exists() and coverage.exists():
        stage("journey_coverage", [node, str(HERE / "journey_coverage.cjs"), "--journey", str(journey),
                                   "--coverage", str(coverage)], args.dry_run, log)
    else:
        log["journey_coverage"] = {"status": "notRun", "reason": "缺少 journey.json 或 coverage.json"}

    design_json = args.design_json
    page_json = args.page_json
    style_diffs = workdir / "styleDiffs.json"
    if design_json and design_json.exists() and page_json and page_json.exists():
        stage("compare_fields", [sys.executable, str(HERE / "compare_fields.py"),
                                 "--design", str(design_json), "--page", str(page_json),
                                 "--page-url", args.page_url or "",
                                 "--output", str(style_diffs)], args.dry_run, log)
        # 模式池接入：默认把 assets/defect_patterns.json 传给 discover_scenarios，
        # 让「历史高频翻车的维度必被覆盖」在标准管线里真的发生。池为空时
        # pattern_weights 返回 {}、applied=false，产物与不传完全一致（冷启动零影响）。
        # pool 已在 main() 开头初始化（F2），这里只做局部覆盖说明。
        patterns_args = [] if pool is None else ["--patterns", str(pool)]
        passthrough = []
        if args.combo_depth:
            passthrough += ["--combo-depth", str(args.combo_depth)]
        if args.roles:
            passthrough += ["--roles", args.roles]
        if args.breakpoints:
            passthrough += ["--breakpoints", args.breakpoints]
        stage("discover_scenarios", [sys.executable, str(HERE / "discover_scenarios.py"),
                                     "--design", str(design_json), "--page", str(page_json),
                                     "--pairs", str(style_diffs),
                                     "--output", str(workdir / "scenarios.json")] + patterns_args + passthrough,
              args.dry_run, log)
    else:
        log["compare_fields"] = {"status": "notRun", "reason": "缺少 --design-json 或 --page-json"}
        log["discover_scenarios"] = {"status": "notRun", "reason": "缺少 --design-json 或 --page-json"}

    if args.report and args.report.exists():
        # 先把各驱动产物的维度证据汇总进 report 的 checks 段，再进门禁——否则
        # coverage_gate 会因为「维度缺失 / notRun 未写原因」直接非零退出，而那份
        # 39 行的维度→状态→原因表此前只能靠 agent 手工拼装。
        # 只收管线与同目录下已存在的产物，缺的就少一路证据（该维度会落到 notRun）。
        # **不判断有无产物**：report 里没有手写 checks 时，也要靠本阶段生成一份
        # 全 notRun 的维度表，否则 coverage_gate 会因「维度缺失」直接非零退出。
        af = []
        if style_diffs.exists():
            af += ["--style-diffs", str(style_diffs)]
        for name, flag in (("findings.json", "--findings"),
                           ("runtime.json", "--findings"),
                           ("journey_findings.json", "--findings"),
                           ("state_scenarios.json", "--state-scenarios"),
                           ("scenario_coverage.json", "--scenario-coverage")):
            candidate = workdir / name
            if candidate.exists():
                af += [flag, str(candidate)]
        stage("assemble_report", [sys.executable, str(HERE / "assemble_report.py"),
                                  "--report", str(args.report)] + af + ["--write"],
              args.dry_run, log)
        stage("validate_defects", [sys.executable, str(HERE / "validate_defects.py"),
                                   "--report", str(args.report), "--strict"], args.dry_run, log)
        stage("coverage_gate", [sys.executable, str(HERE / "coverage_gate.py"),
                                "--report", str(args.report), "--enforce", "--write"], args.dry_run, log)
        # 【F3】门禁失败必须短路后续报告阶段——SKILL.md「校验不通过不得出报告」。
        # 旧行为：validate/coverage 失败只记 status=failed，继续 generate_reports 并
        # return 0，坏数据照常产出三件套报告（最危险的静默假通过）。
        gate_failed = [n for n in ("validate_defects", "coverage_gate", "assemble_report")
                       if log.get(n, {}).get("status") in ("failed",)]
        if gate_failed and not args.dry_run:
            for n in gate_failed:
                print("[abort] {} 失败，按「校验不通过不得出报告」短路后续阶段".format(n))
            log["generate_reports"] = {
                "status": "notRun",
                "reason": "门禁失败短路：{}".format(", ".join(gate_failed)),
            }
            log["baseline_regression"] = {
                "status": "notRun",
                "reason": "门禁失败短路：{}".format(", ".join(gate_failed)),
            }
            if "pattern_pool_merge" not in log:
                log["pattern_pool_merge"] = {
                    "status": "notRun",
                    "reason": "门禁失败短路：{}".format(", ".join(gate_failed)),
                }
            outdir.mkdir(parents=True, exist_ok=True)
            log_file = outdir / "pipeline-log.json"
            log_file.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
            print("日志: {}".format(log_file))
            return 1
        ignore_file = workdir / "ignoredRegions.json"
        if ignore_file.exists():
            stage("ignore_regions", [sys.executable, str(HERE / "ignore_regions.py"),
                                     "--file", str(ignore_file),
                                     "--output", str(outdir / "ignore-audit.json"), "--enforce"], args.dry_run, log)
        stage("baseline_regression", [node, str(HERE / "baseline_regression.cjs"), "--current", str(args.report),
                                      "--baseline-dir", str(workdir / "baseline"), "--out", str(outdir / "regression.json")],
              args.dry_run, log)
        stage("generate_reports", [sys.executable, str(HERE / "generate_reports.py"), "--input", str(args.report),
                                   "--outdir", str(outdir)], args.dry_run, log)
        # 历史学习闭环的最后一环：把本轮缺陷按指纹并回池（幂等，无新模式不写盘）。
        # 只累积与排序，不自动生成用例——见 SKILL.md 对 bug_pattern_pool 的纪律。
        if pool is not None:
            stage("pattern_pool_merge", [sys.executable, str(HERE / "pattern_pool.py"),
                                         "--merge", str(args.report), "--pool", str(pool)],
                  args.dry_run, log)
    else:
        log["baseline_regression"] = {"status": "notRun", "reason": "缺少 --report"}
        log["generate_reports"] = {"status": "notRun", "reason": "缺少 --report"}

    log_file = outdir / "pipeline-log.json"
    if not args.dry_run:
        outdir.mkdir(parents=True, exist_ok=True)
        log_file.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
        print("日志: {}".format(log_file))
    return 0


if __name__ == "__main__":
    sys.exit(main())
