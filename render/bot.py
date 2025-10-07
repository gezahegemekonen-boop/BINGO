import os
import logging
import asyncio
import random
from flask import Flask, request, jsonify, render_template
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, InputFile, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
from sqlalchemy import func
from database import db, init_db
from models import User, Transaction, Game, Lobby, ScheduledGame, GameParticipant
from utils.is_valid_tx_id import is_valid_tx_id
from utils.referral_link import referral_link
from utils.toggle_language import toggle_language
from game_logic import BingoGame

game = BingoGame(game_id=1)
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://arada-bingo.onrender.com")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://arada-bingo.onrender.com/cartela")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "364344971").split(",")]

flask_app = Flask(__name__, template_folder="templates", static_folder="static")
flask_app.secret_key = os.getenv("FLASK_SECRET", "bot_secret")

try:
    init_db(flask_app)
except RuntimeError:
    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///arada.db"
    flask_app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(flask_app)

telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

# --- Flask routes ---
@flask_app.route("/cartela", methods=["GET", "POST"])
def cartela():
    telegram_id = request.args.get("id")
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if request.method == "GET":
        return jsonify({
            "cartela": user.cartela,
            "bonus": [random.randint(1, 90) for _ in range(5)],
            "winner": str(user.telegram_id) if user.games_won > 0 else None
        })
    else:
        new_cartela = request.json.get("cartela")
        user.cartela = new_cartela
        db.session.commit()
        return jsonify({"status": "updated"})

@flask_app.route("/admin/dashboard")
def admin_dashboard():
    pending_deposits = Transaction.query.filter_by(type="deposit", status="pending").all()
    pending_withdrawals = Transaction.query.filter_by(type="withdraw", status="pending").all()
    games = Game.query.order_by(Game.created_at.desc()).limit(10).all()
    players = User.query.order_by(User.created_at.desc()).limit(10).all()
    leaderboard = game.get_leaderboard()
    summary = game.summary()
    users = {u.id: u for u in User.query.all()}
    return render_template("admin_dashboard.html",
        pending_deposits=pending_deposits,
        pending_withdrawals=pending_withdrawals,
        games=games,
        players=players,
        leaderboard=leaderboard,
        summary=summary,
        users=users
    )

@flask_app.route("/admin/approve_deposit", methods=["POST"])
def approve_deposit():
    tx_id = request.form.get("tx_id")
    amount = int(request.form.get("amount"))
    user_id = int(request.form.get("user_id"))
    tx = Transaction.query.get(tx_id)
    user = User.query.get(user_id)
    if tx and user:
        tx.status = "approved"
        tx.amount = amount
        user.balance += amount
        tx.approved_by = "admin"
        tx.approval_note = "manual approval"
        db.session.commit()
    return jsonify({"status": "approved"})

@flask_app.route("/admin/approve_withdrawal", methods=["POST"])
def approve_withdrawal():
    tx_id = request.form.get("tx_id")
    tx = Transaction.query.get(tx_id)
    if tx and tx.status == "pending":
        tx.status = "approved"
        tx.approved_by = "admin"
        tx.approval_note = request.form.get("note", "")
        db.session.commit()
    return jsonify({"status": "approved"})

@flask_app.route("/admin/payout_winner", methods=["POST"])
def payout_winner():
    winner_id = int(request.form.get("winner_id"))
    amount = float(request.form.get("amount"))
    user = User.query.get(winner_id)
    if user:
        user.balance += amount
        tx = Transaction(
            user_id=user.id,
            type="bingo_win",
            amount=amount,
            status="approved",
            reason="Manual payout from dashboard",
            approved_by="admin"
        )
        db.session.add(tx)
        db.session.commit()
        return jsonify({"status": "paid"})
    return jsonify({"status": "error"})

LANGUAGE_MAP = { ... }  # Keep your bilingual dictionary here

def get_lang(context, fallback="en"):
    lang_code = context.chat_data.get("language", fallback)
    return LANGUAGE_MAP.get(lang_code, LANGUAGE_MAP["en"])

