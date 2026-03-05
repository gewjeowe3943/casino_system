from flask import Flask, request, jsonify, render_template
import sqlite3
import os

app = Flask(__name__)
DATABASE = 'casino.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # プレイヤーテーブル（ポイントは最新状態を保持）
        conn.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                points INTEGER DEFAULT 5
            )
        ''')
        # トランザクションテーブル（履歴とUndo用）
        conn.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                change INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_valid BOOLEAN DEFAULT 1,
                FOREIGN KEY(player_id) REFERENCES players(id)
            )
        ''')
        conn.commit()

init_db()

# 全プレイヤー取得
@app.route('/api/players', methods=['GET'])
def get_players():
    with get_db() as conn:
        players = conn.execute('SELECT id, name, points FROM players').fetchall()
    return jsonify([dict(p) for p in players])

# プレイヤー追加（名前のみ）
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

# ポイント更新
@app.route('/api/points', methods=['POST'])
def update_points():
    data = request.get_json()
    player_id = data.get('player_id')
    bet = data.get('bet', 0)
    multiplier = data.get('multiplier', 1)

    if not player_id or bet is None or multiplier is None:
        return jsonify({'error': 'パラメータ不足'}), 400

    with get_db() as conn:
        # 現在のポイントを取得
        player = conn.execute('SELECT points FROM players WHERE id = ?', (player_id,)).fetchone()
        if not player:
            return jsonify({'error': 'プレイヤーが見つかりません'}), 404

        current_points = player['points']
        if bet > current_points:
            return jsonify({'error': '賭け金が足りません'}), 400

        # 新ポイントの計算（賭け金は失い、倍率×賭け金を得る）
        change = bet * multiplier
        new_points = current_points - bet + change

        # トランザクションを挿入
        conn.execute(
            'INSERT INTO transactions (player_id, change) VALUES (?, ?)',
            (player_id, change)
        )
        # プレイヤーのポイントを更新
        conn.execute('UPDATE players SET points = ? WHERE id = ?', (new_points, player_id))
        conn.commit()

    return jsonify({'message': 'ポイント更新完了', 'new_points': new_points})

# 最新の操作を取り消し（Undo）
@app.route('/api/undo', methods=['POST'])
def undo():
    data = request.get_json()
    player_id = data.get('player_id')  # どのプレイヤーの操作を取り消すか指定

    if not player_id:
        return jsonify({'error': 'player_idが必要です'}), 400

    with get_db() as conn:
        # そのプレイヤーの最新の有効なトランザクションを取得
        tx = conn.execute('''
            SELECT id, change FROM transactions
            WHERE player_id = ? AND is_valid = 1
            ORDER BY id DESC LIMIT 1
        ''', (player_id,)).fetchone()

        if not tx:
            return jsonify({'error': '取り消せる操作がありません'}), 400

        # トランザクションを無効化
        conn.execute('UPDATE transactions SET is_valid = 0 WHERE id = ?', (tx['id'],))

        # プレイヤーのポイントを再計算（有効なトランザクションのみ合計 + 初期値5）
        total = conn.execute('''
            SELECT SUM(change) FROM transactions
            WHERE player_id = ? AND is_valid = 1
        ''', (player_id,)).fetchone()[0] or 0
        new_points = 5 + total  # 初期ポイント5を基準
        conn.execute('UPDATE players SET points = ? WHERE id = ?', (new_points, player_id))
        conn.commit()

    return jsonify({'message': '取り消しました', 'new_points': new_points})

# ランキング（上位3名）
@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    with get_db() as conn:
        top = conn.execute('''
            SELECT name, points FROM players
            ORDER BY points DESC LIMIT 3
        ''').fetchall()
    return jsonify([dict(t) for t in top])

# ゲーム終了（全プレイヤーのポイントを5にリセット）
@app.route('/api/reset', methods=['POST'])
def reset():
    with get_db() as conn:
        conn.execute('DELETE FROM transactions')  # 履歴もクリア（必要に応じて）
        conn.execute('UPDATE players SET points = 5')
        conn.commit()
    return jsonify({'message': 'リセット完了'})

# クライアントHTMLを配信
@app.route('/')
def index():
    return render_template('index.html')