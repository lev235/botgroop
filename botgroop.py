
# botgroop.py
import os
import re
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

BOT_TOKEN   = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")          # https://<render-url>
PORT        = int(os.getenv("PORT", 10000))     # Render даёт 10000

# ─────────────────────────────────────────────────────────
user_groups: dict[int, list[str]] = {}          # ссылки-группы
user_posts : dict[int, dict | None] = {}        # {'photo_file_id', 'caption'}
user_states: dict[int, str | None] = {}         # None / edit_groups / edit_post
# ─────────────────────────────────────────────────────────


# ─── helpers ─────────────────────────────────────────────
LINK_RE = re.compile(r"(?:https?://)?t\.me/([\w\d_]+)|@([\w\d_]+)", re.I)

def parse_links(text: str) -> list[str]:
    """Возвращает список ссылок https://t.me/<username> из произвольного текста"""
    links = []
    for m in LINK_RE.finditer(text):
        name = m.group(1) or m.group(2)
        links.append(f"https://t.me/{name}")
    return links
# ─────────────────────────────────────────────────────────


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    uid = update.effective_user.id

    user_groups.setdefault(uid, [])
    user_posts.setdefault(uid, None)
    user_states[uid] = "edit_groups"            # ← сразу ждём ссылки!

    await update.message.reply_text(
        "👋 Привет!\n"
        "1️⃣ Пришли публичные ссылки на группы (через пробел / строку).\n"
        "2️⃣ Пришли фото с подписью – это будет пост.\n"
        "3️⃣ /send – разослать.\n\n"
        "🛠 Кнопки «Изменить» появятся после первого ввода."
    )


async def groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    uid = update.effective_user.id

    # Обрабатываем, если:
    #  ─ пользователь в режиме редактирования групп
    #  ─ или групп ещё нет (первый ввод после /start)
    if user_states.get(uid) not in ("edit_groups", None) and user_groups.get(uid):
        return

    links = parse_links(update.message.text)
    if not links:
        return                                       # это не ссылки – игнорируем

    user_groups[uid] = links
    user_states[uid] = None                          # вышли из edit_groups

    kb = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("✏️ Изменить группы", callback_data="edit_groups")
    )
    await update.message.reply_text(
        f"✅ Сохранено групп: {len(links)}",
        reply_markup=kb,
    )


async def photo_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    uid = update.effective_user.id

    # принимаем фото, если пользователь в edit_post или поста ещё нет
    if user_states.get(uid) not in ("edit_post", None) and user_posts.get(uid):
        return

    if not update.message.photo:
        return

    photo = update.message.photo[-1]
    caption = update.message.caption or ""
    user_posts[uid] = {"photo_file_id": photo.file_id, "caption": caption}
    user_states[uid] = None

    kb = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("✏️ Изменить пост", callback_data="edit_post")
    )
    await update.message.reply_text("📸 Пост сохранён.", reply_markup=kb)


async def send_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    uid = update.effective_user.id
    groups = user_groups.get(uid) or []
    post   = user_posts.get(uid)

    if not groups:
        await update.message.reply_text("⚠️ Сначала пришли ссылки на группы.")
        return
    if not post:
        await update.message.reply_text("⚠️ Сначала пришли фото с подписью.")
        return

    await update.message.reply_text(
        "▶️ Отправляю пост в:\n" + "\n".join(groups)
    )

    sent, errors = 0, []
    for link in groups:
        try:
            await context.bot.send_photo(
                chat_id=link,                       # PTB примет ссылку
                photo=post["photo_file_id"],
                caption=post["caption"]
            )
            sent += 1
        except Exception as e:
            errors.append(f"{link}: {e}")

    await update.message.reply_text(f"✅ Отправлено: {sent}")
    if errors:
        await update.message.reply_text("❌ Ошибки:\n" + "\n".join(errors))


async def show_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    uid = update.effective_user.id
    groups = user_groups.get(uid) or []

    kb = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("✏️ Изменить группы", callback_data="edit_groups")
    )
    text = "Группы не заданы." if not groups else "Ваши группы:\n" + "\n".join(groups)
    await update.message.reply_text(text, reply_markup=kb)


async def show_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    uid = update.effective_user.id
    post = user_posts.get(uid)
    if not post:
        await update.message.reply_text("Пост ещё не сохранён.")
        return

    kb = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("✏️ Изменить пост", callback_data="edit_post")
    )
    await update.message.reply_photo(
        photo=post["photo_file_id"], caption=post["caption"], reply_markup=kb
    )


async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "edit_groups":
        user_states[uid] = "edit_groups"
        await q.message.reply_text("Введите новые ссылки на группы (через пробел / строку).")
    elif q.data == "edit_post":
        user_states[uid] = "edit_post"
        await q.message.reply_text("Пришлите новое фото с подписью.")


# ─── main / webhook ──────────────────────────────────────
def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("send",   send_handler))
    app.add_handler(CommandHandler("groups", show_groups))
    app.add_handler(CommandHandler("post",   show_post))

    app.add_handler(MessageHandler(filters.TEXT  & ~filters.COMMAND,  groups_handler))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND,  photo_post_handler))
    app.add_handler(CallbackQueryHandler(buttons))

    # WebHook
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()