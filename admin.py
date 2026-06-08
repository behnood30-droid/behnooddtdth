"""پنل ادمین."""
import asyncio
import logging
from datetime import datetime, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import Settings
from db import DB
from delivery import create_config_and_deliver
from utils import fa, to_jalali

log = logging.getLogger(__name__)
USERS_PER_PAGE = 20
SEP = "━━━━━━━━━━━━━━━━━━━━"

MAIN_MENU_BUTTONS = {
    "🛒 خرید سرویس", "📋 سرویس‌های من",
    "👤 حساب کاربری", "📚 آموزش", "🎧 پشتیبانی",
}


def is_admin(user_id: int, settings: Settings) -> bool:
    return user_id == settings.admin_telegram_id


def _clear(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("admin_step", None)
    context.user_data.pop("admin_data", None)


def _menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 تنظیم قیمت USDT",       callback_data="admin:set_price")],
        [InlineKeyboardButton("📊 آمار ربات",              callback_data="admin:stats")],
        [InlineKeyboardButton("👥 لیست کاربران",           callback_data="admin:users:0")],
        [InlineKeyboardButton("🔍 جستجوی کاربر",          callback_data="admin:search")],
        [InlineKeyboardButton("⏳ پرداخت‌های در انتظار",  callback_data="admin:pending")],
        [InlineKeyboardButton("🔧 پرداخت‌های ناموفق",     callback_data="admin:failed")],
        [InlineKeyboardButton("📢 پیام همگانی",            callback_data="admin:broadcast")],
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
    _clear(context)
    await update.message.reply_text(
        "🔐 *پنل ادمین*\n\nیکی از گزینه‌ها رو انتخاب کن:",
        parse_mode="Markdown",
        reply_markup=_menu_kb(),
    )


# ─── Callback dispatcher ─────────────────────────────────────────────────────

async def handle_admin_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    query = update.callback_query
    settings: Settings = context.bot_data["settings"]

    if not is_admin(query.from_user.id, settings):
        await query.answer("⛔ دسترسی ندارید.")
        return

    if data == "admin:menu":
        _clear(context)
        await query.edit_message_text(
            "🔐 *پنل ادمین*\n\nیکی از گزینه‌ها رو انتخاب کن:",
            parse_mode="Markdown",
            reply_markup=_menu_kb(),
        )
    elif data == "admin:set_price":
        await _cb_set_price(query, context)
    elif data == "admin:stats":
        await _cb_stats(query, context)
    elif data.startswith("admin:users:"):
        await _cb_users(query, context, int(data.split(":")[2]))
    elif data == "admin:search":
        context.user_data["admin_step"] = "SEARCH"
        await query.edit_message_text(
            "🔍 *جستجوی کاربر*\n\ntelegram\\_id یا یوزرنیم (با یا بدون @) رو وارد کن:",
            parse_mode="Markdown",
        )
    elif data == "admin:pending":
        await _cb_pending(query, context)
    elif data == "admin:failed":
        await _cb_failed(query, context)
    elif data.startswith("admin:approve:"):
        await _cb_approve(query, context, data.split(":", 2)[2])
    elif data.startswith("admin:reject:"):
        db: DB = context.bot_data["db"]
        pid = data.split(":", 2)[2]
        db.expire_payment(pid)
        await query.answer("❌ سفارش لغو شد.")
        await _cb_pending(query, context)
    elif data.startswith("admin:retry:"):
        await _cb_retry(query, context, data.split(":", 2)[2])
    elif data == "admin:broadcast":
        context.user_data["admin_step"] = "BROADCAST_MSG"
        context.user_data["admin_data"] = {}
        await query.edit_message_text(
            "📢 *پیام همگانی*\n\nپیام یا عکس+کپشن مورد نظر رو ارسال کن.\n"
            "برای لغو /cancel رو بزن.",
            parse_mode="Markdown",
        )
    elif data == "admin:broadcast_confirm":
        await _cb_broadcast_send(query, context)
    elif data == "admin:broadcast_cancel":
        _clear(context)
        await query.edit_message_text("❌ پیام همگانی لغو شد.", reply_markup=_menu_kb())


# ─── تنظیم قیمت USDT ─────────────────────────────────────────────────────────

async def _cb_set_price(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    current = db.get_setting("usdt_irt_rate")
    updated = db.get_setting_updated_at("usdt_irt_rate")
    if current:
        info = f"قیمت فعلی: {fa(int(float(current)))} تومان\nآخرین بروزرسانی: {_time_ago(updated)}"
    else:
        info = "⚠️ قیمت هنوز تنظیم نشده."
    context.user_data["admin_step"] = "SET_PRICE"
    await query.edit_message_text(
        f"💵 *تنظیم قیمت USDT*\n\n{info}\n\n"
        f"قیمت جدید رو به تومان وارد کن (مثال: 107000):",
        parse_mode="Markdown",
    )


# ─── آمار ────────────────────────────────────────────────────────────────────

async def _cb_stats(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    s = db.get_stats()
    rate = db.get_setting("usdt_irt_rate")
    rate_str = fa(int(float(rate))) + " تومان" if rate else "⚠️ تنظیم نشده"
    rev_today = fa(s["revenue_today"])
    rev_total = fa(s["revenue_total"])
    await query.edit_message_text(
        f"📊 *آمار ربات*\n{SEP}\n\n"
        f"👤 کل کاربران: {fa(s['total_users'])}\n"
        f"🛒 خریدهای امروز: {fa(s['orders_today'])}\n"
        f"🛒 کل خریدها: {fa(s['orders_total'])}\n"
        f"💰 درآمد امروز: {rev_today} تومان\n"
        f"💰 درآمد کل: {rev_total} تومان\n"
        f"⏳ پرداخت‌های در انتظار: {fa(s['pending_count'])}\n"
        f"🔧 پرداخت‌های ناموفق: {fa(s['failed_count'])}\n"
        f"💵 قیمت USDT: {rate_str}",
        parse_mode="Markdown",
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

    lines = [f"👥 *کاربران* (صفحه {fa(page+1)} از {fa(total_pages)}):\n"]
    for u in users:
        uname = f"@{u['username']}" if u.get("username") else "—"
        lines.append(
            f"• `{u['telegram_id']}` {uname}\n"
            f"  خرید: {fa(u['total_purchases'])} | مجموع: {fa(int(u['purchase_sum']))} تومان"
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
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# ─── پرداخت‌های در انتظار ────────────────────────────────────────────────────

async def _cb_pending(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    payments = db.get_payments_by_status("pending", limit=8)

    if not payments:
        await query.edit_message_text(
            "✅ هیچ پرداخت در انتظاری وجود ندارد.", reply_markup=_back_kb()
        )
        return

    lines = [f"⏳ *پرداخت‌های در انتظار* ({fa(len(payments))} عدد):\n"]
    keyboard_rows = []
    for p in payments:
        method_fa = {"pirooz": "ریالی", "plisio": "کریپتو"}.get(
            p.payment_method, p.payment_method
        )
        lines.append(
            f"• `{p.payment_id[:20]}` — {fa(p.plan_gb)}G — {method_fa} — {_time_ago(p.created_at)}"
        )
        keyboard_rows.append([
            InlineKeyboardButton(f"✅ {p.payment_id[:12]}", callback_data=f"admin:approve:{p.payment_id}"),
            InlineKeyboardButton("❌ لغو", callback_data=f"admin:reject:{p.payment_id}"),
        ])
    keyboard_rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin:menu")])

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
    )


async def _cb_approve(query, context: ContextTypes.DEFAULT_TYPE, payment_id: str) -> None:
    db: DB = context.bot_data["db"]
    settings: Settings = context.bot_data["settings"]
    panel = context.bot_data["panel"]
    payment = db.get_payment(payment_id)
    if not payment or payment.status != "pending":
        await query.answer("این سفارش دیگه pending نیست.")
        return
    db.confirm_payment(payment_id)
    await query.answer("✅ تأیید شد. در حال تحویل...")
    await create_config_and_deliver(
        payment_id=payment_id,
        bot=context.bot, db=db, panel=panel, settings=settings,
    )
    await _cb_pending(query, context)


# ─── پرداخت‌های ناموفق ───────────────────────────────────────────────────────

async def _cb_failed(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    payments = db.get_payments_by_status("failed", limit=8)

    if not payments:
        await query.edit_message_text(
            "✅ هیچ پرداخت ناموفقی وجود ندارد.", reply_markup=_back_kb()
        )
        return

    lines = [f"🔧 *پرداخت‌های ناموفق* ({fa(len(payments))} عدد):\n"]
    keyboard_rows = []
    for p in payments:
        lines.append(
            f"• `{p.payment_id[:20]}` — {fa(p.plan_gb)}G — {_time_ago(p.created_at)}"
        )
        keyboard_rows.append([
            InlineKeyboardButton(f"🔄 {p.payment_id[:12]}", callback_data=f"admin:retry:{p.payment_id}"),
        ])
    keyboard_rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin:menu")])

    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
    )


async def _cb_retry(query, context: ContextTypes.DEFAULT_TYPE, payment_id: str) -> None:
    db: DB = context.bot_data["db"]
    settings: Settings = context.bot_data["settings"]
    panel = context.bot_data["panel"]
    payment = db.get_payment(payment_id)
    if not payment or payment.status != "failed":
        await query.answer("این سفارش در وضعیت failed نیست.")
        return
    db.confirm_payment(payment_id)
    await query.answer("🔄 در حال تلاش مجدد...")
    await create_config_and_deliver(
        payment_id=payment_id,
        bot=context.bot, db=db, panel=panel, settings=settings,
    )
    await _cb_failed(query, context)


# ─── ارسال همگانی ─────────────────────────────────────────────────────────────

async def _cb_broadcast_send(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    d = context.user_data.get("admin_data", {})
    from_chat = d.get("from_chat_id")
    msg_id = d.get("message_id")
    if not from_chat or not msg_id:
        await query.edit_message_text("❌ پیامی یافت نشد.")
        return
    user_ids = db.get_all_user_ids()
    sent = failed = 0
    for uid in user_ids:
        try:
            await query.bot.copy_message(chat_id=uid, from_chat_id=from_chat, message_id=msg_id)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    _clear(context)
    await query.edit_message_text(
        f"📢 *پیام همگانی ارسال شد!*\n\n✅ موفق: {fa(sent)} نفر\n❌ ناموفق: {fa(failed)} نفر",
        parse_mode="Markdown",
        reply_markup=_back_kb(),
    )


# ─── ورودی متنی ادمین ────────────────────────────────────────────────────────

async def handle_admin_text_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    settings: Settings = context.bot_data["settings"]
    if not is_admin(update.effective_user.id, settings):
        return False
    step = context.user_data.get("admin_step")
    if not step:
        return False
    text = update.message.text or ""
    if text in MAIN_MENU_BUTTONS:
        _clear(context)
        return False
    log.info("admin[%d] input step=%s", update.effective_user.id, step)
    if step == "SET_PRICE":
        await _input_set_price(update, context, text)
    elif step == "SEARCH":
        await _input_search(update, context, text)
    elif step == "BROADCAST_MSG":
        await _input_broadcast(update, context)
    elif step == "BROADCAST_CONFIRM_PENDING":
        await update.message.reply_text("⬆️ برای ارسال یا لغو از دکمه‌های بالا استفاده کن.")
    else:
        return False
    return True


async def handle_admin_media_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> bool:
    settings: Settings = context.bot_data["settings"]
    if not is_admin(update.effective_user.id, settings):
        return False
    if context.user_data.get("admin_step") != "BROADCAST_MSG":
        return False
    await _input_broadcast(update, context)
    return True


async def _input_set_price(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    try:
        price = int(_clean_number(text))
        assert price > 0
    except (ValueError, AssertionError):
        await update.message.reply_text("⚠️ عدد معتبر وارد کن (مثال: 107000):")
        return
    db: DB = context.bot_data["db"]
    db.set_setting("usdt_irt_rate", str(price))
    _clear(context)
    await update.message.reply_text(
        f"✅ قیمت USDT بروزرسانی شد: {fa(price)} تومان",
        reply_markup=_back_kb(),
    )


async def _input_search(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    db: DB = context.bot_data["db"]
    user = db.find_user(text.strip())
    _clear(context)
    if not user:
        await update.message.reply_text("❌ کاربری یافت نشد.", reply_markup=_back_kb())
        return
    payments = db.get_user_delivered_payments(user.telegram_id)
    order_lines = ""
    for p in payments:
        order_lines += f"\n  • {fa(p.plan_gb)} گیگ — `{p.sub_link or '—'}`"
    uname = f"@{user.username}" if user.username else "—"
    stats = db.get_user_stats(user.telegram_id)
    await update.message.reply_text(
        f"🔍 *اطلاعات کاربر*\n\n"
        f"🆔 شناسه: `{user.telegram_id}`\n"
        f"👤 یوزرنیم: {uname}\n"
        f"🛒 تعداد خرید: {fa(user.total_purchases)}\n"
        f"💰 مجموع خرید: {fa(stats['sum'])} تومان\n"
        f"📅 عضویت: {user.created_at[:10]}"
        + (f"\n\n📋 *آخرین سرویس‌ها:*{order_lines}" if payments else ""),
        parse_mode="Markdown",
        reply_markup=_back_kb(),
    )


async def _input_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    if "admin_data" not in context.user_data:
        context.user_data["admin_data"] = {}
    context.user_data["admin_data"]["from_chat_id"] = update.message.chat_id
    context.user_data["admin_data"]["message_id"] = update.message.message_id
    context.user_data["admin_step"] = "BROADCAST_CONFIRM_PENDING"
    count = db.get_user_count()
    await update.message.reply_text(
        f"📢 پیام دریافت شد.\n\nارسال به *{fa(count)}* کاربر؟",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ ارسال به همه", callback_data="admin:broadcast_confirm"),
            InlineKeyboardButton("❌ لغو",          callback_data="admin:broadcast_cancel"),
        ]]),
    )
