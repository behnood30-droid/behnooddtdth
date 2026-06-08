"""هندلرهای اصلی ربات تلگرام."""
import json
import logging
import os
from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
)

from admin import (
    cmd_admin,
    handle_admin_callback,
    handle_admin_media_input,
    handle_admin_text_input,
)
from config import Settings
from db import DB
from pasarguard import PasarGuardClient
from payment import (
    on_cancel_payment,
    on_check_payment,
    on_pay_plisio,
    on_pay_pirooz,
    show_payment_methods,
)
from plans import PLANS, get_plan
from utils import bytes_to_gb, fa, progress_bar, to_jalali, unix_to_jalali, user_level

log = logging.getLogger(__name__)
SEP = "━━━━━━━━━━━━━━━━━━━━"

MAIN_BUTTONS = {
    "🛒 خرید سرویس",
    "📋 سرویس‌های من",
    "👤 حساب کاربری",
    "📚 آموزش",
    "🎧 پشتیبانی",
}

TUTORIAL_ANDROID = (
    "📱 *اتصال در اندروید (v2rayNG)*\n"
    f"{SEP}\n\n"
    "۱. v2rayNG رو از گوگل‌پلی نصب کن\n"
    "۲. آیکون + رو بزن\n"
    "۳. «Import config from clipboard» رو انتخاب کن\n"
    "۴. لینک Sub رو paste کن\n"
    "۵. «Update subscriptions» رو بزن\n"
    "۶. روی سرور مورد نظر بزن و کانکت کن ✅"
)

TUTORIAL_IOS = (
    "🍎 *اتصال در iOS (Streisand)*\n"
    f"{SEP}\n\n"
    "۱. Streisand رو از App Store نصب کن\n"
    "۲. + رو بزن\n"
    "۳. «Subscribe» رو انتخاب کن\n"
    "۴. لینک Sub رو وارد کن\n"
    "۵. Save رو بزن\n"
    "۶. کانکت کن ✅"
)

TUTORIAL_WIN = (
    "💻 *اتصال در ویندوز (v2rayN)*\n"
    f"{SEP}\n\n"
    "۱. v2rayN رو از GitHub دانلود کن\n"
    "۲. منوی Servers رو باز کن\n"
    "۳. «Add subscription server» رو بزن\n"
    "۴. لینک Sub رو وارد کن\n"
    "۵. «Update subscription» رو بزن\n"
    "۶. روی سرور دابل‌کلیک کن و کانکت کن ✅"
)

TUTORIAL_FAQ = (
    "❓ *سوالات متداول*\n"
    f"{SEP}\n\n"
    "*لینک Sub چیه؟*\n"
    "یه لینک اشتراک که وقتی سرورها تغییر کنن، خودکار آپدیت میشه. "
    "بهتر از کانفیگ مستقیمه.\n\n"
    "*چرا اتصال برقرار نمیشه؟*\n"
    "• مطمئن شو سرویسم هنوز فعاله و منقضی نشده\n"
    "• «Update subscriptions» رو بزن\n"
    "• اگه مشکل ادامه داشت با پشتیبانی تماس بگیر\n\n"
    "*سرویس چقدر طول میکشه بعد از پرداخت؟*\n"
    "معمولاً کمتر از ۱ دقیقه. اگه بیشتر طول کشید با پشتیبانی در تماس باش."
)


# ─── کیبورد اصلی ─────────────────────────────────────────────────────────────

def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🛒 خرید سرویس", "📋 سرویس‌های من"],
            ["👤 حساب کاربری", "📚 آموزش"],
            ["🎧 پشتیبانی"],
        ],
        resize_keyboard=True,
    )


# ─── میان‌افزار ──────────────────────────────────────────────────────────────

async def _ensure_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
    u = update.effective_user
    db: DB = context.bot_data["db"]
    db.ensure_user(u.id, u.username, u.first_name or "")


# ─── /start ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = update.effective_user.first_name or "دوست عزیز"
    await update.message.reply_text(
        f"سلام {name} 👋\n\n"
        f"به فروشگاه VPN خوش اومدی! 🌐\n"
        f"برای شروع یکی از گزینه‌های زیر رو انتخاب کن 👇",
        reply_markup=main_keyboard(),
    )


# ─── هندلر پیام متنی ─────────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # ادمین در حال استفاده از پنل؟
    if await handle_admin_text_input(update, context):
        return

    text = update.message.text or ""
    dispatch = {
        "🛒 خرید سرویس":   _on_buy,
        "📋 سرویس‌های من": _on_my_services,
        "👤 حساب کاربری":  _on_account,
        "📚 آموزش":         _on_tutorial_menu,
        "🎧 پشتیبانی":      _on_support,
    }
    handler = dispatch.get(text)
    if handler:
        await handler(update, context)


async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await handle_admin_media_input(update, context)


