#!/usr/bin/env python3
"""SQL 训练平台 · 服务端（Python 标准库 + DuckDB，无 Web 框架依赖）

启动：  .venv/bin/python app.py [端口]        默认 3000
访问：  http://localhost:3000
"""
from __future__ import annotations

import json
import os
import random
import sqlite3
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import bank
import engine as E

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "progress.db"
FLASH_PATH = DATA_DIR / "flashcards.json"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", "3000"))

# ─────────────────────────── 实例缓存 ───────────────────────────
class InstanceStore:
    """按 (题目, 种子) 缓存已建好的 DuckDB 实例；超时中断后会丢弃以便重建。"""

    def __init__(self, maxsize: int = 6):
        self.maxsize = maxsize
        self._cache: dict[tuple[str, int], tuple[object, object, float]] = {}
        self._lru: list[tuple[str, int]] = []
        self._lock = threading.Lock()

    def get(self, ex: bank.Exercise, seed: int):
        key = (ex.id, seed)
        with self._lock:
            if key in self._cache:
                con, ds, ceiling = self._cache[key]
                self._lru.remove(key)
                self._lru.append(key)
                return con, ds
        t0 = time.time()
        con, ds = E.build_instance(seed, ex.scale, ex.tables)
        with self._lock:
            while len(self._lru) >= self.maxsize and self._lru:
                old = self._lru.pop(0)
                self._cache.pop(old, None)
            self._cache[key] = (con, ds, time.time() - t0)
            self._lru.append(key)
        return con, ds

    def drop(self, ex_id: str, seed: int) -> None:
        with self._lock:
            key = (ex_id, seed)
            self._cache.pop(key, None)
            if key in self._lru:
                self._lru.remove(key)

    def info(self) -> dict:
        with self._lock:
            return {
                "cached": len(self._lru),
                "items": [{"exercise": k[0], "seed": k[1], "build_seconds": round(v[2], 2)}
                          for k, v in self._cache.items()],
            }


STORE = InstanceStore()
BUILD_LOCK = threading.Lock()     # 首次建实例串行化，避免并发占满内存

