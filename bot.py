"""هندلرهای ربات تلگرام."""
import logging
import os
from datetime import datetime, timedelta, timezone

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

from config import Settings
from db import DB
from delivery import create_config_and_deliver
from pasarguard import PasarGuardClient
from admin import (
    cmd_admin,
    handle_admin_callback,
    handle_admin_media_input,
    handle_admin_text_input,
)
from plans import PLANS, fa, get_plan
from wallet import generate_unique_amount

log = logging.getLogger(__name__)

# ─── ثوابت ────────────────────────────────────────────────────────────────────

MAIN_BUTTONS = {
    "🛒 خرید سرویس",
    "📋 سرویس‌های من",
    "💰 افزایش موجودی",
    "👤 حساب کاربری",
    "📚 آموزش",
    "🎧 پشتیبانی",
}

MSG_TUTORIAL = (
    "📚 <b>آموزش استفاده</b>\n\n"
    "<b>اندروید — v2rayNG:</b>\n"
    "۱. از گوگل‌پلی نصب کن\n"
    "۲. + ← Import config from clipboard\n"
    "۳. لینک ساب رو paste کن\n"
    "۴. Update subscriptions\n"
    "۵. کانکت کن ✅\n\n"
    "<b>iOS — Streisand:</b>\n"
    "۱. از App Store نصب کن\n"
    "۲. + ← Subscribe ← URL رو وارد کن\n"
    "۳. کانکت کن ✅\n\n"
    "<b>ویندوز — v2rayN:</b>\n"
    "۱. از GitHub دانلود کن\n"
    "۲. Servers ← Add subscription server\n"
    "۳. لینک ساب رو وارد کن ← Update\n"
    "۴. کانکت کن ✅\n\n"
    "<b>شارژ کیف پول:</b>\n"
    "۱. «💰 افزایش موجودی» رو بزن\n"
    "۲. شبکه (BEP20 یا TRC20) رو انتخاب کن\n"
    "۳. مبلغ USDT که می‌خوای رو وارد کن\n"
    "۴. ربات آدرس و مبلغ دقیق رو میده\n"
    "۵. دقیقاً همون مبلغ رو به همون آدرس بفرست\n"
    "۶. بعد از تأیید شبکه، موجودی اضافه میشه ✅"
)

# ─── کیبورد اصلی ────────────────────────────────────────────────────────────

def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            ["🛒 خرید سرویس", "📋 سرویس‌های من"],
            ["💰 افزایش موجودی", "👤 حساب کاربری"],
            ["📚 آموزش", "🎧 پشتیبانی"],
        ],
        resize_keyboard=True,
    )


# ─── میان‌افزار: ثبت/بروزرسانی کاربر ────────────────────────────────────────

async def _ensure_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_user:
        return
    u = update.effective_user
    db: DB = context.bot_data["db"]
    db.ensure_user(u.id, u.username, u.first_name or "")


# ─── /start ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    name = update.effective_user.first_name or "دوست عزیز"
    text = (
        f"سلام {name} 👋\n\n"
        f"به ربات خرید VPN خوش اومدی!\n"
        f"برای شروع یکی از گزینه‌های زیر رو انتخاب کن 👇"
    )
    path = settings.welcome_image_path
    if path and os.path.isfile(path):
        with open(path, "rb") as f:
            await update.message.reply_photo(
                photo=f, caption=text, reply_markup=main_keyboard()
            )
    else:
        await update.message.reply_text(text, reply_markup=main_keyboard())


# ─── هندلر اصلی پیام‌ها ──────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""

    # ادمین در حال استفاده از پنل؟
    if await handle_admin_text_input(update, context):
        return

    charge_step = context.user_data.get("charge_step")

    # اگه در مرحله وارد کردن مبلغ هستیم
    if charge_step == "ENTER_AMOUNT":
        if text in MAIN_BUTTONS:
            # کاربر بجای مبلغ یه دکمه اصلی زده → لغو شارژ و ادامه عادی
            context.user_data.pop("charge_step", None)
            context.user_data.pop("charge_network", None)
        else:
            await _handle_amount_input(update, context, text)
            return

    # دکمه‌های منوی اصلی
    dispatch = {
        "🛒 خرید سرویس":    _on_buy_service,
        "📋 سرویس‌های من":  _on_my_services,
        "💰 افزایش موجودی": _on_add_balance,
        "👤 حساب کاربری":   _on_account,
        "📚 آموزش":          _on_tutorial,
        "🎧 پشتیبانی":       _on_support,
    }
    handler = dispatch.get(text)
    if handler:
        await handler(update, context)


