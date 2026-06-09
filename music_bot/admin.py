import os
import logging
import functools
import uuid

from telegram import Update
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from config import ADMIN_ID, SONGS_DIR
import database

logger = logging.getLogger(__name__)

WAITING_AUDIO, WAITING_TITLE, WAITING_ARTIST, WAITING_DESCRIPTION = range(4)


def admin_only(func):
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            if update.message:
                await update.message.reply_text("❌ این دستور فقط برای ادمین در دسترسه.")
            return ConversationHandler.END
        return await func(update, context)
    return wrapper


@admin_only
async def upload_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎵 باشه! فایل صوتی آهنگی که می‌خوای آپلود کنی رو بفرست.\n\n"
        "برای لغو: /cancel"
    )
    return WAITING_AUDIO


async def receive_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    audio = msg.audio or msg.voice

    if audio is None and msg.document:
        mime = getattr(msg.document, "mime_type", "") or ""
        if mime.startswith("audio/"):
            audio = msg.document
        else:
            await msg.reply_text(
                "❌ این فایل صوتی نیست!\n"
                "یه فایل MP3 یا OGG بفرست. برای لغو: /cancel"
            )
            return WAITING_AUDIO

    if audio is None:
        await msg.reply_text(
            "❌ لطفاً یه فایل صوتی بفرست (MP3، OGG، ...).\n"
            "برای لغو: /cancel"
        )
        return WAITING_AUDIO

    context.user_data["audio_file_id"] = audio.file_id
    context.user_data["audio_file_name"] = getattr(audio, "file_name", None) or f"{audio.file_id}.mp3"

    await msg.reply_text(
        "✅ فایل دریافت شد!\n\n"
        "🎵 اسم آهنگ رو بنویس:"
    )
    return WAITING_TITLE


async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    if not title:
        await update.message.reply_text("❌ اسم آهنگ خالیه! دوباره بنویس:")
        return WAITING_TITLE

    context.user_data["title"] = title
    await update.message.reply_text("🎤 اسم خواننده یا گروه رو بنویس:")
    return WAITING_ARTIST


async def receive_artist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    artist = update.message.text.strip()
    if not artist:
        await update.message.reply_text("❌ اسم خواننده خالیه! دوباره بنویس:")
        return WAITING_ARTIST

    context.user_data["artist"] = artist
    await update.message.reply_text(
        "📝 یه توضیح کوتاه برای آهنگ بنویس.\n"
        "(اختیاریه — برای رد کردن /skip بزن)"
    )
    return WAITING_DESCRIPTION


async def skip_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _finalize_upload(update, context, description=None)


async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    description = update.message.text.strip() or None
    return await _finalize_upload(update, context, description=description)


