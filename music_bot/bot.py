import logging
import os
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config import BOT_TOKEN, LOG_FILE, SONGS_DIR
import database
import admin as admin_module

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


async def _check_membership(bot, user_id: int, channels) -> list:
    """Return the list of channels the user has NOT joined."""
    missing = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch["username"], user_id=user_id)
            if member.status in ("left", "kicked"):
                missing.append(ch)
        except TelegramError:
            missing.append(ch)
    return missing


def _build_join_keyboard(missing_channels, song_id: int) -> InlineKeyboardMarkup:
    keyboard = []
    for ch in missing_channels:
        keyboard.append([InlineKeyboardButton(f"📢 {ch['title']}", url=ch["link"])])
    keyboard.append([InlineKeyboardButton("عضو شدم ✅", callback_data=f"check_{song_id}")])
    return InlineKeyboardMarkup(keyboard)


async def _send_song(bot, chat_id: int, song) -> None:
    caption = f"🎵 <b>{song['title']}</b>\n🎤 {song['artist']}"
    if song["description"]:
        caption += f"\n\n📝 {song['description']}"
    await bot.send_audio(
        chat_id=chat_id,
        audio=song["file_id"],
        caption=caption,
        parse_mode="HTML",
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            f"سلام {user.first_name}! 👋\n\n"
            "🎵 به ربات موزیک خوش اومدی!\n"
            "برای دریافت آهنگ از لینک‌های مخصوص استفاده کن."
        )
        return

    try:
        song_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ لینک نامعتبره!")
        return

    song = await database.get_song(song_id)
    if not song:
        await update.message.reply_text(
            "❌ این آهنگ دیگه موجود نیست یا حذف شده.\n"
            "شاید لینک قدیمیه! 🤔"
        )
        return

    channels = await database.get_channels()
    if channels:
        missing = await _check_membership(context.bot, user.id, channels)
        if missing:
            markup = _build_join_keyboard(missing, song_id)
            await update.message.reply_text(
                f"سلام {user.first_name}! 🎵\n\n"
                f"آهنگ «<b>{song['title']}</b>» آماده‌ست برات،\n"
                "ولی قبلش باید عضو کانال‌های زیر بشی 🔒\n\n"
                "بعد از عضو شدن، دکمه «عضو شدم ✅» رو بزن:",
                reply_markup=markup,
                parse_mode="HTML",
            )
            return

    await _send_song(context.bot, user.id, song)


async def membership_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user = update.effective_user

    try:
        song_id = int(query.data.split("_", 1)[1])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ خطایی رخ داد. دوباره از لینک آهنگ استفاده کن.")
        return

    song = await database.get_song(song_id)
    if not song:
        await query.edit_message_text(
            "❌ این آهنگ دیگه موجود نیست یا حذف شده.\n"
            "شاید لینک قدیمیه! 🤔"
        )
        return

    channels = await database.get_channels()
    missing = await _check_membership(context.bot, user.id, channels)

    if missing:
        markup = _build_join_keyboard(missing, song_id)
        names = "، ".join(ch["title"] for ch in missing)
        await query.edit_message_text(
            f"هنوز عضو این کانال‌ها نشدی 🔒\n\n"
            f"📢 {names}\n\n"
            "عضو بشو و دوباره دکمه «عضو شدم ✅» رو بزن:",
            reply_markup=markup,
        )
        return

    await query.edit_message_text(
        f"✅ عالیه! عضویتت تأیید شد.\n\n"
        f"🎶 آهنگ «{song['title']}» داره برات فرستاده میشه..."
    )
    await _send_song(context.bot, user.id, song)


async def error_handler(update: Optional[Update], context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception", exc_info=context.error)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ یه مشکل پیش اومد! لطفاً دوباره امتحان کن."
            )
        except TelegramError:
            pass


async def _post_init(application: Application) -> None:
    await database.init_db()
    os.makedirs(SONGS_DIR, exist_ok=True)
    logger.info("Database initialized. Bot is ready 🎵")


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).post_init(_post_init).build()

    app.add_handler(admin_module.get_upload_handler())

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("songs", admin_module.list_songs))
    app.add_handler(CommandHandler("deletesong", admin_module.delete_song_cmd))
    app.add_handler(CommandHandler("channels", admin_module.list_channels))
    app.add_handler(CommandHandler("addchannel", admin_module.add_channel_cmd))
    app.add_handler(CommandHandler("removechannel", admin_module.remove_channel_cmd))

    app.add_handler(CallbackQueryHandler(membership_callback, pattern=r"^check_\d+$"))
    app.add_error_handler(error_handler)

    logger.info("Starting bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
