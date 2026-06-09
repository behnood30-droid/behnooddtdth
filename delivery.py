"""تحویل کانفیگ با retry در صورت شکست."""
import asyncio
import json
import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import Settings
from db import DB
from pasarguard import PasarGuardClient, PasarGuardError
from utils import fa, to_jalali

log = logging.getLogger(__name__)

RETRY_DELAYS = [5, 15, 45]


async def create_config_and_deliver(
    payment_id: str,
    bot,
    db: DB,
    panel: PasarGuardClient,
    settings: Settings,
) -> None:
    payment = db.get_payment(payment_id)
    if not payment:
        log.error("delivery: payment not found: %s", payment_id)
        return

    tid = payment.telegram_id
    plan_gb = payment.plan_gb
    plan_days = payment.plan_days

    try:
        await bot.send_message(
            tid,
            "✅ پرداخت تأیید شد، در حال ساخت سرویس...\n⏳ یه لحظه صبر کن 🕐",
        )
    except Exception:
        pass

    panel_username = f"peech_{tid}_{int(time.time())}"
    data_limit = plan_gb * 1_073_741_824
    expire_ts = int(time.time()) + plan_days * 86400

    last_error = ""
    for attempt, delay in enumerate(RETRY_DELAYS, 1):
        try:
            log.info("delivery attempt %d for %s", attempt, payment_id)
            user_data = await panel.create_user(
                username=panel_username,
                data_limit=data_limit,
                expire=expire_ts,
                group_ids=[settings.pasarguard_group_id],
            )
            sub_link = user_data.get("subscription_url", "")
            links = user_data.get("links", [])
            configs_json = json.dumps(links, ensure_ascii=False)

            db.deliver_payment(
                payment_id=payment_id,
                panel_username=panel_username,
                sub_link=sub_link,
                configs=configs_json,
            )
            db.increment_purchases(tid)

            pay = db.get_payment(payment_id)
            await _send_delivery_messages(
                bot=bot,
                telegram_id=tid,
                plan_gb=plan_gb,
                sub_link=sub_link,
                links=links,
                expires_at=pay.expires_at if pay else None,
            )
            log.info("delivery success: %s panel_user=%s", payment_id, panel_username)
            return

        except PasarGuardError as e:
            last_error = str(e)
            log.warning("delivery attempt %d failed for %s: %s", attempt, payment_id, e)
            if attempt < len(RETRY_DELAYS):
                await asyncio.sleep(delay)

    # همه تلاش‌ها شکست خورد
    db.fail_payment(payment_id)
    log.error("delivery permanently failed: %s — %s", payment_id, last_error)

    user = db.get_user(tid)
    uname = f"@{user.username}" if user and user.username else str(tid)

    try:
        await bot.send_message(
            tid,
            f"⚠️ مشکلی در ساخت سرویس پیش اومد.\n"
            f"لطفاً به پشتیبانی پیام بده تا فوراً پیگیری کنه:\n\n"
            f"👤 @{settings.support_username}\n\n"
            f"🆔 شناسه سفارش: `{payment_id}`",
            parse_mode="Markdown",
        )
    except Exception:
        log.exception("could not notify user about delivery failure")

    try:
        await bot.send_message(
            settings.admin_telegram_id,
            f"🚨 *خطای جدی!*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ پرداخت تأیید شد ولی کانفیگ ساخته نشد\n"
            f"🆔 سفارش: `{payment_id}`\n"
            f"👤 کاربر: `{tid}` ({uname})\n"
            f"📦 پلن: {fa(plan_gb)} گیگ\n"
            f"💳 روش: {payment.payment_method}\n"
            f"📝 خطا: {last_error[:200]}",
            parse_mode="Markdown",
        )
    except Exception:
        log.exception("could not notify admin about delivery failure")


async def _send_delivery_messages(
    bot,
    telegram_id: int,
    plan_gb: int,
    sub_link: str,
    links: list,
    expires_at: str | None,
) -> None:
    expire_str = to_jalali(expires_at)
    keyboard1 = InlineKeyboardMarkup([[
        InlineKeyboardButton("📚 آموزش اتصال", callback_data="tut"),
        InlineKeyboardButton("📋 سرویس‌های من", callback_data="my_svcs"),
    ]])

    await bot.send_message(
        telegram_id,
        f"🎁 *سرویس شما آماده شد!*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 پلن: {fa(plan_gb)} گیگ\n"
        f"⏱ مدت: ۳۰ روزه\n"
        f"📅 تاریخ انقضا: {expire_str}\n\n"
        f"🔗 *لینک اشتراک (Sub):*\n"
        f"`{sub_link}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 لینک Sub رو در v2rayNG یا Streisand اضافه کن. "
        f"وقتی سرورها تغییر کنن، خودش آپدیت میشه.\n\n"
        f"کانفیگ‌های مستقیم رو در پیام بعدی میفرستم 👇",
        parse_mode="Markdown",
        reply_markup=keyboard1,
    )

    if links:
        sep = "\n\n━━━━━━━━━━━━━━━━━━━━\n\n"
        configs_text = sep.join(f"`{cfg}`" for cfg in links)
        await bot.send_message(
            telegram_id,
            f"🔐 *کانفیگ‌های مستقیم*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"این کانفیگ‌ها رو میتونی مستقیم در هر اپی paste کنی:\n\n"
            f"{configs_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"❓ *کدوم رو استفاده کنم؟*\n"
            f"• لینک Sub: بهترین گزینه (خودکار آپدیت میشه)\n"
            f"• کانفیگ مستقیم: اگه اپت Sub رو پشتیبانی نمیکنه",
            parse_mode="Markdown",
        )
