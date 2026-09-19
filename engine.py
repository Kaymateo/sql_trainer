"""SQL 训练平台 · 数据生成引擎 + 判题引擎 + 查询安全护栏

设计要点
--------
1. 每个「题目实例」= 一个随机种子。数据由种子确定性生成（同一 seed → 同一份数据）。
2. 出题时用参考解（solution）在实例上跑一遍，得到标准答案 → 判题靠「对拍」，
   永远与数据一致，不会出现答案写死和数据对不上的问题。
3. 判题采用集合（多重集）比较：结果行顺序、列名不计；列数与行数必须一致。
4. 用户 SQL 走安全护栏：只允许单条查询语句，禁用 DDL/DML/ATTACH/COPY 等，
   并在连接级别关闭外部文件访问（enable_external_access=false）。
"""
from __future__ import annotations

import datetime as dt
import random
import re
import threading
from collections import Counter
from decimal import Decimal
from typing import Any

import duckdb
import pyarrow as pa

# DuckDB DDL 类型 → pyarrow 类型（用于批量灌数据）
_ARROW_TYPES = {
    "INTEGER": pa.int32(),
    "BIGINT": pa.int64(),
    "VARCHAR": pa.string(),
    "DATE": pa.date32(),
    "TIMESTAMP": pa.timestamp("us"),
    "DOUBLE": pa.float64(),
}

# ───────────────────────────── 基础常量 ─────────────────────────────
DATA_START = dt.date(2025, 1, 1)
DATA_END = dt.date(2026, 6, 30)
NDAYS = (DATA_END - DATA_START).days + 1

PREVIEW_ROWS = 100
GRADE_ROW_CAP = 300_000
QUERY_TIMEOUT = 20          # 秒，超过即中断

CITIES = ["成都", "绵阳", "德阳", "南充", "重庆", "西安", "武汉", "长沙"]
CITY_PROVINCE = {
    "成都": "四川", "绵阳": "四川", "德阳": "四川", "南充": "四川",
    "重庆": "重庆", "西安": "陕西", "武汉": "湖北", "长沙": "湖南",
}
CHANNELS = ["抖音", "微信", "搜索", "地推", "老带新"]
CATEGORIES = ["手机数码", "服饰鞋包", "食品生鲜", "家居日用", "美妆个护"]
BRANDS = {
    "手机数码": ["华为", "小米", "OPPO", "vivo"],
    "服饰鞋包": ["李宁", "安踏", "优衣库", "太平鸟"],
    "食品生鲜": ["三只松鼠", "良品铺子", "百草味", "伊利"],
    "家居日用": ["得力", "苏泊尔", "富光", "京东京造"],
    "美妆个护": ["珀莱雅", "薇诺娜", "自然堂", "花西子"],
}
MEMBER_LEVELS = ["普通", "银卡", "金卡", "钻卡"]
DEVICES = ["iOS", "Android", "PC", "小程序"]
PRODUCT_WORDS = {
    "手机数码": ["手机", "耳机", "充电器", "平板", "音箱"],
    "服饰鞋包": ["运动鞋", "卫衣", "双肩包", "羽绒服", "袜子"],
    "食品生鲜": ["坚果礼盒", "牛肉干", "每日坚果", "牛奶", "水果"],
    "家居日用": ["保温杯", "炒锅", "收纳箱", "台灯", "毛巾"],
    "美妆个护": ["精华", "面膜", "防晒", "洗面奶", "口红"],
}
PAGES = ["首页", "搜索页", "商品详情页", "购物车页", "订单确认页", "支付页", "我的"]
EVENT_TYPES = ["view", "add_cart", "submit_order", "pay", "refund"]
SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏"
GIVEN = ["伟", "芳", "娜", "敏", "静", "磊", "洋", "勇", "艳", "杰", "涛", "明",
         "超", "秀英", "霞", "平", "刚", "桂英", "文", "辉", "雪", "鑫", "宇", "浩"]

# 数据规模（scale=1 基准）
BASE_USERS = 400
BASE_PRODUCTS = 80
BASE_ORDERS = 9000
BASE_LOGINS = 5200
BASE_EVENTS = 9000


# ───────────────────────────── 数据生成 ─────────────────────────────
def _rand_name(rnd: random.Random) -> str:
    return rnd.choice(SURNAMES) + rnd.choice(GIVEN)


