#!/usr/bin/env python3
"""Generate element-level UI scenarios from the design model and page inventory.

Input contract (see references/scenario-contract.md):
  --design  extract_design_fields.py output (optional)
  --page    collect_page_inventory.js output (optional)
  --pairs   compare_fields.py output (optional, drives 7.23 双向盘点)
  --roles   roles to walk, e.g. "admin,member" (optional, drives 7.34)

Output: scenarios.json where every scenario carries its dimension code (7.x),
the target element, the action, the expectation and machine-checkable assertions,
so a runner needs no guesswork. Offline only.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ANOMALY_DATA = [
    {"id": "empty", "value": "", "expect": "必填校验触发并定位到该字段"},
    {"id": "single-char", "value": "a", "expect": "正常接受，不出现布局塌陷"},
    {"id": "long-cjk", "value": "问卷星" * 25, "expect": "截断或换行符合设计，不撑破容器"},
    {"id": "long-latin", "value": "WenjuanxingUI" * 20, "expect": "长英文不撑宽按钮或表格列"},
    {"id": "mixed", "value": "张三 ZhangSan 2026", "expect": "中英混排对齐正常"},
    {"id": "digits-symbols", "value": "1234567890!@#$%^&*()", "expect": "特殊符号按预期处理"},
    {"id": "emoji", "value": "测试😀🎉🚀", "expect": "emoji 不导致行高跳动或错位"},
    {"id": "full-width", "value": "ＡＢＣ１２３（）", "expect": "全角字符不溢出"},
    {"id": "multiline", "value": "第一行\n第二行\n第三行", "expect": "多行输入按设计换行"},
    {"id": "long-url", "value": "https://example.com/" + "a" * 120, "expect": "长链接不撑破容器"},
    {"id": "html-injection", "value": "<b>x</b>&\"'", "expect": "按纯文本展示，不解析为标签"},
    {"id": "extreme-number", "value": "999999999999999", "expect": "超长数字不溢出且校验合理"},
]

CASE_LABEL = {
    "empty": "空值", "single-char": "单字符", "long-cjk": "超长中文", "long-latin": "超长英文",
    "mixed": "中英混排", "digits-symbols": "数字符号", "emoji": "emoji", "full-width": "全角",
    "multiline": "多行", "long-url": "长链接", "html-injection": "标签字符", "extreme-number": "极端数值",
}

DANGER_WORDS = ["删除", "清空", "退出", "解绑", "退款", "支付", "下线", "注销", "移除", "销毁",
                "delete", "remove", "logout", "signout", "sign-out", "unbind", "destroy"]
# 风险词表单源是 scripts/node/risk_words.cjs（js 侧为超集）；本常量与它对拍，
# 由 scripts/tests/test_risk_words_parity.py 保证两边集合一致，改词表只改一处再同步。
CAUTION_WORDS = ["保存", "提交", "创建", "新增", "导入", "上传", "发送", "同步", "发布", "确认", "绑定",
                 "save", "submit", "create", "import", "upload", "send", "sync", "publish"]
MODAL_WORDS = ["新增", "添加", "编辑", "修改", "选择", "设置", "详情", "分享", "create", "add", "edit"]


def safety_of(text: str) -> str:
    lowered = (text or "").lower()
    if any(w in lowered for w in DANGER_WORDS):
        return "danger"
    if any(w in lowered for w in CAUTION_WORDS):
        return "caution"
    return "safe"


def bbox_of(element: dict) -> dict:
    rect = element.get("rect") or element.get("bbox") or {}
    return {"x": rect.get("x", 0), "y": rect.get("y", 0), "w": rect.get("w", 0), "h": rect.get("h", 0)}


# 风险排序：元素级场景有条数上限，按位置切片会让"排在后面的高风险元素"被砍掉。
# 排序把危险/写操作、无名称图标按钮顶到前面，让有限预算先打高价值目标——
# 与默认档相比只是**选择的先后**，场景总数不变（不改变截断上限）。
_BTN_RANK = {"danger": 0, "caution": 1, "safe": 3}


def button_risk(btn: dict) -> int:
    text = str(btn.get("text") or btn.get("title") or "")
    if not text.strip():
        return 2  # 无名称图标按钮：可访问性风险，靠前
    return _BTN_RANK.get(safety_of(text), 3)


def input_risk(item: dict) -> int:
    return 0 if not item.get("labelled") else 1  # 缺 label 关联的输入靠前


# ---------- 缺陷模式池反哺（可选，--patterns） ----------
# 闭环落点：让"上一轮翻车最多的维度"这一轮**一定被覆盖到**（补齐被内容门槛挡掉的场景、
# 加深异常数据），而不是让 agent 自觉多测。**只影响覆盖与深度，不自动生成断言**——
# 从一条历史缺陷推不出"修复后的正确行为"，自动生成会产生错误断言（同 wjx 闭环边界）。
SEV_WEIGHT = {"P0": 8, "P1": 4, "P2": 2, "P3": 1}


def pattern_weights(path) -> dict:
    """读缺陷模式池 → {dimension: 权重}。权重 = Σ(等级权重 × 命中次数)。"""
    weights = {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return weights
    for p in (data.get("patterns") or []):
        dim = str(p.get("dimension") or "").strip()
        if not dim:
            continue
        sev = str(p.get("severity") or "P2").upper()
        w = SEV_WEIGHT.get(sev, 2)
        try:
            hits = max(1, int(p.get("hits") or len(p.get("sources") or []) or 1))
        except (TypeError, ValueError):
            hits = 1
        weights[dim] = weights.get(dim, 0) + w * hits
    return weights


class Builder:
    def __init__(self, page_url: str, max_scenarios: int):
        self.items: list = []
        self.page_url = page_url
        self.max_scenarios = max_scenarios
        self.dimensions: set = set()
        self.dropped: dict = {}

    def add(self, name, dimension, *, level="page", element=None, action=None, expected="", assertions=None,
            data=None, safety="safe", source="baseline", precondition=None, viewport=None, runner=None) -> None:
        if len(self.items) >= self.max_scenarios:
            # 截断必须留痕：被丢弃的场景按维度计数并随结果输出，
            # 由报告写明，不允许静默丢弃。
            self.dropped[dimension] = self.dropped.get(dimension, 0) + 1
            return
        index = len(self.items) + 1
        self.items.append({
            "id": "S-{:04d}".format(index),
            "name": name,
            "dimension": dimension,
            "level": level,
            "element": element,
            "action": action or {"type": "none"},
            "precondition": precondition or [],
            "expected": expected,
            "assertions": assertions or [],
            "data": data,
            "safety": safety,
            "source": source,
            "viewport": viewport,
            "page": self.page_url,
            "runner": runner,
        })
        self.dimensions.add(dimension)


def build(args) -> dict:
    design = json.loads(args.design.read_text(encoding="utf-8")) if args.design and args.design.exists() else {}
    page = json.loads(args.page.read_text(encoding="utf-8")) if args.page and args.page.exists() else {}
    pairs = json.loads(args.pairs.read_text(encoding="utf-8")) if args.pairs and args.pairs.exists() else {}
    page_url = args.page_url or page.get("url") or ""
    roles = [r.strip() for r in (args.roles or "").split(",") if r.strip()]

    kinds = set(page.get("interactionKinds") or []) | set(design.get("interactionKinds") or [])
    buttons = [b for b in (page.get("buttons") or []) if isinstance(b, dict)]
    inputs = [i for i in (page.get("inputs") or []) if isinstance(i, dict)]
    images = [m for m in (page.get("images") or []) if isinstance(m, dict)]
    overlays = [m for m in (page.get("modals") or []) if isinstance(m, dict)]
    empties = [e for e in (page.get("emptyStateCandidates") or []) if isinstance(e, dict)]
    scrollables = page.get("scrollables") or []

    # 组合深度：1=单点（默认，输出与不放宽时一致）；>=2 加深异常数据条数与逐断点展开。
    combo = max(1, int(getattr(args, "combo_depth", 1) or 1))
    bps = [x.strip() for x in str(getattr(args, "breakpoints", "") or "").split(",") if x.strip()]
    # 风险排序（不改变截断上限，只改变选择先后）
    buttons = sorted(buttons, key=button_risk)
    inputs = sorted(inputs, key=input_risk)
    # 自适应深度：表单密集页面在组合档下加深异常数据覆盖
    data_cases = int(args.max_data_cases)
    if combo >= 2 and page.get("forms") and len(inputs) >= 3:
        data_cases = min(len(ANOMALY_DATA), data_cases + 3)

    # 缺陷模式池反哺：历史高频翻车的维度即使被内容门槛挡住也补场景、异常数据加深。
    # 不传 --patterns 时 weights 为空，下面所有分支都不触发——输出与接入前完全一致。
    weights = pattern_weights(args.patterns) if getattr(args, "patterns", None) else {}
    hot = {d for d, w in weights.items() if w > 0}
    deepened = {}
    if "7.17" in hot and len(inputs) >= 1:
        before = data_cases
        data_cases = min(len(ANOMALY_DATA), data_cases + 2)
        # 只在**真的加深了**时才记 deepened：已达上限时记"声称加深但没加"是不诚实的
        if data_cases > before:
            deepened["7.17"] = {"reason": "历史表单校验类缺陷高发", "dataCases": "%s→%s" % (before, data_cases)}

    b = Builder(page_url, args.max_scenarios)

    b.add("页面默认态", "7.1", expected="整页样式与设计一致",
          assertions=["样式层无超容差差异", "像素 diff 在阈值内"], source="baseline")
    if buttons:
        anchor = buttons[0].get("text") or buttons[0].get("selector")
        b.add("按钮悬停态", "7.2", element={"selector": buttons[0].get("selector"), "nth": buttons[0].get("nth", 0), "anchor": anchor},
              action={"type": "hover"}, expected="悬停样式符合设计（背景/边框/阴影变化）",
              assertions=["hover 前后样式差与设计 variant 一致"], source="element-inventory")
        b.add("键盘焦点态", "7.29", element={"selector": buttons[0].get("selector"), "nth": buttons[0].get("nth", 0), "anchor": anchor},
              action={"type": "focus"}, expected="焦点可见（outline 或等价 focus-visible 样式）",
              assertions=["focus 后存在可见焦点环", "outline 未被 outline:none 清除"], source="element-inventory")
    b.add("加载态", "7.20", expected="骨架屏或 loading 占位符合设计且不闪烁",
          assertions=["存在 loading 指示", "加载完成后占位消失"], source="baseline")
    if empties:
        b.add("空数据态", "7.20", element={"selector": empties[0].get("selector"), "nth": 0, "anchor": empties[0].get("text")},
              expected="空状态文案与插图符合设计", assertions=["空状态可见且文案与设计一致"], source="page-inventory")
    if page.get("forms"):
        b.add("表单空值提交", "7.17", action={"type": "click", "target": "submit"},
              expected="必填校验触发并定位到首个错误字段",
              assertions=["出现错误提示", "焦点或滚动定位到错误字段", "提交未成功"], safety="caution", source="page-inventory")
        b.add("表单非法值提交", "7.17", action={"type": "input", "value": "!@#$"},
              expected="非法输入被拦截或给出明确提示", safety="caution", source="page-inventory")
    if combo >= 2 and len(bps) >= 2:
        # 组合档：把"多视口"展开成逐断点场景（单点档只给一条 viewport="all"）
        for bp in bps:
            b.add("视口 %s 适配" % bp, "7.4", viewport=bp,
                  expected="该断点无横向溢出、元素不跑出视口、触控目标达标",
                  assertions=["document.scrollWidth <= innerWidth", "无元素 right > innerWidth", "触控目标 >= 44px"],
                  source="combo")
    else:
        b.add("多视口态", "7.4", viewport="all", expected="各断点无横向溢出、元素不跑出视口",
              assertions=["document.scrollWidth <= innerWidth", "无元素 right > innerWidth", "触控目标 >= 44px"], source="baseline")
    b.add("长文本与多语言", "7.21", action={"type": "input", "value": ANOMALY_DATA[2]["value"]},
          expected="长文案下布局不破坏", source="baseline")
    b.add("密集数据", "7.21", expected="多条目下列表密度、行高与设计一致", safety="caution", source="baseline")
    b.add("暗色模式", "7.25", action={"type": "theme", "value": "dark"},
          expected="深色下文字仍可读、无硬编码浅色背景",
          assertions=["无文字与背景对比度低于 4.5 的元素", "无仅主题变色的硬编码 #fff 背景"],
          runner="node/run_state_scenarios.cjs", source="dimension")
    b.add("打印视图", "7.26", action={"type": "media", "value": "print"},
          expected="打印时不丢失内容、操作按钮不误入",
          runner="node/run_state_scenarios.cjs", source="dimension")
    b.add("慢网络与接口异常", "7.33", action={"type": "network", "value": "500"},
          expected="接口失败时给出错误提示而非白屏或骨架残留",
          assertions=["出现错误提示或重试入口", "骨架屏未永久残留"], safety="caution",
          runner="node/run_state_scenarios.cjs", source="dimension")
    if kinds & {"tabs", "table", "pagination"}:
        b.add("路由切换后状态", "7.32", action={"type": "route-back"},
              expected="返回后筛选/滚动/展开态不残留或按设计重置",
              assertions=["返回后列表状态与首次进入一致"],
              runner="node/run_state_scenarios.cjs", source="dimension")
    elif "7.32" in hot:
        # 池里有状态残留类历史缺陷，但本页没识别到 tabs/table/pagination → 仍补一条页面级
        # 往返场景：hash 导航 + 返回是页面级动作，不需要元素也能实测（记录动因，不静默补）。
        b.add("路由切换后状态（按历史缺陷模式补充）", "7.32", action={"type": "route-back"},
              expected="返回后筛选/滚动/展开态不残留或按设计重置",
              assertions=["返回后页面状态与首次进入一致"],
              runner="node/run_state_scenarios.cjs", source="pattern-deep")
        deepened["7.32"] = {"reason": "池内该维度有历史缺陷但页面未识别到路由类元素，按模式补页面级往返场景"}
    if scrollables:
        b.add("滚动容器与固定元素", "7.31", expected="固定底栏不遮挡内容、sticky 头部不互相重叠",
              assertions=["最后一行内容可完整滚动到可视区", "sticky/fixed 元素不遮挡可点击区域"], source="page-inventory")
    elif "7.31" in hot:
        b.add("滚动与固定元素（按历史缺陷模式补充）", "7.31",
              expected="固定底栏不遮挡内容、无弹层时页面滚动不被锁死",
              assertions=["body 未被无谓锁定滚动", "fixed/sticky 元素不遮挡可点击区域"], source="pattern-deep")
        deepened["7.31"] = {"reason": "池内该维度有历史缺陷但页面未识别到滚动容器，补页面级滚动 UX 场景"}
    if (page.get("viewport") or {}).get("dpr"):
        b.add("截图倍率一致性", "7.1", expected="设计稿导出倍率与页面截图 deviceScaleFactor 相同", source="dimension")
    for overlay in overlays[: min(5, args.max_elements)]:
        b.add("已渲染浮层走查：{}".format(overlay.get("selector")), "7.14", level="element",
              element={"selector": overlay.get("selector"), "nth": 0, "anchor": "浮层", "bbox": bbox_of(overlay)},
              action={"type": "none"}, expected="浮层内部元素与设计一致，未显示时不影响布局", source="page-inventory")

    for btn in buttons[: args.max_elements]:
        text = str(btn.get("text") or btn.get("title") or "")
        element = {"selector": btn.get("selector"), "nth": btn.get("nth", 0), "anchor": text, "bbox": bbox_of(btn)}
        b.add("点击『{}』生效判定".format(text or btn.get("selector")), "7.22", level="element", element=element,
              action={"type": "click"}, expected="点击后产生可观察结果（DOM/URL/请求/Toast/弹窗任一）",
              assertions=["命中测试 elementFromPoint 命中自身", "点击后至少一个生效信号变化"],
              safety=safety_of(text), source="element-inventory")
        if btn.get("inModal"):
            b.add("弹窗内『{}』层级与裁切".format(text or btn.get("selector")), "7.18", level="element", element=element,
                  action={"type": "none"}, expected="弹窗内元素不被父容器裁切、层级正确", source="element-inventory")
        if btn.get("disabled"):
            b.add("禁用态『{}』".format(text or btn.get("selector")), "7.20", level="element", element=element,
                  action={"type": "click"}, expected="禁用态样式与设计一致且点击无效", source="element-inventory")
        if any(w in text for w in MODAL_WORDS):
            b.add("打开『{}』后逐个走查弹窗".format(text), "7.14", level="element", element=element,
                  action={"type": "click"}, expected="弹窗内每个元素与设计一致，关闭后无残留",
                  assertions=["弹窗打开后重新盘点 DOM", "关闭后遮罩与滚动锁恢复"],
                  safety=safety_of(text), source="element-inventory")
        if not btn.get("text") and not btn.get("title"):
            b.add("无名称图标按钮可访问性", "7.19", level="element", element=element, action={"type": "none"},
                  expected="图标按钮有 aria-label 或可读名称", source="element-inventory")

    for input_index, item in enumerate(inputs[: args.max_elements]):
        element = {"selector": item.get("selector"), "nth": item.get("nth", 0),
                   "anchor": item.get("placeholder") or item.get("selector"), "bbox": bbox_of(item)}
        if not item.get("labelled"):
            b.add("字段缺少 label 关联", "7.19", level="element", element=element, action={"type": "none"},
                  expected="label 与输入框建立关联（label[for] 或 aria-label）", source="element-inventory")
        # 按输入框序号轮转取样：固定取前 N 条会让 long-url / html-injection /
        # extreme-number 等排在后面的用例在默认参数下永远覆盖不到。
        offset = input_index % len(ANOMALY_DATA)
        samples = [ANOMALY_DATA[(offset + k) % len(ANOMALY_DATA)] for k in range(min(data_cases, len(ANOMALY_DATA)))]
        for sample in samples:
            b.add("『{}』输入{}".format(element["anchor"], CASE_LABEL.get(sample["id"], sample["id"])),
                  "7.17", level="element", element=element, action={"type": "input", "value": sample["value"]},
                  expected=sample["expect"], data={"case": sample["id"], "value": sample["value"]},
                  assertions=["输入后布局不溢出", "占位与光标位置正常"], safety="caution", source="anomaly-data")
        # 组合档：异常输入 × 断点（仅前 3 个高风险输入、每输入 2 个样本 × 首尾断点，防爆炸）
        if combo >= 2 and bps and input_index < 3:
            for sample in samples[:2]:
                for bp in (bps[0], bps[-1]):
                    b.add("『{}』输入{} @ {}".format(element["anchor"], CASE_LABEL.get(sample["id"], sample["id"]), bp),
                          "7.4", level="element", element=element,
                          action={"type": "input", "value": sample["value"]}, viewport=bp,
                          expected="该断点下异常输入不破坏布局", data={"case": sample["id"], "value": sample["value"], "viewport": bp},
                          assertions=["输入后布局不溢出"], safety="caution", source="combo")
        if item.get("type") in ("number", "tel", "password", "date", "search"):
            b.add("原生控件细节（{}）".format(item.get("type")), "7.28", level="element", element=element,
                  action={"type": "none"}, expected="原生控件外观与交互符合设计，不出现浏览器默认样式破坏布局",
                  assertions=["placeholder 颜色符合设计", "autocomplete 不遮挡字段"], source="element-inventory")

    for image in images[: args.max_elements]:
        ratio, natural_ratio = image.get("ratio"), image.get("naturalRatio")
        element = {"selector": image.get("selector"), "nth": image.get("nth", 0), "anchor": "图片", "bbox": bbox_of(image)}
        if ratio and natural_ratio and abs(ratio - natural_ratio) > 0.05:
            b.add("图片宽高比失真", "7.24", level="element", element=element, action={"type": "none"},
                  expected="渲染比例与图片固有比例一致或按设计裁剪（object-fit）",
                  assertions=["渲染比例与原始比例差 <= 5% 或 object-fit 明确为 cover/contain"], source="page-inventory")
        if image.get("loaded") is False:
            b.add("图片加载失败", "7.24", level="element", element=element, action={"type": "none"},
                  expected="加载失败时有占位或兜底样式，不出现碎图撑破布局", source="page-inventory")

    if "dropdown" in kinds:
        b.add("下拉展开-选择-收起", "7.18", action={"type": "click"},
              expected="下拉跟随触发元素、不被裁切、收起后无残留遮罩",
              assertions=["展开后浮层在视口内", "收起后浮层不可见且无遮挡"], safety="caution", source="dimension")
    if "tooltip" in kinds:
        b.add("Tooltip 位置与视口", "7.18", action={"type": "hover"},
              expected="Tooltip 出现在视口内且不遮挡关键操作", source="dimension")
    if "table" in kinds:
        b.add("表格列宽与长内容", "7.21", expected="长内容下不撑破列宽、不出现横向溢出", source="page-inventory")
    if "upload" in kinds:
        b.add("上传控件与文件校验", "7.17", action={"type": "upload"},
              expected="格式/大小限制有明确提示，失败可恢复", safety="caution", source="dimension")

    unmatched = pairs.get("unmatched") or {}
    for node in (unmatched.get("designOnly") or [])[: args.max_elements]:
        b.add("设计稿有页面无：{}".format(node.get("name")), "7.23", level="element",
              element={"selector": "", "nth": 0, "anchor": node.get("name"), "bbox": bbox_of(node)},
              action={"type": "none"}, expected="确认该元素是否遗漏或实现为其他形式", source="design-inventory")
    for item in (unmatched.get("pageOnly") or [])[: args.max_elements]:
        b.add("页面有设计稿无：{}".format(item.get("text") or item.get("selector")), "7.23", level="element",
              element={"selector": item.get("selector"), "nth": 0, "anchor": item.get("text"), "bbox": {}},
              action={"type": "none"}, expected="确认是否设计遗漏或遗留调试入口", source="page-inventory")

    for role in roles:
        b.add("角色态视图：{}".format(role), "7.34", action={"type": "role", "value": role},
              expected="该角色可见/可操作项与设计一致，无越权入口", source="role")

    return {
        "version": "2.0",
        "page": page_url,
        "comboDepth": combo,
        "breakpoints": bps,
        "generatedFrom": {
            "design": str(args.design) if args.design else None,
            "page": str(args.page) if args.page else None,
            "pairs": str(args.pairs) if args.pairs else None,
            "patterns": str(getattr(args, "patterns", "") or "") or None,
        },
        "patternFeedback": {
            "applied": bool(weights),
            "pool": str(getattr(args, "patterns", "") or "") or None,
            "weights": {d: weights[d] for d in sorted(weights, key=lambda x: -weights[x])[:10]},
            "hotDimensions": sorted(hot),
            "deepened": deepened,
            "note": "历史缺陷模式只影响「哪些维度必被覆盖」与「异常数据深度」，"
                    "不自动生成断言——从一条历史缺陷推不出修复后的正确行为。"
                    "场景顺序不变（保持 S-xxxx 编号稳定，便于与已确认基线/人工引用对照）。"
                    if weights else "未接入缺陷模式池（--patterns），输出与接入前完全一致。",
        },
        "inputStats": {"buttons": len(buttons), "inputs": len(inputs), "images": len(images),
                       "overlays": len(overlays), "interactionKinds": sorted(kinds), "roles": roles},
        "dimensions": sorted(b.dimensions),
        "truncation": {"dropped": sum(b.dropped.values()), "byDimension": b.dropped,
                       "note": "达到 --max-scenarios 上限被丢弃的场景按维度计数，报告中必须写明" if b.dropped else None},
        "scenarios": b.items,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="生成元素级 UI 检查场景矩阵")
    ap.add_argument("--design", type=Path, help="extract_design_fields.py 产物")
    ap.add_argument("--page", type=Path, help="collect_page_inventory.js 产物")
    ap.add_argument("--pairs", type=Path, help="compare_fields.py 产物（驱动 7.23）")
    ap.add_argument("--page-url", default=None)
    ap.add_argument("--roles", default=None, help="逗号分隔的角色名，如 admin,member")
    ap.add_argument("--max-elements", type=int, default=60, help="每类元素最多生成多少条元素级场景")
    ap.add_argument("--max-data-cases", type=int, default=6, help="每个输入框最多生成多少条异常数据场景")
    ap.add_argument("--max-scenarios", type=int, default=300)
    ap.add_argument("--combo-depth", type=int, default=1,
                    help="组合深度：1=单点（默认，输出与不放宽时一致）；2=加深异常数据条数与逐断点展开")
    ap.add_argument("--patterns", default=None,
                    help="缺陷模式池 JSON（assets/defect_patterns.json）：历史高频翻车的维度必被覆盖并加深异常数据；不传则场景清单与接入前一致（产物 patternFeedback 字段恒在，未接入时 applied=false）")
    ap.add_argument("--breakpoints", default="1440,1280,768,375", help="组合用的断点，逗号分隔")
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    if not args.design and not args.page:
        print("至少需要 --design 或 --page 之一，否则只能产出泛化场景", file=sys.stderr)
        return 2
    result = build(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scenarios": len(result["scenarios"]), "dimensions": result["dimensions"],
                      "inputStats": result["inputStats"], "output": str(args.output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
