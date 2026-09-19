"""题目规格定义：一个 Exercise = 模板（题目/参考解/提示/讲解）+ 随机参数生成器。

出题流程：params(rnd) 生成参数 → 模板用参数渲染出题目文本与参考解
→ 参考解在随机数据上跑一遍得到标准答案 → 判题时与用户结果对拍。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

DIFF_LABEL = {1: "基础", 2: "进阶", 3: "挑战"}


@dataclass
class Exercise:
    id: str
    category: str
    difficulty: int
    title: str
    knowledge: list[str]
    tables: list[str]
    prompt: str
    solution: str
    hints: list[str] = field(default_factory=list)
    notes: str = ""
    params: Callable[[object], dict] | None = None
    scale: float = 1.0

    def render(self, rnd) -> dict:
        p = dict(self.params(rnd)) if self.params else {}
        # 自动派生常用参数：动态列名 / IN 列表 / 展示文本
        cats = p.get("cats")
        if cats:
            p["cats_text"] = "、".join(cats)
            p["sql_in_cats"] = ", ".join(f"'{c}'" for c in cats)
            p["sql_quoted_cats"] = ", ".join(f'"{c}"' for c in cats)
            p["sql_cols_cats"] = ",\n  ".join(
                f'ROUND(SUM(CASE WHEN p.category = \'{c}\' THEN o.amount ELSE 0 END), 2) AS "{c}"'
                for c in cats
            )
        return {
            "params": p,
            # 参数里以 sql_ 开头的只用于拼装参考解，不参与题目文本渲染
            "prompt": self.prompt.format(**{k: v for k, v in p.items() if not k.startswith("sql_")}),
            "solution": self.solution.format(**p),
            "hints": [h.format(**p) for h in self.hints],
            "notes": self.notes.format(**p),
        }


def case_pivot(col_expr: str, values: list[str], alias_all: str = "其他") -> str:
    """生成行列转换用的 CASE WHEN 列片段。"""
    return ",\n  ".join(
        f'ROUND(SUM(CASE WHEN {col_expr} = \'{v}\' THEN o.amount ELSE 0 END), 2) AS "{v}"'
        for v in values
    )


def in_list(values: list[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)
