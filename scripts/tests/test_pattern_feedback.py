#!/usr/bin/env python3
"""缺陷模式池反哺场景生成契约测试（v4.17.0）。

锁定三条不变式：
1. **增量**：不传 --patterns 时输出与接入前完全一致（patternFeedback.applied=false，
   无 deepened、场景集合不变）；
2. **反哺生效**：池里有某维度历史缺陷、但页面内容门槛挡住了该场景时，仍然补出该维度场景
   （source=pattern-deep），并把动因写进 patternFeedback.deepened；
3. **只加权不生成断言**：deepened 里只能出现"覆盖/深度"类调整，不得凭空造断言或场景预期；
   且 scenario 数不得因反哺而突破 --max-scenarios 上限。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import discover_scenarios as DS  # noqa: E402

POOL_HOT_32 = {"version": "1.0", "patterns": [
    {"id": "DP-X", "dimension": "7.32", "symptom": "返回后筛选态残留", "severity": "P1", "hits": 2},
    {"id": "DP-Y", "dimension": "7.31", "symptom": "固定底栏遮挡最后一行", "severity": "P2", "hits": 1},
    {"id": "DP-Z", "dimension": "7.17", "symptom": "空提交无校验提示", "severity": "P1", "hits": 1},
]}


def _page(**over):
    page = {
        "url": "https://example.test/page",
        "buttons": [{"selector": "button.save", "nth": 0, "text": "保存"}],
        "inputs": [{"selector": "input.name", "nth": 0, "placeholder": "名称"},
                   {"selector": "input.note", "nth": 0, "placeholder": "备注"}],
        "images": [], "modals": [], "emptyStateCandidates": [], "scrollables": [],
        "forms": [{"selector": "form.main"}],
        # 注意：interactionKinds 不含 tabs/table/pagination，scrollables 为空
        # → 7.32 / 7.31 的常规门槛不满足，正好验证反哺能补上
        "interactionKinds": [],
        "viewport": {},
    }
    page.update(over)
    return page


def _build(tmp: Path, page_obj, patterns=None, max_scenarios=300):
    pf = tmp / "page.json"
    pf.write_text(json.dumps(page_obj, ensure_ascii=False), encoding="utf-8")

    class Args:
        design = None
        page = pf
        pairs = None
        page_url = None
        roles = None
        max_elements = 60
        max_data_cases = 6
        max_scenarios_local = max_scenarios
        combo_depth = 1
        breakpoints = "1440,1280,768,375"
        patterns = None
    Args.max_scenarios = max_scenarios
    Args.patterns = patterns
    return DS.build(Args())


class PatternFeedbackTests(unittest.TestCase):
    def test_no_patterns_is_incremental(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            plain = _build(tmp, _page())
            feedback = plain["patternFeedback"]
            self.assertFalse(feedback["applied"])
            self.assertEqual(feedback["weights"], {})
            self.assertEqual(feedback["hotDimensions"], [])
            self.assertEqual(feedback["deepened"], {})
            self.assertIsNone(plain["generatedFrom"]["patterns"])
            dims = {s["dimension"] for s in plain["scenarios"]}
            self.assertNotIn("7.32", dims, "无池且页面无路由类元素时不应凭空出现 7.32 场景")

    def test_pool_weights_computed(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pool = tmp / "pool.json"
            pool.write_text(json.dumps(POOL_HOT_32, ensure_ascii=False), encoding="utf-8")
            w = DS.pattern_weights(pool)
            # 7.32: P1(4) × hits2 = 8；7.31: P2(2) × 1；7.17: P1(4) × 1
            self.assertEqual(w["7.32"], 8)
            self.assertEqual(w["7.31"], 2)
            self.assertEqual(w["7.17"], 4)

    def test_hot_dims_get_scenarios_despite_gates(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pool = tmp / "pool.json"
            pool.write_text(json.dumps(POOL_HOT_32, ensure_ascii=False), encoding="utf-8")
            result = _build(tmp, _page(), patterns=pool)
            fb = result["patternFeedback"]
            self.assertTrue(fb["applied"])
            self.assertIn("7.32", fb["hotDimensions"])
            deep = [s for s in result["scenarios"] if s.get("source") == "pattern-deep"]
            dims = sorted({s["dimension"] for s in deep})
            self.assertIn("7.32", dims, "历史翻车维度应绕过内容门槛补出页面级往返场景")
            self.assertIn("7.31", dims, "历史翻车维度应绕过滚动容器门槛补出页面级滚动场景")
            self.assertIn("7.32", fb["deepened"])
            self.assertIn("7.31", fb["deepened"])
            for s in deep:
                self.assertTrue(s["expected"], "补充场景仍必须带预期")
                if s["dimension"] == "7.32":
                    self.assertEqual(s["runner"], "node/run_state_scenarios.cjs",
                                     "状态类补充场景必须挂状态场景驱动")
                else:
                    self.assertIsNone(s["runner"], "非状态类维度不挂驱动，不假标可执行")

    def test_form_hot_dim_deepens_data_cases(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pool = tmp / "pool.json"
            pool.write_text(json.dumps(POOL_HOT_32, ensure_ascii=False), encoding="utf-8")
            plain = _build(tmp, _page())
            fed = _build(tmp, _page(), patterns=pool)
            n_plain = len([s for s in plain["scenarios"] if s["dimension"] == "7.17"])
            n_fed = len([s for s in fed["scenarios"] if s["dimension"] == "7.17"])
            self.assertGreater(n_fed, n_plain, "7.17 高发时应加深每个输入框的异常数据条数")
            self.assertIn("7.17", fed["patternFeedback"]["deepened"])

    def test_scenario_cap_respected(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pool = tmp / "pool.json"
            pool.write_text(json.dumps(POOL_HOT_32, ensure_ascii=False), encoding="utf-8")
            fed = _build(tmp, _page(), patterns=pool, max_scenarios=8)
            self.assertLessEqual(len(fed["scenarios"]), 8, "反哺不得突破 --max-scenarios 上限")
            self.assertTrue(fed["truncation"]["dropped"] >= 0)

    def test_no_false_deepened_claim(self):
        """回归（v4.17.0 审查）：异常数据已达上限时不得声称"已加深"——报告不诚实比不加深更糟。"""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            pool = tmp / "pool.json"
            pool.write_text(json.dumps(POOL_HOT_32, ensure_ascii=False), encoding="utf-8")
            fed = _build(tmp, _page(), patterns=pool)
            self.assertIn("7.17", fed["patternFeedback"]["deepened"],
                          "有加深空间时应记录 deepened")
            at_cap = _build_at_cap(tmp, pool, len(DS.ANOMALY_DATA))
            self.assertNotIn("7.17", at_cap["patternFeedback"]["deepened"],
                             "无可加深空间时不得记 deepened（避免虚报）")


def _build_at_cap(tmp: Path, pool: Path, n_data: int) -> dict:
    """以 max_data_cases == len(ANOMALY_DATA) 构造：数据条数已到上限，加深无处可加。"""
    pf = tmp / "page_cap.json"
    pf.write_text(json.dumps(_page(), ensure_ascii=False), encoding="utf-8")

    class Args:
        design = None
        page = pf
        pairs = None
        page_url = None
        roles = None
        max_elements = 60
        max_data_cases = n_data
        max_scenarios = 300
        combo_depth = 1
        breakpoints = "1440,1280,768,375"
        patterns = pool
    return DS.build(Args())


if __name__ == "__main__":
    unittest.main()