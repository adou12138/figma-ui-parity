#!/usr/bin/env python3
"""缺陷模式池管理与风险排序。

为什么需要：
  - bug-driven-checks.md 把真实缺陷**手工**反推成了断言，但那份知识是静态文档，
    新发现的缺陷模式不会自动沉淀，下次仍可能漏掉同一类问题 → 需要可累积的池。
  - 报告里的缺陷是平铺的，人打开报告最该先看的是"最严重的几条"→ 需要风险排序。

池文件：assets/defect_patterns.json（可由 --merge 累积，只增不改 id）。
本脚本不与网络交互，只读写本地文件。

用法：
  python pattern_pool.py --list
  python pattern_pool.py --merge <report.json> [--pool <池路径>]     # 把新缺陷模式并入池（幂等）
  python pattern_pool.py --rank <report.json> --top 8 [--out top.md] # 风险排序 Top N
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_POOL = HERE.parent / "assets" / "defect_patterns.json"
# 【审查修复·C1】入口键单一来源：此前本地维护 ITEM_KEYS 副本且顺序与
# defect_keys.CONTAINER_KEYS 分叉（diffs 排第一、还缺 defectList）——报告同时含
# diffs 与 styleDiffs 时，归一链（CONTAINER_KEYS 序）取 styleDiffs、模式池取
# diffs，两路消费**不同的数组**：styleDiffs 的 confirmed 缺陷进不了池，
# diffs 里的 withinTolerance/pending 噪声反而每轮自动入池，风险排序被噪声灌满。
# 改为直接复用 normalize_evidence.extract_items（键序、dict 形分桶、形状判定
# 永远同源——defect_keys.py 是唯一键表，见该文件头部的历史教训）。
import normalize_evidence as NE  # noqa: E402
SEV_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


def extract_items(data):
    """与 normalize_evidence 完全同一套入口键与容器形状（单一来源）。"""
    items, _source_key = NE.extract_items(data)
    return [i for i in items if isinstance(i, dict)]


def _norm(text, n=60):
    return " ".join(str(text or "").split())[:n]


def fingerprint(item):
    """缺陷→模式指纹：维度 + 属性 + 现象前缀。同一缺陷重复并入时命中同一指纹。"""
    parts = [str(item.get("dimension") or ""), str(item.get("property") or ""),
             _norm(item.get("symptom") or item.get("name") or "")]
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def severity_of(item):
    sev = str(item.get("severity") or item.get("severityHint") or "P2").upper()
    return sev if sev in SEV_RANK else "P2"


def confidence_of(item):
    try:
        return float(item.get("confidence", 0.5))
    except (TypeError, ValueError):
        return 0.5


def load_pool(path):
    if not path.exists():
        return {"version": "1.0", "patterns": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_pool(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.stderr.write("无法读取/解析 %s：%s\n" % (path, e))
        return None


def cmd_list(pool_path):
    data = load_pool(pool_path)
    pats = data.get("patterns") or []
    by_dim = {}
    for p in pats:
        by_dim[p.get("dimension") or "-"] = by_dim.get(p.get("dimension") or "-", 0) + 1
    print("缺陷模式池：%d 条（%s）" % (len(pats), pool_path))
    for dim in sorted(by_dim):
        print("  %-5s %d 条" % (dim, by_dim[dim]))
    return 0


def cmd_merge(pool_path, src):
    data = load_json(src)
    if data is None:
        return 2
    items = extract_items(data)
    pool = load_pool(pool_path)
    pats = pool.setdefault("patterns", [])
    known = {p.get("fingerprint") or fingerprint(p): p for p in pats}
    added = 0
    # 【审查修复·P2 hits 累加】旧版命中已知指纹直接 continue——池里 31 条模式
    # 没有一条有 hits 字段（实测 Counter({None: 31})），"按命中频次看哪些模式
    # 高发"的权重机制形同虚设：同一模式每轮命中零痕迹，无法区分"高频复发"与
    # "一次性偶发"。命中即累加 hits（旧条目缺省按 1 起算）并刷新 lastSeen，
    # 只有池内容真变化才落盘（幂等不重写）。
    hit_updated = False
    for item in items:
        fp = fingerprint(item)
        if fp in known:
            p = known[fp]
            p["hits"] = int(p.get("hits", 1)) + 1
            p["lastSeen"] = Path(src).name
            hit_updated = True
            continue
        entry = {
            "id": "DP-AUTO-%04d" % (len(pats) + 1),
            "dimension": str(item.get("dimension") or ""),
            "symptom": _norm(item.get("symptom") or item.get("name") or "", 120),
            "assertion": _norm(item.get("expected") or item.get("assertion") or "", 120),
            "severity": severity_of(item),
            "source": "merged:%s" % Path(src).name,
            "fingerprint": fp,
            "hits": 1,
        }
        pats.append(entry)
        known[fp] = entry
        added += 1
    if added or hit_updated:
        save_pool(pool_path, pool)
    print("并入完成：新增 %d 条模式（输入 %d 条缺陷），池现 %d 条 -> %s"
          % (added, len(items), len(pats), pool_path))
    return 0


def cmd_rank(src, top, out):
    data = load_json(src)
    if data is None:
        return 2
    items = extract_items(data)
    ranked = sorted(items, key=lambda i: (SEV_RANK[severity_of(i)], -confidence_of(i)))
    chosen = ranked[:max(1, top)]
    lines = ["# 风险排序 Top %d（共 %d 条候选）" % (len(chosen), len(items)), ""]
    for idx, item in enumerate(chosen, 1):
        sev = severity_of(item)
        conf = confidence_of(item)
        dim = item.get("dimension") or "-"
        sym = _norm(item.get("symptom") or item.get("name") or "", 160)
        el = item.get("element") or {}
        sel = el.get("selector") if isinstance(el, dict) else ""
        lines.append("%d. [%s] %s｜%s" % (idx, sev, dim, sym))
        if sel:
            lines.append("   - 定位：%s" % sel)
        lines.append("   - 置信度：%.2f" % conf)
    text = "\n".join(lines) + "\n"
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
        print("风险排序 Top %d 已写入 %s（候选 %d 条）" % (len(chosen), out, len(items)))
    else:
        print(text)
    return 0


def main():
    ap = argparse.ArgumentParser(description="缺陷模式池管理与风险排序")
    ap.add_argument("--pool", type=Path, default=DEFAULT_POOL, help="池文件路径（默认 assets/defect_patterns.json）")
    ap.add_argument("--list", action="store_true", help="列出池内容汇总")
    ap.add_argument("--merge", type=Path, help="把缺陷产物里的新模式并入池（幂等）")
    ap.add_argument("--rank", type=Path, help="对缺陷产物做风险排序")
    ap.add_argument("--top", type=int, default=8, help="--rank 输出的条数")
    ap.add_argument("--out", type=Path, help="--rank 的 Markdown 输出路径（省略则打印）")
    args = ap.parse_args()

    if args.list:
        return cmd_list(args.pool)
    if args.merge:
        return cmd_merge(args.pool, args.merge)
    if args.rank:
        return cmd_rank(args.rank, args.top, args.out)
    ap.error("需要 --list / --merge / --rank 之一")
    return 2


if __name__ == "__main__":
    sys.exit(main())
