#!/usr/bin/env python3
"""Prepare the parity working directory and make sure cost-sensitive files are ignored.

Creates the standard work dir layout and appends the ignore rules that keep
login state out of git. Idempotent: existing .gitignore lines are never rewritten,
only missing ones are appended.

Offline only.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

SUBDIRS = ("reports", "baselines", "shots", "extract", "button-audit", "baseline/runs")
IGNORE_RULES = (
    "# parity work dir (do not commit page credentials or screenshots)",
    "parity-test/",
    ".auth/",
    "auth.storage.json",
    "auth.cookies.json",
    "auth_info.json",
    "*.storage.json",
    "*.cookies.json",
    ".vp_profile*/",
)


def ensure_gitignore(path: Path, rules: tuple, dry_run: bool) -> dict:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    normalized = {line.strip() for line in existing}
    missing = [r for r in rules if r.strip() and r.strip() not in normalized]
    if missing and not dry_run:
        content = "\n".join(existing + ([""] if existing and existing[-1].strip() else []) + missing) + "\n"
        path.write_text(content, encoding="utf-8")
    return {"path": str(path), "added": missing, "created": not existing}


def main() -> int:
    ap = argparse.ArgumentParser(description="初始化 parity 工作目录并补齐忽略规则")
    ap.add_argument("--root", type=Path, default=Path.cwd(), help="工作区根目录，默认当前目录")
    ap.add_argument("--workdir", default="parity-test")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = args.root.resolve()
    workdir = root / args.workdir
    created = []
    for sub in SUBDIRS:
        target = workdir / sub
        if not target.exists():
            if not args.dry_run:
                target.mkdir(parents=True, exist_ok=True)
            created.append(str(target.relative_to(root)))

    auth_dir = workdir / ".auth"
    if not auth_dir.exists() and not args.dry_run:
        auth_dir.mkdir(parents=True, exist_ok=True)
        created.append(str(auth_dir.relative_to(root)))

    gitignore = root / ".gitignore"
    result = ensure_gitignore(gitignore, IGNORE_RULES, args.dry_run)

    print(json.dumps({
        "workdir": str(workdir),
        "created": created,
        "gitignore": result,
        "credentialDir": str(auth_dir),
        "note": "凭据与截图只落在工作目录内，且已被忽略规则覆盖；报告与日志不得写入 token 或 Cookie 原文",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
