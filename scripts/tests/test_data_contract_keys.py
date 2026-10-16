# -*- coding: utf-8 -*-
"""S1 数据契约测试：producer 真实产出的顶层键 ⊇ consumer 实际读取的键。

**为什么必须有这个文件**：此前 4 个 `*_contract.py` 测的都是「文档/注册表一致性」
（维度编号连续、SKILL.md 提及、文件存在），没有一条测数据契约；而全部单测的 fixture
键名都是**手抄**的。实测把 `compare_fields.py:868` 的输出键 `styleDiffs` 改成
`style_diffs`（consumer 读 `styleDiffs`，数据会彻底蒸发），**81 条单测 + 34 条串链全绿**。

本文件的两条纪律：
1. **consumer 读取的键从源码 AST 里提取**，不手抄——手抄的契约测试测的是
   「我抄的键名能用」，不是「两端真连通」。
2. **producer 的键来自真实运行** compare_fields.py 的产物，不读源码字面量。
   只有真跑才能挡住「改了写入键、忘了改读取键」这一类断裂。
"""
import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def _consumer_style_diff_keys() -> set:
    """从 assemble_report.py 的 AST 里提取 collect_style_diffs 实际读取的顶层键。

    认 `for key in ("styleDiffs", "diffs")` 这种元组字面量，以及对 payload 的
    `.get("...")` 调用。提取不到就抛错——宁可测试失败，也不要静默退化成空集断言。
    """
    tree = ast.parse((SCRIPTS / "assemble_report.py").read_text(encoding="utf-8"))
    keys = set()
    for node in ast.walk(tree):
        # (a) `for key in ("styleDiffs", "diffs")` —— For 节点的 iter 字面量
        if isinstance(node, ast.For) and isinstance(node.iter, (ast.Tuple, ast.List, ast.Set)):
            for el in node.iter.elts:
                if isinstance(el, ast.Constant) and isinstance(el.value, str):
                    keys.add(el.value)
        # (b) `payload.get("...")` —— 常量首参
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if not (isinstance(fn, ast.Attribute) and fn.attr == "get") or not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            keys.add(arg.value)
        elif isinstance(arg, (ast.Tuple, ast.List, ast.Set)):
            for el in arg.elts:
                if isinstance(el, ast.Constant) and isinstance(el.value, str):
                    keys.add(el.value)
    # 只保留「缺陷/差异容器」类的顶层键，排除 status/detail/severity 这类条目内字段
    containers = {k for k in keys
                  if k.lower() in ("stylediffs", "diffs", "defects", "defectlist", "issues")}
    if not containers:
        raise AssertionError("未能从 assemble_report.py 提取到容器键，契约测试失效")
    return containers


def _run_producer(tmp: Path) -> dict:
    """真实跑 compare_fields.py，返回它写出的产物 JSON。"""
    btn = {"id": "n1", "name": "btn", "type": "FRAME", "visible": True,
           "rect": {"x": 10, "y": 10, "w": 100, "h": 40},
           "fills": [{"type": "SOLID", "color": {"rgb": [0, 0, 255], "alpha": 1}}],
           "strokes": [{"paint": "#000", "weightPx": 4.0, "align": "CENTER",
                        "cssBorderPx": 2.0}],
           "effects": [{"kind": "DROP_SHADOW", "x": 0, "y": 2,
                        "blur": 12.0, "spread": 0, "color": "#000000"}],
           "children": [
               {"id": "t1", "name": "label", "type": "TEXT", "visible": True,
                "rect": {"x": 20, "y": 18, "w": 30, "h": 16},
                "text": {"characters": "OK", "fontSize": 14, "fontWeight": 400}}]}
    # main() 取 design["flat"] 作为待配对节点列表；缺 flat 时只剩 root 一个节点，
    # root 无 text ⇒ 配不上对 ⇒ styleDiffs 空 ⇒ 契约测试拿不到样本（fixture 陷阱）。
    design = {"tree": {"id": "root", "name": "root", "type": "FRAME",
                       "rect": {"x": 0, "y": 0, "w": 1440, "h": 900},
                       "children": [btn]},
              "flat": [btn, btn["children"][0]]}
    page = {"viewport": {"w": 1440}, "items": [
        {"sel": ".btn", "text": "OK", "rect": {"x": 10, "y": 10, "w": 100, "h": 40},
         "fontSize": "14px", "fontWeight": "400",
         "backgroundColor": "rgb(255, 0, 0)", "border": "1px solid #000000",
         "boxShadow": "0px 2px 4px 0px rgba(0, 0, 0, 0.25)"}]}
    (tmp / "design.json").write_text(json.dumps(design, ensure_ascii=False), encoding="utf-8")
    (tmp / "page.json").write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")
    out = tmp / "out.json"
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "compare_fields.py"),
         "--design", str(tmp / "design.json"), "--page", str(tmp / "page.json"),
         "--output", str(out), "--page-url", "https://p.test/"],
        capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        raise AssertionError("compare_fields 未产出（rc=%s）err=%s" % (r.returncode, r.stderr[-400:]))
    return json.loads(out.read_text(encoding="utf-8"))


