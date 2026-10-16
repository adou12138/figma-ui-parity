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


def _hsl_to_rgb(h, s, l):
    """HSL(0-360, 0-1, 0-1) → [r,g,b]（0-255）。标准 CSS 转换公式。"""
    h = (float(h) % 360.0) / 360.0
    s = max(0.0, min(1.0, float(s)))
    l = max(0.0, min(1.0, float(l)))
    if s == 0:
        v = int(round(l * 255))
        return [v, v, v]
    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q

    def channel(t):
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1.0 / 6:
            return p + (q - p) * 6 * t
        if t < 1.0 / 2:
            return q
        if t < 2.0 / 3:
            return p + (q - p) * (2.0 / 3 - t) * 6
        return p

    return [int(round(channel(h + 1.0 / 3) * 255)),
            int(round(channel(h) * 255)),
            int(round(channel(h - 1.0 / 3) * 255))]


def _num_or_pct(token, scale=255.0):
    """`50%` → 50%*scale；`0.5` → 0.5。"""
    token = token.strip()
    if token.endswith("%"):
        return float(token[:-1]) / 100.0 * scale
    return float(token)


# 解析失败的颜色原文（去重、限量）。留痕用：颜色静默跳过比对曾是漏测来源
# （F19），不解析出值又不记录的话，读报告的人无从知道有哪些颜色没比过。
_UNPARSED_COLORS: list = []
_COLOR_SYNTAX = re.compile(r"^\s*(#[0-9a-fA-F]+|rgba?\s*\(|hsla?\s*\(|color\s*\()")


def parse_rgb(value) -> list | None:
    """Return [r,g,b] or None. Fully transparent colors return None.

    `rgba(0,0,0,0)` (transparent background) must NOT be treated as black —
    doing so turns every element whose background is transparent into a
    false "color mismatch".

    【F19】支持全部常见 CSS 颜色写法：`#rgb` / `#rgba` / `#rrggbb` / `#rrggbbaa`、
    `rgb()/rgba()` 的逗号与空格两种分隔、`/ alpha` 斜杠 alpha、百分比分量，
    以及 `hsl()/hsla()`。此前只认 `#rrggbb(aa)` 与逗号式 `rgb()`——移动端浏览器
    实测常返回 `rgb(255 0 0 / 50%)` 与 `#abc`，这些颜色被静默跳过比对（漏测）。
    仍无法解析且形似颜色时记入 `_UNPARSED_COLORS`（报告 parseWarnings 透出）。
    """
    rgb, alpha = None, 1.0
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        rgb = [int(v) for v in value[:3]]
    elif isinstance(value, str):
        text = value.strip()
        low = text.lower()
        if low.startswith("#"):
            body = text[1:]
            if len(body) in (3, 4):                      # #abc / #abcd
                rgb = [int(c * 2, 16) for c in body[:3]]
                if len(body) == 4:
                    alpha = int(body[3] * 2, 16) / 255.0
            elif len(body) in (6, 8):                    # #rrggbb / #rrggbbaa
                rgb = [int(body[i:i + 2], 16) for i in (0, 2, 4)]
                if len(body) == 8:
                    alpha = int(body[6:8], 16) / 255.0
        elif low.startswith("rgb"):
            body = text[text.find("(") + 1:text.rfind(")")]
            if "/" in body:                              # rgb(255 0 0 / 50%)
                body, slash_alpha = body.split("/", 1)
                try:
                    alpha = _num_or_pct(slash_alpha, 1.0)
                except ValueError:
                    alpha = 1.0
            parts = [p for p in re.split(r"[,\s]+", body.strip()) if p]
            try:
                rgb = [int(round(_num_or_pct(p))) for p in parts[:3]]
            except ValueError:
                rgb = None
            else:
                # 分量不足 3 个（rgb() / rgb(1)）不得返回 []/[1]——下游 delta_e 会
                # 按 3 元素解包，直接 ValueError；且 [] 在 `or` 链里 falsy 会静默跳过。
                if len(rgb) != 3:
                    rgb = None
                if len(parts) >= 4:                      # rgba(..., 0.5) / rgba(... 0.5)
                    try:
                        alpha = _num_or_pct(parts[3], 1.0)
                    except ValueError:
                        alpha = 1.0
        elif low.startswith("hsl"):
            body = text[text.find("(") + 1:text.rfind(")")]
            if "/" in body:
                body, slash_alpha = body.split("/", 1)
                try:
                    alpha = _num_or_pct(slash_alpha, 1.0)
                except ValueError:
                    alpha = 1.0
            parts = [p for p in re.split(r"[,\s]+", body.strip()) if p]
            try:
                if len(parts) < 3:
                    raise ValueError("hsl 分量不足 3 个")
                h = float(parts[0].rstrip("deg"))
                s = float(parts[1].rstrip("%")) / 100.0
                l = float(parts[2].rstrip("%")) / 100.0
                rgb = _hsl_to_rgb(h, s, l)
            except (ValueError, IndexError):
                rgb = None
            else:
                if len(parts) >= 4:
                    try:
                        alpha = _num_or_pct(parts[3], 1.0)
                    except ValueError:
                        alpha = 1.0
        if rgb is None and _COLOR_SYNTAX.match(text):
            if text not in _UNPARSED_COLORS and len(_UNPARSED_COLORS) < 50:
                _UNPARSED_COLORS.append(text)
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


