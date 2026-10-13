#!/usr/bin/env python3
"""多页用户旅程契约测试（v4.15.0）。

锁定不变式：
1. 维度 7.39 已登记进 check-dimensions.json（script 级自动化，owner 指向 references/journeys.md）；
2. SKILL.md 已登记 run_journeys.cjs 与 references/journeys.md（过孤儿门禁）；
3. bug-driven-checks.md 的维度说明含 7.39 节。
"""
import json
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]


class JourneyContractTests(unittest.TestCase):
    def setUp(self):
        self.dims = {d["id"]: d for d in json.loads(
            (SKILL / "schemas" / "check-dimensions.json").read_text(encoding="utf-8"))["dimensions"]}
        self.skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.bug_md = (SKILL / "references" / "bug-driven-checks.md").read_text(encoding="utf-8")

    def test_dimension_739_registered(self):
        self.assertIn("7.39", self.dims)
        d = self.dims["7.39"]
        self.assertEqual(d["automation"], "script")
        self.assertIn("run_journeys.cjs", d["script"])
        self.assertEqual(d["owner"], "references/journeys.md")

    def test_dimension_count_is_39(self):
        """维度总数 39（7.1–7.39），命名空间连续无洞。"""
        ids = sorted(self.dims.keys(), key=lambda x: float(x))
        self.assertEqual(len(ids), 39, "维度总数应为 39，实际 %d" % len(ids))
        expected = sorted(["7.%d" % i for i in range(1, 40)], key=float)
        self.assertEqual(ids, expected, "维度编号应连续 7.1–7.39")

    def test_skill_md_registers_journeys(self):
        self.assertIn("run_journeys.cjs", self.skill_md)
        self.assertIn("references/journeys.md", self.skill_md)
        self.assertIn("7.39", self.skill_md)

    def test_journeys_reference_exists(self):
        ref = SKILL / "references" / "journeys.md"
        self.assertTrue(ref.exists())
        text = ref.read_text(encoding="utf-8")
        for kw in ("run_journeys.cjs", "max-hops", "confirmed", "pending", "staticOnly"):
            self.assertIn(kw, text, "journeys.md 应包含 %s" % kw)

    def test_bug_driven_checks_mentions_739(self):
        self.assertIn("7.39", self.bug_md)
        self.assertIn("run_journeys.cjs", self.bug_md)


if __name__ == "__main__":
    unittest.main()
