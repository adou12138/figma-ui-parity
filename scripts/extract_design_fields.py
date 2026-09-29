#!/usr/bin/env python3
"""Normalize a Figma node dump into a comparable design model.

Input: the JSON returned by Figma `get_file_nodes` / REST `/v1/files/:key/nodes`
(or any object containing a `nodes` map). Output: a normalized model whose
values are already in CSS-comparable units, so comparison needs no ad-hoc math.

Offline only: reads a local JSON file, writes a local JSON file.
"""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path

WEIGHT_BY_NAME = {
    "thin": 100, "extralight": 200, "ultralight": 200, "light": 300,
    "regular": 400, "normal": 400, "book": 400, "medium": 500,
    "semibold": 600, "demibold": 600, "bold": 700,
    "extrabold": 800, "ultrabold": 800, "black": 900, "heavy": 900,
}
STYLE_SUFFIXES = ("italic", "oblique")


def round2(value: float) -> float:
    return round(float(value) + 0.0, 2)


def color_to_css(color: dict) -> dict:
    r = int(round(color.get("r", 0) * 255))
    g = int(round(color.get("g", 0) * 255))
    b = int(round(color.get("b", 0) * 255))
    a = round2(color.get("a", 1))
    return {
        "rgb": [r, g, b],
        "hex": "#{:02x}{:02x}{:02x}".format(r, g, b),
        "alpha": a,
        "css": "rgba({}, {}, {}, {})".format(r, g, b, a),
    }


def gradient_angle(handles: list) -> float | None:
    """Convert Figma gradient handles to a CSS linear-gradient angle."""
    if not isinstance(handles, list) or len(handles) < 2:
        return None
    start, end = handles[0], handles[1]
    dx = end.get("x", 0) - start.get("x", 0)
    dy = end.get("y", 0) - start.get("y", 0)
    if dx == 0 and dy == 0:
        return None
    return round2((math.degrees(math.atan2(dx, -dy)) + 360) % 360)


def paint(p: dict) -> dict:
    out = {"type": p.get("type"), "visible": p.get("visible", True), "opacity": round2(p.get("opacity", 1))}
    if p.get("type") == "SOLID" and isinstance(p.get("color"), dict):
        out["color"] = color_to_css(p["color"])
    stops = p.get("gradientStops")
    if isinstance(stops, list):
        out["angle"] = gradient_angle(p.get("gradientHandlePositions", []))
        out["stops"] = [
            {"position": round2(s.get("position", 0)), "color": color_to_css(s.get("color", {}))}
            for s in stops if isinstance(s, dict)
        ]
    if p.get("imageRef"):
        out["imageRef"] = p["imageRef"]
        out["scaleMode"] = p.get("scaleMode")
    return out


def font_weight(text_style: dict) -> int | None:
    """字重取值：优先 Figma API 的数值 fontWeight 字段，名称映射只作回退。

    英文名称映射覆盖不到数字/本地化 style（如 "W6"），映射失败返回 None
    会让字重比对静默跳过形成漏报；API 的 style.fontWeight 数值始终可靠。
    """
    if not isinstance(text_style, dict):
        return None
    numeric = text_style.get("fontWeight")
    if isinstance(numeric, (int, float)) and not isinstance(numeric, bool) and 100 <= numeric <= 900:
        return int(numeric)
    font_name = text_style.get("fontName")
    if not isinstance(font_name, dict):
        return None
    style = str(font_name.get("style", "")).lower().replace(" ", "")
    for suffix in STYLE_SUFFIXES:
        style = style.replace(suffix, "")
    if style in WEIGHT_BY_NAME:
        return WEIGHT_BY_NAME[style]
    for name, weight in WEIGHT_BY_NAME.items():
        if style.startswith(name):
            return weight
    return None


