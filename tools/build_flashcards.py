#!/usr/bin/env python3
"""从《大数据开发面试复习路线》文档第 5 章提取理论题库 → data/flashcards.json"""
from __future__ import annotations

import json
import re
from pathlib import Path

SRC = Path("/home/user/bigdata_offer/bigdata_interview_roadmap.md")
OUT = Path(__file__).resolve().parent.parent / "data" / "flashcards.json"


def parse() -> list[dict]:
    if not SRC.exists():
        raise SystemExit(f"找不到来源文档：{SRC}")
    cards: list[dict] = []
    module = None
    for ln in SRC.read_text(encoding="utf-8").splitlines():
        if re.match(r"^##\s", ln):        # 进入别的章节 → 停止收集第 5 章的表格
            module = None
            continue
        m = re.match(r"^###\s+5\.(\d+)\s+(.+)$", ln)
        if m:
            module = re.split(r"[（(]", m.group(2))[0].strip()
            continue
        if not module or not ln.startswith("|"):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        if cells[0] in ("#", "") or set(cells[0]) <= set("-: "):
            continue                      # 表头 / 分隔行
        q, a = cells[1], cells[2]
        if not q or not a:
            continue
        cards.append({
            "id": f"c{len(cards) + 1:03d}",
            "module": module,
            "q": q,
            "a": a,
        })
    return cards


def main() -> None:
    cards = parse()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(cards, ensure_ascii=False, indent=1), encoding="utf-8")
    by_mod: dict[str, int] = {}
    for c in cards:
        by_mod[c["module"]] = by_mod.get(c["module"], 0) + 1
    print(f"✅ 提取理论卡片 {len(cards)} 张 → {OUT}")
    for k, v in by_mod.items():
        print(f"   {k}: {v}")
    assert len(cards) >= 100, "卡片数量异常，检查来源文档格式"


if __name__ == "__main__":
    main()
