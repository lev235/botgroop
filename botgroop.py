import os
import re
import asyncio
import logging
import nest_asyncio
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from telegram.error import TelegramError

nest_asyncio.apply()                          # ← патчим loop для Render

BOT_TOKEN   = os.getenv("BOT_TOKEN")
PORT        = int(os.getenv("PORT", 8443))    # Render передаёт PORT автоматически
WEBHOOK_URL = os.getenv("WEBHOOK_URL")        # https://…onrender.com/webhook
URL_PATH    = "webhook"                       # то, что после «/» в WEBHOOK_URL

# ──────────── вспом-функции ──────────────────────────────────────────────────
LINK_RE = re.compile(r"(https?://t\.me/[^\s]+|@[\w\d_]+)", re.IGNORECASE)
def extract_targets(text: str) -> list[str]:
    links = LINK_RE.findall(text)
    out = []
    for raw in links:
        if raw.startswith("@"):
            out.append(raw)
        else:
            tail = raw.rsplit("/", 1)[-1]
            out.append(raw if tail.startswith("+") else "@" + tail)
    return out

# хранение данных между сообщениями (в RAM)
user_data_store: dict[int, dict] = {}

# ──────────── handlers ───────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот-рассыльщик.\n"
        "1) пришли фото/текст\n"
        "2) /addgroups <@ссылки или t.me/…>\n"
        "3) /send — отправка"
    )

async def add_groups(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid   = update.effective_user.id
    links = extract_targets(update.message.text)
    if not links:
        await update.message.reply_text("⚠️ Не нашёл групп.")
        return

    store = user_data_store.setdefault(uid, {"photos": [], "text": "", "groups": []})
    ok, bad = [], []
    for tgt in links:
        try:
            chat = await (ctx.bot.join_chat(tgt) if tgt.startswith("https://t.me/+")
                          else ctx.bot.get_chat(tgt))
            member = await ctx.bot.get_chat_member(chat.id, ctx.bot.id)
            if member.status in ("left", "kicked"):
                raise ValueError("бот не в группе")
        except TelegramError as e:
            bad.append(f"{tgt} ({e.message})")
            continue
        except Exception as e:
            bad.append(f"{tgt} ({e})")
            continue
        if chat.id not in store["groups"]:
            store["groups"].append(chat.id)
        ok.append(chat.title or chat.username or str(chat.id))

    msg = []
    if ok:  msg.append("✅ Добавил: " + ", ".join(ok))
    if bad: msg.append("⚠️ Не смог: " + ", ".join(bad))
    await update.message.reply_text("\n".join(msg))

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    store = user_data_store.setdefault(uid, {"photos": [], "text": "", "groups": []})
    store["photos"].append(update.message.photo[-1].file_id)
    await update.message.reply_text("📸 Фото сохранено.")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith("/"):
        return
    uid = update.effective_user.id
    store = user_data_store.setdefault(uid, {"photos": [], "text": "", "groups": []})
    store["text"] = update.message.text
    await update.message.reply_text("✏️ Текст сохранён.")

async def send_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    data = user_data_store.get(uid)
    if not data or (not data["photos"] and not data["text"]):
        await update.message.reply_text("⚠️ Нет контента.")
        return
    if not data["groups"]:
        await update.message.reply_text("⚠️ Сначала /addgroups.")
        return

    errors = []
    for gid in data["groups"]:
        try:
            if len(data["photos"]) > 1:
                media = [InputMediaPhoto(p) for p in data["photos"]]
                media[0].caption = data["text"]
                await ctx.bot.send_media_group(gid, media)
            else:
                await ctx.bot.send_photo(gid, photo=data["photos"][0], caption=data["text"])
        except TelegramError as e:
            errors.append(f"{gid}: {e.message}")
        except Exception as e:
            errors.append(f"{gid}: {e}")

    await update.message.reply_text(
        "✅ Разослано!" if not errors else "Часть групп не приняла:\n" + "\n".join(errors)
    )
    user_data_store.pop(uid, None)

# ──────────── main ───────────────────────────────────────────────────────────
async def main():
    logging.basicConfig(level=logging.INFO)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("addgroups",  add_groups))
    app.add_handler(CommandHandler("send",       send_post))
    app.add_handler(MessageHandler(filters.PHOTO,                 handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # 1) регистрируем webhook (делать до run_webhook)
    await app.bot.set_webhook(WEBHOOK_URL)
    print("🤖 Webhook зарегистрирован:", WEBHOOK_URL)

    # 2) запускаем aiohttp-сервер PTB
    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=URL_PATH,      # ← правильное имя параметра!
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    asyncio.run(main())