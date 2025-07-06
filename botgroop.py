# botgroop.py
import os, re, logging
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
PORT        = int(os.getenv("PORT", 10000))     # Render выдаёт 10000

# ─────────────────────────────────────────────────────────
user_groups: dict[int, list[int]] = {}          # chat_id-ы групп
user_posts : dict[int, dict | None] = {}        # {'kind','file_id','caption'}
user_states: dict[int, str | None] = {}         # None / edit_groups / edit_post
# ─────────────────────────────────────────────────────────

# ╭─ helpers ──────────────────────────────────────────────╮
LINK_RE = re.compile(r"(https?://t\.me/[^\s]+|@[\w\d_]+)", re.I)

def extract_targets(text: str) -> list[str]:
    """Из текста достаём ссылки/юзернеймы групп."""
    out = []
    for raw in LINK_RE.findall(text):
        if raw.startswith("@"):
            out.append(raw)
        elif raw.startswith("https://t.me/+"):
            out.append(raw)               # инвайт-ссылка, оставляем как есть
        else:                             # https://t.me/username
            out.append("@" + raw.rsplit("/", 1)[-1])
    return out
# ╰────────────────────────────────────────────────────────╯


# ─── /start ──────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.chat.type != "private":
        return
    uid = update.effective_user.id
    user_groups.setdefault(uid, [])
    user_posts.setdefault(uid, None)
    user_states[uid] = "edit_groups"

    await update.message.reply_text(
        "👋 Привет!\n"
        "1️⃣ Пришли ссылки на группы.\n"
        "2️⃣ Пришли фото **или видео** с подписью – это будет пост.\n"
        "3️⃣ /send – разослать."
    )

# ╭─ обработчик ссылок / групп ───────────────────────────╮
async def groups_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.chat.type != "private":
        return
    uid = update.effective_user.id
    if user_states.get(uid) not in ("edit_groups", None) and user_groups.get(uid):
        return

    targets = extract_targets(update.message.text)
    if not targets:
        await update.message.reply_text("⚠️ Не увидел ни одной валидной ссылки.")
        return

    chat_ids, added, failed = [], [], []
    for tgt in targets:
        try:
            chat = (
                await context.bot.join_chat(tgt)
                if tgt.startswith("https://t.me/+") else
                await context.bot.get_chat(tgt)
            )
            member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if member.status in ("left", "kicked"):
                raise ValueError("бот не состоит в группе")

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
    await update.message.reply_text("✅ Добавил: " + ", ".join(added), reply_markup=kb)
    if failed:
        await update.message.reply_text(
            "⚠️ Не удалось:\n" + "\n".join(failed) +
            "\nУбедитесь, что бот добавлен и имеет права."
        )
# ╰────────────────────────────────────────────────────────╯


# ─── приём МЕДИА (фото или видео) ────────────────────────
async def media_post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.chat.type != "private":
        return
    uid = update.effective_user.id
    if user_states.get(uid) not in ("edit_post", None) and user_posts.get(uid):
        return

    kind, file_id = None, None
    if update.message.photo:
        kind   = "photo"
        file_id = update.message.photo[-1].file_id
    elif update.message.video:
        kind   = "video"
        file_id = update.message.video.file_id
    else:
        return                                  # что-то прислали, но не медиа

    user_posts[uid] = {
        "kind":   kind,
        "file_id": file_id,
        "caption": update.message.caption or ""
    }
    user_states[uid] = None

    kb = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("✏️ Изменить пост", callback_data="edit_post")
    )
    await update.message.reply_text("✅ Пост сохранён.", reply_markup=kb)


# ─── /send ───────────────────────────────────────────────
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
        await update.message.reply_text("⚠️ Сначала пришли фото/видео с подписью.")
        return

    await update.message.reply_text(
        "▶️ Отправляю пост в:\n" + "\n".join(map(str, groups))
    )

    sent, errors = 0, []
    for chat_id in groups:
        try:
            if post["kind"] == "photo":
                await context.bot.send_photo(
                    chat_id, photo=post["file_id"], caption=post["caption"]
                )
            else:  # "video"
                await context.bot.send_video(
                    chat_id, video=post["file_id"], caption=post["caption"]
                )
            sent += 1
        except TelegramError as e:
            errors.append(f"{chat_id}: {e.message}")

    await update.message.reply_text(f"✅ Отправлено: {sent}")
    if errors:
        await update.message.reply_text("❌ Ошибки:\n" + "\n".join(errors))


# ─── /groups  /post  ─────────────────────────────────────
async def show_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.chat.type != "private":
        return
    uid, groups = update.effective_user.id, user_groups.get(uid) or []
    kb = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("✏️ Изменить группы", callback_data="edit_groups")
    )
    txt = "Группы не заданы." if not groups else "Ваши группы:\n" + "\n".join(map(str, groups))
    await update.message.reply_text(txt, reply_markup=kb)


async def show_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.chat.type != "private":
        return
    uid, post = update.effective_user.id, user_posts.get(uid)
    if not post:
        await update.message.reply_text("Пост ещё не сохранён."); return

    kb = InlineKeyboardMarkup.from_button(
        InlineKeyboardButton("✏️ Изменить пост", callback_data="edit_post")
    )
    if post["kind"] == "photo":
        await update.message.reply_photo(post["file_id"], caption=post["caption"], reply_markup=kb)
    else:
        await update.message.reply_video(post["file_id"], caption=post["caption"], reply_markup=kb)


# ─── кнопки «Изменить …» ─────────────────────────────────
async def buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q is None: return
    await q.answer()
    uid = q.from_user.id
    if q.data == "edit_groups":
        user_states[uid] = "edit_groups"
        await q.message.reply_text("Введите новые ссылки (через пробел / строку).")
    elif q.data == "edit_post":
        user_states[uid] = "edit_post"
        await q.message.reply_text("Пришлите новое фото или видео с подписью.")


# ─── main / webhook ─────────────────────────────────────
def main() -> None:
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("send",   send_handler))
    app.add_handler(CommandHandler("groups", show_groups))
    app.add_handler(CommandHandler("post",   show_post))

    media_filter = filters.PHOTO | filters.VIDEO
    app.add_handler(MessageHandler(filters.TEXT  & ~filters.COMMAND, groups_handler))
    app.add_handler(MessageHandler(media_filter & ~filters.COMMAND,  media_post_handler))
    app.add_handler(CallbackQueryHandler(buttons))

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
    )

if __name__ == "__main__":
    main()