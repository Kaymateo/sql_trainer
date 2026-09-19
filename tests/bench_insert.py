"""对比三种造数据写入方案的耗时，选最快的落地到 engine。"""
import time

import duckdb

import engine as E

ds = E.Dataset(3, 1.0)
rows = ds.rows_for("dwd_order")
ncol = len(rows[0])
ddl = E.Dataset.DDL["dwd_order"]
print(f"rows={len(rows)} cols={ncol} sample={rows[0]}")


def t_executemany():
    con = E.new_connection()
    con.execute(ddl)
    t = time.time()
    con.executemany(f"INSERT INTO dwd_order VALUES ({','.join('?' * ncol)})", rows)
    return time.time() - t


def t_batched(batch=500):
    con = E.new_connection()
    con.execute(ddl)
    one = "(" + ",".join("?" * ncol) + ")"
    sql = f"INSERT INTO dwd_order VALUES " + ",".join([one] * batch)
    t = time.time()
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        if len(chunk) < batch:
            sql = f"INSERT INTO dwd_order VALUES " + ",".join([one] * len(chunk))
        flat = [v for r in chunk for v in r]
        con.execute(sql, flat)
    return time.time() - t


def t_arrow():
    import pyarrow
    con = E.new_connection()
    con.execute(ddl)
    cols = ["order_id", "user_id", "product_id", "quantity", "amount", "order_status",
            "order_time", "pay_time", "province", "dt"]
    t = time.time()
    tbl = pyarrow.Table.from_pydict({c: [r[i] for r in rows] for i, c in enumerate(cols)})
    con.register("_tmp", tbl)
    con.execute("INSERT INTO dwd_order SELECT * FROM _tmp")
    con.unregister("_tmp")
    return time.time() - t


print("executemany      : %.2fs" % t_executemany())
print("batched VALUES   : %.2fs" % t_batched())
try:
    import pyarrow  # noqa: F401
    print("pyarrow register : %.2fs" % t_arrow())
except ImportError:
    print("pyarrow register : (pyarrow 未安装)")

# 验证 pyarrow 不可用时 batched 的正确性
con = E.new_connection()
con.execute(ddl)
one = "(" + ",".join("?" * ncol) + ")"
sql = f"INSERT INTO dwd_order VALUES " + ",".join([one] * 500)
for i in range(0, len(rows), 500):
    chunk = rows[i:i + 500]
    if len(chunk) < 500:
        sql = f"INSERT INTO dwd_order VALUES " + ",".join([one] * len(chunk))
    con.execute(sql, [v for r in chunk for v in r])
print("batched 校验 count =", con.sql("select count(*) from dwd_order").fetchone()[0],
      "sum =", con.sql("select round(sum(amount),2) from dwd_order").fetchone()[0])
