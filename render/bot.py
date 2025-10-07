import os
import logging
import asyncio
import random
from flask import Flask, request, jsonify, render_template
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo, InputFile, ReplyKeyboardMarkup, BotCommand
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from sqlalchemy import func
from database import db, init_db
from models import User, Transaction, Game, Lobby, ScheduledGame, GameParticipant
from utils.is_valid_tx_id import is_valid_tx_id
from utils.referral_link import referral_link
from utils.toggle_language import toggle_language
from game_logic import BingoGame

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
game = BingoGame(game_id=1)

# ------------------ Flask Routes ------------------

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

LANGUAGE_MAP = {
    "en": {
        "welcome": "🎉 Welcome to Arada Bingo!",
        "deposit": "💰 Please send your deposit transaction ID.",
        "withdraw": "🏧 Enter the amount you want to withdraw:",
        "balance": "💳 Your current balance",
        "play": "🎮 Play Bingo",
        "invite": "🎁 Invite your friends!",
        "leaderboard": "🏆 Leaderboard",
        "summary": "📊 Game Summary",
        "mycartela": "🧩 My Cartela",
        "mygames": "📜 My Games",
        "referrals": "👥 Referrals",
        "toggle_sound": "🔈 Toggle Sound",
        "report_bug": "🐞 Report Bug",
        "schedule_game": "🗓 Schedule Game",
        "broadcast": "📢 Broadcast Message",
        "adminstats": "📈 Admin Stats",
        "cartela_preview": "🧾 Cartela Preview",
    },
    "am": {
        "welcome": "🎉 እንኳን ወደ አራዳ ቢንጎ በደህና መጡ!",
        "deposit": "💰 የተጣለውን የሂሳብ መለያ ቁጥር ያስገቡ።",
        "withdraw": "🏧 የሚያወጡትን መጠን ያስገቡ።",
        "balance": "💳 ያለዎት መጠን",
        "play": "🎮 ቢንጎ ይጫወቱ",
        "invite": "🎁 ጓደኞችዎን ይጋብዙ!",
        "leaderboard": "🏆 የአሸናፊዎች ዝርዝር",
        "summary": "📊 የጨዋታ ማጠቃለያ",
        "mycartela": "🧩 ካርቴላዬ",
        "mygames": "📜 ጨዋታዬ",
        "referrals": "👥 የተጠቃሚ መጠቀሚያዎች",
        "toggle_sound": "🔈 ድምፅ ተቆልቋይ",
        "report_bug": "🐞 ችግኝ ያሳውቁ",
        "schedule_game": "🗓 ጨዋታ ያቅዱ",
        "broadcast": "📢 መልዕክት ይላኩ",
        "adminstats": "📈 የአስተዳዳሪ እይታ",
        "cartela_preview": "🧾 የካርቴላ ቅድመ እይታ",
    },
}

def get_lang(context, fallback="en"):
    lang_code = context.chat_data.get("language", fallback)
    return LANGUAGE_MAP.get(lang_code, LANGUAGE_MAP["en"])

# ------------------ Telegram Command Handlers ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    first_name = update.effective_user.first_name or "Player"
    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            user = User(telegram_id=telegram_id, name=first_name, balance=0)
            db.session.add(user)
            db.session.commit()

    lang = get_lang(context)
    keyboard = [
        [InlineKeyboardButton(lang["play"], callback_data="play")],
        [InlineKeyboardButton(lang["deposit"], callback_data="deposit"),
         InlineKeyboardButton(lang["withdraw"], callback_data="withdraw")],
        [InlineKeyboardButton(lang["balance"], callback_data="balance"),
         InlineKeyboardButton(lang["invite"], callback_data="invite")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(lang["welcome"], reply_markup=reply_markup)


async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.chat_data["deposit_method"] = "manual"
    lang = get_lang(context)
    await update.message.reply_text(lang["deposit"])


async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    await update.message.reply_text(lang["withdraw"])


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if user:
            lang = get_lang(context)
            await update.message.reply_text(f"{lang['balance']}: {user.balance} birr")
        else:
            await update.message.reply_text("❌ Please use /start first.")


async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            await update.message.reply_text("❌ You must start first with /start.")
            return

        if user.balance < 5:
            await update.message.reply_text("❌ You need at least 5 birr to play.")
            return

        user.balance -= 5
        db.session.commit()
        await update.message.reply_text("🎮 You joined the Bingo game! Good luck!")


async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    invite_link = f"https://t.me/{context.bot.username}?start={telegram_id}"
    await update.message.reply_text(
        f"🎁 Share this link with friends to invite them:\n\n{invite_link}"
    )


async def transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            await update.message.reply_text("❌ You must /start first.")
            return

        txs = Transaction.query.filter_by(user_id=user.id).order_by(Transaction.created_at.desc()).limit(5).all()
        if not txs:
            await update.message.reply_text("📭 No recent transactions.")
            return

        msg = "📜 *Recent Transactions:*\n\n"
        for tx in txs:
            msg += f"{tx.type.capitalize()} — {tx.amount} birr — {tx.status}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")


async def game_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            await update.message.reply_text("❌ Please /start first.")
            return

        games = Game.query.filter(Game.players.contains(user)).order_by(Game.created_at.desc()).limit(5).all()
        if not games:
            await update.message.reply_text("📭 No games played yet.")
            return

        msg = "🎮 *Your Recent Games:*\n\n"
        for g in games:
            msg += f"Game #{g.id} — Winner: {g.winner_id or 'None'} — {g.status}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")


