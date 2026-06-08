"""پنل ادمین — منطق کامل مدیریت ربات."""
import asyncio
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import Settings
from db import DB
from plans import fa

log = logging.getLogger(__name__)

USERS_PER_PAGE = 20

# ─── ابزارهای کمکی ────────────────────────────────────────────────────────────

def is_admin(user_id: int, settings: Settings) -> bool:
    return user_id == settings.admin_telegram_id


def _clear(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("admin_step", None)
    context.user_data.pop("admin_data", None)


def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 تنظیم قیمت USDT",  callback_data="admin:set_price")],
        [InlineKeyboardButton("📊 آمار ربات",         callback_data="admin:stats")],
        [InlineKeyboardButton("👥 لیست کاربران",      callback_data="admin:users:0")],
        [InlineKeyboardButton("🔍 جستجوی کاربر",     callback_data="admin:search")],
        [InlineKeyboardButton("💰 شارژ دستی کاربر",  callback_data="admin:charge")],
        [InlineKeyboardButton("📢 پیام همگانی",       callback_data="admin:broadcast")],
    ])


def _back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 پنل ادمین", callback_data="admin:menu")
    ]])


def _time_ago(ts_str: str | None) -> str:
    if not ts_str:
        return "نامشخص"
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = int((datetime.now(timezone.utc) - dt).total_seconds())
        if secs < 60:    return "همین الان"
        if secs < 3600:  return f"{fa(secs // 60)} دقیقه پیش"
        if secs < 86400: return f"{fa(secs // 3600)} ساعت پیش"
        return f"{fa(secs // 86400)} روز پیش"
    except Exception:
        return ts_str[:16]


def _clean_number(text: str) -> str:
    """اعداد فارسی و کاماها رو پاک می‌کنه."""
    return (
        text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٬،", "0123456789  "))
        .replace(",", "").replace(" ", "")
    )


# ─── /admin ──────────────────────────────────────────────────────────────────

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    if not is_admin(update.effective_user.id, settings):
        await update.message.reply_text("⛔ شما دسترسی ادمین ندارید.")
        return
    log.info("admin[%d] opened panel", update.effective_user.id)
    _clear(context)
    await update.message.reply_text(
        "🔐 <b>پنل ادمین</b>\n\nیکی از گزینه‌ها رو انتخاب کن:",
        parse_mode="HTML",
        reply_markup=_menu_kb(),
    )


# ─── پردازش callback های ادمین ───────────────────────────────────────────────

async def handle_admin_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    query = update.callback_query
    settings: Settings = context.bot_data["settings"]

    if not is_admin(query.from_user.id, settings):
        await query.answer("⛔ دسترسی ندارید.")
        return

    log.info("admin[%d] callback: %s", query.from_user.id, data)

    if data == "admin:menu":
        _clear(context)
        await query.edit_message_text(
            "🔐 <b>پنل ادمین</b>\n\nیکی از گزینه‌ها رو انتخاب کن:",
            parse_mode="HTML",
            reply_markup=_menu_kb(),
        )

    elif data == "admin:set_price":
        await _cb_set_price(query, context)

    elif data == "admin:stats":
        await _cb_stats(query, context)

    elif data.startswith("admin:users:"):
        page = int(data.split(":")[2])
        await _cb_users(query, context, page)

    elif data == "admin:search":
        context.user_data["admin_step"] = "SEARCH"
        await query.edit_message_text(
            "🔍 <b>جستجوی کاربر</b>\n\n"
            "telegram_id عددی یا یوزرنیم (با یا بدون @) رو وارد کن:",
            parse_mode="HTML",
        )

    elif data == "admin:charge":
        context.user_data["admin_step"] = "CHARGE_ID"
        context.user_data["admin_data"] = {}
        await query.edit_message_text(
            "💰 <b>شارژ دستی کاربر</b>\n\n"
            "telegram_id یا یوزرنیم کاربر رو وارد کن:",
            parse_mode="HTML",
        )

    elif data == "admin:broadcast":
        context.user_data["admin_step"] = "BROADCAST_MSG"
        context.user_data["admin_data"] = {}
        await query.edit_message_text(
            "📢 <b>پیام همگانی</b>\n\n"
            "پیام یا عکس+کپشن مورد نظر رو ارسال کن.\n"
            "برای لغو /cancel رو بزن.",
            parse_mode="HTML",
        )

    elif data == "admin:broadcast_confirm":
        await _cb_broadcast_send(query, context)

    elif data == "admin:broadcast_cancel":
        _clear(context)
        await query.edit_message_text("❌ پیام همگانی لغو شد.", reply_markup=_menu_kb())


