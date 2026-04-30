from flask import Flask, request, jsonify, g
from flask_cors import CORS
import sqlite3, bcrypt, jwt, uuid, os
from datetime import datetime, timezone, timedelta
from functools import wraps

app = Flask(__name__)
CORS(app)

DB = os.environ.get('DB_PATH', os.path.join(os.path.dirname(__file__), 'phone_recycle.db'))
JWT_SECRET = os.environ.get('JWT_SECRET', 'dev-secret-change-in-prod')
JWT_EXP_HOURS = 24

# ── 数据库 ────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
        g.db.execute('PRAGMA journal_mode=WAL')
        g.db.execute('PRAGMA foreign_keys=ON')
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                username   TEXT    UNIQUE NOT NULL,
                password   TEXT    NOT NULL,
                nickname   TEXT    DEFAULT '',
                avatar     TEXT    DEFAULT '',
                phone      TEXT    DEFAULT '',
                created_at INTEGER DEFAULT (strftime('%s','now'))
            );
            CREATE TABLE IF NOT EXISTS models (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS valuations (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id          INTEGER NOT NULL REFERENCES users(id),
                model            TEXT,
                ram              TEXT,
                storage          TEXT,
                channel          TEXT,
                usage_months     INTEGER,
                appearance_score INTEGER,
                battery_health   INTEGER,
                camera           TEXT,
                microphone       TEXT,
                fingerprint      TEXT,
                charging_port    TEXT,
                screen_func      TEXT,
                speaker          TEXT,
                volume_key       TEXT,
                power_key        TEXT,
                water_damage     TEXT,
                repaired         TEXT,
                repair_note      TEXT,
                recycle_price    INTEGER,
                sale_price       INTEGER,
                created_at       INTEGER DEFAULT (strftime('%s','now'))
            );
        ''')
        # 默认机型
        models = [
            # Mate 系列
            '华为 Mate 80 RS 非凡大师','华为 Mate 80 Pro Max','华为 Mate 80 Pro','华为 Mate 80',
            '华为 Mate 70 Pro+','华为 Mate 70 Pro','华为 Mate 70',
            '华为 Mate 60 RS 非凡大师','华为 Mate 60 Pro+','华为 Mate 60 Pro','华为 Mate 60',
            '华为 Mate 50 RS 保时捷设计','华为 Mate 50 Pro','华为 Mate 50',
            '华为 Mate 40 RS 保时捷设计','华为 Mate 40 Pro+','华为 Mate 40 Pro','华为 Mate 40',
            '华为 Mate 30 Pro','华为 Mate 30',
            '华为 Mate 20 X','华为 Mate 20 Pro','华为 Mate 20',
            '华为 Mate 10 Pro','华为 Mate 10',
            '华为 Mate 9',
            # Pura / P 系列
            '华为 Pura 80','华为 Pura 70 Ultra','华为 Pura 70 Pro+','华为 Pura 70 Pro','华为 Pura 70',
            '华为 P60 Art','华为 P60 Pro','华为 P60',
            '华为 P50 Pro','华为 P50',
            '华为 P40 Pro+','华为 P40 Pro','华为 P40',
            '华为 P30 Pro','华为 P30',
            '华为 P20 Pro','华为 P20',
            '华为 P10 Plus','华为 P10',
            '华为 P9 Plus','华为 P9',
            # nova 系列
            '华为 nova 15 Pro','华为 nova 15',
            '华为 nova 14 Ultra','华为 nova 14 Pro','华为 nova 14',
            '华为 nova 13 Pro',
            '华为 nova 12 Ultra','华为 nova 12 Pro','华为 nova 12',
            '华为 nova 11 Ultra','华为 nova 11 Pro','华为 nova 11',
            '华为 nova 10 Pro','华为 nova 10',
            '华为 nova 9 Pro','华为 nova 9',
            '华为 nova 8 Pro','华为 nova 8',
            '华为 nova 7 Pro','华为 nova 7',
            '华为 nova 6',
            '华为 nova 5 Pro','华为 nova 5',
            '华为 nova 4','华为 nova 3',
            '华为 nova 2s','华为 nova 青春版','华为 nova',
            # 畅享系列
            '华为 畅享 80','华为 畅享 70X',
            '华为 畅享 60X','华为 畅享 60',
            '华为 畅享 50',
            '华为 畅享 20 Plus','华为 畅享 20',
            '华为 畅享 10',
            '华为 畅享 9 Plus',
            '华为 畅享 8',
            '华为 畅享 7s','华为 畅享 7',
            # 麦芒系列
            '华为 麦芒 40','华为 麦芒 30','华为 麦芒 20',
            '华为 麦芒 11','华为 麦芒 10','华为 麦芒 9',
            '华为 麦芒 8','华为 麦芒 7','华为 麦芒 6','华为 麦芒 5',
        ]
        for m in models:
            db.execute('INSERT OR IGNORE INTO models (name) VALUES (?)', (m,))
        # 默认管理员（首次运行时创建）
        pw = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt()).decode()
        db.execute('INSERT OR IGNORE INTO users (username, password) VALUES (?,?)', ('admin', pw))
        db.commit()

# ── 响应工具 ──────────────────────────────────────────────

def ok(data=None, msg='ok', **kw):
    return jsonify({'code': 0, 'msg': msg, 'data': data, **kw})

def err(msg, status=400):
    return jsonify({'code': 1, 'msg': msg, 'data': None}), status

# ── JWT 工具 ──────────────────────────────────────────────

def make_token(user_id: int, username: str) -> str:
    payload = {
        'sub': user_id,
        'username': username,
        'exp': datetime.now(timezone.utc) + timedelta(hours=JWT_EXP_HOURS),
        'jti': uuid.uuid4().hex,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except jwt.PyJWTError:
        return None

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        raw = request.headers.get('Authorization', '')
        token = raw.removeprefix('Bearer ').strip()
        payload = decode_token(token)
        if not payload:
            return err('未登录或 token 已过期', 401)
        g.current_user = payload
        return f(*args, **kwargs)
    return wrapper

# ── 参数校验工具 ──────────────────────────────────────────

def require_fields(body: dict, *fields):
    missing = [f for f in fields if body.get(f) is None]
    if missing:
        return err(f'缺少必填字段：{", ".join(missing)}')
    return None

# ── 用户接口 ──────────────────────────────────────────────

@app.post('/api/register')
def register():
    body = request.get_json(silent=True) or {}
    e = require_fields(body, 'username', 'password')
    if e: return e
    username = body['username'].strip()
    password = body['password']
    if len(username) < 2 or len(username) > 20:
        return err('用户名长度须在 2~20 个字符之间')
    if len(password) < 6:
        return err('密码长度不能少于 6 位')
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    db = get_db()
    try:
        db.execute('INSERT INTO users (username, password) VALUES (?,?)', (username, pw_hash))
        db.commit()
    except sqlite3.IntegrityError:
        return err('用户名已存在')
    return ok(msg='注册成功'), 201

@app.post('/api/login')
def login():
    body = request.get_json(silent=True) or {}
    e = require_fields(body, 'username', 'password')
    if e: return e
    db = get_db()
    row = db.execute('SELECT * FROM users WHERE username=?', (body['username'],)).fetchone()
    if not row or not bcrypt.checkpw(body['password'].encode(), row['password'].encode()):
        return err('用户名或密码错误', 401)
    token = make_token(row['id'], row['username'])
    return ok({'token': token, 'username': row['username']})

@app.post('/api/change-password')
@login_required
def change_password():
    body = request.get_json(silent=True) or {}
    e = require_fields(body, 'old_password', 'new_password')
    if e: return e
    if len(body['new_password']) < 6:
        return err('新密码长度不能少于 6 位')
    db = get_db()
    row = db.execute('SELECT * FROM users WHERE id=?', (g.current_user['sub'],)).fetchone()
    if not bcrypt.checkpw(body['old_password'].encode(), row['password'].encode()):
        return err('原密码错误')
    new_hash = bcrypt.hashpw(body['new_password'].encode(), bcrypt.gensalt()).decode()
    db.execute('UPDATE users SET password=? WHERE id=?', (new_hash, g.current_user['sub']))
    db.commit()
    return ok(msg='密码修改成功')

@app.get('/api/me')
@login_required
def me():
    db = get_db()
    row = db.execute('SELECT id, username, nickname, avatar, phone, created_at FROM users WHERE id=?',
                     (g.current_user['sub'],)).fetchone()
    return ok(dict(row))

@app.post('/api/profile')
@login_required
def update_profile():
    body = request.get_json(silent=True) or {}
    nickname = body.get('nickname', '').strip()
    avatar   = body.get('avatar', '').strip()
    phone    = body.get('phone', '').strip()
    db = get_db()
    db.execute(
        'UPDATE users SET nickname=?, avatar=?, phone=? WHERE id=?',
        (nickname, avatar, phone, g.current_user['sub'])
    )
    db.commit()
    return ok(msg='资料更新成功')

# ── 机型接口 ──────────────────────────────────────────────

@app.get('/api/models')
def get_models():
    db = get_db()
    rows = db.execute('SELECT * FROM models ORDER BY id').fetchall()
    return ok([dict(r) for r in rows])

# 机型规格映射：每个机型对应的 [内存, 存储] 组合列表
MODEL_SPECS = {
    # ── Mate 系列 ──
    '华为 Mate 80 RS 非凡大师': [['20GB','512GB'],['20GB','1TB']],
    '华为 Mate 80 Pro Max':     [['16GB','512GB'],['16GB','1TB']],
    '华为 Mate 80 Pro':         [['12GB','256GB'],['12GB','512GB']],
    '华为 Mate 80':             [['12GB','256GB'],['12GB','512GB']],
    '华为 Mate 70 Pro+':        [['16GB','512GB'],['16GB','1TB']],
    '华为 Mate 70 Pro':         [['12GB','256GB'],['12GB','512GB']],
    '华为 Mate 70':             [['12GB','256GB'],['12GB','512GB']],
    '华为 Mate 60 RS 非凡大师': [['16GB','512GB'],['16GB','1TB']],
    '华为 Mate 60 Pro+':        [['12GB','512GB'],['12GB','1TB']],
    '华为 Mate 60 Pro':         [['12GB','256GB'],['12GB','512GB'],['12GB','1TB']],
    '华为 Mate 60':             [['12GB','256GB'],['12GB','512GB']],
    '华为 Mate 50 RS 保时捷设计':[['12GB','512GB']],
    '华为 Mate 50 Pro':         [['8GB','256GB'],['8GB','512GB']],
    '华为 Mate 50':             [['8GB','128GB'],['8GB','256GB']],
    '华为 Mate 40 RS 保时捷设计':[['12GB','256GB'],['12GB','512GB']],
    '华为 Mate 40 Pro+':        [['12GB','256GB']],
    '华为 Mate 40 Pro':         [['8GB','128GB'],['8GB','256GB'],['8GB','512GB']],
    '华为 Mate 40':             [['8GB','128GB'],['8GB','256GB']],
    '华为 Mate 30 Pro':         [['8GB','128GB'],['8GB','256GB'],['8GB','512GB']],
    '华为 Mate 30':             [['8GB','128GB'],['8GB','256GB']],
    '华为 Mate 20 X':           [['6GB','128GB'],['8GB','256GB']],
    '华为 Mate 20 Pro':         [['6GB','128GB'],['8GB','128GB'],['8GB','256GB']],
    '华为 Mate 20':             [['6GB','64GB'],['6GB','128GB'],['8GB','256GB']],
    '华为 Mate 10 Pro':         [['6GB','64GB'],['6GB','128GB']],
    '华为 Mate 10':             [['4GB','64GB'],['6GB','128GB']],
    '华为 Mate 9':              [['4GB','64GB'],['6GB','128GB'],['6GB','256GB']],
    # ── Pura / P 系列 ──
    '华为 Pura 80':             [['12GB','256GB'],['12GB','512GB']],
    '华为 Pura 70 Ultra':       [['16GB','512GB'],['16GB','1TB']],
    '华为 Pura 70 Pro+':        [['12GB','512GB'],['12GB','1TB']],
    '华为 Pura 70 Pro':         [['12GB','256GB'],['12GB','512GB']],
    '华为 Pura 70':             [['12GB','256GB'],['12GB','512GB']],
    '华为 P60 Art':             [['12GB','512GB'],['12GB','1TB']],
    '华为 P60 Pro':             [['8GB','256GB'],['8GB','512GB']],
    '华为 P60':                 [['8GB','128GB'],['8GB','256GB']],
    '华为 P50 Pro':             [['8GB','128GB'],['8GB','256GB']],
    '华为 P50':                 [['8GB','128GB'],['8GB','256GB']],
    '华为 P40 Pro+':            [['8GB','256GB'],['8GB','512GB']],
    '华为 P40 Pro':             [['8GB','128GB'],['8GB','256GB'],['8GB','512GB']],
    '华为 P40':                 [['6GB','128GB'],['8GB','128GB'],['8GB','256GB']],
    '华为 P30 Pro':             [['8GB','128GB'],['8GB','256GB'],['8GB','512GB']],
    '华为 P30':                 [['8GB','64GB'],['8GB','128GB'],['8GB','256GB']],
    '华为 P20 Pro':             [['6GB','64GB'],['6GB','128GB'],['6GB','256GB']],
    '华为 P20':                 [['6GB','64GB'],['6GB','128GB']],
    '华为 P10 Plus':            [['6GB','64GB'],['6GB','128GB'],['6GB','256GB']],
    '华为 P10':                 [['4GB','64GB'],['4GB','128GB']],
    '华为 P9 Plus':             [['4GB','64GB'],['4GB','128GB']],
    '华为 P9':                  [['3GB','32GB'],['4GB','64GB']],
    # ── nova 系列 ──
    '华为 nova 15 Pro':         [['12GB','256GB'],['12GB','512GB']],
    '华为 nova 15':             [['8GB','128GB'],['8GB','256GB'],['12GB','256GB']],
    '华为 nova 14 Ultra':       [['12GB','256GB'],['12GB','512GB'],['12GB','1TB']],
    '华为 nova 14 Pro':         [['12GB','256GB'],['12GB','512GB']],
    '华为 nova 14':             [['8GB','128GB'],['8GB','256GB'],['12GB','256GB']],
    '华为 nova 13 Pro':         [['12GB','256GB'],['12GB','512GB'],['12GB','1TB']],
    '华为 nova 12 Ultra':       [['12GB','512GB'],['12GB','1TB']],
    '华为 nova 12 Pro':         [['12GB','256GB']],
    '华为 nova 12':             [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 11 Ultra':       [['8GB','256GB'],['8GB','512GB']],
    '华为 nova 11 Pro':         [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 11':             [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 10 Pro':         [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 10':             [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 9 Pro':          [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 9':              [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 8 Pro':          [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 8':              [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 7 Pro':          [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 7':              [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 6':              [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 5 Pro':          [['8GB','128GB'],['8GB','256GB']],
    '华为 nova 5':              [['8GB','128GB']],
    '华为 nova 4':              [['8GB','128GB']],
    '华为 nova 3':              [['6GB','128GB']],
    '华为 nova 2s':             [['4GB','64GB'],['6GB','64GB'],['6GB','128GB']],
    '华为 nova 青春版':          [['4GB','64GB']],
    '华为 nova':                [['3GB','32GB'],['4GB','64GB']],
    # ── 畅享系列 ──
    '华为 畅享 80':             [['8GB','128GB'],['8GB','256GB'],['8GB','512GB']],
    '华为 畅享 70X':            [['8GB','256GB']],
    '华为 畅享 60X':            [['8GB','128GB'],['8GB','256GB'],['8GB','512GB']],
    '华为 畅享 60':             [['8GB','128GB'],['8GB','256GB']],
    '华为 畅享 50':             [['6GB','128GB'],['8GB','128GB'],['8GB','256GB']],
    '华为 畅享 20 Plus':        [['6GB','128GB'],['8GB','128GB']],
    '华为 畅享 20':             [['4GB','128GB'],['6GB','128GB']],
    '华为 畅享 10':             [['4GB','64GB'],['6GB','64GB']],
    '华为 畅享 9 Plus':         [['4GB','64GB'],['4GB','128GB']],
    '华为 畅享 8':              [['3GB','32GB'],['4GB','64GB']],
    '华为 畅享 7s':             [['3GB','32GB'],['4GB','64GB']],
    '华为 畅享 7':              [['2GB','16GB'],['3GB','32GB']],
    # ── 麦芒系列 ──
    '华为 麦芒 40':             [['8GB','256GB'],['12GB','256GB'],['12GB','512GB']],
    '华为 麦芒 30':             [['8GB','256GB'],['12GB','256GB']],
    '华为 麦芒 20':             [['8GB','256GB'],['12GB','256GB']],
    '华为 麦芒 11':             [['8GB','128GB'],['8GB','256GB']],
    '华为 麦芒 10':             [['8GB','128GB']],
    '华为 麦芒 9':              [['6GB','128GB'],['8GB','128GB']],
    '华为 麦芒 8':              [['6GB','128GB']],
    '华为 麦芒 7':              [['6GB','64GB']],
    '华为 麦芒 6':              [['4GB','64GB']],
    '华为 麦芒 5':              [['3GB','32GB'],['4GB','64GB']],
}

@app.get('/api/models/specs')
def get_model_specs():
    return ok(MODEL_SPECS)

@app.post('/api/models')
@login_required
def add_model():
    body = request.get_json(silent=True) or {}
    name = body.get('name', '').strip()
    if not name:
        return err('机型名称不能为空')
    db = get_db()
    try:
        cur = db.execute('INSERT INTO models (name) VALUES (?)', (name,))
        db.commit()
    except sqlite3.IntegrityError:
        return err('机型已存在')
    return ok({'id': cur.lastrowid, 'name': name}, msg='添加成功'), 201

@app.delete('/api/models/<int:mid>')
@login_required
def del_model(mid):
    db = get_db()
    db.execute('DELETE FROM models WHERE id=?', (mid,))
    db.commit()
    return ok(msg='删除成功')

# ── 估值接口 ──────────────────────────────────────────────

BASE_PRICES = {
    # 格式：'机型': {'存储': 基准价, ...}
    # ── Mate 系列 ──
    '华为 Mate 80 RS 非凡大师': {'512GB': 11999, '1TB': 12999},
    '华为 Mate 80 Pro Max':     {'512GB': 7999,  '1TB': 8999},
    '华为 Mate 80 Pro':         {'256GB': 5999,  '512GB': 6499},
    '华为 Mate 80':             {'256GB': 4699,  '512GB': 5199},
    '华为 Mate 70 Pro+':        {'512GB': 8499,  '1TB': 9499},
    '华为 Mate 70 Pro':         {'256GB': 6499,  '512GB': 6999},
    '华为 Mate 70':             {'256GB': 5499,  '512GB': 5999},
    '华为 Mate 60 RS 非凡大师': {'512GB': 11999, '1TB': 12999},
    '华为 Mate 60 Pro+':        {'512GB': 8999,  '1TB': 9999},
    '华为 Mate 60 Pro':         {'256GB': 6499,  '512GB': 6999, '1TB': 7999},
    '华为 Mate 60':             {'256GB': 5499,  '512GB': 5999},
    '华为 Mate 50 RS 保时捷设计':{'512GB': 12999},
    '华为 Mate 50 Pro':         {'256GB': 6799,  '512GB': 7799},
    '华为 Mate 50':             {'128GB': 4999,  '256GB': 5499},
    '华为 Mate 40 RS 保时捷设计':{'256GB': 11999, '512GB': 12999},
    '华为 Mate 40 Pro+':        {'256GB': 8999},
    '华为 Mate 40 Pro':         {'128GB': 6499,  '256GB': 6999, '512GB': 7999},
    '华为 Mate 40':             {'128GB': 4999,  '256GB': 5499},
    '华为 Mate 30 Pro':         {'128GB': 6899,  '256GB': 7399, '512GB': 7899},
    '华为 Mate 30':             {'128GB': 4999,  '256GB': 5499},
    '华为 Mate 20 X':           {'128GB': 4999,  '256GB': 5999},
    '华为 Mate 20 Pro':         {'128GB': 5399,  '256GB': 6799},
    '华为 Mate 20':             {'64GB':  3999,  '128GB': 4499, '256GB': 5499},
    '华为 Mate 10 Pro':         {'64GB':  4899,  '128GB': 5399},
    '华为 Mate 10':             {'64GB':  3899,  '128GB': 4499},
    '华为 Mate 9':              {'64GB':  3399,  '128GB': 4399, '256GB': 5299},
    # ── Pura / P 系列 ──
    '华为 Pura 80':             {'256GB': 4699,  '512GB': 5199},
    '华为 Pura 70 Ultra':       {'512GB': 9999,  '1TB': 10999},
    '华为 Pura 70 Pro+':        {'512GB': 7999,  '1TB': 8999},
    '华为 Pura 70 Pro':         {'256GB': 6499,  '512GB': 6999},
    '华为 Pura 70':             {'256GB': 5499,  '512GB': 5999},
    '华为 P60 Art':             {'512GB': 8988,  '1TB': 10988},
    '华为 P60 Pro':             {'256GB': 6988,  '512GB': 7988},
    '华为 P60':                 {'128GB': 4488,  '256GB': 4988},
    '华为 P50 Pro':             {'128GB': 5988,  '256GB': 6488},
    '华为 P50':                 {'128GB': 4488,  '256GB': 4988},
    '华为 P40 Pro+':            {'256GB': 7988,  '512GB': 8888},
    '华为 P40 Pro':             {'128GB': 5988,  '256GB': 6488, '512GB': 7388},
    '华为 P40':                 {'128GB': 4188,  '256GB': 4988},
    '华为 P30 Pro':             {'128GB': 5488,  '256GB': 5988, '512GB': 6788},
    '华为 P30':                 {'64GB':  3988,  '128GB': 4288, '256GB': 4788},
    '华为 P20 Pro':             {'64GB':  4988,  '128GB': 5488, '256GB': 6288},
    '华为 P20':                 {'64GB':  3788,  '128GB': 4288},
    '华为 P10 Plus':            {'64GB':  4388,  '128GB': 4888, '256GB': 5588},
    '华为 P10':                 {'64GB':  3788,  '128GB': 4288},
    '华为 P9 Plus':             {'64GB':  3988,  '128GB': 4388},
    '华为 P9':                  {'32GB':  2988,  '64GB':  3688},
    # ── nova 系列 ──
    '华为 nova 15 Pro':         {'256GB': 3499,  '512GB': 3899},
    '华为 nova 15':             {'128GB': 2699,  '256GB': 2999},
    '华为 nova 14 Ultra':       {'256GB': 4199,  '512GB': 4499, '1TB': 4999},
    '华为 nova 14 Pro':         {'256GB': 3499,  '512GB': 3799},
    '华为 nova 14':             {'128GB': 2699,  '256GB': 2999},
    '华为 nova 13 Pro':         {'256GB': 3699,  '512GB': 3999, '1TB': 4499},
    '华为 nova 12 Ultra':       {'512GB': 4699,  '1TB': 5499},
    '华为 nova 12 Pro':         {'256GB': 3999},
    '华为 nova 12':             {'128GB': 2999,  '256GB': 3299},
    '华为 nova 11 Ultra':       {'256GB': 4499,  '512GB': 4999},
    '华为 nova 11 Pro':         {'128GB': 3499,  '256GB': 3799},
    '华为 nova 11':             {'128GB': 2499,  '256GB': 2799},
    '华为 nova 10 Pro':         {'128GB': 3699,  '256GB': 3999},
    '华为 nova 10':             {'128GB': 2699,  '256GB': 2999},
    '华为 nova 9 Pro':          {'128GB': 3499,  '256GB': 3899},
    '华为 nova 9':              {'128GB': 2699,  '256GB': 2999},
    '华为 nova 8 Pro':          {'128GB': 3999,  '256GB': 4399},
    '华为 nova 8':              {'128GB': 3299,  '256GB': 3699},
    '华为 nova 7 Pro':          {'128GB': 3699,  '256GB': 4099},
    '华为 nova 7':              {'128GB': 2999,  '256GB': 3399},
    '华为 nova 6':              {'128GB': 3199,  '256GB': 4199},
    '华为 nova 5 Pro':          {'128GB': 2999,  '256GB': 3399},
    '华为 nova 5':              {'128GB': 2799},
    '华为 nova 4':              {'128GB': 3099},
    '华为 nova 3':              {'128GB': 2999},
    '华为 nova 2s':             {'64GB':  2699,  '128GB': 3399},
    '华为 nova 青春版':          {'64GB':  1999},
    '华为 nova':                {'32GB':  2099,  '64GB':  2399},
    # ── 畅享系列 ──
    '华为 畅享 80':             {'128GB': 1199,  '256GB': 1399, '512GB': 1699},
    '华为 畅享 70X':            {'256GB': 1799},
    '华为 畅享 60X':            {'128GB': 1799,  '256GB': 1999, '512GB': 2299},
    '华为 畅享 60':             {'128GB': 1299,  '256GB': 1499},
    '华为 畅享 50':             {'128GB': 1299,  '256GB': 1699},
    '华为 畅享 20 Plus':        {'128GB': 2299},
    '华为 畅享 20':             {'128GB': 1699},
    '华为 畅享 10':             {'64GB':  1199},
    '华为 畅享 9 Plus':         {'64GB':  1499,  '128GB': 1699},
    '华为 畅享 8':              {'32GB':  1299,  '64GB':  1599},
    '华为 畅享 7s':             {'32GB':  1499,  '64GB':  1699},
    '华为 畅享 7':              {'16GB':  899,   '32GB':  1099},
    # ── 麦芒系列 ──
    '华为 麦芒 40':             {'256GB': 1999,  '512GB': 2499},
    '华为 麦芒 30':             {'256GB': 1999},
    '华为 麦芒 20':             {'256GB': 1799},
    '华为 麦芒 11':             {'128GB': 1799,  '256GB': 1999},
    '华为 麦芒 10':             {'128GB': 2299},
    '华为 麦芒 9':              {'128GB': 2199},
    '华为 麦芒 8':              {'128GB': 1899},
    '华为 麦芒 7':              {'64GB':  2399},
    '华为 麦芒 6':              {'64GB':  2399},
    '华为 麦芒 5':              {'32GB':  2399,  '64GB':  2599},
}

def _clamp(val, lo, hi):
    return max(lo, min(hi, int(val)))

def _get_base(model, storage):
    specs = BASE_PRICES.get(model)
    if not specs:
        return 4000
    if storage in specs:
        return specs[storage]
    # 找最接近的存储版本
    return list(specs.values())[0]

FUNC_FIELDS = ['camera', 'microphone', 'fingerprint', 'charging_port',
               'screen_func', 'speaker', 'volume_key', 'power_key']

def calc_price(model, storage, usage_months, appearance_score, battery_health,
               water_damage='无', repaired='未维修', func_status=None):
    base       = _get_base(model, storage)
    usage      = _clamp(usage_months,    0, 72)
    appearance = _clamp(appearance_score, 0, 100)
    battery    = _clamp(battery_health,   0, 100)

    # 时间折旧：每月 1.2%，最低保留 15%
    time_factor = max(1 - 0.012 * usage, 0.15)

    # 外观系数
    appearance_factor = appearance / 100

    # 电池系数：权重低，100%→1.0，0%→0.85
    battery_factor = 0.85 + 0.15 * (battery / 100)

    # 功能扣分：每项异常扣 5%，最多扣 25%
    abnormal = 0
    if func_status:
        for f in FUNC_FIELDS:
            if func_status.get(f) == '异常':
                abnormal += 1
    func_factor = 1 - min(abnormal * 0.05, 0.25)

    factor = time_factor * appearance_factor * battery_factor * func_factor

    if water_damage == '有':
        factor *= 0.65
    if repaired == '已维修':
        factor *= 0.88

    factor = max(factor, 0.08)
    return int(base * factor * 0.72), int(base * factor * 0.85)


@app.post('/api/valuate')
@login_required
def valuate():
    b = request.get_json(silent=True) or {}
    e = require_fields(b, 'model', 'usage_months', 'appearance_score', 'battery_health')
    if e: return e

    recycle_price, sale_price = calc_price(
        b['model'], b.get('storage', ''),
        b['usage_months'], b['appearance_score'], b['battery_health'],
        b.get('water_damage', '无'), b.get('repaired', '未维修'),
        func_status={f: b.get(f, '正常') for f in FUNC_FIELDS}
    )

    db = get_db()
    try:
        cur = db.execute('''
            INSERT INTO valuations
                (user_id, model, ram, storage, channel, usage_months,
                 appearance_score, battery_health,
                 camera, microphone, fingerprint, charging_port, screen_func,
                 speaker, volume_key, power_key,
                 water_damage, repaired, repair_note,
                 recycle_price, sale_price)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            g.current_user['sub'],
            b.get('model'), b.get('ram'), b.get('storage'),
            b.get('channel'), _clamp(b['usage_months'], 0, 72),
            _clamp(b['appearance_score'], 0, 100),
            _clamp(b['battery_health'], 0, 100),
            b.get('camera', '正常'), b.get('microphone', '正常'),
            b.get('fingerprint', '正常'), b.get('charging_port', '正常'),
            b.get('screen_func', '正常'), b.get('speaker', '正常'),
            b.get('volume_key', '正常'), b.get('power_key', '正常'),
            b.get('water_damage', '无'), b.get('repaired', '未维修'),
            b.get('repair_note', ''),
            recycle_price, sale_price,
        ))
        db.commit()
    except sqlite3.IntegrityError:
        return err('用户不存在，请重新登录', 401)
    return ok({
        'id': cur.lastrowid,
        'recycle_price': recycle_price,
        'sale_price': sale_price,
    })

@app.get('/api/valuations')
@login_required
def get_valuations():
    db = get_db()
    rows = db.execute(
        'SELECT * FROM valuations WHERE user_id=? ORDER BY created_at DESC',
        (g.current_user['sub'],)
    ).fetchall()
    return ok([dict(r) for r in rows])

@app.get('/api/valuations/<int:vid>')
@login_required
def get_valuation(vid):
    db = get_db()
    row = db.execute(
        'SELECT * FROM valuations WHERE id=? AND user_id=?',
        (vid, g.current_user['sub'])
    ).fetchone()
    if not row:
        return err('记录不存在', 404)
    return ok(dict(row))

@app.delete('/api/valuations/<int:vid>')
@login_required
def del_valuation(vid):
    db = get_db()
    cur = db.execute(
        'DELETE FROM valuations WHERE id=? AND user_id=?',
        (vid, g.current_user['sub'])
    )
    db.commit()
    if cur.rowcount == 0:
        return err('记录不存在或无权限', 404)
    return ok(msg='删除成功')

# ── 启动 ──────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    print('后端启动: http://localhost:5000')
    print('默认账号: admin / admin123')
    app.run(host='0.0.0.0', debug=True, port=5000)