# --- Command handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    args = context.args
    referral_telegram_id = int(args[0]) if args and args[0].isdigit() else None
    telegram_id = update.effective_user.id
    username = update.effective_user.username

    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=str(telegram_id)).first()
        if not user:
            user = User(telegram_id=str(telegram_id), username=username, balance=0, language="en")
            db.session.add(user)
            db.session.commit()
            if referral_telegram_id and referral_telegram_id != telegram_id:
                referrer = User.query.filter_by(telegram_id=str(referral_telegram_id)).first()
                if referrer:
                    user.referrer_id = referrer.id
                    db.session.commit()

        user_language = user.language

    context.chat_data["language"] = user_language
    lang = get_lang(context)
    keyboard = ReplyKeyboardMarkup([
        [lang["play"], lang["deposit"]],
        [lang["balance"], lang["withdraw"]],
        [lang["invite"], lang["language"]],
        [lang["summary"], lang["leaderboard"]],
        [lang["mycartela"], lang["mygames"]],
        [lang["referrals"], lang["toggle_sound"]],
        [lang["report_bug"], lang["call"]]
    ], resize_keyboard=True)
    await update.message.reply_text(lang["welcome"], reply_markup=keyboard)

# ... (all other handler functions as in your version)

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    telegram_id = str(update.effective_user.id)
    text = update.message.text.strip()

    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            await update.message.reply_text("❌ You must start the bot first using /start.")
            return

        if text.startswith("edit:"):
            user.cartela = text.replace("edit:", "").strip()
            db.session.commit()
            await update.message.reply_text("✅ Cartela updated.")
            return

        if context.chat_data and "deposit_method" in context.chat_data:
            method = context.chat_data.pop("deposit_method", None)
            if not is_valid_tx_id(text):
                await update.message.reply_text("❌ Invalid transaction ID.")
                return
            tx = Transaction(user_id=user.id, type="deposit", amount=0, method=method,
                             status="pending", reference=text)
            db.session.add(tx)
            db.session.commit()
            await update.message.reply_text("✅ Transaction received. Awaiting approval.")
            return

        try:
            amount = int(text)
            if amount <= 0 or amount > user.balance:
                await update.message.reply_text("❌ Invalid amount or insufficient balance.")
                return
            tx = Transaction(user_id=user.id, type="withdraw", amount=amount, status="pending")
            db.session.add(tx)
            db.session.commit()
            await update.message.reply_text(f"✅ Withdrawal request for {amount} birr submitted.")
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ Something went wrong. Please try again.")

from telegram import BotCommand

async def main():
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("deposit", deposit))
    telegram_app.add_handler(CommandHandler("withdraw", withdraw))
    telegram_app.add_handler(CommandHandler("balance", balance))
    telegram_app.add_handler(CommandHandler("referral_contest", referral_contest))
    telegram_app.add_handler(CommandHandler("invite", invite))
    telegram_app.add_handler(CommandHandler("language", language))
    telegram_app.add_handler(CommandHandler("play", play_game))
    telegram_app.add_handler(CommandHandler("call", call_number))
    telegram_app.add_handler(CommandHandler("leaderboard", leaderboard))
    telegram_app.add_handler(CommandHandler("summary", summary))
    telegram_app.add_handler(CommandHandler("mycartela", mycartela))
    telegram_app.add_handler(CommandHandler("mygames", mygames))
    telegram_app.add_handler(CommandHandler("referrals", referrals))
    telegram_app.add_handler(CommandHandler("toggle_sound", toggle_sound))
    telegram_app.add_handler(CommandHandler("report_bug", report_bug))
    telegram_app.add_handler(CommandHandler("schedule_game", schedule_game))
    telegram_app.add_handler(CommandHandler("broadcast", admin_broadcast))
    telegram_app.add_handler(CommandHandler("adminstats", admin_stats))
    telegram_app.add_handler(CommandHandler("cartela_preview", cartela_preview))

    telegram_app.add_handler(CallbackQueryHandler(toggle_language, pattern="toggle_lang"))
    telegram_app.add_handler(MessageHandler(filters.TEXT, handle_user_input))
    telegram_app.add_error_handler(error_handler)

    logging.info("✅ Arada Bingo Ethiopia bot is starting...")

    flask_app.app_context().push()

    commands = [
        BotCommand("start", "Start the game"),
        BotCommand("play", "Play Bingo"),
        BotCommand("withdraw", "Withdraw balance"),
        BotCommand("balance", "Check balance"),
        BotCommand("deposit", "Deposit funds"),
        BotCommand("language", "Choose language"),
        BotCommand("convert", "Convert coins to wallet"),
        BotCommand("transaction", "View transaction history"),
        BotCommand("game", "View game history"),
        BotCommand("instruction", "Game instructions"),
        BotCommand("invite", "Invite friends to play Bingo")
    ]
    await telegram_app.bot.set_my_commands(commands)

    await telegram_app.bot.delete_webhook(drop_pending_updates=True)
    await telegram_app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
