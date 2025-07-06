import os
import logging
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

# ──────────────────── Константы ────────────────────
BOT_TOKEN   = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")          # https://botgroop-6.onrender.com/webhook
PORT        = int(os.getenv("PORT", 10000))     # Render задаёт PORT

if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Нужно установить переменные окружения BOT_TOKEN и WEBHOOK_URL")

# ──────────────────── Логирование ─────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# ──────────────────── Хендлеры ─────────────────────
user_data_store = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я бот-рассыльщик.\nНапиши /help для справки.")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start – приветствие\n/help – помощь")

async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ты написал: {update.message.text}")

# ──────────────────── main() ───────────────────────
async def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Вызовет setWebhook и запустит встроенный aiohttp-сервер
    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="/webhook",
        webhook_url=WEBHOOK_URL
    )

# ──────────────────── Точка входа ──────────────────
if __name__ == "__main__":
    import asyncio
    asyncio.run(main())