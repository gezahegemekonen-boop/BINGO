# ============================================================
# 🎯 Arada Bingo Telegram Bot — Clean Version
# ============================================================

import os
import logging
import nest_asyncio
import asyncio
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo, InputFile, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from flask import Flask
from models import db, User, Game, GameParticipant, Transaction, ScheduledGame
from sqlalchemy import func
from utils import get_lang, referral_link, is_valid_tx_id
import game

# ============================================================
# 🧩 Basic Configuration
# ============================================================

# Use your Render live URL here:
WEBHOOK_URL = "https://bingo-pgil.onrender.com"

TOKEN = os.environ.get("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")

# Admin IDs — replace with your Telegram user ID(s)
ADMIN_IDS = [123456789]  # Example: [7247278760]

# Flask app
flask_app = Flask(__name__)
flask_app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///bingo.db")
db.init_app(flask_app)

# Telegram bot app
telegram_app = Application.builder().token(TOKEN).build()

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ============================================================
# 🧠 COMMAND HANDLERS
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Play", callback_data="play_game")],
        [InlineKeyboardButton("💰 Deposit", callback_data="deposit")],
        [InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")],
        [InlineKeyboardButton("🌐 Language", callback_data="language")]
    ])
    await update.message.reply_text(lang["welcome"], reply_markup=keyboard)


async def deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    context.chat_data["deposit_method"] = "cbe_birr"
    await update.message.reply_text(lang["deposit"])


async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    await update.message.reply_text(lang["withdraw"])


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    user = User.query.filter_by(telegram_id=telegram_id).first()
    if user:
        lang = get_lang(context)
        await update.message.reply_text(f"{lang['balance']}: {user.balance} birr")
    else:
        await update.message.reply_text("❌ You must start the bot first using /start.")


async def referral_contest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_lang(context)
    telegram_id = str(update.effective_user.id)
    link = referral_link(telegram_id)
    await update.message.reply_text(f"{lang['referral_contest']}:\n{link}")


async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = str(update.effective_user.id)
    lang = get_lang(context)
    link = referral_link(telegram_id)
    await update.message.reply_text(f"{lang['invite']}: {link}")


async def language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌐 Choose your language:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🇬🇧 English", callback_data="toggle_lang:en")],
            [InlineKeyboardButton("🇪🇹 አማርኛ", callback_data="toggle_lang:am")]
        ])
    )


async def play_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.effective_user.id
    lang = get_lang(context)
    await update.message.reply_text(
        f"{lang['play']}...",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🧩 Open Game WebApp",
                web_app=WebAppInfo(url=f"{WEBHOOK_URL}?id={telegram_id}")
            )]
        ])
    )
    game.start_game(chat_id=update.effective_chat.id, context=context)


async def call_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = game.call_number(chat_id=update.effective_chat.id, context=context)
    if result:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"🎱 {result['formatted']}")
        try:
            await context.bot.send_voice(chat_id=update.effective_chat.id, voice=InputFile("audio/number_call_am.ogg"))
        except Exception:
            pass
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ Game finished!")

# ============================================================
# 💬 HANDLE USER INPUT
# ============================================================

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

        # ✅ Edit cartela
        if text.startswith("edit:"):
            new_cartela = text.replace("edit:", "").strip()
            user.cartela = new_cartela
            db.session.commit()
            await update.message.reply_text("✅ Cartela updated.")
            return

        # 💰 Handle deposit
        if context.chat_data.get("deposit_method"):
            method = context.chat_data["deposit_method"]
            if not is_valid_tx_id(text):
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
            return

        # 💸 Handle withdrawal
        try:
            amount = int(text)
            if amount <= 0 or amount > user.balance:
                await update.message.reply_text("❌ Invalid amount or insufficient balance.")
                return

            tx = Transaction(
                user_id=user.id,
                type="withdraw",
                amount=amount,
                status="pending"
            )
            db.session.add(tx)
            db.session.commit()
            await update.message.reply_text(f"✅ Withdrawal request for {amount} birr submitted.")
        except ValueError:
            await update.message.reply_text("❌ Please enter a valid number.")


# ============================================================
# ⚠️ ERROR HANDLER
# ============================================================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.error("Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("⚠️ Something went wrong. Please try again.")


# ============================================================
# 🚀 MAIN FUNCTION
# ============================================================

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

    telegram_app.add_handler(MessageHandler(filters.TEXT, handle_user_input))
    telegram_app.add_error_handler(error_handler)

    logging.info("✅ Arada Bingo Ethiopia bot is starting...")

    flask_app.app_context().push()

    # 🧩 Telegram commands
    commands = [
        BotCommand("start", "Start the game"),
        BotCommand("play", "Play Bingo"),
        BotCommand("withdraw", "Withdraw balance"),
        BotCommand("balance", "Check balance"),
        BotCommand("deposit", "Deposit funds"),
        BotCommand("language", "Choose language"),
        BotCommand("invite", "Invite friends to play Bingo")
    ]
    await telegram_app.bot.set_my_commands(commands)

    # 🪝 Setup webhook
    await telegram_app.bot.delete_webhook(drop_pending_updates=True)
    await telegram_app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        webhook_url=f"{WEBHOOK_URL}/webhook"
    )


if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    import asyncio
    asyncio.get_event_loop().run_until_complete(main())
