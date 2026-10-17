#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
两条页面提取路径的一致性校验（对应 TRACE 评测 P2-5）。

MCP 路径（browser_evaluate 注入 collect_page_inventory.js）与 node 兜底路径
（run_official_extraction.cjs 注入同一脚本）现在都产出同一份 page.json 契约。
本脚本对比两份 page.json 的可比计数，标记漂移，防止"两条路径产出字段漂移"导致
下游 compare_fields.py 行为不一致。

复用 run_official_extraction.cjs 中 qualityCheck 的思路：元素极少 / 零尺寸占比高 /
关键计数漂移 > 阈值 → 告警。

用法：
  python scripts/verify_extraction_contract.py \
    --mcp  ./parity-test/page_mcp.json \
    --node ./parity-test/extract/page.json \
    --threshold 0.3 \
    --out  ./parity-test/extract/contraction_check.json
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
TZ = timezone(timedelta(hours=8))

# 两条路径都应产出的可比计数键（collect_page_inventory.js 契约字段）
COMPARABLE = [
    "buttons", "inputs", "images", "modals", "dropdowns",
    "tabs", "tables", "emptyStateCandidates", "stickyOrFixed", "scrollables",
]


def load(path):
    if not os.path.exists(path):
        return None, "file-not-found"
    try:
        return json.load(open(path, encoding="utf-8")), None
    except Exception as e:  # noqa: BLE001
        return None, "parse-error:" + str(e)[:120]


def count_of(obj, key):
    v = obj.get(key) if isinstance(obj, dict) else None
    # 【审查修复·P2】tables 键是数字（querySelectorAll(...).length），此前只对
    # list 求 len——数字键恒落 0，两路径真实漂移也被 0==0 静默放行，契约校验
    # 对该键形同虚设。数字与列表同口径计数。
    if isinstance(v, list):
        return len(v)
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return int(v)
    return 0


def main():
    ap = argparse.ArgumentParser(description="对比 MCP 与 node 两条页面提取路径的产出一致性")
    ap.add_argument("--mcp", required=True, help="MCP 路径产出的 page.json")
    ap.add_argument("--node", required=True, help="node 兜底路径产出的 page.json")
    ap.add_argument("--threshold", type=float, default=0.3, help="计数漂移阈值（默认 0.3）")
    ap.add_argument("--out", default=None, help="校验结果输出路径")
    args = ap.parse_args()

    mcp, mcp_err = load(args.mcp)
    node, node_err = load(args.node)

    result = {
        "comparedAt": datetime.now(TZ).isoformat(),
        "files": {"mcp": args.mcp, "node": args.node},
        "errors": {"mcp": mcp_err, "node": node_err},
        "counts": {},
        "drift": {},
        "warnings": [],
        "ok": True,
    }

    if mcp is None or node is None:
        result["ok"] = False
        result["warnings"].append("缺少可对比文件：" + ", ".join(
            [k for k, e in (("mcp", mcp_err), ("node", node_err)) if e]))
        _write(args.out, result)
        print("CONTRACT: FAIL (missing files)")
        return 2

    total = 0
    for key in COMPARABLE:
        a, b = count_of(mcp, key), count_of(node, key)
        result["counts"][key] = [a, b]
        total += a + b
        m = max(a, b)
        if m == 0:
            result["drift"][key] = 0.0
            continue
        ratio = abs(a - b) / m
        result["drift"][key] = round(ratio, 3)
        if ratio > args.threshold:
            result["warnings"].append(
                "漂移超阈值 %s: mcp=%d node=%d (ratio=%.2f > %.2f)" % (key, a, b, ratio, args.threshold))
            result["ok"] = False

    # 复用 qualityCheck：总元素数异常少
    if total < 10:
        result["warnings"].append("两条路径合计元素数过少（%d < 10），可能提取未稳或页面空" % total)
        result["ok"] = False

    _write(args.out, result)
    print("CONTRACT:", "PASS" if result["ok"] else "FAIL",
          "| driftKeys:", [k for k in result["drift"] if result["drift"][k] > 0])
    if result["warnings"]:
        for w in result["warnings"]:
            print("  -", w)
    return 0 if result["ok"] else 1


def _write(out, result):
    if not out:
        return
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("contract-check ->", out)


if __name__ == "__main__":
    sys.exit(main())
