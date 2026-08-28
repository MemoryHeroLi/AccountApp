"""Flask 应用：页面路由 + JSON API。"""
import calendar as cal
import uuid
from datetime import date, datetime

from flask import Flask, jsonify, render_template, request

import classifier
import importers
from db import DEFAULT_BOOKKEEPER, get_db

SOURCE_NAMES = {'wechat': '微信', 'alipay': '支付宝', 'manual': '手动'}


def tx_to_dict(row):
    d = dict(row)
    d['source_name'] = SOURCE_NAMES.get(d['source'], d['source'])
    return d


def create_app():
    app = Flask(__name__)
    app.json.ensure_ascii = False

    # ---------------- 页面 ----------------
    @app.get('/')
    def page_transactions():
        return render_template('transactions.html', active='transactions')

    @app.get('/calendar')
    def page_calendar():
        return render_template('calendar.html', active='calendar')

    @app.get('/stats')
    def page_stats():
        return render_template('stats.html', active='stats')

    @app.get('/rules')
    def page_rules():
        return render_template('rules.html', active='rules')

    @app.get('/categories')
    def page_categories():
        return render_template('categories.html', active='categories')

    # ---------------- 导入 ----------------
    @app.post('/api/import')
    def api_import():
        f = request.files.get('file')
        if not f or not f.filename:
            return jsonify({'error': '请选择文件'}), 400
        name = f.filename.lower()
        source = None
        try:
            if name.endswith('.xlsx'):
                txs, source = importers.parse_wechat(f), 'wechat'
            elif name.endswith('.csv'):
                txs, source = importers.parse_alipay(f), 'alipay'
            else:
                return jsonify({'error': '仅支持微信 xlsx 或支付宝 csv 账单'}), 400
        except Exception as e:
            return jsonify({'error': f'解析失败: {e}'}), 400

        conn = get_db()
        imported = 0
        for tx in txs:
            cid, sid = classifier.classify(conn, tx['counterparty'],
                                           tx['description'], tx['alipay_category'])
            cur = conn.execute(
                'INSERT OR IGNORE INTO transactions'
                '(order_no, source, tx_time, counterparty, description, amount,'
                ' refund_amount, pay_method, category_id, subcategory_id,'
                ' bookkeeper, alipay_category)'
                ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                (tx['order_no'], source, tx['tx_time'], tx['counterparty'],
                 tx['description'], tx['amount'], tx['refund_amount'],
                 tx['pay_method'], cid, sid, DEFAULT_BOOKKEEPER, tx['alipay_category']))
            imported += cur.rowcount
        conn.commit()
        conn.close()
        return jsonify({'total': len(txs), 'imported': imported,
                        'duplicate': len(txs) - imported})

    # ---------------- 元数据（下拉框用） ----------------
    @app.get('/api/meta')
    def api_meta():
        conn = get_db()
        months = [r[0] for r in conn.execute(
            "SELECT DISTINCT substr(tx_time,1,7) FROM transactions "
            "ORDER BY 1 DESC")]
        categories = [dict(r) for r in conn.execute(
            'SELECT id, name, parent_id FROM categories ORDER BY id')]
        bookkeepers = [r[0] for r in conn.execute(
            "SELECT DISTINCT bookkeeper FROM transactions "
            "WHERE bookkeeper != '' ORDER BY 1")]
        pending = conn.execute(
            'SELECT COUNT(*) FROM transactions WHERE category_id IS NULL').fetchone()[0]
        conn.close()
        return jsonify({'months': months, 'categories': categories,
                        'bookkeepers': bookkeepers, 'pending': pending})

    # ---------------- 交易明细 ----------------
    @app.get('/api/transactions')
    def api_transactions():
        month = request.args.get('month', '').strip()
        category = request.args.get('category', '').strip()
        subcategory = request.args.get('subcategory', '').strip()
        source = request.args.get('source', '').strip()
        bookkeeper = request.args.get('bookkeeper', '').strip()
        q = request.args.get('q', '').strip()

        sql = ('SELECT t.*, c.name AS category_name, s.name AS subcategory_name '
               'FROM transactions t '
               'LEFT JOIN categories c ON c.id = t.category_id '
               'LEFT JOIN categories s ON s.id = t.subcategory_id WHERE 1=1')
        params = []
        if month:
            sql += " AND t.tx_time LIKE ?"
            params.append(month + '-%')
        if category == 'none':
            sql += ' AND t.category_id IS NULL'
        elif category:
            sql += ' AND t.category_id = ?'
            params.append(int(category))
        if subcategory:
            sql += ' AND t.subcategory_id = ?'
            params.append(int(subcategory))
        if source:
            sql += ' AND t.source = ?'
            params.append(source)
        if bookkeeper:
            sql += ' AND t.bookkeeper = ?'
            params.append(bookkeeper)
        if q:
            sql += ' AND (t.counterparty LIKE ? OR t.description LIKE ?)'
            params.extend([f'%{q}%'] * 2)
        sql += ' ORDER BY t.tx_time DESC LIMIT 1000'

        conn = get_db()
        rows = [tx_to_dict(r) for r in conn.execute(sql, params)]
        total = round(sum(r['amount'] for r in rows), 2)
        conn.close()
        return jsonify({'transactions': rows, 'count': len(rows), 'total': total})

    @app.post('/api/transaction')
    def api_add_transaction():
        d = request.get_json(force=True)
        try:
            tx_date = d['date']
            datetime.strptime(tx_date, '%Y-%m-%d')
            amount = round(float(d['amount']), 2)
            if amount <= 0:
                raise ValueError
        except (KeyError, ValueError, TypeError):
            return jsonify({'error': '请填写正确的日期和金额'}), 400
        conn = get_db()
        bookkeeper = (d.get('bookkeeper') or '').strip() or DEFAULT_BOOKKEEPER
        category_id = int(d['category_id']) if d.get('category_id') else None
        subcategory_id = int(d['subcategory_id']) if d.get('subcategory_id') else None
        if subcategory_id:
            srow = conn.execute('SELECT parent_id FROM categories WHERE id=?',
                                (subcategory_id,)).fetchone()
            if not srow or srow['parent_id'] != category_id:
                conn.close()
                return jsonify({'error': '二级分类不属于所选一级分类'}), 400
        conn.execute(
            'INSERT INTO transactions(order_no, source, tx_time, counterparty,'
            ' description, amount, pay_method, category_id, subcategory_id,'
            ' bookkeeper, manual) VALUES (?,?,?,?,?,?,?,?,?,?,1)',
            ('M-' + uuid.uuid4().hex[:16], 'manual', tx_date, '',
             d.get('description', '').strip(), amount,
             d.get('pay_method', '').strip(), category_id, subcategory_id,
             bookkeeper))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    @app.get('/api/transaction/<int:tx_id>')
    def api_get_transaction(tx_id):
        conn = get_db()
        row = conn.execute(
            'SELECT t.*, c.name AS category_name, s.name AS subcategory_name '
            'FROM transactions t '
            'LEFT JOIN categories c ON c.id=t.category_id '
            'LEFT JOIN categories s ON s.id=t.subcategory_id WHERE t.id=?',
            (tx_id,)).fetchone()
        conn.close()
        if not row:
            return jsonify({'error': '交易不存在'}), 404
        return jsonify(tx_to_dict(row))

    @app.post('/api/transaction/<int:tx_id>')
    def api_edit_transaction(tx_id):
        d = request.get_json(force=True)
        conn = get_db()
        row = conn.execute('SELECT * FROM transactions WHERE id=?', (tx_id,)).fetchone()
        if not row:
            conn.close()
            return jsonify({'error': '交易不存在'}), 404

        tx_time = row['tx_time']
        if d.get('date'):
            time_part = tx_time[11:] if len(tx_time) > 10 else ''
            tx_time = d['date'] + (' ' + time_part if time_part else '')
        amount = round(float(d['amount']), 2) if d.get('amount') else row['amount']
        if amount < 0:
            conn.close()
            return jsonify({'error': '金额不能为负'}), 400
        category_id = int(d['category_id']) if d.get('category_id') else None
        subcategory_id = int(d['subcategory_id']) if d.get('subcategory_id') else None
        bookkeeper = d['bookkeeper'].strip() if 'bookkeeper' in d else row['bookkeeper']
        if subcategory_id:
            srow = conn.execute('SELECT parent_id FROM categories WHERE id=?',
                                (subcategory_id,)).fetchone()
            if not srow or srow['parent_id'] != category_id:
                conn.close()
                return jsonify({'error': '二级分类不属于所选一级分类'}), 400
        conn.execute(
            'UPDATE transactions SET tx_time=?, amount=?, description=?,'
            ' pay_method=?, category_id=?, subcategory_id=?, bookkeeper=?, manual=1 WHERE id=?',
            (tx_time, amount,
             d['description'] if 'description' in d else row['description'],
             d['pay_method'] if 'pay_method' in d else row['pay_method'],
             category_id, subcategory_id, bookkeeper, tx_id))
        # 勾选“同时添加规则”：该关键词今后自动归入所选（二级优先）类别
        if d.get('add_rule') and d.get('rule_keyword'):
            rule_cat = subcategory_id or category_id
            cat = conn.execute('SELECT id FROM categories WHERE id=?',
                               (rule_cat,)).fetchone()
            if cat:
                conn.execute(
                    'INSERT INTO rules(keyword, category_id, sort_order) '
                    'SELECT ?, ?, COALESCE(MAX(sort_order),0)+1 FROM rules',
                    (d['rule_keyword'].strip(), rule_cat))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    @app.delete('/api/transaction/<int:tx_id>')
    def api_delete_transaction(tx_id):
        conn = get_db()
        conn.execute('DELETE FROM transactions WHERE id=?', (tx_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    # ---------------- 消费日历 ----------------
    @app.get('/api/calendar')
    def api_calendar():
        month = request.args.get('month', datetime.now().strftime('%Y-%m'))
        conn = get_db()
        days = {}
        for r in conn.execute(
                "SELECT substr(tx_time,1,10) AS d, ROUND(SUM(amount),2) AS total,"
                " COUNT(*) AS cnt FROM transactions WHERE tx_time LIKE ?"
                " GROUP BY d", (month + '-%',)):
            days[r['d']] = {'total': r['total'], 'cnt': r['cnt']}
        conn.close()

        year, mon = map(int, month.split('-'))
        days_in_month = cal.monthrange(year, mon)[1]
        month_total = round(sum(v['total'] for v in days.values()), 2)
        if month == datetime.now().strftime('%Y-%m'):
            elapsed = date.today().day
        else:
            elapsed = days_in_month
        daily_avg = round(month_total / elapsed, 2) if elapsed else 0
        return jsonify({'days': days, 'month_total': month_total,
                        'daily_avg': daily_avg, 'days_in_month': days_in_month})

    @app.get('/api/day')
    def api_day():
        d = request.args.get('date', '')
        if len(d) != 10:
            return jsonify({'error': '日期格式错误'}), 400
        conn = get_db()
        rows = [tx_to_dict(r) for r in conn.execute(
            'SELECT t.*, c.name AS category_name, s.name AS subcategory_name '
            'FROM transactions t '
            'LEFT JOIN categories c ON c.id=t.category_id '
            'LEFT JOIN categories s ON s.id=t.subcategory_id '
            'WHERE t.tx_time LIKE ? ORDER BY t.tx_time', (d + '%',))]
        conn.close()
        return jsonify({'transactions': rows,
                        'total': round(sum(r['amount'] for r in rows), 2)})

    # ---------------- 统计分析 ----------------
    @app.get('/api/stats')
    def api_stats():
        start = request.args.get('start', '').strip()
        end = request.args.get('end', '').strip()
        where, params = '', []
        if start:
            where += ' AND tx_time >= ?'
            params.append(start + '-01')
        if end:
            where += ' AND tx_time <= ?'
            params.append(end + '-31 23:59:59')
        cond = ('WHERE 1=1' + where) if where else ''
        conn = get_db()

        months = [r[0] for r in conn.execute(
            'SELECT DISTINCT substr(tx_time,1,7) FROM transactions ORDER BY 1')]
        monthly = [dict(r) for r in conn.execute(
            f"SELECT substr(tx_time,1,7) AS month, ROUND(SUM(amount),2) AS total"
            f" FROM transactions {cond} GROUP BY month ORDER BY month", params)]
        categories = [dict(r) for r in conn.execute(
            f"SELECT COALESCE(p.name, c.name, '待分类') AS name,"
            f" ROUND(SUM(t.amount),2) AS total"
            f" FROM transactions t LEFT JOIN categories c ON c.id=t.category_id"
            f" LEFT JOIN categories p ON p.id=c.parent_id"
            f" {cond} GROUP BY COALESCE(p.name, c.name, '待分类') ORDER BY total DESC", params)]
        subcats = [dict(r) for r in conn.execute(
            f"SELECT p.name AS parent, s.name AS name, ROUND(SUM(t.amount),2) AS total"
            f" FROM transactions t JOIN categories s ON s.id=t.subcategory_id"
            f" JOIN categories p ON p.id=s.parent_id"
            f" {cond} GROUP BY p.name, s.name ORDER BY total DESC", params)]
        merchants = [dict(r) for r in conn.execute(
            f"SELECT COALESCE(NULLIF(NULLIF(counterparty,''),'/'),'(未知)') AS name,"
            f" ROUND(SUM(amount),2) AS total, COUNT(*) AS cnt"
            f" FROM transactions {cond} GROUP BY name ORDER BY total DESC LIMIT 10",
            params)]
        weekday = [dict(r) for r in conn.execute(
            f"SELECT CAST(strftime('%w',tx_time) AS INTEGER) AS dow,"
            f" ROUND(SUM(amount),2) AS total FROM transactions {cond} GROUP BY dow",
            params)]
        paymethod = [dict(r) for r in conn.execute(
            f"SELECT COALESCE(NULLIF(pay_method,''),'未记录') AS name,"
            f" ROUND(SUM(amount),2) AS total FROM transactions {cond}"
            f" GROUP BY name ORDER BY total DESC", params)]
        conn.close()
        return jsonify({'months': months, 'monthly': monthly,
                        'categories': categories, 'subcats': subcats,
                        'merchants': merchants,
                        'weekday': weekday, 'paymethod': paymethod})

    # ---------------- 分类规则 ----------------
    @app.get('/api/rules')
    def api_rules():
        conn = get_db()
        rules = [dict(r) for r in conn.execute(
            'SELECT r.*, c.name AS category_name, p.id AS parent_id,'
            ' p.name AS parent_name FROM rules r '
            'JOIN categories c ON c.id = r.category_id '
            'LEFT JOIN categories p ON p.id = c.parent_id '
            'ORDER BY r.sort_order, r.id')]
        conn.close()
        return jsonify({'rules': rules})

    @app.post('/api/rules')
    def api_add_rule():
        d = request.get_json(force=True)
        keyword = (d.get('keyword') or '').strip()
        if not keyword or not d.get('category_id'):
            return jsonify({'error': '关键词和类别不能为空'}), 400
        category_id = int(d['category_id'])
        subcategory_id = int(d['subcategory_id']) if d.get('subcategory_id') else None
        leaf = subcategory_id or category_id
        conn = get_db()
        if subcategory_id:
            srow = conn.execute('SELECT parent_id FROM categories WHERE id=?',
                                (subcategory_id,)).fetchone()
            if not srow or srow['parent_id'] != category_id:
                conn.close()
                return jsonify({'error': '二级分类不属于所选一级分类'}), 400
        conn.execute(
            'INSERT INTO rules(keyword, category_id, sort_order) '
            'SELECT ?, ?, COALESCE(MAX(sort_order),0)+1 FROM rules',
            (keyword, leaf))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    @app.post('/api/rule/<int:rule_id>')
    def api_edit_rule(rule_id):
        d = request.get_json(force=True)
        keyword = (d.get('keyword') or '').strip()
        if not keyword or not d.get('category_id'):
            return jsonify({'error': '关键词和类别不能为空'}), 400
        category_id = int(d['category_id'])
        subcategory_id = int(d['subcategory_id']) if d.get('subcategory_id') else None
        leaf = subcategory_id or category_id
        conn = get_db()
        if subcategory_id:
            srow = conn.execute('SELECT parent_id FROM categories WHERE id=?',
                                (subcategory_id,)).fetchone()
            if not srow or srow['parent_id'] != category_id:
                conn.close()
                return jsonify({'error': '二级分类不属于所选一级分类'}), 400
        conn.execute('UPDATE rules SET keyword=?, category_id=? WHERE id=?',
                     (keyword, leaf, rule_id))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    @app.post('/api/rule/<int:rule_id>/toggle')
    def api_toggle_rule(rule_id):
        conn = get_db()
        conn.execute('UPDATE rules SET enabled = 1 - enabled WHERE id=?', (rule_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    @app.post('/api/rule/<int:rule_id>/move')
    def api_move_rule(rule_id):
        direction = request.get_json(force=True).get('dir')
        conn = get_db()
        ordered = [r['id'] for r in conn.execute(
            'SELECT id FROM rules ORDER BY sort_order, id')]
        i = ordered.index(rule_id) if rule_id in ordered else -1
        j = i - 1 if direction == 'up' else i + 1
        if 0 <= i < len(ordered) and 0 <= j < len(ordered):
            ordered[i], ordered[j] = ordered[j], ordered[i]
            for pos, rid in enumerate(ordered):
                conn.execute('UPDATE rules SET sort_order=? WHERE id=?', (pos, rid))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    @app.delete('/api/rule/<int:rule_id>')
    def api_delete_rule(rule_id):
        conn = get_db()
        conn.execute('DELETE FROM rules WHERE id=?', (rule_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    @app.post('/api/reclassify')
    def api_reclassify():
        conn = get_db()
        changed = classifier.reclassify(conn)
        conn.close()
        return jsonify({'changed': changed})

    # ---------------- 类别管理 ----------------
    @app.get('/api/categories')
    def api_categories():
        conn = get_db()
        cats = [dict(r) for r in conn.execute(
            'SELECT c.id, c.name, c.parent_id,'
            ' (SELECT COUNT(*) FROM transactions t'
            '  WHERE t.category_id=c.id OR t.subcategory_id=c.id) AS cnt'
            ' FROM categories c ORDER BY c.id')]
        conn.close()
        return jsonify({'categories': cats})

    @app.post('/api/categories')
    def api_add_category():
        d = request.get_json(force=True)
        name = (d.get('name') or '').strip()
        if not name:
            return jsonify({'error': '类别名不能为空'}), 400
        conn = get_db()
        try:
            if d.get('parent_id'):
                parent_id = int(d['parent_id'])
                p = conn.execute('SELECT id FROM categories WHERE id=? AND parent_id IS NULL',
                                 (parent_id,)).fetchone()
                if not p:
                    conn.close()
                    return jsonify({'error': '请选择有效的一级分类'}), 400
                conn.execute('INSERT INTO categories(name, parent_id) VALUES (?,?)',
                             (name, parent_id))
            else:
                conn.execute('INSERT INTO categories(name) VALUES (?)', (name,))
            conn.commit()
        except Exception:
            conn.close()
            return jsonify({'error': '类别已存在'}), 400
        conn.close()
        return jsonify({'ok': True})

    @app.post('/api/category/<int:cat_id>')
    def api_rename_category(cat_id):
        name = (request.get_json(force=True).get('name') or '').strip()
        if not name:
            return jsonify({'error': '类别名不能为空'}), 400
        conn = get_db()
        try:
            cur = conn.execute('UPDATE categories SET name=? WHERE id=?',
                               (name, cat_id))
            conn.commit()
        except Exception:
            conn.close()
            return jsonify({'error': '类别名已存在'}), 400
        if cur.rowcount == 0:
            conn.close()
            return jsonify({'error': '类别不存在'}), 404
        conn.close()
        return jsonify({'ok': True})

    @app.delete('/api/category/<int:cat_id>')
    def api_delete_category(cat_id):
        conn = get_db()
        row = conn.execute('SELECT parent_id FROM categories WHERE id=?',
                           (cat_id,)).fetchone()
        if not row:
            conn.close()
            return jsonify({'error': '类别不存在'}), 404
        if row['parent_id'] is None:
            # 一级分类：检查自身及子级是否被交易引用
            cnt = conn.execute(
                'SELECT COUNT(*) FROM transactions t '
                'WHERE t.category_id=? OR t.subcategory_id IN '
                '(SELECT id FROM categories WHERE parent_id=?)',
                (cat_id, cat_id)).fetchone()[0]
            if cnt > 0:
                conn.close()
                return jsonify({'error': f'仍有 {cnt} 笔交易使用该类别'
                                         f'或其二级分类，请先改分类后再删除'}), 400
            child_ids = [r['id'] for r in conn.execute(
                'SELECT id FROM categories WHERE parent_id=?', (cat_id,))]
            for cid in child_ids:
                conn.execute('DELETE FROM rules WHERE category_id=?', (cid,))
            conn.execute('DELETE FROM rules WHERE category_id=?', (cat_id,))
            conn.execute('DELETE FROM categories WHERE id=? OR parent_id=?',
                         (cat_id, cat_id))
        else:
            # 二级分类
            cnt = conn.execute('SELECT COUNT(*) FROM transactions '
                               'WHERE subcategory_id=?', (cat_id,)).fetchone()[0]
            if cnt > 0:
                conn.close()
                return jsonify({'error': f'仍有 {cnt} 笔交易使用该类别，'
                                         f'请先改分类后再删除'}), 400
            conn.execute('DELETE FROM rules WHERE category_id=?', (cat_id,))
            conn.execute('DELETE FROM categories WHERE id=?', (cat_id,))
        conn.commit()
        conn.close()
        return jsonify({'ok': True})

    return app
