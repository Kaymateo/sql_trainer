"""端到端验收：模拟浏览器完整走一遍（出题 → 运行 → 提交 → 判错 → 拦截 → 统计）。"""
import json
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:3000"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return r.status, json.loads(r.read().decode())


def post(path, obj):
    req = urllib.request.Request(BASE + path, data=json.dumps(obj).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


ok_cnt = fail_cnt = 0


def check(name, cond, extra=""):
    global ok_cnt, fail_cnt
    if cond:
        ok_cnt += 1
        print(f"✅ {name} {extra}")
    else:
        fail_cnt += 1
        print(f"❌ {name} {extra}")


# 1. 健康检查 + 首页 + 静态资源
st, h = get("/api/health")
check("健康检查", st == 200 and h["ok"], f"表 {len(h['tables'])} 张")
for f in ["/", "/styles.css", "/app.js", "/vendor/codemirror.min.js", "/vendor/sql.min.js"]:
    with urllib.request.urlopen(BASE + f, timeout=30) as r:
        check(f"静态资源 {f}", r.status == 200, f"{len(r.read())}B")

# 2. 目录
st, cat = get("/api/catalog")
check("题目目录", st == 200 and len(cat["exercises"]) == 42,
      f"{len(cat['exercises'])} 题 / {len(cat['categories'])} 分类")

# 3. 为每道题出一次题（随机种子）+ 参考解必须能通过判题
print("\n--- 逐题验收：出题 + 参考解提交（应全部通过）---")
bad = []
for ex in cat["exercises"]:
    t0 = time.time()
    st, inst = get(f"/api/exercise?id={ex['id']}")
    if st != 200:
        bad.append((ex["id"], "出题失败"))
        continue
    e = inst["exercise"]
    st, sol = get(f"/api/solution?id={ex['id']}&seed={e['seed']}")
    st, res = post("/api/submit", {"id": ex["id"], "seed": e["seed"], "sql": sol["solution"],
                                   "hints_used": 0, "used_solution": True})
    dur = time.time() - t0
    if not res.get("ok"):
        bad.append((ex["id"], res.get("verdict") or res.get("error")))
    print(f"  {ex['id']:<26} {'✅' if res.get('ok') else '❌'} "
          f"{res.get('your_total', '?')} 行 / 参考 {res.get('ref_total', '?')} 行  {dur:.1f}s")
check("全部 42 题参考解可通过判题", not bad, f"失败：{bad}" if bad else "")

# 4. 错解必须判失败（且给出有效反馈）
st, inst = get("/api/exercise?id=win_topn_category")
e = inst["exercise"]
st, wrong = post("/api/submit", {"id": e["id"], "seed": e["seed"],
                                 "sql": "SELECT category, product_name, '0.00' AS sales FROM dim_product LIMIT 5",
                                 "hints_used": 1, "used_solution": False})
check("错解被判失败", wrong["ok"] is False and "不一致" in wrong["verdict"],
      f"判定={wrong.get('verdict')}｜{str(wrong.get('detail'))[:60]}…")

# 5. 安全护栏
for sql, why in [("DROP TABLE dim_user", "DDL"),
                 ("DELETE FROM dwd_order", "DML"),
                 ("SELECT * FROM '/etc/passwd'", "读文件"),
                 ("SELECT 1; SELECT 2", "多语句"),
                 ("INSTALL httpfs", "安装扩展")]:
    st, r = post("/api/run", {"id": e["id"], "seed": e["seed"], "sql": sql})
    check(f"拦截 {why}", r.get("ok") is False, (r.get("error") or r.get("detail", ""))[:70])

# 6. 正常运行（不判分）
st, run = post("/api/run", {"id": e["id"], "seed": e["seed"],
                            "sql": "SELECT category, COUNT(*) c FROM dim_product GROUP BY 1 ORDER BY 1"})
check("自由运行返回结果", run.get("ok") and run["total_rows"] > 0,
      f"{run.get('total_rows')} 行, 列={run.get('columns')}")

# 7. 统计 & 错题本 & 理论卡片
st, stats = get("/api/stats")
passed = sum(1 for v in stats["progress"]["exercises"].values() if v["passed"])
check("统计接口", st == 200 and passed >= 42, f"已通过 {passed} 题，通过率 {stats['progress']['pass_rate']}%")
check("错题本记录失败提交", any(w["id"] == "win_topn_category" for w in stats["mistakes"]),
      f"错过 {len(stats['mistakes'])} 道（待攻克 {len(stats['wrongbook'])} 道）")
st, fc = get("/api/flashcards")
check("理论卡片", len(fc["cards"]) == 136, f"{len(fc['cards'])} 张")
st, _ = post("/api/flashcard", {"id": fc["cards"][0]["id"], "status": "已掌握"})
st, fc2 = get("/api/flashcards")
check("卡片状态持久化", fc2["cards"][0]["status"] == "已掌握")
st, _ = post("/api/note", {"id": e["id"], "content": "测试笔记：列序不影响判题"})
st, stats2 = get("/api/stats")
check("笔记持久化", stats2["notes"].get(e["id"], "").startswith("测试笔记"))

# 8. 换一道新数据：同一题目不同种子 → 数据不同但题目可解
st, a = get("/api/exercise?id=ser_consecutive_login")
st, b = get("/api/exercise?id=ser_consecutive_login")
check("随机出题（种子不同）", a["exercise"]["seed"] != b["exercise"]["seed"],
      f"seed {a['exercise']['seed']} vs {b['exercise']['seed']}")
st, r = get(f"/api/solution?id=ser_consecutive_login&seed={b['exercise']['seed']}")
st, res = post("/api/submit", {"id": "ser_consecutive_login", "seed": b["exercise"]["seed"],
                               "sql": r["solution"], "hints_used": 0, "used_solution": True})
check("新种子下参考解仍通过", res.get("ok") is True, f"{res.get('your_total')} 行")

print(f"\n{'=' * 70}\n通过 {ok_cnt} 项，失败 {fail_cnt} 项")
raise SystemExit(1 if fail_cnt else 0)