def _name_segment_hit(name, selector):
    """设计节点名与页面选择器的**词段**级比对，返回 'segment' / 'substring' / None。

    【F17】旧实现是裸子串 `name in selector`：短节点名（`a`/`li`/`icon`）能命中大量
    无关选择器，错配后所有属性都基于错对象 → 假失败，同时把 unmatched 计数压低
    （掩盖真缺失）。规则：
      - 名字先按非字母数字切段，选择器同样切段（类名/属性值都在其中）；
      - **所有**名字段都出现在选择器段集合里 → 'segment'（唯一可给高置信的路径）；
      - 名字 <3 字符一律不参与（`a`/`li` 这类没有区分度）；
      - 非 ASCII 名（中文）无法切段匹配，退化为受限子串（≥2 字符）→ 'substring'
        （低置信，调用方据此降 pending 而不是直接判 confirmed）。
    """
    name = str(name or "").strip().lower()
    sel = str(selector or "").lower()
    if not name or not sel:
        return None
    if not re.search(r"[a-z0-9]", name):
        # 非 ASCII（中文）名无法按 class 段切分：退化为受限子串（≥2 字符）并标低置信，
        # 调用方据此降 pending。长度门槛在此之前判，否则「提交」这类 2 字中文名会被误杀。
        return "substring" if len(name) >= 2 and name in sel else None
    if len(name) < 3:
        return None
    segs = {s for s in re.split(r"[^a-z0-9]+", sel) if s}
    tokens = [t for t in re.split(r"[^a-z0-9]+", name) if t]
    if tokens and all(t in segs for t in tokens):
        return "segment"
    return None


