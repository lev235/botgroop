import os
import logging
from telegram import (
    Update, InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")  # Твой токен
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # Например https://yourdomain.com
PORT = int(os.getenv("PORT", 8443))

# Хранилища (для простоты в памяти, для продакшена — БД)
user_groups = {}
user_posts = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    user_groups.setdefault(user_id, set())
    user_posts.setdefault(user_id, None)
    await update.message.reply_text(
        "Привет!\n"
        "1) Отправь мне ссылки на публичные группы (https://t.me/username) через пробел.\n"
        "2) Отправь фото с подписью.\n"
        "3) Используй /send для рассылки."
    )

async def groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    user_id = update.effective_user.id
    text = update.message.text.strip()

    if context.user_data.get("editing") != "groups":
        await update.message.reply_text("Чтобы изменить группы, нажми кнопку 'Изменить группы'.")
        return

    links = text.split()
    valid_chat_ids = set()
    errors = []

    for link in links:
        username = None
        if link.startswith("https://t.me/"):
            username = link[len("https://t.me/") :]
        elif link.startswith("@"):
            username = link[1:]
        else:
            errors.append(f"Неверный формат ссылки: {link}")
            continue

        try:
            chat = await context.bot.get_chat(username)
            member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if member.status in ("left", "kicked"):
                errors.append(f"Бот не состоит в группе {link}")
                continue
            valid_chat_ids.add(chat.id)
        except Exception as e:
            errors.append(f"Не удалось получить чат по {link}: {e}")

    if valid_chat_ids:
        user_groups[user_id] = valid_chat_ids
        context.user_data["editing"] = None
        keyboard = InlineKeyboardMarkup.from_button(
            InlineKeyboardButton("Изменить группы", callback_data="edit_groups")
        )
        await update.message.reply_text(
            f"Сохранено {len(valid_chat_ids)} групп.",
            reply_markup=keyboard,
        )
    else:
        await update.message.reply_text("Не удалось сохранить ни одной группы.")

    if errors:
        await update.message.reply_text("\n".join(errors))


async def photo_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return

    user_id = update.effective_user.id

    editing = context.user_data.get("editing")
    if editing is not None and editing != "post":
        await update.message.reply_text(
            "Сейчас вы не можете отправлять фото. Используйте кнопки для изменения."
        )
        return

    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправь фото с подписью.")
        return

    photo = update.message.photo[-1]
    caption = update.message.caption or ""

    user_posts[user_id] = {"photo_file_id": photo.file_id, "caption": caption}
    context.user_data["editing"] = None

    keyboard = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("Изменить пост", callback_data="edit_post")
    )
    await update.message.reply_text("Пост с фото сохранён. Отправь /send для рассылки.", reply_markup=keyboard)


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

    # Отправляем предпросмотр с кнопками подтверждения
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Подтвердить рассылку", callback_data="confirm_send"),
                InlineKeyboardButton("❌ Отменить", callback_data="cancel_send"),
            ],
            [
                InlineKeyboardButton("✏️ Изменить группы", callback_data="edit_groups"),
                InlineKeyboardButton("✏️ Изменить пост", callback_data="edit_post"),
            ],
        ]
    )

    await update.message.reply_photo(
        photo=post["photo_file_id"],
        caption=f"Предпросмотр поста для рассылки в {len(groups)} групп:\n\n{post['caption']}",
        reply_markup=keyboard,
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "edit_groups":
        context.user_data["editing"] = "groups"
        await query.message.reply_text(
            "Отправь новые ссылки на публичные группы через пробел."
        )
    elif query.data == "edit_post":
        context.user_data["editing"] = "post"
        await query.message.reply_text(
            "Отправь новое фото с подписью для поста."
        )
    elif query.data == "confirm_send":
        groups = user_groups.get(user_id)
        post = user_posts.get(user_id)

        if not groups or not post:
            await query.message.reply_text("Нет данных для рассылки.")
            return

        sent_count = 0
        errors = []

        for chat_id in groups:
            try:
                await context.bot.send_photo(
                    chat_id=chat_id,
                    photo=post["photo_file_id"],
                    caption=post["caption"],
                )
                sent_count += 1
            except Exception as e:
                errors.append(f"Ошибка при отправке в {chat_id}: {e}")

        await query.message.reply_text(f"Пост отправлен в {sent_count} групп.")
        if errors:
            await query.message.reply_text("Ошибки:\n" + "\n".join(errors))
    elif query.data == "cancel_send":
        await query.message.reply_text("Рассылка отменена.")
    else:
        await query.message.reply_text("Неизвестная команда.")


async def show_groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
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
    if update.message.chat.type != "private":
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

    # Сообщения
    app.add_handler(MessageHandler(filters.PHOTO & (~filters.COMMAND), photo_post_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), groups_handler))  # Обрабатываем текст при редактировании групп

    # Кнопки
    app.add_handler(CallbackQueryHandler(callback_handler))

    # Запускаем webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )


if __name__ == "__main__":
    main()