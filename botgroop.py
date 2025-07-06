import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters,
    CallbackQueryHandler,
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Например, https://yourdomain.com
PORT = int(os.getenv("PORT", "8443"))

user_groups = {}
user_posts = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    user_groups.setdefault(user_id, [])
    user_posts.setdefault(user_id, None)
    await update.message.reply_text(
        "Привет!\n"
        "Отправь ссылки на публичные группы вида https://t.me/username или @username через пробел.\n"
        "Затем отправь фото с подписью — это будет пост.\n"
        "Команда /send отправит пост во все выбранные группы.\n"
        "Команда /groups покажет текущие группы.\n"
        "Команда /post покажет текущий сохранённый пост."
    )

async def groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()

    links = text.split()
    valid_links = []
    errors = []

    for link in links:
        if link.startswith("https://t.me/"):
            valid_links.append(link)
        elif link.startswith("@"):
            valid_links.append("https://t.me/" + link[1:])
        else:
            errors.append(f"Неверный формат ссылки: {link}")

    if valid_links:
        user_groups[user_id] = valid_links
        keyboard = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton("Изменить группы", callback_data="edit_groups")
        )
        await update.message.reply_text(
            f"Сохранено {len(valid_links)} групп.",
            reply_markup=keyboard,
        )
    else:
        await update.message.reply_text("Не удалось сохранить ни одной ссылки.")

    if errors:
        await update.message.reply_text("\n".join(errors))

async def photo_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
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

    keyboard = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("Изменить пост", callback_data="edit_post")
    )

    await update.message.reply_text("Пост с фото сохранён.", reply_markup=keyboard)

async def send_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
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

    # Покажем пользователю, куда будет отправлен пост
    groups_text = "\n".join(groups)
    await update.message.reply_text(
        f"Пост будет отправлен в следующие группы:\n{groups_text}\n\nОтправляем..."
    )

    sent_count = 0
    errors = []
    for chat_link in groups:
        try:
            await context.bot.send_photo(
                chat_id=chat_link,
                photo=post["photo_file_id"],
                caption=post["caption"],
            )
            sent_count += 1
        except Exception as e:
            errors.append(f"Ошибка при отправке в {chat_link}: {e}")

    await update.message.reply_text(f"Пост отправлен в {sent_count} групп.")
    if errors:
        await update.message.reply_text("Ошибки:\n" + "\n".join(errors))

async def show_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    groups = user_groups.get(user_id)
    if not groups:
        await update.message.reply_text("Группы не заданы.")
        return

    keyboard = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("Изменить группы", callback_data="edit_groups")
    )

    await update.message.reply_text(
        "Ваши группы для рассылки:\n" + "\n".join(groups),
        reply_markup=keyboard,
    )

async def show_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    post = user_posts.get(user_id)
    if not post:
        await update.message.reply_text("Пост ещё не сохранён.")
        return

    keyboard = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("Изменить пост", callback_data="edit_post")
    )

    await update.message.reply_photo(photo=post["photo_file_id"], caption=post["caption"], reply_markup=keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == "edit_groups":
        await query.message.reply_text("Отправьте новые ссылки на группы для рассылки (через пробел).")
        user_groups[user_id] = []  # Сбросим текущие группы

    elif query.data == "edit_post":
        await query.message.reply_text("Отправьте новое фото с подписью для рассылки.")
        user_posts[user_id] = None  # Сбросим текущий пост

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("send", send_handler))
    app.add_handler(CommandHandler("groups", show_groups_handler))
    app.add_handler(CommandHandler("post", show_post_handler))

    app.add_handler(MessageHandler(filters.PHOTO & (~filters.COMMAND), photo_post_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), groups_handler))

    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()