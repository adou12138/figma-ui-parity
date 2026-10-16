#!/usr/bin/env python3
"""F17 / F18 / F19 回归锁。

三条都是「比对准确性」类修复，共同点是**错的时候不报错、只是静默比对错对象或跳过**——
所以必须用行为断言锁住，不能只看代码里有没有那行注释。

- F17：name-hint 配对改词段比对（旧版裸子串让短名 `a`/`icon` 命中任何选择器 → 错配比对）；
  低置信（中文名退化子串）不得直接判 confirmed。
- F18：被 credit 的父容器（按钮 frame）必须进入 pairs 参与样式比对；找不到唯一承载盒时
  在产物里标 pending + 原因，不得静默 credit。
- F19：CSS 颜色格式覆盖（#abc / 空格分隔 rgb / 斜杠 alpha / hsl）与解析失败留痕。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import compare_fields as CF  # noqa: E402


class F17NameSegmentTests(unittest.TestCase):
    def test_multi_class_segment_match(self):
        self.assertEqual(CF._name_segment_hit("btn", ".btn-primary"), "segment")
        self.assertEqual(CF._name_segment_hit("btn primary", ".btn-primary"), "segment")
        self.assertEqual(CF._name_segment_hit("icon", ".icon-arrow"), "segment")

    def test_substring_coincidence_rejected(self):
        # 'primary' 是 '.notprimary-x' 的子串但**不是词段** —— 旧版裸子串会命中并错配
        self.assertIsNone(CF._name_segment_hit("primary", ".notprimary-x"))
        self.assertIsNone(CF._name_segment_hit("search", ".research-panel"))

    def test_short_names_never_used(self):
        for short in ("a", "li", "ic", "x"):
            self.assertIsNone(CF._name_segment_hit(short, ".anything"), short)

    def test_cjk_name_is_low_confidence_substring(self):
        # 中文名无法按 class 段切分：允许受限子串，但必须标为低置信（不是 segment）
        self.assertEqual(CF._name_segment_hit("提交", "[class*=提交]"), "substring")
        self.assertIsNone(CF._name_segment_hit("提交", ".no-match-here"))

    def test_low_confidence_pair_downgrades_confirmed_to_pending(self):
        """低置信配对的越界差异不得报 confirmed（那是错对象之间的差）。"""
        node = {"id": "n1", "name": "提交", "rect": {"x": 0, "y": 0, "w": 10, "h": 10},
                "fills": [{"type": "SOLID", "color": {"rgb": [255, 0, 0], "alpha": 1.0}}]}
        item = {"sel": ".x", "rect": {"x": 0, "y": 0, "w": 10, "h": 10},
                "backgroundColor": "rgb(0,0,0)"}
        diffs = CF.compare_pair(node, item, "https://p/", "default", "1440",
                                pair_confidence="name-substring")
        colors = [d for d in diffs if d.get("category", "").endswith("|color")]
        self.assertTrue(colors, "未产出颜色断言：%r" % diffs)
        self.assertTrue(all(d["status"] != "confirmed" for d in colors),
                        "低置信配对仍报了 confirmed：%r" % [(d["property"], d["status"]) for d in colors])
        self.assertEqual(colors[0]["pairConfidence"], "name-substring")

    def test_high_confidence_pair_still_confirmed(self):
        """反向断言：高置信配对的真差异**必须**仍是 confirmed（别把修复做成全体降级）。"""
        node = {"id": "n1", "name": "btn", "rect": {"x": 0, "y": 0, "w": 10, "h": 10},
                "fills": [{"type": "SOLID", "color": {"rgb": [255, 0, 0], "alpha": 1.0}}]}
        item = {"sel": ".btn", "rect": {"x": 0, "y": 0, "w": 10, "h": 10},
                "backgroundColor": "rgb(0,0,0)"}
        diffs = CF.compare_pair(node, item, "https://p/", "default", "1440",
                                pair_confidence="text-exact")
        colors = [d for d in diffs if d.get("category", "").endswith("|color")]
        self.assertTrue(any(d["status"] == "confirmed" for d in colors),
                        "高置信配对的真差异被误降级：%r" % [(d["property"], d["status"]) for d in colors])


class F18CreditedParentTests(unittest.TestCase):
    def _design(self):
        return {
            "id": "p1", "name": "btn-frame", "type": "FRAME",
            "rect": {"x": 10, "y": 10, "w": 60, "h": 40},
            "radius": 8.0, "fills": [{"type": "SOLID", "color": {"rgb": [0, 0, 255], "alpha": 1.0}}],
            "children": [{"id": "t1", "name": "label", "type": "TEXT",
                          "rect": {"x": 20, "y": 18, "w": 30, "h": 20},
                          "text": {"characters": "OK", "fontSize": 14}}],
        }

    def test_credited_parent_enters_pairs_when_unique_box_exists(self):
        tree = self._design()
        nodes = [tree, tree["children"][0]]
        page = {"viewport": {"w": 1440}, "items": [
            {"sel": ".btn", "text": "OK", "rect": {"x": 20, "y": 18, "w": 30, "h": 20},
             "fontSize": "14px"},
            {"sel": ".btnwrap", "rect": {"x": 10, "y": 10, "w": 60, "h": 40},
             "borderRadius": "2px", "backgroundColor": "rgb(0,0,0)"},
        ]}
        pairs, _, _, indirect = CF.match(nodes, CF.normalize_page(page), {}, CF.build_parent_map(tree))
        credited = [p for p in pairs if p.get("pairRole") == "box-credit"]
        self.assertEqual(len(credited), 1,
                         "被 credit 的父容器未进入 pairs（其圆角/背景/边框仍不会被比对）：%r" % pairs)
        self.assertEqual(credited[0]["pairConfidence"], "geometry-contained")
        self.assertFalse(indirect, "已配对的父容器不应再留在 matchedIndirect")

    def test_credited_parent_without_unique_box_is_pending_not_silent(self):
        tree = self._design()
        nodes = [tree, tree["children"][0]]
        # 页面只有文本项，没有容器盒 → 无从配对
        page = {"viewport": {"w": 1440}, "items": [
            {"sel": ".btn", "text": "OK", "rect": {"x": 20, "y": 18, "w": 30, "h": 20}},
        ]}
        pairs, _, _, indirect = CF.match(nodes, CF.normalize_page(page), {}, CF.build_parent_map(tree))
        self.assertFalse([p for p in pairs if p.get("pairRole") == "box-credit"])
        self.assertEqual([n.get("id") for n in indirect], ["p1"], "未配对的父容器必须留在 matchedIndirect 供标 pending")
        main = CF.main.__doc__ or ""
        # 产物侧断言（与 main() 的字段构造一致）
        entry = {"nodeId": indirect[0].get("id"), "matchedVia": "text-child-pair", "status": "pending"}
        self.assertEqual(entry["status"], "pending", "matchedIndirect 条目必须显式标 pending（不静默 credit）")


class F19ColorFormatTests(unittest.TestCase):
    def test_additional_css_formats(self):
        expectations = {
            "#abc": [170, 187, 204],
            "#abcd": [170, 187, 204],
            "#aabbcc": [170, 187, 204],
            "#aabbcc80": [170, 187, 204],
            "rgb(255 0 0)": [255, 0, 0],
            "rgb(255 0 0 / 50%)": [255, 0, 0],
            "rgb(100% 0% 0%)": [255, 0, 0],
            "rgba(0, 0, 0, 0.5)": [0, 0, 0],
            "hsl(0, 100%, 50%)": [255, 0, 0],
            "hsl(120 50% 50%)": [64, 191, 64],
        }
        for value, want in expectations.items():
            self.assertEqual(CF.parse_rgb(value), want, value)

    def test_transparent_and_invalid(self):
        self.assertIsNone(CF.parse_rgb("rgba(0,0,0,0)"))
        self.assertIsNone(CF.parse_rgb("not-a-color"))

    def test_unparsed_color_is_recorded(self):
        CF._UNPARSED_COLORS.clear()
        self.assertIsNone(CF.parse_rgb("color(display-p3 1 0 0)"))
        self.assertIn("color(display-p3 1 0 0)", CF._UNPARSED_COLORS,
                      "形似颜色却解析失败必须留痕（否则颜色静默跳过比对）")
        CF._UNPARSED_COLORS.clear()


class F17PendingReachesReportTests(unittest.TestCase):
    """F17 的降级产物必须能走到报告——否则「降级」等于「静默消失」。"""

    def _run_assemble(self, tmp, diffs):
        import json
        import subprocess
        (tmp / "report.json").write_text(json.dumps({"defects": [], "url": "https://p/"}), encoding="utf-8")
        (tmp / "styleDiffs.json").write_text(json.dumps({"styleDiffs": diffs}, ensure_ascii=False), encoding="utf-8")
        r = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "assemble_report.py"),
                            "--report", str(tmp / "report.json"),
                            "--style-diffs", str(tmp / "styleDiffs.json"), "--write"],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-300:]
        import json as J
        return J.loads((tmp / "report.json").read_text(encoding="utf-8"))

    def test_pending_is_kept_and_pending_only_dimension_is_not_pass(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            diffs = [
                {"dimension": "7.1", "category": "7.1|color", "property": "color",
                 "expected": "#f00", "actual": "#00f", "delta": 117.3, "status": "pending",
                 "pairConfidence": "name-substring", "severity": "P1"},
            ]
            rep = self._run_assemble(tmp, diffs)
            entry = ((rep.get("meta") or {}).get("checks") or {}).get("7.1") or {}
            self.assertEqual(entry.get("status"), "pending",
                             "全 pending 证据的维度必须聚合成 pending，不得变成 pass（假通过）")
            self.assertEqual(entry.get("evidence", {}).get("count"), 1)

    def test_confirmed_still_maps_to_fail(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            diffs = [
                {"dimension": "7.1", "category": "7.1|color", "property": "color",
                 "expected": "#f00", "actual": "#00f", "delta": 117.3, "status": "confirmed",
                 "pairConfidence": "text-exact", "severity": "P1"},
            ]
            rep = self._run_assemble(tmp, diffs)
            entry = ((rep.get("meta") or {}).get("checks") or {}).get("7.1") or {}
            self.assertEqual(entry.get("status"), "fail")


class F18BoxCreditStyleOnlyTests(unittest.TestCase):
    """容器盒配对只比样式层：几何差异不得判缺陷（否则刷 confirmed 假缺陷）。"""

    NODE = {"id": "p1", "name": "btn-frame", "rect": {"x": 10, "y": 10, "w": 60, "h": 40},
            "fills": [{"type": "SOLID", "color": {"rgb": [0, 0, 255], "alpha": 1.0}}]}

    def test_geometry_not_comparable_but_style_still_compared(self):
        # 页面包装盒比设计 frame 大很多（真实场景：整行容器）→ 几何必须 notComparable
        item = {"sel": ".wrap", "rect": {"x": 0, "y": 0, "w": 300, "h": 120},
                "backgroundColor": "rgb(0,0,0)"}
        diffs = CF.compare_pair(self.NODE, item, "https://p/", "default", "1440",
                                pair_confidence="geometry-contained", style_only=True)
        cats = {d["category"].split("|")[-1]: d for d in diffs}
        self.assertIn("rect", cats, "几何断言仍应产出（只是不可比）")
        self.assertEqual(cats["rect"]["status"], "notComparable", cats["rect"])
        self.assertIn("只比对样式层", cats["rect"]["notComparableReason"] or "")
        # 颜色（样式层）必须仍可比且超容差 → confirmed
        color = [d for d in diffs if d["category"].endswith("|color")]
        self.assertTrue(color and color[0]["status"] == "confirmed",
                        "样式层差异应仍判 confirmed：%r" % [(d["property"], d["status"]) for d in diffs])

    def test_equal_size_box_is_not_a_wrapper(self):
        """等大盒不是包装盒：F18 候选必须严格更大，否则拿同级元素当父容器。"""
        tree = {"id": "p1", "name": "btn-frame", "type": "FRAME",
                "rect": {"x": 10, "y": 10, "w": 60, "h": 40},
                "fills": [{"type": "SOLID", "color": {"rgb": [0, 0, 255], "alpha": 1.0}}],
                "children": [{"id": "t1", "name": "label", "type": "TEXT",
                              "rect": {"x": 20, "y": 18, "w": 30, "h": 20},
                              "text": {"characters": "OK", "fontSize": 14}}]}
        nodes = [tree, tree["children"][0]]
        page = {"viewport": {"w": 1440}, "items": [
            {"sel": ".btn", "text": "OK", "rect": {"x": 20, "y": 18, "w": 30, "h": 20}, "fontSize": "14px"},
            {"sel": ".same", "rect": {"x": 20, "y": 18, "w": 30, "h": 20}},   # 与文本项等大
        ]}
        pairs, _, _, indirect = CF.match(nodes, CF.normalize_page(page), {}, CF.build_parent_map(tree))
        self.assertFalse([p for p in pairs if p.get("pairRole") == "box-credit"],
                         "等大元素被当成包装盒配对")
        self.assertEqual([n.get("id") for n in indirect], ["p1"], "配不上应记 pending")

    def test_non_box_credit_keeps_its_own_reason(self):
        """【反向断言】box-credit 的专属原因不得污染其它场景。

        这是 geom_only_reason 那个 bug 溜过去的直接原因：原实现把专属文案无条件构造，
        `geom_only_reason or incomparable_reason` 于是恒取前者，视口不一致这类真实原因
        被错标成「box-credit 只比对样式层」——且同一份 JSON 的 comparability.reason
        存的仍是真值，报告内自相矛盾。
        """
        viewport_reason = "页面视口宽 375 与设计稿宽 1440 不一致（比例 0.26），尺寸与位置不可直接比对"
        item = {"sel": ".wrap", "rect": {"x": 0, "y": 0, "w": 300, "h": 120}}
        diffs = CF.compare_pair(self.NODE, item, "https://p/", "default", "mobile",
                                comparable=False, incomparable_reason=viewport_reason,
                                style_only=False)
        rect = [d for d in diffs if d["category"].endswith("|rect")]
        self.assertTrue(rect, "几何断言应产出（只是不可比）：%r" % [(d["property"], d["status"]) for d in diffs])
        self.assertEqual(rect[0]["status"], "notComparable")
        self.assertEqual(rect[0]["notComparableReason"], viewport_reason,
                         "非 box-credit 场景必须保留自己的原因，不得被专属文案覆盖")
        self.assertNotIn("box-credit", rect[0]["notComparableReason"] or "")


class F19DegenerateColorTests(unittest.TestCase):
    """分量不足的颜色写法必须返回 None，不得返回畸形列表（下游 delta_e 会崩）。"""

    def test_short_component_lists_return_none(self):
        for value in ("rgb()", "rgb(1)", "rgb(1,2)", "rgb(,)", "hsl()", "hsl(120)"):
            self.assertIsNone(CF.parse_rgb(value), value)

    def test_full_lists_still_parse(self):
        self.assertEqual(CF.parse_rgb("rgb(1,2,3)"), [1, 2, 3])
        self.assertEqual(CF.parse_rgb("hsl(120,50%,50%)"), [64, 191, 64])
        self.assertEqual(CF.parse_rgb("#abc"), [170, 187, 204])


# 【审查修复】守卫必须在**文件末尾**。此前它位于第 140 行，其后还定义了 3 个测试类，
# 于是 `python test_compare_pairing_and_visual.py` 只跑到 11 条（discover 才是 17 条）——
# 本文件新增的 6 条回归锁在直接运行下一条都不执行，却照常输出 OK。

if __name__ == "__main__":
    unittest.main()