def line_height(lh: dict, font_size: float) -> dict:
    if not isinstance(lh, dict):
        return {"css": "normal", "px": None, "ratio": None, "unit": "AUTO"}
    unit = lh.get("unit", "AUTO")
    value = lh.get("value")
    if unit == "PIXELS" and value is not None:
        return {"css": "{}px".format(round2(value)), "px": round2(value), "ratio": round2(value / font_size) if font_size else None, "unit": unit}
    if unit == "PERCENT" and value is not None:
        px = value / 100.0 * font_size if font_size else None
        return {"css": "{}%".format(round2(value)), "px": round2(px) if px else None, "ratio": round2(value / 100.0), "unit": unit}
    return {"css": "normal", "px": None, "ratio": None, "unit": unit}


def letter_spacing(ls: dict, font_size: float) -> dict:
    if not isinstance(ls, dict):
        return {"css": "normal", "px": 0.0, "unit": "PIXELS"}
    unit = ls.get("unit", "PIXELS")
    value = ls.get("value", 0) or 0
    if unit == "PERCENT":
        px = value / 100.0 * font_size if font_size else 0.0
        return {"css": "{}em".format(round2(value / 100.0)), "px": round2(px), "unit": unit}
    return {"css": "{}px".format(round2(value)), "px": round2(value), "unit": unit}


def stroke(strokes: list) -> list:
    out = []
    for s in strokes or []:
        if not isinstance(s, dict) or not s.get("visible", True):
            continue
        align = s.get("strokeAlign", "CENTER")
        weight = round2(s.get("strokeWeight", 1) or 1)
        css_weight = weight if align == "CENTER" else weight
        out.append({
            "paint": paint(s),
            "weightPx": weight,
            "align": align,
            "cssBorderPx": css_weight,
            "note": {
                "INSIDE": "border 计入盒内，等价 box-sizing:border-box",
                "OUTSIDE": "border 在盒外，页面常用 outline 或额外占位实现",
                "CENTER": "border 居中绘制，页面上应取 1/2 可视宽度",
            }.get(align, "border 居中绘制"),
        })
    return out


def effects(items: list) -> list:
    out = []
    for e in items or []:
        if not isinstance(e, dict) or not e.get("visible", True):
            continue
        kind = e.get("type")
        if kind not in ("DROP_SHADOW", "INNER_SHADOW"):
            continue
        offset = e.get("offset", {}) or {}
        out.append({
            "kind": kind,
            "x": round2(offset.get("x", 0)),
            "y": round2(offset.get("y", 0)),
            "blur": round2(e.get("radius", 0)),
            "spread": round2(e.get("spread", 0)),
            "color": color_to_css(e.get("color", {})),
            "css": "{}{}px {}px {}px {}px {}".format(
                "inset " if kind == "INNER_SHADOW" else "",
                round2(offset.get("x", 0)), round2(offset.get("y", 0)),
                round2(e.get("radius", 0)), round2(e.get("spread", 0)),
                color_to_css(e.get("color", {}))["css"],
            ),
        })
    return out