# ─── تنظیم قیمت USDT ─────────────────────────────────────────────────────────

async def _cb_set_price(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    current  = db.get_setting("usdt_irt_rate")
    updated  = db.get_setting_updated_at("usdt_irt_rate")

    if current:
        info = (
            f"قیمت فعلی: {fa(f'{int(float(current)):,}')} تومان\n"
            f"آخرین بروزرسانی: {_time_ago(updated)}"
        )
    else:
        info = "⚠️ قیمت هنوز تنظیم نشده."

    context.user_data["admin_step"] = "SET_PRICE"
    await query.edit_message_text(
        f"💵 <b>تنظیم قیمت USDT</b>\n\n"
        f"{info}\n\n"
        f"قیمت جدید رو به تومان وارد کن (مثال: 107000):",
        parse_mode="HTML",
    )


# ─── آمار ─────────────────────────────────────────────────────────────────────

async def _cb_stats(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    s = db.get_stats()
    rate = db.get_setting("usdt_irt_rate")
    rate_str = fa(f"{int(float(rate)):,}") if rate else "⚠️ تنظیم نشده"

    rev_today_fa = fa(f"{s['revenue_today']:,}")
    rev_total_fa = fa(f"{s['revenue_total']:,}")
    await query.edit_message_text(
        f"📊 <b>آمار ربات</b>\n\n"
        f"👤 کل کاربران: {fa(s['total_users'])}\n"
        f"🛒 خریدهای امروز: {fa(s['orders_today'])}\n"
        f"🛒 کل خریدها: {fa(s['orders_total'])}\n"
        f"💰 درآمد امروز: {rev_today_fa} تومان\n"
        f"💰 درآمد کل: {rev_total_fa} تومان\n"
        f"✅ شارژهای موفق امروز: {fa(s['charges_today'])}\n"
        f"💵 قیمت USDT: {rate_str} تومان",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin:stats"),
            InlineKeyboardButton("🔙 بازگشت",    callback_data="admin:menu"),
        ]]),
    )


# ─── لیست کاربران ─────────────────────────────────────────────────────────────

