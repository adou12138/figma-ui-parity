#!/usr/bin/env python3
"""Audit ignored regions so suppression cannot silently hide real regressions.

Reports expired / stale / malformed / over-broad regions and prints the list that
is effective for the current run (the report must embed that list).

Offline only.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import date, datetime, timedelta
from pathlib import Path

DEFAULT_TTL_DAYS = 90
BROAD_SELECTORS = {"*", "body", "html", "div", "main", "#app", "#root", ".container"}
REQUIRED = ("id", "selector", "changeFingerprint", "reason")


def parse_date(value) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(text[:len(fmt) + 4], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="忽略区审计：过期、宽泛与字段缺失检查")
    ap.add_argument("--file", type=Path, default=Path("./parity-test/ignoredRegions.json"))
    ap.add_argument("--ttl-days", type=int, default=DEFAULT_TTL_DAYS)
    ap.add_argument("--today", default=None, help="用于测试的当天日期 YYYY-MM-DD，默认取系统日期")
    ap.add_argument("--enforce", action="store_true", help="存在过期或宽泛忽略项时以非零码退出")
    ap.add_argument("--output", type=Path, default=None, help="审计结论写入文件，供报告引用")
    args = ap.parse_args()

    today = parse_date(args.today) or date.today()
    if not args.file.exists():
        result = {"file": str(args.file), "exists": False, "effective": [], "expired": [], "malformed": [], "overBroad": [],
                  "summary": "无忽略文件，本次不屏蔽任何区域"}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    data = json.loads(args.file.read_text(encoding="utf-8"))
    regions = data.get("regions") if isinstance(data, dict) else data
    regions = regions if isinstance(regions, list) else []

    effective, expired, malformed, over_broad = [], [], [], []
    for region in regions:
        if not isinstance(region, dict):
            malformed.append({"reason": "条目不是对象", "value": str(region)[:80]})
            continue
        rid = region.get("id") or region.get("selector") or "(无 id)"
        missing = [f for f in REQUIRED if not region.get(f)]
        if missing:
            malformed.append({"id": rid, "missing": missing})
        expires_at = parse_date(region.get("expiresAt"))
        reviewed_at = parse_date(region.get("reviewedAt"))
        deadline = expires_at or ((reviewed_at + timedelta(days=args.ttl_days)) if reviewed_at else None)
        entry = {"id": rid, "selector": region.get("selector"), "reason": region.get("reason"),
                 "expiresAt": expires_at.isoformat() if expires_at else None,
                 "reviewedAt": reviewed_at.isoformat() if reviewed_at else None,
                 "autoDeadline": deadline.isoformat() if deadline else None}
        if deadline and deadline < today:
            entry["expiredDays"] = (today - deadline).days
            expired.append(entry)
            continue
        if deadline is None:
            entry["note"] = "未声明 expiresAt 或 reviewedAt，无法判断是否过期"
            over_broad.append({"id": rid, "reason": "缺少到期信息，需补 expiresAt 或 reviewedAt"})
        selector = str(region.get("selector") or "").strip().lower()
        if selector in BROAD_SELECTORS:
            over_broad.append({"id": rid, "reason": "忽略选择器过于宽泛：{}".format(selector)})
        applies = region.get("appliesTo") or []
        if "diff" in applies and not region.get("bbox") and not selector:
            over_broad.append({"id": rid, "reason": "appliesTo 含 diff 但既无 selector 也无 bbox"})
        effective.append(entry)

    result = {
        "file": str(args.file), "exists": True, "today": today.isoformat(), "ttlDays": args.ttl_days,
        "effective": effective, "expired": expired, "malformed": malformed, "overBroad": over_broad,
        "summary": "生效 {} 条，过期 {} 条，字段缺失 {} 条，宽泛或缺少到期信息 {} 条".format(
            len(effective), len(expired), len(malformed), len(over_broad)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.enforce and (expired or malformed or over_broad):
        print("门禁未通过：存在过期、字段缺失或宽泛/缺到期信息的忽略项，需复核后移除或补全", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
