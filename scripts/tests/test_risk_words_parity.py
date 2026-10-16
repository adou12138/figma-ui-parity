#!/usr/bin/env python3
"""风险词表对拍契约测试。

背景：discover_scenarios.py（场景生成）与 run_journeys.cjs（跨页旅程）曾各自维护一份
DANGER_WORDS 且内容不一致（js 版为超集，多「销毁 / signout / sign-out / unbind / destroy」）。
词表漂移会让同一个按钮在一侧判 safe、另一侧判 danger，直接违反分级执行边界。

锁定的不变式：**两边 DANGER_WORDS 集合必须完全一致**。改词表只能改
scripts/node/risk_words.cjs 这一处，再同步 python 侧常量；本测试负责抓住"只改了一边"。
"""
import re
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import discover_scenarios  # noqa: E402

RISK_WORDS_JS = SCRIPTS / "node" / "risk_words.cjs"


def _js_array(name: str) -> set:
    src = RISK_WORDS_JS.read_text(encoding="utf-8")
    m = re.search(r"const\s+%s\s*=\s*\[(.*?)\]" % name, src, re.S)
    assert m, "risk_words.cjs 里找不到 %s 定义" % name
    return set(re.findall(r"'([^']*)'", m.group(1)))


class RiskWordsParityTests(unittest.TestCase):
    def test_danger_words_match_js_side(self):
        js = _js_array("DANGER_WORDS")
        py = set(discover_scenarios.DANGER_WORDS)
        self.assertEqual(
            js, py,
            "风险词表不一致：js 侧独有 %s；python 侧独有 %s（改词表请改 scripts/node/risk_words.cjs 后同步）"
            % (sorted(js - py), sorted(py - js)))

    def test_caution_words_match_js_side(self):
        js = _js_array("CAUTION_WORDS")
        py = set(discover_scenarios.CAUTION_WORDS)
        self.assertEqual(
            js, py,
            "CAUTION 词表不一致：js 侧独有 %s；python 侧独有 %s"
            % (sorted(js - py), sorted(py - js)))

    def test_danger_words_nonempty(self):
        for name in ("DANGER_WORDS", "CAUTION_WORDS"):
            self.assertTrue(getattr(discover_scenarios, name), "%s 不能为空" % name)


if __name__ == "__main__":
    unittest.main()
