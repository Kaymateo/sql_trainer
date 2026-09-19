"""题库 C：多表关联与集合 / 日期与时间 / 数仓口径与建模"""
import datetime as dt

from bank.spec import Exercise, case_pivot, in_list

CAT_F = "多表关联与集合"
CAT_G = "日期与时间"
CAT_H = "数仓口径与建模"

_CATS_PIVOT = ("手机数码", "服饰鞋包", "食品生鲜", "家居日用", "美妆个护")


def _snap_date(r):
    return (dt.date(2025, 7, 1) + dt.timedelta(days=r.randint(0, 300))).isoformat()


def _upd_users(r):
    ids = sorted(r.sample(range(1, 41), 2))
    cities = r.sample(["成都", "绵阳", "西安", "武汉"], 2)
    levels = r.sample(["银卡", "金卡", "钻卡"], 2)
    return {"uid_a": ids[0], "uid_b": ids[1], "city_a": cities[0], "city_b": cities[1],
            "lv_a": levels[0], "lv_b": levels[1]}


EXERCISES = [
    # ───────────────────────── 多表关联与集合 ─────────────────────────
    Exercise(
        id="join_pay_rate",
        category=CAT_F,
        difficulty=2,
        title="各城市支付成功率（LEFT JOIN + COUNT 的坑）",
        knowledge=["left join", "count(col) 与 count(*)", "一对多关联"],
        tables=["dwd_order", "dwd_payment", "dim_user"],
        prompt="""统计每个城市的订单数、**有支付流水的订单数**以及支付率：
city、orders（订单总数）、paid_orders（在支付表中有记录的订单数）、pay_rate（支付率百分数，2 位小数）。

输出列：city, orders, paid_orders, pay_rate，按 city 升序。""",
        solution="""SELECT u.city,
       COUNT(*) AS orders,
       COUNT(p.order_id) AS paid_orders,
       ROUND(COUNT(p.order_id) * 100.0 / COUNT(*), 2) AS pay_rate
FROM dwd_order o
JOIN dim_user u ON o.user_id = u.user_id
LEFT JOIN dwd_payment p ON o.order_id = p.order_id
GROUP BY 1
ORDER BY city""",
        hints=[
            "订单表与支付表是一对零或一的关系（未支付订单没有支付记录），必须用 LEFT JOIN 才能保住分母。",
            "计数用 COUNT(p.order_id)（只统计关联上的行），而不是 COUNT(*)（会把没支付的行也算进去）。",
            "COUNT(某列) 会忽略 NULL —— 这是「关联后统计子表行数」的标准写法。",
        ],
        notes="""**考点**：`COUNT(*)` 与 `COUNT(列)` 的差异 + 一对多关联的计数陷阱。这是 SQL 面试的必考题。

| 写法 | 含义 |
|---|---|
| COUNT(*) | 统计结果集行数（LEFT JOIN 补出来的 NULL 行也算） |
| COUNT(列) | 只统计该列非 NULL 的行 |
| COUNT(DISTINCT 列) | 去重计数 |

**为什么容易错**：LEFT JOIN 后，未匹配的右表字段是 NULL，此时 `COUNT(*)` 仍然会计 1，用它当「支付订单数」就全算成 100% 了。

**关联膨胀的两种情况**：
1. **一对多**（一个订单对应多条支付流水/退款流水）→ 行数翻倍，SUM 会重复累加 → 必须先去重或先聚合再关联。
2. **多对多** → 笛卡尔积，数据量爆炸，是生产事故的常见原因。

**面试追问**：「如果支付表里同一个订单有多条重试记录怎么办？」→ 先按 order_id 去重（row_number 取最新一条）或加 GROUP BY 聚合，再关联。""",
    ),
    Exercise(
        id="join_avoid_expand",
        category=CAT_F,
        difficulty=3,
        title="避免关联膨胀：城市的 GMV 与退款金额",
        knowledge=["关联膨胀", "先聚合再关联", "一对多"],
        tables=["dwd_order", "dwd_refund", "dim_user"],
        prompt="""按城市统计已支付订单的 GMV、退款金额与退款率：
city、gmv（2 位小数）、refund_amt（2 位小数，无退款记 0）、refund_rate（退款金额占 GMV 的百分数，2 位小数，无退款记 0）。

输出列：city, gmv, refund_amt, refund_rate，按 city 升序。

注意：退款表与订单表是一对多关系（同一订单可能多次退款）。""",
        solution="""WITH o AS (
  SELECT u.city, SUM(o.amount) AS gmv
  FROM dwd_order o
  JOIN dim_user u ON o.user_id = u.user_id
  WHERE o.order_status = '已支付'
  GROUP BY 1
),
r AS (
  SELECT u.city, SUM(r.refund_amount) AS refund_amt
  FROM dwd_refund r
  JOIN dwd_order o ON r.order_id = o.order_id
  JOIN dim_user u ON o.user_id = u.user_id
  GROUP BY 1
)
SELECT o.city,
       ROUND(o.gmv, 2) AS gmv,
       ROUND(COALESCE(r.refund_amt, 0), 2) AS refund_amt,
       ROUND(COALESCE(r.refund_amt, 0) * 100.0 / o.gmv, 2) AS refund_rate
FROM o
LEFT JOIN r ON o.city = r.city
ORDER BY city""",
        hints=[
            "不要直接把订单表和退款表 join 在一起再 SUM —— 一个订单多条退款会让订单金额被重复累加。",
            "正确做法：各自聚合到城市粒度，再按城市关联（先聚合、后关联）。",
            "没有退款的城市要补 0：LEFT JOIN + COALESCE。",
        ],
        notes="""**考点**：关联膨胀（fan-out）—— 数仓开发最经典的事故来源，面试高频。

**错误示范**（一定要能说出为什么错）：
```sql
-- 一个订单有 2 条退款记录时，这笔订单的 amount 会被计 2 次，GMV 虚高
SELECT u.city, SUM(o.amount), SUM(r.refund_amount)
FROM dwd_order o
LEFT JOIN dwd_refund r ON o.order_id = r.order_id
JOIN dim_user u ON o.user_id = u.user_id
GROUP BY 1;
```

**正确姿势**（三种，按场景选）：
1. **先聚合再关联**（本题）—— 最稳，推荐
2. **先按主键去重右表**（row_number 取一条）
3. **用子查询把右表预聚合成一列**，再关到主表上

**怎么发现膨胀**：关联前后对比行数（`COUNT(*)` 与 `COUNT(DISTINCT 主键)` 是否相等）；生产上做「对账」，跟源系统核总数。

**面试话术**：「我遇到过一个问题：订单表和退款表关联后 GMV 涨了 3%，定位到是一对多膨胀，改成先按城市聚合再关联就一致了。」—— 一句话体现你有生产经验。""",
    ),
    Exercise(
        id="join_zero_orders",
        category=CAT_F,
        difficulty=2,
        title="零单用户分布（LEFT JOIN 必须保住零单用户）",
        knowledge=["left join", "coalesce", "分桶", "零值处理"],
        tables=["dim_user", "dwd_order"],
        prompt="""统计全部**注册用户**按下单笔数的分布（零单用户必须统计在内）：
user_bucket（'0单'、'1单'、'2-4单'、'5单及以上'）、bucket_order（1~4）、users（用户数）

口径：以 dim_user 为基准表；订单只算 order_status = '已支付' 的。
输出列：user_bucket, bucket_order, users，按 bucket_order 升序。""",
        solution="""WITH c AS (
  SELECT u.user_id, COUNT(o.order_id) AS cnt
  FROM dim_user u
  LEFT JOIN dwd_order o
    ON o.user_id = u.user_id AND o.order_status = '已支付'
  GROUP BY 1
)
SELECT CASE WHEN cnt = 0 THEN '0单'
            WHEN cnt = 1 THEN '1单'
            WHEN cnt <= 4 THEN '2-4单'
            ELSE '5单及以上' END AS user_bucket,
       CASE WHEN cnt = 0 THEN 1 WHEN cnt = 1 THEN 2 WHEN cnt <= 4 THEN 3 ELSE 4 END AS bucket_order,
       COUNT(*) AS users
FROM c
GROUP BY 1, 2
ORDER BY bucket_order""",
        hints=[
            "基准表必须是 dim_user（要统计零单用户），LEFT JOIN 订单表；过滤条件写在 ON 里而不是 WHERE 里。",
            "计单数用 COUNT(o.order_id)（不是 COUNT(*)），否则零单用户会被算成 1 单。",
            "分桶用 CASE WHEN，同时输出 bucket_order 作为排序键。",
        ],
        notes="""**考点**：LEFT JOIN 的过滤条件位置 —— 写在 ON 还是 WHERE，结果完全不同。

**这是面试最爱考的细节**：
```sql
-- ✅ 正确：未支付订单只是不参与计数，用户仍在结果里
LEFT JOIN dwd_order o ON o.user_id = u.user_id AND o.order_status = '已支付'
-- ❌ 错误：WHERE 会把「关联不上的 NULL 行」过滤掉，LEFT JOIN 退化成 INNER JOIN，零单用户全丢
LEFT JOIN dwd_order o ON o.user_id = u.user_id
WHERE o.order_status = '已支付'
```

**记忆口诀**：主表要全保留 → 右表的过滤条件必须写在 ON 里。

**为什么要看零单用户**：零单用户占比是「转化漏斗」的关键指标；只统计下单用户会得到「下沉市场不存在」的错误结论 —— 这是分析师的经典失误，也是面试的加分回答。

**延伸**：活跃用户里从不下单的高频访问用户（只浏览不下单）→ dim_user LEFT JOIN 订单 + 埋点事件，双条件过滤。""",
    ),
    Exercise(
        id="join_anti_exists",
        category=CAT_F,
        difficulty=3,
        title="加购但从未下单的用户（反连接）",
        knowledge=["not exists", "left join is null", "反连接"],
        tables=["dwd_page_event"],
        params=lambda r: {"k": r.choice([10, 15, 20])},
        prompt="""找出**发生过 add_cart 事件、但从未有过 submit_order 事件**的用户，取前 {k} 个（按 user_id 升序）。

同时输出他们的加购次数：
输出列：user_id, add_cart_cnt
排序：user_id 升序（LIMIT {k}）。""",
        solution="""SELECT e.user_id, COUNT(*) AS add_cart_cnt
FROM dwd_page_event e
WHERE e.event_type = 'add_cart'
  AND NOT EXISTS (
    SELECT 1 FROM dwd_page_event x
    WHERE x.user_id = e.user_id AND x.event_type = 'submit_order'
  )
GROUP BY 1
ORDER BY user_id
LIMIT {k}""",
        hints=[
            "「有 A 且没有 B」是典型的反连接（anti-join）问题。",
            "三种写法等价：NOT EXISTS（推荐）、LEFT JOIN ... WHERE 右表主键 IS NULL、EXCEPT/NOT IN。",
            "注意 NOT IN 遇到子查询里有 NULL 会整体失效 —— 这是面试官很爱追问的坑。",
        ],
        notes="""**考点**：反连接（anti-join）的三种实现与坑。

```sql
-- 1) NOT EXISTS（推荐，能利用索引，NULL 安全）
WHERE NOT EXISTS (SELECT 1 FROM b WHERE b.uid = a.uid)
-- 2) LEFT JOIN + IS NULL
LEFT JOIN b ON a.uid = b.uid WHERE b.uid IS NULL
-- 3) NOT IN（⚠️ 有坑）
WHERE uid NOT IN (SELECT uid FROM b)   -- 子查询结果含 NULL 时，整个条件永远为 UNKNOWN，返回空集！
```

**为什么 NOT EXISTS 更好**：语义清晰、NULL 安全、多数引擎能优化成 anti-join 算子。

**业务场景**：
- 加购未下单 → 流失分析、购物车召回
- 注册未激活 / 领券未使用 → 运营触达
- 有浏览无购买的品类 → 选品分析
- 数据质量里的「孤儿记录」（事实表关联不上维表）也是反连接

**面试延伸**：「找出只买过 A 品类、从没买过 B 品类的用户」→ 同一个套路，换条件即可。""",
    ),
    Exercise(
        id="join_product_pairs",
        category=CAT_F,
        difficulty=3,
        title="商品两两共同购买次数 TopN（自关联）",
        knowledge=["self join", "自关联去重", "组合统计"],
        tables=["dwd_order"],
        params=lambda r: {"k": r.choice([10, 15, 20])},
        prompt="""统计**经常被同一用户购买的商品组合**，输出共同购买次数最多的前 {k} 组：
pid_a、pid_b（商品 ID，保证 pid_a < pid_b）、users（共同购买该组合的用户数）

口径：只统计已支付订单；同一用户对同一商品买多次只算一次。
输出列：pid_a, pid_b, users，按 users 降序、pid_a 升序、pid_b 升序。""",
        solution="""WITH u AS (
  SELECT DISTINCT user_id, product_id
  FROM dwd_order
  WHERE order_status = '已支付'
)
SELECT a.product_id AS pid_a, b.product_id AS pid_b, COUNT(*) AS users
FROM u a
JOIN u b ON a.user_id = b.user_id AND a.product_id < b.product_id
GROUP BY 1, 2
ORDER BY users DESC, pid_a, pid_b
LIMIT {k}""",
        hints=[
            "同一张表关联自己：用户买过的商品集合与自己做笛卡尔配对。",
            "关键去重：先 SELECT DISTINCT user_id, product_id（同一商品买多次只算一次），否则次数会虚高。",
            "用 a.product_id < b.product_id 去掉自身配对和重复组合（(A,B) 与 (B,A) 只保留一个）。",
        ],
        notes="""**考点**：自关联 + 组合统计，是「购物篮分析 / 关联推荐」的基础。

**三个关键技巧**：
1. **先去重再自关联**：`SELECT DISTINCT user_id, product_id`，否则一个用户买 3 次同一商品会被算成 3 次共购。
2. **用不等号去重**：`a.pid < b.pid` 同时解决了「自己跟自己配对」和「(A,B)/(B,A) 重复」两个问题。
3. **性能**：自关联是 O(n²) 级别的操作，大数据量下必须先用 `DISTINCT` 或聚合把数据缩小 —— 面试问到性能这样答。

**延伸（面试常见追问）**：
- 提升到「支持度 / 置信度 / 提升度」→ 关联规则挖掘（Apriori），SQL 能算支持度与置信度：`P(B|A) = 共购次数 / 买过 A 的用户数`。
- 商品组合去重（3 件套）→ 再加一层自关联，但组合数会爆炸，生产上常用 minhash / 采样。
- 如果用 Hive：自关联会触发大 shuffle，需要控制数据量或改成 broadcast。""",
    ),

    # ───────────────────────── 日期与时间 ─────────────────────────
    Exercise(
        id="date_running_total",
        category=CAT_G,
        difficulty=2,
        title="每日 GMV 与累计 GMV（窗口帧）",
        knowledge=["累计求和", "窗口帧", "日期聚合"],
        tables=["dwd_order"],
        params=lambda r: {"start": r.choice(["2026-01-01", "2026-03-01", "2025-10-01"])},
        prompt="""统计 **{start} 之后**每个有已支付订单的日期的：dt、gmv（2 位小数）、cum_gmv（截至当日的累计 GMV，2 位小数）。

输出列：dt, gmv, cum_gmv，按 dt 升序。""",
        solution="""WITH d AS (
  SELECT dt, SUM(amount) AS gmv
  FROM dwd_order
  WHERE order_status = '已支付' AND dt >= DATE '{start}'
  GROUP BY 1
)
SELECT dt, ROUND(gmv, 2) AS gmv,
       ROUND(SUM(gmv) OVER (ORDER BY dt
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cum_gmv
FROM d
ORDER BY dt""",
        hints=[
            "先聚合到天粒度，再用窗口函数做累计求和。",
            "累计求和必须显式写窗口帧：ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW。",
            "如果只写 SUM(gmv) OVER (ORDER BY dt)，DuckDB / 标准 SQL 默认帧也是到当前行，但显式写出来更清晰、也是面试要考的。",
        ],
        notes="""**考点**：累计求和（running total），窗口帧是必考细节。

**默认帧规则**（面试必答）：
- 有 ORDER BY 时：默认帧是 `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`
- 无 ORDER BY 时：默认帧是整张表（`ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`）
- `ROWS` 按物理行，`RANGE` 按值分组（相同排序值的行算同一「peer」，会一起被包含）

**为什么用 RANGE 会出错**：如果同一天有多行（比如按日期+城市），RANGE 会把当天所有行都算进去，得到「截至当天的完整汇总」而不是逐行累计。

**Hive 的替代写法**：`SUM(gmv) OVER (ORDER BY dt ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)` 完全一样；Hive 2.0 之前的版本不支持窗口帧 → 需要用自关联 `a.dt >= b.dt` 求和（面试问「不用窗口函数怎么写」时答这个）。

**常见变体**：月度累计（YTD）、分组内累计、滑动窗口平均值（`ROWS BETWEEN 6 PRECEDING AND CURRENT ROW`）。""",
    ),
    Exercise(
        id="date_hour_peak",
        category=CAT_G,
        difficulty=2,
        title="下单时段分布与高峰分析",
        knowledge=["extract", "时间函数", "占比", "排名"],
        tables=["dwd_order"],
        prompt="""统计已支付订单在一天 24 小时内的分布：
hour_of_day（0~23）、orders（订单数）、order_pct（占全天订单的百分数，2 位小数）、rk（订单数排名，并列同号不跳号）

输出列：hour_of_day, orders, order_pct, rk，按 hour_of_day 升序。""",
        solution="""SELECT EXTRACT(HOUR FROM order_time) AS hour_of_day,
       COUNT(*) AS orders,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS order_pct,
       DENSE_RANK() OVER (ORDER BY COUNT(*) DESC) AS rk
FROM dwd_order
WHERE order_status = '已支付'
GROUP BY 1
ORDER BY hour_of_day""",
        hints=[
            "取小时用 EXTRACT(HOUR FROM 时间戳)；Hive 里用 hour(order_time) 或 from_unixtime(unix_timestamp(...),'HH')。",
            "占比的分母 SUM(COUNT(*)) OVER () 会算出全天的订单总数。",
            "排名用 DENSE_RANK() OVER (ORDER BY COUNT(*) DESC)，注意排名里的排序键是聚合结果。",
        ],
        notes="""**考点**：时间维度提取 + 聚合后再开窗。

**时间函数对照表**（面试高频，一定要能说出 Hive 对应写法）：

| 需求 | DuckDB | Hive |
|---|---|---|
| 取小时 | EXTRACT(HOUR FROM t) | hour(t) |
| 取年月 | STRFTIME(t,'%Y-%m') | date_format(t,'yyyy-MM') / substr(t,1,7) |
| 截断到月 | DATE_TRUNC('month', t) | trunc(t,'MM') |
| 日期加减 | d + 1 / d - INTERVAL 1 DAY | date_add(d,1) / date_sub(d,1) |
| 求差 | date_diff('day', a, b) | datediff(b, a) |
| 时间戳转字符串 | STRFTIME(t,'%Y-%m-%d %H:%i:%s') | from_unixtime(unix_timestamp(t)) |
| 字符串转时间 | STRPTIME(s,'%Y-%m-%d') | to_date(s) / unix_timestamp(s,'yyyy-MM-dd') |

**业务价值**：时段分布用于「投放时段优化 / 运力排班 / 大促爆发点预判」，面试讲出业务含义是加分项。

**注意**：`EXTRACT(HOUR FROM order_time)` 受时区影响，生产上要明确数据是 UTC 还是本地时间 —— 时间戳跨时区问题在实时数仓里非常常见。""",
    ),
    Exercise(
        id="date_weekend",
        category=CAT_G,
        difficulty=1,
        title="工作日与周末的 GMV 对比",
        knowledge=["日期维表关联", "分组对比"],
        tables=["dwd_order", "dim_date"],
        prompt="""借助日期维表 dim_date 的 is_weekend 标记（1 为周末），对比工作日与周末的：
day_type（'工作日' / '周末'）、days（有已支付订单的天数）、gmv（2 位小数）、avg_daily_gmv（日均 GMV，2 位小数）

输出列：day_type, days, gmv, avg_daily_gmv，按 day_type 升序。只统计已支付订单。""",
        solution="""SELECT CASE WHEN d.is_weekend = 1 THEN '周末' ELSE '工作日' END AS day_type,
       COUNT(DISTINCT o.dt) AS days,
       ROUND(SUM(o.amount), 2) AS gmv,
       ROUND(SUM(o.amount) / COUNT(DISTINCT o.dt), 2) AS avg_daily_gmv
FROM dwd_order o
JOIN dim_date d ON o.dt = d.dt
WHERE o.order_status = '已支付'
GROUP BY 1
ORDER BY day_type""",
        hints=[
            "订单表按 dt 关联日期维表，用 is_weekend 分组。",
            "天数要用 COUNT(DISTINCT o.dt) —— 直接 COUNT(*) 得到的是订单数不是天数。",
            "日均 GMV = 总 GMV / 天数，注意分母别用错。",
        ],
        notes="""**考点**：日期维表的使用 + 「人次 vs 天数」的分母意识。

**日期维表（dim_date）的价值**（面试常问「为什么要建日期维表」）：
1. 存放节假日、促销日、财年、周数等**业务属性**，避免每次用函数计算（性能更好）
2. **补全日期序列**，解决「某天没有数据」导致的分析断档（见「连续低销售」那道题）
3. 统一口径：周的定义（周一还是周日起）、财年口径

**关联字段选择**：订单表里同时有 `dt`（日期）和 `order_time`（时间戳），关联维表要用 dt，不要用时间戳（否则要转换，无法命中分区裁剪）。

**面试延伸**：如果订单表没有 dt 字段，只有时间戳怎么办？→ 用 `CAST(order_time AS DATE)` 关联，但这样无法利用分区裁剪，所以在数仓建模时**一定会把分区字段 dt 冗余到事实表里** —— 这是非常实用的建模经验。""",
    ),
    Exercise(
        id="date_pay_duration",
        category=CAT_G,
        difficulty=3,
        title="支付时效分布与累计占比",
        knowledge=["时间差", "分桶", "累计占比", "窗口聚合"],
        tables=["dwd_order"],
        prompt="""分析**已支付/已退款订单**从下单到支付的时间间隔，按以下区间分桶：
0-30分钟、30-60分钟、1-2小时、2小时以上。

输出列：bucket（档位名）、bucket_order（1~4）、orders（订单数）、avg_minutes（平均时长分钟，2 位小数）、
pct（订单数占比百分数，2 位小数）、cum_pct（累计占比百分数，2 位小数）
排序：bucket_order 升序。""",
        solution="""WITH t AS (
  SELECT date_diff('minute', order_time, pay_time) AS dur
  FROM dwd_order
  WHERE order_status IN ('已支付', '已退款')
),
b AS (
  SELECT CASE WHEN dur <= 30 THEN '0-30分钟'
              WHEN dur <= 60 THEN '30-60分钟'
              WHEN dur <= 120 THEN '1-2小时'
              ELSE '2小时以上' END AS bucket,
         CASE WHEN dur <= 30 THEN 1 WHEN dur <= 60 THEN 2 WHEN dur <= 120 THEN 3 ELSE 4 END AS bucket_order,
         dur
  FROM t
)
SELECT bucket, bucket_order,
       COUNT(*) AS orders,
       ROUND(AVG(dur), 2) AS avg_minutes,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct,
       ROUND(SUM(COUNT(*)) OVER (ORDER BY bucket_order)
             * 100.0 / SUM(COUNT(*)) OVER (), 2) AS cum_pct
FROM b
GROUP BY 1, 2
ORDER BY bucket_order""",
        hints=[
            "时间差用 date_diff('minute', 下单时间, 支付时间)（Hive 用 (unix_timestamp(pay_time)-unix_timestamp(order_time))/60）。",
            "分桶用 CASE WHEN，同时输出一个 bucket_order 用于排序和累计。",
            "累计占比 = SUM(COUNT(*)) OVER (ORDER BY bucket_order) / SUM(COUNT(*)) OVER () —— 两个窗口函数，一个带排序一个不带。",
        ],
        notes="""**考点**：分桶 + 占比 + 累计占比（帕累托分析的基础）。

**累计占比的作用**：回答「多少比例的订单在 30 分钟内完成支付」这类 SLA 问题。业务上常用于：
- 支付时效 SLA 监控（如「95% 的订单应在 1 小时内支付」）
- 用户行为分布（多少用户贡献了 80% 的 GMV）
- 延迟分位数分析（配合 percentile 更精确）

**注意累计的两个写法**：
1. `SUM(x) OVER (ORDER BY 有序键)` —— 累计（含当前行）
2. `SUM(x) OVER ()` —— 总计（分母）

**性能提示**：COUNT(*) 被用了两次窗口计算，生产上更推荐先聚合出明细桶再开窗（本题已经这么做了）。

**面试追问**：「如果要算 P95 支付时长」→ 用 `QUANTILE_CONT(dur, 0.95)`，比手工分桶更精确。""",
    ),
    Exercise(
        id="date_mau_mom",
        category=CAT_G,
        difficulty=2,
        title="月活跃用户数与环比",
        knowledge=["count distinct", "lag", "环比", "月粒度"],
        tables=["dwd_page_event"],
        prompt="""以埋点表 dwd_page_event 计算每月的活跃用户数（UV）及其环比增长率：
ym（2025-01 形式）、mau（月活跃用户数）、mom_pct（环比增长百分数，2 位小数；首月无上月则留 NULL）

输出列：ym, mau, mom_pct，按 ym 升序。""",
        solution="""WITH m AS (
  SELECT STRFTIME(dt, '%Y-%m') AS ym, COUNT(DISTINCT user_id) AS mau
  FROM dwd_page_event
  GROUP BY 1
),
t AS (
  SELECT ym, mau, LAG(mau) OVER (ORDER BY ym) AS prev_mau FROM m
)
SELECT ym, mau,
       ROUND((mau - prev_mau) * 100.0 / prev_mau, 2) AS mom_pct
FROM t
ORDER BY ym""",
        hints=[
            "月活跃 = 该月去重用户数：COUNT(DISTINCT user_id) 按月份分组。",
            "环比用 LAG(mau) OVER (ORDER BY ym)。",
            "首月没有上月 → 表达式结果是 NULL，这是正常的，不要用 COALESCE 填 0（0 和 NULL 语义不同）。",
        ],
        notes="""**考点**：COUNT(DISTINCT) + 环比 + NULL 语义。

**关键认知**：
1. **去重计数是重操作**：大数据量下 COUNT(DISTINCT) 会产生巨大 shuffle，Hive 里常用 `size(collect_set(user_id))` 或近似算法（HyperLogLog）。面试问「亿级 UV 怎么算」→ 答 HLL / BitMap（`bitmap_count`、`intersect_count` 在 ClickHouse / Doris 里是标准做法）。
2. **NULL 不能当 0**：首月环比是 NULL（不可比），填 0 会误导业务方「首月没有增长」。
3. **月活口径**：自然月内的去重用户数。要区分「月活跃」与「月活跃且下单」—— 口径不同结论可能完全相反。

**面试延伸**：
- UV / DAU / MAU / 周活 的差异与计算
- DAU/MAU 比（用户粘性指标）
- 留存与活跃的区别（留存按首次行为划分人群，活跃只看当期是否出现）""",
    ),

    # ───────────────────────── 数仓口径与建模 ─────────────────────────
    Exercise(
        id="dw_gmv_caliber",
        category=CAT_H,
        difficulty=2,
        title="GMV / 支付金额 / 退款金额 / 净收入 的口径拆解",
        knowledge=["指标口径", "口径拆解", "cross join"],
        tables=["dwd_order", "dwd_refund"],
        prompt="""按下面的口径算出 4 个指标（**一行结果**）：
- gmv：全部订单的金额之和（含待支付/已取消/已退款）
- paid_amount：已支付与已退款订单的金额之和（即支付成功的金额）
- refund_amount：退款表 dwd_refund 的退款金额之和
- net_amount：净收入 = paid_amount - refund_amount

输出列：gmv, paid_amount, refund_amount, net_amount（都保留 2 位小数）""",
        solution="""WITH o AS (
  SELECT SUM(amount) AS gmv,
         SUM(CASE WHEN order_status IN ('已支付', '已退款') THEN amount ELSE 0 END) AS paid_amount
  FROM dwd_order
),
r AS (
  SELECT SUM(refund_amount) AS refund_amount FROM dwd_refund
)
SELECT ROUND(o.gmv, 2) AS gmv,
       ROUND(o.paid_amount, 2) AS paid_amount,
       ROUND(r.refund_amount, 2) AS refund_amount,
       ROUND(o.paid_amount - r.refund_amount, 2) AS net_amount
FROM o CROSS JOIN r""",
        hints=[
            "两个表各自聚合成一行（单值），再用 CROSS JOIN 拼成一行结果。",
            "gmv 的统计范围是全部订单；paid_amount 只算「已支付 + 已退款」（退款订单当初也是支付成功的）。",
            "口径拆解是数仓面试的高频题，答的时候要先复述口径再写 SQL。",
        ],
        notes="""**考点**：指标口径拆解 —— 面试官判断你「是不是真的做过数仓」的关键题。

**必背口径**：
| 指标 | 口径 |
|---|---|
| GMV | 下单总金额（含未支付、已取消、已退款）—— 反映交易规模 |
| 支付金额 | 支付成功的金额（含后来退款的） |
| 退款金额 | 退款成功的金额 |
| 净收入 | 支付金额 - 退款金额（近似口径，严格口径还要扣除渠道手续费） |
| 客单价 | GMV / 下单用户数（注意分母口径：下单用户 vs 支付用户） |

**面试必问的两个问题**：
1. 「GMV 包含退款订单吗？」→ 通常包含（GMV 是交易规模指标），但也有公司口径是「不含退款」——**关键是能说清你用的是哪一种，并且整个团队统一**。
2. 「为什么要区分这些口径？」→ 因为业务方看的是规模（GMV）、财务看的是实收（净收入），口径混用会导致报表对不上。

**工程落地**：口径要写在**指标字典/口径文档**里，每个指标记录：名称、定义、计算公式、数据来源、责任人、更新频率。这是数据治理的核心产物，面试中主动提到会加分。""",
    ),
    Exercise(
        id="dw_daily_uv_pv",
        category=CAT_H,
        difficulty=2,
        title="每日 UV / PV / 人均页面数（含无流量日期补零）",
        knowledge=["补日期", "nullif", "防除零", "left join"],
        tables=["dwd_page_event", "dim_date"],
        params=lambda r: {"start": r.choice(["2026-05-01", "2026-04-01", "2025-12-01"])},
        prompt="""以日期维表 dim_date 为基准，输出 **{start} 之后**每一天的：
dt、pv（页面事件数）、uv（去重用户数）、pv_per_uv（人均页面数，2 位小数）

要求：没有流量的日期也要输出（pv / uv 记为 0，人均页面数记为 0 或 NULL 均可，但必须避免除零错误）。
输出列：dt, pv, uv, pv_per_uv，按 dt 升序。""",
        solution="""WITH e AS (
  SELECT dt, COUNT(*) AS pv, COUNT(DISTINCT user_id) AS uv
  FROM dwd_page_event
  GROUP BY 1
)
SELECT d.dt,
       COALESCE(e.pv, 0) AS pv,
       COALESCE(e.uv, 0) AS uv,
       ROUND(COALESCE(e.pv, 0) * 1.0 / NULLIF(e.uv, 0), 2) AS pv_per_uv
FROM dim_date d
LEFT JOIN e ON d.dt = e.dt
WHERE d.dt >= DATE '{start}'
ORDER BY d.dt""",
        hints=[
            "以日期维表为主表 LEFT JOIN 流量表，缺失日期自然变成 NULL，再用 COALESCE 补 0。",
            "人均 = pv / uv，uv 可能为 0 → 用 NULLIF(uv, 0) 把 0 变成 NULL，避免除零报错。",
            "注意映射到维表后没有流量的日期也要出现在结果里（这就是用 dim_date 当主表的意义）。",
        ],
        notes="""**考点**：日期补全 + 除零保护，是两个「生产必备但面试常考」的细节。

**除零的三种处理**：
1. `NULLIF(分母, 0)` —— 最通用，让 0 变成 NULL，结果为 NULL 而不报错
2. `CASE WHEN 分母 = 0 THEN NULL ELSE 分子/分母 END`
3. `分母 = 0 THEN 0`（业务上要求显示 0 时）

**为什么要补日期**：报表系统要求「每天都有数据点」，缺失日期会让折线图断掉、环比计算错位。所以数仓 ADS 层会有一批「日期骨架 + LEFT JOIN 指标」的任务。

**加餐（面试延伸）**：
- 如果补齐的是「用户 × 日期」的骨架，数据量会爆炸（用户数 × 天数），生产上要慎用，通常只在活跃用户子集上做。
- 大数据的日期序列生成：Hive 用 `posexplode(split(space(datediff(end,start)), ' '))`，DuckDB 用 `GENERATE_SERIES(start, end, INTERVAL 1 DAY)`。""",
    ),
    Exercise(
        id="dw_zip_snapshot",
        category=CAT_H,
        difficulty=2,
        title="拉链表：查询某天的用户全量快照",
        knowledge=["拉链表", "SCD2", "区间查询", "历史快照"],
        tables=["dim_user_zip"],
        params=lambda r: {"snap": _snap_date(r)},
        prompt="""dim_user_zip 是一张用户维度**拉链表**：每条记录表示用户在 [start_date, end_date] 区间内的属性版本，
当前有效的记录 end_date = 9999-12-31。

请查询 **{snap} 这一天**的用户全量快照。

输出列：user_id, user_name, city, member_level, start_date, end_date
排序：user_id 升序。""",
        solution="""SELECT user_id, user_name, city, member_level, start_date, end_date
FROM dim_user_zip
WHERE start_date <= DATE '{snap}'
  AND end_date   >= DATE '{snap}'
ORDER BY user_id""",
        hints=[
            "拉链表的每一行是一个「有效区间」，查某天快照就是查「该天落在哪个区间内」。",
            "条件：start_date <= 目标日期 AND end_date >= 目标日期（闭区间）。",
            "注意当前有效记录的 end_date 是 9999-12-31（开链），所以查询不需要额外分支。",
        ],
        notes="""**考点**：拉链表（SCD Type 2）—— 数仓面试的最高频建模题。

**什么是拉链表**：记录维度数据**历史变更**的表。每行有 `start_date` 和 `end_date`，代表该属性版本的有效期。

**三个必须答对的点**：
1. **查某天快照**：`start_date <= 日期 AND end_date >= 日期`（注意闭区间，有的公司用 `< end_date` 的开区间写法，要看清口径）
2. **当前有效**：`end_date = '9999-12-31'`（开链）
3. **为什么要拉链**：不用每天存全量快照（10 年 × 每天 1 亿行 = 巨大存储），只存变化，节省 90%+ 存储；同时能还原任意历史时刻的状态。

**对比其他 SCD 方案**：
| 类型 | 做法 | 缺点 |
|---|---|---|
| SCD1 | 直接覆盖旧值 | 丢失历史 |
| SCD2（拉链） | 加 start/end 日期，保留所有版本 | 表结构复杂，查询要带区间条件 |
| SCD3 | 增加「上一版本」字段 | 只能存上一个版本 |

**面试延伸**：拉链表某天记得住几条？→ 用 `COUNT(*)` 比 `COUNT(DISTINCT user_id)` 就能看出有变更的用户占比。""",
    ),
    Exercise(
        id="dw_zip_versions",
        category=CAT_H,
        difficulty=3,
        title="拉链表：统计用户属性变更次数（TopN）",
        knowledge=["拉链表", "版本分析", "count distinct", "TopN"],
        tables=["dim_user_zip"],
        params=lambda r: {"k": r.choice([10, 15, 20])},
        prompt="""基于拉链表 dim_user_zip，统计**属性变更最频繁**的前 {k} 个用户：
user_id、versions（历史版本数，即拉链行数）、cities（历史上出现过的不同城市数）、
levels（历史上出现过的不同会员等级数）

输出列：user_id, versions, cities, levels
排序：versions 降序、cities 降序、user_id 升序。""",
        solution="""SELECT user_id,
       COUNT(*) AS versions,
       COUNT(DISTINCT city) AS cities,
       COUNT(DISTINCT member_level) AS levels
FROM dim_user_zip
GROUP BY 1
ORDER BY versions DESC, cities DESC, user_id
LIMIT {k}""",
        hints=[
            "拉链表里同一用户有几行，就代表发生了几次属性变更（含初始版本）。",
            "版本数用 COUNT(*)，出现过的不同取值用 COUNT(DISTINCT 列)。",
            "排序时把 versions、cities、user_id 都写进 ORDER BY，保证结果稳定。",
        ],
        notes="""**考点**：从拉链表反推变更历史 —— 这是拉链表题目的进阶问法，考察你是否真的理解表结构。

**分析口径**：
- **版本数** = 拉链行数 = 初始版本 + 变更次数
- **首次值 / 最新值**：`MIN_BY(city, start_date)` / `MAX_BY(city, start_date)`（Hive 2.0+）或对 start_date 排序后取首尾
- **某属性变更了几次**：`COUNT(DISTINCT 属性)` - 1（本用例的 cities - 1）

**面试延伸**：
1. 「拉链表怎么更新？」→ 关链（把当前有效行的 end_date 改成昨天）+ 开链（新变更数据 start_date = 今天，end_date = 9999-12-31）—— 见下一题。
2. 「拉链表怎么优化查询？」→ 每天产出一份「当日快照」宽表供下游直查，避免每次都做区间判断。
3. 「变更频率高的维度适合拉链吗？」→ 不适合（行数会爆炸），考虑 SCD1 + 变更日志表。""",
    ),
    Exercise(
        id="dw_zip_merge",
        category=CAT_H,
        difficulty=3,
        title="拉链表 T+1 更新：关链 + 开链",
        knowledge=["拉链表", "关链开链", "union all", "left join"],
        tables=["dim_user_zip"],
        params=lambda r: dict(_upd_users(r), snap="2026-06-30"),
        prompt="""今天是 **{snap}**，当天有 2 条用户属性变更需要合并进拉链表 dim_user_zip：

| user_id | city | member_level |
|---|---|---|
| {uid_a} | {city_a} | {lv_a} |
| {uid_b} | {city_b} | {lv_b} |

请写出**合并后的完整拉链表**（关链 + 开链）：
- 被变更用户的原「当前有效记录」（end_date = 9999-12-31）的 end_date 改为 {snap} 的前一天
- 新增两条记录：start_date = {snap}，end_date = 9999-12-31，取新的 city / member_level，user_name 沿用原值
- 其他记录原样保留

输出列：user_id, user_name, city, member_level, start_date, end_date
排序：user_id、start_date 升序。

提示：变更表可以用 `SELECT * FROM (VALUES ...) AS t(user_id, city, member_level)` 在 SQL 里直接构造，不要新建表。""",
        solution="""WITH upd AS (
  SELECT * FROM (VALUES ({uid_a}, '{city_a}', '{lv_a}'), ({uid_b}, '{city_b}', '{lv_b}'))
    AS t(user_id, city, member_level)
),
closed AS (
  SELECT z.user_id, z.user_name, z.city, z.member_level, z.start_date,
         CASE WHEN u.user_id IS NOT NULL AND z.end_date = DATE '9999-12-31'
              THEN DATE '{snap}' - 1 ELSE z.end_date END AS end_date
  FROM dim_user_zip z
  LEFT JOIN upd u ON z.user_id = u.user_id
),
opened AS (
  SELECT u.user_id, z.user_name, u.city, u.member_level,
         DATE '{snap}' AS start_date, DATE '9999-12-31' AS end_date
  FROM upd u
  JOIN dim_user_zip z ON u.user_id = z.user_id AND z.end_date = DATE '9999-12-31'
)
SELECT * FROM closed
UNION ALL
SELECT * FROM opened
ORDER BY user_id, start_date""",
        hints=[
            "拆成两部分：关链（改旧记录的 end_date）+ 开链（插入新版本），最后 UNION ALL。",
            "关链用 LEFT JOIN 变更表，只对「当前有效记录」（end_date = 9999-12-31）做 CASE WHEN 改 end_date。",
            "开链要拿变更值 + 原表的 user_name，所以用变更表 JOIN 原表的当前有效记录。",
        ],
        notes="""**考点**：拉链表的更新逻辑 —— 面试如果问到「拉链表怎么维护」，答这个。

**标准流程**：
1. **关链**：把变更用户当前有效行的 `end_date` 改成「昨天」（新版本生效日 - 1）
2. **开链**：插入新版本，`start_date` = 今天，`end_date` = 9999-12-31
3. **合并**：`UNION ALL` 两部分 + 未变更的原记录

**生产落地细节**（面试加分项）：
- 通常写成 **INSERT OVERWRITE 全表重建** 或 **分区增量**：按「变更日」分区存增量，代价是查询要聚合多个分区
- 也可以用 `MERGE INTO`（Hive 3.x / Spark 3 / Doris 支持 update + insert）
- **幂等性**：重跑必须用全表重建模式（overwrite），否则会重复开链
- **NULL 处理**：如果变更字段为 NULL，表示该字段无变化，要写 `COALESCE(新值, 老值)`

**面试话术**：「我一般用 INSERT OVERWRITE 全表重建保证幂等，变更数据来自业务库的 Binlog 抽取；如果有分区，就按 dt 分区存每日增量 + 一份当日全量快照表供下游直查。」""",
    ),
    Exercise(
        id="dw_quality_check",
        category=CAT_H,
        difficulty=3,
        title="数据质量校验：4 条规则查出脏数据",
        knowledge=["数据质量", "唯一性", "非空", "合法性", "一致性"],
        tables=["dwd_order", "dim_user"],
        prompt="""对订单表 dwd_order 做一次数据质量体检，**输出一行** 4 个指标：
- dup_order_id：order_id 重复的订单个数（即重复出现的 order_id 有多少个）
- null_user_orders：user_id 为空的订单数
- bad_amount_orders：amount 小于等于 0 的订单数
- orphan_orders：user_id 在 dim_user 中不存在的订单数（孤儿记录）

输出列：dup_order_id, null_user_orders, bad_amount_orders, orphan_orders""",
        solution="""SELECT
  (SELECT COUNT(*) FROM (
      SELECT order_id FROM dwd_order GROUP BY order_id HAVING COUNT(*) > 1
   ) d) AS dup_order_id,
  (SELECT COUNT(*) FROM dwd_order WHERE user_id IS NULL) AS null_user_orders,
  (SELECT COUNT(*) FROM dwd_order WHERE amount <= 0) AS bad_amount_orders,
  (SELECT COUNT(*) FROM dwd_order o
     LEFT JOIN dim_user u ON o.user_id = u.user_id
   WHERE o.user_id IS NOT NULL AND u.user_id IS NULL) AS orphan_orders""",
        hints=[
            "四条规则对应数据质量的四个维度：唯一性、非空、合法性、一致性。",
            "重复主键的查法：GROUP BY 主键 HAVING COUNT(*) > 1，再 COUNT 一下有多少个这样的主键。",
            "孤儿记录用 LEFT JOIN 维表 + WHERE 维表主键 IS NULL（注意先排除 user_id 本身为空的行，两类问题要分开统计）。",
        ],
        notes="""**考点**：数据质量校验 —— 数据平台 / 数仓开发面试的高频考点，也是入职后的日常。

**数据质量六大维度**（背下来）：
| 维度 | 含义 | 典型规则 |
|---|---|---|
| 唯一性 | 主键唯一 | 主键重复数 = 0 |
| 完整性/非空 | 关键字段不为空 | user_id IS NOT NULL |
| 有效性/合法性 | 取值在合理范围 | amount > 0、状态枚举合法 |
| 一致性 | 跨表一致、口径一致 | 事实表能关联上维表（无孤儿）、实时与离线对账 |
| 及时性 | 数据按时产出 | 任务 SLA、分区就绪时间 |
| 准确性 | 与源系统或业务真值一致 | 总量对账、抽样比对 |

**生产做法**：
1. 规则配置化（阈值可调），异常分级告警（企业微信 / 钉钉 / 邮件）
2. **波动检测**：同环比超过 ±30% 自动告警（比固定阈值更灵敏）
3. 出问题要有**影响面分析**（血缘定位下游）和**回滚/补数**预案
4. 质量分（每个表一个分数）挂到数据地图上，让使用方看到可信度

**面试话术**：「数据质量我用规则引擎 + 波动检测双轨：规则覆盖唯一/非空/枚举/值域，波动检测看同环比突变；告警后先止血（标记数据不可用）再定位根因，最后补数并沉淀规则。」""",
    ),
]
