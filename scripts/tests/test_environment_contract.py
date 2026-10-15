import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check_environment.py"


def run_check(cwd):
    return json.loads(subprocess.check_output([sys.executable, str(CHECK)], cwd=cwd, text=True))


def test_environment_reports_skill_version_and_real_browser_probe(tmp_path):
    result = run_check(tmp_path)
    assert result["version"] == "4.22.0"
    ids = {item["id"] for item in result["checks"]}
    assert {"playwright-core", "headed-browser"}.issubset(ids)
    assert all(item["status"] != "unknown" for item in result["checks"])


def test_login_script_resolves_installed_browser_and_requires_url():
    script = ROOT / "scripts" / "node" / "save_auth.cjs"
    text = script.read_text(encoding="utf-8")
    assert "PLAYWRIGHT_CHROME_PATH" in text
    assert "C:\\\\Program Files\\\\Google\\\\Chrome" in text
    proc = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert proc.returncode == 1
    assert "--url required" in proc.stderr
