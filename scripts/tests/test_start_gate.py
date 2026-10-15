import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "start_test.py"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


class StartGateTests(unittest.TestCase):
    def test_consultation_does_not_start_environment_check(self):
        proc = run("--instruction", "解释 playwright-core 和 MCP 的区别")
        self.assertEqual(proc.returncode, 0)
        result = json.loads(proc.stdout)
        self.assertFalse(result["started"])
        self.assertEqual(result["trigger"], "not_a_test_start")

    def test_explicit_test_start_requires_safety_policy_before_environment_check(self):
        proc = run("--instruction", "开始执行 Figma UI parity 测试", "--figma-url", "https://www.figma.com/design/abc/x")
        self.assertEqual(proc.returncode, 2)
        result = json.loads(proc.stdout)
        self.assertTrue(result["started"])
        self.assertEqual(result["reason"], "safety_policy_required")

    def test_responsive_check_counts_as_test_start(self):
        proc = run("--instruction", "帮我看看这个页面的响应式有没有问题")
        self.assertEqual(proc.returncode, 2)
        result = json.loads(proc.stdout)
        self.assertTrue(result["started"])
        self.assertEqual(result["trigger"], "explicit_test_instruction")
        self.assertEqual(result["reason"], "safety_policy_required")

    def test_breakpoint_check_counts_as_test_start(self):
        proc = run("--instruction", "检查一下各断点下的适配")
        self.assertEqual(proc.returncode, 2)
        result = json.loads(proc.stdout)
        self.assertTrue(result["started"])

    def test_bare_topic_mention_does_not_start(self):
        proc = run("--instruction", "响应式是怎么回事")
        self.assertEqual(proc.returncode, 0)
        result = json.loads(proc.stdout)
        self.assertFalse(result["started"])
        self.assertEqual(result["trigger"], "not_a_test_start")

    def test_ui_walkthrough_counts_as_test_start(self):
        proc = run("--instruction", "帮我走查一下这个页面有没有 bug")
        self.assertEqual(proc.returncode, 2)
        result = json.loads(proc.stdout)
        self.assertTrue(result["started"])
        self.assertEqual(result["trigger"], "explicit_test_instruction")

    def test_url_pair_start_writes_manifest_after_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run(
                "--figma-url", "https://www.figma.com/design/abc/x",
                "--page-url", "https://devtest.example.test/page",
                "--safety-policy", "staticOnly",
                "--user-safety-selection", "仅静态检查",
                "--root", tmp,
                "--workdir", "parity-test",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            self.assertTrue(result["started"])
            manifest = json.loads((Path(tmp) / "parity-test" / "run-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["safetyPolicy"], "staticOnly")
            self.assertFalse(manifest["testEnvironmentConfirmed"])
            self.assertEqual(manifest["writeInterception"], "abort")


if __name__ == "__main__":
    unittest.main()
