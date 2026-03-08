from flask import Flask, request, jsonify, render_template, send_from_directory
import sqlite3
import json
import os

app = Flask(__name__)
DATABASE = 'casino.db'
CONFIG_PATH = 'config.json'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                points INTEGER DEFAULT 100
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                change INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_valid BOOLEAN DEFAULT 1,
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE
            )
        ''')
        conn.commit()

init_db()

# 設定ファイルを返す
@app.route('/api/config')
def get_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify({"error": "config not found"}), 500

# 全プレイヤー取得
@app.route('/api/players', methods=['GET'])
def get_players():
    with get_db() as conn:
        players = conn.execute('SELECT id, name, points FROM players').fetchall()
    return jsonify([dict(p) for p in players])

# プレイヤー追加
@app.route('/api/players', methods=['POST'])
def add_player():
    data = request.get_json()
    name = data.get('name')
    if not name:
        return jsonify({'error': '名前が必要です'}), 400
    try:
        with get_db() as conn:
            conn.execute('INSERT INTO players (name) VALUES (?)', (name,))
            conn.commit()
        return jsonify({'message': f'{name} を追加しました'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'その名前は既に使われています'}), 400

# プレイヤー削除
@app.route('/api/players/<int:player_id>', methods=['DELETE'])
def delete_player(player_id):
    with get_db() as conn:
        conn.execute('DELETE FROM players WHERE id = ?', (player_id,))
        conn.commit()
    return jsonify({'message': '削除しました'})

# ポイント更新（ゲーム用）
@app.route('/api/points', methods=['POST'])
def update_points():
    data = request.get_json()
    player_id = data.get('player_id')
    bet = data.get('bet', 0)
    multiplier = data.get('multiplier', 1)

    if not player_id or bet is None or multiplier is None:
        return jsonify({'error': 'パラメータ不足'}), 400

    with get_db() as conn:
        player = conn.execute('SELECT points FROM players WHERE id = ?', (player_id,)).fetchone()
        if not player:
            return jsonify({'error': 'プレイヤーが見つかりません'}), 404

        current_points = player['points']
        if bet > current_points:
            return jsonify({'error': '賭け金が足りません'}), 400

        change = bet * multiplier
        new_points = current_points - bet + change

        conn.execute(
            'INSERT INTO transactions (player_id, change) VALUES (?, ?)',
            (player_id, change)
        )
        conn.execute('UPDATE players SET points = ? WHERE id = ?', (new_points, player_id))
        conn.commit()

    return jsonify({'message': 'ポイント更新完了', 'new_points': new_points})

# ゲーム用 Undo（最新の有効なトランザクションを取り消し）
@app.route('/api/undo', methods=['POST'])
def undo():
    data = request.get_json()
    player_id = data.get('player_id')
    if not player_id:
        return jsonify({'error': 'player_idが必要です'}), 400

    with get_db() as conn:
        tx = conn.execute('''
            SELECT id, change FROM transactions
            WHERE player_id = ? AND is_valid = 1
            ORDER BY id DESC LIMIT 1
        ''', (player_id,)).fetchone()

        if not tx:
            return jsonify({'error': '取り消せる操作がありません'}), 400

        conn.execute('UPDATE transactions SET is_valid = 0 WHERE id = ?', (tx['id'],))

        total = conn.execute('''
            SELECT SUM(change) FROM transactions
            WHERE player_id = ? AND is_valid = 1
        ''', (player_id,)).fetchone()[0] or 0
        new_points = 100 + total  # 初期値は config から取るべきだが、後でフロントに合わせる
        conn.execute('UPDATE players SET points = ? WHERE id = ?', (new_points, player_id))
        conn.commit()

    return jsonify({'message': '取り消しました', 'new_points': new_points})

# 直接ポイント編集（管理用、トランザクションは記録しない）
@app.route('/api/players/<int:player_id>/points', methods=['PUT'])
def set_player_points(player_id):
    data = request.get_json()
    points = data.get('points')
    if points is None:
        return jsonify({'error': 'ポイントが必要です'}), 400
    with get_db() as conn:
        conn.execute('UPDATE players SET points = ? WHERE id = ?', (points, player_id))
        conn.commit()
    return jsonify({'message': 'ポイントを更新しました'})

# 全データ削除（次のゲーム用）
@app.route('/api/reset', methods=['POST'])
def reset():
    with get_db() as conn:
        conn.execute('DELETE FROM transactions')
        conn.execute('DELETE FROM players')
        conn.commit()
    return jsonify({'message': '全データを削除しました'})

# ポイントのみリセット（プレイヤーは残す、トランザクション削除）
@app.route('/api/reset-points', methods=['POST'])
def reset_points():
    initial = 100  # config から取得したいが、ここでは仮置き
    with get_db() as conn:
        conn.execute('DELETE FROM transactions')
        conn.execute('UPDATE players SET points = ?', (initial,))
        conn.commit()
    return jsonify({'message': 'ポイントをリセットしました'})

# ランキング用（全プレイヤー取得）
@app.route('/api/ranking', methods=['GET'])
def ranking():
    with get_db() as conn:
        players = conn.execute('SELECT id, name, points FROM players ORDER BY points DESC').fetchall()
    return jsonify([dict(p) for p in players])

@app.route('/')
def index():
    return render_template('index.html')