# ─────────────────────────── 进度库 ───────────────────────────
def db_connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def db_init() -> None:
    with db_connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS attempts(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ex_id TEXT NOT NULL, seed INTEGER NOT NULL, sql TEXT NOT NULL,
              ok INTEGER NOT NULL, reason TEXT, detail TEXT,
              elapsed_ms INTEGER, hints_used INTEGER DEFAULT 0, used_solution INTEGER DEFAULT 0,
              created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_attempts_ex ON attempts(ex_id);
            CREATE TABLE IF NOT EXISTS notes(
              ex_id TEXT PRIMARY KEY, content TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS flash(
              card_id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TEXT NOT NULL);
            """
        )


def db_progress() -> dict:
    with db_connect() as con:
        rows = con.execute(
            """SELECT ex_id, SUM(ok) AS ok_cnt, COUNT(*) AS tries, MAX(created_at) AS last_at,
                      MAX(hints_used) AS hints, MAX(used_solution) AS used_sol
               FROM attempts GROUP BY ex_id"""
        ).fetchall()
        agg = con.execute(
            """SELECT COUNT(*) AS total, SUM(ok) AS passed,
                      SUM(CASE WHEN ok=1 THEN elapsed_ms ELSE 0 END) AS passed_ms,
                      MAX(created_at) AS last_at FROM attempts"""
        ).fetchone()
        day = con.execute(
            "SELECT COUNT(DISTINCT substr(created_at,1,10)) AS days FROM attempts WHERE ok=1"
        ).fetchone()
    prog: dict[str, dict] = {}
    for r in rows:
        prog[r["ex_id"]] = {"passed": bool(r["ok_cnt"]), "tries": r["tries"],
                            "last_at": r["last_at"], "hints": r["hints"] or 0,
                            "used_solution": bool(r["used_sol"])}
    total = agg["total"] or 0
    return {
        "exercises": prog,
        "total_submits": total,
        "total_passed": agg["passed"] or 0,
        "pass_rate": round((agg["passed"] or 0) * 100.0 / total, 1) if total else 0.0,
        "practice_days": day["days"] or 0,
        "avg_passed_ms": int((agg["passed_ms"] or 0) / (agg["passed"] or 1)) if total else 0,
        "last_at": agg["last_at"],
    }


def db_record(ex_id, seed, sql, ok, reason, detail, elapsed_ms, hints_used, used_solution) -> None:
    with db_connect() as con:
        con.execute(
            """INSERT INTO attempts(ex_id, seed, sql, ok, reason, detail, elapsed_ms,
                                    hints_used, used_solution, created_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (ex_id, seed, sql, int(ok), reason, detail[:2000], elapsed_ms,
             hints_used, int(used_solution), time.strftime("%Y-%m-%d %H:%M:%S")),
        )


def db_mistakes() -> list[dict]:
    """所有出现过失败提交的题目（含已攻克的，保留复盘记录）。"""
    with db_connect() as con:
        rows = con.execute(
            """SELECT a.ex_id,
                      SUM(CASE WHEN a.ok = 0 THEN 1 ELSE 0 END) AS fails,
                      SUM(a.ok) AS oks,
                      MAX(a.created_at) AS last_at,
                      (SELECT x.detail FROM attempts x
                        WHERE x.ex_id = a.ex_id AND x.ok = 0 ORDER BY x.id DESC LIMIT 1) AS last_detail,
                      (SELECT n.content FROM notes n WHERE n.ex_id = a.ex_id) AS note
               FROM attempts a
               GROUP BY a.ex_id
               HAVING SUM(CASE WHEN a.ok = 0 THEN 1 ELSE 0 END) > 0
               ORDER BY (SUM(a.ok) = 0) DESC, fails DESC, last_at DESC"""
        ).fetchall()
    out = []
    for r in rows:
        ex = bank.BY_ID.get(r["ex_id"])
        if not ex:
            continue
        out.append({
            "id": ex.id, "title": ex.title, "category": ex.category,
            "difficulty": ex.difficulty, "fails": r["fails"], "last_at": r["last_at"],
            "passed_now": bool(r["oks"]), "last_detail": r["last_detail"], "note": r["note"],
        })
    return out


def db_notes() -> dict:
    with db_connect() as con:
        return {r["ex_id"]: r["content"] for r in con.execute("SELECT * FROM notes")}


def load_flashcards() -> list[dict]:
    if not FLASH_PATH.exists():
        return []
    cards = json.loads(FLASH_PATH.read_text(encoding="utf-8"))
    with db_connect() as con:
        state = {r["card_id"]: r["status"] for r in con.execute("SELECT * FROM flash")}
    for c in cards:
        c["status"] = state.get(c["id"], "未掌握")
    return cards


# ─────────────────────────── 业务动作 ───────────────────────────
def make_instance(ex: bank.Exercise, seed: int | None) -> dict:
    seed = seed if seed else random.randint(1, 10**6)
    rnd = random.Random(seed * 7919 + 13)
    r = ex.render(rnd)
    with BUILD_LOCK:
        con, _ = STORE.get(ex, seed)
    schema = {t: {"columns": E.table_schema(con, t), "sample": E.table_sample(con, t, 4)}
              for t in ex.tables}
    return {
        "id": ex.id, "title": ex.title, "category": ex.category,
        "difficulty": ex.difficulty, "diff_text": bank.DIFF_TEXT[ex.difficulty],
        "knowledge": ex.knowledge, "seed": seed, "prompt": r["prompt"],
        "hints": r["hints"], "schema": schema, "tables": ex.tables,
    }


def get_con(ex: bank.Exercise, seed: int):
    with BUILD_LOCK:
        return STORE.get(ex, seed)[0]


def run_user_sql(ex_id: str, seed: int, sql: str) -> dict:
    ex = bank.BY_ID.get(ex_id)
    if not ex:
        return {"ok": False, "error": f"未找到题目 {ex_id}"}
    con = get_con(ex, seed)
    try:
        guarded = E.guard(sql)
    except E.QueryRejected as e:
        return {"ok": False, "error": str(e)}
    try:
        res = E.run_query(con, guarded, timeout=15, max_rows=50_000)
    except E.QueryRejected as e:
        STORE.drop(ex_id, seed)          # 超时后连接状态不可靠，下次重建
        return {"ok": False, "error": str(e)}
    except Exception as e:                # noqa: BLE001
        return {"ok": False, "error": f"执行异常：{e}"}
    return {
        "ok": True,
        "columns": [str(c) for c in res["columns"]],
        "rows": [[E._cell(v) for v in row] for row in res["rows"][:E.PREVIEW_ROWS]],
        "total_rows": len(res["rows"]),
        "truncated": len(res["rows"]) > E.PREVIEW_ROWS,
    }


def submit(ex_id: str, seed: int, sql: str, hints_used: int, used_solution: bool) -> dict:
    ex = bank.BY_ID.get(ex_id)
    if not ex:
        return {"ok": False, "error": f"未找到题目 {ex_id}"}
    con = get_con(ex, seed)
    rnd = random.Random(seed * 7919 + 13)
    ref_sql = ex.render(rnd)["solution"]
    t0 = time.time()
    try:
        user = E.run_query(con, E.guard(sql), timeout=15, max_rows=E.GRADE_ROW_CAP)
    except E.QueryRejected as e:
        STORE.drop(ex_id, seed)
        db_record(ex_id, seed, sql, False, "执行失败", str(e), 0, hints_used, used_solution)
        return {"ok": False, "verdict": "执行失败", "detail": str(e)}
    except Exception as e:                # noqa: BLE001
        return {"ok": False, "verdict": "执行异常", "detail": str(e)}
    elapsed_ms = int((time.time() - t0) * 1000)
    try:
        ref = E.run_query(con, E.guard(ref_sql), timeout=25, max_rows=E.GRADE_ROW_CAP)
    except Exception as e:                # noqa: BLE001
        return {"ok": False, "verdict": "参考解异常", "detail": f"请反馈：{e}"}

    verdict = E.compare(user, ref)
    db_record(ex_id, seed, sql, verdict["ok"], verdict["reason"], verdict["detail"],
              elapsed_ms, hints_used, used_solution)
    return {
        "ok": verdict["ok"],
        "verdict": verdict["reason"],
        "detail": verdict["detail"],
        "elapsed_ms": elapsed_ms,
        "your_rows": [[E._cell(v) for v in row] for row in user["rows"][:E.PREVIEW_ROWS]],
        "your_columns": [str(c) for c in user["columns"]],
        "your_total": len(user["rows"]),
        "ref_rows": [[E._cell(v) for v in row] for row in ref["rows"][:E.PREVIEW_ROWS]],
        "ref_columns": [str(c) for c in ref["columns"]],
        "ref_total": len(ref["rows"]),
    }


def solution(ex_id: str, seed: int) -> dict:
    ex = bank.BY_ID.get(ex_id)
    if not ex:
        return {"ok": False, "error": "未找到题目"}
    r = ex.render(random.Random((seed or 1) * 7919 + 13))
    return {"ok": True, "solution": r["solution"], "notes": r["notes"]}


def stats_payload() -> dict:
    prog = db_progress()
    cards = load_flashcards()
    mistakes = db_mistakes()
    cat_stat: dict[str, dict] = {}
    for ex in bank.ALL:
        d = cat_stat.setdefault(ex.category, {"total": 0, "passed": 0})
        d["total"] += 1
        if prog["exercises"].get(ex.id, {}).get("passed"):
            d["passed"] += 1
    diff_stat: dict[str, dict] = {}
    for ex in bank.ALL:
        label = bank.DIFF_TEXT[ex.difficulty]
        d = diff_stat.setdefault(label, {"total": 0, "passed": 0})
        d["total"] += 1
        if prog["exercises"].get(ex.id, {}).get("passed"):
            d["passed"] += 1
    return {
        "progress": prog,
        "categories": cat_stat,
        "difficulties": diff_stat,
        "mistakes": mistakes,
        "wrongbook": [m for m in mistakes if not m["passed_now"]],
        "notes": db_notes(),
        "flash_total": len(cards),
        "flash_mastered": sum(1 for c in cards if c["status"] == "已掌握"),
        "instances": STORE.info(),
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


# ─────────────────────────── HTTP ───────────────────────────
class Handler(BaseHTTPRequestHandler):
    server_version = "SqlTrainer/1.0"

    def log_message(self, fmt, *args):    # 静音，避免刷屏（错误仍会走 stderr）
        return

    # ── 工具 ──
    def _json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        try:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:                  # noqa: BLE001
            return {}

    def _file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404, "Not Found")
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }.get(path.suffix, "application/octet-stream")
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    # ── 路由 ──
    def do_GET(self):                      # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        p = u.path
        try:
            if p == "/api/health":
                return self._json({"ok": True, "tables": list(E.Dataset.DDL),
                                   "port": PORT, "time": time.time()})
            if p == "/api/catalog":
                return self._json({"categories": bank.CATEGORIES, "exercises": bank.catalog(),
                                   "bank_stats": bank.stats(), "progress": db_progress()})
            if p == "/api/exercise":
                ex = bank.BY_ID.get(q.get("id", [""])[0])
                if not ex:
                    return self._json({"ok": False, "error": "未找到题目"}, 404)
                seed = int(q["seed"][0]) if q.get("seed") else None
                return self._json({"ok": True, "exercise": make_instance(ex, seed)})
            if p == "/api/solution":
                return self._json(solution(q.get("id", [""])[0],
                                           int(q.get("seed", ["0"])[0] or 0)))
            if p == "/api/stats":
                return self._json(stats_payload())
            if p == "/api/flashcards":
                return self._json({"cards": load_flashcards()})
            if p.startswith("/api/"):
                return self._json({"ok": False, "error": f"未知接口 {p}"}, 404)

            rel = unquote(p).lstrip("/") or "index.html"
            target = (STATIC_DIR / rel).resolve()
            if STATIC_DIR.resolve() not in target.parents and target != STATIC_DIR.resolve():
                return self.send_error(403, "Forbidden")
            return self._file(target)
        except BrokenPipeError:
            return
        except Exception as e:             # noqa: BLE001
            traceback.print_exc()
            return self._json({"ok": False, "error": f"服务端异常：{e}"}, 500)

    def do_POST(self):                     # noqa: N802
        u = urlparse(self.path)
        b = self._body()
        try:
            if u.path == "/api/run":
                return self._json(run_user_sql(b.get("id", ""), int(b.get("seed") or 0),
                                               b.get("sql", "")))
            if u.path == "/api/submit":
                return self._json(submit(b.get("id", ""), int(b.get("seed") or 0),
                                         b.get("sql", ""), int(b.get("hints_used") or 0),
                                         bool(b.get("used_solution"))))
            if u.path == "/api/note":
                with db_connect() as con:
                    con.execute(
                        "INSERT INTO notes(ex_id, content, updated_at) VALUES(?,?,?) "
                        "ON CONFLICT(ex_id) DO UPDATE SET content=excluded.content, "
                        "updated_at=excluded.updated_at",
                        (b.get("id", ""), b.get("content", ""), time.strftime("%Y-%m-%d %H:%M:%S")))
                return self._json({"ok": True})
            if u.path == "/api/flashcard":
                with db_connect() as con:
                    con.execute(
                        "INSERT INTO flash(card_id, status, updated_at) VALUES(?,?,?) "
                        "ON CONFLICT(card_id) DO UPDATE SET status=excluded.status, "
                        "updated_at=excluded.updated_at",
                        (b.get("id", ""), b.get("status", "未掌握"),
                         time.strftime("%Y-%m-%d %H:%M:%S")))
                return self._json({"ok": True})
            return self._json({"ok": False, "error": f"未知接口 {u.path}"}, 404)
        except Exception as e:             # noqa: BLE001
            traceback.print_exc()
            return self._json({"ok": False, "error": f"服务端异常：{e}"}, 500)


def main() -> None:
    db_init()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"SQL 训练平台已启动： http://localhost:{PORT}")
    print(f"题目 {len(bank.ALL)} 道｜题库分类 {len(bank.CATEGORIES)} 个｜"
          f"理论卡片 {len(load_flashcards())} 张")
    print(f"数据目录 {DATA_DIR}｜日志请重定向到文件（本进程仅打印启动信息）")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