# ─── خرید سرویس ──────────────────────────────────────────────────────────────

async def _on_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(p.label, callback_data=f"plan:{p.id}")] for p in PLANS]
    )
    await update.message.reply_text(
        f"🛒 *فروشگاه سرویس*\n{SEP}\n\nپلن مورد نظرت رو انتخاب کن 👇",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ─── سرویس‌های من ─────────────────────────────────────────────────────────────

async def _on_my_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    panel: PasarGuardClient = context.bot_data["panel"]
    payments = db.get_user_delivered_payments(update.effective_user.id)

    if not payments:
        await update.message.reply_text(
            f"📋 *سرویس‌های من*\n{SEP}\n\n"
            f"❌ هنوز سرویسی نخریدی\n\n"
            f"از منوی پایین «🛒 خرید سرویس» رو بزن",
            parse_mode="Markdown",
        )
        return

    for i, payment in enumerate(payments, 1):
        try:
            info = await panel.get_user(payment.panel_username)
        except Exception:
            info = {}

        used = info.get("used_traffic", 0)
        total = info.get("data_limit", payment.plan_gb * 1_073_741_824)
        expire_ts = info.get("expire")
        status = info.get("status", "active")
        panel_status = {
            "active": "🟢 فعال",
            "disabled": "🟡 غیرفعال",
            "expired": "🔴 منقضی",
            "limited": "🟠 محدود",
        }.get(status, f"🔘 {status}")

        used_gb = bytes_to_gb(used)
        total_gb = bytes_to_gb(total)
        remaining_gb = max(0.0, round(total_gb - used_gb, 2))
        pct = int((used / total * 100) if total > 0 else 0)
        bar = progress_bar(used, total)

        created_str = to_jalali(payment.created_at)
        expire_str = unix_to_jalali(expire_ts) if expire_ts else to_jalali(payment.expires_at)
        days_left = 0
        if expire_ts:
            days_left = max(0, int((expire_ts - datetime.now(timezone.utc).timestamp()) / 86400))

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔗 لینک اشتراک",       callback_data=f"sub:{payment.payment_id}"),
                InlineKeyboardButton("🔐 کانفیگ‌های مستقیم", callback_data=f"cfg:{payment.payment_id}"),
            ],
            [InlineKeyboardButton("📚 آموزش اتصال", callback_data="tut")],
        ])

        await update.message.reply_text(
            f"{fa(i)}. 📦 *{fa(payment.plan_gb)} گیگ* | {panel_status}\n"
            f"{SEP}\n\n"
            f"📊 *مصرف:*\n"
            f"{bar}\n"
            f"{fa(used_gb)} از {fa(total_gb)} گیگ ({fa(pct)}%)\n"
            f"💾 باقیمانده: *{fa(remaining_gb)} گیگ*\n\n"
            f"⏱ *زمان:*\n"
            f"📅 شروع: {created_str}\n"
            f"📅 انقضا: {expire_str}\n"
            f"⏰ باقیمانده: *{fa(days_left)} روز*\n"
            f"{SEP}",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


# ─── حساب کاربری ─────────────────────────────────────────────────────────────

async def _on_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    tid = update.effective_user.id
    user = db.get_user(tid)
    if not user:
        await update.message.reply_text("خطا. /start رو بزن.")
        return

    stats = db.get_user_stats(tid)
    active_count = len(db.get_user_delivered_payments(tid, limit=20))
    level = user_level(stats["count"])
    joined = to_jalali(user.created_at)
    uname = f"@{user.username}" if user.username else "—"

    await update.message.reply_text(
        f"👤 *حساب کاربری*\n{SEP}\n\n"
        f"🆔 شناسه: `{user.telegram_id}`\n"
        f"👋 نام: {user.first_name}\n"
        f"📱 یوزرنیم: {uname}\n\n"
        f"{SEP}\n\n"
        f"🛒 تعداد خریدها: *{fa(stats['count'])}*\n"
        f"💎 مجموع خرید: *{fa(stats['sum'])} تومان*\n"
        f"🟢 سرویس‌های تحویل‌شده: *{fa(active_count)}*\n\n"
        f"{SEP}\n\n"
        f"📅 عضو از: {joined}\n"
        f"🎖 سطح: {level}",
        parse_mode="Markdown",
    )


# ─── آموزش ───────────────────────────────────────────────────────────────────

async def _on_tutorial_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 اتصال در اندروید (v2rayNG)", callback_data="tut:android")],
        [InlineKeyboardButton("🍎 اتصال در iOS (Streisand)",   callback_data="tut:ios")],
        [InlineKeyboardButton("💻 اتصال در ویندوز",            callback_data="tut:windows")],
        [InlineKeyboardButton("❓ سوالات متداول",              callback_data="tut:faq")],
    ])
    await update.message.reply_text(
        f"📚 *مرکز آموزش*\n{SEP}\n\nبرای دیدن آموزش، یکی رو انتخاب کن:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ─── پشتیبانی ────────────────────────────────────────────────────────────────

async def _on_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    await update.message.reply_text(
        f"🎧 *پشتیبانی*\n{SEP}\n\n"
        f"📞 اگه سوال یا مشکلی داری:\n\n"
        f"👤 پیام به پشتیبانی:\n"
        f"   @{settings.support_username}\n\n"
        f"⏰ ساعات پاسخگویی:\n"
        f"   ۱۰ صبح تا ۲ بامداد\n\n"
        f"{SEP}",
        parse_mode="Markdown",
    )


# ─── /cancel ─────────────────────────────────────────────────────────────────

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("admin_step", None)
    context.user_data.pop("admin_data", None)
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=main_keyboard())


