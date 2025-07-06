import os
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
import logging
import asyncio

# Включаем логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Получаем переменные окружения
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # Пример: https://botgroop-6.onrender.com/webhook

if not BOT_TOKEN or not WEBHOOK_URL:
    raise ValueError("Необходимо установить переменные окружения BOT_TOKEN и WEBHOOK_URL")

# Flask-приложение
flask_app = Flask(__name__)

# Объявляем объект бота глобально, чтобы использовать в обработчике Flask
bot_app = None

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Привет! Я бот по инкрустации. Напиши мне что-нибудь!")

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛠 Доступные команды:\n/start — начать\n/help — помощь")

# Ответ на любое текстовое сообщение
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"Ты написал: {update.message.text}")

# Обработчик webhook-запроса от Telegram
@flask_app.post("/webhook")
async def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), bot_app.bot)
        await bot_app.process_update(update)
        return "ok", 200

# Асинхронный запуск приложения и установка webhook
async def main():
    global bot_app
    bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Обработчики команд и сообщений
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    # Устанавливаем Webhook
    await bot_app.bot.set_webhook(url=WEBHOOK_URL)
    print("✅ Webhook установлен!")

# Точка входа
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "event loop is already running" in str(e):
            # Обход ошибки, характерной для Render
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
        else:
            raise