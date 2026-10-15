#!/usr/bin/env python3
"""Start gate for UI parity runs.

This is a deterministic gate, not an interactive question UI. The orchestrator
must obtain the user's safety choice before invoking it and pass that choice in.
Non-test consultations should not call this script.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
TRIGGERS = re.compile(
    r"(开始|启动|重新执行|继续|跑|执行|检查|查看|看看|查查|验证|测|审)"
    r".*(ui\s*parity|figma|视觉|还原|走查|对照|响应式|自适应|断点|适配)"
    r"|ui\s*parity|走查",
    re.I,
)
FIGMA_HOSTS = {"figma.com", "www.figma.com"}


def is_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def is_figma_url(value: str | None) -> bool:
    if not is_url(value):
        return False
    host = urlparse(value).netloc.lower().split(":")[0]
    return host in FIGMA_HOSTS or host.endswith(".figma.com")


def should_start(instruction: str | None, figma_url: str | None, page_urls: list[str]) -> tuple[bool, str]:
    if instruction and TRIGGERS.search(instruction):
        return True, "explicit_test_instruction"
    if is_figma_url(figma_url) and any(is_url(item) for item in page_urls):
        return True, "figma_and_page_urls_present"
    return False, "not_a_test_start"


def run_json(command: list[str], cwd: Path) -> dict:
    proc = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "command failed").strip())
    return json.loads(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="UI parity 测试启动门禁")
    parser.add_argument("--instruction", default="")
    parser.add_argument("--figma-url", default="")
    parser.add_argument("--page-url", action="append", default=[])
    parser.add_argument("--safety-policy", choices=["all", "safe", "mockWrites", "staticOnly"], required=False)
    parser.add_argument("--test-environment-confirmed", action="store_true")
    parser.add_argument("--user-safety-selection", default="")
    parser.add_argument("--workdir", type=Path, default=Path("./parity-test"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    started, reason = should_start(args.instruction, args.figma_url, args.page_url)
    result = {"started": started, "trigger": reason}
    if not started:
        result["message"] = "未识别为 UI parity 测试启动，不执行环境检查或页面交互。"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if not args.safety_policy:
        result.update({"status": "blocked", "reason": "safety_policy_required", "message": "正式测试前必须先取得本轮安全策略选择。"})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    if args.safety_policy == "all" and not args.test_environment_confirmed:
        result.update({"status": "blocked", "reason": "test_environment_confirmation_required", "message": "全部操作必须确认当前为隔离测试环境。"})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    root = args.root.resolve()
    workdir = args.workdir if args.workdir.is_absolute() else root / args.workdir
    subprocess.run(
        [sys.executable, str(HERE / "init_workdir.py"), "--root", str(root)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    environment = run_json([sys.executable, str(HERE / "check_environment.py")], root)
    write_interception = {"all": "none", "safe": "abort", "mockWrites": "mock", "staticOnly": "abort"}[args.safety_policy]
    manifest = {
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "trigger": reason,
        "figmaUrl": args.figma_url,
        "pageUrls": args.page_url,
        "safetyPolicy": args.safety_policy,
        "userSafetySelection": args.user_safety_selection or args.safety_policy,
        "writeInterception": write_interception,
        "testEnvironmentConfirmed": bool(args.test_environment_confirmed),
        "environment": environment,
        "notRun": [] if args.safety_policy == "all" else ["caution", "danger"] if args.safety_policy == "safe" else ["danger"] if args.safety_policy == "mockWrites" else ["all interactive actions"],
    }
    workdir.mkdir(parents=True, exist_ok=True)
    manifest_path = workdir / "run-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    result.update({"status": "ready", "manifest": str(manifest_path), "environment": environment, "safetyPolicy": args.safety_policy})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
