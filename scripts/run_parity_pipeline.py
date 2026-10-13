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
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    node = resolve_node()
    workdir: Path = args.workdir
    outdir: Path = args.outdir or workdir / "reports"
    log: dict = {"workdir": str(workdir), "dryRun": args.dry_run}

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
        stage("discover_scenarios", [sys.executable, str(HERE / "discover_scenarios.py"),
                                     "--design", str(design_json), "--page", str(page_json),
                                     "--pairs", str(style_diffs),
                                     "--output", str(workdir / "scenarios.json")], args.dry_run, log)
    else:
        log["compare_fields"] = {"status": "notRun", "reason": "缺少 --design-json 或 --page-json"}
        log["discover_scenarios"] = {"status": "notRun", "reason": "缺少 --design-json 或 --page-json"}

    if args.report and args.report.exists():
        stage("validate_defects", [sys.executable, str(HERE / "validate_defects.py"),
                                   "--report", str(args.report), "--strict"], args.dry_run, log)
        stage("coverage_gate", [sys.executable, str(HERE / "coverage_gate.py"),
                                "--report", str(args.report), "--enforce", "--write"], args.dry_run, log)
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
