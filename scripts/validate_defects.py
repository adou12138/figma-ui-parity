#!/usr/bin/env python3
"""Validate defects in a parity report against schemas/defect.schema.json.

Why this exists: the schema used to be prose-only, so "每条缺陷必须有现象和元素定位"
was unenforceable — a defect missing `symptom` or `element` passed silently.
This script turns that rule into a hard gate. Offline, no external dependency.

Exit codes: 0 ok / 2 input missing / 4 schema load error / 6 validation failed.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

import defect_keys as DK

TYPE_MAP = {
    "object": dict, "array": list, "string": str, "number": (int, float),
    "integer": int, "boolean": bool, "null": type(None),
}


def type_ok(value, expected) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    if isinstance(expected, list):
        return any(type_ok(value, t) for t in expected)
    python_type = TYPE_MAP.get(expected)
    return isinstance(value, python_type) if python_type else True


def validate(value, schema: dict, path: str, errors: list, strict: bool) -> None:
    expected = schema.get("type")
    if expected and not type_ok(value, expected):
        errors.append("{}: 类型应为 {}，实际 {}".format(path, expected, type(value).__name__))
        return
    if "enum" in schema and value not in schema["enum"]:
        errors.append("{}: 取值 {} 不在允许集合 {}".format(path, value, schema["enum"]))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append("{}: 长度 {} 小于 {}（{}）".format(path, len(value), schema["minLength"], schema.get("description", "")))
        if "pattern" in schema:
            import re
            if not re.match(schema["pattern"], value):
                errors.append("{}: 值 {} 不匹配 {}".format(path, value, schema["pattern"]))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("{}: 值 {} 小于最小值 {}".format(path, value, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append("{}: 值 {} 大于最大值 {}".format(path, value, schema["maximum"]))
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append("{}: 缺少必填字段 {}".format(path, key))
        for key, sub in (schema.get("properties") or {}).items():
            if key in value:
                validate(value[key], sub, "{}.{}".format(path, key), errors, strict)
    if isinstance(value, list) and "items" in schema:
        for index, entry in enumerate(value):
            validate(entry, schema["items"], "{}[{}]".format(path, index), errors, strict)


def collect(report: dict) -> list:
    """收集待校验的缺陷条目。

    【F25 修复】compare_fields.py 的产物键是 `styleDiffs`，旧 collect 只认
    defects/defectList/issues——生产方与校验器对「缺陷在哪」认知不一致：styleDiffs 里
    status=confirmed 的差异完全没被校验，且顶层无 defects 键时严格模式直接 rc=6。

    【键表统一】候选键现取自 defect_keys.CONTAINER_KEYS（唯一来源）。此前漏了
    `findings` / `diffs`，而 generate_reports / gen_excel_fallback / normalize_evidence
    都认这两个键——于是 findings 型报告一条都不校验，严格模式还把这种合法形状误判成
    「忘填缺陷数组键」rc=6。

    筛选策略保持原语义不变：defects/defectList/issues 视为**已确认的交付产物**全量收；
    其余键（styleDiffs / diffs / findings）是原始差异，只收 status == "confirmed"，
    避免把 withinTolerance / pending 的容差内差异当缺陷校验。
    """
    primary = ("defects", "defectList", "issues")
    secondary = tuple(k for k in DK.CONTAINER_KEYS if k not in primary)
    out: list = []
    for key in primary:
        value = report.get(key)
        if isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    out.append(("{}[{}]".format(key, index), item))
            break
    # 其余容器键与 primary 并存时全部收集（compare_fields 同时输出多类差异）。
    for key in secondary:
        value = report.get(key)
        if not isinstance(value, list):
            continue
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                continue
            if item.get("status") != "confirmed":
                continue
            item = dict(item)
            item.setdefault("status", "confirmed")
            out.append(("{}[{}]".format(key, index), item))
    for key in ("pendingChecks", "pending"):
        value = report.get(key)
        if isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    item = dict(item)
                    item.setdefault("status", "pending")
                    out.append(("{}[{}]".format(key, index), item))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="按 defect.schema.json 校验报告中的缺陷记录")
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--schema", type=Path, default=Path(__file__).resolve().parent.parent / "schemas" / "defect.schema.json")
    ap.add_argument("--strict", action="store_true", help="额外要求 evidence 非空、reproduction 非空、suggestion 非空")
    ap.add_argument("--write", action="store_true", help="通过时把校验结论写回 report.meta.defectValidation")
    args = ap.parse_args()

    if not args.report.exists():
        print("报告不存在: {}".format(args.report), file=sys.stderr)
        return 2
    try:
        schema = json.loads(args.schema.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print("schema 无法解析: {}".format(exc), file=sys.stderr)
        return 4

    report = json.loads(args.report.read_text(encoding="utf-8"))
    entries = collect(report)
    errors = []
    for path, defect in entries:
        before = len(errors)
        validate(defect, schema, path, errors, args.strict)
        if args.strict and len(errors) == before:
            for field in ("evidence", "reproduction", "suggestion"):
                if not defect.get(field):
                    errors.append("{}.{}: 严格模式下不允许为空".format(path, field))

    # 【F25 反静默假通过】严格模式下要求 report **显式存在**缺陷数组键（允许空数组
    # 但键必须在）：「忘了填缺陷数组」与「真零缺陷」产出完全相同的 exit 0——前者是
    # 最常见的静默假通过形态，配合报告出口的形状分歧曾形成完整假通过链。
    # 键集合与 collect() 的 CONTAINER_KEYS 严格一致（含 findings/diffs），否则
    # 「产物只有 findings」会因顶层无 defects 键被判 rc=6，与 collect 刚纳入的
    # findings 自相矛盾。
    if args.strict and not any(
            isinstance(report.get(k), list) for k in DK.CONTAINER_KEYS):
        errors.append("严格模式：report 缺少显式缺陷数组键（%s 任一，"
                      "允许空数组但键必须存在）——「忘填」与「真零缺陷」必须可区分"
                      % "/".join(DK.CONTAINER_KEYS))

    result = {"checked": len(entries), "errors": len(errors), "strict": args.strict,
              "dimensionsCovered": sorted({str(d.get("dimension")) for _, d in entries if d.get("dimension")})}
    if args.write:
        if errors:
            # 【F25 配套】校验失败时不写回——help 承诺「通过时写回」，旧行为失败也写。
            print("--write 已跳过：校验失败时不写回报告", file=sys.stderr)
        elif isinstance(report.get("meta"), dict):
            report["meta"]["defectValidation"] = result
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        else:
            # 【反静默修复】旧行为：报告无 meta 键时 --write 什么都不做，却 rc=0、
            # 无 stderr、meta.defectValidation 也没写进去——「写回」是调用方
            # （报告出口）判定校验已落地的唯一凭据，静默无操作等于假成功。
            # 现在显式建 meta 写进去，不让调用方误判。
            report["meta"] = {"defectValidation": result}
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if errors:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        for line in errors[:60]:
            print(" - {}".format(line), file=sys.stderr)
        if len(errors) > 60:
            print(" ... 另有 {} 条".format(len(errors) - 60), file=sys.stderr)
        return 6
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
