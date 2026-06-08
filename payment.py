"""فلوی پرداخت: pirooz و Plisio."""
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import Settings
from db import DB
from delivery import create_config_and_deliver
from pasarguard import PasarGuardClient
from plisio import PlisioClient
from pirooz import PiroozClient
from plans import get_plan
from utils import fa

log = logging.getLogger(__name__)

SEP = "━━━━━━━━━━━━━━━━━━━━"


def _make_payment_id(telegram_id: int) -> str:
    return f"peech_{telegram_id}_{int(time.time())}"


def _ownership_ok(payment, telegram_id: int) -> bool:
    return payment is not None and payment.telegram_id == telegram_id


# ─── انتخاب روش پرداخت ───────────────────────────────────────────────────────

async def show_payment_methods(query, context: ContextTypes.DEFAULT_TYPE, plan_id: int) -> None:
    plan = get_plan(plan_id)
    if not plan:
        await query.answer("پلن یافت نشد.")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💵 پرداخت ریالی (کارت بانکی)", callback_data=f"pm:{plan_id}:pirooz")],
        [InlineKeyboardButton("💎 پرداخت ارز دیجیتال (USDT)", callback_data=f"pm:{plan_id}:plisio")],
        [InlineKeyboardButton("❌ انصراف", callback_data="cancel_order")],
    ])
    await query.edit_message_text(
        f"📦 *خلاصه سفارش*\n"
        f"{SEP}\n\n"
        f"🎯 پلن: {fa(plan.gb)} گیگ\n"
        f"⏱ مدت: ۳۰ روزه\n"
        f"💰 قیمت: {fa(plan.price_toman)} تومان\n\n"
        f"{SEP}\n\n"
        f"💳 *روش پرداخت رو انتخاب کن:*",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ─── پرداخت ریالی (پیروز) ─────────────────────────────────────────────────────

async def on_pay_pirooz(query, context: ContextTypes.DEFAULT_TYPE, plan_id: int) -> None:
    plan = get_plan(plan_id)
    if not plan:
        await query.answer("پلن یافت نشد.")
        return

    db: DB = context.bot_data["db"]
    settings: Settings = context.bot_data["settings"]
    pirooz: PiroozClient = context.bot_data["pirooz"]

    payment_id = _make_payment_id(query.from_user.id)

    try:
        resp = await pirooz.create_payment(
            payment_id=payment_id,
            amount_toman=plan.price_toman,
            plan_gb=plan.gb,
        )
        deep_link = resp.get("deep_link", "")
    except Exception as e:
        log.exception("pirooz create_payment failed: %s", e)
        await query.edit_message_text(
            "❌ خطا در ایجاد سفارش پیروز. لطفاً دوباره تلاش کن یا روش دیگه‌ای انتخاب کن.",
        )
        return

    db.create_payment(
        payment_id=payment_id,
        telegram_id=query.from_user.id,
        plan_gb=plan.gb,
        plan_days=plan.days,
        price_toman=plan.price_toman,
        payment_method="pirooz",
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 ورود به ربات پرداخت", url=deep_link)],
        [InlineKeyboardButton("🔄 بررسی وضعیت پرداخت", callback_data=f"chk:{payment_id}")],
        [InlineKeyboardButton("❌ لغو سفارش", callback_data=f"cnl:{payment_id}")],
    ])
    await query.edit_message_text(
        f"💵 *پرداخت ریالی*\n"
        f"{SEP}\n\n"
        f"📦 پلن: {fa(plan.gb)} گیگ - ۳۰ روزه\n"
        f"💰 مبلغ: {fa(plan.price_toman)} تومان\n\n"
        f"🆔 شناسه سفارش:\n"
        f"`{payment_id}`\n\n"
        f"{SEP}\n\n"
        f"برای پرداخت روی دکمه پایین کلیک کن. به ربات پیروزچنج هدایت میشی "
        f"و میتونی با کارت بانکی پرداخت کنی.\n\n"
        f"⏱ این سفارش تا ۳۰ دقیقه فعاله",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ─── پرداخت کریپتو (Plisio) ──────────────────────────────────────────────────

async def on_pay_plisio(query, context: ContextTypes.DEFAULT_TYPE, plan_id: int) -> None:
    plan = get_plan(plan_id)
    if not plan:
        await query.answer("پلن یافت نشد.")
        return

    db: DB = context.bot_data["db"]
    settings: Settings = context.bot_data["settings"]
    plisio: PlisioClient = context.bot_data["plisio"]

    rate_str = db.get_setting("usdt_irt_rate")
    if not rate_str:
        await query.edit_message_text(
            f"⏳ قیمت ارز دیجیتال در حال بروزرسانیه. لطفاً چند دقیقه دیگه تلاش کن "
            f"یا با پشتیبانی تماس بگیر: @{settings.support_username}",
        )
        try:
            await context.bot.send_message(
                settings.admin_telegram_id,
                "⚠️ یک کاربر سعی کرد پرداخت Plisio کنه اما نرخ دلار ست نشده.\n"
                "لطفاً از /admin نرخ رو تنظیم کن.",
            )
        except Exception:
            pass
        return

    usd_amount = round(plan.price_toman / int(rate_str), 2)
    payment_id = _make_payment_id(query.from_user.id)
    bot_username = settings.bot_username
    bot_url = f"https://t.me/{bot_username}" if bot_username else "https://t.me/"

    try:
        resp = await plisio.create_invoice(
            payment_id=payment_id,
            source_amount=usd_amount,
            order_name=f"خرید VPN {plan.gb} گیگ",
            callback_url=f"{settings.webhook_domain}/webhook/plisio",
            success_url=bot_url,
            fail_url=bot_url,
        )
        invoice_url = resp["invoice_url"]
    except Exception as e:
        log.exception("plisio create_invoice failed: %s", e)
        await query.edit_message_text(
            "❌ خطا در ایجاد سفارش کریپتو. لطفاً دوباره تلاش کن یا روش دیگه‌ای انتخاب کن.",
        )
        return

    db.create_payment(
        payment_id=payment_id,
        telegram_id=query.from_user.id,
        plan_gb=plan.gb,
        plan_days=plan.days,
        price_toman=plan.price_toman,
        payment_method="plisio",
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 پرداخت با کریپتو", url=invoice_url)],
        [InlineKeyboardButton("🔄 بررسی وضعیت", callback_data=f"chk:{payment_id}")],
        [InlineKeyboardButton("❌ لغو سفارش", callback_data=f"cnl:{payment_id}")],
    ])
    await query.edit_message_text(
        f"💎 *پرداخت با ارز دیجیتال*\n"
        f"{SEP}\n\n"
        f"📦 پلن: {fa(plan.gb)} گیگ - ۳۰ روزه\n"
        f"💰 قیمت: {fa(plan.price_toman)} تومان\n\n"
        f"🆔 شناسه سفارش:\n"
        f"`{payment_id}`\n\n"
        f"{SEP}\n\n"
        f"برای پرداخت روی دکمه پایین کلیک کن.\n"
        f"صفحه پرداخت Plisio باز میشه و میتونی با\n"
        f"USDT یا سایر ارزها پرداخت کنی.\n\n"
        f"⏱ این سفارش تا ۳۰ دقیقه فعاله",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


# ─── بررسی وضعیت ─────────────────────────────────────────────────────────────

async def on_check_payment(query, context: ContextTypes.DEFAULT_TYPE, payment_id: str) -> None:
    db: DB = context.bot_data["db"]
    settings: Settings = context.bot_data["settings"]
    panel: PasarGuardClient = context.bot_data["panel"]

    payment = db.get_payment(payment_id)
    if not _ownership_ok(payment, query.from_user.id):
        await query.message.reply_text("⛔ این سفارش متعلق به شما نیست.")
        return

    if payment.status == "delivered":
        await query.message.reply_text("✅ این سفارش قبلاً تحویل داده شده.")
        return

    if payment.status in ("expired", "failed"):
        await query.message.reply_text(f"❌ وضعیت سفارش: {payment.status}")
        return

    if payment.payment_method == "pirooz":
        pirooz: PiroozClient = context.bot_data["pirooz"]
        try:
            data = await pirooz.check_status(payment_id)
        except Exception as e:
            log.exception("pirooz check_status failed: %s", e)
            await query.message.reply_text("❌ خطا در بررسی وضعیت. دوباره تلاش کن.")
            return
        pirooz_status = data.get("status", "unknown")

        if pirooz_status == "approved":
            tracking = data.get("tracking_code", "")
            db.confirm_payment(payment_id, tracking_code=tracking)
            await query.message.reply_text("✅ پرداخت تأیید شد! در حال ساخت سرویس...")
            await create_config_and_deliver(
                payment_id=payment_id,
                bot=context.bot, db=db, panel=panel, settings=settings,
            )
        elif pirooz_status == "pending":
            await query.message.reply_text("⏳ هنوز پرداخت نشده. صبر کن و دوباره بررسی کن.")
        elif pirooz_status in ("rejected", "expired"):
            db.expire_payment(payment_id)
            await query.message.reply_text(f"❌ پرداخت {pirooz_status} شد. سفارش لغو شد.")
        else:
            await query.message.reply_text("🔍 وضعیت نامشخص. کمی صبر کن.")

    elif payment.payment_method == "plisio":
        if payment.status == "confirmed":
            await query.message.reply_text("✅ پرداخت تأیید شد! در حال ساخت سرویس...")
            await create_config_and_deliver(
                payment_id=payment_id,
                bot=context.bot, db=db, panel=panel, settings=settings,
            )
        else:
            await query.message.reply_text(
                "⏳ پرداخت هنوز تأیید نشده.\n"
                "بعد از انجام پرداخت، به صورت خودکار سرویس برات ارسال میشه."
            )


# ─── لغو سفارش ───────────────────────────────────────────────────────────────

async def on_cancel_payment(query, context: ContextTypes.DEFAULT_TYPE, payment_id: str) -> None:
    db: DB = context.bot_data["db"]
    payment = db.get_payment(payment_id)
    if not _ownership_ok(payment, query.from_user.id):
        await query.message.reply_text("⛔ این سفارش متعلق به شما نیست.")
        return
    db.cancel_payment(payment_id)
    await query.edit_message_text(
        f"❌ سفارش لغو شد.\n🆔 شناسه: `{payment_id}`",
        parse_mode="Markdown",
    )
