"""分类引擎：用户规则优先 -> 支付宝自带分类映射 -> 待分类(None)。"""


# 支付宝自带分类 -> 本应用类别（交通出行与爱车养车合并，商业服务并入生活服务）
ALIPAY_MAP = {
    '交通出行': '交通出行',
    '爱车养车': '交通出行',
    '餐饮美食': '餐饮美食',
    '日用百货': '日用百货',
    '充值缴费': '充值缴费',
    '医疗健康': '医疗健康',
    '文化休闲': '文化休闲',
    '服饰装扮': '服饰装扮',
    '数码电器': '数码电器',
    '家居家装': '家居家装',
    '生活服务': '生活服务',
    '商业服务': '生活服务',
    '其他': '其他',
}


def _category_id_by_name(conn, name):
    if not name:
        return None
    row = conn.execute('SELECT id FROM categories WHERE name=?', (name,)).fetchone()
    return row['id'] if row else None


def classify(conn, counterparty, description, alipay_category=''):
    """返回类别 id；无法判定时返回 None（待分类）。"""
    text = f'{counterparty or ""} {description or ""}'
    for rule in conn.execute(
            'SELECT keyword, category_id FROM rules WHERE enabled=1 ORDER BY sort_order, id'):
        if rule['keyword'] and rule['keyword'] in text:
            return rule['category_id']
    if alipay_category:
        mapped = ALIPAY_MAP.get(alipay_category, '其他')
        cid = _category_id_by_name(conn, mapped)
        if cid is None:  # 用户可能改过类别名，退回用原始分类名找
            cid = _category_id_by_name(conn, alipay_category)
        return cid
    return None


def reclassify(conn):
    """按最新规则重算全部历史交易的分类；手动指定过分类的(manual=1)不覆盖。

    返回本次发生变化的笔数。"""
    changed = 0
    for tx in conn.execute(
            'SELECT id, counterparty, description, category_id, alipay_category '
            'FROM transactions WHERE manual=0').fetchall():
        new_cid = classify(conn, tx['counterparty'], tx['description'],
                           tx['alipay_category'])
        if new_cid != tx['category_id']:
            conn.execute('UPDATE transactions SET category_id=? WHERE id=?',
                         (new_cid, tx['id']))
            changed += 1
    conn.commit()
    return changed
