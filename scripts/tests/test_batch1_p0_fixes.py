#!/usr/bin/env python3
"""批次1 P0 修复的行为回归测试（F1/F2/F3/F7/F8/F23/F24/F25）。

每条对应方案里的一个编号，修复前必红、修复后绿。核心断言形态是
「守恒」与「端到端」：产出的 checks 能过门禁、confirmed 缺陷必映射成 fail。
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

import assemble_report as AR       # noqa: E402
import normalize_evidence as NE    # noqa: E402
import coverage_gate as CG         # noqa: E402

DIMS = json.loads((SKILL / "schemas" / "check-dimensions.json").read_text(encoding="utf-8"))
ALL_DIM_IDS = [str(d["id"]) for d in DIMS.get("dimensions", []) if d.get("id")]


def _run(cmd):
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True)


class TestF1StyleDiffsReachReport(unittest.TestCase):
    """F1：compare_fields 的 styleDiffs/defects 必须进 checks（端到端断裂修复）。"""

    def test_collect_reads_stylediffs_key(self):
        sd = {"styleDiffs": [
            {"dimension": "7.1", "property": "color", "status": "confirmed", "delta": "2.1"},
            {"dimension": "7.1", "property": "fontSize", "status": "withinTolerance", "delta": "0.5"},
            {"dimension": "7.8", "property": "characters", "status": "notComparable", "delta": None},
        ]}
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "styleDiffs.json"
            p.write_text(json.dumps(sd), encoding="utf-8")
            ev = {}
            AR.collect_style_diffs(p, ev)
        self.assertEqual(ev["7.1"][0]["status"], "fail", "confirmed 必须映射 fail")
        self.assertEqual(ev["7.1"][1]["status"], "pass")
        self.assertEqual(ev["7.8"][0]["status"], "dataMissing")

    def test_end_to_end_confirmed_becomes_fail_in_checks(self):
        """端到端：带 confirmed 的 styleDiffs → assemble → checks 里 7.1=fail。"""
        sd = {"styleDiffs": [
            {"dimension": "7.1", "property": "color", "status": "confirmed", "delta": "2.1"}]}
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            sdp = tmp / "styleDiffs.json"
            sdp.write_text(json.dumps(sd), encoding="utf-8")
            report = {"url": "https://p.test/", "defects": []}
            rp = tmp / "report.json"
            rp.write_text(json.dumps(report), encoding="utf-8")
            proc = _run([sys.executable, SCRIPTS / "assemble_report.py",
                         "--report", rp, "--style-diffs", sdp, "--write"])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            written = json.loads(rp.read_text(encoding="utf-8"))
            checks = written["meta"]["checks"]
            self.assertEqual(checks["7.1"]["status"], "fail",
                             "F1 断裂：confirmed 缺陷未映射成 fail")


class TestF24DataMissingHasReason(unittest.TestCase):
    """F24：dataMissing 证据无 reason 时 summarize 兜底补——否则修好 F1 后门禁假失败。"""

    def test_not_comparable_gets_fallback_reason(self):
        sd = {"styleDiffs": [
            {"dimension": "7.8", "property": "characters", "status": "notComparable"}]}
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            sdp = tmp / "styleDiffs.json"
            sdp.write_text(json.dumps(sd), encoding="utf-8")
            rp = tmp / "report.json"
            rp.write_text(json.dumps({"url": "x", "defects": []}), encoding="utf-8")
            proc = _run([sys.executable, SCRIPTS / "assemble_report.py",
                         "--report", rp, "--style-diffs", sdp, "--write"])
            self.assertEqual(proc.returncode, 0, proc.stderr)
            checks = json.loads(rp.read_text(encoding="utf-8"))["meta"]["checks"]
            entry = checks["7.8"]
            self.assertEqual(entry["status"], "dataMissing")
            self.assertTrue(entry.get("reason"), "dataMissing 必须带兜底 reason")
        # 且能过 coverage_gate 的「未写明原因」检查
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rp = tmp / "report.json"
            rp.write_text(json.dumps({"url": "x", "defects": [],
                                      "meta": {"checks": {dim: {
                                          "status": "notRun",
                                          "reason": "无产物"} for dim in ALL_DIM_IDS}}}),
                          encoding="utf-8")
            # 把 7.8 换成无 reason 的 dataMissing，模拟修复前形状
            checks = json.loads(rp.read_text(encoding="utf-8"))["meta"]["checks"]
            checks["7.8"] = {"status": "dataMissing"}
            rp.write_text(json.dumps({"meta": {"checks": checks}}), encoding="utf-8")
            entry = CG.status_of(checks["7.8"])
            self.assertEqual(entry[0], "dataMissing")


class TestF8FingerprintKeepsDistinctFindings(unittest.TestCase):
    """F8：不同 dimension/property/symptom 的 findings 不得被指纹塌缩。"""

    def test_three_distinct_739_findings_survive(self):
        items = [
            {"dimension": "7.39", "property": "js-error", "symptom": "doc error: TypeError x",
             "element": None},
            {"dimension": "7.39", "property": "noop", "symptom": "click did nothing on .save"},
            {"dimension": "7.39", "property": "back-broken", "symptom": "history.back no-op"},
        ]
        fps = [NE.fingerprint(i) for i in items]
        self.assertEqual(len(set(fps)), 3, "三条不同缺陷被指纹塌缩（证据蒸发）")

    def test_true_duplicate_still_merges(self):
        a = {"dimension": "7.35", "property": "js-error", "symptom": "boom",
             "element": {"selector": ".s", "nth": 0}, "page": "p"}
        import copy
        b = copy.deepcopy(a)
        self.assertEqual(NE.fingerprint(a), NE.fingerprint(b), "真重复必须仍判同")


class TestF23MissingDimensionIsUnexplained(unittest.TestCase):
    """F23：维度整体缺失必须进 unexplained（不能删行绕过门禁）。"""

    def test_missing_dim_triggers_rc5(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            # checks 覆盖全部维度但**删掉 7.34**
            checks = {dim: {"status": "pass"} for dim in ALL_DIM_IDS if dim != "7.34"}
            rp = tmp / "report.json"
            rp.write_text(json.dumps({"meta": {"checks": checks}}), encoding="utf-8")
            proc = _run([sys.executable, SCRIPTS / "coverage_gate.py",
                         "--report", rp, "--enforce", "--write"])
            self.assertEqual(proc.returncode, 5,
                             "删维度必须按「未写明原因」拦截（旧版 exit 0 绕过）")
            cov = json.loads(rp.read_text(encoding="utf-8"))["meta"]["coverage"]
            self.assertIn("7.34", cov["missingDimensions"])
            self.assertTrue(any("7.34" in u for u in cov["unexplained"]))


class TestF25EmptyDefectsExplicit(unittest.TestCase):
    """F25：严格模式下 report 必须显式存在缺陷数组键；失败时不写回。"""

    def test_strict_rejects_missing_defect_key(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rp = tmp / "report.json"
            rp.write_text(json.dumps({"url": "x", "note": "没有任何缺陷键"}), encoding="utf-8")
            proc = _run([sys.executable, SCRIPTS / "validate_defects.py",
                         "--report", rp, "--strict"])
            self.assertEqual(proc.returncode, 6, "缺缺陷键必须报错（忘填≠真零缺陷）")

    def test_explicit_empty_list_passes_strict(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rp = tmp / "report.json"
            rp.write_text(json.dumps({"url": "x", "defects": []}), encoding="utf-8")
            proc = _run([sys.executable, SCRIPTS / "validate_defects.py",
                         "--report", rp, "--strict"])
            self.assertEqual(proc.returncode, 0, "显式空数组是真零缺陷，应通过")

    def test_no_write_on_failure(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            rp = tmp / "report.json"
            original = {"url": "x", "note": "no defect key"}
            rp.write_text(json.dumps(original), encoding="utf-8")
            proc = _run([sys.executable, SCRIPTS / "validate_defects.py",
                         "--report", rp, "--strict", "--write"])
            self.assertEqual(proc.returncode, 6)
            after = json.loads(rp.read_text(encoding="utf-8"))
            self.assertNotIn("defectValidation", after.get("meta", {}),
                             "校验失败时不得写回（help 承诺通过时才写）")


class TestF7ExcelReadsListDefects(unittest.TestCase):
    """F7：gen_excel_fallback 必须同时认列表形与 dict 形缺陷。"""

    def test_rows_from_list_defects(self):
        sys.path.insert(0, str(SCRIPTS))
        import gen_excel_fallback as GE
        report = {"defects": [
            {"severity": "high", "category": "颜色", "element": {"selector": ".a"},
             "issue": "主色错", "fix": "改回 #1677ff"}]}
        rows = GE.rows_from_report(report)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["等级"], "高")

    def test_rows_from_dict_diffs_still_work(self):
        sys.path.insert(0, str(SCRIPTS))
        import gen_excel_fallback as GE
        report = {"diffs": {"high": [
            {"category": "尺寸", "element": {"selector": ".b"},
             "issue": "宽 200→180", "fix": "核对宽度"}]}}
        rows = GE.rows_from_report(report)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