def _unique_containing_box(parent_node, paired_snapshot, parent_of, index, used):
    """找承接该父容器文本子项的**唯一**页面容器盒，供 F18 的样式比对。

    判据：盒 bbox 完整包含已配对文本项的 bbox（左上对齐的包含关系）。候选多于一个
    时返回 None——宁可不配（记 pending）也不赌，错配出来的样式差是纯噪音。
    """
    pid = str(parent_node.get("id") or "")
    child_ids = {cid for cid, par in parent_of.items() if par == pid}
    if not child_ids:
        return None
    candidates = []
    for rec in paired_snapshot:
        if str(rec["node"].get("id") or "") not in child_ids:
            continue
        r = rec["item"].get("rect") or rec["item"].get("bbox") or {}
        if not all(isinstance(r.get(k), (int, float)) for k in ("x", "y", "w", "h")):
            continue
        for cand in index["boxItems"]:
            if id(cand) in used:
                continue
            cr = cand.get("rect") or cand.get("bbox") or {}
            if not all(isinstance(cr.get(k), (int, float)) for k in ("x", "y", "w", "h")):
                continue
            if (cr["x"] <= r["x"] and cr["y"] <= r["y"]
                    and cr["x"] + cr["w"] >= r["x"] + r["w"]
                    and cr["y"] + cr["h"] >= r["y"] + r["h"]
                    # 必须**严格更大**：等大/更小的不是包装盒而是同级元素，拿它当父容器
                    # 比对出来的样式差是错对象噪音（等大时更可能是同一个元素被抓了两遍）
                    and cr["w"] > r["w"] and cr["h"] > r["h"]):
                candidates.append(cand)
    uniq = list({id(c): c for c in candidates}.values())
    return uniq[0] if len(uniq) == 1 else None


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

    def take(node, target, pair_role=None, confidence=None):
        used.add(id(target))
        record = {"node": node, "item": target}
        if pair_role:
            record["pairRole"] = pair_role
        if confidence:
            record["pairConfidence"] = confidence
        pairs.append(record)

    for node in design_nodes:
        node_id = str(node.get("id") or "")
        is_text = bool(node.get("text"))
        pool = index["textItems"] if is_text else index["boxItems"]
        target, confidence = None, None
        entry = mapping.get(node_id)
        if isinstance(entry, dict):
            selector = entry.get("selector")
            nth = int(entry.get("nth", 0) or 0)
            candidates = index["bySelector"].get(str(selector), [])
            if nth < len(candidates):
                target, confidence = candidates[nth], "explicit"
        if target is None:
            text = ((node.get("text") or {}).get("characters") or "").strip()
            if text and index["byText"].get(text):
                for candidate in index["byText"][text]:
                    if id(candidate) not in used:
                        target, confidence = candidate, "text-exact"
                        break
        if target is None:
            # 【F17】name-hint 走词段比对（旧版裸子串：短名 a/li/icon 命中任何选择器，
            # 错配后所有属性都基于错对象 → 假失败，同时 unmatched 虚低掩盖真缺失）。
            name = node.get("name")
            if name:
                for item in pool:
                    if id(item) in used:
                        continue
                    hit = _name_segment_hit(name, item.get("sel") or item.get("selector"))
                    if hit:
                        target = item
                        confidence = "name-segment" if hit == "segment" else "name-substring"
                        break
        if target is None:
            unmatched.append(node)
            continue
        take(node, target, confidence=confidence)

    # 第二次机会：未配对的非文本设计节点（按钮 frame 等）允许与仍未被占用的
    # 带文本页面项配对，避免被误报为「设计稿有页面无」。
    still_unmatched = []
    for node in unmatched:
        if node.get("text"):
            still_unmatched.append(node)
            continue
        name = node.get("name")
        target, confidence = None, None
        if name:
            for item in index["textItems"]:
                if id(item) in used:
                    continue
                hit = _name_segment_hit(name, item.get("sel") or item.get("selector"))
                if hit:
                    target = item
                    confidence = "name-segment" if hit == "segment" else "name-substring"
                    break
        if target is None:
            still_unmatched.append(node)
        else:
            take(node, target, pair_role="box-to-text-item", confidence=confidence)
    unmatched = still_unmatched

    # 父节点 credit：设计文本子节点配对成功时，其直接父容器（按钮 frame 等）
    # 不再假报 designOnly——页面元素已被该文本占用，父容器本身没有独立落点。
    matched_indirect = []
    if parent_of:
        paired_ids = {str(rec["node"].get("id") or "") for rec in pairs}
        credited_parents = {parent_of[pid] for pid in paired_ids if parent_of.get(pid)}
        kept = []
        # 【F18】被 credit 的父容器（按钮 frame 等）自身样式旧版**从不参与比对**——
        # 圆角缺失/背景色错/边框粗细这类历史高发缺陷既不在 designOnly 也不在
        # styleDiffs，静默漏测。改为：先尝试与「承载其文本子项的最近唯一容器盒」
        # 配对并走正常样式比对；找不到唯一候选时记 pending（不静默 credit）。
        paired_snapshot = list(pairs)
        for node in unmatched:
            if str(node.get("id") or "") in credited_parents and not node.get("text"):
                cand = _unique_containing_box(node, paired_snapshot, parent_of, index, used)
                if cand is not None:
                    take(node, cand, pair_role="box-credit", confidence="geometry-contained")
                else:
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
    """设计侧圆角：新格式（标量，extract_design_fields._radius_of 直接算好生效圆角）
    优先；旧格式 dict（corners/uniform）兼容——corners 优先取 max，再回落 uniform。

    【F15 反死代码 + 审查修复】旧判定顺序 uniform 在前——extract_design_fields 的
    uniform 恒存在（缺省 0.0），corners 分支是死代码：设计用独立四角圆角（卡片/
    半屏弹层极常见）时设计侧恒 0、页面侧取 8 → confirmed 圆角假缺陷且淹没真缺陷。
    审查发现：本函数首行 `not isinstance(r, dict): return None` 会把新格式的
    **标量**直接判 None——圆角比对整体失活（比修复前更糟）。新格式标量直通。"""
    r = node.get("radius")
    if isinstance(r, (int, float)) and not isinstance(r, bool):
        return float(r)
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
                 incomparable_reason=None, color_skips=None, pair_confidence=None,
                 style_only=False) -> list:
    # style_only：容器盒配对（F18 box-credit）专用——包装盒的几何尺寸随页面结构变化，
    # 与设计 frame 的 rect 天然不可比，直接比会刷一批 confirmed 假缺陷。只放开样式层。
    # 【审查修复】此专属原因**只在 style_only 时存在**：原写法无条件构造出非空常量，
    # 下面的 `geom_only_reason or incomparable_reason` 于是恒取前者 → incomparable_reason
    # 形参彻底失效，视口不一致这类真实原因被错标成「box-credit 只比对样式层」。
    # 更糟的是同一份 JSON 的 comparability.reason 存的仍是真值，报告内自相矛盾。
    geom_only_reason = (None if not style_only else
                        "容器盒配对（box-credit）只比对样式层：包装盒的位置/尺寸随页面结构变化，"
                        "不据此判缺陷（设计容器自身的几何请用 --mapping 显式配对）")
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
    # ⚠️ 成员必须与 emit() 的 category 实参**同名**（样式类走 emit 第一参，文本类走
    # prop.lower() → "lineheight"/"letterspacing"），**不是** TOLERANCE/DIMENSION 的
    # tol_key（那是 "line_height_px"）。写错名字即静默失效，parity 由
    # tests/test_style_categories.py 锁住。
    STYLE_ONLY_CATEGORIES = {"color", "characters", "font", "radius", "border",
                             "shadow", "opacity", "lineheight", "letterspacing"}

    def emit(category, prop, expected, actual, delta, tolerance_key, dimension=None) -> None:
        tol = TOLERANCE.get(tolerance_key)
        exceeded = delta > tol if tol is not None else True
        # 几何类受视口比例影响；样式类恒可比
        item_comparable = comparable or str(category) in STYLE_ONLY_CATEGORIES
        if style_only and str(category) not in STYLE_ONLY_CATEGORIES:
            item_comparable = False
        status = "confirmed" if (exceeded and item_comparable) else ("notComparable" if not item_comparable else "withinTolerance")
        # 【F17】低置信配对（中文名退化子串命中）不得直接判 confirmed——配错对象时
        # 越界的属性差是**错对象之间的差**，报 confirmed 会刷假缺陷。降为 pending
        # （门禁把 pending 计入 executed，不需要 reason，不影响覆盖率）。
        if status == "confirmed" and pair_confidence == "name-substring":
            status = "pending"
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
            "notComparableReason": ((geom_only_reason or incomparable_reason)
                                    if not item_comparable and (geom_only_reason or incomparable_reason) else None),
            "pairConfidence": pair_confidence,
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
        # 【审查修复】跨模块契约断裂：producer（extract_design_fields.stroke）写的键是
        # weightPx / cssBorderPx，这里却读 strokeWeight / weight —— 三个键一个都不存在，
        # _num(None) 直接跳过，**边框宽度变化永远不产 diff**（历史高发缺陷静默漏测）。
        # 口径：用 F16 专门算好的 cssBorderPx（CENTER 描边页面 CSS 只画 1/2，用 weightPx
        # 会让所有 CENTER 描边按钮恒判超差 = 假缺陷）；缺失时回退 weightPx，再兼容历史键。
        d_bw = _num(s0.get("cssBorderPx"))
        if d_bw is None:
            d_bw = _num(s0.get("weightPx", s0.get("strokeWeight", s0.get("weight"))))
        if d_bw is not None:
            emit("border", "borderWidth", round2(d_bw), round2(p_border),
                 abs(d_bw - p_border), "border_px")

    d_effects = node.get("effects")
    p_shadow = _shadow_blur_offset(item.get("boxShadow"))
    if isinstance(d_effects, list) and d_effects and p_shadow is not None:
        e0 = d_effects[0] if isinstance(d_effects[0], dict) else {}
        # 同上：producer 写的是 blur，这里读 radius —— 键名对不上导致阴影模糊恒不比对。
        d_blur = _num(e0.get("blur", e0.get("radius")))
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
                                  color_skips=color_skips,
                                  pair_confidence=rec.get("pairConfidence"),
                                  style_only=(rec.get("pairRole") == "box-credit")))
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
            # 【F17】配对置信度分布：低置信（name-substring）占比高说明设计节点名与
            # 页面选择器命名体系不一致，属性差异的可信度整体下降，需人工抽查。
            "pairConfidence": {lv: len([r for r in pairs if r.get("pairConfidence") == lv])
                               for lv in {r.get("pairConfidence") for r in pairs if r.get("pairConfidence")}},
            "colorCompareSkipped": len(color_skips),
        },
        "styleDiffs": diffs,
        "defects": real,
        "unmatched": {
            "designOnly": [{"nodeId": n.get("id"), "name": n.get("name"), "rect": n.get("rect")} for n in unmatched_design],
            "pageOnly": [{"selector": i.get("sel") or i.get("selector"), "text": i.get("text"), "kind": i.get("_kind")} for i in unmatched_page],
        },
        "matchedIndirect": [{"nodeId": n.get("id"), "name": n.get("name"), "matchedVia": "text-child-pair",
                             "status": "pending",
                             "reason": "父容器未找到唯一承载盒，其自身样式（圆角/背景/边框/阴影）本次未比对；"
                                       "如需覆盖请用 --mapping 显式指定该容器选择器"}
                            for n in matched_indirect],
        "colorCompareSkipped": color_skips,
        # 【F19 留痕】形似颜色却解析失败的原文——颜色被静默跳过比对是漏测来源，
        # 报告里必须能看见「哪些值没比过」，而不是永远空着让人以为全比了。
        "parseWarnings": {"unparsedColors": list(_UNPARSED_COLORS)},
        "tolerance": TOLERANCE,
        "note": "unmatched.designOnly 与 unmatched.pageOnly 是双向盘点输入，需按 7.23 判定后转为缺陷或忽略",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    if basis_warnings:
        for w in basis_warnings:
            print("警告：{}".format(w), file=sys.stderr)
    if _UNPARSED_COLORS:
        print("警告：{} 个颜色值形似 CSS 颜色但解析失败、已跳过比对（见产物 parseWarnings）：{}".format(
            len(_UNPARSED_COLORS), "、".join(_UNPARSED_COLORS[:5])), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
