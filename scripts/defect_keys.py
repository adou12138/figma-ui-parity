# -*- coding: utf-8 -*-
"""缺陷容器键的唯一来源。

figma-ui-parity 的 report 里「缺陷可能挂在哪些顶层键下」此前在四处各留一份、
且互不一致，已实测造成两类静默蒸发：

- ``gen_excel_fallback`` 漏 ``styleDiffs`` ⇒ Excel 交付件 0 条缺陷，且 stderr 还打印
  「请检查 report.json 是否缺少缺陷数组键」——键明明在里面，这条警告本身把排查方向带偏；
- ``validate_defects`` 漏 ``findings`` / ``diffs`` ⇒ findings 型报告 checked=0，
  严格模式误报 rc=6「缺少显式缺陷数组键」，合法形状被判成「忘填」。

键表统一到本模块，改键只改这一处。**筛选策略**（只收 status=confirmed？取第一路
还是取并集？）属各 consumer 的语义差异，仍由各自保留，不在此统一。
"""

# 有序：越靠前越「权威」。采用「取第一路非空」策略的 consumer 按此序试探。
# violations 是 assert_constraints 的 7.4 约束违反条目（自带 status=confirmed），
# 与 findings 同级：它此前没有任何消费方，7.4 的缺陷产出通道是断的。
CONTAINER_KEYS = ("defects", "defectList", "styleDiffs", "diffs", "findings",
                  "violations", "issues")

# 历史 dict 形 diffs{high,medium,low}——与上面的列表形 diffs 同名不同形状，消费前须判形状。
LEGACY_DICT_KEY = "diffs"

# 缺陷去重签名只取结构化字段：自然语言描述（symptom/detail）措辞差一个空格不该算两条。
SIGNATURE_FIELDS = ("dimension", "property", "category", "page", "target",
                    "expected", "actual")


def signature(item: dict) -> tuple:
    """缺陷条目的去重签名（跨来源合并时用）。"""
    if not isinstance(item, dict):
        return ()
    return tuple(str(item.get(f)) for f in SIGNATURE_FIELDS)


def iter_containers(report: dict, first_only: bool = False):
    """按 CONTAINER_KEYS 序产出 (key, list) 。

    first_only=True 时只产出第一路非空列表（「取第一路」策略的 consumer 用），
    否则产出全部非空列表（「取并集」策略用）。
    """
    if not isinstance(report, dict):
        return
    for key in CONTAINER_KEYS:
        value = report.get(key)
        if isinstance(value, list) and value:
            yield key, value
            if first_only:
                return
