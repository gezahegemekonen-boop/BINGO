import os
import logging
import asyncio
import random
from flask import Flask, request, jsonify, render_template
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, InputFile, ReplyKeyboardMarkup, BotCommand
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


@flask_app.route("/cartela", methods=["GET", "POST"])
def cartela():
    telegram_id = request.args.get("id")
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if request.method == "GET":
        return jsonify({
            "cartela": user.cartela if user else [],
            "bonus": [random.randint(1, 90) for _ in range(5)],
            "winner": str(user.telegram_id) if user and user.games_won > 0 else None
        })
    else:
        new_cartela = request.json.get("cartela")
        if user:
            user.cartela = new_cartela
            db.session.commit()
            return jsonify({"status": "updated"})
        return jsonify({"status": "error", "message": "user not found"})


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.message:
        return

    telegram_id = update.effective_user.id
    username = update.effective_user.username

    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=str(telegram_id)).first()
        if not user:
            user = User(telegram_id=str(telegram_id), username=username, balance=0, language="en")
            db.session.add(user)
            db.session.commit()

    keyboard = ReplyKeyboardMarkup([
        ["🎮 Play", "💰 Deposit"],
        ["💵 Balance", "🏧 Withdraw"],
        ["📢 Invite", "🌐 Language"],
        ["🏆 Leaderboard", "📜 My Games"]
    ], resize_keyboard=True)

    await update.message.reply_text(
        f"👋 Welcome {username or 'player'} to Arada Bingo Ethiopia!\nChoose an option below to start:",
        reply_markup=keyboard
    )

# 🩵 Generic command placeholders (so your bot never crashes)
async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎮 Starting a Bingo game soon... stay tuned!")

async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💰 Please send your transaction ID for deposit verification.")

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏧 Enter the amount you want to withdraw:")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    with flask_app.app_context():
        user = User.query.filter_by(telegram_id=telegram_id).first()
        if user:
            await update.message.reply_text(f"💳 Your balance is {user.balance} birr.")
        else:
            await update.message.reply_text("❌ You must start with /start first.")

async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    link = f"https://t.me/AradaBingoBot?start={telegram_id}"
    await update.message.reply_text(f"📢 Invite your friends to play:\n{link}")

async def language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌐 Language switching coming soon!")

async def referral_contest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏆 Referral contest details coming soon!")

async def call_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("☎️ Admin contact: +251-9XX-XXX-XXX")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏆 Leaderboard feature coming soon!")

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📊 Game summary coming soon!")

async def mycartela(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎟️ Showing your cartela... (feature coming soon)")

async def mygames(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📜 Your previous games will be shown here soon!")

async def referrals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👥 Referral list coming soon!")

async def toggle_sound(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔊 Sound toggled (simulated).")

async def report_bug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🐞 Please describe the issue, our team will check it.")

async def schedule_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🕒 Game scheduling not yet implemented.")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📢 Broadcast feature only for admins.")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📈 Admin stats coming soon.")

async def cartela_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎴 Cartela preview feature under development.")

async def handle_user_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Text commands not recognized. Use menu buttons or /help.")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ Something went wrong. Please try again.")

async def main():
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("play", play_game))
    telegram_app.add_handler(CommandHandler("deposit", deposit))
    telegram_app.add_handler(CommandHandler("withdraw", withdraw))
    telegram_app.add_handler(CommandHandler("balance", balance))
    telegram_app.add_handler(CommandHandler("invite", invite))
    telegram_app.add_handler(CommandHandler("language", language))
    telegram_app.add_handler(CommandHandler("referral_contest", referral_contest))
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

    telegram_app.add_handler(MessageHandler(filters.TEXT, handle_user_input))
    telegram_app.add_error_handler(error_handler)

    # Set Telegram menu commands
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
