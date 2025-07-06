import os
import logging
import nest_asyncio
import asyncio

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# ────────────── Логирование ───────────────
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)

# ─────────────── Переменные окружения ───────────────
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # https://your-service.onrender.com/webhook
PORT = int(os.getenv("PORT", 10000))

if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("Установи переменные BOT_TOKEN и WEBHOOK_URL")

# ─────────────── Хендлеры ───────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я бот.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Список команд:\n/start\n/help")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(update.message.text)

# ─────────────── Основная логика ───────────────
async def main():
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    await application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="/webhook",
        webhook_url=WEBHOOK_URL
    )

# ─────────────── Точка входа ───────────────
if __name__ == "__main__":
    nest_asyncio.apply()  # ← исправляет ошибку event loop already running
    asyncio.get_event_loop().run_until_complete(main())