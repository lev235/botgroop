import os
import re
import asyncio
import logging

from telegram import Update, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError
import nest_asyncio

nest_asyncio.apply()

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # должен оканчиваться на /webhook
PORT = int(os.getenv("PORT", 8443))

user_data_store: dict[int, dict] = {}
LINK_RE = re.compile(r"(https?://t\.me/[^\s]+|@[\w\d_]+)", re.IGNORECASE)


def extract_targets(text: str) -> list[str]:
    links = LINK_RE.findall(text)
    normalized = []
    for raw in links:
        if raw.startswith("@"):
            normalized.append(raw)
        else:
            tail = raw.rsplit("/", 1)[-1]
            normalized.append(raw if tail.startswith("+") else "@" + tail)
    return normalized


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для рассылки постов.\n"
        "1️⃣ Пришли фото и/или текст.\n"
        "2️⃣ /addgroups <@ссылки или t.me/…>\n"
        "3️⃣ /send — разослать пост."
    )


async def add_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    targets = extract_targets(update.message.text)

    if not targets:
        await update.message.reply_text("⚠️ Я не нашёл ни одной ссылки или @юзернейма.")
        return

    store = user_data_store.setdefault(user_id, {"photos": [], "text": "", "groups": []})
    added, failed = [], []

    for tgt in targets:
        try:
            chat = await (context.bot.join_chat(tgt) if tgt.startswith("https://t.me/+")
                          else context.bot.get_chat(tgt))
            member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if member.status in ("left", "kicked"):
                raise ValueError("Бот не состоит в группе")
        except TelegramError as e:
            failed.append(f"{tgt} ({e.message})")
            continue
        except Exception as e:
            failed.append(f"{tgt} ({e})")
            continue

        if chat.id not in store["groups"]:
            store["groups"].append(chat.id)
        added.append(chat.title or chat.username or str(chat.id))

    msgs = []
    if added:
        msgs.append(f"✅ Добавил: {', '.join(added)}")
    if failed:
        msgs.append(
            f"⚠️ Не удалось: {', '.join(failed)}\n"
            "Убедитесь, что бот добавлен в группы и имеет право писать."
        )
    await update.message.reply_text("\n".join(msgs))


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo_id = update.message.photo[-1].file_id
    store = user_data_store.setdefault(user_id, {"photos": [], "text": "", "groups": []})
    store["photos"].append(photo_id)
    await update.message.reply_text("📸 Фото сохранено.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith("/"):
        return
    user_id = update.effective_user.id
    store = user_data_store.setdefault(user_id, {"photos": [], "text": "", "groups": []})
    store["text"] = update.message.text
    await update.message.reply_text("✏️ Текст сохранён.")


async def send_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data_store.get(user_id)

    if not data or (not data["photos"] and not data["text"]):
        await update.message.reply_text("⚠️ Нет данных для отправки.")
        return
    if not data.get("groups"):
        await update.message.reply_text("⚠️ Сначала укажи группы через /addgroups.")
        return

    errors = []
    for gid in data["groups"]:
        try:
            if len(data["photos"]) > 1:
                media = [InputMediaPhoto(p) for p in data["photos"]]
                media[0].caption = data["text"]
                await context.bot.send_media_group(gid, media)
            else:
                await context.bot.send_photo(gid, photo=data["photos"][0], caption=data["text"])
        except TelegramError as e:
            errors.append(f"{gid}: {e.message}")
        except Exception as e:
            errors.append(f"{gid}: {e}")

    if errors:
        await update.message.reply_text("Часть групп не приняла пост:\n" + "\n".join(errors))
    else:
        await update.message.reply_text("✅ Пост разослан по всем группам!")

    user_data_store.pop(user_id, None)


# ──────────── Запуск ──────────────────────────────────────────────────────────
async def main():
    logging.basicConfig(level=logging.INFO)

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addgroups", add_groups))
    app.add_handler(CommandHandler("send", send_post))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    await app.bot.set_webhook(WEBHOOK_URL)
    print(f"🤖 Webhook установлен: {WEBHOOK_URL}")

    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL,
        path="/webhook"  # важно для PTB!
    )


if __name__ == "__main__":
    asyncio.run(main())