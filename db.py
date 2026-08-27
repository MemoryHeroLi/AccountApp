"""SQLite 数据库：建表、默认类别、种子规则。"""
import os
import sqlite3

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DB_PATH = os.path.join(DB_DIR, 'account.db')

DEFAULT_BOOKKEEPER = '旺仔爹地'

DEFAULT_CATEGORIES = [
    '餐饮美食', '交通出行', '日用百货', '充值缴费', '医疗健康', '文化休闲',
    '服饰装扮', '数码电器', '家居家装', '生活服务', '人情往来', '其他',
]

# (关键词, 类别)
SEED_RULES = [
    ('12306', '交通出行'),
    ('滴滴', '交通出行'),
    ('ETC', '交通出行'),
    ('中国移动', '充值缴费'),
    ('中国联通', '充值缴费'),
    ('中国电信', '充值缴费'),
    ('水费', '充值缴费'),
    ('电费', '充值缴费'),
    ('燃气', '充值缴费'),
    ('美团', '餐饮美食'),
    ('饿了么', '餐饮美食'),
    ('肯德基', '餐饮美食'),
    ('麦当劳', '餐饮美食'),
    ('星巴克', '餐饮美食'),
    ('京东', '日用百货'),
    ('拼多多', '日用百货'),
    ('红包', '人情往来'),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword     TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    enabled     INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS transactions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no         TEXT UNIQUE,             -- 交易单号，用于去重；手动记账为 NULL
    source           TEXT NOT NULL,           -- wechat / alipay / manual
    tx_time          TEXT NOT NULL,           -- 'YYYY-MM-DD[ HH:MM:SS]'
    counterparty     TEXT DEFAULT '',
    description      TEXT DEFAULT '',
    amount           REAL NOT NULL,           -- 有效金额（退款冲减后）
    refund_amount    REAL NOT NULL DEFAULT 0,
    pay_method       TEXT DEFAULT '',
    bookkeeper       TEXT DEFAULT '',         -- 记账人
    category_id      INTEGER REFERENCES categories(id),  -- NULL = 待分类
    manual           INTEGER NOT NULL DEFAULT 0,         -- 1 = 用户手动指定过分类，重新归类时不覆盖
    alipay_category  TEXT DEFAULT ''                     -- 支付宝账单自带分类，留作重新归类
);

CREATE INDEX IF NOT EXISTS idx_tx_time ON transactions(tx_time);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions(category_id);
"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(DB_DIR, exist_ok=True)
    conn = get_db()
    conn.executescript(SCHEMA)
    # 迁移：旧库补充 bookkeeper 列，并把存量交易记账人填为默认值
    cols = [r['name'] for r in conn.execute('PRAGMA table_info(transactions)')]
    if 'bookkeeper' not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN bookkeeper TEXT DEFAULT ''")
        conn.execute('UPDATE transactions SET bookkeeper=?', (DEFAULT_BOOKKEEPER,))
    for name in DEFAULT_CATEGORIES:
        conn.execute('INSERT OR IGNORE INTO categories(name) VALUES (?)', (name,))
    # 类别齐了才补种子规则（规则依赖类别 id）
    for keyword, cat in SEED_RULES:
        row = conn.execute('SELECT id FROM categories WHERE name=?', (cat,)).fetchone()
        if row:
            conn.execute(
                'INSERT INTO rules(keyword, category_id) '
                'SELECT ?, ? WHERE NOT EXISTS (SELECT 1 FROM rules WHERE keyword=?)',
                (keyword, row['id'], keyword))
    # 初始化排序号
    ids = [r['id'] for r in conn.execute('SELECT id FROM rules ORDER BY id')]
    for i, rid in enumerate(ids):
        conn.execute('UPDATE rules SET sort_order=? WHERE id=?', (i, rid))
    conn.commit()
    conn.close()