class DataContractKeyTests(unittest.TestCase):
    """producer 顶层键 ⊇ consumer 读取键（改任一端都会红）。"""

    def test_producer_top_level_keys_cover_consumer_read_keys(self):
        with tempfile.TemporaryDirectory() as td:
            produced = _run_producer(Path(td))
        want = _consumer_style_diff_keys()
        hit = want & set(produced)
        # consumer 是 `for key in ("styleDiffs", "diffs")` 的 or 链（按优先级尝试），
        # 所以**不要求**每个候选键都存在——`diffs` 是历史报告形状的兼容键，producer
        # 只产 `styleDiffs` 是正常的。要求「全部命中」会把兼容机制误判成断裂。
        # 真正必须成立的是：**主键 styleDiffs 对齐**，且两侧至少有一个候选命中。
        self.assertTrue(
            hit,
            "assemble_report.py 读取的容器键 %s 与 compare_fields.py 产物顶层 %s 完全不相交"
            "（数据会彻底蒸发）" % (sorted(want), sorted(produced)))
        self.assertIn(
            "styleDiffs", produced,
            "producer 顶层缺少主键 styleDiffs（assemble_report 的 or 链首选）；实际键：%s"
            % sorted(produced))

    def test_style_diffs_entries_carry_gate_required_fields(self):
        """每条差异必须带齐门禁需要的字段，否则映射时会被 .get() 静默兜底。"""
        with tempfile.TemporaryDirectory() as td:
            produced = _run_producer(Path(td))
        entries = produced.get("styleDiffs")
        self.assertIsInstance(entries, list, "styleDiffs 必须是列表（assemble_report 按列表消费）")
        self.assertTrue(entries, "本 fixture 应至少产出一条差异（设计蓝 vs 页面红）")
        required = ("dimension", "category", "property", "expected", "actual",
                    "delta", "status", "severity", "fingerprint")
        for i, e in enumerate(entries):
            absent = [k for k in required if k not in e]
            self.assertFalse(absent, "第 %d 条差异缺字段 %s（键集合会漂移）" % (i, absent))

    def test_status_values_are_in_gate_vocabulary(self):
        """compare_fields 产的 status 必须都能被 assemble_report 映射，不许被 continue 丢弃。"""
        with tempfile.TemporaryDirectory() as td:
            produced = _run_producer(Path(td))
        src = (SCRIPTS / "assemble_report.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        mapped = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        mapped.add(k.value)
        used = {e.get("status") for e in produced.get("styleDiffs") or []}
        unknown = sorted(s for s in used if s and s not in mapped)
        self.assertFalse(
            unknown,
            "差异状态 %s 不在 assemble_report 的映射表里，会被 .get()->None->continue 静默丢弃"
            % unknown)


if __name__ == "__main__":
    unittest.main()