import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters,
)
import logging

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "8443"))

user_groups = {}
user_posts = {}

def extract_username(link: str) -> str:
    if link.startswith("https://t.me/"):
        username = link[len("https://t.me/"):]
        username = username.lstrip('@').split('/')[0]  # Убираем @ и лишнее после слэша
        return '@' + username
    if link.startswith('@'):
        return link
    return link  # Если уже chat_id или что-то другое

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return  # игнорируем не личные чаты
    user_id = update.effective_user.id
    if user_id not in user_groups:
        user_groups[user_id] = set()
        user_posts[user_id] = None
    await update.message.reply_text(
        "Привет!\n"
        "Отправь мне ссылки на группы (через пробел), куда хочешь рассылать посты.\n"
        "После этого отправь фото с подписью (текст поста).\n"
        "Команда /send отправит твой пост во все выбранные группы."
    )

async def groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return
    user_id = update.effective_user.id
    text = update.message.text.strip()
    links = text.split()

    valid_chat_ids = set()
    for link in links:
        username_or_id = extract_username(link)
        try:
            chat = await context.bot.get_chat(username_or_id)
            valid_chat_ids.add(chat.id)
        except Exception as e:
            await update.message.reply_text(f"Не удалось получить чат по ссылке: {link}")
            logging.warning(f"User {user_id} invalid chat link {link}: {e}")

    if not valid_chat_ids:
        await update.message.reply_text("Не удалось получить ни одной группы по ссылкам. Отправь правильные ссылки.")
        return

    user_groups[user_id] = valid_chat_ids
    await update.message.reply_text(f"Сохранено {len(valid_chat_ids)} групп для рассылки.")

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

    await update.message.reply_text("Пост с фото сохранён. Для рассылки отправь /send.")

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
    for chat_id in groups:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=post["photo_file_id"],
                caption=post["caption"]
            )
            sent_count += 1
        except Exception as e:
            logging.error(f"Ошибка при отправке в группу {chat_id}: {e}")

    await update.message.reply_text(f"Пост отправлен в {sent_count} групп.")

async def show_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return
    user_id = update.effective_user.id
    groups = user_groups.get(user_id)
    if not groups:
        await update.message.reply_text("Группы не заданы.")
    else:
        texts = []
        for chat_id in groups:
            try:
                chat = await context.bot.get_chat(chat_id)
                if chat.username:
                    link = f"https://t.me/{chat.username}"
                else:
                    link = f"chat_id: {chat_id}"
                texts.append(link)
            except Exception:
                texts.append(f"chat_id: {chat_id} (не доступен)")
        await update.message.reply_text("Ваши группы для рассылки:\n" + "\n".join(texts))

async def show_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return
    user_id = update.effective_user.id
    post = user_posts.get(user_id)
    if not post:
        await update.message.reply_text("Пост ещё не сохранён.")
    else:
        await update.message.reply_photo(
            photo=post["photo_file_id"],
            caption=post["caption"]
        )

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("send", send_handler))
    app.add_handler(CommandHandler("groups", show_groups_handler))
    app.add_handler(CommandHandler("post", show_post_handler))

    async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.chat.type != 'private':
            return
        user_id = update.effective_user.id
        if user_id not in user_groups or not user_groups[user_id]:
            await groups_handler(update, context)
        else:
            await update.message.reply_text(
                "Группы уже заданы. Чтобы изменить группы, отправь команду /start."
            )

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_router))
    app.add_handler(MessageHandler(filters.PHOTO & (~filters.COMMAND), photo_post_handler))

    port = PORT
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=BOT_TOKEN,
        webhook_url=f"https://botgroop-6.onrender.com/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()