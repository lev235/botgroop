import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters, CallbackContext
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # например https://yourdomain.com/yourtoken
PORT = int(os.getenv("PORT", 8443))

user_groups = {}
user_posts = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return
    user_id = update.effective_user.id
    user_groups.setdefault(user_id, set())
    user_posts.setdefault(user_id, None)
    await update.message.reply_text(
        "Привет!\n"
        "Отправь мне ссылки на публичные группы вида https://t.me/username через пробел.\n"
        "Затем отправь фото с подписью.\n"
        "После отправь /send для рассылки."
    )

async def groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Парсим ссылки https://t.me/username или @username
    links = text.split()
    valid_chat_ids = set()
    errors = []

    for link in links:
        username = None
        if link.startswith("https://t.me/"):
            username = link[len("https://t.me/"):]
        elif link.startswith("@"):
            username = link[1:]
        else:
            errors.append(f"Неверный формат ссылки: {link}")
            continue

        try:
            chat = await context.bot.get_chat(username)
            # Проверка: бот должен быть в группе
            member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if member.status in ("left", "kicked"):
                errors.append(f"Бот не состоит в группе {link}")
                continue
            valid_chat_ids.add(chat.id)
        except Exception as e:
            errors.append(f"Не удалось получить чат по {link}: {e}")

    if valid_chat_ids:
        user_groups[user_id] = valid_chat_ids
        await update.message.reply_text(f"Сохранено {len(valid_chat_ids)} групп.")
    else:
        await update.message.reply_text("Не удалось получить ни одной группы по ссылкам.")

    if errors:
        await update.message.reply_text("\n".join(errors))

async def photo_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return
    user_id = update.effective_user.id
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправь фото с подписью.")
        return

    photo = update.message.photo[-1]
    caption = update.message.caption or ""

    user_posts[user_id] = {
        "photo_file_id": photo.file_id,
        "caption": caption
    }
    await update.message.reply_text("Пост с фото сохранён. Отправь /send для рассылки.")

async def send_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return
    user_id = update.effective_user.id
    groups = user_groups.get(user_id)
    post = user_posts.get(user_id)

    if not groups:
        await update.message.reply_text("Сначала отправь ссылки на группы для рассылки.")
        return
    if not post:
        await update.message.reply_text("Сначала отправь фото с подписью для рассылки.")
        return

    sent_count = 0
    errors = []
    for chat_id in groups:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=post["photo_file_id"],
                caption=post["caption"]
            )
            sent_count += 1
        except Exception as e:
            errors.append(f"Ошибка при отправке в {chat_id}: {e}")

    await update.message.reply_text(f"Пост отправлен в {sent_count} групп.")
    if errors:
        await update.message.reply_text("Ошибки:\n" + "\n".join(errors))

async def show_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return
    user_id = update.effective_user.id
    groups = user_groups.get(user_id)
    if not groups:
        await update.message.reply_text("Группы не заданы.")
        return
    texts = []
    for chat_id in groups:
        try:
            chat = await context.bot.get_chat(chat_id)
            if chat.username:
                texts.append(f"https://t.me/{chat.username}")
            else:
                texts.append(f"chat_id: {chat_id}")
        except Exception:
            texts.append(f"chat_id: {chat_id} (недоступен)")
    await update.message.reply_text("Ваши группы для рассылки:\n" + "\n".join(texts))

async def show_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return
    user_id = update.effective_user.id
    post = user_posts.get(user_id)
    if not post:
        await update.message.reply_text("Пост ещё не сохранён.")
    else:
        await update.message.reply_photo(photo=post["photo_file_id"], caption=post["caption"])

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("send", send_handler))
    app.add_handler(CommandHandler("groups", show_groups_handler))
    app.add_handler(CommandHandler("post", show_post_handler))
    app.add_handler(MessageHandler(filters.PHOTO & (~filters.COMMAND), photo_post_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), groups_handler))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=f"webhook/{BOT_TOKEN}",
        webhook_url=f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}"
    )

if __name__ == '__main__':
    main()