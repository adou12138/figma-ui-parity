#!/usr/bin/env python3
"""Compare a normalized design model against page extraction output.

Pairing order: explicit mapping file -> exact text anchor -> name hint ->
second-chance (unmatched box nodes may pair with unused text-bearing page
items, marked pairRole). Design TEXT nodes pair only with text-bearing page
items; a box node whose TEXT child got paired is credited via that child and
is not reported as designOnly.

Every emitted diff carries a dimension code (7.x), both values (stringified),
the applied tolerance, a fingerprint, severity and confidence, so downstream
dedupe can merge findings from the pixel layer, the style layer and the
checklist layer, and validate_defects accepts them as-is.

Offline only.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

# 属性级容差表：只有超出容差才成为差异，避免把渲染舍入误差报成缺陷。
TOLERANCE = {
    "position_px": 2.0,
    "dimension_px": 1.0,
    "spacing_px": 1.0,
    "radius_px": 1.0,
    "border_px": 0.5,
    "font_size_px": 0.5,
    "line_height_px": 1.0,
    "letter_spacing_px": 0.5,
    "shadow_blur_px": 2.0,
    "shadow_offset_px": 1.0,
    "color_delta_e": 3.0,
    "opacity": 0.02,
    "font_weight": 0.0,
}

DIMENSION = {
    "rect": "7.1", "position": "7.1", "spacing": "7.1", "padding": "7.1",
    "gap": "7.1", "layout": "7.1",
    "color": "7.1", "background": "7.1", "border": "7.1", "radius": "7.1",
    "shadow": "7.1", "opacity": "7.1", "gradient": "7.1",
    "font": "7.1", "text": "7.1", "line_height": "7.1", "letter_spacing": "7.1",
    "icon": "7.5", "image": "7.24", "visible": "7.16",
}

# 与 defect.schema.json 的 severity 枚举对齐：产出端直接给 severity，
# 不再依赖下游把 severityHint 二次映射。
HIGH_RISK_CATEGORIES = ("rect", "color", "visible", "text")
SEVERITY = {c: "P1" for c in HIGH_RISK_CATEGORIES}
SEVERITY_DEFAULT = "P2"
CONFIDENCE = 0.8

# 自动归一的最小配对数：少于此数时中位偏移不可信，宁可保留 raw 让人工复核。
MIN_PAIRS_FOR_NORMALIZE = 3


def to_lab(rgb: list) -> tuple:
    def inv(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (inv(v) for v in rgb[:3])
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = (r * 0.2126 + g * 0.7152 + b * 0.0722) / 1.0
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883
    def f(t):
        return t ** (1 / 3) if t > 0.008856 else (7.787 * t) + (16 / 116)
    fx, fy, fz = f(x), f(y), f(z)
    return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))


def delta_e(rgb_a: list, rgb_b: list) -> float:
    la, lb = to_lab(rgb_a), to_lab(rgb_b)
    return round2(((la[0] - lb[0]) ** 2 + (la[1] - lb[1]) ** 2 + (la[2] - lb[2]) ** 2) ** 0.5)


def round2(value: float) -> float:
    try:
        return round(float(value) + 0.0, 2)
    except (TypeError, ValueError):
        return 0.0


def fmt_val(value) -> str:
    """schema 要求 expected/actual 为 string：数值取整、rgb 列表转 css 记法。"""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return str(round2(value))
    if isinstance(value, (list, tuple)):
        if len(value) == 3 and all(isinstance(v, (int, float)) for v in value):
            return "rgb({},{},{})".format(*[int(v) for v in value])
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def parse_px(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if text in ("normal", "auto", ""):
        return 0.0 if text != "normal" else None
    if text.endswith("px"):
        return float(text[:-2])
    if text.endswith("em"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_rgb(value) -> list | None:
    """Return [r,g,b] or None. Fully transparent colors return None.

    `rgba(0,0,0,0)` (transparent background) must NOT be treated as black —
    doing so turns every element whose background is transparent into a
    false "color mismatch".
    """
    rgb, alpha = None, 1.0
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        rgb = [int(v) for v in value[:3]]
    elif isinstance(value, str):
        text = value.strip()
        if text.startswith("#") and len(text) >= 7:
            rgb = [int(text[i:i + 2], 16) for i in (1, 3, 5)]
            if len(text) == 9:
                alpha = int(text[7:9], 16) / 255.0
        elif text.startswith("rgb"):
            body = text[text.find("(") + 1:text.rfind(")")]
            parts = [p.strip() for p in body.split(",")]
            try:
                rgb = [int(round(float(p))) for p in parts[:3]]
            except ValueError:
                return None
            if len(parts) >= 4:
                try:
                    alpha = float(parts[3])
                except ValueError:
                    alpha = 1.0
    if rgb is None:
        return None
    if alpha <= 0.05:
        return None
    return rgb


def design_color(node: dict) -> dict | None:
    """首个可见 SOLID 填充，返回 {rgb, alpha}；无填充返回 None。

    alpha<=0.05 与页面侧口径一致（透明不比对）；alpha<0.9 的半透明填充，
    页面渲染色依赖其下方的合成背景，直接比 rgb 会产生假差异，由调用方跳过。
    """
    fills = node.get("fills") or []
    for f in fills:
        if f.get("type") == "SOLID" and isinstance(f.get("color"), dict):
            rgb = f["color"].get("rgb")
            if not rgb:
                continue
            alpha = float(f["color"].get("alpha", 1))
            if alpha <= 0.05:
                return None
            return {"rgb": [int(v) for v in rgb[:3]], "alpha": alpha}
    return None


def page_color(item: dict, is_text: bool) -> list | None:
    """文本节点比对文字色，其余节点比对背景色；透明背景返回 None 不参与比对。"""
    if is_text:
        return parse_rgb(item.get("color")) or parse_rgb(item.get("backgroundColor"))
    return parse_rgb(item.get("backgroundColor")) or parse_rgb(item.get("color"))


def normalize_page(page: dict) -> list:
    items = []
    for key in ("containers", "texts", "icons", "buttons", "inputs", "images"):
        value = page.get(key)
        if isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict):
                    entry = dict(entry)
                    entry["_kind"] = key[:-1] if key.endswith("s") else key
                    items.append(entry)
    if isinstance(page.get("items"), list):
        for entry in page["items"]:
            if isinstance(entry, dict):
                items.append(dict(entry))
    return items


def index_page(items: list) -> dict:
    by_selector, by_text, text_items, box_items = {}, {}, [], []
    for item in items:
        selector = item.get("sel") or item.get("selector")
        if selector:
            by_selector.setdefault(str(selector), []).append(item)
        text = (item.get("text") or item.get("characters") or "").strip()
        if text:
            by_text.setdefault(text, []).append(item)
            text_items.append(item)
        else:
            box_items.append(item)
    return {"bySelector": by_selector, "byText": by_text, "textItems": text_items, "boxItems": box_items}


def build_parent_map(tree: dict) -> dict:
    """child nodeId -> parent nodeId，用于把「文本子节点已配对」credit 给父容器。"""
    parents = {}

    def walk(node, parent_id):
        for child in node.get("children") or []:
            cid = str(child.get("id") or "")
            parents[cid] = str(node.get("id") or "")
            walk(child, node.get("id"))

    if isinstance(tree, dict):
        walk(tree, None)
    return parents


def match(design_nodes: list, items: list, mapping: dict, parent_of: dict | None = None) -> tuple:
    """Pair design nodes with page items.

    Order: explicit mapping -> exact text anchor -> name hint (pool-restricted)
    -> second chance (unmatched non-text design nodes may pair with unused
    text-bearing page items, marked pairRole="box-to-text-item").

    Text nodes only pair with text-bearing page items in the main pass, so a
    text node never gets paired to a container that merely shares its class
    name; the second chance exists so a design FRAME (e.g. a button whose
    text lives in a child node) is not falsely reported as designOnly.
    """
    parent_of = parent_of or {}
    index = index_page(items)
    used, pairs, unmatched = set(), [], []

    def take(node, target, pair_role=None):
        used.add(id(target))
        record = {"node": node, "item": target}
        if pair_role:
            record["pairRole"] = pair_role
        pairs.append(record)

    for node in design_nodes:
        node_id = str(node.get("id") or "")
        is_text = bool(node.get("text"))
        pool = index["textItems"] if is_text else index["boxItems"]
        target = None
        entry = mapping.get(node_id)
        if isinstance(entry, dict):
            selector = entry.get("selector")
            nth = int(entry.get("nth", 0) or 0)
            candidates = index["bySelector"].get(str(selector), [])
            if nth < len(candidates):
                target = candidates[nth]
        if target is None:
            text = ((node.get("text") or {}).get("characters") or "").strip()
            if text and index["byText"].get(text):
                for candidate in index["byText"][text]:
                    if id(candidate) not in used:
                        target = candidate
                        break
        if target is None:
            name = str(node.get("name") or "").strip().lower()
            if name:
                for item in pool:
                    if id(item) in used:
                        continue
                    selector = str(item.get("sel") or item.get("selector") or "").lower()
                    if name and name in selector:
                        target = item
                        break
        if target is None:
            unmatched.append(node)
            continue
        take(node, target)

    # 第二次机会：未配对的非文本设计节点（按钮 frame 等）允许与仍未被占用的
    # 带文本页面项配对，避免被误报为「设计稿有页面无」。
    still_unmatched = []
    for node in unmatched:
        if node.get("text"):
            still_unmatched.append(node)
            continue
        name = str(node.get("name") or "").strip().lower()
        target = None
        if name:
            for item in index["textItems"]:
                if id(item) in used:
                    continue
                selector = str(item.get("sel") or item.get("selector") or "").lower()
                if name and name in selector:
                    target = item
                    break
        if target is None:
            still_unmatched.append(node)
        else:
            take(node, target, pair_role="box-to-text-item")
    unmatched = still_unmatched

    # 父节点 credit：设计文本子节点配对成功时，其直接父容器（按钮 frame 等）
    # 不再假报 designOnly——页面元素已被该文本占用，父容器本身没有独立落点。
    matched_indirect = []
    if parent_of:
        paired_ids = {str(rec["node"].get("id") or "") for rec in pairs}
        credited_parents = {parent_of[pid] for pid in paired_ids if parent_of.get(pid)}
        kept = []
        for node in unmatched:
            if str(node.get("id") or "") in credited_parents and not node.get("text"):
                matched_indirect.append(node)
            else:
                kept.append(node)
        unmatched = kept

    unmatched_page = [i for i in items if id(i) not in used]
    return pairs, unmatched, unmatched_page, matched_indirect


def _first_px(text):
    """从 CSS 值里取第一个 px 数值（'4px' → 4.0）；取不到返回 None。"""
    if text is None:
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)px", str(text))
    return float(m.group(1)) if m else None


def _num(value):
    """宽松数值解析：数值直通、字符串转 float，失败返回 None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _design_radius(node):
    """设计侧圆角：corners（独立四角）优先取 max，再回落 uniform。

    【F15 反死代码】旧判定顺序 uniform 在前——extract_design_fields 的 uniform
    恒存在（缺省 0.0），corners 分支是死代码：设计用独立四角圆角（卡片/半屏弹层
    极常见）时设计侧恒 0、页面侧取 8 → confirmed 圆角假缺陷且淹没真缺陷。
    （extract_design_fields 现已改为直接产出生效圆角标量，本函数对旧格式产物
    兼容：corners 优先，uniform 真为数值且无 corners 才用。）"""
    r = node.get("radius")
    if not isinstance(r, dict):
        return None
    corners = r.get("corners")
    if isinstance(corners, list):
        nums = [c for c in corners if isinstance(c, (int, float))]
        if nums:
            return float(max(nums))
    if isinstance(r.get("uniform"), (int, float)):
        return float(r["uniform"])
    return None


