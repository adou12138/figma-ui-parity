#!/usr/bin/env python3
"""Normalize and deduplicate defect evidence without accessing network or credentials.

Entry keys accepted (in order): a bare JSON list, or an object holding one of
`diffs` / `styleDiffs` / `defects` / `findings` / `issues`. This matches every
producer in this skill (compare_fields -> styleDiffs, extra_checks -> findings,
assembled reports -> defects) so the normalizer never silently sees zero items.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ITEM_KEYS = ("diffs", "styleDiffs", "defects", "findings", "issues")


def extract_items(data) -> tuple:
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        for key in ITEM_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                return value, key
    return [], None


def fingerprint(item):
    e = item.get("element", {}) if isinstance(item.get("element"), dict) else {}
    parts = [str(item.get("page", "")), str(item.get("scenario", "")), str(e.get("selector", "")), str(e.get("nth", "")), str(item.get("category", "")), str(item.get("viewport", ""))]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input", type=Path)
    ap.add_argument("output", type=Path)
    a = ap.parse_args()
    data = json.loads(a.input.read_text(encoding="utf-8"))
    items, source_key = extract_items(data)
    items = [i for i in items if isinstance(i, dict)]
    merged = {}
    for item in items:
        fp = item.get("fingerprint") or fingerprint(item)
        item["fingerprint"] = fp
        if fp not in merged:
            merged[fp] = item
            merged[fp].setdefault("sources", [])
        else:
            old = merged[fp]
            old["sources"] = sorted(set(old.get("sources", []) + item.get("sources", [item.get("source", "unknown")])))
            old.setdefault("evidence", []).extend(item.get("evidence", []))
    result = {"diffs": list(merged.values()), "deduplicated": len(items) - len(merged), "total": len(merged),
              "sourceKey": source_key or "bare-list"}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