# ─── بخش خرید سرویس ──────────────────────────────────────────────────────────

async def _on_buy_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(p.label, callback_data=f"plan:{p.id}")] for p in PLANS]
    )
    await update.message.reply_text(
        "🛒 <b>خرید سرویس</b>\n\nپلن مورد نظر رو انتخاب کن:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def _on_plan_selected(query, context: ContextTypes.DEFAULT_TYPE, plan_id: int) -> None:
    plan = get_plan(plan_id)
    if not plan:
        return
    db: DB = context.bot_data["db"]
    balance = db.get_balance(query.from_user.id)
    price_fa = fa(f"{plan.price_toman:,}")
    bal_fa = fa(f"{int(balance):,}")

    if balance >= plan.price_toman:
        text = (
            f"📦 <b>پلن:</b> {fa(plan.gb)} گیگ — {fa(plan.days)} روزه\n"
            f"💰 <b>قیمت:</b> {price_fa} تومان\n"
            f"💳 <b>موجودی شما:</b> {bal_fa} تومان\n\n"
            f"آیا مطمئنی؟"
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ تأیید خرید", callback_data=f"confirm_buy:{plan_id}"),
            InlineKeyboardButton("❌ انصراف",      callback_data="cancel_buy"),
        ]])
    else:
        needed = plan.price_toman - int(balance)
        text = (
            f"📦 <b>پلن:</b> {fa(plan.gb)} گیگ — {fa(plan.days)} روزه\n"
            f"💰 <b>قیمت:</b> {price_fa} تومان\n"
            f"💳 <b>موجودی شما:</b> {bal_fa} تومان\n\n"
            f"⚠️ موجودی کافی نیست.\n"
            f"به {fa(f'{needed:,}')} تومان دیگه نیاز داری."
        )
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("💰 افزایش موجودی", callback_data="go_charge"),
        ]])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=keyboard)


async def _on_confirm_buy(query, context: ContextTypes.DEFAULT_TYPE, plan_id: int) -> None:
    plan = get_plan(plan_id)
    if not plan:
        return
    db: DB = context.bot_data["db"]
    settings: Settings = context.bot_data["settings"]
    panel: PasarGuardClient = context.bot_data["panel"]

    deducted = db.deduct_balance(query.from_user.id, plan.price_toman)
    if not deducted:
        await query.edit_message_text(
            "❌ موجودی کافی نیست. لطفاً کیف پول رو شارژ کن."
        )
        return

    order_id = db.create_order(
        telegram_id=query.from_user.id,
        plan_gb=plan.gb,
        price_toman=plan.price_toman,
        days=plan.days,
    )
    await query.edit_message_text("⏳ در حال ساخت سرویس...\nیه لحظه صبر کن 🕐")

    await create_config_and_deliver(
        order_id=order_id,
        plan_gb=plan.gb,
        days=plan.days,
        price_toman=plan.price_toman,
        telegram_id=query.from_user.id,
        bot=context.bot,
        db=db,
        panel=panel,
        settings=settings,
    )


# ─── بخش سرویس‌های من ────────────────────────────────────────────────────────