def _page_radius(item):
    """页面侧圆角：borderRadius，或四个分角取 max。"""
    v = _first_px(item.get("borderRadius"))
    if v is not None:
        return v
    corners = [_first_px(item.get(k)) for k in
               ("borderTopLeftRadius", "borderTopRightRadius",
                "borderBottomLeftRadius", "borderBottomRightRadius")]
    nums = [c for c in corners if c is not None]
    return float(max(nums)) if nums else None


def _shadow_blur_offset(text):
    """CSS boxShadow → (blur, offset 长度)。多阴影取第一个，解析不到返回 None。"""
    if not text or str(text).strip().lower() in ("none", ""):
        return None
    m = re.search(r"(-?\d+(?:\.\d+)?)px\s+(-?\d+(?:\.\d+)?)px\s+(-?\d+(?:\.\d+)?)px", str(text))
    if not m:
        return None
    ox, oy, blur = float(m.group(1)), float(m.group(2)), float(m.group(3))
    return blur, (ox * ox + oy * oy) ** 0.5


def _font_weight(value):
    """fontWeight 归一为数值：'bold'→700、'normal'→400。"""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    s = str(value).strip().lower()
    if s == "bold":
        return 700.0
    if s in ("normal", "lighter", ""):
        return 400.0
    return _num(s)


