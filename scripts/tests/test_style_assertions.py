#!/usr/bin/env python3
"""盒模型 / 阴影 / 透明度补充断言契约测试。

背景：TOLERANCE 与 DIMENSION 早就声明了 radius_px / border_px / shadow_* / opacity，
但 compare_fields.py 此前只 emit 6 类属性（rect/position/color/fontSize/lineHeight/
letterSpacing/characters），圆角、边框粗细、阴影模糊、字重、透明度**没有任何发射路径**
——「圆角 4→2px」这类历史高发缺陷只能靠像素 diff 碰运气。

锁定的不变式：
1. 圆角 / 边框粗细 / 阴影模糊差异**必须**被检出并标 confirmed；
2. 字重 / 透明度无差异时**不得**报（withinTolerance）；
3. **设计侧缺对应字段时一律不 emit**——不得把「设计稿没定义」判成缺陷；
4. 新属性全部归 7.1 维度，与 DIMENSION 表一致。
"""
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL / "scripts"))

from compare_fields import compare_pair  # noqa: E402

BASE_NODE = {
    "id": "1:2", "name": "卡片", "type": "FRAME",
    "rect": {"x": 0, "y": 0, "w": 200, "h": 100},
    "text": {"characters": "标题", "fontWeight": 700, "fontSize": 14},
}
BASE_ITEM = {
    "x": 0, "y": 0, "w": 200, "h": 100,
    "fontSize": "14px", "fontWeight": "700",
    "color": "rgb(0,0,0)", "text": "标题",
}


def _run(node_extra, item_extra):
    node = dict(BASE_NODE)
    node.update(node_extra)
    if "text" in node_extra:
        node["text"] = dict(BASE_NODE["text"], **node_extra["text"])
    item = dict(BASE_ITEM)
    item.update(item_extra)
    return compare_pair(node, item, "https://p.test/", "s1", "1440")


class StyleAssertionTests(unittest.TestCase):
    def test_radius_diff_detected(self):
        diffs = _run({"radius": {"uniform": 8}}, {"borderRadius": "2px"})
        hit = [d for d in diffs if d["property"] == "borderRadius"]
        self.assertEqual(len(hit), 1, "圆角差异必须检出")
        self.assertEqual(hit[0]["status"], "confirmed")
        self.assertEqual(hit[0]["delta"], 6.0)
        self.assertEqual(hit[0]["dimension"], "7.1")

    def test_border_width_diff_detected(self):
        diffs = _run({"strokes": [{"strokeWeight": 2}]}, {"border": "1px solid rgb(0,0,0)"})
        hit = [d for d in diffs if d["property"] == "borderWidth"]
        self.assertEqual(len(hit), 1, "边框粗细差异必须检出")
        self.assertEqual(hit[0]["status"], "confirmed")

    def test_shadow_blur_diff_detected(self):
        diffs = _run({"effects": [{"type": "DROP_SHADOW", "radius": 6}]},
                     {"boxShadow": "rgba(0,0,0,0.2) 0px 2px 2px"})
        hit = [d for d in diffs if d["property"] == "boxShadowBlur"]
        self.assertEqual(len(hit), 1, "阴影模糊差异必须检出")
        self.assertEqual(hit[0]["status"], "confirmed")

    def test_font_weight_and_opacity_within_tolerance_not_reported(self):
        diffs = _run({"opacity": 1.0}, {"opacity": "1"})
        for prop in ("fontWeight", "opacity"):
            hit = [d for d in diffs if d["property"] == prop]
            self.assertTrue(hit, "%s 应出现 withinTolerance 记录" % prop)
            self.assertEqual(hit[0]["status"], "withinTolerance")

    def test_missing_design_side_never_emits(self):
        """设计侧没画那层样式 → 不 emit，不得判缺陷。"""
        diffs = _run({}, {"borderRadius": "2px", "border": "1px solid rgb(0,0,0)",
                          "boxShadow": "rgba(0,0,0,0.2) 0px 2px 2px", "opacity": "0.5"})
        for prop in ("borderRadius", "borderWidth", "boxShadowBlur", "opacity"):
            self.assertEqual([d for d in diffs if d["property"] == prop], [],
                             "设计侧缺 %s 时不得 emit" % prop)

    def test_radius_per_corner_takes_max(self):
        """设计侧四角不同取 max；页面侧分角同样取 max。"""
        diffs = _run({"radius": {"corners": [4, 12, 4, 4]}},
                     {"borderTopLeftRadius": "4px", "borderTopRightRadius": "12px",
                      "borderBottomLeftRadius": "4px", "borderBottomRightRadius": "4px"})
        hit = [d for d in diffs if d["property"] == "borderRadius"]
        self.assertEqual(hit[0]["status"], "withinTolerance", "四角一致时不应报")


if __name__ == "__main__":
    unittest.main()