async def _finalize_upload(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    description: str | None,
):
    file_id = context.user_data.get("audio_file_id")
    title = context.user_data.get("title")
    artist = context.user_data.get("artist")
    orig_name = context.user_data.get("audio_file_name", f"{file_id}.mp3")

    _, ext = os.path.splitext(orig_name)
    ext = ext or ".mp3"
    uid = str(uuid.uuid4())[:8]
    safe = "".join(c for c in f"{artist}_{title}" if c.isalnum() or c in "_ -").replace(" ", "_")
    file_name = f"{safe}_{uid}{ext}"
    file_path = os.path.join(SONGS_DIR, file_name)

    os.makedirs(SONGS_DIR, exist_ok=True)

    try:
        tg_file = await context.bot.get_file(file_id)
        await tg_file.download_to_drive(file_path)
    except Exception as e:
        logger.warning("Could not download file to disk, storing file_id only: %s", e)
        file_path = None

    try:
        song_id = await database.add_song(title, artist, description, file_id, file_path)
        bot_info = await context.bot.get_me()
        link = f"https://t.me/{bot_info.username}?start={song_id}"

        await update.message.reply_text(
            f"✅ آهنگ با موفقیت ذخیره شد!\n\n"
            f"🎵 <b>{title}</b>\n"
            f"🎤 {artist}\n"
            f"🆔 شناسه: <code>{song_id}</code>\n\n"
            f"🔗 لینک آهنگ:\n{link}\n\n"
            "این لینک رو توی کانالت بذار 👆",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error("Error saving song to DB: %s", e)
        await update.message.reply_text("❌ خطا در ذخیره‌سازی. لطفاً دوباره امتحان کن.")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ آپلود لغو شد.")
    return ConversationHandler.END


@admin_only
async def list_songs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    songs = await database.get_all_songs()
    if not songs:
        await update.message.reply_text("📭 هنوز هیچ آهنگی آپلود نشده.")
        return

    bot_info = await context.bot.get_me()
    lines = ["🎵 <b>لیست آهنگ‌ها:</b>\n"]
    for s in songs:
        link = f"https://t.me/{bot_info.username}?start={s['id']}"
        lines.append(
            f"🆔 <code>{s['id']}</code> — <b>{s['title']}</b> – {s['artist']}\n"
            f"🔗 {link}\n"
        )

    text = "\n".join(lines)
    if len(text) <= 4096:
        await update.message.reply_text(text, parse_mode="HTML")
    else:
        chunk = ""
        for line in lines:
            if len(chunk) + len(line) + 1 > 4000:
                await update.message.reply_text(chunk, parse_mode="HTML")
                chunk = line
            else:
                chunk += "\n" + line
        if chunk:
            await update.message.reply_text(chunk, parse_mode="HTML")


@admin_only
async def delete_song_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ فرمت: /deletesong <شناسه>   مثلاً: /deletesong 3")
        return

    try:
        song_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ شناسه باید عدد باشه.")
        return

    file_path = await database.delete_song(song_id)
    if file_path is None:
        await update.message.reply_text("❌ آهنگی با این شناسه پیدا نشد.")
        return

    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError as e:
            logger.error("Could not delete file %s: %s", file_path, e)

    await update.message.reply_text(f"✅ آهنگ شماره {song_id} حذف شد.")


@admin_only
async def list_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channels = await database.get_channels()
    if not channels:
        await update.message.reply_text("📭 هنوز هیچ کانالی اضافه نشده.")
        return

    lines = ["📢 <b>کانال‌های اجباری:</b>\n"]
    for ch in channels:
        lines.append(f"• <b>{ch['title']}</b>  ({ch['username']})\n  🔗 {ch['link']}\n")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@admin_only
async def add_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "❌ فرمت:\n"
            "<code>/addchannel @username | عنوان | لینک</code>\n\n"
            "مثلاً:\n"
            "<code>/addchannel @mychannel | کانال من | https://t.me/mychannel</code>",
            parse_mode="HTML",
        )
        return

    text = " ".join(context.args)
    parts = [p.strip() for p in text.split("|")]
    if len(parts) != 3:
        await update.message.reply_text("❌ سه بخش لازمه (با | جدا شده باشن):\n@username | عنوان | لینک")
        return

    username, title, link = parts
    if not username.startswith("@"):
        username = "@" + username

    ok = await database.add_channel(username, title, link)
    if ok:
        await update.message.reply_text(f"✅ کانال {username} به لیست اضافه شد!")
    else:
        await update.message.reply_text(f"⚠️ کانال {username} قبلاً در لیست بود.")


@admin_only
async def remove_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ فرمت: /removechannel @username")
        return

    username = context.args[0]
    if not username.startswith("@"):
        username = "@" + username

    ok = await database.remove_channel(username)
    if ok:
        await update.message.reply_text(f"✅ کانال {username} از لیست حذف شد.")
    else:
        await update.message.reply_text(f"❌ کانال {username} در لیست پیدا نشد.")


def get_upload_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CommandHandler("upload", upload_start)],
        states={
            WAITING_AUDIO: [
                MessageHandler(
                    filters.AUDIO | filters.VOICE | filters.Document.AUDIO,
                    receive_audio,
                ),
                MessageHandler(filters.Document.ALL, receive_audio),
            ],
            WAITING_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)
            ],
            WAITING_ARTIST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_artist)
            ],
            WAITING_DESCRIPTION: [
                CommandHandler("skip", skip_description),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_description),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_upload)],
        allow_reentry=True,
    )
