# app.py
from flask import Flask, request, jsonify
from database import db, init_db
from models import User, Game, GameParticipant, Transaction
from game_logic import BingoGame
from datetime import datetime
import os

# 🔧 Flask App Setup
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "arada_secret_key")

# 🧠 Database Initialization
try:
    init_db(app)
except RuntimeError as e:
    print(f"❌ Database setup error: {e}")
    # Fallback to SQLite for local development
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///arada.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

# 🎮 In-memory game store
active_games = {}

# -------------------- GAME ROUTES --------------------

@app.route("/game/create", methods=["POST"])
def create_game():
    data = request.json
    entry_price = data.get("entry_price", 10)
    game = BingoGame(game_id=len(active_games) + 1, entry_price=entry_price)
    active_games[game.game_id] = game
    return jsonify({"game_id": game.game_id})

@app.route("/game/join", methods=["POST"])
def join_game():
    data = request.json
    game_id = data.get("game_id")
    user_id = data.get("user_id")
    cartela_number = data.get("cartela_number")

    game = active_games.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    board = game.add_player(user_id, cartela_number)
    return jsonify({"cartela": board})

@app.route("/game/call/<int:game_id>", methods=["POST"])
def call_number(game_id):
    game = active_games.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    result = game.call_number()
    return jsonify(result)

@app.route("/game/mark", methods=["POST"])
def mark_number():
    data = request.json
    game_id = data.get("game_id")
    user_id = data.get("user_id")
    number = data.get("number")

    game = active_games.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    updated = game.mark_number(user_id, number)
    win, message = game.check_winner(user_id)

    if win:
        game.end_game(user_id)

    return jsonify({
        "marked": updated,
        "win": win,
        "message": message
    })

# -------------------- DEPOSIT & WITHDRAW --------------------

@app.route("/deposit", methods=["POST"])
def deposit():
    data = request.json
    user_id = data.get("user_id")
    amount = data.get("amount")
    method = data.get("method")
    phone = data.get("phone")
    code = data.get("code")

    if amount < 30:
        return jsonify({"error": "Minimum deposit is 30 ETB"}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    tx = Transaction(
        user_id=user.id,
        type="deposit",
        amount=amount,
        method=method,
        deposit_phone=phone,
        transaction_id=code,
        status="completed",
        created_at=datetime.utcnow(),
        completed_at=datetime.utcnow()
    )
    db.session.add(tx)
    user.balance += amount
    db.session.commit()

    return jsonify({"message": "Deposit confirmed", "new_balance": user.balance})

@app.route("/withdraw", methods=["POST"])
def withdraw():
    data = request.json
    user_id = data.get("user_id")
    amount = data.get("amount")
    phone = data.get("phone")

    user = User.query.get(user_id)
    if not user or user.balance < amount:
        return jsonify({"error": "Insufficient balance"}), 400

    tx = Transaction(
        user_id=user.id,
        type="withdraw",
        amount=amount,
        withdrawal_phone=phone,
        withdrawal_status="pending",
        status="pending",
        created_at=datetime.utcnow()
    )
    db.session.add(tx)
    db.session.commit()

    return jsonify({"message": "Withdrawal request submitted."})

# -------------------- ADMIN ROUTES --------------------

@app.route("/admin/transactions", methods=["GET"])
def admin_transactions():
    txs = Transaction.query.order_by(Transaction.created_at.desc()).limit(50).all()
    data = []
    for tx in txs:
        user = User.query.get(tx.user_id)
        data.append({
            "id": tx.id,
            "user": user.username if user else "unknown",
            "type": tx.type,
            "amount": tx.amount,
            "method": tx.method,
            "reference": tx.reference,
            "status": tx.status,
            "created_at": tx.created_at.isoformat()
        })
    return jsonify(data)

@app.route("/admin/approve/<int:tx_id>", methods=["POST"])
def approve_transaction(tx_id):
    tx = Transaction.query.get(tx_id)
    if not tx or tx.status != "pending":
        return jsonify({"error": "Transaction not found or already processed"}), 400

    tx.status = "approved"
    tx.completed_at = datetime.utcnow()

    user = User.query.get(tx.user_id)
    if tx.type == "deposit":
        user.balance += tx.amount
    elif tx.type == "withdraw":
        user.balance -= tx.amount

    db.session.commit()
    return jsonify({"message": "Transaction approved."})

@app.route("/admin/reject/<int:tx_id>", methods=["POST"])
def reject_transaction(tx_id):
    tx = Transaction.query.get(tx_id)
    if not tx or tx.status != "pending":
        return jsonify({"error": "Transaction not found or already processed"}), 400

    tx.status = "rejected"
    db.session.commit()
    return jsonify({"message": "Transaction rejected."})

# -------------------- LEADERBOARD --------------------

@app.route("/leaderboard", methods=["GET"])
def leaderboard():
    top_users = User.query.order_by(User.games_won.desc(), User.balance.desc()).limit(10).all()
    data = [
        {
            "username": user.username,
            "wins": user.games_won,
            "balance": user.balance
        }
        for user in top_users
    ]
    return jsonify(data)

# -------------------- START SERVER --------------------

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=int(os.getenv("FLASK_PORT", 5000)), debug=True)
