import cProfile
import pstats
import time

import engine as E

t0 = time.time()
ds = E.Dataset(1, 1.0)
print("Dataset() only: %.2fs" % (time.time() - t0))

t0 = time.time()
con = E.new_connection()
print("new_connection(): %.2fs" % (time.time() - t0))

t0 = time.time()
tables = ["dim_user", "dim_product", "dwd_order", "dim_date", "dwd_login_log", "dim_user_zip"]
for t in tables:
    con.execute(E.Dataset.DDL[t])
    rows = ds.rows_for(t)
    t1 = time.time()
    if rows:
        con.executemany(f"INSERT INTO {t} VALUES ({','.join('?' * len(rows[0]))})", rows)
    print(f"  {t}: {len(rows)} rows in {time.time() - t1:.2f}s")

cProfile.run("E.Dataset(2, 1.0)", "/tmp/prof.txt")
p = pstats.Stats("/tmp/prof.txt")
p.sort_stats("cumulative").print_stats(12)
