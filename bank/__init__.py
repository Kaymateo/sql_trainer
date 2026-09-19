"""题库注册表：汇总所有题目并提供查询接口。"""
from __future__ import annotations

from bank import ex_metric, ex_model, ex_window
from bank.spec import DIFF_LABEL, Exercise

ALL: list[Exercise] = ex_window.EXERCISES + ex_metric.EXERCISES + ex_model.EXERCISES
BY_ID: dict[str, Exercise] = {e.id: e for e in ALL}
assert len(BY_ID) == len(ALL), "题目 id 重复：" + str([e.id for e in ALL if [x.id for x in ALL].count(e.id) > 1])

CATEGORY_ORDER = [
    "窗口函数与排名",
    "连续区间问题",
    "留存与漏斗",
    "聚合进阶",
    "行列转换",
    "多表关联与集合",
    "日期与时间",
    "数仓口径与建模",
]
_extra = [e.category for e in ALL if e.category not in CATEGORY_ORDER]
CATEGORIES = CATEGORY_ORDER + sorted(set(_extra))

DIFF_TEXT = {1: "★", 2: "★★", 3: "★★★"}


def catalog() -> list[dict]:
    """题目索引（不含答案），前端左侧列表用。"""
    return [
        {
            "id": e.id,
            "category": e.category,
            "difficulty": e.difficulty,
            "diff_text": DIFF_TEXT[e.difficulty],
            "title": e.title,
            "knowledge": e.knowledge,
            "tables": e.tables,
        }
        for e in ALL
    ]


def stats() -> dict:
    by_cat: dict[str, int] = {}
    by_diff: dict[str, int] = {}
    for e in ALL:
        by_cat[e.category] = by_cat.get(e.category, 0) + 1
        by_diff[DIFF_LABEL[e.difficulty]] = by_diff.get(DIFF_LABEL[e.difficulty], 0) + 1
    return {"total": len(ALL), "by_category": by_cat, "by_difficulty": by_diff}
