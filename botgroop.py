from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)

# Словарь пользователей и их данных:
# user_id -> {"username": str, "groups": {chat_id: group_name}, "post": {"text": str, "photo": file_id}}
users_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name

    if user_id not in users_data:
        users_data[user_id] = {"username": username, "groups": {}, "post": {}}
        await update.message.reply_text(
            f"Привет, {username}! Ты зарегистрирован.\n"
            "Добавь свои группы командой /addgroup <chat_id>.\n"
            "Например: /addgroup -1001234567890"
        )
    else:
        await update.message.reply_text(
            f"Привет, {username}! Ты уже зарегистрирован.\n"
            "Добавляй группы командой /addgroup <chat_id>.\n"
            "Посмотреть группы — /groups"
        )

async def addgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in users_data:
        await update.message.reply_text("Сначала отправь /start для регистрации.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Пожалуйста, укажи ID группы. Например:\n/addgroup -1001234567890")
        return

    chat_id_str = args[0]
    try:
        chat_id = int(chat_id_str)
    except ValueError:
        await update.message.reply_text("ID группы должен быть числом, начинающимся с минуса, например -1001234567890.")
        return

    # Можно попытаться получить название группы через API, но проще попросить указать вручную
    # Для упрощения запросим название группы у пользователя
    users_data[user_id]["groups"][chat_id] = "Группа без названия"

    await update.message.reply_text(
        f"Группа с ID {chat_id} добавлена.\n"
        "Чтобы задать название группы, отправь команду:\n"
        f"/setgroupname {chat_id} <название>"
    )

async def setgroupname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data:
        await update.message.reply_text("Сначала отправь /start для регистрации.")
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Использование:\n/setgroupname <chat_id> <название группы>")
        return

    try:
        chat_id = int(args[0])
    except ValueError:
        await update.message.reply_text("ID группы должен быть числом.")
        return

    name = " ".join(args[1:])
    if chat_id not in users_data[user_id]["groups"]:
        await update.message.reply_text("У тебя нет такой группы. Добавь сначала /addgroup.")
        return

    users_data[user_id]["groups"][chat_id] = name
    await update.message.reply_text(f"Название группы с ID {chat_id} установлено: {name}")

async def groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in users_data or not users_data[user_id]["groups"]:
        await update.message.reply_text("У тебя ещё нет добавленных групп. Добавь с помощью /addgroup.")
        return

    msg = "Твои группы:\n"
    for chat_id, name in users_data[user_id]["groups"].items():
        msg += f"{chat_id} — {name}\n"
    await update.message.reply_text(msg)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if user_id not in users_data:
        await update.message.reply_text("Сначала отправь /start для регистрации.")
        return

    users_data[user_id]["post"]["text"] = text
    users_data[user_id]["post"].pop("photo", None)  # если было фото, удаляем

    await update.message.reply_text("Текст сохранён. Теперь отправь /send для рассылки.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    photo = update.message.photo[-1]
    caption = update.message.caption or ""

    if user_id not in users_data:
        await update.message.reply_text("Сначала отправь /start для регистрации.")
        return

    users_data[user_id]["post"]["photo"] = photo.file_id
    users_data[user_id]["post"]["text"] = caption

    await update.message.reply_text("Фото и подпись сохранены. Отправь /send для рассылки.")

async def send_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in users_data:
        await update.message.reply_text("Сначала отправь /start для регистрации.")
        return

    post = users_data[user_id]["post"]
    if not post:
        await update.message.reply_text("У тебя нет сохранённого поста. Отправь текст или фото с подписью.")
        return

    groups = users_data[user_id]["groups"]
    if not groups:
        await update.message.reply_text("У тебя нет добавленных групп. Добавь с помощью /addgroup.")
        return

    buttons = [
        [InlineKeyboardButton(name, callback_data=str(chat_id))]
        for chat_id, name in groups.items()
    ]
    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Выбери группу для отправки:", reply_markup=keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = int(query.data)

    await query.answer()

    if user_id not in users_data:
        await query.edit_message_text("Ты не зарегистрирован. Отправь /start.")
        return

    post = users_data[user_id]["post"]
    if not post:
        await query.edit_message_text("Пост не найден. Отправь текст или фото.")
        return

    try:
        if "photo" in post:
            await context.bot.send_photo(chat_id=chat_id, photo=post["photo"], caption=post.get("text", ""))
        else:
            await context.bot.send_message(chat_id=chat_id, text=post.get("text", ""))
        await query.edit_message_text("✅ Пост отправлен.")
        users_data[user_id]["post"] = {}
    except Exception as e:
        await query.edit_message_text(f"Ошибка при отправке: {e}")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Неизвестная команда.")

def main():
    TOKEN = "8178775990:AAGGwrAEHAnWRvfbUrnpRbhWHfJjHDPOf1w"

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addgroup", addgroup))
    application.add_handler(CommandHandler("setgroupname", setgroupname))
    application.add_handler(CommandHandler("groups", groups))
    application.add_handler(CommandHandler("send", send_command))

    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text))

    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    print("Бот запущен...")
    application.run_polling()

if __name__ == "__main__":
    main()