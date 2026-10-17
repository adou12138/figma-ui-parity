#!/usr/bin/env python3
"""Normalize and deduplicate defect evidence without accessing network or credentials.

Entry keys accepted (in order): a bare JSON list, or an object holding one of the
keys in `defect_keys.CONTAINER_KEYS`. The key table lives in exactly one place
(`defect_keys.py`) because three consumers used to keep their own copy and drifted
apart — `gen_excel_fallback` lost every `styleDiffs` defect and `validate_defects`
rejected `findings`-shaped reports with rc=6. This matches every producer in this
skill (compare_fields -> styleDiffs, extra_checks -> findings, assembled reports ->
defects) so the normalizer never silently sees zero items.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

import defect_keys as DK

ITEM_KEYS = DK.CONTAINER_KEYS

# 历史 dict 形容器的严重度桶序（与 gen_excel_fallback 的消费顺序一致：高→中→低）
_SEVERITY_ORDER = ("high", "medium", "low")


def extract_items(data) -> tuple:
    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        for key in ITEM_KEYS:
            value = data.get(key)
            if isinstance(value, list):
                return value, key
        # 【审查修复·M1】历史 dict 形容器：diffs 是 {"high": [...], "medium": [...],
        # "low": [...]} 按严重度分桶（defect_keys.LEGACY_DICT_KEY，主报告模板
        # references/report-templates.md 的 diffs 段即此形状，gen_excel_fallback
        # 早已消费）。旧版只认列表形容器，按模板写的报告在这里收 0 条，全部缺陷
        # 在归一链路静默蒸发。现与 gen_excel_fallback 同一桶序合并全部桶；
        # 桶值非列表的键跳过不猜（不把 {"diffs": {"meta": {...}}} 之类误判成分桶）。
        legacy = data.get(DK.LEGACY_DICT_KEY)
        if isinstance(legacy, dict):
            merged = []
            for level in _SEVERITY_ORDER:
                bucket = legacy.get(level)
                if isinstance(bucket, list):
                    merged.extend(bucket)
            return merged, "diffs:severity-buckets"
    return [], None


def fingerprint(item):
    """缺陷指纹（结构化口径，**不含任何自然语言描述**）。

    【F8 证据蒸发修复】旧指纹 = page+scenario+selector+nth+category+viewport，
    不含 dimension/property——旅程/状态类 findings 多为 element:null、
    无 page/scenario/category（只写 dimension+property），实测 3 条不同的 7.39
    缺陷（doc-error / noop / back-broken）被塌缩成 1 条，整页旅程缺陷在归一阶段
    蒸发。故补入 dimension|property|raw.url。

    【措辞漂移修复】中途又把 symptom[:48] 塞进了指纹——措辞差一个空格的**同一**缺陷
    指纹就不同，真重复漏合并（实测同批 3 条近重复 deduplicated=0），且与本函数
    docstring 声称的「对『真重复』的合并语义不变」自相矛盾。指纹的职责是「是不是
    同一个缺陷」，而 symptom 是同一缺陷的自由措辞：把它计入指纹等于要求复述逐字
    一致。故 symptom 彻底移出指纹；同一元素的同维度/同属性缺陷靠 evidence 合并，
    不同措辞不再分裂成多条。raw.url 保留：不同来源 URL 确属不同缺陷。
    """
    e = item.get("element", {}) if isinstance(item.get("element"), dict) else {}
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    parts = [
        str(item.get("page", "")), str(item.get("scenario", "")),
        str(e.get("selector", "")), str(e.get("nth", "")),
        str(item.get("category", "")), str(item.get("viewport", "")),
        # F8 新增：同一元素上不同 dimension/property 是不同缺陷
        str(item.get("dimension", "")),
        str(item.get("property", "")),
        # 指纹标识符（由 producer 提供的稳定 id，不含自然语言描述）
        str(item.get("id", "")),
        str(e.get("anchor", "")),
        str(raw.get("url", "")), str(raw.get("signature", "")),
        str(raw.get("method", "")), str(raw.get("status", "")),
    ]
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
