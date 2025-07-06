import os
import logging
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters,
)
from telegram.error import TelegramError

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "8443"))

# Хранилища: user_id -> set(chat_id)
user_groups = {}
# user_id -> {"photo_file_id": ..., "caption": ...}
user_posts = {}

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
    failed_links = []

    for link in links:
        try:
            chat = await context.bot.get_chat(link)
            valid_chat_ids.add(chat.id)
        except TelegramError as e:
            failed_links.append(f"{link} ({e.message})")
            logging.warning(f"User {user_id} invalid chat link {link}: {e}")
        except Exception as e:
            failed_links.append(f"{link} ({str(e)})")
            logging.warning(f"User {user_id} invalid chat link {link}: {e}")

    if not valid_chat_ids:
        await update.message.reply_text("Не удалось получить ни одной группы по ссылкам. Отправь правильные ссылки.")
        return

    user_groups[user_id] = valid_chat_ids

    msg = f"Сохранено {len(valid_chat_ids)} групп для рассылки."
    if failed_links:
        msg += "\n⚠️ Не удалось обработать:\n" + "\n".join(failed_links)
        msg += "\nУбедись, что бот добавлен в эти группы и имеет права."

    await update.message.reply_text(msg)

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
    failed = []

    for chat_id in groups:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=post["photo_file_id"],
                caption=post["caption"]
            )
            sent_count += 1
        except TelegramError as e:
            logging.error(f"Ошибка при отправке в группу {chat_id}: {e.message}")
            failed.append(f"Группа {chat_id}: {e.message}")
        except Exception as e:
            logging.error(f"Ошибка при отправке в группу {chat_id}: {e}")
            failed.append(f"Группа {chat_id}: {e}")

    reply_msg = f"Пост отправлен в {sent_count} групп."
    if failed:
        reply_msg += "\nОшибки при отправке в некоторые группы:\n" + "\n".join(failed)

    await update.message.reply_text(reply_msg)

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
        return

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
            # Если группы не заданы — считаем, что текст — это ссылки и пробуем обработать
            await groups_handler(update, context)
        else:
            await update.message.reply_text(
                "Группы уже заданы. Чтобы изменить группы, отправь команду /start."
            )

    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_router))
    app.add_handler(MessageHandler(filters.PHOTO & (~filters.COMMAND), photo_post_handler))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"https://botgroop-6.onrender.com/{BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()