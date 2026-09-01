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

# 二级分类（一级分类 -> 其下二级分类列表）
DEFAULT_SUBCATEGORIES = {
    '餐饮美食': ['外卖', '堂食', '咖啡饮品', '零食甜点'],
    '交通出行': ['公共交通', '打车·网约车', '加油·充电', '过路·停车'],
    '日用百货': ['超市购物', '网购', '生鲜果蔬'],
    '充值缴费': ['话费流量', '水电燃气', '会员订阅'],
    '医疗健康': ['药品', '门诊就医'],
    '文化休闲': ['电影演出', '运动健身', '图书文具'],
    '服饰装扮': ['服装', '鞋包配饰'],
    '数码电器': ['数码配件', '家用电器'],
    '家居家装': ['家居日用'],
    '生活服务': ['家政维修', '美容美发'],
    '人情往来': ['红包礼金', '请客送礼'],
}

# (关键词, 一级分类, 二级分类)；二级可为空表示规则指向一级
SEED_RULES = [
    ('12306', '交通出行', '公共交通'),
    ('地铁', '交通出行', '公共交通'),
    ('公交', '交通出行', '公共交通'),
    ('滴滴', '交通出行', '打车·网约车'),
    ('ETC', '交通出行', '过路·停车'),
    ('中国移动', '充值缴费', '话费流量'),
    ('中国联通', '充值缴费', '话费流量'),
    ('中国电信', '充值缴费', '话费流量'),
    ('水费', '充值缴费', '水电燃气'),
    ('电费', '充值缴费', '水电燃气'),
    ('燃气', '充值缴费', '水电燃气'),
    ('美团', '餐饮美食', '外卖'),
    ('饿了么', '餐饮美食', '外卖'),
    ('肯德基', '餐饮美食', '堂食'),
    ('麦当劳', '餐饮美食', '堂食'),
    ('星巴克', '餐饮美食', '咖啡饮品'),
    ('京东', '日用百货', '网购'),
    ('拼多多', '日用百货', '网购'),
    ('红包', '人情往来', '红包礼金'),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    name      TEXT UNIQUE NOT NULL,
    parent_id INTEGER REFERENCES categories(id)   -- NULL = 一级分类，非 NULL = 该一级下的二级分类
);

CREATE TABLE IF NOT EXISTS rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword     TEXT NOT NULL,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    enabled     INTEGER NOT NULL DEFAULT 1,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS bookkeepers (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
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
    category_id      INTEGER REFERENCES categories(id),   -- 一级分类；NULL = 待分类
    subcategory_id   INTEGER REFERENCES categories(id),   -- 二级分类；NULL = 未细分
    manual           INTEGER NOT NULL DEFAULT 0,          -- 1 = 用户手动指定过分类，重新归类时不覆盖
    alipay_category  TEXT DEFAULT ''                      -- 支付宝账单自带分类，留作重新归类
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
    tcols = [r['name'] for r in conn.execute('PRAGMA table_info(transactions)')]
    if 'bookkeeper' not in tcols:
        conn.execute("ALTER TABLE transactions ADD COLUMN bookkeeper TEXT DEFAULT ''")
        conn.execute('UPDATE transactions SET bookkeeper=?', (DEFAULT_BOOKKEEPER,))
    # 迁移：旧库补充 subcategory_id 列
    if 'subcategory_id' not in tcols:
        conn.execute('ALTER TABLE transactions ADD COLUMN subcategory_id INTEGER')
    # 迁移：旧库 categories 补充 parent_id 列
    ccols = [r['name'] for r in conn.execute('PRAGMA table_info(categories)')]
    if 'parent_id' not in ccols:
        conn.execute('ALTER TABLE categories ADD COLUMN parent_id INTEGER')
    # 一级分类
    for name in DEFAULT_CATEGORIES:
        conn.execute('INSERT OR IGNORE INTO categories(name) VALUES (?)', (name,))
    # 二级分类（挂在对应一级下）
    for top, subs in DEFAULT_SUBCATEGORIES.items():
        top_row = conn.execute(
            'SELECT id FROM categories WHERE name=? AND parent_id IS NULL', (top,)).fetchone()
        if not top_row:
            continue
        for sub in subs:
            conn.execute('INSERT OR IGNORE INTO categories(name, parent_id) VALUES (?,?)',
                         (sub, top_row['id']))
    # 种子规则（可指向二级分类）：已存在的规则若仍指向旧一级默认，则重指到二级；否则不覆盖用户改动
    for keyword, top, sub in SEED_RULES:
        top_row = conn.execute(
            'SELECT id FROM categories WHERE name=? AND parent_id IS NULL', (top,)).fetchone()
        if not top_row:
            continue
        target_id = top_row['id']
        if sub:
            sub_row = conn.execute(
                'SELECT id FROM categories WHERE name=? AND parent_id=?',
                (sub, top_row['id'])).fetchone()
            if sub_row:
                target_id = sub_row['id']
        row = conn.execute('SELECT id, category_id FROM rules WHERE keyword=?',
                           (keyword,)).fetchone()
        if row:
            cur = conn.execute('SELECT name FROM categories WHERE id=?',
                               (row['category_id'],)).fetchone()
            if cur and cur['name'] == top:
                conn.execute('UPDATE rules SET category_id=? WHERE id=?',
                             (target_id, row['id']))
        else:
            conn.execute('INSERT INTO rules(keyword, category_id) VALUES (?,?)',
                         (keyword, target_id))
    # 记账人注册表（下拉数据源，预置两位记账人）
    for name in ('旺仔爹地', '王女士'):
        conn.execute('INSERT OR IGNORE INTO bookkeepers(name) VALUES (?)', (name,))
    # 初始化排序号
    ids = [r['id'] for r in conn.execute('SELECT id FROM rules ORDER BY id')]
    for i, rid in enumerate(ids):
        conn.execute('UPDATE rules SET sort_order=? WHERE id=?', (i, rid))
    conn.commit()
    conn.close()
