"""题库自检：对每道题跑多个随机种子，验证参考解能跑通、有结果、判题链路正确。

用法：PYTHONPATH=~/sql_trainer .venv/bin/python tests/test_bank.py [种子数]
"""
import random
import sys
import time
import traceback

import bank
import engine as E

N_SEEDS = int(sys.argv[1]) if len(sys.argv) > 1 else 8
SEEDS = [1, 7, 42, 99, 123, 2026, 31337, 555, 8080, 66, 2024, 777]

fails: list[str] = []
slow: list[tuple[str, float]] = []
t_all = time.time()
built_cache: dict[tuple, object] = {}

for ex in bank.ALL:
    t0 = time.time()
    n_rows_seen, err = None, None
    try:
        for i in range(N_SEEDS):
            seed = SEEDS[i % len(SEEDS)]
            rnd = random.Random(seed * 7919 + 13)
            r = ex.render(rnd)
            key = (seed, ex.scale, tuple(ex.tables))
            if key not in built_cache:
                con, _ = E.build_instance(seed, ex.scale, ex.tables)
                built_cache.clear()          # 只缓存一个实例，避免内存堆积
                built_cache[key] = con
            con = built_cache[key]
            sql = E.guard(r["solution"])
            ref = E.run_query(con, sql)
            n_rows = len(ref["rows"])
            if n_rows == 0:
                raise AssertionError("参考解返回 0 行（题目可能无解）")
            # 判题链路：与自身对拍必须通过
            same = E.compare(ref, E.run_query(con, E.guard(r["solution"])))
            if not same["ok"]:
                raise AssertionError(f"自对拍失败：{same['reason']}")
            # 反例：加一个不可能的过滤条件，必须判失败
            neg = E.run_query(con, f"SELECT * FROM ({r['solution'].rstrip(';')}) t WHERE 1 = 2")
            if E.compare(neg, ref)["ok"]:
                raise AssertionError("错解被判通过（判题有漏洞）")
            if r["prompt"].strip() == "" or r["solution"].strip() == "":
                raise AssertionError("题目或参考解为空")
            n_rows_seen = n_rows if n_rows_seen is None else min(n_rows_seen, n_rows)
    except Exception as e:  # noqa: BLE001
        fails.append(f"{ex.id}: {type(e).__name__}: {e}")
        err = traceback.format_exc(limit=3)
    dt_s = time.time() - t0
    slow.append((ex.id, dt_s))
    flag = "❌" if err else "✅"
    print(f"{flag} {ex.id:<26} {ex.category:<8} {bank.DIFF_TEXT[ex.difficulty]:<3} "
          f"最小行数={n_rows_seen} {dt_s:.1f}s/{N_SEEDS}种子")
    if err:
        print("   ", err.replace("\n", " ")[:200])

print("\n" + "=" * 78)
st = bank.stats()
print(f"题目总数 {st['total']}｜分类分布 {st['by_category']}｜难度分布 {st['by_difficulty']}")
print(f"总耗时 {time.time() - t_all:.1f}s，最慢: " +
      ", ".join(f"{i}({s:.1f}s)" for i, s in sorted(slow, key=lambda x: -x[1])[:5]))
if fails:
    print(f"\n❌ 失败 {len(fails)} 项：")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("\n✅ 全部题目通过：参考解可执行、有结果、判题链路正确、错解会被判失败")
