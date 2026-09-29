#!/usr/bin/env python3
"""Assert Figma layout constraints across viewports.

Constraints are the design's promise about how an element behaves when the frame
resizes. Prose rules cannot enforce them, so this script does the arithmetic:
for every node and every measured viewport it checks the constraint's invariant.

Inputs
  --design        extract_design_fields.py output (rect + constraints per node)
  --measurements  {"base": 1440, "viewports": {"768": {"frameWidth":768, "items": {"<nodeId>": {"x":..,"y":..,"w":..,"h":..}}}}}

Invariants (tolerance: 2px positional, 2% proportional)
  LEFT   x 不变           RIGHT  frameWidth-(x+w) 不变
  CENTER x+w/2 不变        SCALE  w/frameWidth 不变     FIXED w 不变
  TOP    y 不变           BOTTOM frameHeight-(y+h) 不变
  CENTER y+h/2 不变        SCALE  h/frameHeight 不变    FIXED h 不变

A viewport whose frameWidth/frameHeight is missing or zero is skipped with a
recorded reason (no division by zero); a node without a base measurement is
skipped too — falling back to the design rect would mix the frame-relative
basis with the page-relative one and produce fake violations.

Offline only. Exit 1 with --enforce when violations exist.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

POSITION_TOLERANCE = 2.0
PROPORTION_TOLERANCE = 0.02


def check_axis(rule, rect, frame_w, frame_h, base_rect, base_frame, axis) -> tuple:
    """Return (ok, expected, actual) for one axis."""
    if axis == "h":
        a, b, length = rect.get("x"), frame_w, rect.get("w")
        base_a, base_len = base_rect.get("x"), base_rect.get("w")
        base_frame_size = base_frame.get("w")
    else:
        a, b, length = rect.get("y"), frame_h, rect.get("h")
        base_a, base_len = base_rect.get("y"), base_rect.get("h")
        base_frame_size = base_frame.get("h")
    if None in (a, b, length, base_a, base_len, base_frame_size) or not b:
        return True, None, None
    if rule in ("LEFT", "TOP"):
        return abs(a - base_a) <= POSITION_TOLERANCE, base_a, a
    if rule in ("RIGHT", "BOTTOM"):
        now, before = b - (a + length), base_frame_size - (base_a + base_len)
        return abs(now - before) <= POSITION_TOLERANCE, round(before, 2), round(now, 2)
    if rule == "CENTER":
        now, before = a + length / 2.0, base_a + base_len / 2.0
        return abs(now - before) <= POSITION_TOLERANCE, round(before, 2), round(now, 2)
    if rule == "SCALE":
        now, before = length / b, base_len / base_frame_size
        return abs(now - before) <= PROPORTION_TOLERANCE, round(before, 4), round(now, 4)
    if rule == "FIXED":
        return abs(length - base_len) <= POSITION_TOLERANCE, base_len, length
    return True, None, None


def main() -> int:
    ap = argparse.ArgumentParser(description="constraints 跨视口断言")
    ap.add_argument("--design", required=True, type=Path)
    ap.add_argument("--measurements", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--enforce", action="store_true")
    args = ap.parse_args()

    design = json.loads(args.design.read_text(encoding="utf-8"))
    data = json.loads(args.measurements.read_text(encoding="utf-8"))
    nodes = {str(n.get("id")): n for n in (design.get("flat") or []) if n.get("constraints")}
    base_key = str(data.get("base") or (design.get("frame") or {}).get("w") or "")
    viewports = data.get("viewports") or {}
    if base_key not in viewports and viewports:
        base_key = sorted(viewports)[0]
    base = viewports.get(base_key) or {}
    base_items = base.get("items") or {}
    base_frame = {"w": base.get("frameWidth") or (design.get("frame") or {}).get("w") or 0,
                  "h": base.get("frameHeight") or (design.get("frame") or {}).get("h") or 0}

    violations, checked = [], 0
    skipped_viewports, skipped_nodes = [], []
    for viewport, payload in viewports.items():
        if str(viewport) == str(base_key):
            continue
        frame_w = payload.get("frameWidth") or 0
        frame_h = payload.get("frameHeight") or 0
        if not frame_w or not frame_h:
            skipped_viewports.append({"viewport": str(viewport),
                                      "reason": "frameWidth/frameHeight 缺失或为 0，无法计算约束不变量，该视口跳过"})
            continue
        items = payload.get("items") or {}
        for node_id, rect in items.items():
            node = nodes.get(str(node_id))
            # 只用本次实测的 base 测量做基准；回退设计 rect 会混用
            # frame 相对系与文档相对系，产生假违规，宁可跳过并记录。
            base_rect = base_items.get(str(node_id))
            if not node:
                continue
            if not base_rect:
                skipped_nodes.append({"viewport": str(viewport), "nodeId": str(node_id),
                                      "reason": "缺少该节点的基准视口测量，跳过约束断言"})
                continue
            constraints = node.get("constraints") or {}
            for axis, key in (("h", "horizontal"), ("v", "vertical")):
                rule = constraints.get(key)
                if not rule:
                    continue
                checked += 1
                ok, expected, actual = check_axis(rule, rect, frame_w, frame_h, base_rect, base_frame, axis)
                if not ok:
                    raw_delta = abs((actual or 0) - (expected or 0))
                    violations.append({
                        "viewport": viewport, "nodeId": node_id, "name": node.get("name"),
                        "dimension": "7.4", "property": "{}.{}".format(key, rule),
                        "expected": "按 {} 约束，{} 轴应保持 {}".format(rule, axis, expected),
                        "actual": str(actual),
                        "delta": round(raw_delta, 2),
                        "tolerance": PROPORTION_TOLERANCE if rule == "SCALE" else POSITION_TOLERANCE,
                        "status": "confirmed", "severity": "P1" if rule == "SCALE" else "P2",
                        "confidence": 0.8,
                        "symptom": "元素未按设计的 {} 约束响应视口变化（设计预期 {}，实际 {}）".format(rule, expected, actual),
                        "element": {"selector": "", "nth": 0, "bbox": rect, "anchor": node.get("name"), "frame": "design-node"},
                        "designRef": {"nodeId": node_id, "path": node.get("name")},
                        "evidence": [{"type": "constraint-assert", "result": "violated", "property": rule}],
                        "sources": ["constraint-assert"],
                        "fingerprint": "{}|responsive|{}|7.4|{}".format(viewport, node_id, rule),
                    })

    result = {"base": base_key, "viewports": [v for v in viewports if str(v) != str(base_key)],
              "checkedAssertions": checked, "violations": violations,
              "skippedViewports": skipped_viewports, "skippedNodes": skipped_nodes,
              "summary": {"checked": checked, "violated": len(violations),
                          "skippedViewports": len(skipped_viewports), "skippedNodes": len(skipped_nodes)}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    if args.enforce and violations:
        print("constraints 断言未通过：{} 条违反，详见 {}".format(len(violations), args.output), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