# ─── Callback dispatcher ──────────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # آموزش
    if data == "tut" or data.startswith("tut:"):
        part = data.split(":", 1)[1] if ":" in data else "menu"
        texts = {
            "android": TUTORIAL_ANDROID,
            "ios":     TUTORIAL_IOS,
            "windows": TUTORIAL_WIN,
            "faq":     TUTORIAL_FAQ,
        }
        if part in texts:
            await query.edit_message_text(texts[part], parse_mode="Markdown",
                                          reply_markup=InlineKeyboardMarkup([[
                                              InlineKeyboardButton("🔙 برگشت", callback_data="tut:menu")
                                          ]]))
        else:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("📱 اندروید (v2rayNG)", callback_data="tut:android")],
                [InlineKeyboardButton("🍎 iOS (Streisand)",   callback_data="tut:ios")],
                [InlineKeyboardButton("💻 ویندوز",            callback_data="tut:windows")],
                [InlineKeyboardButton("❓ سوالات متداول",    callback_data="tut:faq")],
            ])
            await query.edit_message_text(
                f"📚 *مرکز آموزش*\n{SEP}\n\nیکی رو انتخاب کن:",
                parse_mode="Markdown", reply_markup=kb
            )
        return

    # نمایش سرویس‌های من از طریق callback
    if data == "my_svcs":
        await query.message.reply_text("📋 از منوی پایین «📋 سرویس‌های من» رو بزن.")
        return

    # پلن انتخاب شد
    if data.startswith("plan:"):
        plan_id = int(data.split(":")[1])
        await show_payment_methods(query, context, plan_id)
        return

    # روش پرداخت
    if data.startswith("pm:"):
        _, plan_id_s, method = data.split(":")
        plan_id = int(plan_id_s)
        if method == "pirooz":
            await on_pay_pirooz(query, context, plan_id)
        elif method == "plisio":
            await on_pay_plisio(query, context, plan_id)
        return

    # بررسی وضعیت
    if data.startswith("chk:"):
        await on_check_payment(query, context, data[4:])
        return

    # لغو سفارش
    if data.startswith("cnl:"):
        await on_cancel_payment(query, context, data[4:])
        return

    # لینک Sub
    if data.startswith("sub:"):
        pid = data[4:]
        db: DB = context.bot_data["db"]
        payment = db.get_payment(pid)
        if not payment or payment.telegram_id != query.from_user.id:
            await query.answer("⛔ دسترسی ندارید.", show_alert=True)
            return
        await query.answer()
        await query.message.reply_text(
            f"🔗 *لینک اشتراک:*\n`{payment.sub_link}`",
            parse_mode="Markdown",
        )
        return

    # کانفیگ‌های مستقیم
    if data.startswith("cfg:"):
        pid = data[4:]
        db: DB = context.bot_data["db"]
        payment = db.get_payment(pid)
        if not payment or payment.telegram_id != query.from_user.id:
            await query.answer("⛔ دسترسی ندارید.", show_alert=True)
            return
        if not payment.configs:
            await query.answer("کانفیگی یافت نشد.", show_alert=True)
            return
        try:
            links = json.loads(payment.configs)
        except Exception:
            links = [payment.configs]
        sep = "\n\n━━━━━━━━━━━━━━━━━━━━\n\n"
        configs_text = sep.join(f"`{lnk}`" for lnk in links)
        await query.message.reply_text(
            f"🔐 *کانفیگ‌های مستقیم*\n{SEP}\n\n{configs_text}",
            parse_mode="Markdown",
        )
        return

    # انصراف از خرید
    if data == "cancel_order":
        await query.edit_message_text("❌ سفارش لغو شد.")
        return

    # ادمین callbacks
    if data.startswith("admin:"):
        await handle_admin_callback(update, context, data)
        return


# ─── ثبت هندلرها ─────────────────────────────────────────────────────────────

def register_handlers(app: Application) -> None:
    app.add_handler(TypeHandler(Update, _ensure_user), group=-1)

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("admin",  cmd_admin))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_media))
    app.add_handler(CallbackQueryHandler(handle_callback))
