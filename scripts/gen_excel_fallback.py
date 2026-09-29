# -*- coding: utf-8 -*-
"""
gen_excel_fallback.py — Excel 缺陷报告生成（mcp_Excel 不可用时的回退脚本）

用法:
    python gen_excel_fallback.py <report.json> [defects.xlsx]

输入: figma-ui-parity 步骤 9.2 生成的 report.json
输出: 8 列缺陷表（仅缺陷项，与 mcp_Excel 版表头/类型完全一致；含「元素定位」列）
依赖: openpyxl（pip install openpyxl）
"""
import json
import sys
from pathlib import Path

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError:
    sys.exit("缺少 openpyxl：请先执行 pip install openpyxl")

HEADERS = ["序号", "等级", "缺陷类型", "功能模块", "问题描述", "解决方案", "元素定位", "备注(附图)"]
VALID_TYPES = [
    "尺寸与间距", "排版样式", "视觉样式", "交互状态",
    "内容适配", "图标与图片", "响应式缺陷",
    "对齐与居中", "布局与显隐",
]
LEVEL_FILL = {
    "高": PatternFill("solid", fgColor="FFC7CE"),
    "中": PatternFill("solid", fgColor="FFEB9C"),
    "低": PatternFill("solid", fgColor="C6EFCE"),
}


def loc_str(el):
    """从 element 对象构造「元素定位」单元格内容：selector @ (x,y,w,h) anchor。
    element 可能为 dict（新 schema）或遗留字符串，均做兼容。"""
    if not isinstance(el, dict):
        return str(el) if el else ""
    sel = el.get("selector") or ""
    bbox = el.get("bbox") or {}
    x, y, w, h = bbox.get("x"), bbox.get("y"), bbox.get("w"), bbox.get("h")
    anchor = el.get("anchor") or ""
    parts = sel
    if None not in (x, y, w, h):
        parts += " @ ({},{},{},{})".format(x, y, w, h)
    if anchor:
        parts += " " + anchor
    return parts.strip()


def module_name(el):
    """功能模块列：优先用人类可读的 anchor，否则退化为 selector。"""
    if isinstance(el, dict):
        return el.get("anchor") or el.get("selector") or ""
    return str(el) if el else ""


def rows_from_report(report: dict):
    """从 report.json 提取缺陷行：diffs(high/medium/low) + responsive.issues（均含 element 定位对象）"""
    rows = []
    for level in ("high", "medium", "low"):
        for d in report.get("diffs", {}).get(level, []):
            rows.append({
                "等级": {"high": "高", "medium": "中", "low": "低"}[level],
                "缺陷类型": d.get("category", d.get("type", "视觉样式")),
                "功能模块": module_name(d.get("element")),
                "问题描述": d.get("issue", d.get("detail", "")),
                "解决方案": d.get("fix", d.get("suggestion", "")),
                "元素定位": loc_str(d.get("element")),
                "备注(附图)": d.get("screenshot", d.get("note", "")),
            })
    for vp in report.get("responsive", {}).get("perViewport", []):
        for iss in vp.get("issues", []):
            rows.append({
                "等级": {"high": "高", "medium": "中", "low": "低"}.get(iss.get("severity", "medium"), "中"),
                "缺陷类型": "响应式缺陷",
                "功能模块": module_name(iss.get("element")),
                "问题描述": f"[视口{vp.get('viewport')}px] {iss.get('detail', '')}",
                "解决方案": iss.get("fix", ""),
                "元素定位": loc_str(iss.get("element")),
                "备注(附图)": f"screenshot_{vp.get('viewport')}.png",
            })
    return rows


PENDING_HEADERS = ["序号", "待确认项", "类别", "确认位置", "页面元素", "设计参考", "无法自动判定原因", "确认建议"]


def pending_rows_from_report(report: dict):
    """从 report.json 提取待确认问题行：pendingChecks（需视觉核对 / 无法自动判定项）。
    每条必须带确认位置与页面元素，便于人工回查页面核实。"""
    rows = []
    for pc in report.get("pendingChecks", []):
        el = pc.get("element") or {}
        confirm = pc.get("confirmLocation") or ""
        if not confirm:  # 兜底：设计参考 ↔ 元素定位
            dr = pc.get("designRef", "")
            confirm = (dr + " ↔ " if dr else "") + loc_str(el)
        page_el = pc.get("pageElement") or module_name(el)
        rows.append({
            "待确认项": pc.get("name", ""),
            "类别": pc.get("category", ""),
            "确认位置": confirm,
            "页面元素": page_el,
            "设计参考": pc.get("designRef", ""),
            "无法自动判定原因": pc.get("reason", ""),
            "确认建议": pc.get("suggestion", ""),
        })
    return rows


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    report_path = Path(sys.argv[1])
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else report_path.parent / "defects.xlsx"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = rows_from_report(report)

    wb = Workbook()
    ws = wb.active
    ws.title = "UI缺陷清单"

    # 表头
    for col, h in enumerate(HEADERS, 1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="D9E1F2")
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"

    # 数据行（仅缺陷项）
    for i, r in enumerate(rows, 1):
        row_idx = i + 1
        vals = [i, r["等级"], r["缺陷类型"], r["功能模块"], r["问题描述"], r["解决方案"], r["元素定位"], r["备注(附图)"]]
        for col, v in enumerate(vals, 1):
            ws.cell(row=row_idx, column=col, value=v)
        lv = r["等级"]
        if lv in LEVEL_FILL:
            ws.cell(row=row_idx, column=2).fill = LEVEL_FILL[lv]
        if r["缺陷类型"] not in VALID_TYPES:
            ws.cell(row=row_idx, column=3).comment = None  # 类型超出枚举时人工复核
            print(f"警告: 第{i}行缺陷类型 '{r['缺陷类型']}' 不在标准类型表中，请人工复核")

    # 列宽
    widths = [6, 8, 14, 18, 46, 40, 40, 24]
    for col, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(col)].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(vertical="top", wrap_text=True)

    # 待确认问题 sheet（需视觉核对 / 无法自动判定项）
    prows = pending_rows_from_report(report)
    if prows:
        pws = wb.create_sheet("待确认问题")
        for col, h in enumerate(PENDING_HEADERS, 1):
            c = pws.cell(row=1, column=col, value=h)
            c.font = Font(bold=True)
            c.fill = PatternFill("solid", fgColor="FCE4D6")
            c.alignment = Alignment(horizontal="center", vertical="center")
        pws.freeze_panes = "A2"
        for i, r in enumerate(prows, 1):
            vals = [i, r["待确认项"], r["类别"], r["确认位置"], r["页面元素"],
                    r["设计参考"], r["无法自动判定原因"], r["确认建议"]]
            for col, v in enumerate(vals, 1):
                pws.cell(row=i + 1, column=col, value=v)
        pwidths = [6, 18, 22, 46, 28, 30, 44, 40]
        for col, w in enumerate(pwidths, 1):
            pws.column_dimensions[get_column_letter(col)].width = w
        for row in pws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(vertical="top", wrap_text=True)
        print(f"已生成「待确认问题」sheet（{len(prows)} 条）")

    wb.save(out_path)
    print(f"已生成 {out_path}（{len(rows)} 条缺陷）")


if __name__ == "__main__":
    main()
