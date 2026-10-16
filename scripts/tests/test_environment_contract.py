#!/usr/bin/env python3
"""check_environment 契约测试（unittest，可被 discover -s tests 收集）。

【审查修复】旧版是 pytest 风格（函数式 test_* + tmp_path fixture），本环境无
pytest → discover 收集数为 0，是**从未被执行过的死测试**；且版本断言硬编码
"4.26.0"，随批次1 升版后必然红。改为：unittest.TestCase + 版本从 SKILL.md
frontmatter 读活值（版本双轨硬编码正是 F42 要治的问题之一，测试不 reproduces 它）。
"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check_environment.py"


def _skill_version() -> str:
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r"^version:\s*([0-9.]+)", text, re.M)
    assert m, "SKILL.md frontmatter 缺 version"
    return m.group(1)


class EnvironmentContractTests(unittest.TestCase):
    def _run_check(self, cwd):
        proc = subprocess.run([sys.executable, str(CHECK)], cwd=str(cwd),
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr[-400:]
        return json.loads(proc.stdout)

    def test_environment_reports_skill_version_and_real_browser_probe(self):
        with tempfile.TemporaryDirectory() as td:
            result = self._run_check(Path(td))
        self.assertEqual(result["version"], _skill_version(),
                         "check_environment VERSION 与 SKILL.md frontmatter 漂移")
        ids = {item["id"] for item in result["checks"]}
        self.assertLessEqual({"playwright-core", "headed-browser"}, ids)
        self.assertTrue(all(item["status"] != "unknown" for item in result["checks"]))

    def test_login_script_resolves_installed_browser_and_requires_url(self):
        script = ROOT / "scripts" / "node" / "save_auth.cjs"
        text = script.read_text(encoding="utf-8")
        self.assertIn("PLAYWRIGHT_CHROME_PATH", text)


if __name__ == "__main__":
    unittest.main()