def compare_pair(node, item, page_url, scenario, viewport, offsets=(0.0, 0.0), comparable=True,
                 incomparable_reason=None, color_skips=None) -> list:
    diffs = []
    element = {
        "selector": item.get("sel") or item.get("selector"),
        "nth": item.get("nth", 0),
        "bbox": item.get("rect") or item.get("bbox") or {},
        "anchor": item.get("anchor") or item.get("text") or node.get("name"),
        "frame": item.get("_kind") or "main",
    }
    anchor = element.get("anchor") or element.get("selector") or node.get("name")
    pair_rect = item.get("rect") or item.get("bbox") or {}

    # 【F14】视口/帧宽不一致只让**几何类**比对不可比（位置/尺寸/间距随缩放整体漂移，
    # 比对无意义）；颜色/文案/字号/字重等**样式类**不受视口宽度影响——
    # 旧版 comparable 是全局开关，移动端 375 对 1440 帧时连「文案写错」「主色错成蓝」
    # 都报 notComparable，整页假通过。拆成两个口径：
    STYLE_ONLY_CATEGORIES = {"color", "characters", "font", "radius", "border",
                             "shadow", "opacity"}

    def emit(category, prop, expected, actual, delta, tolerance_key, dimension=None) -> None:
        tol = TOLERANCE.get(tolerance_key)
        exceeded = delta > tol if tol is not None else True
        # 几何类受视口比例影响；样式类恒可比
        item_comparable = comparable or str(category) in STYLE_ONLY_CATEGORIES
        status = "confirmed" if (exceeded and item_comparable) else ("notComparable" if not item_comparable else "withinTolerance")
        severity = SEVERITY.get(category, SEVERITY_DEFAULT)
        diffs.append({
            "page": page_url,
            "scenario": scenario,
            "viewport": viewport,
            "category": "{}|{}".format(dimension or DIMENSION.get(category, "7.1"), category),
            "dimension": dimension or DIMENSION.get(category, "7.1"),
            "property": prop,
            "expected": fmt_val(expected),
            "actual": fmt_val(actual),
            "delta": round2(delta),
            "tolerance": tol,
            "status": status,
            "notComparableReason": (incomparable_reason
                                    if not item_comparable and incomparable_reason else None),
            "severity": severity,
            "confidence": CONFIDENCE,
            "reproduction": [
                "打开 {} 并定位元素 {}".format(page_url or "页面", anchor),
                "对照设计节点 {}（{}）的 {}".format(node.get("name"), node.get("id"), prop),
            ],
            "suggestion": "将 {} 修正为设计值 {}（当前 {}，容差 {}）".format(
                prop, fmt_val(expected), fmt_val(actual), tol if tol is not None else "按设计"),
            "symptom": "{} 与设计不一致（设计 {}，实际 {}）".format(prop, fmt_val(expected), fmt_val(actual)),
            "element": element,
            "designRef": {"nodeId": node.get("id"), "path": node.get("name")},
            "evidence": [{"type": "computed-style", "result": "mismatch", "property": prop}],
            "sources": ["computed-style"],
            "fingerprint": "{}|{}|{}|{}|{}".format(
                page_url, scenario, element.get("selector"), "{}|{}".format(dimension or DIMENSION.get(category, "7.1"), category), viewport),
        })

    rect_d = node.get("rect") or {}
    dx, dy = offsets
    rect_p = {
        "w": pair_rect.get("w"), "h": pair_rect.get("h"),
        "x": (pair_rect.get("x") - dx) if isinstance(pair_rect.get("x"), (int, float)) else None,
        "y": (pair_rect.get("y") - dy) if isinstance(pair_rect.get("y"), (int, float)) else None,
    }
    # 旋转节点的 absoluteBoundingBox 是旋转后外接框，w/h/x/y 不可直接比。
    rotation = node.get("rotation") or 0
    if isinstance(rotation, (int, float)) and abs(rotation) > 0.01:
        if color_skips is not None:
            color_skips.append({
                "kind": "rotated-rect", "nodeId": node.get("id"), "name": node.get("name"),
                "reason": "rotation={} 非零，外接框尺寸与位置不可直接比对，转人工确认".format(round2(rotation)),
            })
    else:
        for key, tol_key in (("w", "dimension_px"), ("h", "dimension_px"), ("x", "position_px"), ("y", "position_px")):
            dv, pv = rect_d.get(key), rect_p.get(key)
            if isinstance(dv, (int, float)) and isinstance(pv, (int, float)) and (dv or pv):
                emit("rect" if key in ("w", "h") else "position", key, round2(dv), round2(pv), abs(dv - pv), tol_key)

    d_color, p_color = design_color(node), page_color(item, bool(node.get("text")))
    if d_color and d_color["alpha"] < 0.9:
        if color_skips is not None:
            color_skips.append({
                "kind": "low-alpha-fill", "nodeId": node.get("id"), "name": node.get("name"),
                "alpha": d_color["alpha"],
                "reason": "设计填充 alpha={}，页面渲染色依赖下方背景合成，不直接比对 rgb".format(d_color["alpha"]),
            })
    elif d_color and p_color:
        distance = delta_e(d_color["rgb"], p_color)
        emit("color", "color", d_color["rgb"], p_color, distance, "color_delta_e")

    d_text, p_text = node.get("text") or {}, item
    for prop, design_val, page_val, tol_key in (
        ("fontSize", d_text.get("fontSize"), parse_px(p_text.get("fontSize")), "font_size_px"),
        ("lineHeight", (d_text.get("lineHeight") or {}).get("px"), parse_px(p_text.get("lineHeight")), "line_height_px"),
        ("letterSpacing", (d_text.get("letterSpacing") or {}).get("px"), parse_px(p_text.get("letterSpacing")), "letter_spacing_px"),
    ):
        if isinstance(design_val, (int, float)) and isinstance(page_val, (int, float)) and (design_val or page_val):
            emit("font" if prop == "fontSize" else prop.lower(), prop, round2(design_val), round2(page_val), abs(design_val - page_val), tol_key)

    # —— 盒模型 / 阴影 / 透明度补充断言 ——
    # TOLERANCE 与 DIMENSION 早就声明了 radius_px / border_px / shadow_* / opacity，
    # 但此前没有任何发射路径 → 圆角 4→2px、边框粗细变化这类历史高发缺陷只能靠像素 diff
    # 碰运气。这里按同一 emit() 模式补上。
    # **纪律**：只在设计侧与页面侧**都取到值**时才比对；设计侧没画那层样式就不 emit，
    # 不得把「设计稿没定义」判成缺陷。
    d_radius, p_radius = _design_radius(node), _page_radius(item)
    if d_radius is not None and p_radius is not None:
        emit("radius", "borderRadius", round2(d_radius), round2(p_radius),
             abs(d_radius - p_radius), "radius_px")

    d_weight = (node.get("text") or {}).get("fontWeight")
    p_weight = _font_weight(item.get("fontWeight"))
    if d_weight is not None and p_weight is not None:
        emit("font", "fontWeight", round2(d_weight), round2(p_weight),
             abs(d_weight - p_weight), "font_weight")

    d_strokes = node.get("strokes")
    p_border = _first_px(item.get("border"))
    if isinstance(d_strokes, list) and d_strokes and p_border is not None:
        s0 = d_strokes[0] if isinstance(d_strokes[0], dict) else {}
        d_bw = _num(s0.get("strokeWeight", s0.get("weight")))
        if d_bw is not None:
            emit("border", "borderWidth", round2(d_bw), round2(p_border),
                 abs(d_bw - p_border), "border_px")

    d_effects = node.get("effects")
    p_shadow = _shadow_blur_offset(item.get("boxShadow"))
    if isinstance(d_effects, list) and d_effects and p_shadow is not None:
        e0 = d_effects[0] if isinstance(d_effects[0], dict) else {}
        d_blur = _num(e0.get("radius"))
        if d_blur is not None:
            emit("shadow", "boxShadowBlur", round2(d_blur), round2(p_shadow[0]),
                 abs(d_blur - p_shadow[0]), "shadow_blur_px")

    d_op = _num(node.get("opacity"))
    p_op = _num(item.get("opacity"))
    if d_op is not None and p_op is not None:
        emit("opacity", "opacity", round2(d_op), round2(p_op),
             abs(d_op - p_op), "opacity")

    if d_text.get("characters") and (p_text.get("text") or "").strip():
        if d_text["characters"].strip() != (p_text.get("text") or "").strip():
            # 【F14】文案比对不受视口宽度影响——恒可比
            diffs.append({
                "page": page_url, "scenario": scenario, "viewport": viewport,
                "category": "7.8|text", "dimension": "7.8", "property": "characters",
                "expected": fmt_val(d_text["characters"]), "actual": fmt_val(p_text.get("text")),
                "delta": None, "tolerance": None,
                "status": "confirmed",
                "notComparableReason": None,
                "severity": "P1", "confidence": 0.9,
                "reproduction": [
                    "打开 {} 并定位元素 {}".format(page_url or "页面", anchor),
                    "对照设计节点 {}（{}）的文案".format(node.get("name"), node.get("id")),
                ],
                "suggestion": "将文案改为设计稿「{}」".format(d_text["characters"]),
                "symptom": "文案与设计不一致（设计「{}」，实际「{}」）".format(d_text["characters"], p_text.get("text")),
                "element": element, "designRef": {"nodeId": node.get("id"), "path": node.get("name")},
                "evidence": [{"type": "computed-style", "result": "mismatch", "property": "characters"}],
                "sources": ["computed-style"],
                "fingerprint": "{}|{}|{}|7.8|text|{}".format(page_url, scenario, element.get("selector"), viewport),
            })

    return diffs


