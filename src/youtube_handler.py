"""هندلر Conversation برای دریافت ویدیو از تلگرام و آپلود روی یوتیوب Shorts."""

import logging
import os

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from .youtube_uploader import upload_short

log = logging.getLogger(__name__)

TITLE, DESCRIPTION, HASHTAGS, TAGS, CONFIRM = range(5)

_DOWNLOADS_DIR = "downloads"


async def _cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _cleanup(context)
    await update.message.reply_text("❌ لغو شد.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


def _cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    path = context.user_data.pop("video_path", None)
    if path and os.path.exists(path):
        os.remove(path)
    context.user_data.clear()


async def receive_video(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    video = msg.video or (msg.document if msg.document and msg.document.mime_type and msg.document.mime_type.startswith("video/") else None)
    if not video:
        await msg.reply_text("لطفاً یه فایل ویدیو بفرست.")
        return ConversationHandler.END

    os.makedirs(_DOWNLOADS_DIR, exist_ok=True)
    tg_file = await context.bot.get_file(video.file_id)
    video_path = os.path.join(_DOWNLOADS_DIR, f"{video.file_id}.mp4")
    await tg_file.download_to_drive(video_path)

    context.user_data["video_path"] = video_path
    await msg.reply_text(
        "✅ ویدیو دریافت شد!\n\n🎬 *تایتل* ویدیو رو بفرست:",
        parse_mode="Markdown",
    )
    return TITLE


async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["title"] = update.message.text.strip()
    await update.message.reply_text(
        "📝 *توضیحات (Description)* ویدیو رو بفرست:",
        parse_mode="Markdown",
    )
    return DESCRIPTION


async def receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["description"] = update.message.text.strip()
    await update.message.reply_text(
        "🔢 *هشتگ‌ها* رو بفرست (با کاما جدا کن):\n"
        "مثال: `طبیعت, ایران, سفر`",
        parse_mode="Markdown",
    )
    return HASHTAGS


async def receive_hashtags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    hashtags = [h.strip().lstrip("#") for h in raw.split(",") if h.strip()]
    context.user_data["hashtags"] = hashtags
    await update.message.reply_text(
        "🏷️ *تگ‌ها (Tags)* رو بفرست (با کاما جدا کن):\n"
        "مثال: `nature, travel, iran`",
        parse_mode="Markdown",
    )
    return TAGS


async def receive_tags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = update.message.text.strip()
    tags = [t.strip() for t in raw.split(",") if t.strip()]
    context.user_data["tags"] = tags

    d = context.user_data
    hashtag_preview = "  ".join(f"#{h}" for h in d["hashtags"])
    summary = (
        "✅ *خلاصه اطلاعات ویدیو:*\n\n"
        f"🎬 تایتل: `{d['title']}`\n"
        f"📝 توضیحات: _{d['description'][:120]}{'...' if len(d['description']) > 120 else ''}_\n"
        f"#️⃣ هشتگ‌ها: `{hashtag_preview}`\n"
        f"🏷️ تگ‌ها: `{', '.join(d['tags'])}`\n\n"
        "آپلود بشه روی یوتیوب Shorts؟"
    )

    keyboard = [["✅ بله، آپلود کن", "❌ لغو"]]
    await update.message.reply_text(
        summary,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return CONFIRM


async def confirm_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message.text != "✅ بله، آپلود کن":
        _cleanup(context)
        await update.message.reply_text("❌ لغو شد.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    await update.message.reply_text(
        "⏳ در حال آپلود روی یوتیوب...\nممکنه چند دقیقه طول بکشه.",
        reply_markup=ReplyKeyboardRemove(),
    )

    d = context.user_data
    try:
        url = upload_short(
            video_path=d["video_path"],
            title=d["title"],
            description=d["description"],
            hashtags=d["hashtags"],
            tags=d["tags"],
        )
        await update.message.reply_text(
            f"✅ *آپلود با موفقیت انجام شد!*\n\n🔗 {url}",
            parse_mode="Markdown",
        )
    except FileNotFoundError as e:
        log.error("YouTube token missing: %s", e)
        await update.message.reply_text(
            f"⚠️ ربات هنوز به یوتیوب وصل نشده.\n"
            "ادمین باید اول `youtube_auth.py` رو اجرا کنه."
        )
    except Exception as e:
        log.exception("YouTube upload failed: %s", e)
        await update.message.reply_text(f"❌ خطا در آپلود:\n`{e}`", parse_mode="Markdown")

    _cleanup(context)
    return ConversationHandler.END


def build_youtube_conv_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            MessageHandler(filters.VIDEO, receive_video),
            MessageHandler(filters.Document.VIDEO, receive_video),
        ],
        states={
            TITLE:       [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_description)],
            HASHTAGS:    [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_hashtags)],
            TAGS:        [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_tags)],
            CONFIRM:     [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_upload)],
        },
        fallbacks=[CommandHandler("cancel", _cmd_cancel)],
        allow_reentry=True,
    )