class Dataset:
    """按种子确定性生成的全量业务数据。"""

    def __init__(self, seed: int, scale: float = 1.0):
        self.seed = seed
        self.scale = scale
        self.rnd = random.Random(seed * 1_000_003 + 17)
        rnd = self.rnd
        n_users = max(60, int(BASE_USERS * scale))
        n_products = max(20, int(BASE_PRODUCTS * scale))
        n_orders = max(300, int(BASE_ORDERS * scale))
        n_logins = max(400, int(BASE_LOGINS * scale))
        n_events = max(600, int(BASE_EVENTS * scale))

        # ── 维度：用户 ──────────────────────────────────────────
        self.users: list[tuple] = []
        self.user_reg: dict[int, dt.date] = {}
        self.sticky_users: set[int] = set()
        self.active_pool: list[int] = []
        for uid in range(1, n_users + 1):
            reg_offset = rnd.randint(0, NDAYS - 30)
            reg = DATA_START + dt.timedelta(days=reg_offset)
            self.user_reg[uid] = reg
            city = rnd.choice(CITIES)
            self.users.append((
                uid, _rand_name(rnd), city, rnd.choice(CHANNELS), reg,
                rnd.choices(MEMBER_LEVELS, weights=[55, 25, 15, 5])[0],
            ))
        # 高活跃用户（保证连续登录类题目有解）
        n_sticky = max(5, n_users // 20)
        self.sticky_users = set(rnd.sample(range(1, n_users + 1), n_sticky))
        self.active_pool = list(range(1, n_users + 1))

        # ── 维度：商品 ──────────────────────────────────────────
        self.products: list[tuple] = []
        for pid in range(1, n_products + 1):
            cat = rnd.choice(CATEGORIES)
            brand = rnd.choice(BRANDS[cat])
            word = rnd.choice(PRODUCT_WORDS[cat])
            price = round(rnd.uniform(29, 899) if cat != "手机数码" else rnd.uniform(199, 6999), 2)
            self.products.append((pid, f"{brand}{word}{rnd.randint(1, 99)}", cat, brand, Decimal(str(price))))

        # ── 事实：订单（18 个月，含增长趋势 / 周末效应 / 低谷期）──
        self.cold_start = DATA_START + dt.timedelta(days=rnd.randint(180, 330))
        cold_len = rnd.randint(7, 12)
        self.cold_days = {self.cold_start + dt.timedelta(days=i) for i in range(cold_len)}
        weights = []
        for i in range(NDAYS):
            day = DATA_START + dt.timedelta(days=i)
            w = 1.0 + 1.2 * (i / NDAYS)                       # 增长趋势
            if day.weekday() >= 5:
                w *= 1.35                                     # 周末高峰
            if day in self.cold_days:
                w *= 0.04                                     # 低谷期
            weights.append(w)
        day_choices = rnd.choices(range(NDAYS), weights=weights, k=n_orders)
        day_choices.sort()                                    # 订单按时间有序，贴近真实

        self.orders: list[tuple] = []
        self.payments: list[tuple] = []
        self.refunds: list[tuple] = []
        pay_id = ref_id = 0
        oid = 100_000
        # 用户活跃度呈长尾分布（少数用户贡献大部分订单），一次性抽好，避免逐条 shuffle
        # 约 30% 注册用户从未下单 —— 用于 LEFT JOIN / 留存 / 零单分析类题目
        n_active = max(10, int(n_users * 0.7))
        active_set = set(rnd.sample(range(1, n_users + 1), n_active))
        uid_weights = [rnd.paretovariate(1.6) if uid in active_set else 0.0
                       for uid in range(1, n_users + 1)]
        order_uids = rnd.choices(range(1, n_users + 1), weights=uid_weights, k=n_orders)
        for di, uid in zip(day_choices, order_uids):
            oid += 1
            day = DATA_START + dt.timedelta(days=di)
            pid, _, cat, _, price = self.products[rnd.randrange(len(self.products))]
            qty = rnd.choices([1, 2, 3, 4], weights=[70, 18, 8, 4])[0]
            amount = (price * qty).quantize(Decimal("0.01"))
            status = rnd.choices(
                ["已支付", "待支付", "已退款", "已取消"], weights=[78, 10, 7, 5]
            )[0]
            hour = rnd.choices(
                list(range(24)),
                weights=[1, 1, 1, 1, 1, 2, 3, 5, 8, 10, 11, 10, 9, 8, 9, 10, 11, 12, 13, 12, 10, 7, 4, 2],
            )[0]
            order_time = dt.datetime.combine(day, dt.time(hour, rnd.randint(0, 59), rnd.randint(0, 59)))
            pay_time = None
            if status in ("已支付", "已退款"):
                pay_time = order_time + dt.timedelta(minutes=rnd.randint(1, 180))
                pay_id += 1
                self.payments.append((
                    pay_id, oid, rnd.choice(["支付宝", "微信支付", "银行卡", "余额"]),
                    amount, pay_time, "成功", day,
                ))
            if status == "已退款":
                ref_id += 1
                refund_time = (pay_time or order_time) + dt.timedelta(days=rnd.randint(1, 20))
                self.refunds.append((
                    ref_id, oid, (amount * Decimal("1.0")).quantize(Decimal("0.01")),
                    refund_time, rnd.choice(["不想要了", "质量问题", "发错货", "效果不符"]),
                    refund_time.date(),
                ))
            self.orders.append((
                oid, uid, pid, qty, amount, status, order_time, pay_time,
                CITY_PROVINCE[self.users[uid - 1][2]], day,
            ))

        # ── 事实：登录日志 ─────────────────────────────────────
        self.logins: list[tuple] = []
        for uid in range(1, n_users + 1):
            reg = self.user_reg[uid]
            span_start = max(reg, DATA_START)
            span_days = (DATA_END - span_start).days
            if span_days <= 0:
                continue
            if uid in self.sticky_users:
                # 连续活跃型：一段 8–20 天的连续登录
                streak = rnd.randint(8, 20)
                begin = rnd.randint(0, max(0, span_days - streak))
                for i in range(streak):
                    d = span_start + dt.timedelta(days=begin + i)
                    self.logins.append((uid, d, dt.datetime.combine(d, dt.time(rnd.randint(6, 23), rnd.randint(0, 59))),
                                        rnd.choice(DEVICES)))
            n_log = rnd.choices([0, 1, 2, 4, 8, 15], weights=[8, 12, 25, 30, 18, 7])[0]
            for _ in range(n_log):
                d = span_start + dt.timedelta(days=rnd.randint(0, span_days))
                self.logins.append((uid, d, dt.datetime.combine(d, dt.time(rnd.randint(6, 23), rnd.randint(0, 59))),
                                    rnd.choice(DEVICES)))
        self.logins.sort(key=lambda r: r[2])
        if len(self.logins) > n_logins * 3:
            self.logins = self.logins[: n_logins * 3]

        # ── 事实：页面事件（含会话间隔，用于会话切割）──────────
        # 约 15% 的用户是「只看不买」型：不会出现 submit_order / pay 事件
        # （保证「加购未下单」这类反连接题目永远有解，也更贴近真实转化漏斗）
        self.non_buyers = set(rnd.sample(range(1, n_users + 1), max(5, n_users // 7)))
        buy_types = (["view", "add_cart", "submit_order", "pay", "refund"], [70, 15, 7, 6, 2])
        browse_types = (["view", "add_cart"], [82, 18])
        self.events: list[tuple] = []
        eid = 0
        for _ in range(n_events):
            uid = rnd.randrange(1, n_users + 1)
            start_i = rnd.randrange(NDAYS)
            base = dt.datetime.combine(
                DATA_START + dt.timedelta(days=start_i),
                dt.time(rnd.choices(range(24), weights=[1, 1, 1, 1, 1, 2, 3, 5, 8, 10, 11, 10,
                                                        9, 8, 9, 10, 11, 12, 13, 12, 10, 7, 4, 2])[0],
                                  rnd.randint(0, 59)),
            )
            burst = rnd.randint(1, 8)
            t = base
            sess = f"s{uid}_{base.strftime('%Y%m%d%H%M')}_{rnd.randint(100, 999)}"
            for _ in range(burst):
                eid += 1
                gap = rnd.choices([rnd.randint(1, 25), rnd.randint(30, 120)], weights=[8, 2])[0]
                t = t + dt.timedelta(minutes=gap)
                if t.date() > DATA_END:
                    break
                t_list, t_w = browse_types if uid in self.non_buyers else buy_types
                etype = rnd.choices(t_list, weights=t_w)[0]
                self.events.append((
                    eid, uid, sess, etype, rnd.choice(PAGES), t,
                    rnd.randint(1, 900), t.date(),
                ))
        self.events.sort(key=lambda r: r[5])

        # ── 维度：日期 ─────────────────────────────────────────
        self.dim_date: list[tuple] = []
        for i in range(NDAYS):
            d = DATA_START + dt.timedelta(days=i)
            iso = d.isocalendar()
            self.dim_date.append((d, d.strftime("%Y%m%d"), iso[1], d.month, (d.month - 1) // 3 + 1,
                                  1 if d.weekday() >= 5 else 0, d.strftime("%Y-%m")))

        # ── 拉链表：用户属性变更历史（SCD2）────────────────────
        self.user_zip: list[tuple] = []
        for uid, name, city, channel, reg, level in self.users:
            n_ver = rnd.choices([1, 2, 3], weights=[55, 33, 12])[0]
            cuts = sorted(rnd.sample(range(1, max(2, (DATA_END - reg).days)), k=min(n_ver - 1, 2))) \
                if (DATA_END - reg).days > 3 else []
            start = reg
            cur_city, cur_level = city, level
            for c in cuts:
                end = reg + dt.timedelta(days=c)
                self.user_zip.append((uid, name, cur_city, cur_level, start, end - dt.timedelta(days=1)))
                start = end
                cur_city = rnd.choice(CITIES)
                cur_level = rnd.choice(MEMBER_LEVELS)
            self.user_zip.append((uid, name, cur_city, cur_level, start, dt.date(9999, 12, 31)))

        self._inject_dirty()

    def _inject_dirty(self) -> None:
        """注入少量脏数据（重复主键 / 孤儿用户 / 空用户 / 非法金额）。

        真实数仓一定有脏数据，数据质量校验类题目必须能查出问题，
        否则「校验规则」就成了纸面功夫。
        """
        rnd = self.rnd
        dup = next((r for r in self.orders if r[5] == "已支付"), self.orders[0])
        self.orders.append(tuple(dup))                       # 1) 重复主键
        for suffix, patch in ((900, {"uid": 999_999}),       # 2) 孤儿用户
                              (910, {"uid": None}),          # 3) 用户为空
                              (920, {"amount": Decimal("0.00")}),
                              (920, {"amount": Decimal("-10.00")})):
            for _ in range(2 if suffix == 920 else 3 if suffix == 900 else 2):
                r = list(self.orders[rnd.randrange(len(self.orders))])
                r[0] = suffix * 1000 + rnd.randint(1, 999)
                if "uid" in patch:
                    r[1] = patch["uid"]
                if "amount" in patch:
                    r[4] = patch["amount"]
                self.orders.append(tuple(r))
        if self.events:                                      # 4) 埋点用户为空
            for _ in range(3):
                e = list(self.events[rnd.randrange(len(self.events))])
                e[0] = 930_000 + rnd.randint(1, 999)
                e[1] = None
                self.events.append(tuple(e))
        self.orders.sort(key=lambda r: r[6])
        self.events.sort(key=lambda r: r[5])

    # ── 建表语句 ──────────────────────────────────────────────
    DDL: dict[str, str] = {
        "dim_user": """CREATE TABLE dim_user(
            user_id INTEGER, user_name VARCHAR, city VARCHAR, channel VARCHAR,
            reg_date DATE, member_level VARCHAR)""",
        "dim_product": """CREATE TABLE dim_product(
            product_id INTEGER, product_name VARCHAR, category VARCHAR,
            brand VARCHAR, price DECIMAL(12,2))""",
        "dwd_order": """CREATE TABLE dwd_order(
            order_id BIGINT, user_id INTEGER, product_id INTEGER, quantity INTEGER,
            amount DECIMAL(12,2), order_status VARCHAR, order_time TIMESTAMP,
            pay_time TIMESTAMP, province VARCHAR, dt DATE)""",
        "dwd_payment": """CREATE TABLE dwd_payment(
            payment_id BIGINT, order_id BIGINT, pay_channel VARCHAR, pay_amount DECIMAL(12,2),
            pay_time TIMESTAMP, pay_status VARCHAR, dt DATE)""",
        "dwd_refund": """CREATE TABLE dwd_refund(
            refund_id BIGINT, order_id BIGINT, refund_amount DECIMAL(12,2),
            refund_time TIMESTAMP, reason VARCHAR, dt DATE)""",
        "dwd_login_log": """CREATE TABLE dwd_login_log(
            user_id INTEGER, login_date DATE, login_time TIMESTAMP, device VARCHAR)""",
        "dwd_page_event": """CREATE TABLE dwd_page_event(
            event_id BIGINT, user_id INTEGER, session_id VARCHAR, event_type VARCHAR,
            page_name VARCHAR, event_time TIMESTAMP, stay_seconds INTEGER, dt DATE)""",
        "dim_date": """CREATE TABLE dim_date(
            dt DATE, ymd VARCHAR, week_of_year INTEGER, month INTEGER,
            quarter INTEGER, is_weekend INTEGER, ym VARCHAR)""",
        "dim_user_zip": """CREATE TABLE dim_user_zip(
            user_id INTEGER, user_name VARCHAR, city VARCHAR, member_level VARCHAR,
            start_date DATE, end_date DATE)""",
    }

    def rows_for(self, table: str) -> list[tuple]:
        return {
            "dim_user": self.users,
            "dim_product": self.products,
            "dwd_order": self.orders,
            "dwd_payment": self.payments,
            "dwd_refund": self.refunds,
            "dwd_login_log": self.logins,
            "dwd_page_event": self.events,
            "dim_date": self.dim_date,
            "dim_user_zip": self.user_zip,
        }[table]


# ───────────────────────────── 连接初始化 ─────────────────────────────
# Hive / MySQL 风格函数别名（降低方言切换成本；失败则忽略）
HIVE_MACROS = [
    "CREATE OR REPLACE MACRO nvl(a, b) AS coalesce(a, b)",
    "CREATE OR REPLACE MACRO datediff(d1, d2) AS date_diff('day', d2, d1)",
    "CREATE OR REPLACE MACRO date_sub(d, n) AS (d - (n) * INTERVAL 1 DAY)",
    "CREATE OR REPLACE MACRO date_add(d, n) AS (d + (n) * INTERVAL 1 DAY)",
    "CREATE OR REPLACE MACRO from_unixtime(s) AS to_timestamp(s)",
    "CREATE OR REPLACE MACRO unix_timestamp(t) AS epoch(t)",
    "CREATE OR REPLACE MACRO collect_list(x) AS list(x)",
    "CREATE OR REPLACE MACRO get_json_object(j, p) AS json_extract_string(j, p)",
    "CREATE OR REPLACE MACRO size(x) AS len(x)",
    "CREATE OR REPLACE MACRO ifnull(a, b) AS coalesce(a, b)",
]


def new_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("SET enable_external_access = false")      # 禁读文件 / 网络
    con.execute("SET autoinstall_known_extensions = false")
    con.execute("SET autoload_known_extensions = false")
    con.execute("SET preserve_insertion_order = false")
    for m in HIVE_MACROS:
        try:
            con.execute(m)
        except Exception:
            pass
    return con


def _arrow_schema(con: duckdb.DuckDBPyConnection, table: str) -> pa.Schema:
    """按 DuckDB 里已建好的表结构构造 pyarrow schema，保证 NULL 列也能正确灌入。"""
    fields = []
    for name, typ, *_ in con.sql(f"DESCRIBE {table}").fetchall():
        t = str(typ).upper()
        if t.startswith("DECIMAL"):
            p, s = t[t.index("(") + 1:t.index(")")].split(",")
            at = pa.decimal128(int(p), int(s))
        else:
            at = _ARROW_TYPES.get(t, pa.string())
        fields.append(pa.field(name, at))
    return pa.schema(fields)


def insert_rows(con: duckdb.DuckDBPyConnection, table: str, rows: list[tuple]) -> None:
    """通过 pyarrow 批量灌数据：9000 行约 0.1s（executemany 需要 19s）。"""
    if not rows:
        return
    schema = _arrow_schema(con, table)
    cols = {f.name: [r[i] for r in rows] for i, f in enumerate(schema)}
    con.register("_batch", pa.Table.from_pydict(cols, schema=schema))
    try:
        con.execute(f"INSERT INTO {table} SELECT * FROM _batch")
    finally:
        con.unregister("_batch")


def build_instance(seed: int, scale: float, tables: list[str]) -> tuple[duckdb.DuckDBPyConnection, Dataset]:
    ds = Dataset(seed, scale)
    con = new_connection()
    for t in tables:
        con.execute(Dataset.DDL[t])
        insert_rows(con, t, ds.rows_for(t))
    return con, ds


def table_schema(con: duckdb.DuckDBPyConnection, table: str) -> list[dict]:
    desc = con.sql(f"DESCRIBE {table}").fetchall()
    return [{"column": r[0], "type": r[1]} for r in desc]


def table_sample(con: duckdb.DuckDBPyConnection, table: str, n: int = 5) -> dict:
    cur = con.sql(f"SELECT * FROM {table} LIMIT {n}")
    cols = [d[0] for d in cur.description]
    rows = [[_cell(v) for v in r] for r in cur.fetchall()]
    total = con.sql(f"SELECT count(*) FROM {table}").fetchone()[0]
    return {"columns": cols, "rows": rows, "total_rows": total}


# ───────────────────────────── 查询护栏 ─────────────────────────────
class QueryRejected(Exception):
    pass


BANNED = (
    "attach", "detach", "install", "load", "copy", "export", "import", "pragma",
    "create", "drop", "alter", "truncate", "delete", "update", "insert", "merge",
    "call", "vacuum", "checkpoint", "begin", "commit", "rollback", "grant", "revoke",
    "set", "use", "reset", "force", "refresh",
    # 文件 / 外部数据源相关函数（函数名后跟括号，必须用词边界匹配才抓得到）
    "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto",
    "read_ndjson", "read_xlsx", "read_text", "read_blob", "parquet_scan", "csv_scan",
    "json_scan", "delta_scan", "iceberg_scan", "sqlite_scan", "postgres_scan",
    "mysql_scan", "glob", "shell", "getenv", "install_extension", "load_extension",
)
_BANNED_RE = re.compile(r"(?<![\w])(?:" + "|".join(BANNED) + r")(?![\w])", re.I)

# DuckDB 的 replacement scan：FROM '/etc/passwd' 或 FROM 'data.csv' 可直接读文件。
# 执行层已由 enable_external_access=false 挡住，这里再加一层文本拦截 + 友好提示。
# 只匹配 FROM / JOIN 后面紧跟的字符串字面量，避免误伤 'yyyy/MM/dd' 这类格式串。
FILE_SOURCE = re.compile(
    r"""\b(?:from|join)\s+'(?:[^']*[/\\][^']*|[^']*\.(?:csv|parquet|json|jsonl|tsv|txt|gz|db|orc|xlsx))'""",
    re.I,
)


def guard(sql: str) -> str:
    s = (sql or "").strip()
    if not s:
        raise QueryRejected("SQL 为空")
    body = s.rstrip().rstrip(";").strip()
    if ";" in body:
        raise QueryRejected("只允许提交单条查询语句（不要把多条 SQL 用分号拼在一起）")
    low = body.lower()
    if not (low.startswith("select") or low.startswith("with")
            or low.startswith("from") or low.startswith("values")
            or low.startswith("pivot") or low.startswith("unpivot")):
        raise QueryRejected("只允许查询语句（SELECT / WITH / FROM ... / PIVOT）")
    for kw in BANNED:
        if low.startswith(kw):
            raise QueryRejected(f"检测到不允许的关键字 `{kw.upper()}`：平台只读，禁止改表/读文件/改配置")
    hit = _BANNED_RE.search(body)
    if hit:
        raise QueryRejected(f"检测到不允许的关键字 `{hit.group(0).upper()}`：平台只读，禁止改表/读文件/改配置")
    if FILE_SOURCE.search(body):
        raise QueryRejected("平台禁止把文件路径当数据源（FROM / JOIN '路径'），只能查询数据字典里的表")
    return body


def run_query(con: duckdb.DuckDBPyConnection, sql: str, timeout: int = QUERY_TIMEOUT,
              max_rows: int = GRADE_ROW_CAP) -> dict:
    """在独立线程中执行，超时调用 con.interrupt() 中断。"""
    box: dict[str, Any] = {}

    def work():
        try:
            cur = con.cursor()
            cur.execute(sql)
            cols = [d[0] for d in (cur.description or [])]
            rows = cur.fetchmany(max_rows + 1) if cols else []
            box["cols"], box["rows"] = cols, rows
        except Exception as e:                       # noqa: BLE001
            box["err"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        try:
            con.interrupt()
        except Exception:
            pass
        t.join(3)
        raise QueryRejected(f"查询超过 {timeout} 秒仍未返回，已中断（检查是否产生笛卡尔积或全表排序）")
    if "err" in box:
        raise QueryRejected(_friendly_error(box["err"]))
    rows = box["rows"]
    if len(rows) > max_rows:
        raise QueryRejected(f"结果集超过 {max_rows:,} 行，请检查是否缺少聚合或过滤条件")
    return {"columns": box["cols"], "rows": rows}


def _friendly_error(msg: str) -> str:
    low = msg.lower()
    if "no such table" in low or "does not exist" in low and "table" in low:
        return f"执行失败：{msg}\n提示：核对表名是否与本题数据字典一致。"
    if "binder error" in low and "column" in low:
        return f"执行失败：{msg}\n提示：核对列名拼写，可用左侧数据字典确认字段。"
    if "syntax error" in low or "parser error" in low:
        return f"执行失败：{msg}\n提示：注意引擎为 DuckDB（标准 SQL + 分析函数），不支持 Hive 专属语法。"
    if "conversion error" in low:
        return f"执行失败：{msg}\n提示：检查字段类型是否需要 CAST。"
    return f"执行失败：{msg}"


# ───────────────────────────── 判题 ─────────────────────────────
def _cell(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat(sep=" ") if isinstance(v, dt.datetime) else v.isoformat()
    if isinstance(v, Decimal):
        return _num(float(v))
    if isinstance(v, float):
        return _num(v)
    if isinstance(v, int):
        return str(v)
    return str(v)


def _num(f: float) -> str:
    if f != f or f in (float("inf"), float("-inf")):
        return "nan"
    r = round(f, 6)
    if r == int(r):
        return str(int(r))
    return f"{r:.6f}".rstrip("0")


def _key(rows: list[tuple], sort_cells: bool = False) -> Counter:
    if sort_cells:
        return Counter(tuple(sorted(_cell(v) for v in r)) for r in rows)
    return Counter(tuple(_cell(v) for v in r) for r in rows)


def compare(user: dict, ref: dict) -> dict:
    """对拍判题。行顺序不计；列顺序不一致但内容一致时也算通过（会在反馈中说明）。"""
    if len(user["columns"]) != len(ref["columns"]):
        return {
            "ok": False, "reason": "列数不一致",
            "detail": f"你返回 {len(user['columns'])} 列（{', '.join(map(str, user['columns']))}），"
                      f"参考结果 {len(ref['columns'])} 列（{', '.join(map(str, ref['columns']))}）。",
        }
    if len(user["rows"]) != len(ref["rows"]):
        uk, rk = _key(user["rows"]), _key(ref["rows"])
        missing = list((rk - uk).elements())[:3]
        d = [f"你返回 {len(user['rows'])} 行，参考结果 {len(ref['rows'])} 行。"]
        if len(uk) < len(user["rows"]):
            d.append("结果中含重复行，确认是否漏了去重/分组维度。")
        if missing:
            d.append("参考结果中有而你没有的行，例如：" + "；".join(str(x) for x in missing))
        return {"ok": False, "reason": "行数不一致", "detail": " ".join(d)}

    if _key(user["rows"]) == _key(ref["rows"]):
        return {"ok": True, "reason": "通过", "detail": f"结果集完全一致（{len(user['rows'])} 行）。"}
    if _key(user["rows"], True) == _key(ref["rows"], True):
        return {"ok": True, "reason": "通过（列顺序不同）",
                "detail": f"内容完全正确（{len(user['rows'])} 行），只是列的顺序与参考解不同——面试中通常不影响。"}

    uk, rk = _key(user["rows"]), _key(ref["rows"])
    diff = list((rk - uk).elements())[:2]
    wrong = list((uk - rk).elements())[:2]
    return {
        "ok": False, "reason": "结果内容不一致",
        "detail": f"列数与行数都正确（{len(user['rows'])} 行），但有 {len(rk - uk)} 行取值不同。"
                  f"参考值示例：{diff}；你的值示例：{wrong}。检查聚合口径、去重粒度和过滤条件。",
    }
