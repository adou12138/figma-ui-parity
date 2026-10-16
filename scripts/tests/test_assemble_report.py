#!/usr/bin/env python3
"""assemble_report 契约测试。

锁定的不变式（按重要性排序）：
1. **无证据的维度只能填 notRun + reason，严禁推断 pass**——「没跑」和「跑了没发现问题」
   是两件事，混为一谈会让覆盖率从诚实记录变成装饰；
2. notRun / dataMissing 必须带 reason（coverage_gate 对无原因项直接非零退出）；
3. styleDiffs 的 status 必须映射到门禁词表（confirmed→fail、withinTolerance→pass、
   notComparable→dataMissing），原值不是门禁词表；
4. scenario_coverage 只用来回答「有场景但没跑」，**不产生 pass**；
5. report 里已有的手写 checks 不被覆盖（人填的比机器猜的优先级高）；
6. 同维多份证据取最严重状态；
7. 产出的 checks 必须能被 coverage_gate 消费且不触发「未写明原因」。
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

import assemble_report as AR  # noqa: E402

DIMS = json.loads((SKILL / "schemas" / "check-dimensions.json").read_text(encoding="utf-8"))
ALL_DIM_IDS = [str(d["id"]) for d in DIMS.get("dimensions", []) if d.get("id")]


def _assemble(tmp: Path, **kwargs):
    """跑一次 assemble_report，返回 (report, checks, stdout_dict)。"""
    report = kwargs.pop("report", {"url": "https://p.test/", "defects": []})
    rp = tmp / "report.json"
    rp.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    cmd = [sys.executable, str(SCRIPTS / "assemble_report.py"), "--report", str(rp), "--write"]
    for key, val in kwargs.items():
        if val is None:
            continue
        flag = "--" + key.replace("_", "-")
        if isinstance(val, list):
            for v in val:
                cmd += [flag, str(v)]
        else:
            cmd += [flag, str(val)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    written = json.loads(rp.read_text(encoding="utf-8"))
    return written, written.get("meta", {}).get("checks", {}), out


class AssembleReportTests(unittest.TestCase):
    def test_no_evidence_all_not_run_with_reason(self):
        """核心纪律：没有任何产物时，39 个维度全部 notRun 且每个都带 reason。"""
        with tempfile.TemporaryDirectory() as td:
            _, checks, out = _assemble(Path(td))
            self.assertEqual(len(checks), len(ALL_DIM_IDS))
            for dim_id, entry in checks.items():
                self.assertEqual(entry["status"], "notRun", dim_id)
                self.assertTrue(entry.get("reason"), "{} 必须带 reason".format(dim_id))
            self.assertEqual(out["notRunTotal"], len(ALL_DIM_IDS))

    def test_style_diffs_status_mapping(self):
        """styleDiffs 的 status 不是门禁词表，必须映射。"""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            sd = tmp / "styleDiffs.json"
            sd.write_text(json.dumps([
                {"dimension": "7.1", "property": "borderRadius", "status": "confirmed", "delta": 6},
                {"dimension": "7.15", "property": "color", "status": "withinTolerance", "delta": 0.4},
                {"dimension": "7.16", "property": "position", "status": "notComparable", "delta": 0},
            ], ensure_ascii=False), encoding="utf-8")
            _, checks, _ = _assemble(tmp, style_diffs=sd)
            self.assertEqual(checks["7.1"]["status"], "fail")
            self.assertEqual(checks["7.15"]["status"], "pass")
            self.assertEqual(checks["7.16"]["status"], "dataMissing")
            self.assertTrue(checks["7.16"].get("reason") or checks["7.16"].get("note"))

    def test_findings_and_state_scenarios_consumed(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            f1 = tmp / "findings.json"
            f1.write_text(json.dumps({"url": "u", "findings": [
                {"dimension": "7.35", "status": "confirmed", "symptom": "运行期抛异常"}]}),
                encoding="utf-8")
            ss = tmp / "state_scenarios.json"
            ss.write_text(json.dumps([
                {"dimension": "7.25", "status": "fail", "findings": []},
                {"dimension": "7.26", "status": "notRun",
                 "reason": "未提供打印设计稿，无法比对"},
            ], ensure_ascii=False), encoding="utf-8")
            _, checks, _ = _assemble(tmp, findings=[f1], state_scenarios=ss)
            self.assertEqual(checks["7.35"]["status"], "fail")
            self.assertEqual(checks["7.25"]["status"], "fail")
            self.assertEqual(checks["7.26"]["status"], "notRun")
            self.assertEqual(checks["7.26"]["reason"], "未提供打印设计稿，无法比对")

    def test_scenario_coverage_never_produces_pass(self):
        """场景执行率只能证明「没跑」，不能证明「跑过没问题」。"""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            cov = tmp / "scenario_coverage.json"
            cov.write_text(json.dumps({
                "planned": {"total": 10, "byDimension": {"7.31": 3}},
                "executed": {"total": 0, "byDimension": {}},
                "notExecuted": {"total": 10, "byDimension": {"7.31": 3}},
            }, ensure_ascii=False), encoding="utf-8")
            _, checks, _ = _assemble(tmp, scenario_coverage=cov)
            self.assertEqual(checks["7.31"]["status"], "notRun")
            self.assertIn("场景", checks["7.31"]["reason"])

    def test_manual_checks_not_overwritten(self):
        """人填的比机器猜的优先级高。"""
        with tempfile.TemporaryDirectory() as td:
            _, checks, out = _assemble(Path(td), report={
                "meta": {"checks": {"7.39": {"status": "pass", "reason": "人工已走查"}}}})
            self.assertEqual(checks["7.39"]["status"], "pass")
            self.assertEqual(checks["7.39"]["reason"], "人工已走查")
            self.assertEqual(out["keptManual"], 1)

    def test_most_severe_wins(self):
        """同维多份证据取最严重：fail 压过 pass。"""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            sd = tmp / "styleDiffs.json"
            sd.write_text(json.dumps([
                {"dimension": "7.1", "property": "color", "status": "withinTolerance", "delta": 0.2},
                {"dimension": "7.1", "property": "borderRadius", "status": "confirmed", "delta": 6},
            ], ensure_ascii=False), encoding="utf-8")
            _, checks, _ = _assemble(tmp, style_diffs=sd)
            self.assertEqual(checks["7.1"]["status"], "fail")
            self.assertEqual(checks["7.1"]["evidence"]["count"], 2)

    def test_gate_accepts_output_without_unexplained(self):
        """端到端：产出的 checks 过 coverage_gate 不触发「未写明原因」。"""
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            ss = tmp / "state_scenarios.json"
            ss.write_text(json.dumps([
                {"dimension": "7.25", "status": "fail", "findings": []}]), encoding="utf-8")
            _, _, _ = _assemble(tmp, state_scenarios=ss)
            proc = subprocess.run(
                [sys.executable, str(SCRIPTS / "coverage_gate.py"),
                 "--report", str(tmp / "report.json")],
                capture_output=True, text=True)
            # 允许因覆盖率低而 enforce 失败（returncode 1），但不允许 4/5（非法状态/无原因）
            self.assertIn(proc.returncode, (0, 1), proc.stderr)
            self.assertNotIn("未写明原因", proc.stderr)


if __name__ == "__main__":
    unittest.main()