def node_model(node: dict, frame_origin: dict | None = None) -> dict:
    rect = node.get("absoluteBoundingBox") or node.get("bbox") or {}
    origin = frame_origin or {"x": 0, "y": 0}
    style = node.get("style") or {}
    font_size = float(style.get("fontSize", node.get("fontSize", 0)) or 0)
    model = {
        "id": node.get("id"),
        "name": node.get("name"),
        "type": node.get("type"),
        "visible": node.get("visible", True),
        "opacity": round2(node.get("opacity", 1)),
        "rect": {
            "x": round2(rect.get("x", 0) - origin.get("x", 0)),
            "y": round2(rect.get("y", 0) - origin.get("y", 0)),
            "w": round2(rect.get("width", 0)),
            "h": round2(rect.get("height", 0)),
        },
        "rotation": round2(node.get("rotation", 0) or 0),
        "constraints": node.get("constraints") or {},
        "layout": {
            "mode": node.get("layoutMode"),
            "itemSpacing": round2(node.get("itemSpacing", 0) or 0),
            "counterAxisSpacing": round2(node.get("counterAxisSpacing", 0) or 0) if node.get("counterAxisSpacing") is not None else None,
            "padding": {
                "top": round2(node.get("paddingTop", 0) or 0),
                "right": round2(node.get("paddingRight", 0) or 0),
                "bottom": round2(node.get("paddingBottom", 0) or 0),
                "left": round2(node.get("paddingLeft", 0) or 0),
            },
            "primaryAxisAlign": node.get("primaryAxisAlignItems"),
            "counterAxisAlign": node.get("counterAxisAlignItems"),
        },
        "fills": [paint(p) for p in (node.get("fills") or []) if isinstance(p, dict) and p.get("visible", True)],
        "strokes": stroke(node.get("strokes")),
        "radius": {
            "uniform": round2(node.get("cornerRadius", 0) or 0),
            "corners": node.get("rectangleCornerRadii"),
            "perCorner": bool(node.get("rectangleCornerRadii")),
        },
        "effects": effects(node.get("effects")),
        "clipsContent": node.get("clipsContent"),
    }
    if node.get("type") == "TEXT" or style:
        model["text"] = {
            "characters": node.get("characters"),
            "fontFamily": style.get("fontFamily") or (style.get("fontName") or {}).get("family"),
            "fontPostScriptName": style.get("fontPostScriptName") or (style.get("fontName") or {}).get("family"),
            "fontWeight": font_weight(style),
            "fontSize": round2(font_size),
            "lineHeight": line_height(style.get("lineHeight") or {}, font_size),
            "letterSpacing": letter_spacing(style.get("letterSpacing") or {}, font_size),
            "textCase": style.get("textCase", "ORIGINAL"),
            "textAlignHorizontal": style.get("textAlignHorizontal"),
            "textAlignVertical": style.get("textAlignVertical"),
            "paragraphSpacing": round2(style.get("paragraphSpacing", 0) or 0),
        }
    children = node.get("children") or []
    if children:
        model["children"] = [node_model(c, origin) for c in children]
    return model


def flatten(nodes: list, out: list | None = None) -> list:
    out = out if out is not None else []
    for n in nodes:
        out.append(n)
        flatten(n.get("children") or [], out)
    return out


def pick_root(payload: dict, node_id: str | None) -> dict | None:
    nodes = payload.get("nodes")
    if isinstance(nodes, dict) and nodes:
        key = node_id if node_id in nodes else next(iter(nodes))
        entry = nodes[key]
        return entry.get("document", entry) if isinstance(entry, dict) else None
    if isinstance(payload.get("document"), dict):
        return payload["document"]
    if payload.get("id") and payload.get("type"):
        return payload
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="把 Figma 节点 dump 规范化为可比设计模型")
    ap.add_argument("--input", required=True, type=Path, help="get_file_nodes 返回的 JSON")
    ap.add_argument("--node-id", default=None, help="指定根节点，缺省取 nodes 里的第一个")
    ap.add_argument("--output", required=True, type=Path)
    args = ap.parse_args()

    if not args.input.exists():
        print("输入不存在: {}".format(args.input), file=sys.stderr)
        return 2
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    root = pick_root(payload, args.node_id)
    if root is None:
        print("未找到节点树：期望顶层含 nodes / document，或本身是 node", file=sys.stderr)
        return 3

    rect = root.get("absoluteBoundingBox") or root.get("bbox") or {}
    origin = {"x": rect.get("x", 0), "y": rect.get("y", 0)}
    model = node_model(root, origin)
    flat = flatten([model])
    text_nodes = [n for n in flat if "text" in n]
    result = {
        "source": str(args.input),
        "rootId": root.get("id"),
        "frame": {"name": root.get("name"), "w": round2(rect.get("width", 0)), "h": round2(rect.get("height", 0))},
        "stats": {"nodes": len(flat), "textNodes": len(text_nodes), "withFills": len([n for n in flat if n["fills"]])},
        "tree": model,
        "flat": flat,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "nodes": len(flat), "textNodes": len(text_nodes), "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
