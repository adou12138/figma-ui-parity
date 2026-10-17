#!/usr/bin/env python3
"""Start gate for UI parity runs.

This is a deterministic gate, not an interactive question UI. The orchestrator
must obtain the user's safety choice before invoking it and pass that choice in.
Non-test consultations should not call this script.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
TRIGGERS = re.compile(
    r"(开始|启动|重新执行|继续|跑|执行|检查|查看|看看|查查|验证|测|审)"
    r".*(ui\s*parity|figma|视觉|还原|走查|对照|响应式|自适应|断点|适配)"
    r"|ui\s*parity|走查",
    re.I,
)
FIGMA_HOSTS = {"figma.com", "www.figma.com"}


def is_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


def is_figma_url(value: str | None) -> bool:
    if not is_url(value):
        return False
    host = urlparse(value).netloc.lower().split(":")[0]
    return host in FIGMA_HOSTS or host.endswith(".figma.com")


# 【F43a】否定前缀：否定词后的「取消/不要/无需/先不」等意图反转词——
# 「取消走查」「不要跑 parity」不应触发 started=true（旧版裸词或运算全命中）。
#
# 【误伤修复】否定只应否定**紧随其后的那个短语**。旧实现对整句做 NEGATION.search，
# 只要句中任意位置出现「否定词 + 8 字内目标词」就无条件 return False：
#   - 「停止响应式适配检查，现在开始 UI Parity」被拒（真实意图是启动，否定在前一分句）；
#   - 「这个页面不需要响应式适配，走查走查」反而漏网（词表缺「不需要」）。
# 修法：① 按句读边界（。！？；\n）切句，判定范围限定在否定词所在的**那个分句**内；
#       ② 补齐「不需要/不想/不必/别」等词条。
# 句读边界：。！？；\n 为强边界；逗号同样是分句边界且是实测必需——
# 「停止响应式适配检查，现在开始 UI Parity」「这个页面不需要响应式适配，走查走查」
# 两例都只靠逗号断成「否定分句 + 启动分句」，只切强边界会落回整句单分句而误拒。
SENTENCE_SPLIT = re.compile(r"[。！？!?；;，,\n]")
NEGATION_WORDS = ("取消", "撤销", "不要", "无需", "先不", "暂停", "终止", "停止",
                  "放弃", "跳过", "不需要", "不想", "不必", "别", "不用", "无需再")
NEGATION_TARGETS = re.compile(
    r"(ui\s*parity|figma|视觉|还原|走查|对照|响应式|自适应|断点|适配|测试)", re.I)
NEGATION = re.compile(
    "(?:%s)\\s*[^。；！？!?\\n]{0,8}?(?:%s)"
    % ("|".join(NEGATION_WORDS), NEGATION_TARGETS.pattern), re.I)


def is_negated(instruction: str | None) -> bool:
    """判定整句是否含否定意图：只在否定词所在的**分句**内做匹配。

    分句之外的匹配一律不算否定——「停止响应式适配检查，现在开始 UI Parity」的第一个
    分句含否定（该分句内确实在否定适配检查），但第二个分句是明确的启动意图；
    因此只要**任一分句**不含否定、且整句含触发词，就应放行。
    这里返回「是否存在一个分句，其内含否定+目标词」——调用方据此与 TRIGGERS 联合判定。
    """
    if not instruction:
        return False
    for clause in SENTENCE_SPLIT.split(instruction):
        if clause.strip() and NEGATION.search(clause):
            return True
    return False


def positive_clause(instruction: str | None) -> str:
    """返回含触发词且不含否定的那部分文本（多个分句以空格连接）。

    触发判定同样必须限定在分句内：否定只否定紧随的短语，不能让否定分句里的
    目标词满足 TRIGGERS。
    """
    if not instruction:
        return ""
    ok = [c.strip() for c in SENTENCE_SPLIT.split(instruction)
          if c.strip() and not NEGATION.search(c)]
    return " ".join(ok)


def should_start(instruction: str | None, figma_url: str | None, page_urls: list[str]) -> tuple[bool, str]:
    # 否定判定收窄到分句后，只有当**全部分句**都被否定时才拒绝启动：
    # 「停止响应式适配检查，现在开始 UI Parity」——第一分句否定、第二分句启动 → 放行。
    if instruction and is_negated(instruction) and not positive_clause(instruction).strip():
        return False, "negated_test_instruction"
    if instruction and TRIGGERS.search(positive_clause(instruction)):
        return True, "explicit_test_instruction"
    if is_figma_url(figma_url) and any(is_url(item) for item in page_urls):
        return True, "figma_and_page_urls_present"
    return False, "not_a_test_start"


def run_json(command: list[str], cwd: Path) -> dict:
    proc = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "command failed").strip())
    return json.loads(proc.stdout)


def main() -> int:
    parser = argparse.ArgumentParser(description="UI parity 测试启动门禁")
    parser.add_argument("--instruction", default="")
    parser.add_argument("--figma-url", default="")
    parser.add_argument("--page-url", action="append", default=[])
    parser.add_argument("--safety-policy", choices=["all", "safe", "mockWrites", "staticOnly"], required=False)
    parser.add_argument("--test-environment-confirmed", action="store_true")
    parser.add_argument("--user-safety-selection", default="")
    parser.add_argument("--workdir", type=Path, default=Path("./parity-test"))
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    started, reason = should_start(args.instruction, args.figma_url, args.page_url)
    result = {"started": started, "trigger": reason}
    if not started:
        result["message"] = "未识别为 UI parity 测试启动，不执行环境检查或页面交互。"
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if not args.safety_policy:
        result.update({"status": "blocked", "reason": "safety_policy_required", "message": "正式测试前必须先取得本轮安全策略选择。"})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    if args.safety_policy == "all" and not args.test_environment_confirmed:
        result.update({"status": "blocked", "reason": "test_environment_confirmation_required", "message": "全部操作必须确认当前为隔离测试环境。"})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    root = args.root.resolve()
    workdir = args.workdir if args.workdir.is_absolute() else root / args.workdir
    subprocess.run(
        [sys.executable, str(HERE / "init_workdir.py"), "--root", str(root)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    environment = run_json([sys.executable, str(HERE / "check_environment.py")], root)
    # 【F43b】环境门禁必须真判：state=unavailable/needs_setup 时不得输出 status:ready——
    # 旧版拿到 environment 只透传不判断，「环境门禁」形同虚设。
    env_state = str((environment or {}).get("state", ""))
    write_interception = {"all": "none", "safe": "abort", "mockWrites": "mock", "staticOnly": "abort"}[args.safety_policy]
    # 【F43c】userSafetySelection 必须是用户原话：缺失时置 null（留痕"未提供"），
    # 不得用策略值伪造「用户选择」——违反 SKILL.md 留痕要求。
    user_selection = (args.user_safety_selection or "").strip()
    manifest = {
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "trigger": reason,
        "figmaUrl": args.figma_url,
        "pageUrls": args.page_url,
        "safetyPolicy": args.safety_policy,
        "userSafetySelection": user_selection or None,
        "userSafetySelectionProvided": bool(user_selection),
        "writeInterception": write_interception,
        "testEnvironmentConfirmed": bool(args.test_environment_confirmed),
        "environment": environment,
        "notRun": [] if args.safety_policy == "all" else ["caution", "danger"] if args.safety_policy == "safe" else ["danger"] if args.safety_policy == "mockWrites" else ["all interactive actions"],
    }
    # 【F49】run-manifest 必须落盘，即使环境降级/阻断也不例外——它记录的是本轮的
    # 安全策略与用户选择（SKILL.md 工作流第 1 步），旧版在 needs_setup/unavailable
    # 分支直接 return 且 manifest=None，安全留痕随环境缺失一起蒸发。
    workdir.mkdir(parents=True, exist_ok=True)
    manifest_path = workdir / "run-manifest.json"
    if env_state in ("unavailable", "needs_setup"):
        manifest["environmentGate"] = {
            "state": env_state,
            "verdict": "blocked" if env_state == "unavailable" else "degraded",
            "note": "环境检查未通过（%s）——依赖缺失时不得以 ready 状态放行正式测试" % env_state,
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        result.update({
            "status": "blocked" if env_state == "unavailable" else "degraded",
            "reason": "environment_%s" % env_state,
            "message": "环境检查状态为 %s：%s" % (
                env_state,
                "缺不可用依赖，正式测试被阻断；请先补齐依赖" if env_state == "unavailable"
                else "部分依赖未就绪，可降级执行但产物需标注环境降级"),
            "manifest": str(manifest_path),
            "environment": environment,
            "safetyPolicy": args.safety_policy,
        })
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3 if env_state == "unavailable" else 0
    manifest["environmentGate"] = {"state": env_state, "verdict": "pass"}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    result.update({"status": "ready", "manifest": str(manifest_path), "environment": environment, "safetyPolicy": args.safety_policy})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
