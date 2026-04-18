from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3, hashlib, uuid, time, os

app = Flask(__name__)
CORS(app)

DB = 'phone_recycle.db'

# ── 数据库初始化 ──────────────────────────────────────────
def get_db():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS models (
            id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name  TEXT UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS valuations (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            model           TEXT,
            ram             TEXT,
            storage         TEXT,
            channel         TEXT,
            usage_months    INTEGER,
            appearance_score INTEGER,
            battery_health  INTEGER,
            camera          TEXT,
            fingerprint     TEXT,
            charging_port   TEXT,
            screen          TEXT,
            speaker         TEXT,
            recycle_price   INTEGER,
            sale_price      INTEGER,
            created_at      INTEGER DEFAULT (strftime('%s','now'))
        );
        INSERT OR IGNORE INTO users (username, password) VALUES ('admin', '''' + md5('admin123') + ''');
        INSERT OR IGNORE INTO models (name) VALUES
            ('华为 Mate 60 Pro'),('华为 Mate 60'),('华为 P60 Pro'),('华为 P60'),
            ('华为 Mate 50 Pro'),('华为 Mate 50'),('华为 P50 Pro'),('华为 P50'),
            ('华为 nova 11 Pro'),('华为 nova 11');
    ''')
    db.commit()
    db.close()

def md5(s):
    return hashlib.md5(s.encode()).hexdigest()

# 简易 token 存储（生产环境应用 JWT 或 Redis）
tokens = {}

def auth(req):
    token = req.headers.get('Authorization', '').replace('Bearer ', '')
    return tokens.get(token)

def ok(data=None, **kw):
    return jsonify({'code': 0, 'data': data, **kw})

def err(msg, code=400):
    return jsonify({'code': 1, 'msg': msg}), code

# ── 用户接口 ─────────────────────────────────────────────
@app.post('/api/login')
def login():
    body = request.json or {}
    username, password = body.get('username'), body.get('password')
    if not username or not password:
        return err('用户名或密码不能为空')
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE username=? AND password=?',
                      (username, md5(password))).fetchone()
    db.close()
    if not user:
        return err('用户名或密码错误')
    token = uuid.uuid4().hex
    tokens[token] = dict(user)
    return ok({'token': token, 'username': username})

@app.post('/api/register')
def register():
    body = request.json or {}
    username, password = body.get('username'), body.get('password')
    if not username or not password:
        return err('参数缺失')
    db = get_db()
    try:
        db.execute('INSERT INTO users (username, password) VALUES (?,?)',
                   (username, md5(password)))
        db.commit()
    except sqlite3.IntegrityError:
        return err('用户名已存在')
    finally:
        db.close()
    return ok(msg='注册成功')

# ── 机型接口 ──────────────────────────────────��──────────
@app.get('/api/models')
def get_models():
    db = get_db()
    rows = db.execute('SELECT * FROM models ORDER BY id').fetchall()
    db.close()
    return ok([dict(r) for r in rows])

@app.post('/api/models')
def add_model():
    user = auth(request)
    if not user:
        return err('未登录', 401)
    name = (request.json or {}).get('name', '').strip()
    if not name:
        return err('机型名称不能为空')
    db = get_db()
    try:
        db.execute('INSERT INTO models (name) VALUES (?)', (name,))
        db.commit()
    except sqlite3.IntegrityError:
        return err('机型已存在')
    finally:
        db.close()
    return ok(msg='添加成功')

@app.delete('/api/models/<int:mid>')
def del_model(mid):
    if not auth(request):
        return err('未登录', 401)
    db = get_db()
    db.execute('DELETE FROM models WHERE id=?', (mid,))
    db.commit()
    db.close()
    return ok(msg='删除成功')

# ── 估值接口 ─────────────────────────────────────────────
@app.post('/api/valuate')
def valuate():
    user = auth(request)
    if not user:
        return err('未登录', 401)
    b = request.json or {}

    # 估值计算逻辑
    base_prices = {
        '华为 Mate 60 Pro': 6999, '华为 Mate 60': 5499,
        '华为 P60 Pro': 5988,    '华为 P60': 4488,
        '华为 Mate 50 Pro': 5499,'华为 Mate 50': 3999,
        '华为 P50 Pro': 4488,    '华为 P50': 3288,
        '华为 nova 11 Pro': 3499,'华为 nova 11': 2499,
    }
    base = base_prices.get(b.get('model', ''), 4000)
    usage = max(0, min(int(b.get('usage_months', 12)), 60))
    appearance = max(0, min(int(b.get('appearance_score', 80)), 100))
    battery = max(0, min(int(b.get('battery_health', 90)), 100))

    factor = (1 - 0.018 * usage) * (appearance / 100) * (battery / 100)
    recycle_price = int(base * factor * 0.75)
    sale_price    = int(base * factor * 0.88)

    db = get_db()
    db.execute('''INSERT INTO valuations
        (user_id,model,ram,storage,channel,usage_months,appearance_score,
         battery_health,camera,fingerprint,charging_port,screen,speaker,
         recycle_price,sale_price)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        user['id'], b.get('model'), b.get('ram'), b.get('storage'),
        b.get('channel'), usage, appearance, battery,
        b.get('camera','正常'), b.get('fingerprint','正常'),
        b.get('charging_port','正常'), b.get('screen','正常'),
        b.get('speaker','正常'), recycle_price, sale_price
    ))
    db.commit()
    db.close()
    return ok({'recycle_price': recycle_price, 'sale_price': sale_price})

@app.get('/api/valuations')
def get_valuations():
    user = auth(request)
    if not user:
        return err('未登录', 401)
    db = get_db()
    rows = db.execute(
        'SELECT * FROM valuations WHERE user_id=? ORDER BY created_at DESC',
        (user['id'],)
    ).fetchall()
    db.close()
    return ok([dict(r) for r in rows])

@app.delete('/api/valuations/<int:vid>')
def del_valuation(vid):
    user = auth(request)
    if not user:
        return err('未登录', 401)
    db = get_db()
    db.execute('DELETE FROM valuations WHERE id=? AND user_id=?', (vid, user['id']))
    db.commit()
    db.close()
    return ok(msg='删除成功')

# ── 启动 ─────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    print('后端启动: http://localhost:5000')
    print('默认账号: admin / admin123')
    app.run(debug=True, port=5000)
