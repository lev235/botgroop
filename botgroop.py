import os, re, asyncio, logging, nest_asyncio
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from telegram.error import TelegramError, TimedOut, BadRequest

nest_asyncio.apply()

BOT_TOKEN   = os.getenv("BOT_TOKEN")
PORT        = int(os.getenv("PORT", 8443))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")               # https://…onrender.com/webhook
URL_PATH    = "webhook"

LINK_RE = re.compile(r"(https?://t\.me/[^\s]+|@[\w\d_]+)", re.IGNORECASE)
user_data_store: dict[int, dict] = {}

def extract_targets(text: str) -> list[str]:
    links = LINK_RE.findall(text)
    out = []
    for raw in links:
        tail = raw.rsplit("/", 1)[-1] if raw.startswith("http") else raw
        out.append(raw if tail.startswith("+") else ("@" + tail.lstrip("@")))
    return out

# ──────────── handlers ────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот-рассыльщик.\n"
        "1. Пришли фото/текст\n"
        "2. /addgroups <@ссылки или t.me/…>\n"
        "3. /send — разослать"
    )

async def add_groups(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid, text = update.effective_user.id, update.message.text
    targets = extract_targets(text)
    if not targets:
        return await update.message.reply_text("⚠️ Не нашёл групп.")

    store = user_data_store.setdefault(uid, {"photos": [], "text": "", "groups": []})
    ok, bad = [], []
    for tgt in targets:
        try:
            chat = await (ctx.bot.join_chat(tgt) if tgt.startswith("https://t.me/+")
                          else ctx.bot.get_chat(tgt))
            member = await ctx.bot.get_chat_member(chat.id, ctx.bot.id)
            if member.status in ("left", "kicked"):
                raise ValueError("бот не состоит в группе")
        except (TelegramError, Exception) as e:
            bad.append(f"{tgt} ({e})"); continue

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
    # апдейты без текста (service, sticker, и т.п.) отфильтровываем
    if not (update.message and update.message.text):
        return
    if update.message.text.startswith("/"):
        return
    uid = update.effective_user.id
    store = user_data_store.setdefault(uid, {"photos": [], "text": "", "groups": []})
    store["text"] = update.message.text
    await update.message.reply_text("✏️ Текст сохранён.")

async def send_post(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = user_data_store.get(uid)
    if not data or (not data["photos"] and not data["text"]):
        return await update.message.reply_text("⚠️ Нет контента.")
    if not data["groups"]:
        return await update.message.reply_text("⚠️ Сначала /addgroups.")

    errors = []
    for gid in data["groups"]:
        try:
            if len(data["photos"]) > 1:
                media = [InputMediaPhoto(p) for p in data["photos"]]
                media[0].caption = data["text"]
                await ctx.bot.send_media_group(gid, media)
            else:
                await ctx.bot.send_photo(gid, data["photos"][0], caption=data["text"])
        except (TelegramError, Exception) as e:
            errors.append(f"{gid}: {e}")

    await update.message.reply_text(
        "✅ Разослано!" if not errors else "Некуда отправить:\n" + "\n".join(errors)
    )
    user_data_store.pop(uid, None)

# глобальный логгер ошибок — чтобы бот не падал
async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    logging.exception("Unhandled exception while processing update:", exc_info=ctx.error)

# ──────────── main ───────────────────────────────────────────────────────────
async def main():
    logging.basicConfig(level=logging.INFO)

    builder = ApplicationBuilder().token(BOT_TOKEN)
    # увеличиваем таймауты до 20 сек
    builder = builder.http_version("1.1").connect_timeout(10).read_timeout(20)
    app = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addgroups", add_groups))
    app.add_handler(CommandHandler("send",  send_post))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_error_handler(error_handler)

    await app.bot.set_webhook(WEBHOOK_URL)
    print("🤖 Webhook зарегистрирован:", WEBHOOK_URL)

    await app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=URL_PATH,           # ← ключевой фикс
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    asyncio.run(main())