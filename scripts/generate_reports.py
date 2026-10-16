#!/usr/bin/env python3
"""Render a parity report into HTML + JSON + CSV.

Section list follows references/report-templates.md: 概览统计、对象匹配、并排截图、
热力图、场景覆盖、样式分组差异、图标与图片、关键差异汇总、修复建议、待确认、
回归对比、降级能力、增强视图（diffScore 趋势）。

CSV columns follow the 8-column defect table spec exactly.
Offline only: reads local JSON, writes local files.
"""
from __future__ import annotations
import argparse, csv, html, json, sys
from datetime import datetime
from pathlib import Path

DEFECT_KEYS = ("defects", "defectList", "diffs", "issues", "findings")
SEVERITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
CSV_COLUMNS = ["序号", "等级", "缺陷类型", "功能模块", "问题描述", "解决方案", "元素定位", "备注(附图)"]
GRADE_LABEL = {"P0": "高", "P1": "高", "P2": "中", "P3": "低"}
DIMENSION_GROUPS = {
    "尺寸与间距": ("rect", "position", "spacing", "padding", "gap", "layout"),
    "排版样式": ("font", "text", "line_height", "letter_spacing"),
    "视觉样式": ("color", "background", "border", "radius", "shadow", "opacity", "gradient"),
    "图标与图片": ("icon", "image"),
}


def default_dimensions_path() -> Path:
    return Path(__file__).resolve().parent.parent / "schemas" / "check-dimensions.json"