async def _cb_users(query, context: ContextTypes.DEFAULT_TYPE, page: int) -> None:
    db: DB = context.bot_data["db"]
    users, total = db.list_users_paginated(page, USERS_PER_PAGE)
    total_pages = max(1, (total + USERS_PER_PAGE - 1) // USERS_PER_PAGE)

    if not users:
        await query.edit_message_text("هیچ کاربری ثبت نشده.", reply_markup=_back_kb())
        return

    lines = [f"👥 <b>کاربران</b> (صفحه {fa(page+1)} از {fa(total_pages)}):\n"]
    for u in users:
        uname = f"@{u.username}" if u.username else "—"
        lines.append(
            f"• <code>{u.telegram_id}</code> {uname}\n"
            f"  موجودی: {fa(f'{int(u.balance_toman):,}')} ت | خرید: {fa(u.total_purchases)}"
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ قبلی", callback_data=f"admin:users:{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("بعدی ▶️", callback_data=f"admin:users:{page+1}"))

    keyboard = [nav] if nav else []
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin:menu")])

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ─── ارسال همگانی ─────────────────────────────────────────────────────────────

async def _cb_broadcast_send(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    d = context.user_data.get("admin_data", {})
    from_chat = d.get("from_chat_id")
    msg_id    = d.get("message_id")

    if not from_chat or not msg_id:
        await query.edit_message_text("❌ پیامی یافت نشد. دوباره تلاش کن.")
        return

    user_ids = db.get_all_user_ids()
    sent = failed = 0
    for uid in user_ids:
        try:
            await query.bot.copy_message(
                chat_id=uid, from_chat_id=from_chat, message_id=msg_id
            )
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    _clear(context)
    log.info("admin broadcast done: sent=%d failed=%d", sent, failed)
    await query.edit_message_text(
        f"📢 <b>پیام همگانی ارسال شد!</b>\n\n"
        f"✅ موفق: {fa(sent)} نفر\n"
        f"❌ ناموفق: {fa(failed)} نفر",
        parse_mode="HTML",
        reply_markup=_back_kb(),
    )


# ─── پردازش ورودی متنی ادمین ─────────────────────────────────────────────────

MAIN_MENU_BUTTONS = {
    "🛒 خرید سرویس", "📋 سرویس‌های من",
    "💰 افزایش موجودی", "👤 حساب کاربری",
    "📚 آموزش", "🎧 پشتیبانی",
}


async def handle_admin_text_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """
    ورودی متنی ادمین رو پردازش می‌کنه.
    True = مدیریت شد، False = ربطی به پنل نداشت یا باید به هندلر عادی بره.
    """
    settings: Settings = context.bot_data["settings"]
    if not is_admin(update.effective_user.id, settings):
        return False

    step = context.user_data.get("admin_step")
    if not step:
        return False

    text = update.message.text or ""

    # دکمه‌های منوی اصلی → state رو پاک کن و بذار هندلر عادی ادامه بده
    if text in MAIN_MENU_BUTTONS:
        _clear(context)
        return False

    log.info("admin[%d] input step=%s", update.effective_user.id, step)

    if step == "SET_PRICE":
        await _input_set_price(update, context, text)
    elif step == "SEARCH":
        await _input_search(update, context, text)
    elif step == "CHARGE_ID":
        await _input_charge_id(update, context, text)
    elif step == "CHARGE_AMOUNT":
        await _input_charge_amount(update, context, text)
    elif step == "CHARGE_REASON":
        await _input_charge_reason(update, context, text)
    elif step == "BROADCAST_MSG":
        await _input_broadcast(update, context)
    elif step == "BROADCAST_CONFIRM_PENDING":
        # کاربر متن فرستاد به جای کلیک روی دکمه
        await update.message.reply_text(
            "⬆️ برای ارسال یا لغو از دکمه‌های بالا استفاده کن."
        )
    else:
        return False

    return True


async def handle_admin_media_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    """مدیریت عکس/فایل در جریان broadcast."""
    settings: Settings = context.bot_data["settings"]
    if not is_admin(update.effective_user.id, settings):
        return False
    if context.user_data.get("admin_step") != "BROADCAST_MSG":
        return False
    await _input_broadcast(update, context)
    return True


# ─── هندلرهای ورودی ادمین ────────────────────────────────────────────────────

async def _input_set_price(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    try:
        price = int(_clean_number(text))
        assert price > 0
    except (ValueError, AssertionError):
        await update.message.reply_text("⚠️ عدد معتبر وارد کن (مثال: 107000):")
        return

    db: DB = context.bot_data["db"]
    db.set_setting("usdt_irt_rate", str(price))
    _clear(context)
    log.info("admin[%d] set usdt_rate=%d", update.effective_user.id, price)
    await update.message.reply_text(
        f"✅ قیمت USDT بروزرسانی شد: {fa(f'{price:,}')} تومان",
        reply_markup=_back_kb(),
    )


async def _input_search(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    db: DB = context.bot_data["db"]
    user = db.find_user(text.strip())
    _clear(context)

    if not user:
        await update.message.reply_text("❌ کاربری یافت نشد.", reply_markup=_back_kb())
        return

    orders = db.list_user_orders(user.telegram_id, limit=5)
    order_lines = ""
    for o in orders:
        order_lines += f"\n  • {fa(o.plan_gb)} گیگ — <code>{o.sub_link or '—'}</code>"

    uname = f"@{user.username}" if user.username else "—"
    await update.message.reply_text(
        f"🔍 <b>اطلاعات کاربر</b>\n\n"
        f"🆔 شناسه: <code>{user.telegram_id}</code>\n"
        f"👤 یوزرنیم: {uname}\n"
        f"💰 موجودی: {fa(f'{int(user.balance_toman):,}')} تومان\n"
        f"🛒 تعداد خرید: {fa(user.total_purchases)}\n"
        f"📅 عضویت: {user.created_at[:10]}"
        + (f"\n\n📋 <b>آخرین سرویس‌ها:</b>{order_lines}" if orders else ""),
        parse_mode="HTML",
        reply_markup=_back_kb(),
    )


async def _input_charge_id(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    db: DB = context.bot_data["db"]
    user = db.find_user(text.strip())
    if not user:
        await update.message.reply_text(
            "❌ کاربری یافت نشد. دوباره وارد کن:"
        )
        return
    context.user_data["admin_data"]["target_id"] = user.telegram_id
    context.user_data["admin_step"] = "CHARGE_AMOUNT"
    uname = f"@{user.username}" if user.username else str(user.telegram_id)
    await update.message.reply_text(
        f"کاربر: {uname}\n"
        f"موجودی فعلی: {fa(f'{int(user.balance_toman):,}')} تومان\n\n"
        f"مبلغ به تومان وارد کن:\n"
        f"(مثبت برای افزایش، منفی برای کاهش — مثال: 50000 یا -20000)"
    )


async def _input_charge_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    try:
        amount = int(_clean_number(text))
    except ValueError:
        await update.message.reply_text(
            "⚠️ عدد معتبر وارد کن (مثال: 50000 یا -20000):"
        )
        return
    context.user_data["admin_data"]["amount"] = amount
    context.user_data["admin_step"] = "CHARGE_REASON"
    await update.message.reply_text(
        "علت تغییر موجودی رو بنویس:\n(اختیاری — برای رد کردن /skip بزن)"
    )


async def _input_charge_reason(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    data      = context.user_data.get("admin_data", {})
    target_id = data.get("target_id")
    amount    = data.get("amount", 0)
    reason    = "" if text.strip().lower() in ("/skip", "skip") else text.strip()
    _clear(context)

    if not target_id:
        await update.message.reply_text("❌ خطا. دوباره تلاش کن.")
        return

    db: DB = context.bot_data["db"]
    new_bal = db.add_balance(target_id, amount)
    sign = "+" if amount >= 0 else ""
    log.info(
        "admin[%d] manual charge: user=%d amount=%d reason=%s",
        update.effective_user.id, target_id, amount, reason,
    )

    await update.message.reply_text(
        f"✅ موجودی بروزرسانی شد.\n"
        f"کاربر: <code>{target_id}</code>\n"
        f"تغییر: {sign}{fa(f'{amount:,}')} تومان\n"
        f"موجودی جدید: {fa(f'{int(new_bal):,}')} تومان"
        + (f"\nعلت: {reason}" if reason else ""),
        parse_mode="HTML",
        reply_markup=_back_kb(),
    )

    try:
        if amount >= 0:
            msg = f"💰 مبلغ {fa(f'{amount:,}')} تومان به کیف پول شما افزوده شد."
        else:
            msg = f"⚠️ مبلغ {fa(f'{abs(amount):,}')} تومان از کیف پول شما کسر شد."
        if reason:
            msg += f"\nعلت: {reason}"
        await context.bot.send_message(target_id, msg)
    except Exception:
        log.warning("could not notify user %d about balance change", target_id)


async def _input_broadcast(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    db: DB = context.bot_data["db"]
    context.user_data["admin_data"]["from_chat_id"] = update.message.chat_id
    context.user_data["admin_data"]["message_id"]   = update.message.message_id
    context.user_data["admin_step"] = "BROADCAST_CONFIRM_PENDING"

    count = db.get_user_count()
    await update.message.reply_text(
        f"📢 پیام دریافت شد.\n\n"
        f"ارسال به <b>{fa(count)}</b> کاربر؟",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ ارسال به همه", callback_data="admin:broadcast_confirm"),
            InlineKeyboardButton("❌ لغو",          callback_data="admin:broadcast_cancel"),
        ]]),
    )
