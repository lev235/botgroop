import os
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler,
    CallbackQueryHandler, filters, ConversationHandler
)
import logging

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "8443"))

user_data = {}  # {user_id: {'groups': set(), 'photo': file_id, 'caption': str}}

# Состояния для ConversationHandler
EDIT_GROUPS, EDIT_PHOTO, EDIT_TEXT, CONFIRM_SEND = range(4)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_data:
        user_data[user_id] = {'groups': set(), 'photo': None, 'caption': ""}
    await update.message.reply_text(
        "Привет!\n"
        "Отправь мне ссылки на группы (через пробел), куда хочешь рассылать посты.\n"
        "После этого отправь фото с подписью (текст поста).\n"
        "Команда /preview — показать текущий пост и группы.\n"
        "Команда /send — отправить пост."
    )

async def groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    links = text.split()

    valid_chat_ids = set()
    failed = []
    for link in links:
        try:
            chat = await context.bot.get_chat(link)
            valid_chat_ids.add(chat.id)
        except Exception as e:
            failed.append(link)

    if not valid_chat_ids:
        await update.message.reply_text("Не удалось получить ни одной группы. Отправь правильные ссылки.")
        return EDIT_GROUPS

    user_data[user_id]['groups'] = valid_chat_ids
    await update.message.reply_text(f"Сохранено {len(valid_chat_ids)} групп.")
    return ConversationHandler.END

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not update.message.photo:
        await update.message.reply_text("Пожалуйста, отправь фото с подписью.")
        return EDIT_PHOTO
    photo = update.message.photo[-1]
    caption = update.message.caption or ""

    user_data[user_id]['photo'] = photo.file_id
    user_data[user_id]['caption'] = caption

    await update.message.reply_text("Фото и подпись сохранены.")
    return ConversationHandler.END

async def preview_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data.get(user_id)
    if not data:
        await update.message.reply_text("Данные ещё не заданы. Используй /start.")
        return
    if not data['groups']:
        await update.message.reply_text("Группы не заданы. Отправь ссылки на группы.")
        return
    if not data['photo']:
        await update.message.reply_text("Фото с подписью не заданы. Отправь фото с подписью.")
        return

    groups_links = []
    for gid in data['groups']:
        try:
            chat = await context.bot.get_chat(gid)
            if chat.username:
                groups_links.append(f"https://t.me/{chat.username}")
            else:
                groups_links.append(f"chat_id: {gid}")
        except Exception:
            groups_links.append(f"chat_id: {gid} (не доступен)")

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Изменить группы", callback_data='edit_groups')],
        [InlineKeyboardButton("Изменить фото/текст", callback_data='edit_photo')],
        [InlineKeyboardButton("Отправить пост", callback_data='send_post')],
        [InlineKeyboardButton("Отмена", callback_data='cancel')]
    ])

    await update.message.reply_photo(
        photo=data['photo'],
        caption=f"{data['caption']}\n\nОтправится в группы:\n" + "\n".join(groups_links),
        reply_markup=keyboard
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == 'edit_groups':
        await query.edit_message_caption(caption="Отправь новые ссылки на группы (через пробел):")
        return EDIT_GROUPS
    elif query.data == 'edit_photo':
        await query.edit_message_caption(caption="Отправь новое фото с подписью:")
        return EDIT_PHOTO
    elif query.data == 'send_post':
        # Отправляем пост во все группы
        data = user_data.get(user_id)
        if not data:
            await query.edit_message_text("Данные не найдены. Используй /start.")
            return ConversationHandler.END
        sent = 0
        errors = []
        for gid in data['groups']:
            try:
                await context.bot.send_photo(gid, photo=data['photo'], caption=data['caption'])
                sent += 1
            except Exception as e:
                errors.append(f"Ошибка при отправке в {gid}: {e}")

        text = f"Пост отправлен в {sent} групп."
        if errors:
            text += "\nОшибки:\n" + "\n".join(errors)
        await query.edit_message_text(text)
        # Очистить данные
        user_data.pop(user_id, None)
        return ConversationHandler.END
    elif query.data == 'cancel':
        await query.edit_message_text("Отмена. Используй /start чтобы начать заново.")
        return ConversationHandler.END

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Действие отменено. Используй /start чтобы начать заново.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start),
                      CommandHandler('groups', groups_handler),
                      MessageHandler(filters.PHOTO, photo_handler),
                      CommandHandler('preview', preview_handler)],
        states={
            EDIT_GROUPS: [MessageHandler(filters.TEXT & ~filters.COMMAND, groups_handler)],
            EDIT_PHOTO: [MessageHandler(filters.PHOTO, photo_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel_handler)],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))

    app.add_handler(CommandHandler("send", preview_handler))  # чтобы preview был и с /send тоже

    port = PORT
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=BOT_TOKEN,
        webhook_url=f"https://botgroop-6.onrender.com/{BOT_TOKEN}"
    )


if __name__ == "__main__":
    main()