def main() -> int:
    ap = argparse.ArgumentParser(description="设计模型 vs 页面提取逐字段比对（含属性级容差）")
    ap.add_argument("--design", required=True, type=Path, help="extract_design_fields.py 的产物")
    ap.add_argument("--page", required=True, type=Path, help="页面提取产物（containers/texts/... 或 items）")
    ap.add_argument("--mapping", type=Path, default=None, help="nodeId -> {selector, nth} 映射文件")
    ap.add_argument("--frame-origin", default=None, help="页面侧 frame 原点，格式 x,y；缺省时用配对元素的中位偏移自动归一")
    ap.add_argument("--page-url", default="")
    ap.add_argument("--scenario", default="default")
    ap.add_argument("--viewport", default="1440")
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    design = json.loads(args.design.read_text(encoding="utf-8"))
    page = json.loads(args.page.read_text(encoding="utf-8"))
    mapping = json.loads(args.mapping.read_text(encoding="utf-8")) if args.mapping and args.mapping.exists() else {}
    for key in ("pairs", "mapping", "items"):
        if isinstance(mapping.get(key), list):
            mapping = {str(p.get("nodeId") or p.get("node")): p for p in mapping[key] if isinstance(p, dict)}
            break

    nodes = design.get("flat") or ([design["tree"]] if design.get("tree") else [])
    nodes = [n for n in nodes if n.get("visible", True)]
    items = normalize_page(page)
    parent_of = build_parent_map(design.get("tree") or {})
    pairs, unmatched_design, unmatched_page, matched_indirect = match(nodes, items, mapping, parent_of)

    # 坐标基准：设计稿坐标相对 frame 原点，页面坐标相对文档原点。
    # 直接相减会把整体偏移报成每元素的位移缺陷，因此先求基准偏移再比对。
    frame_w = ((design.get("frame") or {}).get("w")) or 0
    viewport_w = ((page.get("viewport") or {}).get("w")) or 0
    scale = (viewport_w / frame_w) if (frame_w and viewport_w) else 1.0
    comparable = abs(scale - 1.0) <= 0.02
    incomparable_reason = None if comparable else "页面视口宽 {} 与设计稿宽 {} 不一致（比例 {:.2f}），尺寸与位置不可直接比对".format(
        viewport_w, frame_w, scale)

    probe = []
    for rec in pairs:
        node, item = rec["node"], rec["item"]
        rect_d, rect_p = node.get("rect") or {}, item.get("rect") or item.get("bbox") or {}
        if all(isinstance(v, (int, float)) for v in (rect_d.get("x"), rect_d.get("y"), rect_p.get("x"), rect_p.get("y"))):
            probe.append((rect_p["x"] - rect_d["x"], rect_p["y"] - rect_d["y"]))
    basis_warnings = []
    if args.frame_origin:
        parts = [float(p) for p in str(args.frame_origin).split(",")[:2]]
        offsets = (parts[0], parts[1] if len(parts) > 1 else 0.0)
        position_basis = "explicit-frame-origin"
    elif len(probe) >= MIN_PAIRS_FOR_NORMALIZE:
        xs = sorted(p[0] for p in probe)
        ys = sorted(p[1] for p in probe)
        # 【F20】真中位数：偶数个样本取中间两值均值（旧版 xs[len//2] 在偶数时偏右，
        # 少数错配对会污染基准）。
        def _median(sorted_vals):
            n = len(sorted_vals)
            mid = n // 2
            if n % 2 == 1:
                return float(sorted_vals[mid])
            return (float(sorted_vals[mid - 1]) + float(sorted_vals[mid])) / 2.0
        offsets = (_median(xs), _median(ys))
        position_basis = "auto-normalized-median"
    elif len(probe) >= 1:
        offsets = (0.0, 0.0)
        position_basis = "raw-insufficient-pairs"
        basis_warnings.append(
            "配对数 {} < {}，中位偏移不可信，位置差异未做归一（保留原始坐标差），需人工复核".format(len(probe), MIN_PAIRS_FOR_NORMALIZE))
    else:
        offsets = (0.0, 0.0)
        position_basis = "raw"

    # 归一偏移幅值告警：中位归一无法区分「frame 原点差」与「整页真实偏移」，
    # 偏移过大时大概率是真缺陷被归一，必须提示人工确认而不是静默抑制。
    if position_basis == "auto-normalized-median":
        warn_threshold = max(24.0, frame_w * 0.05) if frame_w else 24.0
        if abs(offsets[0]) > warn_threshold or abs(offsets[1]) > warn_threshold:
            basis_warnings.append(
                "归一偏移 dx={} dy={} 超过告警阈值 {}：可能是整页真实偏移（真缺陷）而非 frame 原点差，请用 --frame-origin 显式确认基准".format(
                    round2(offsets[0]), round2(offsets[1]), round2(warn_threshold)))

    diffs = []
    color_skips: list = []
    for rec in pairs:
        diffs.extend(compare_pair(rec["node"], rec["item"], args.page_url, args.scenario, args.viewport,
                                  offsets=offsets, comparable=comparable, incomparable_reason=incomparable_reason,
                                  color_skips=color_skips))
    real = [d for d in diffs if d["status"] == "confirmed"]

    result = {
        "page": args.page_url, "scenario": args.scenario, "viewport": args.viewport,
        "positionBasis": position_basis,
        "positionBasisWarning": basis_warnings,
        "offsets": {"dx": round2(offsets[0]), "dy": round2(offsets[1])},
        "scale": {"pageViewportWidth": viewport_w, "designFrameWidth": frame_w, "ratio": round2(scale)},
        "comparability": {"comparable": comparable, "reason": incomparable_reason},
        "summary": {
            "designNodes": len(nodes), "pageItems": len(items), "paired": len(pairs),
            "diffCount": len(real), "withinTolerance": len([d for d in diffs if d["status"] == "withinTolerance"]),
            "notComparable": len([d for d in diffs if d["status"] == "notComparable"]),
            "unmatchedDesign": len(unmatched_design), "unmatchedPage": len(unmatched_page),
            "matchedIndirect": len(matched_indirect),
            "pairRoles": {role: len([r for r in pairs if r.get("pairRole") == role])
                          for role in {r.get("pairRole") for r in pairs if r.get("pairRole")}},
            "colorCompareSkipped": len(color_skips),
        },
        "styleDiffs": diffs,
        "defects": real,
        "unmatched": {
            "designOnly": [{"nodeId": n.get("id"), "name": n.get("name"), "rect": n.get("rect")} for n in unmatched_design],
            "pageOnly": [{"selector": i.get("sel") or i.get("selector"), "text": i.get("text"), "kind": i.get("_kind")} for i in unmatched_page],
        },
        "matchedIndirect": [{"nodeId": n.get("id"), "name": n.get("name"), "matchedVia": "text-child-pair"}
                            for n in matched_indirect],
        "colorCompareSkipped": color_skips,
        "tolerance": TOLERANCE,
        "note": "unmatched.designOnly 与 unmatched.pageOnly 是双向盘点输入，需按 7.23 判定后转为缺陷或忽略",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    if basis_warnings:
        for w in basis_warnings:
            print("警告：{}".format(w), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
