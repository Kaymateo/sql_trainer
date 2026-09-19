"""题库 B：留存与漏斗 / 聚合进阶 / 行列转换"""
from bank.spec import Exercise, case_pivot, in_list

CAT_C = "留存与漏斗"
CAT_D = "聚合进阶"
CAT_E = "行列转换"

_CATS_PIVOT = ("手机数码", "服饰鞋包", "食品生鲜", "家居日用", "美妆个护")

EXERCISES = [
    # ───────────────────────── 留存与漏斗 ─────────────────────────
    Exercise(
        id="fun_retention_d1",
        category=CAT_C,
        difficulty=3,
        title="分月次日留存率",
        knowledge=["留存率", "left join", "日期加减", "口径"],
        tables=["dim_user", "dwd_page_event"],
        prompt="""以 dim_user 的注册日 reg_date 为准，计算**每个月新增用户的次日留存率**（注册次日仍有页面事件的用户占比）。

输出列：ym（形如 2025-03）、new_users（当月新增用户数）、d1_users（次日留存用户数）、d1_rate（次日留存率百分比，保留 2 位小数）
排序：ym 升序。""",
        solution="""WITH act AS (
  SELECT DISTINCT user_id, dt FROM dwd_page_event
),
j AS (
  SELECT u.user_id, u.reg_date,
         CASE WHEN a.dt IS NOT NULL THEN 1 ELSE 0 END AS is_d1
  FROM dim_user u
  LEFT JOIN act a
    ON a.user_id = u.user_id AND a.dt = u.reg_date + 1
)
SELECT STRFTIME(reg_date, '%Y-%m') AS ym,
       COUNT(*) AS new_users,
       SUM(is_d1) AS d1_users,
       ROUND(SUM(is_d1) * 100.0 / COUNT(*), 2) AS d1_rate
FROM j
GROUP BY 1
ORDER BY ym""",
        hints=[
            "留存的分母是「当天新增用户」，分子是「这批用户里第二天还活跃的」。",
            "活跃判断要去重：SELECT DISTINCT user_id, dt FROM dwd_page_event（一天多次访问算一次）。",
            "用 LEFT JOIN 关联「注册日 + 1 天」的活跃记录：关联到就是留存，关联不到就是流失 —— 不能用 INNER JOIN，会把流失用户丢掉、留存率虚高。",
        ],
        notes="""**考点**：留存率是数仓分析师最常被问的指标，口径必须说清楚。

**标准口径（面试口播）**：
> 次日留存率 = 注册当天的新增用户中，注册次日有活跃行为的用户数 / 当天新增用户数。

**三个易错点**：
1. **必须 LEFT JOIN**：用 INNER JOIN 会把「没有次日活跃」的用户整个丢掉，分母变小 → 留存率虚高。这是最高频的错误。
2. **活跃要去重**：一天多次访问算一个用户，"按天去重"是留存计算的前提。
3. **日期 +1 的写法**：DuckDB / MySQL 用 `reg_date + 1`（或 `DATE_ADD(reg_date, INTERVAL 1 DAY)`）；Hive 用 `date_add(reg_date, 1)`。

**延伸追问**：
- 7 日留存 → 把 `+1` 改成 `+7`；如果要求「第 7 天当天活跃」就是经典 7 日留存，如果要「7 天内任意一天活跃」口径不同。
- 留存矩阵（注册日 × 第 N 天）→ 用 CROSS JOIN 生成 0..N 的偏移天数序列再 LEFT JOIN，最后 PIVOT 成矩阵。""",
    ),
    Exercise(
        id="fun_funnel",
        category=CAT_C,
        difficulty=2,
        title="行为漏斗转化率（浏览 → 加购 → 下单 → 支付）",
        knowledge=["漏斗", "多指标一次算出", "标量子查询"],
        tables=["dwd_page_event"],
        prompt="""基于埋点表 dwd_page_event，统计 4 个步骤的**去重用户数**与相对第一步的转化率：
浏览(view) → 加购(add_cart) → 提交订单(submit_order) → 支付(pay)。

输出列：step（事件类型）、users（去重用户数）、rate（相对 view 的转化率百分比，保留 2 位小数）
排序：按漏斗顺序 view → add_cart → submit_order → pay。""",
        solution="""WITH s AS (
  SELECT event_type, COUNT(DISTINCT user_id) AS users
  FROM dwd_page_event
  WHERE event_type IN ('view', 'add_cart', 'submit_order', 'pay')
  GROUP BY 1
)
SELECT event_type AS step, users,
       ROUND(users * 100.0 / (SELECT users FROM s WHERE event_type = 'view'), 2) AS rate
FROM s
ORDER BY CASE event_type
           WHEN 'view' THEN 1 WHEN 'add_cart' THEN 2
           WHEN 'submit_order' THEN 3 ELSE 4 END""",
        hints=[
            "四个步骤 = 四个事件类型，用 COUNT(DISTINCT user_id) 按事件类型分组统计。",
            "转化率的分母是第一步的 users，用标量子查询 (SELECT users FROM s WHERE event_type='view') 拿。",
            "输出顺序要和漏斗顺序一致，用 CASE WHEN 把事件类型映射成 1/2/3/4 再排序。",
        ],
        notes="""**考点**：漏斗分析。三个关键点：

1. **去重**：漏斗每一步统计的是「人数」不是「次数」，必须 COUNT(DISTINCT user_id)。
2. **严格漏斗 vs 宽松漏斗**：严格漏斗要求用户按顺序发生行为且时间递增（需要按用户+时间做序列判断）；宽松漏斗只看「有没有发生」。面试一定要先问口径！本题是宽松漏斗。
3. **分母**：相对第一步转化率 = 本步 / 第一步；「步骤间转化率」= 本步 / 上一步，两者不要混。

**严格漏斗的写法**（进阶）：按用户取每个事件的最早时间，然后 `view_time < cart_time < order_time < pay_time` 逐级过滤，或用窗口函数 + 行序列比较。

**Hive 中常用**：`COUNT(DISTINCT IF(event='pay', user_id, NULL))` 一次算出多列，避免多次扫表。""",
    ),
    Exercise(
        id="fun_repurchase",
        category=CAT_C,
        difficulty=2,
        title="复购率与人均下单次数",
        knowledge=["复购率", "多指标聚合", "口径"],
        tables=["dwd_order"],
        prompt="""基于已支付订单，统计整体的复购情况（**一行结果**）：
buyers（有支付订单的用户数）、repeat_buyers（支付订单数 ≥ 2 的用户数）、repeat_rate（复购率百分比，2 位小数）、
avg_orders（人均支付订单数，2 位小数）、arpu（人均支付金额，2 位小数）。

输出列：buyers, repeat_buyers, repeat_rate, avg_orders, arpu""",
        solution="""WITH u AS (
  SELECT user_id, COUNT(*) AS cnt, SUM(amount) AS amt
  FROM dwd_order
  WHERE order_status = '已支付'
  GROUP BY 1
)
SELECT COUNT(*) AS buyers,
       SUM(CASE WHEN cnt >= 2 THEN 1 ELSE 0 END) AS repeat_buyers,
       ROUND(SUM(CASE WHEN cnt >= 2 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS repeat_rate,
       ROUND(AVG(cnt), 2) AS avg_orders,
       ROUND(AVG(amt), 2) AS arpu
FROM u""",
        hints=[
            "先把订单聚合到用户粒度：每人几笔、共多少钱。",
            "复购用户 = 笔数 ≥ 2 的用户，用 SUM(CASE WHEN cnt >= 2 THEN 1 ELSE 0 END) 计数。",
            "人均指标注意分母：这里的分母是「有支付行为的用户数」，不是全部注册用户 —— arpu 通常按全部用户算，arpu（下单用户）是两回事，面试要说清口径。",
        ],
        notes="""**考点**：复购率 + 人均指标，考察你是否理解「分子分母口径」。

**必背口径辨析**：
- **复购率** = 支付 ≥ 2 次的用户数 / 有支付行为的用户数
- **人均订单数** = 总订单数 / 有支付行为的用户数
- **ARPU** = 总收入 / **全部用户数**（含未下单用户）；分母换成分层用户就是 ARPPU
- 面试官常追问：「你的 ARPU 分母是注册用户还是活跃用户？」—— 答不上来就掉分。

**小技巧**：`SUM(CASE WHEN ... THEN 1 ELSE 0 END)` 等价于 `COUNT(*) FILTER (WHERE ...)`（DuckDB / PostgreSQL 支持），但 Hive 不支持 FILTER，所以 CASE WHEN 更通用 —— 面试写 CASE WHEN 最稳。

**延伸**：按品类算复购率 → 先 GROUP BY user_id, category 算每人每品类的购买次数，再统计 ≥ 2 的占比。""",
    ),
    Exercise(
        id="fun_new_old_gmv",
        category=CAT_C,
        difficulty=3,
        title="新客与老客的 GMV 贡献",
        knowledge=["新老客划分", "first order", "占比计算"],
        tables=["dwd_order"],
        params=lambda r: {"w": r.choice([0, 1, 3])},
        prompt="""以每个用户的**首笔已支付订单日期**为界：订单日期等于首单日期的算「新客」，晚于首单日期 {w} 天及以上的算「老客」
（即 `dt >= first_dt + {w}` 时算老客）。

按新老客分组统计：customer_type、users（去重用户数）、orders（订单数）、gmv（2 位小数）、gmv_pct（GMV 占比百分数，2 位小数）
排序：customer_type 升序。""",
        solution="""WITH f AS (
  SELECT user_id, MIN(dt) AS first_dt
  FROM dwd_order WHERE order_status = '已支付' GROUP BY 1
),
t AS (
  SELECT o.user_id, o.amount,
         CASE WHEN o.dt >= f.first_dt + {w} THEN '老客' ELSE '新客' END AS customer_type
  FROM dwd_order o
  JOIN f ON o.user_id = f.user_id
  WHERE o.order_status = '已支付'
)
SELECT customer_type,
       COUNT(DISTINCT user_id) AS users,
       COUNT(*) AS orders,
       ROUND(SUM(amount), 2) AS gmv,
       ROUND(SUM(amount) * 100.0 / (SELECT SUM(amount) FROM t), 2) AS gmv_pct
FROM t
GROUP BY 1
ORDER BY customer_type""",
        hints=[
            "第一步找出每个用户的首单日期：MIN(dt) GROUP BY user_id。",
            "第二步把首单日期关联回订单明细（join on user_id），用 CASE WHEN 打新老客标签。",
            "占比的分母是全部 GMV，可以用标量子查询 (SELECT SUM(amount) FROM t) —— t 就是你已经分好标签的那张表。",
        ],
        notes="""**考点**：新老客划分与贡献度分析，是最常见的「经营分析」类题目。

**口径要点**：
1. **首单定义**：通常用「首笔支付成功的订单日期」作为用户的生命周期起点（本题用的口径）。
2. **新老客不是按注册时间判断**，而是按**首次交易时间**判断 —— 这是最容易答错的点。
3. 间隔参数 w：w=0 表示「首单当天算新客」，w=1 表示「次日即算老客」。真实业务里还会用「自然月内首次下单算新客」的口径。

**面试追问**：
- 老客的复购周期怎么算？→ 相邻订单日期差（LAG），再取中位数。
- 新客的获取成本 / ROI 怎么算？→ 需要投放花费表，按渠道 join。
- 为什么老客 GMV 占比高？→ 要能给出业务解释（复购频次高、客单价变化）。""",
    ),
    Exercise(
        id="fun_active_layer",
        category=CAT_C,
        difficulty=2,
        title="各城市的会话质量（人均 PV 与跳出率）",
        knowledge=["分组聚合", "业务比率", "case when"],
        tables=["dwd_page_event", "dim_user"],
        prompt="""以埋点表自带的 session_id 为会话标识，按用户所在城市（dim_user.city）统计：
sessions（会话数）、avg_pv（人均会话页面数，2 位小数）、bounce_rate（跳出率 = 只有 1 个页面事件的会话占比，百分数 2 位小数）。

输出列：city, sessions, avg_pv, bounce_rate，按 city 升序。""",
        solution="""WITH s AS (
  SELECT user_id, session_id, COUNT(*) AS pv
  FROM dwd_page_event
  GROUP BY 1, 2
),
c AS (
  SELECT d.city, s.pv
  FROM s JOIN dim_user d ON s.user_id = d.user_id
)
SELECT city,
       COUNT(*) AS sessions,
       ROUND(AVG(pv), 2) AS avg_pv,
       ROUND(SUM(CASE WHEN pv = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS bounce_rate
FROM c
GROUP BY 1
ORDER BY city""",
        hints=[
            "先算会话粒度的数据：按 (user_id, session_id) 分组 COUNT(*) 得到每个会话的页面数。",
            "再用 (user_id → city) 关联用户维表，把会话挂到城市上。",
            "跳出率 = 页面数为 1 的会话占比，用 SUM(CASE WHEN pv = 1 THEN 1 ELSE 0 END) / COUNT(*)。",
        ],
        notes="""**考点**：从明细 → 会话粒度 → 城市粒度的两级聚合，考察「聚合粒度」意识。

**关键意识**：同一份数据可以按不同粒度看 —— 明细行、会话、用户、天、城市。分析前先明确「一行代表什么」，这是数仓最基本的思维。

**常见追问**：
- 人均 PV 的分母能不能用「全部用户」？→ 那叫「人均页面数」而不是「人均会话页面数」，口径不同结果差很多。
- 跳出率有多重定义（单页会话 / 停留时间 < 5 秒 / 无二次交互），面试要主动说明你选哪一种。
- 如果 session_id 不可信怎么办？→ 见「会话切割」那道题（按 30 分钟超时自己切）。""",
    ),

    # ───────────────────────── 聚合进阶 ─────────────────────────
    Exercise(
        id="agg_rollup",
        category=CAT_D,
        difficulty=3,
        title="城市 × 品类销售额的多级汇总（ROLLUP）",
        knowledge=["rollup", "grouping sets", "小计行", "coalesce"],
        tables=["dwd_order", "dim_user", "dim_product"],
        prompt="""统计「城市 × 品类」的销售额，并**同时输出小计与总计**：
- 明细行：city + category 都有值
- 城市小计行：category 显示为 'ALL'
- 总计行：city 和 category 都显示为 'ALL'

输出列：city, category, sales（2 位小数）、orders（订单数）
排序：city 升序、category 升序（'ALL' 按字典序参与排序）。
只统计已支付订单。""",
        solution="""SELECT COALESCE(u.city, 'ALL') AS city,
       COALESCE(p.category, 'ALL') AS category,
       ROUND(SUM(o.amount), 2) AS sales,
       COUNT(*) AS orders
FROM dwd_order o
JOIN dim_user u ON o.user_id = u.user_id
JOIN dim_product p ON o.product_id = p.product_id
WHERE o.order_status = '已支付'
GROUP BY ROLLUP(u.city, p.category)
ORDER BY city, category""",
        hints=[
            "ROLLUP(a, b) 会一次生成：a+b 明细、a 级小计、全表总计 —— 一步到位，不用写多次 UNION ALL。",
            "ROLLUP 生成的小计行里被汇总的维度是 NULL，用 COALESCE(..., 'ALL') 显示成文本。",
            "DuckDB / Hive / Spark 都支持 GROUP BY ROLLUP；MySQL 用 WITH ROLLUP 后缀。",
        ],
        notes="""**考点**：多级汇总的两种写法 —— `GROUP BY ROLLUP / GROUPING SETS / CUBE`。

| 写法 | 生成的分组 |
|---|---|
| GROUP BY a, b | 只有 a+b |
| GROUP BY ROLLUP(a, b) | a+b、a、总计（有层次的汇总） |
| GROUP BY CUBE(a, b) | a+b、a、b、总计（所有组合） |
| GROUP BY GROUPING SETS((a,b),(b)) | 只生成你指定的组合 |

**关键细节**：
1. 小计行的维度值是 NULL，用 COALESCE 或 `GROUPING()` 函数处理（`GROUPING(col)=1` 表示该行是汇总行）。
2. 生产上「明细 + 小计 + 总计」放同一张结果表，下游 BI 直接展示，避免前端再算。
3. UNION ALL 手写也能实现，但会多次扫表；ROLLUP 一次扫描更快 —— 面试问到就说这句。

**面试延伸**：如果小计行要区分「城市小计」和「总计」，可以用 `GROUPING_ID()` 或再加一个 `CASE WHEN city='ALL' THEN 2 WHEN category='ALL' THEN 1 ELSE 0 END AS level` 级别列。""",
    ),
    Exercise(
        id="agg_quantile",
        category=CAT_D,
        difficulty=2,
        title="各品类订单金额的中位数与 P90",
        knowledge=["median", "quantile", "分位数"],
        tables=["dwd_order", "dim_product"],
        prompt="""统计每个品类已支付订单的金额分布：orders（订单数）、med（中位数，2 位小数）、p90（90 分位数，2 位小数）、
avg_amt（平均金额，2 位小数）。

输出列：category, orders, med, p90, avg_amt，按 category 升序。""",
        solution="""SELECT p.category,
       COUNT(*) AS orders,
       ROUND(MEDIAN(o.amount), 2) AS med,
       ROUND(QUANTILE_CONT(o.amount, 0.9), 2) AS p90,
       ROUND(AVG(o.amount), 2) AS avg_amt
FROM dwd_order o
JOIN dim_product p ON o.product_id = p.product_id
WHERE o.order_status = '已支付'
GROUP BY 1
ORDER BY category""",
        hints=[
            "DuckDB / Hive 都有 MEDIAN() 和 PERCENTILE / QUANTILE_CONT 函数。",
            "DuckDB 写法：QUANTILE_CONT(x, 0.9) 是连续插值分位数，QUANTILE_DISC 是取实际存在的值。",
            "Hive 里中位数可用 PERCENTILE(amount, 0.5)（Hive 2.0+ 有 percentile_approx）。",
        ],
        notes="""**考点**：分位数计算。中位数是「抗极值」指标，面试常用来对比平均值。

**为什么业务方要看中位数**：订单金额长尾分布，平均值会被大额订单拉高，中位数更能代表「典型用户」。

**实现方式**：
1. `MEDIAN(x)` —— 最直接（DuckDB / Hive / Presto 都支持）
2. `PERCENTILE(x, 0.5)` —— Hive 2.0 之前用这个
3. `percentile_approx(x, 0.5)` —— 大数据量场景（Hive），有误差但快很多，**生产环境常答这个**
4. **面试手写版**（考察窗口函数功底）：
```sql
SELECT category, AVG(amount) AS med FROM (
  SELECT category, amount,
         ROW_NUMBER() OVER (PARTITION BY category ORDER BY amount) AS rn,
         COUNT(*)     OVER (PARTITION BY category) AS cnt
  FROM dwd_order WHERE order_status='已支付'
) t
WHERE rn IN ((cnt+1)/2, (cnt+2)/2)
GROUP BY category;
```
这个写法（上下中位数取平均）是必背的，因为面试官常要求「不许用内置中位数函数」。""",
    ),
    Exercise(
        id="agg_multi_metric",
        category=CAT_D,
        difficulty=2,
        title="一次扫表算出多个指标（含退款率）",
        knowledge=["条件聚合", "多指标", "case when"],
        tables=["dwd_order", "dim_user"],
        prompt="""按城市（dim_user.city）统计订单的整体情况：
orders（全部订单数）、paid_orders（已支付订单数）、refund_orders（已退款订单数）、
pay_rate（支付率 = 已支付/全部，百分数 2 位小数）、refund_rate（退款率 = 已退款/全部，百分数 2 位小数）。

输出列：city, orders, paid_orders, refund_orders, pay_rate, refund_rate，按 city 升序。""",
        solution="""SELECT u.city,
       COUNT(*) AS orders,
       SUM(CASE WHEN o.order_status = '已支付' THEN 1 ELSE 0 END) AS paid_orders,
       SUM(CASE WHEN o.order_status = '已退款' THEN 1 ELSE 0 END) AS refund_orders,
       ROUND(SUM(CASE WHEN o.order_status = '已支付' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS pay_rate,
       ROUND(SUM(CASE WHEN o.order_status = '已退款' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 2) AS refund_rate
FROM dwd_order o
JOIN dim_user u ON o.user_id = u.user_id
GROUP BY 1
ORDER BY city""",
        hints=[
            "条件聚合：SUM(CASE WHEN 条件 THEN 1 ELSE 0 END) 就是「满足条件的行数」。",
            "所有指标都在同一个 SELECT 里算，只扫一次表 —— 这是数仓开发的基本要求。",
            "比率的分母都是 COUNT(*)（全部订单），注意分子分母不要搞混。",
        ],
        notes="""**考点**：条件聚合（一次扫描出多个指标）。生产数仓中一个 ADS 指标表往往有几十个指标，绝对不能一张表扫几十遍。

**写法对比**：
- 通用：`SUM(CASE WHEN cond THEN 1 ELSE 0 END)`（Hive / Spark / MySQL 全支持，面试首选）
- 现代：`COUNT(*) FILTER (WHERE cond)`（DuckDB / PostgreSQL / Spark 2.4+），更简洁但 Hive 不支持
- 金额类：`SUM(CASE WHEN cond THEN amount ELSE 0 END)`

**口径提示**：退款率的分母建议用「已支付订单数」而不是「全部订单数」（只有支付成功的订单才可能退款）—— 面试时主动说明你的口径选择，这是加分点。本题为演示多指标写法统一用了全部订单数，实际业务建议分口径。

**延伸追问**：如果还要算「净收入」= 支付金额 - 退款金额，怎么写？→ `SUM(CASE WHEN order_status='已支付' THEN amount WHEN order_status='已退款' THEN 0 ELSE 0 END)` 配合退款表的金额做减法。""",
    ),
    Exercise(
        id="agg_bucket",
        category=CAT_D,
        difficulty=1,
        title="订单金额分桶统计",
        knowledge=["case when 分桶", "占比", "自定义排序"],
        tables=["dwd_order"],
        prompt="""把已支付订单按金额分为 4 档：0-500、500-1000、1000-3000、3000 以上（区间为左闭右开）。

输出列：bucket（档位名称，如 '0-500'、'500-1000'、'1000-3000'、'3000+'）、bucket_order（1~4，用于排序）、
orders（订单数）、gmv（2 位小数）、order_pct（订单数占比百分数，2 位小数）
排序：bucket_order 升序。""",
        solution="""WITH b AS (
  SELECT CASE
           WHEN amount < 500  THEN '0-500'
           WHEN amount < 1000 THEN '500-1000'
           WHEN amount < 3000 THEN '1000-3000'
           ELSE '3000+'
         END AS bucket,
         CASE
           WHEN amount < 500  THEN 1
           WHEN amount < 1000 THEN 2
           WHEN amount < 3000 THEN 3
           ELSE 4
         END AS bucket_order,
         amount
  FROM dwd_order
  WHERE order_status = '已支付'
)
SELECT bucket, bucket_order,
       COUNT(*) AS orders,
       ROUND(SUM(amount), 2) AS gmv,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS order_pct
FROM b
GROUP BY 1, 2
ORDER BY bucket_order""",
        hints=[
            "分桶用 CASE WHEN，注意从上到下判断，写 `< 500`、`< 1000` 这种递进条件就不用写区间上下界。",
            "为了排序正确，额外输出一个 bucket_order（1~4）作为排序键 —— 纯文本排序会得到 '0-500', '1000-3000', '3000+', '500-1000' 这种奇怪顺序。",
            "占比的分母用 SUM(COUNT(*)) OVER ()：窗口函数作用在聚合结果上，一次算出总订单数。",
        ],
        notes="""**考点**：分桶 + 占比 + 自定义排序键，是「分布分析」类题目的标准结构。

**要点**：
1. **分桶边界**：明确左闭右开还是左开右闭，边界值归哪一档要说清楚（面试必问）。
2. **排序键**：文本分档必须附带一个数值排序键，否则 BI 上展示顺序会乱 —— 这个细节很能体现生产经验。
3. **占比写法**：`COUNT(*) * 100.0 / SUM(COUNT(*)) OVER ()`，窗口函数在 GROUP BY 之后执行，所以可以直接对聚合结果再求和。
4. **兜底**：真实数据可能有负数或 NULL，要加 `ELSE '异常'` 分支。

**延伸**：分位数分桶（用 NTILE 或 percentile 边界）、RFM 分档、用户消费分层。""",
    ),

    # ───────────────────────── 行列转换 ─────────────────────────
    Exercise(
        id="piv_category_city_case",
        category=CAT_E,
        difficulty=2,
        title="行转列：城市 × 品类销售额矩阵（CASE WHEN 通用写法）",
        knowledge=["行转列", "条件聚合", "crosstab"],
        tables=["dwd_order", "dim_user", "dim_product"],
        params=lambda r: {"cats": sorted(r.sample(_CATS_PIVOT, r.choice([3, 3, 4]))),
                          "sql_cols": ""},
        prompt="""把「城市 × 品类」的销售额做成**宽表**（每个品类一列），只统计已支付订单，并且**只保留**这几个品类：{cats_text}。

输出列：city，然后每个品类一列（列名用品类名，值为该城市在该品类的销售额，2 位小数）
排序：city 升序。
提示：不存在的组合要输出 0，不要输出 NULL。""",
        solution="""SELECT u.city,
  {sql_cols_cats}
FROM dwd_order o
JOIN dim_user u ON o.user_id = u.user_id
JOIN dim_product p ON o.product_id = p.product_id
WHERE o.order_status = '已支付'
  AND p.category IN ({sql_in_cats})
GROUP BY 1
ORDER BY city""",
        hints=[
            "行转列的本质是「条件聚合」：每个目标列写一个 CASE WHEN 判断维度值，再对度量求和。",
            "列名要用双引号包住中文，例如 CASE WHEN p.category='手机数码' THEN o.amount ELSE 0 END AS \"手机数码\"。",
            "ELSE 0 保证不存在的组合输出 0 而不是 NULL；外层用 SUM 聚合，GROUP BY 城市。",
        ],
        notes="""**考点**：行转列（crosstab），数仓面试必考，因为报表几乎都是宽表。

**万能模板**（背下来）：
```sql
SELECT 固定维度,
       SUM(CASE WHEN 分类列 = '值1' THEN 度量 ELSE 0 END) AS "值1",
       SUM(CASE WHEN 分类列 = '值2' THEN 度量 ELSE 0 END) AS "值2"
FROM 表
GROUP BY 固定维度;
```

**四个细节**：
1. `ELSE 0` vs `ELSE NULL`：想让缺失组合显示 0 就用 ELSE 0；想区分「没有数据」和「为 0」就用 ELSE NULL。
2. **分组冲突**：如果同一个城市同一个品类有多行，必须在外层 SUM 聚合，否则报错。
3. **中文列名**要加双引号（标准 SQL）或反引号（MySQL）。
4. **列数写死**是这种写法的最大缺点：新增品类要改 SQL。生产上一般用调度参数动态生成，或改用 PIVOT / BI 层透视。

**Hive 特有写法**：`collect_list` + `str_to_map` / `map(key, value)` 也可以做行转列，但 CASE WHEN 最通用。""",
    ),
    Exercise(
        id="col_aggregate_list",
        category=CAT_E,
        difficulty=2,
        title="列转行（上）：把多行金额拼成一行字符串/数组",
        knowledge=["string_agg", "list", "array_to_string", "collect_list"],
        tables=["dwd_order"],
        params=lambda r: {"max_uid": r.choice([20, 30, 40])},
        prompt="""对 user_id ≤ {max_uid} 的用户，把他们**每一笔订单的金额按时间顺序拼起来**：
amt_str（用 | 连接的字符串）、amt_list_len（订单笔数）、first_amount（首单金额）、last_amount（末单金额）。

输出列：amt_str, amt_list_len, first_amount, last_amount, user_id
要求：每个用户一行（只保留有订单的用户），按 user_id 升序。""",
        solution="""SELECT STRING_AGG(CAST(amount AS VARCHAR), '|' ORDER BY order_time, order_id) AS amt_str,
       COUNT(*) AS amt_list_len,
       ARBITRARY(amount ORDER BY order_time, order_id) AS first_amount,
       ARBITRARY(amount ORDER BY order_time DESC, order_id DESC) AS last_amount,
       user_id
FROM dwd_order
WHERE user_id <= {max_uid}
GROUP BY user_id
ORDER BY user_id""",
        hints=[
            "把多行拼成一个值：STRING_AGG(表达式, '分隔符' ORDER BY 排序键)。",
            "Hive 里对应 collect_list() 收集数组、collect_set() 去重收集、concat_ws('|', collect_list(...)) 拼字符串。",
            "想同时拿排序后的首尾元素，可以用 ARBITRARY(x ORDER BY ...)（取排序后的第一个），或 max_by / min_by。",
        ],
        notes="""**考点**：多行 → 一行的「聚合拼接」，是 Hive 的高频行列转换考点。

**函数对照表**（面试常被让「说出 Hive 里对应写法」）：

| 需求 | DuckDB | Hive |
|---|---|---|
| 拼字符串 | STRING_AGG(x, ',') | concat_ws(',', collect_list(x)) |
| 收集数组（保序、有重复） | LIST(x) / ARRAY_AGG(x) | collect_list(x) |
| 收集数组（去重） | LIST(DISTINCT x) | collect_set(x) |
| 取首/末元素 | ARBITRARY(x ORDER BY t) / MIN_BY / MAX_BY | min_by / max_by（Hive 2.0+） |

**注意**：
1. collect_list 的顺序**不保证**，生产上要先用子查询排序再收集（Hive 里常写 `sort_array` 或先 `ORDER BY` 再过一层）。
2. 拼接长字符串会消耗内存，字段多、行数大时要谨慎 —— 面试问到内存问题可以提这点。

**延伸**：用户行为路径分析（浏览 → 加购 → 下单的顺序）就是 collect_list + 排序的典型应用。""",
    ),
    Exercise(
        id="row_explode_list",
        category=CAT_E,
        difficulty=2,
        title="列转行（下）：把数组炸成多行（explode / unnest）",
        knowledge=["unnest", "explode", "lateral view"],
        tables=["dwd_order"],
        params=lambda r: {"max_uid": r.choice([3, 5, 6])},
        prompt="""对 user_id ≤ {max_uid} 的用户，先把每个用户的订单金额收集成一个**数组**（按 order_time 升序、order_id 升序），
然后把这个数组**炸成多行**输出。

输出列：user_id, amount_item（数组中的单个金额）、item_index（在数组中的序号，从 1 开始）、total_items（该用户的订单总数）
要求：一行一个金额；排序按 user_id、item_index 升序。""",
        solution="""WITH a AS (
  SELECT user_id,
         LIST(amount ORDER BY order_time, order_id) AS amts
  FROM dwd_order
  WHERE user_id <= {max_uid}
  GROUP BY 1
)
SELECT user_id,
       UNNEST(amts) AS amount_item,
       GENERATE_SUBSCRIPTS(amts, 1) AS item_index,
       LEN(amts) AS total_items
FROM a
ORDER BY user_id, item_index""",
        hints=[
            "先把多行聚合成数组：LIST(amount ORDER BY order_time) 或 ARRAY_AGG。",
            "再把数组展开成多行：DuckDB 用 UNNEST(arr)。Hive 用 LATERAL VIEW explode(arr) t AS item。",
            "数组下标可以用 GENERATE_SUBSCRIPTS(arr, 1)，Hive 里用 posexplode() 同时拿到下标。",
        ],
        notes="""**考点**：explode / UNNEST —— 数组、Map 打散成多行，Hive 面试的高频考点。

**Hive 标准写法**（必须背）：
```sql
SELECT user_id, item
FROM user_orders
LATERAL VIEW explode(amount_list) t AS item;
-- 带下标
LATERAL VIEW posexplode(amount_list) t AS idx, item;
```

**DuckDB / Spark SQL 写法**：
```sql
SELECT user_id, UNNEST(amts) AS item FROM t;          -- DuckDB
SELECT user_id, explode(amts) AS item FROM t;         -- Spark SQL
```

**典型应用**：
1. 用户标签数组 → 打散成「用户-标签」明细表（一对多展开）
2. JSON 数组字段解析后展开
3. 订单商品明细：一个订单含多个商品，用 explode 展开成商品粒度

**性能提示**：explode 会让数据量膨胀（一行变 N 行），是 Spark / Flink 里数据膨胀和长尾任务的常见原因；大数据量下要注意倾斜（见「数据倾斜」相关题目）。""",
    ),
    Exercise(
        id="piv_pivot_syntax",
        category=CAT_E,
        difficulty=2,
        title="行转列：用 PIVOT 语法写（不用手写 CASE WHEN）",
        knowledge=["pivot", "pivot clause", "聚合透视"],
        tables=["dwd_order", "dim_user", "dim_product"],
        params=lambda r: {"cats": sorted(r.sample(_CATS_PIVOT, 3))},
        prompt="""用 **PIVOT 透视语法**（不要用 CASE WHEN 手写），把已支付订单的销售额按「城市 × 品类」做成宽表，
只保留品类：{cats_text}。

输出列：city，以及每个品类一列（值为销售额）
排序：city 升序。""",
        solution="""WITH t AS (
  SELECT u.city, p.category, o.amount
  FROM dwd_order o
  JOIN dim_user u ON o.user_id = u.user_id
  JOIN dim_product p ON o.product_id = p.product_id
  WHERE o.order_status = '已支付'
)
SELECT * FROM t
PIVOT (SUM(amount) FOR category IN ({sql_in_cats}))
ORDER BY city""",
        hints=[
            "PIVOT 语法的结构：FROM 子查询 PIVOT (聚合函数(度量) FOR 维度列 IN (值列表))。",
            "IN 列表里的值会直接变成输出列名，可以加双引号写成 IN (\"手机数码\", \"服饰鞋包\")。",
            "PIVOT 前先用 CTE 把需要的列（城市、品类、金额）选出来，PIVOT 只能引用子查询里的列。",
        ],
        notes="""**考点**：PIVOT / UNPIVOT 语法，Spark SQL 3.4+、DuckDB、Presto 都支持；Hive 不支持（Hive 只能用 CASE WHEN）。

**语法对照**：
```sql
-- DuckDB / Spark SQL 3.4+
SELECT * FROM t PIVOT (SUM(amount) FOR category IN ('A', 'B'));
-- 老式 SQL Server / Oracle
SELECT * FROM t PIVOT (SUM(amount) FOR category IN ([A], [B])) p;
```

**什么时候用 PIVOT 而不用 CASE WHEN**：
- 列值集合固定且不多 → PIVOT 更简洁
- 列值需要动态生成（每天品类都变）→ Spark SQL 可以 `PIVOT (SUM(x) FOR col IN (SELECT DISTINCT col FROM ...))`，或干脆在 BI 层处理

**面试怎么答**：「我一般用 PIVOT 语法（Spark 3.4+/DuckDB），但在 Hive 环境里只能用 CASE WHEN 的条件聚合手写，而且列数写死，新增品类要改 SQL。」—— 这句话能同时体现你懂多引擎和懂工程约束。

**UNPIVOT 反向操作**：宽表 → 长表，语法是 `FROM wide UNPIVOT (value FOR name IN (col1, col2, ...))`，Hive 里用 explode(map(...)) 或 union all 手写。""",
    ),
    Exercise(
        id="unpivot_wide_to_long",
        category=CAT_E,
        difficulty=3,
        title="列转行：宽表转长表（UNPIVOT）",
        knowledge=["unpivot", "宽表转长表", "union all"],
        tables=["dwd_order", "dim_user", "dim_product"],
        params=lambda r: {"cats": sorted(r.sample(_CATS_PIVOT, 3))},
        prompt="""先用条件聚合把「城市 × 品类（仅 {cats_text}）」做成宽表，再用 **UNPIVOT** 把它转回长表，
只要求保留销售额 > 0 的组合。

输出列：city, category（品类名）、sales（2 位小数）
排序：city 升序、sales 降序。""",
        solution="""WITH wide AS (
  SELECT u.city,
    {sql_cols_cats}
  FROM dwd_order o
  JOIN dim_user u ON o.user_id = u.user_id
  JOIN dim_product p ON o.product_id = p.product_id
  WHERE o.order_status = '已支付' AND p.category IN ({sql_in_cats})
  GROUP BY 1
),
long AS (
  SELECT city, category, sales
  FROM wide
  UNPIVOT (sales FOR category IN ({sql_quoted_cats}))
)
SELECT city, category, ROUND(sales, 2) AS sales
FROM long
WHERE sales > 0
ORDER BY city, sales DESC""",
        hints=[
            "先用 CASE WHEN 条件聚合造出宽表（CTE 里），列名就是品类名。",
            "UNPIVOT 语法：FROM 宽表 UNPIVOT (值列名 FOR 名称列名 IN (列1, 列2, ...))。",
            "宽表的列名是中文，IN 列表里要用双引号引用标识符：IN (\"手机数码\", \"服饰鞋包\")。",
        ],
        notes="""**考点**：宽表转长表，报表回流数仓的常见场景。

**为什么需要**：上游给的是宽表（每个月一列），但入仓建模需要长表（一行一个指标），否则新增月份就要改表结构。

**三种实现**：
1. `UNPIVOT` 语法（DuckDB / Spark / Presto / SQL Server）
2. `UNION ALL` 手写（Hive 通用，但 N 列要写 N 段 SQL，容易出错）
3. `explode(map('品类A', colA, '品类B', colB))`（Hive 技巧写法，一行搞定）

**Hive 的 map + explode 写法**：
```sql
SELECT city, category, sales
FROM t
LATERAL VIEW explode(map('手机数码', c1, '服饰鞋包', c2)) tmp AS category, sales
```

**注意**：UNPIVOT 会保留 NULL，如果宽表里某个组合是 NULL 而你想要 0，外围要 COALESCE。""",
    ),
]
