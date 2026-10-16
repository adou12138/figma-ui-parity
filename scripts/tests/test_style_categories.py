#!/usr/bin/env python3
"""F14 样式类口径的 parity 测试：`emit()` 产出的 category 名必须被
`STYLE_ONLY_CATEGORIES`（或几何白名单）覆盖。

**为什么需要这条**：`STYLE_ONLY_CATEGORIES` 是视口不一致时「该不该判 notComparable」
的唯一开关，而它的成员与 `emit()` 第一参是两个独立维护的字符串集合。实测过写错名字
的后果——`line_height`（tol_key 命名）与 `lineheight`（emit 命名）差一个下划线，
加了等于没加、且完全静默。这类「键名不同源」是本仓库反复出现的病（F1/F7/F8 同源）。
"""
import re
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "compare_fields.py"
TEXT = SRC.read_text(encoding="utf-8")

# 几何类：受视口比例影响，视口不一致时**应当**不可比
GEOMETRY_CATEGORIES = {"rect", "position"}


def _style_only_categories() -> set:
    m = re.search(r"STYLE_ONLY_CATEGORIES = \{([^}]*)\}", TEXT, re.S)
    assert m, "未找到 STYLE_ONLY_CATEGORIES 定义"
    return set(re.findall(r'"([^"]+)"', m.group(1)))


def _first_arg(text: str, start: int) -> str:
    """从 emit( 之后的 start 位置取第一个实参（顶层逗号处截断）。"""
    depth, quote, buf = 0, None, []
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = None
            buf.append(ch)
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "([{":
            depth += 1
            buf.append(ch)
        elif ch in ")]}":
            if depth == 0:
                break
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            break
        else:
            buf.append(ch)
        i += 1
    return "".join(buf).strip()


def _emitted_categories() -> set:
    """抽出所有 emit( 调用的第一参：字面量（含三元里的每个分支）+ 动态 prop.lower()。"""
    cats = set()
    for m in re.finditer(r"emit\(", TEXT):
        head = _first_arg(TEXT, m.end())
        if not head:
            continue
        # 第一参可能是纯字面量或三元（"rect" if cond else "position"）——只取**取值位**的
        # 字面量（首字面量与 else 之后的字面量），不取条件里的字符串。
        first = re.match(r'"([A-Za-z_]+)"', head)
        if first:
            cats.add(first.group(1))
        alt = re.search(r'else\s+"([A-Za-z_]+)"', head)
        if alt:
            cats.add(alt.group(1))
        if "prop.lower()" in head:
            # emit("font" if prop == "fontSize" else prop.lower(), ...) —— 文本三属性
            for prop in ("lineHeight", "letterSpacing"):
                cats.add(prop.lower())
    return cats


class StyleCategoryParityTests(unittest.TestCase):
    def test_every_emitted_category_is_classified(self):
        emitted = _emitted_categories()
        self.assertTrue(emitted, "未抽到任何 emit 类别——正则可能已失效")
        unclassified = emitted - _style_only_categories() - GEOMETRY_CATEGORIES
        self.assertFalse(
            unclassified,
            "以下 emit 类别既不在 STYLE_ONLY_CATEGORIES 也不在几何白名单：%s"
            "（视口不一致时会被判 notComparable，可能静默漏比对）" % sorted(unclassified))

    def test_text_prop_categories_are_style_comparable(self):
        """锁定本仓库踩过的坑：行距/字间距的 category 是无下划线的 prop.lower()，
        而 tol_key 是带下划线的 line_height_px / letter_spacing_px——写混即静默失效。"""
        style = _style_only_categories()
        # emit 侧类别名 ↔ tol_key 侧命名
        pairs = {"lineheight": "line_height_px", "letterspacing": "letter_spacing_px"}
        for emitted, tol_key in pairs.items():
            self.assertIn(emitted, style,
                          "emit 产出的类别名 %r 不在集合里（切勿写成 tol_key 形态的 %r）"
                          % (emitted, tol_key))
            self.assertNotIn(tol_key.rstrip("_px"), style,
                             "集合里混进了 tol_key 形态的 %r——它永远匹配不上 emit 的 %r，"
                             "是死条目且会误导维护者" % (tol_key.rstrip("_px"), emitted))


if __name__ == "__main__":
    unittest.main()