async def instruction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 *How to Play Bingo:*\n\n"
        "1️⃣ Deposit funds using /deposit.\n"
        "2️⃣ Join a game with /play.\n"
        "3️⃣ When numbers are called, mark them on your card.\n"
        "4️⃣ First to complete a row or full card wins!\n"
        "🏆 Good luck!"
    )


async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 Conversion feature coming soon...")


async def language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en"),
         InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="lang_am")]
    ]
    await update.message.reply_text("🌐 Choose your language:", reply_markup=InlineKeyboardMarkup(keyboard))

# ------------------ Message + Error Handlers ------------------

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    text = update.message.text.strip()
    telegram_id = str(update.effective_user.id)

    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if not user:
            await update.message.reply_text("❌ You must start the bot first using /start.")
            return

        # Example handling of manual deposit transaction IDs
        if "deposit_method" in context.chat_data:
            method = context.chat_data["deposit_method"]
            if len(text) < 6:
                await update.message.reply_text("❌ Invalid transaction ID. Please try again.")
                return

            tx = Transaction(
                user_id=user.id,
                type="deposit",
                amount=0,
                method=method,
                status="pending",
                reference=text
            )
            db.session.add(tx)
            db.session.commit()
            await update.message.reply_text("✅ Transaction received. Awaiting admin approval.")
            del context.chat_data["deposit_method"]
            return

        await update.message.reply_text("💬 Please use the available commands to interact with the bot.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("⚠️ Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ Something went wrong. Please try again later.")


# ------------------ Main Bot Setup ------------------

from telegram import BotCommand

async def main():
    # Register command handlers
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("play", play_game))
    telegram_app.add_handler(CommandHandler("deposit", deposit))
    telegram_app.add_handler(CommandHandler("withdraw", withdraw))
    telegram_app.add_handler(CommandHandler("balance", balance))
    telegram_app.add_handler(CommandHandler("invite", invite))
    telegram_app.add_handler(CommandHandler("transaction", transaction))
    telegram_app.add_handler(CommandHandler("game", game_history))
    telegram_app.add_handler(CommandHandler("instruction", instruction))
    telegram_app.add_handler(CommandHandler("convert", convert))
    telegram_app.add_handler(CommandHandler("language", language))

    # Callback + message + error
    telegram_app.add_handler(CallbackQueryHandler(language, pattern="lang_"))
    telegram_app.add_handler(MessageHandler(filters.TEXT, handle_user_input))
    telegram_app.add_error_handler(error_handler)

    # Set visible Telegram bot commands
    commands = [
        BotCommand("start", "Start the game"),
        BotCommand("play", "Play Bingo"),
        BotCommand("deposit", "Deposit funds"),
        BotCommand("withdraw", "Withdraw balance"),
        BotCommand("balance", "Check balance"),
        BotCommand("invite", "Invite friends to play Bingo"),
        BotCommand("transaction", "View transaction history"),
        BotCommand("game", "View game history"),
        BotCommand("instruction", "Game instructions"),
        BotCommand("convert", "Convert coins to wallet"),
        BotCommand("language", "Choose language")
    ]
    await telegram_app.bot.set_my_commands(commands)

    # Flask context setup
    flask_app.app_context().push()
    logging.info("✅ Arada Bingo Ethiopia bot is starting...")

    # Start webhook server
    await telegram_app.bot.set_webhook(WEBHOOK_URL)
await telegram_app.run_polling()

    )
# ------------------ Entry Point ------------------
if __name__ == "__main__":
    import nest_asyncio
    import asyncio

    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
