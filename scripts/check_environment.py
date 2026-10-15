#!/usr/bin/env python3
"""Read-only dependency check for figma-ui-parity v4.20.0."""
from __future__ import annotations
import json, os, shutil, subprocess, sys
from pathlib import Path

VERSION = "4.20.0"
checks = []
def add(id, status, detail): checks.append({"id": id, "status": status, "detail": detail})

def browser_candidates():
    candidates = []
    if os.environ.get("PLAYWRIGHT_CHROME_PATH"):
        candidates.append(Path(os.environ["PLAYWRIGHT_CHROME_PATH"]))
    home = Path.home()
    base = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", home / "AppData/Local/ms-playwright"))
    if base.exists():
        candidates.extend(sorted(base.glob("chromium-*/chrome-win64/chrome.exe"), reverse=True))
    candidates.extend(Path(p) for p in (
        r"C:/Program Files/Google/Chrome/Application/chrome.exe",
        r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        r"C:/Program Files/Microsoft/Edge/Application/msedge.exe",
        r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    ))
    return [p for p in candidates if p.exists()]

add("python-runtime", "ready" if sys.version_info >= (3, 10) else "unavailable", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
node = shutil.which("node")
add("node-runtime", "ready" if node else "unavailable", "available" if node else "not-found")
playwright_ok = False
if node:
    probe_code = "require('playwright-core')"
    local_pw = Path(__file__).resolve().parents[3] / "cdp_driver" / "node_modules" / "playwright-core"
    if local_pw.exists():
        probe_code = f"require({json.dumps(str(local_pw))})"
    probe = subprocess.run([node, "-e", probe_code], capture_output=True, text=True)
    playwright_ok = probe.returncode == 0
add("playwright-core", "ready" if playwright_ok else "needs_setup", "loadable" if playwright_ok else "not-found")
browsers = browser_candidates()
add("headed-browser", "ready" if browsers else "needs_setup", str(browsers[0]) if browsers else "not-found")
add("playwright-mcp", "partial", "host-provided capability; verify through MCP before run")
add("figma-source", "partial", "MCP must be selected by orchestrator; no token printed")
add("visual-parity", "partial", "compare capability must be verified by orchestrator")
work = Path.cwd() / "parity-test"
try:
    work.mkdir(parents=True, exist_ok=True)
    probe = work / ".write_probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    add("output-directory", "ready", str(work))
except OSError as exc:
    add("output-directory", "unavailable", type(exc).__name__)

statuses = {x["status"] for x in checks}
state = "unavailable" if "unavailable" in statuses else "needs_setup" if "needs_setup" in statuses else "partial" if "partial" in statuses else "ready"
print(json.dumps({"state": state, "skill": "figma-ui-parity", "version": VERSION, "checks": checks}, ensure_ascii=False, indent=2))
