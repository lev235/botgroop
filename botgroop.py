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
from telegram.error import TelegramError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

BOT_TOKEN   = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")          # https://<render-url>
PORT        = int(os.getenv("PORT", 10000))     # Render даёт 10000

# ─────────────────────────────────────────────────────────
user_groups: dict[int, list[int]] = {}          # chat_id-ы групп
user_posts : dict[int, dict | None] = {}        # {'photo_file_id', 'caption'}
user_states: dict[int, str | None] = {}         # None / edit_groups / edit_post
# ─────────────────────────────────────────────────────────

# ╭─ helpers ─────────────────────────────────────────────╮
LINK_RE = re.compile(r"(https?://t\.me/[^\s]+|@[\w\d_]+)", re.I)

def extract_targets(text: str) -> list[str]:
    """
    Принимает любое сообщение пользователя, возвращает «цели»:
    •  https://t.me/username  →  @username
    •  @username              →  @username
    •  https://t.me/+abcdef   →  https://t.me/+abcdef   (инвайт-ссылка)
    """
    out = []
    for raw in LINK_RE.findall(text):
        if raw.startswith("@"):
            out.append(raw)                   # уже username
        elif raw.startswith("https://t.me/+"):
            out.append(raw)                   # инвайт-ссылка оставляем как есть
        else:                                 # обычная https://t.me/username
            tail = raw.rsplit("/", 1)[-1]
            out.append("@" + tail)
    return out
# ╰───────────────────────────────────────────────────────╯


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.chat.type != "private":
        return
    uid = update.effective_user.id

    user_groups.setdefault(uid, [])
    user_posts.setdefault(uid, None)
    user_states[uid] = "edit_groups"

    await update.message.reply_text(
        "👋 Привет!\n"
        "1️⃣ Пришли публичные ссылки на группы.\n"
        "2️⃣ Пришли фото с подписью – это будет пост.\n"
        "3️⃣ /send – разослать.\n\n"
        "🛠 Кнопки «Изменить» появятся после первого ввода."
    )


# ╭─ НОВЫЙ groups_handler ───────────────────────────────╮
async def groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.chat.type != "private":
        return
    uid = update.effective_user.id

    if user_states.get(uid) not in ("edit_groups", None) and user_groups.get(uid):
        return

    targets = extract_targets(update.message.text)
    if not targets:
        await update.message.reply_text("⚠️ Я не нашёл ни одной ссылки или @юзернейма.")
        return

    chat_ids, added, failed = [], [], []

    for tgt in targets:
        try:
            # 1) инвайт-ссылка → пробуем вступить
            if tgt.startswith("https://t.me/+"):
                chat = await context.bot.join_chat(tgt)
            else:
                # 2) обычный @username  /  числовой chat_id
                chat = await context.bot.get_chat(tgt)

            # проверяем, что бот уже состоит и не забанен
            member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if member.status in ("left", "kicked"):
                raise ValueError("Бот не состоит в группе")

        except TelegramError as e:
            failed.append(f"{tgt} ({e.message})")
            continue
        except Exception as e:
            failed.append(f"{tgt} ({e})")
            continue

        chat_ids.append(chat.id)
        added.append(chat.title or chat.username or str(chat.id))

    if not chat_ids:
        await update.message.reply_text("❌ Не удалось сохранить ни одну группу.")
        if failed:
            await update.message.reply_text("⚠️ Причины:\n" + "\n".join(failed))
        return

    user_groups[uid] = chat_ids
    user_states[uid] = None

    kb = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("✏️ Изменить группы", callback_data="edit_groups")
    )
    await update.message.reply_text(
        f"✅ Добавил: {', '.join(added)}", reply_markup=kb
    )
    if failed:
        await update.message.reply_text(
            "⚠️ Не удалось:\n" + "\n".join(failed) +
            "\nУбедитесь, что бот добавлен в группы и имеет права."
        )
# ╰───────────────────────────────────────────────────────╯


# ─── photo / send / show / buttons  (без изменений) ────
async def photo_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.chat.type != "private":
        return
    uid = update.effective_user.id

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
    if update.message is None or update.message.chat.type != "private":
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
        "▶️ Отправляю пост в:\n" + "\n".join(map(str, groups))
    )

    sent, errors = 0, []
    for chat_id in groups:
        try:
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=post["photo_file_id"],
                caption=post["caption"]
            )
            sent += 1
        except TelegramError as e:
            errors.append(f"{chat_id}: {e.message}")

    await update.message.reply_text(f"✅ Отправлено: {sent}")
    if errors:
        await update.message.reply_text("❌ Ошибки:\n" + "\n".join(errors))


async def show_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.chat.type != "private":
        return
    uid = update.effective_user.id
    groups = user_groups.get(uid) or []

    kb = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("✏️ Изменить группы", callback_data="edit_groups")
    )
    text = "Группы не заданы." if not groups else "Ваши группы:\n" + "\n".join(map(str, groups))
    await update.message.reply_text(text, reply_markup=kb)


async def show_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.chat.type != "private":
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
    if q is None:
        return
    await q.answer()
    uid = q.from_user.id

    if q.data == "edit_groups":
        user_states[uid] = "edit_groups"
        await q.message.reply_text("Введите новые ссылки на группы (через пробел / строку).")
    elif q.data == "edit_post":
        user_states[uid] = "edit_post"
        await q.message.reply_text("Пришлите новое фото с подписью.")


# ─── main / webhook ─────────────────────────────────────
def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("send",   send_handler))
    app.add_handler(CommandHandler("groups", show_groups))
    app.add_handler(CommandHandler("post",   show_post))

    app.add_handler(MessageHandler(filters.TEXT  & ~filters.COMMAND,  groups_handler))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND,  photo_post_handler))
    app.add_handler(CallbackQueryHandler(buttons))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()