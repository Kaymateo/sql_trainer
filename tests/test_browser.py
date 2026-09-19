"""真实浏览器验收（playwright + chromium）：渲染、交互、判题全流程 + 截图留证。

用法：/tmp/pwenv/bin/python tests/test_browser.py
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:3000"
SHOT = Path("/home/user/sql_trainer/tests/screenshots")
SHOT.mkdir(parents=True, exist_ok=True)

ok = fail = 0
console_errors: list[str] = []


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"✅ {name} {extra}")
    else:
        fail += 1
        print(f"❌ {name} {extra}")


def api(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode())


with sync_playwright() as pw:
    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1680, "height": 1000})
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}"))

    # 1. 首页渲染
    page.goto(BASE, wait_until="networkidle")
    page.wait_for_selector(".ex-item", timeout=30000)
    items = page.locator(".ex-item").count()
    check("题库侧栏渲染题目列表", items >= 40, f"{items} 条")
    title = page.locator(".card h2").first.inner_text()
    check("题目卡片渲染标题", len(title) > 3, f"当前题目：{title}")
    check("题目正文（Markdown）已渲染", page.locator(".card .md").first.inner_text().__len__() > 30)
    check("CodeMirror 编辑器已挂载", page.locator(".CodeMirror").count() == 1)
    page.screenshot(path=str(SHOT / "1-题库-出题.png"), full_page=False)

    # 2. 数据字典展开
    page.locator("details summary").first.click()
    page.wait_for_timeout(400)
    n_tables = page.locator(".schema-table").count()
    n_samples = page.locator(".sample table.grid").count()
    check("数据字典可展开（表结构 + 样例数据）", n_tables >= 1 and n_samples >= 1,
          f"{n_tables} 张表 / {n_samples} 个样例表")
    page.screenshot(path=str(SHOT / "2-数据字典与样例数据.png"))

    # 3. 提示功能
    page.click("#btn-hint")
    page.wait_for_timeout(300)
    check("提示可逐级展示", "提示 1 /" in page.locator("#hintbox").inner_text())

    # 4. 运行（自由运行）
    page.evaluate("S.editor.setValue(\"SELECT category, COUNT(*) AS cnt FROM dim_product GROUP BY 1 ORDER BY 1\")")
    page.click("#btn-run")
    page.wait_for_selector("#result .verdict", timeout=30000)
    page.wait_for_timeout(300)
    run_rows = page.locator("#result table.grid tbody tr").count()
    check("「仅运行」返回结果表", run_rows > 0, f"{run_rows} 行渲染")
    page.screenshot(path=str(SHOT / "3-运行结果.png"))

    # 5. 故意提交错解 → 必须判失败并给出反馈
    page.evaluate("S.editor.setValue(\"SELECT 'wrong' AS x\")")
    page.click("#btn-submit")
    page.wait_for_selector("#result .verdict", timeout=30000)
    page.wait_for_timeout(500)
    vtext = page.locator("#result .verdict").inner_text()
    check("错解被判失败并给出反馈", "未通过" in vtext, vtext.replace("\n", " ")[:80])
    page.screenshot(path=str(SHOT / "4-错解反馈.png"))

    # 6. 提交参考解 → 必须判通过（Result tabs 齐全）
    ex_id = page.evaluate("S.cur.id")
    seed = page.evaluate("S.cur.seed")
    sol = api(f"/api/solution?id={ex_id}&seed={seed}")["solution"]
    page.evaluate("sql => S.editor.setValue(sql)", sol)
    page.click("#btn-submit")
    page.wait_for_timeout(200)
    page.wait_for_function(
        "() => document.querySelector('#result .verdict') && document.querySelector('#result .verdict').innerText.includes('通过')",
        timeout=30000)
    page.wait_for_timeout(400)
    vtext = page.locator("#result .verdict").inner_text()
    check("参考解被判通过", "通过" in vtext, vtext.replace("\n", " ")[:70])
    tabs = page.locator("#result .tabs button").all_inner_texts()
    check("结果区包含 4 个标签页", len(tabs) == 4, str(tabs))
    page.locator("#result .tabs button").nth(3).click()   # 讲解
    page.wait_for_timeout(300)
    notes_txt = page.locator("#notes-md").inner_text()
    check("讲解（考点解析）已渲染", len(notes_txt) > 200, f"{len(notes_txt)} 字")
    page.screenshot(path=str(SHOT / "5-判题通过与讲解.png"))

    # 7. 换一道新数据（随机出题）
    old_seed = page.evaluate("S.cur.seed")
    page.click("#btn-new")
    page.wait_for_timeout(2500)
    page.wait_for_selector(".CodeMirror", timeout=30000)
    new_seed = page.evaluate("S.cur.seed")
    check("换一道新数据（重新随机出题）", new_seed != old_seed, f"seed {old_seed} → {new_seed}")

    # 8. 侧栏搜索 + 切题
    page.fill("#search", "留存")
    page.wait_for_timeout(500)
    n = page.locator(".ex-item").count()
    check("搜索过滤题目", 0 < n < items, f"命中 {n} 条")
    page.locator(".ex-item").first.click()
    page.wait_for_timeout(2000)
    check("点击题目可切换", page.evaluate("S.cur.title") != "")

    # 9. 理论卡片视图
    page.click("nav button[data-view='flash']")
    page.wait_for_selector(".flash-card", timeout=30000)
    cards = page.locator(".flash-card").count()
    check("理论卡片视图渲染", cards >= 100, f"{cards} 张卡片")
    page.locator("[data-show]").first.click()
    page.wait_for_timeout(200)
    check("卡片可展开答案", page.locator("[data-show]").first.inner_text() == "隐藏答案")
    page.screenshot(path=str(SHOT / "6-理论卡片.png"), full_page=False)

    # 10. 统计视图
    page.click("nav button[data-view='stats']")
    page.wait_for_selector(".stat-box", timeout=30000)
    boxes = page.locator(".stat-box").count()
    check("统计视图渲染 KPI 卡片", boxes >= 6, f"{boxes} 个指标卡")
    page.screenshot(path=str(SHOT / "7-统计面板.png"))

    # 11. 错题本视图
    page.click("nav button[data-view='wrong']")
    page.wait_for_timeout(1200)
    wb = page.locator(".content").inner_text()
    check("错题本视图渲染", "错题本" in wb and "待攻克" in wb)
    page.screenshot(path=str(SHOT / "8-错题本.png"))

    # 12. 回到题库，检查刷新后进度仍在（持久化）
    page.click("nav button[data-view='bank']")
    page.wait_for_timeout(1500)
    passed_txt = page.locator("#kpi-passed").inner_text()
    check("顶栏进度统计已更新", passed_txt.isdigit() and int(passed_txt) >= 1, f"已通过 {passed_txt} 题")

    # 13. 无控制台报错
    real_errors = [e for e in console_errors if "favicon" not in e.lower()]
    check("浏览器控制台无 JS 报错", not real_errors, str(real_errors[:2]))

    browser.close()

print(f"\n{'=' * 70}\n浏览器验收：通过 {ok} 项，失败 {fail} 项")
print("截图：", ", ".join(p.name for p in sorted(SHOT.glob("*.png"))))
sys.exit(1 if fail else 0)