def load_dimension_names(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {d["id"]: d.get("name", "") for d in data.get("dimensions", []) if d.get("id")}
    except Exception:  # noqa: BLE001
        return {}


def collect_defects(data) -> list:
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    for key in DEFECT_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return [d for d in value if isinstance(d, dict)]
    return []


def dedupe(defects: list) -> tuple:
    merged, duplicates = {}, 0
    for item in defects:
        fingerprint = str(item.get("fingerprint") or "")
        if not fingerprint:
            element = item.get("element") if isinstance(item.get("element"), dict) else {}
            fingerprint = "|".join([
                str(item.get("page", "")), str(item.get("scenario", "")),
                str(element.get("selector", "")), str(element.get("nth", "")),
                str(item.get("dimension") or item.get("category", "")), str(item.get("viewport", "")),
            ])
            item["fingerprint"] = fingerprint
        if fingerprint not in merged:
            merged[fingerprint] = dict(item)
        else:
            duplicates += 1
            old = merged[fingerprint]
            sources = set(old.get("sources", []) or []) | set(item.get("sources", []) or [])
            if item.get("source"):
                sources.add(str(item["source"]))
            old["sources"] = sorted(sources)
            evidence = list(old.get("evidence", []) or [])
            evidence.extend(list(item.get("evidence", []) or []))
            old["evidence"] = evidence
    return list(merged.values()), duplicates


def sort_defects(defects: list) -> list:
    def key(d):
        return (SEVERITY_ORDER.get(str(d.get("severity", "")), 9), -float(d.get("confidence", 0) or 0), str(d.get("id", "")))
    return sorted(defects, key=key)


def locate(d: dict) -> str:
    element = d.get("element") if isinstance(d.get("element"), dict) else {}
    selector = element.get("selector") or ""
    nth = element.get("nth")
    bbox = element.get("bbox") if isinstance(element.get("bbox"), dict) else {}
    parts = [p for p in [selector, "[{}]".format(nth) if nth is not None else ""] if p]
    if bbox:
        parts.append("@({x},{y},{w},{h})".format(x=bbox.get("x", "-"), y=bbox.get("y", "-"), w=bbox.get("w", "-"), h=bbox.get("h", "-")))
    if element.get("anchor"):
        parts.append(str(element["anchor"]))
    return " ".join(parts) or "-"


def describe(defect: dict) -> str:
    """问题描述 = 现象 + 指标（同列双段，不新增列）。"""
    symptom = str(defect.get("symptom") or "").strip()
    expected, actual = defect.get("expected"), defect.get("actual")
    if expected is not None or actual is not None:
        return "{}（设计 {}，实际 {}）".format(symptom, expected, actual) if symptom else "设计 {}，实际 {}".format(expected, actual)
    return symptom


def evidence_text(defect: dict) -> str:
    items = defect.get("evidence") or []
    artifacts = [str(e.get("artifact")) for e in items if isinstance(e, dict) and e.get("artifact")]
    text = "; ".join(artifacts) if artifacts else "; ".join(
        "{}:{}".format(e.get("type"), e.get("result")) for e in items if isinstance(e, dict))
    status = defect.get("status")
    return " ".join([p for p in [text, "[{}]".format(status) if status else ""] if p]) or "-"


def _csv_safe(value) -> str:
    """【F33 反公式注入】Excel/Sheets 会把以 = + - @ 开头的单元格当公式执行——
    缺陷描述来自页面/设计稿文本（不可信输入），` =HYPERLINK(...)` 型单元格能
    构成从测试产物到分析者的攻击链。前置 ' 让它按文本呈现。"""
    s = str(value if value is not None else "")
    if s.startswith(("=", "+", "-", "@", "\t")):
        return "'" + s
    return s


def write_csv(path: Path, defects: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(CSV_COLUMNS)
        for index, d in enumerate(defects, 1):
            writer.writerow([
                index,
                _csv_safe(GRADE_LABEL.get(str(d.get("severity")), str(d.get("severity", "")))),
                _csv_safe(d.get("category") or d.get("dimension", "")),
                _csv_safe(d.get("module") or d.get("scenario", "")),
                _csv_safe(describe(d)),
                _csv_safe(d.get("suggestion", "")),
                _csv_safe(locate(d)),
                _csv_safe(("[P0] " if str(d.get("severity")) == "P0" else "") + evidence_text(d)),
            ])


def table(headers: list, rows: list, klass: str = "") -> str:
    if not rows:
        return "<p class='muted'>无记录</p>"
    head = "".join("<th>{}</th>".format(html.escape(str(h))) for h in headers)
    return "<table class='{}'><thead><tr>{}</tr></thead><tbody>{}</tbody></table>".format(klass, head, "\n".join(rows))


def kv_table(mapping: dict) -> str:
    if not mapping:
        return "<p class='muted'>无记录</p>"
    rows = "".join("<tr><th>{}</th><td>{}</td></tr>".format(html.escape(str(k)), html.escape(str(v))) for k, v in mapping.items())
    return "<table class='kv'>{}</table>".format(rows)


def scenario_coverage_table(cov) -> str:
    """场景执行率专区渲染。

    scenario_coverage.py 的产物是多层嵌套 dict（planned/executed/notExecuted/...），
    直接交给 kv_table 会被 str() 成 Python dict repr，读者看不见执行率与未执行分布。
    这里把它扁平化成「关键指标 + 未执行按维度 + 未写原因 + 不稳定场景」四段。
    """
    if not isinstance(cov, dict) or not cov:
        return "<p class='muted'>无场景统计</p>"
    if "planned" not in cov and "executed" not in cov:
        # 其他形状（如早期 scenarioSummary）：容器值压平成可读串，别输出 repr
        flat = {k: (v if isinstance(v, (str, int, float, bool)) else str(v))
                for k, v in cov.items()}
        return kv_table(flat)
    planned = cov.get("planned") or {}
    executed = cov.get("executed") or {}
    notrun = cov.get("notExecuted") or {}
    multi = cov.get("multipleRecords") or {}
    rate = executed.get("rate")
    rate_txt = "{}%".format(round(rate * 100, 1)) if isinstance(rate, (int, float)) else "—"
    # 【审查修复·死数据激活】rateIncludingTruncated（截断场景计入分母的保守口径）
    # 此前产出但无人消费——它的存在意义就是让人看见「截断虚高」。两口径并排展示，
    # 差距大 = 大量意图场景被截断静默丢弃。
    rate_trunc = executed.get("rateIncludingTruncated")
    rate_trunc_txt = "{}%".format(round(rate_trunc * 100, 1)) if isinstance(rate_trunc, (int, float)) else "—"
    parts = [kv_table({
        "计划场景总数": planned.get("total", 0),
        "计入执行率": planned.get("counted", 0),
        "已执行": executed.get("total", 0),
        "执行率": rate_txt,
        "执行率（含截断，保守）": rate_trunc_txt,
        "未执行": notrun.get("total", 0),
        "截断丢弃": planned.get("truncated", 0),
        "豁免维度": "、".join(planned.get("exemptDimensions") or []) or "无",
    })]
    by_dim = notrun.get("byDimension") or {}
    if by_dim:
        rows = "".join("<tr><th>{}</th><td>{} 条</td></tr>".format(
            html.escape(str(d)), html.escape(str(n))) for d, n in list(by_dim.items())[:10])
        parts.append("<h3>未执行场景按维度（Top 10）</h3><table class='kv'>{}</table>".format(rows))
    unexplained = notrun.get("unexplained") or []
    if unexplained:
        parts.append("<p class='note'>未写原因的未执行 {} 条：{}</p>".format(
            len(unexplained), html.escape("、".join(str(x) for x in unexplained[:10]))))
    flaky = multi.get("flakyScenarioIds") or []
    if flaky:
        parts.append("<p class='note'>不稳定场景（终态不一致）{} 个：{}</p>".format(
            len(flaky), html.escape("、".join(str(x) for x in flaky[:10]))))
    unknown = cov.get("unknownResults") or []
    if unknown:
        parts.append("<p class='note'>计划外回填 {} 个（可能来自旧计划）：{}</p>".format(
            len(unknown), html.escape("、".join(str(x) for x in unknown[:10]))))
    if cov.get("note"):
        parts.append("<p class='note'>{}</p>".format(html.escape(str(cov["note"]))))
    return "".join(parts)


def section(title: str, content: str, note: str = "") -> str:
    return "<section><h2>{}</h2>{}<div>{}</div></section>".format(
        html.escape(title), "<p class='note'>{}</p>".format(html.escape(note)) if note else "", content)


def gallery(items: list, key_pairs: list) -> str:
    if not items:
        return "<p class='muted'>未提供截图</p>"
    cards = []
    for item in items:
        images = "".join(
            "<figure><img src='{}' alt='{}'><figcaption>{}</figcaption></figure>".format(
                html.escape(str(item.get(key, ""))), html.escape(str(item.get(key, ""))), html.escape(label))
            for key, label in key_pairs if item.get(key))
        cards.append("<div class='card'><h3>{}</h3>{}</div>".format(html.escape(str(item.get("label", ""))), images))
    return "<div class='gallery'>{}</div>".format("".join(cards))


def sparkline(history: list) -> str:
    if not history:
        return "<p class='muted'>无历史数据</p>"
    values = [float(h.get("diffScore", 0) or 0) for h in history]
    labels = [str(h.get("run", "")) for h in history]
    peak = max(values + [1.0])
    bars = "".join(
        "<div class='bar' style='height:{:.1f}%' title='{}: {}'><span>{}</span></div>".format(
            max(2.0, v / peak * 100.0), html.escape(labels[i]), v, html.escape(labels[i]))
        for i, v in enumerate(values))
    return "<div class='spark'>{}</div><p class='note'>按运行顺序的 diffScore 趋势，用于识别波动项。</p>".format(bars)


def dimension_table(coverage: dict, checks: dict, names: dict) -> str:
    if not checks:
        return "<p class='muted'>报告未提供逐维度结论，覆盖率不可计算</p>"
    rows = []
    for dim_id in sorted(checks, key=lambda x: [int(p) for p in str(x).split(".") if p.isdigit()] or [999]):
        entry = checks[dim_id]
        status = entry.get("status") if isinstance(entry, dict) else str(entry)
        reason = entry.get("reason", "") if isinstance(entry, dict) else ""
        css = {"pass": "ok", "fail": "bad", "warn": "warn", "pending": "warn"}.get(str(status), "muted")
        rows.append("<tr><td>{}</td><td>{}</td><td class='{}'>{}</td><td>{}</td></tr>".format(
            html.escape(str(dim_id)), html.escape(names.get(str(dim_id), "")), css,
            html.escape(str(status or "")), html.escape(str(reason or ""))))
    banner = ""
    if coverage:
        if coverage.get("belowThreshold"):
            banner = "<p class='alert'>本报告非全量覆盖：已完成 {}/{} 项（覆盖率 {:.0%}），未覆盖 {}。</p>".format(
                coverage.get("executed"), coverage.get("total"), coverage.get("coverageRate", 0),
                "、".join(coverage.get("notExecutedDimensions", []) + coverage.get("missingDimensions", [])))
        else:
            banner = "<p class='good'>覆盖率 {:.0%}（{}/{} 项）</p>".format(
                coverage.get("coverageRate", 0), coverage.get("executed"), coverage.get("total"))
    return banner + table(["ID", "维度", "结论", "说明/原因"], rows, "dims")


def style_diff_groups(style_diffs: list) -> str:
    if not style_diffs:
        return "<p class='muted'>未提供样式层差异明细</p>"
    blocks = []
    for group, properties in DIMENSION_GROUPS.items():
        picked = [d for d in style_diffs if str(d.get("category", "")).split("|")[-1] in properties]
        if not picked:
            continue
        rows = []
        for d in picked[:80]:
            rows.append("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                html.escape(str(d.get("dimension", ""))), html.escape(str(d.get("property", ""))),
                html.escape(str(d.get("expected", ""))), html.escape(str(d.get("actual", ""))),
                html.escape(str(d.get("delta", ""))), html.escape(str(d.get("tolerance", ""))),
                html.escape(str(d.get("status", "")))))
        blocks.append("<h3>{}</h3>{}".format(html.escape(group),
                                            table(["维度", "属性", "设计值", "实际值", "差值", "容差", "结论"], rows)))
    return "".join(blocks) if blocks else "<p class='muted'>未提供样式层差异明细</p>"


def build_html(payload: dict, defects: list, duplicates: int, dimensions: dict) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    coverage = meta.get("coverage") or payload.get("coverage")
    checks = meta.get("checks") or payload.get("checks") or {}
    counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for d in defects:
        severity = str(d.get("severity", ""))
        if severity in counts:
            counts[severity] += 1
    pending = [d for d in defects if d.get("status") in ("pending", "dataMissing")] + list(payload.get("pendingChecks") or [])
    style_diffs = payload.get("styleDiffs") or []
    scenarios = payload.get("scenarios") or payload.get("scenarioSummary") or {}

    head = dict(summary)
    head.update({
        "缺陷总数": len(defects),
        "P0/P1/P2/P3": "{} / {} / {} / {}".format(counts["P0"], counts["P1"], counts["P2"], counts["P3"]),
        "待确认": len(pending),
        "合并重复证据": duplicates,
        "样式层差异": len(style_diffs),
        "生成时间": payload.get("generatedAt", ""),
    })

    defect_rows = []
    for index, d in enumerate(defects, 1):
        repro = "<br>".join(html.escape(str(s)) for s in (d.get("reproduction") or [])) or "-"
        defect_rows.append("<tr><td>{}</td><td class='sev-{}'>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            index, html.escape(str(d.get("severity", ""))), html.escape(str(d.get("severity", ""))),
            html.escape(str(d.get("category") or d.get("dimension", ""))), html.escape(describe(d)),
            html.escape(str(d.get("suggestion", "-"))), html.escape(locate(d)), repro))

    pending_rows = []
    for d in pending[:80]:
        if not isinstance(d, dict):
            continue
        pending_rows.append("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(d.get("dimension", ""))), html.escape(str(d.get("symptom", ""))),
            html.escape(str(d.get("status", "pending"))), html.escape(str(d.get("reason") or d.get("actual", "")))))

    reg_rows = []
    regression = payload.get("regression")
    if isinstance(regression, dict):
        for bucket in ("added", "fixed", "persistent", "flaky", "notComparable"):
            for item in (regression.get(bucket) or []):
                reg_rows.append("<tr><td>{}</td><td>{}</td><td>{}</td></tr>".format(
                    html.escape(bucket),
                    html.escape(str(item if not isinstance(item, dict) else item.get("symptom") or item.get("property") or "")),
                    html.escape(str(item.get("dimension", "")) if isinstance(item, dict) else "")))

    return """<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>
<title>{title}</title><style>
body{{font-family:-apple-system,'Segoe UI','Microsoft YaHei',sans-serif;margin:0 auto;max-width:1200px;padding:24px;color:#1f2328;background:#fff;line-height:1.55}}
h1{{font-size:22px}} h2{{font-size:17px;margin-top:28px;border-left:3px solid #0969da;padding-left:8px}} h3{{font-size:14px;margin:16px 0 4px}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin-top:6px}}
th,td{{border:1px solid #d8dee4;padding:6px 8px;text-align:left;vertical-align:top}}
th{{background:#f3f5f7}} table.kv{{width:auto;min-width:360px}}
.alert{{background:#fff1f0;border:1px solid #ffa39e;padding:10px;border-radius:6px}}
.good{{background:#f6ffed;border:1px solid #b7eb8f;padding:8px;border-radius:6px}}
.note{{color:#57606a;font-size:12px;margin:4px 0}}
.muted{{color:#6e7781;font-size:13px}}
.ok{{color:#116329;font-weight:600}} .bad{{color:#b42318;font-weight:700}} .warn{{color:#8a6d1f}}
.sev-P0{{color:#b42318;font-weight:700}} .sev-P1{{color:#c4320a;font-weight:600}} .sev-P2{{color:#8a6d1f}} .sev-P3{{color:#475467}}
.gallery{{display:flex;flex-wrap:wrap;gap:12px}} .card{{border:1px solid #d8dee4;border-radius:8px;padding:8px;max-width:560px}}
figure{{margin:0 6px 6px 0;display:inline-block}} img{{max-width:260px;border:1px solid #d8dee4;border-radius:4px}}
figcaption{{font-size:12px;color:#57606a}}
.spark{{display:flex;align-items:flex-end;gap:6px;height:110px;border-bottom:1px solid #d8dee4;margin-top:8px}}
.bar{{background:#0969da;width:28px;border-radius:3px 3px 0 0;display:flex;align-items:flex-end;justify-content:center}}
.bar span{{font-size:10px;color:#57606a;transform:translateY(-16px)}}
</style></head><body>
<h1>{title}</h1>
<p class='note'>页面：{page} · 设计：{design} · 视口：{viewport}</p>
{coverage_section}
{summary_section}
{match_section}
{scenario_section}
{shot_section}
{heat_section}
{style_section}
{icon_section}
{key_section}
{defect_section}
{pending_section}
{regression_section}
{degradation_section}
{enhance_section}
{threshold_section}
</body></html>""".format(
        title=html.escape(str(payload.get("title", "Figma UI Parity 报告"))),
        page=html.escape(str(payload.get("page") or meta.get("pageUrl", ""))),
        design=html.escape(str(payload.get("designRef") or meta.get("figmaKey", ""))),
        viewport=html.escape(str(payload.get("viewport", ""))),
        coverage_section=section("检查维度完成度", dimension_table(coverage or {}, checks, dimensions),
                                 "7.x 为检查维度编号，定义见 references/check-dimensions.md；覆盖率由 coverage_gate.py 计算"),
        summary_section=section("执行摘要", kv_table(head)),
        match_section=section("对象匹配与坐标基准", kv_table({
            "位置基准": payload.get("positionBasis", "未记录"),
            "坐标偏移 dx,dy": str(payload.get("offsets", "")),
            "缩放": str(payload.get("scale", "")),
            "可比性": str(payload.get("comparability", "")),
        }), "位置比对前必须归一坐标基准，否则整体偏移会被误报为每元素位移"),
        scenario_section=section("场景覆盖", scenario_coverage_table(scenarios) if isinstance(scenarios, dict) else "<p class='muted'>无场景统计</p>"),
        shot_section=section("并排截图", gallery(payload.get("screenshots") or [], [("design", "设计稿"), ("page", "实际页面")])),
        heat_section=section("差异热力图", gallery(payload.get("heatmaps") or [], [("image", "热力图")])),
        style_section=section("样式分组差异", style_diff_groups(style_diffs)),
        icon_section=section("图标与图片差异",
                             style_diff_groups([d for d in style_diffs if str(d.get("dimension")) in ("7.3", "7.5", "7.24")])
                             + gallery(payload.get("iconDiffs") or [], [("design", "设计图标"), ("page", "实际图标")])),
        key_section=section("关键差异汇总", table(["等级", "类型", "现象", "修复建议", "定位", "复现"], defect_rows[:20])),
        defect_section=section("缺陷清单（全部 {} 条）".format(len(defects)),
                              table(["#", "等级", "类型", "现象与指标", "修复建议", "元素定位", "复现步骤"], defect_rows)),
        pending_section=section("待确认与数据缺失", table(["维度", "现象", "状态", "原因/实际"], pending_rows)),
        regression_section=section("回归对比", table(["类别", "内容", "维度"], reg_rows), "新增 / 已修复 / 持续 / 波动 / 不可比"),
        degradation_section=section("降级能力", kv_table(payload.get("degradations") if isinstance(payload.get("degradations"), dict) else {})),
        enhance_section=section("增强视图：diffScore 趋势", sparkline(payload.get("history") or [])),
        threshold_section=section("阈值与忽略项声明", kv_table({
            "像素阈值": str((payload.get("thresholds") or {}).get("pixel", "未声明") if isinstance(payload.get("thresholds"), dict) else "未声明"),
            "区域差异百分比": str((payload.get("thresholds") or {}).get("regionPercent", "未声明") if isinstance(payload.get("thresholds"), dict) else "未声明"),
            "属性级容差": str(payload.get("tolerance", "")),
            "本次生效忽略项": str(payload.get("ignoredRegions", "无")),
        }), "报告必须声明所用阈值，避免同一张图在两套口径下结论不同"),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 HTML / JSON / CSV 三格式对比报告")
    ap.add_argument("--input", required=True, type=Path, help="上游报告 JSON")
    ap.add_argument("--outdir", required=True, type=Path)
    ap.add_argument("--title", default="Figma UI Parity 报告")
    ap.add_argument("--formats", default="html,json,csv")
    ap.add_argument("--dimensions", type=Path, default=default_dimensions_path())
    args = ap.parse_args()

    if not args.input.exists():
        print("输入文件不存在: {}".format(args.input), file=sys.stderr)
        return 2
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        payload = {"defects": payload}

    style_diffs = [d for d in (payload.get("styleDiffs") or []) if isinstance(d, dict) and d.get("status") == "confirmed"]
    base = collect_defects(payload) or style_diffs
    defects, duplicates = dedupe(base)
    # 兜底：上游只带 severityHint（如旧版产出端）时映射为 severity（schema 必填），
    # 否则 CSV 等级列与 HTML 等级计数全部为空。
    for d in defects:
        if not d.get("severity") and d.get("severityHint"):
            d["severity"] = str(d["severityHint"])
    defects = sort_defects(defects)

    payload = dict(payload)
    payload["title"] = args.title
    payload["generatedAt"] = datetime.now().isoformat(timespec="seconds")
    payload["defects"] = defects
    payload["summary"] = dict(payload.get("summary") or {})
    payload["summary"]["defectTotal"] = len(defects)
    payload["summary"]["duplicatesMerged"] = duplicates

    formats = {f.strip().lower() for f in args.formats.split(",") if f.strip()}
    outdir = args.outdir
    written = {}
    if "html" in formats:
        path = outdir / "report.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_html(payload, defects, duplicates, load_dimension_names(args.dimensions)), encoding="utf-8")
        written["html"] = str(path)
    if "json" in formats:
        path = outdir / "report.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        written["json"] = str(path)
    if "csv" in formats:
        path = outdir / "defects.csv"
        write_csv(path, defects)
        written["csv"] = str(path)

    print(json.dumps({"defects": len(defects), "duplicatesMerged": duplicates, "outputs": written}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
