#!/usr/bin/env python3
"""场景执行率闭环契约测试（v4.23.0）。

锁定不变式：
1. **度量真实**：计划 5 条、只回填 2 条 → 执行率必须反映 2/5，而不是"维度跑过就算全覆盖"；
2. **原因必填**：notRun 无 reason → --enforce 必须非零退出（沿用 coverage_gate 的纪律）；
3. **豁免显式且单列**：豁免维度从分母剔除、不进分子，但在 planned.exemptDimensions 里可见；
4. **从报告回收**：findings 带 `scenario` 字段时能自动回收成已执行痕迹；
5. **计划外 ID 不阻塞**：只告警不失败（旧计划残留不该卡门禁）；
6. **不虚报**：结果文件里显式状态优先于从报告隐式回收的状态。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import scenario_coverage as SC  # noqa: E402

PLAN = {"version": "2.0", "scenarios": [
    {"id": "S-0001", "dimension": "7.1", "safety": "safe"},
    {"id": "S-0002", "dimension": "7.22", "safety": "caution"},
    {"id": "S-0003", "dimension": "7.17", "safety": "caution"},
    {"id": "S-0004", "dimension": "7.32", "safety": "safe"},
    {"id": "S-0005", "dimension": "7.39", "safety": "safe"},
], "truncation": {"dropped": 3}}


class ScenarioCoverageTests(unittest.TestCase):
    def test_rate_reflects_actual_execution(self):
        cov = SC.compute(PLAN, [{"scenarioId": "S-0001", "status": "pass"},
                                {"scenarioId": "S-0002", "status": "fail"}], [])
        self.assertEqual(cov["executed"]["total"], 2)
        self.assertEqual(cov["notExecuted"]["total"], 3)
        self.assertEqual(cov["executed"]["rate"], 0.4)
        self.assertEqual(len(cov["notExecuted"]["unexplained"]), 3,
                         "计划内但无执行记录的场景必须进 unexplained")

    def test_notrun_without_reason_is_unexplained(self):
        cov = SC.compute(PLAN, [{"scenarioId": "S-0001", "status": "pass"},
                                {"scenarioId": "S-0002", "status": "notRun"}], [])
        self.assertTrue(any("未写明原因" in x for x in cov["notExecuted"]["unexplained"]))
        cov2 = SC.compute(PLAN, [{"scenarioId": "S-0002", "status": "notRun", "reason": "策略限制"}], [])
        self.assertFalse(any("未写明原因" in x for x in cov2["notExecuted"]["unexplained"]))

    def test_exempt_dimension_removed_from_denominator(self):
        # 豁免 7.17（该维度本轮结构性不适用）→ 分母 5-1=4
        cov = SC.compute(PLAN, [{"scenarioId": "S-0001", "status": "pass"},
                                {"scenarioId": "S-0002", "status": "pass"}], ["7.17"])
        self.assertEqual(cov["planned"]["counted"], 4)
        self.assertEqual(cov["planned"]["exemptDimensions"], ["7.17"])
        self.assertEqual(cov["executed"]["rate"], 0.5)
        self.assertNotIn("7.17", cov["notExecuted"]["byDimension"],
                         "豁免维度不应计入未执行分布")

    def test_results_recovered_from_report(self):
        report = {"defects": [
            {"scenario": "S-0001", "symptom": "颜色不符", "severity": "P1"},
            {"nested": [{"scenarioId": "S-0004"}]},
        ]}
        found = SC.results_from_report(report)
        self.assertEqual(sorted(r["scenarioId"] for r in found), ["S-0001", "S-0004"])
        self.assertTrue(all(r["implicit"] for r in found))

    def test_explicit_result_beats_implicit(self):
        results = [{"scenarioId": "S-0001", "status": "notRun", "reason": "未跑", "implicit": False},
                   {"scenarioId": "S-0001", "status": "fail", "reason": "缺陷", "implicit": True}]
        cov = SC.compute(PLAN, results, [])
        self.assertEqual(cov["executed"]["total"], 0,
                         "显式 notRun 应覆盖从报告隐式回收到的 fail")
        self.assertEqual(cov["notExecuted"]["total"], 5,
                         "S-0001 显式 notRun + 其余 4 条无记录 = 5 条未执行")
        # S-0001 写明了原因 → 不进 unexplained；其余 4 条无任何记录 → 进 unexplained
        self.assertEqual(len(cov["notExecuted"]["unexplained"]), 4)
        self.assertTrue(all("S-0001" not in x for x in cov["notExecuted"]["unexplained"]))

    def test_unknown_result_ids_do_not_block(self):
        cov = SC.compute(PLAN, [{"scenarioId": "S-9999", "status": "pass"}], [])
        self.assertEqual(cov["unknownResults"], ["S-9999"])
        self.assertEqual(cov["executed"]["total"], 0)

    def test_rerun_takes_executed_over_notrun(self):
        """回归（审查抓到）：同 id 多条**显式**结果（重跑/并进）时原实现取首条
        → 「首轮 notRun、次轮 pass」的场景被记成未执行，且因首条写了 reason 而
        **不落 unexplained**（完全静默的漏报，执行率被低估）。"""
        results = [
            {"scenarioId": "S-0001", "status": "notRun", "reason": "首轮未执行"},
            {"scenarioId": "S-0001", "status": "pass"},
            {"scenarioId": "S-0002", "status": "pass"},
            {"scenarioId": "S-0003", "status": "pass"},
            {"scenarioId": "S-0004", "status": "pass"},
            {"scenarioId": "S-0005", "status": "pass"},
        ]
        cov = SC.compute(PLAN, results, [])
        self.assertEqual(cov["executed"]["total"], 5, "重跑通过的场景必须算已执行")
        self.assertEqual(cov["executed"]["rate"], 1.0)
        self.assertEqual(cov["notExecuted"]["total"], 0)
        self.assertEqual(cov["notExecuted"]["unexplained"], [])
        self.assertIn("S-0001", cov["multipleRecords"]["scenarioIds"],
                      "多记录情况必须落进产物，不静默")

    def test_multiple_records_flaky_is_named(self):
        """同场景终态不一致 = 不稳定，应被点名（多记录的另一层信息）。"""
        results = [{"scenarioId": s["id"], "status": "pass"} for s in PLAN["scenarios"]]
        results.append({"scenarioId": "S-0001", "status": "fail"})
        cov = SC.compute(PLAN, results, [])
        self.assertIn("S-0001", cov["multipleRecords"]["flakyScenarioIds"])
        self.assertNotIn("S-0002", cov["multipleRecords"]["flakyScenarioIds"])

    def test_enforce_exit_codes(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            plan_f = tmp / "scenarios.json"
            plan_f.write_text(json.dumps(PLAN, ensure_ascii=False), encoding="utf-8")
            res_f = tmp / "results.json"
            out_f = tmp / "cov.json"

            # ① 未写原因的 notRun → 失败
            res_f.write_text(json.dumps({"results": [{"scenarioId": "S-0002", "status": "notRun"}]},
                                        ensure_ascii=False), encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPTS / "scenario_coverage.py"),
                                "--plan", str(plan_f), "--results", str(res_f), "--enforce"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 1, "未写原因的 notRun 应被 enforce 拦截")
            self.assertIn("未写明原因", r.stderr)

            # ② 全部 pass → 通过
            res_f.write_text(json.dumps({"results": [{"scenarioId": s["id"], "status": "pass"} for s in PLAN["scenarios"]]},
                                        ensure_ascii=False), encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPTS / "scenario_coverage.py"),
                                "--plan", str(plan_f), "--results", str(res_f), "--out", str(out_f),
                                "--enforce", "--min-rate", "1.0"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[-300:])
            cov = json.loads(out_f.read_text(encoding="utf-8"))
            self.assertEqual(cov["executed"]["rate"], 1.0)
            self.assertEqual(cov["planned"]["truncated"], 3)

            # ③ 执行率低于下限 → 失败
            res_f.write_text(json.dumps({"results": [{"scenarioId": "S-0001", "status": "pass"}]},
                                        ensure_ascii=False), encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPTS / "scenario_coverage.py"),
                                "--plan", str(plan_f), "--results", str(res_f),
                                "--enforce", "--min-rate", "0.8"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("低于下限", r.stderr)


if __name__ == "__main__":
    unittest.main()