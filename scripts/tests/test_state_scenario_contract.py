#!/usr/bin/env python3
"""状态场景驱动契约测试（v4.14.0）。

锁定三条不变式：
1. discover_scenarios.py 对 7.25 / 7.26 / 7.32 / 7.33 场景必须带 runner 字段
   （指向 node/run_state_scenarios.cjs）——场景可执行性显式化，不再依赖 agent 临场发挥；
2. 页内脚本 state_probes.js 必须存在且全文无反斜杠（MCP 传参吃掉一层反斜杠会静默改语义）；
3. check-dimensions.json 中 7.26 必须已是 script 级自动化（不再是 none）。
"""
import json
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import discover_scenarios as DS  # noqa: E402

DRIVER = "node/run_state_scenarios.cjs"
DRIVER_DIMS = ("7.25", "7.26", "7.32", "7.33")


def _build(tmp_path, **kw):
    """用最小 fixture 跑一次 build（page 侧声明 forms 让 7.17 等场景也生成）。"""
    page = {
        "url": "https://example.test/page",
        "buttons": [{"selector": "button.save", "nth": 0, "text": "保存"}],
        "inputs": [{"selector": "input.name", "nth": 0, "placeholder": "名称"}],
        "images": [],
        "modals": [],
        "emptyStateCandidates": [],
        "scrollables": [],
        "forms": [{"selector": "form.main"}],
        "interactionKinds": ["table", "pagination"],
        "viewport": {},
    }
    pf = tmp_path / "page.json"
    pf.write_text(json.dumps(page, ensure_ascii=False), encoding="utf-8")

    class Args:
        design = None
        page = pf
        pairs = None
        page_url = None
        roles = None
        max_elements = 60
        max_data_cases = 6
        max_scenarios = 300
        combo_depth = 1
        breakpoints = "1440,1280,768,375"
    for k, v in kw.items():
        setattr(Args, k, v)
    return DS.build(Args())


class StateScenarioContractTests(unittest.TestCase):
    def test_state_dimensions_carry_runner(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            result = _build(Path(td))
        by_dim = {}
        for s in result["scenarios"]:
            by_dim.setdefault(s["dimension"], []).append(s)
        for dim in DRIVER_DIMS:
            self.assertIn(dim, by_dim, "维度 %s 应有场景生成" % dim)
            for s in by_dim[dim]:
                self.assertEqual(s.get("runner"), DRIVER,
                                 "维度 %s 场景 %s 必须带 runner=%s" % (dim, s["id"], DRIVER))

    def test_non_state_scenarios_have_no_runner(self):
        """未接驱动的场景 runner 必须为 null（不能假标可执行）。"""
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            result = _build(Path(td))
        for s in result["scenarios"]:
            if s["dimension"] not in DRIVER_DIMS:
                self.assertIsNone(s.get("runner"),
                                  "场景 %s（维度 %s）未接驱动，runner 必须为 null" % (s["id"], s["dimension"]))

    def test_state_probes_no_backslash(self):
        src = (SCRIPTS / "state_probes.js").read_text(encoding="utf-8")
        self.assertNotIn(chr(92), src, "state_probes.js 含反斜杠，违反页内脚本约定")

    def test_dimensions_726_is_script_automation(self):
        data = json.loads((SKILL / "schemas" / "check-dimensions.json").read_text(encoding="utf-8"))
        dim = {d["id"]: d for d in data["dimensions"]}
        self.assertEqual(dim["7.26"]["automation"], "script", "7.26 应已是 script 级自动化")
        self.assertIn("state_probes.js", dim["7.26"]["script"])
        for d in ("7.25", "7.32", "7.33"):
            self.assertIn("run_state_scenarios.cjs", dim[d]["script"],
                          "%s 的 script 应登记 run_state_scenarios.cjs" % d)

    def test_driver_and_probe_files_exist(self):
        self.assertTrue((SCRIPTS / "state_probes.js").exists())
        self.assertTrue((SCRIPTS / "node" / "run_state_scenarios.cjs").exists())


if __name__ == "__main__":
    unittest.main()
