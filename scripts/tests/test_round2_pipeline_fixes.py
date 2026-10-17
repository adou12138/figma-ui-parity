#!/usr/bin/env python3
"""第二轮深审管线修复的锁定测试（P2-9 / P2-12 / P2-16）。

P2-9  非门禁 stage 失败必须反映在退出码与 pipeline-log（degraded）——
      旧版 stabilize/diff_score/compare_fields 崩掉时管线仍 return 0。
P2-12 stage stdout 落盘（journey_coverage 完整矩阵此前只留 400 字符 tail）。
P2-16 dry-run + --page-url 时 state_scenarios 必须记 planned，
      不得报与事实相反的「缺少 --page-url」。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SKILL = Path(__file__).resolve().parents[2]
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

import run_parity_pipeline as RPP  # noqa: E402


def _run_pipeline(*extra, workdir, outdir):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / "run_parity_pipeline.py"),
         "--workdir", str(workdir), "--outdir", str(outdir), "--no-patterns", *extra],
        capture_output=True, text=True, timeout=120)


class TestRound2PipelineFailedStageExitCode(unittest.TestCase):
    """P2-9：非门禁 stage 失败 → rc=1 + pipelineStatus=degraded + stderr 告警。"""

    def test_diff_score_failure_fails_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = Path(tmp) / "wd"
            outdir = Path(tmp) / "out"
            # 两个不存在的 PNG 路径：Path 非空即进 stage，diff_score.js 打不开文件
            # 必然非零退出——非门禁 stage 的确定性失败。
            r = _run_pipeline("--figma-png", str(Path(tmp) / "nope1.png"),
                              "--page-png", str(Path(tmp) / "nope2.png"),
                              workdir=workdir, outdir=outdir)
            self.assertEqual(r.returncode, 1, r.stderr[-300:])
            self.assertIn("stage 失败", r.stderr)
            log = json.loads((outdir / "pipeline-log.json").read_text(encoding="utf-8"))
            self.assertEqual(log["pipelineStatus"], "degraded")
            self.assertIn("diff_score", log["failedStages"])

    def test_clean_partial_run_stays_zero(self):
        """无 stage 失败的部分链路（不传任何可选产物）仍 rc=0——P2-9 不误伤。"""
        with tempfile.TemporaryDirectory() as tmp:
            r = _run_pipeline(workdir=Path(tmp) / "wd", outdir=Path(tmp) / "out")
            self.assertEqual(r.returncode, 0, r.stderr[-300:])


class TestRound2StageStdoutCapture(unittest.TestCase):
    """P2-12：stdout_path 落盘——成功写全量、失败/空输出不写半截产物。"""

    def _stage_with(self, rc, stdout, tmpdir):
        log = {}
        out = Path(tmpdir) / "reports" / "journey_coverage.json"
        fake = SimpleNamespace(returncode=rc, stdout=stdout, stderr="")
        with mock.patch.object(RPP.subprocess, "run", return_value=fake):
            RPP.stage("probe", ["cmd"], False, log, stdout_path=out)
        return log, out

    def test_success_writes_full_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = json.dumps({"rate": 0.5, "matrix": ["x" * 5000]})
            log, out = self._stage_with(0, payload, tmp)
            self.assertEqual(log["probe"]["status"], "ran")
            self.assertEqual(log["probe"]["stdoutFile"], str(out))
            written = json.loads(out.read_text(encoding="utf-8"))
            self.assertEqual(written["rate"], 0.5)
            self.assertGreater(len(written["matrix"][0]), 4000, "落盘必须全量而非 400 字符 tail")

    def test_failure_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log, out = self._stage_with(1, '{"half": 1}', tmp)
            self.assertEqual(log["probe"]["status"], "failed")
            self.assertNotIn("stdoutFile", log["probe"])
            self.assertFalse(out.exists(), "失败 stage 不得产出半截产物")

    def test_empty_stdout_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log, out = self._stage_with(0, "", tmp)
            self.assertNotIn("stdoutFile", log["probe"])
            self.assertFalse(out.exists())


class TestRound2DryRunPlansStateScenarios(unittest.TestCase):
    """P2-16：dry-run + --page-url → state_scenarios 记 planned（对齐 stabilize），
    不得报与事实相反的「缺少 --page-url」。"""

    def test_dry_run_with_page_url_plans_state_scenarios(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = _run_pipeline("--dry-run", "--page-url", "https://example.test/",
                              workdir=Path(tmp) / "wd", outdir=Path(tmp) / "out")
            self.assertEqual(r.returncode, 0, r.stderr[-300:])
            planned = [line for line in r.stdout.splitlines()
                       if line.startswith("[plan]") and "run_state_scenarios" in line]
            self.assertTrue(planned, "dry-run 计划必须包含 state_scenarios 阶段")
            self.assertNotIn("缺少 --page-url", r.stdout, "reason 不得与事实相反")

    def test_no_page_url_still_explains(self):
        """真跑（非 dry-run）无 page-url：notRun + 准确的缺失说明进 pipeline-log。"""
        with tempfile.TemporaryDirectory() as tmp:
            r = _run_pipeline(workdir=Path(tmp) / "wd", outdir=Path(tmp) / "out")
            self.assertEqual(r.returncode, 0, r.stderr[-300:])
            log = json.loads((Path(tmp) / "out" / "pipeline-log.json").read_text(encoding="utf-8"))
            self.assertEqual(log["state_scenarios"]["status"], "notRun")
            self.assertIn("缺少 --page-url", log["state_scenarios"]["reason"])


if __name__ == "__main__":
    unittest.main()