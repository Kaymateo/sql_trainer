import time
import engine as E

t0 = time.time()
con, ds = E.build_instance(seed=1, scale=1.0, tables=[
    "dim_user", "dim_product", "dwd_order", "dim_date", "dwd_login_log", "dim_user_zip"])
print("build %.2fs" % (time.time() - t0))
for t in ["dim_user", "dim_product", "dwd_order", "dim_date", "dwd_login_log", "dim_user_zip"]:
    print(t, con.sql(f"select count(*) from {t}").fetchone()[0])
print(E.table_schema(con, "dwd_order"))
print(E.table_sample(con, "dim_user", 2))

queries = [
    "select nvl(null,1)",
    "select datediff(date '2026-01-10', date '2026-01-01')",
    "select date_sub(date '2026-01-10', 3)",
    "select collect_list(x) from (select 1 x union all select 2)",
    "select size([1,2,3])",
    "select ifnull(null, 5)",
]
for q in queries:
    try:
        print(q, "=>", con.sql(q).fetchall())
    except Exception as e:
        print(q, "=> FAIL", e)

print(E.run_query(con, "select count(*) c from dwd_order"))

for q in ["select * from '/etc/passwd' limit 1", "select * from read_csv('/etc/hosts')"]:
    try:
        print(q, "=>", E.run_query(con, q)["rows"][:1])
    except E.QueryRejected as e:
        print("BLOCKED:", str(e)[:100])

for q in ["drop table dim_user", "select 1; select 2", "set enable_external_access=true",
          "delete from dim_user", "explain select 1"]:
    try:
        E.guard(q)
        print("LEAK:", q)
    except E.QueryRejected as e:
        print("guard ok:", q, "->", str(e)[:70])

# 判题对拍
ref = E.run_query(con, "select city, count(*) c from dim_user group by 1 order by 1")
same = E.run_query(con, "select count(user_id) c, city from dim_user group by city")
print("compare(reordered) ->", E.compare(same, ref)["reason"])
bad = E.run_query(con, "select city, count(*) c from dim_user group by 1 order by 1 limit 3")
print("compare(truncated) ->", E.compare(bad, ref)["detail"][:140])
