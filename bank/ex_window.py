"""题库 A：窗口函数与排名 / 连续区间问题"""
from bank.spec import Exercise

CAT_A = "窗口函数与排名"
CAT_B = "连续区间问题"

EXERCISES = [
    Exercise(
        id="win_latest_order",
        category=CAT_A,
        difficulty=1,
        title="每个用户最近一笔订单",
        knowledge=["row_number", "分组取最新", "窗口排序"],
        tables=["dwd_order"],
        params=lambda r: {"k": r.choice([50, 80, 100])},
        prompt="""从订单表 dwd_order 中取出**每个用户最近的一笔订单**，输出前 {k} 个用户的：user_id、order_id、amount、order_time。

要求：每个用户只保留一行；按 user_id 升序输出。
输出列：user_id, order_id, amount, order_time""",
        solution="""WITH r AS (
  SELECT user_id, order_id, amount, order_time,
         ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY order_time DESC, order_id DESC) AS rn
  FROM dwd_order
)
SELECT user_id, order_id, amount, order_time
FROM r WHERE rn = 1 AND user_id <= {k}
ORDER BY user_id""",
        hints=[
            "分组内排序取第一名：先按 user_id 分组（PARTITION BY），组内按时间倒序编号。",
            "用 ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY order_time DESC) 打编号，再在外层过滤 rn = 1。",
            "注意次级排序键：同一用户同一秒下单的情况要用 order_id 兜底，否则结果不稳定。",
        ],
        notes="""**考点**：分组取最新 / TopN 是最高频的窗口函数题。

**通用套路**（面试直接背这个骨架）：
```sql
WITH r AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY 分组键 ORDER BY 排序键 DESC) rn
  FROM 表
)
SELECT * FROM r WHERE rn = 1;
```

**为什么不用 GROUP BY + MAX**：GROUP BY 只能拿到最大值本身，拿不到「那一行」的其他字段（除非再 join 一次，性能更差）。用窗口函数一次扫描即可。

**注意**：ORDER BY 必须能唯一确定一行（通常加主键兜底），否则并列时结果不稳定 —— 面试官会追问这一点。""",
    ),
    Exercise(
        id="win_topn_category",
        category=CAT_A,
        difficulty=2,
        title="每个品类销售额 TopN 的商品",
        knowledge=["row_number", "多表关联", "TopN 子查询"],
        tables=["dim_product", "dwd_order"],
        params=lambda r: {"top": r.choice([2, 3, 4])},
        prompt="""统计每个品类（category）销售额最高的 **前 {top} 个商品**，只统计「已支付」订单。

输出列：category, product_name, sales（销售额，保留 2 位小数）
排序：category 升序，同名次内销售额降序（即按品类、名次排列）。""",
        solution="""WITH t AS (
  SELECT p.category, p.product_name, ROUND(SUM(o.amount), 2) AS sales
  FROM dwd_order o
  JOIN dim_product p ON o.product_id = p.product_id
  WHERE o.order_status = '已支付'
  GROUP BY 1, 2
),
r AS (
  SELECT category, product_name, sales,
         ROW_NUMBER() OVER (PARTITION BY category ORDER BY sales DESC, product_name) AS rn
  FROM t
)
SELECT category, product_name, sales
FROM r WHERE rn <= {top}
ORDER BY category, rn""",
        hints=[
            "先按 品类 + 商品 聚合出销售额，再用窗口函数在品类内排名。",
            "聚合要放在子查询（CTE）里，窗口函数不能直接作用在 GROUP BY 的结果上——必须嵌套一层。",
            "排名用 ROW_NUMBER()，并列时加 product_name 作为次级排序键，保证结果稳定。",
        ],
        notes="""**考点**：TopN 是「先聚合、再排名、后过滤」的三段式。三个坑：

1. **窗口函数不能写在 WHERE 里**（执行顺序：FROM → WHERE → GROUP BY → HAVING → 窗口函数 → ORDER BY），必须嵌一层子查询。
2. **ROW_NUMBER / RANK / DENSE_RANK 的选择**：
   - ROW_NUMBER：并列也不同号，取固定条数（本可用这个）
   - RANK：并列同号且跳号（1,1,3）
   - DENSE_RANK：并列同号不跳号（1,1,2）
3. **并列值会让 ROW_NUMBER 结果不确定**，务必加次级排序键。

面试延伸：改成「销售额占比 Top 80% 的商品」→ 用 `SUM(sales) OVER (ORDER BY sales DESC) / SUM(sales) OVER ()` 算累计占比再过滤。""",
    ),
    Exercise(
        id="win_rank_compare",
        category=CAT_A,
        difficulty=2,
        title="三种排名函数的差异（订单量 Top30 用户）",
        knowledge=["rank", "dense_rank", "row_number"],
        tables=["dwd_order"],
        params=lambda r: {"k": r.choice([20, 30, 40])},
        prompt="""按订单笔数（COUNT(*)）从高到低，取**前 {k} 个用户**，同时输出三种排名：
user_id、order_cnt、rn（ROW_NUMBER）、rk（RANK）、drk（DENSE_RANK）。

要求：三种排名都在**全体用户**上计算（不是只在前 {k} 个里算）。
输出列：user_id, order_cnt, rn, rk, drk，按 rn 升序。""",
        solution="""WITH t AS (
  SELECT user_id, COUNT(*) AS order_cnt
  FROM dwd_order
  GROUP BY 1
),
r AS (
  SELECT user_id, order_cnt,
         ROW_NUMBER() OVER (ORDER BY order_cnt DESC, user_id) AS rn,
         RANK()       OVER (ORDER BY order_cnt DESC)          AS rk,
         DENSE_RANK() OVER (ORDER BY order_cnt DESC)          AS drk
  FROM t
)
SELECT user_id, order_cnt, rn, rk, drk
FROM r WHERE rn <= {k}
ORDER BY rn""",
        hints=[
            "先用 GROUP BY 算出每个用户的订单笔数。",
            "ROW_NUMBER 加 user_id 做兜底排序（保证输出行确定），RANK / DENSE_RANK 只按 order_cnt 排。",
            "三种函数写在同一个 SELECT 里即可，不要分三次查询。",
        ],
        notes="""**考点**：三种排名函数的差异，几乎每场面试都会问。

| 函数 | 并列处理 | 示例（10,10,8） |
|---|---|---|
| ROW_NUMBER | 不并列，强行编号 | 1,2,3 |
| RANK | 并列同号，后续跳号 | 1,1,3 |
| DENSE_RANK | 并列同号，不跳号 | 1,1,2 |

**使用场景**：
- 取固定条数 TopN → ROW_NUMBER（结果稳定可控）
- 排行榜展示（同名次）→ RANK
- 分组数排名（如「销量第 3 高的品类」）→ DENSE_RANK

**注意**：订单笔数这种整数指标并列很多，如果用 ROW_NUMBER 不加次级排序键，每次跑出来的「前 30 名」都可能不一样。""",
    ),
    Exercise(
        id="win_first_last",
        category=CAT_A,
        difficulty=3,
        title="首单与末单金额（LAST_VALUE 窗口帧陷阱）",
        knowledge=["first_value", "last_value", "窗口帧"],
        tables=["dwd_order"],
        params=lambda r: {"k": r.choice([60, 80, 100])},
        prompt="""计算每个用户的**首单金额**与**末单金额**（按 order_time 先后），输出前 {k} 个用户：
user_id、first_amount、last_amount、order_cnt。

要求：每个用户一行；按下单笔数降序、user_id 升序输出。
输出列：user_id, first_amount, last_amount, order_cnt""",
        solution="""WITH r AS (
  SELECT user_id, amount,
         FIRST_VALUE(amount) OVER (
           PARTITION BY user_id ORDER BY order_time, order_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS first_amount,
         LAST_VALUE(amount) OVER (
           PARTITION BY user_id ORDER BY order_time, order_id
           ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS last_amount,
         ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY order_time, order_id) AS rn,
         COUNT(*) OVER (PARTITION BY user_id) AS order_cnt
  FROM dwd_order
)
SELECT user_id, first_amount, last_amount, order_cnt
FROM r WHERE rn = 1 AND user_id <= {k}
ORDER BY order_cnt DESC, user_id""",
        hints=[
            "FIRST_VALUE / LAST_VALUE 都是窗口函数，作用范围由窗口帧（frame）决定。",
            "LAST_VALUE 的默认帧是「从第一行到当前行」，所以它返回的是当前行而不是末行——必须显式写 ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING。",
            "每个用户只保留一行：用 ROW_NUMBER 取 rn = 1；笔数可以用 COUNT(*) OVER (PARTITION BY user_id)。",
        ],
        notes="""**考点**：窗口函数的默认帧 —— 这是最高频的「埋雷题」。

- 默认帧：`RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`（有 ORDER BY 时）
- 所以 `LAST_VALUE(...) OVER (PARTITION BY u ORDER BY t)` 拿到的是**当前行的值**，不是最后一个值。
- 正确写法：显式声明 `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`。

**延伸**：`ROWS` 与 `RANGE` 的区别 —— ROWS 按物理行数，RANGE 按值范围（值相同的行算同一个 peer）。累计求和使用 `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`。

**面试加分**：如果只想取首单金额，也可以 `MIN_BY(amount, order_time)`（DuckDB / Hive 2.0+ 的 `min_by`），或用 FIRST_VALUE 的简化写法。""",
    ),
    Exercise(
        id="win_lag_gap",
        category=CAT_A,
        difficulty=2,
        title="相邻两笔订单的间隔时长",
        knowledge=["lag", "时间差计算", "半连接过滤"],
        tables=["dwd_order"],
        params=lambda r: {"min_orders": r.choice([5, 8, 10])},
        prompt="""只考虑下单笔数 ≥ {min_orders} 的用户，计算他们**每一笔订单与上一笔订单的间隔小时数**。

输出列：user_id, order_id, gap_hours（距上一笔订单的小时数，保留 2 位小数，按 order_time 升序取上一笔）
要求：每笔订单一行（用户的第 1 笔没有上一笔，予以排除）；按 user_id、order_time 升序输出。""",
        solution="""WITH t AS (
  SELECT user_id, order_id, order_time,
         LAG(order_time) OVER (PARTITION BY user_id ORDER BY order_time, order_id) AS prev_time
  FROM dwd_order
  WHERE user_id IN (
    SELECT user_id FROM dwd_order GROUP BY user_id HAVING COUNT(*) >= {min_orders}
  )
)
SELECT user_id, order_id,
       ROUND(date_diff('minute', prev_time, order_time) / 60.0, 2) AS gap_hours
FROM t
WHERE prev_time IS NOT NULL
ORDER BY user_id, order_time""",
        hints=[
            "取上一行的时间：LAG(order_time) OVER (PARTITION BY user_id ORDER BY order_time)。",
            "时间差用 date_diff('minute', 上一笔, 当前笔) 再除以 60 得到小时（Hive 里可写 datediff 按天，DuckDB 用 date_diff 指定单位）。",
            "第一笔订单的 LAG 是 NULL，用 WHERE prev_time IS NOT NULL 过滤掉。",
        ],
        notes="""**考点**：LAG / LEAD 计算相邻差值，是「同比环比 / 间隔 / 连续增长」类题的基础。

- `LAG(col, 1, 默认值)` 取上一行，`LEAD` 取下一行；第 3 个参数可以给默认值避免 NULL。
- 时间差写法：DuckDB 用 `date_diff('day', a, b)`；Hive 用 `datediff(end, start)`（天）或 `unix_timestamp` 相减（秒）。
- **边界**：第一行的 LAG 为 NULL，必须显式处理（过滤或给默认值）。

**延伸**：要求「订单量连续 3 天增长」→ 用 LAG 取前两天的值做比较；要求「用户复购间隔的中位数」→ LAG + `median()`。""",
    ),
    Exercise(
        id="win_mom",
        category=CAT_A,
        difficulty=2,
        title="月度 GMV 与环比增长率",
        knowledge=["lag", "date_trunc", "除零保护"],
        tables=["dwd_order"],
        params=lambda r: {"k": r.choice([6, 8, 10])},
        prompt="""计算**每个月已支付订单的 GMV**，以及相对上一个月的环比增长率，输出最近 {k} 个月。

输出列：ym（形如 2026-05）、gmv（保留 2 位小数）、mom_pct（环比增长百分比，保留 2 位小数，如 12.35 表示 +12.35%）
要求：第一个月没有上月，排除；按 ym 升序。""",
        solution="""WITH m AS (
  SELECT STRFTIME(dt, '%Y-%m') AS ym, ROUND(SUM(amount), 2) AS gmv
  FROM dwd_order
  WHERE order_status = '已支付'
  GROUP BY 1
),
t AS (
  SELECT ym, gmv, LAG(gmv) OVER (ORDER BY ym) AS prev_gmv
  FROM m
)
SELECT ym, gmv, ROUND((gmv - prev_gmv) / prev_gmv * 100, 2) AS mom_pct
FROM t
WHERE prev_gmv IS NOT NULL
ORDER BY ym DESC
LIMIT {k}""",
        hints=[
            "先把订单聚合到月粒度：STRFTIME(dt, '%Y-%m') 得到月份字符串（Hive 用 date_format(dt,'yyyy-MM') 或 substr）。",
            "环比 = 本月与上月相比，用 LAG(gmv) OVER (ORDER BY ym) 取上月值。",
            "注意用月份字符串排序比 DATE_TRUNC 更直观；取最近 N 个月可在最后 ORDER BY DESC + LIMIT 实现。",
        ],
        notes="""**考点**：同比 / 环比的固定写法。

- **环比**：与上一期比 → `LAG(metric) OVER (ORDER BY 时间)`
- **同比**：与去年同期比 → 自关联 `a.ym = 去年同期` 或 `LAG(metric, 12)`
- **通用公式**：`（本期 - 上期）/ 上期 * 100`

**坑**：
1. 除零 —— 上期为 0 时会报错，生产上要写 `CASE WHEN prev = 0 THEN NULL ELSE ...`。
2. 月份缺失 —— 如果某个月没有数据，LAG 拿到的是「有数据的上一个月」而不是「物理上一个月」，需要补全日期序列（见 dim_date 关联题目）。
3. 排序依据 —— 一定要按月份排序后取 LAG，不能用自然顺序。""",
    ),
    Exercise(
        id="win_ntile",
        category=CAT_A,
        difficulty=2,
        title="按消费金额把用户分成 N 档",
        knowledge=["ntile", "分桶", "用户分层"],
        tables=["dwd_order"],
        params=lambda r: {"n": r.choice([3, 4, 5])},
        prompt="""把**有已支付订单的用户**按累计消费金额从高到低分成 {n} 档（1 档为金额最高），统计每档的：
档位 grp、用户数 users、平均消费 avg_amt（2 位小数）、总消费 total_amt（2 位小数）。

输出列：grp, users, avg_amt, total_amt，按 grp 升序。""",
        solution="""WITH u AS (
  SELECT user_id, SUM(amount) AS amt
  FROM dwd_order WHERE order_status = '已支付'
  GROUP BY 1
),
q AS (
  SELECT user_id, amt, NTILE({n}) OVER (ORDER BY amt DESC, user_id) AS grp
  FROM u
)
SELECT grp, COUNT(*) AS users,
       ROUND(AVG(amt), 2) AS avg_amt,
       ROUND(SUM(amt), 2) AS total_amt
FROM q
GROUP BY 1
ORDER BY 1""",
        hints=[
            "先用 GROUP BY 算出每个用户的累计消费。",
            "NTILE(N) OVER (ORDER BY amt DESC) 把结果集平均切成 N 份，返回 1..N。",
            "外层再 GROUP BY 档位做聚合；为了让并列金额的顺序稳定，NTILE 里的 ORDER BY 加 user_id 兜底。",
        ],
        notes="""**考点**：NTILE 分桶，常用于用户分层 / 高价值用户识别（RFM 模型里的 M 打分）。

- `NTILE(N) OVER (ORDER BY x)` 把有序结果集**尽量等分**成 N 份。
- 行数不能被 N 整除时，前面的桶会多一行。
- **和 PERCENT_RANK / CUME_DIST 的区别**：NTILE 按行数均分，PERCENT_RANK 按排名比例。

**生产写法**：用户分层更常用「阈值分档」（CASE WHEN CTS >= 1000 THEN '高'）而不是 NTILE，因为 NTILE 的边界每次跑都会变；但面试里 NTILE 是必须会的。""",
    ),
    Exercise(
        id="win_share",
        category=CAT_A,
        difficulty=2,
        title="各品类销售额占比与排名",
        knowledge=["sum over", "占比计算", "多表关联"],
        tables=["dim_product", "dwd_order"],
        params=lambda r: {"th": r.choice([0, 1000])},
        prompt="""统计每个品类的销售额、占总销售额的比例、以及销售额排名，只统计「已支付」订单，
且只保留销售额大于 {th} 的品类。

输出列：category, sales（2 位小数）、pct（占比，百分数保留 2 位小数）、rk（销售额排名，并列同号不跳号）
排序：rk 升序。""",
        solution="""WITH c AS (
  SELECT p.category, ROUND(SUM(o.amount), 2) AS sales
  FROM dwd_order o
  JOIN dim_product p ON o.product_id = p.product_id
  WHERE o.order_status = '已支付'
  GROUP BY 1
  HAVING SUM(o.amount) > {th}
)
SELECT category, sales,
       ROUND(sales / SUM(sales) OVER () * 100, 2) AS pct,
       DENSE_RANK() OVER (ORDER BY sales DESC) AS rk
FROM c
ORDER BY rk""",
        hints=[
            "先聚合出每个品类的销售额（JOIN 商品维表拿 category）。",
            "占比 = 本行销售额 / 全部销售额之和，分母用 SUM(sales) OVER () 一次算出（不带 PARTITION BY 就是全表）。",
            "排名用 DENSE_RANK() OVER (ORDER BY sales DESC)；过滤品类用 HAVING（在聚合之后过滤）。",
        ],
        notes="""**考点**：`SUM(x) OVER ()` 是占比类题目的核心写法，不需要子查询自连接。

**三个易错点**：
1. `HAVING` 过滤的是聚合结果，`WHERE` 过滤的是原始行 —— 销售额阈值必须写在 HAVING。
2. 占比的分母：如果题目要求「占全部销售额」，分母不带 PARTITION BY；要求「占该品类」，则写 PARTITION BY category。
3. 百分数保留 2 位小数要 `* 100` 之后 ROUND；如果直接用 DECIMAL 运算，注意除法的精度类型（DuckDB 会返回 DOUBLE）。

**面试延伸**：二八法则（找出贡献 80% 销售额的商品）→ 累计占比 = `SUM(sales) OVER (ORDER BY sales DESC) / SUM(sales) OVER ()`。""",
    ),
    Exercise(
        id="ser_consecutive_login",
        category=CAT_B,
        difficulty=3,
        title="连续登录 ≥N 天的用户（经典连续区间）",
        knowledge=["连续区间", "gaps and islands", "date - rownum"],
        tables=["dwd_login_log"],
        params=lambda r: {"n": r.choice([3, 5, 7])},
        prompt="""找出**连续登录天数 ≥ {n} 天**的用户及其连续区间。

输出列：user_id, start_date, end_date, days（连续天数）
要求：同一天多次登录按一次算；一个用户有多个达标区间就输出多行。
排序：days 降序、user_id 升序、start_date 升序。""",
        solution="""WITH d AS (
  SELECT DISTINCT user_id, login_date FROM dwd_login_log
),
g AS (
  SELECT user_id, login_date,
         login_date - CAST(ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY login_date) AS INTEGER) AS grp
  FROM d
),
s AS (
  SELECT user_id, grp, COUNT(*) AS days,
         MIN(login_date) AS start_date, MAX(login_date) AS end_date
  FROM g
  GROUP BY 1, 2
)
SELECT user_id, start_date, end_date, days
FROM s WHERE days >= {n}
ORDER BY days DESC, user_id, start_date""",
        hints=[
            "第一步必须先去重：同一天多次登录算一天 → SELECT DISTINCT user_id, login_date。",
            "核心技巧：连续的日期减去连续的行号，结果不变 —— login_date - ROW_NUMBER() 相同的行属于同一个连续区间。",
            "按 (user_id, 差值) 分组，COUNT(*) 就是连续天数，MIN/MAX 得到区间起止。",
        ],
        notes="""**考点**：连续区间问题（gaps and islands），大厂面试出现频率最高的 SQL 之一。

**万能套路**：
```sql
SELECT DISTINCT user_id, dt, dt - ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY dt) AS grp
```
连续的日期与递增的行号同时 +1，差值恒定 → 用这个差值作为「岛编号」分组即可。

**三个关键点**：
1. **必须先按天去重**，否则同一天多条记录会把行号打乱，区间被切碎。
2. 日期减整数：DuckDB / MySQL / PostgreSQL 都支持 `date - n`；Hive 用 `date_sub(dt, n)`。
3. 如果日期字段是字符串，先转 CAST 成 DATE。

**同类变形**（同一套路）：
- 连续 N 天下单 / 连续 N 天盈利 / 连续 N 天低于阈值
- 求每个用户的最长连续登录天数（外层再套一层 MAX）
- 连续登录的第 2 天留存""",
    ),
    Exercise(
        id="ser_max_streak",
        category=CAT_B,
        difficulty=3,
        title="每个用户的最长连续登录天数",
        knowledge=["连续区间", "二次聚合", "TopN"],
        tables=["dwd_login_log"],
        params=lambda r: {"k": r.choice([15, 20, 25])},
        prompt="""计算每个用户**历史上最长的一次连续登录天数**，取前 {k} 名用户。

输出列：user_id, max_streak
排序：max_streak 降序、user_id 升序。""",
        solution="""WITH d AS (
  SELECT DISTINCT user_id, login_date FROM dwd_login_log
),
g AS (
  SELECT user_id, login_date,
         login_date - CAST(ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY login_date) AS INTEGER) AS grp
  FROM d
),
s AS (
  SELECT user_id, grp, COUNT(*) AS days FROM g GROUP BY 1, 2
)
SELECT user_id, MAX(days) AS max_streak
FROM s
GROUP BY 1
ORDER BY max_streak DESC, user_id
LIMIT {k}""",
        hints=[
            "复用连续区间套路：去重 → date - ROW_NUMBER() 得到岛编号 → 每个岛 COUNT(*) 得到区间长度。",
            "每个用户可能有多个连续区间，最长的那一个用 MAX(days) 取，所以要再套一层 GROUP BY user_id。",
            "取前 N 名用 LIMIT，但 ORDER BY 必须带上 user_id 兜底，否则并列时结果不稳定。",
        ],
        notes="""**考点**：连续区间的二次聚合 —— 从「有哪些区间」到「每个用户的最长区间」。

**结构层次**：
1. 去重（同一天算一天）
2. 打岛编号（`dt - ROW_NUMBER()`）
3. 第一层聚合：每个岛 → 区间长度（COUNT）
4. 第二层聚合：每个用户 → MAX(区间长度)

**面试追问**：
- 「如果要求连续登录的区间必须是最近 30 天内？」→ 在去重那步加 WHERE 时间过滤。
- 「如果定义是连续 7 天内至少登录 5 天？」→ 窗口函数滑动计数（`COUNT(*) OVER (ORDER BY dt RANGE BETWEEN 6 PRECEDING AND CURRENT ROW)`），不是 gaps-and-islands。
- 「如果日期不连续但有重复？」→ 先去重再算，这是最常被考的细节。""",
    ),
    Exercise(
        id="ser_low_sales",
        category=CAT_B,
        difficulty=3,
        title="连续 N 天低销售的日期区间（补零 + 区间）",
        knowledge=["日期补全", "left join", "连续区间", "阈值过滤"],
        tables=["dwd_order", "dim_date"],
        params=lambda r: {"n": r.choice([5, 6, 7]), "th": r.choice([3, 5])},
        prompt="""以 dim_date 的完整日期为基准（必须补齐没有订单的日期，按 0 计算），找出所有
**连续 {n} 天及以上、每日已支付订单数都小于 {th} 单**的日期区间。

输出列：start_date, end_date, days（区间天数）、total_paid（该区间内的已支付订单总数）
排序：start_date 升序。""",
        solution="""WITH sales AS (
  SELECT dt, SUM(CASE WHEN order_status = '已支付' THEN 1 ELSE 0 END) AS paid_cnt
  FROM dwd_order GROUP BY 1
),
days AS (
  SELECT d.dt, COALESCE(s.paid_cnt, 0) AS paid_cnt
  FROM dim_date d
  LEFT JOIN sales s ON d.dt = s.dt
),
flag AS (
  SELECT dt, paid_cnt, CASE WHEN paid_cnt < {th} THEN 1 ELSE 0 END AS is_low FROM days
),
g AS (
  SELECT dt, paid_cnt, is_low,
         dt - CAST(ROW_NUMBER() OVER (PARTITION BY is_low ORDER BY dt) AS INTEGER) AS grp
  FROM flag
),
s AS (
  SELECT grp, MIN(dt) AS start_date, MAX(dt) AS end_date, COUNT(*) AS days,
         SUM(paid_cnt) AS total_paid
  FROM g WHERE is_low = 1 GROUP BY 1
)
SELECT start_date, end_date, days, total_paid
FROM s WHERE days >= {n}
ORDER BY start_date""",
        hints=[
            "第一步补齐日期：用 dim_date 左连接聚合后的销售表，COALESCE 把没有订单的日期补 0。",
            "第二步标记阈值：CASE WHEN paid_cnt < 阈值 THEN 1 ELSE 0，得到「是否低销售」标记列。",
            "第三步套连续区间：PARTITION BY 标记列，dt - ROW_NUMBER() 得到岛编号，再按岛聚合。",
        ],
        notes="""**考点**：日期补全 + 连续区间。日期补全是数仓面试的高频细节 —— 真实业务里「没有数据」和「数据为 0」是两件事。

**为什么必须补零**：如果只按有订单的日期算，中间空缺的那几天不会出现在结果里，连续区间会被错误地「接上」，答案就错了。

**补日期序列的三种做法**：
1. **用日期维表**（本题，生产最常用 —— 就是 dim_date 的价值）
2. `GENERATE_SERIES(start, end, INTERVAL 1 DAY)`（DuckDB / PostgreSQL）
3. Hive：`posexplode(split(space(datediff(end,start)), ' '))`

**面试追问**：「如果要求连续 N 天销售额为 0（不是低于阈值）」→ 把 `< th` 改成 `= 0`；「如果只统计大促期间」→ 在 dim_date 上加过滤。""",
    ),
    Exercise(
        id="ser_session",
        category=CAT_B,
        difficulty=3,
        title="按 30 分钟超时切割用户会话",
        knowledge=["lag", "累计标记", "会话切割"],
        tables=["dwd_page_event"],
        params=lambda r: {"k": r.choice([10, 15, 20])},
        prompt="""把用户的行为事件按「**相邻事件间隔超过 30 分钟就算新会话**」的规则切分会话，统计
会话数最多的前 {k} 个用户。

输出列：user_id, sessions（会话数）、avg_minutes（平均会话时长分钟数，保留 2 位小数）、pv（总事件数）
排序：sessions 降序、user_id 升序。

提示：原表的 session_id 字段不可信，请忽略它、自己按时间间隔重新切分。""",
        solution="""WITH e AS (
  SELECT user_id, event_time,
         CASE WHEN LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time) IS NULL
              OR date_diff('minute',
                   LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time),
                   event_time) > 30
              THEN 1 ELSE 0 END AS is_new
  FROM dwd_page_event
),
s AS (
  SELECT user_id, event_time,
         SUM(is_new) OVER (PARTITION BY user_id ORDER BY event_time
                           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS sess_no
  FROM e
),
a AS (
  SELECT user_id, sess_no, COUNT(*) AS pv,
         MIN(event_time) AS st, MAX(event_time) AS et
  FROM s GROUP BY 1, 2
)
SELECT user_id, COUNT(*) AS sessions,
       ROUND(AVG(date_diff('minute', st, et)), 2) AS avg_minutes,
       SUM(pv) AS pv
FROM a
GROUP BY 1
ORDER BY sessions DESC, user_id
LIMIT {k}""",
        hints=[
            "第一步算相邻事件间隔：LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time)。",
            "第二步打新会话标记：间隔 > 30 分钟（或第一行）标记 1，否则 0。",
            "第三步用累计求和把标记变成会话号：SUM(is_new) OVER (... ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) 是会话号，按 (user_id, 会话号) 聚合得到每个会话的时长和 PV。",
        ],
        notes="""**考点**：会话切割 = LAG 求间隔 + 累计求和生成「会话号」，是行为分析的核心套路。

**三步骤记忆法**：
1. `LAG` 取上一行时间，算差值
2. `CASE WHEN 差值 > 阈值 THEN 1 ELSE 0` 打新会话标记（第一行也是 1）
3. `SUM(标记) OVER (ORDER BY 时间)` → 会话编号（累计求和 = 分组编号）

**为什么不能用原表 session_id**：埋点上报的 session_id 经常因为 App 后台被杀、跨端登录而错乱，生产上分析师通常要自己重新切分 —— 这个回答会让面试官觉得你懂真实数据。

**延伸**：`ROW_NUMBER() OVER (PARTITION BY user_id, sess_no ORDER BY event_time)` 可以得到会话内的行为序号，用于漏斗分析。""",
    ),
]