async def _on_my_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    orders = db.list_user_orders(update.effective_user.id)
    if not orders:
        await update.message.reply_text(
            "📋 هنوز سرویسی خریداری نکردی.\n"
            "برای خرید «🛒 خرید سرویس» رو بزن."
        )
        return

    lines = ["📋 <b>سرویس‌های من:</b>\n"]
    for i, o in enumerate(orders, 1):
        try:
            created = datetime.fromisoformat(o.created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            expire = created + timedelta(days=o.days)
            expire_str = expire.strftime("%Y/%m/%d")
        except Exception:
            expire_str = "نامشخص"

        lines.append(
            f"<b>{fa(i)}.</b> {fa(o.plan_gb)} گیگ — انقضا: {expire_str}\n"
            f"🔗 <code>{o.sub_link}</code>"
        )
    await update.message.reply_text("\n\n".join(lines), parse_mode="HTML")


# ─── بخش افزایش موجودی ───────────────────────────────────────────────────────

async def _on_add_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    existing = db.get_user_pending_charge(update.effective_user.id)
    if existing:
        await _show_pending_charge(update, existing)
        return
    # شروع فلوی شارژ — انتخاب شبکه
    context.user_data["charge_step"] = "CHOOSE_NETWORK"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔷 BEP20 (BSC)", callback_data="net:BEP20"),
        InlineKeyboardButton("🔴 TRC20 (Tron)", callback_data="net:TRC20"),
    ]])
    await update.message.reply_text(
        "💰 <b>افزایش موجودی</b>\n\n"
        "شبکه پرداخت رو انتخاب کن:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


async def _show_pending_charge(update, charge) -> None:
    settings_addr = {
        "BEP20": "آدرس BEP20",
        "TRC20": "آدرس TRC20",
    }
    await update.message.reply_text(
        f"⏳ یه درخواست شارژ در انتظار داری:\n\n"
        f"شبکه: {charge.network}\n"
        f"مبلغ دقیق: <code>{charge.unique_amount}</code> USDT\n\n"
        f"اگه پرداخت کردی صبر کن تا تأیید بشه.\n"
        f"برای لغو /cancel رو بزن.",
        parse_mode="HTML",
    )


async def _on_network_chosen(query, context: ContextTypes.DEFAULT_TYPE, network: str) -> None:
    if context.user_data.get("charge_step") != "CHOOSE_NETWORK":
        await query.answer("این درخواست قدیمی یا لغو شده.")
        return
    context.user_data["charge_network"] = network
    context.user_data["charge_step"] = "ENTER_AMOUNT"
    await query.edit_message_text(
        f"شبکه <b>{network}</b> انتخاب شد.\n\n"
        f"مبلغ USDT که می‌خوای واریز کنی رو بنویس:\n"
        f"(مثال: ۱۰ یا ۲۵.۵)\n\n"
        f"برای لغو /cancel رو بزن.",
        parse_mode="HTML",
    )


async def _handle_amount_input(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
) -> None:
    network = context.user_data.get("charge_network", "")
    if not network:
        context.user_data.pop("charge_step", None)
        await update.message.reply_text("خطا در فلوی شارژ. دوباره تلاش کن.")
        return

    # اعداد فارسی رو تبدیل کن
    text = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٬", "0123456789,")).replace(",", "")
    try:
        amount_usdt = float(text)
        assert 1 <= amount_usdt <= 10_000
    except (ValueError, AssertionError):
        await update.message.reply_text(
            "⚠️ مبلغ نامعتبر. یه عدد بین ۱ و ۱۰٬۰۰۰ وارد کن."
        )
        return

    # گرفتن نرخ از تنظیمات ادمین
    db: DB = context.bot_data["db"]
    settings: Settings = context.bot_data["settings"]
    rate_str = db.get_setting("usdt_irt_rate")
    if not rate_str:
        await update.message.reply_text(
            f"⏳ قیمت در حال بروزرسانی است. لطفاً چند دقیقه دیگه تلاش کن "
            f"یا با پشتیبانی تماس بگیر: @{settings.support_username}"
        )
        try:
            await context.bot.send_message(
                settings.admin_telegram_id,
                "⚠️ یک کاربر سعی کرد شارژ کنه اما قیمت USDT ست نشده.\n"
                "لطفاً از /admin قیمت رو تنظیم کن.",
            )
        except Exception:
            pass
        return
    price_toman = int(rate_str)

    amount_toman = int(amount_usdt * price_toman)

    unique = generate_unique_amount(amount_usdt, network, db)
    charge_id = db.create_charge(
        telegram_id=update.effective_user.id,
        amount_usdt=amount_usdt,
        amount_toman=amount_toman,
        unique_amount=unique,
        network=network,
    )

    address = (
        settings.usdt_bep20_address if network == "BEP20"
        else settings.usdt_trc20_address
    )
    network_label = "BEP20 (BSC)" if network == "BEP20" else "TRC20 (Tron)"

    # پاک کردن state
    context.user_data.pop("charge_step", None)
    context.user_data.pop("charge_network", None)

    await update.message.reply_text(
        f"✅ <b>درخواست شارژ ثبت شد!</b>\n\n"
        f"💳 <b>اطلاعات واریز:</b>\n"
        f"شبکه: {network_label}\n"
        f"مبلغ دقیق: <code>{unique}</code> USDT\n"
        f"آدرس:\n<code>{address}</code>\n\n"
        f"معادل تومانی: {fa(f'{amount_toman:,}')} تومان\n"
        f"(نرخ لحظه: {fa(f'{price_toman:,}')} تومان/USDT)\n\n"
        f"⚠️ <b>توجه:</b>\n"
        f"• مبلغ رو <b>دقیقاً</b> <code>{unique}</code> وارد کن\n"
        f"• این مبلغ مختص شماست و ربات باهاش تراکنش رو شناسایی می‌کنه\n"
        f"• مهلت پرداخت: ۳۰ دقیقه\n"
        f"• بعد از تأیید شبکه، موجودی خودکار اضافه میشه",
        parse_mode="HTML",
    )


# ─── بخش حساب کاربری ─────────────────────────────────────────────────────────

async def _on_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    user = db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("خطا. /start رو بزن.")
        return
    try:
        joined = datetime.fromisoformat(user.created_at).strftime("%Y/%m/%d")
    except Exception:
        joined = user.created_at

    await update.message.reply_text(
        f"👤 <b>حساب کاربری</b>\n\n"
        f"🆔 شناسه: <code>{user.telegram_id}</code>\n"
        f"👤 نام: {user.first_name}\n"
        f"💰 موجودی: {fa(f'{int(user.balance_toman):,}')} تومان\n"
        f"🛒 تعداد خریدها: {fa(user.total_purchases)}\n"
        f"📅 تاریخ عضویت: {joined}",
        parse_mode="HTML",
    )


# ─── بخش آموزش ───────────────────────────────────────────────────────────────

async def _on_tutorial(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(MSG_TUTORIAL, parse_mode="HTML")


# ─── بخش پشتیبانی ────────────────────────────────────────────────────────────

async def _on_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.bot_data["settings"]
    await update.message.reply_text(
        f"🎧 <b>پشتیبانی</b>\n\n"
        f"برای ارتباط با پشتیبانی:\n"
        f"👉 @{settings.support_username}",
        parse_mode="HTML",
    )


# ─── /cancel ─────────────────────────────────────────────────────────────────

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: DB = context.bot_data["db"]
    db.cancel_user_pending_charge(update.effective_user.id)
    context.user_data.pop("charge_step", None)
    context.user_data.pop("charge_network", None)
    await update.message.reply_text(
        "❌ عملیات لغو شد.",
        reply_markup=main_keyboard(),
    )


# ─── دستور ادمین ─────────────────────────────────────────────────────────────

async def cmd_admin_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ادمین: افزودن دستی موجودی — /addbalance <telegram_id> <amount_toman>"""
    settings: Settings = context.bot_data["settings"]
    if update.effective_user.id != settings.admin_telegram_id:
        return
    args = context.args or []
    if len(args) != 2:
        await update.message.reply_text("استفاده: /addbalance <telegram_id> <amount_toman>")
        return
    db: DB = context.bot_data["db"]
    try:
        uid = int(args[0])
        amount = int(args[1])
        new_bal = db.add_balance(uid, amount)
        await update.message.reply_text(
            f"✅ {fa(f'{amount:,}')} تومان به کاربر {uid} اضافه شد.\n"
            f"موجودی جدید: {fa(f'{int(new_bal):,}')} تومان"
        )
    except Exception as e:
        await update.message.reply_text(f"خطا: {e}")


# ─── CallbackQuery dispatcher ─────────────────────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    if data.startswith("plan:"):
        await _on_plan_selected(query, context, int(data.split(":")[1]))

    elif data.startswith("confirm_buy:"):
        await _on_confirm_buy(query, context, int(data.split(":")[1]))

    elif data == "cancel_buy":
        await query.edit_message_text("❌ خرید لغو شد.")

    elif data.startswith("net:"):
        await _on_network_chosen(query, context, data.split(":")[1])

    elif data == "go_charge":
        await query.edit_message_text(
            "برای شارژ کیف پول «💰 افزایش موجودی» رو از منو بزن."
        )

    elif data.startswith("admin:"):
        await handle_admin_callback(update, context, data)


# ─── هندلر مدیا (عکس) ────────────────────────────────────────────────────────

async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await handle_admin_media_input(update, context)


# ─── ثبت هندلرها ─────────────────────────────────────────────────────────────

def register_handlers(app: Application) -> None:
    # میان‌افزار: قبل از همه هندلرها اجرا میشه
    app.add_handler(TypeHandler(Update, _ensure_user), group=-1)

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("addbalance", cmd_admin_balance))
    app.add_handler(CommandHandler("admin", cmd_admin))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    app.add_handler(
        MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_media)
    )
    app.add_handler(CallbackQueryHandler(handle_callback))
