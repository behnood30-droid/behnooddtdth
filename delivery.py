"""ساخت کانفیگ با retry و refund در صورت شکست."""
import asyncio
import logging
import secrets

from telegram import Bot

from config import Settings
from db import DB
from pasarguard import PasarGuardClient, PasarGuardError
from plans import fa

log = logging.getLogger(__name__)

MSG_SUCCESS = (
    "🎉 سرویس شما آماده‌ست!\n\n"
    "🔗 <b>لینک اشتراک:</b>\n"
    "<code>{sub_link}</code>\n\n"
    "📱 <b>آموزش اتصال:</b>\n"
    "• <b>اندروید:</b> نصب v2rayNG ← + ← Import config from clipboard\n"
    "• <b>iOS:</b> نصب Streisand یا Shadowrocket ← + ← از URL وارد کن\n"
    "• <b>ویندوز:</b> نصب v2rayN ← سرورها ← افزودن از لینک اشتراک\n"
    "• <b>macOS:</b> نصب V2Box یا Hiddify ← افزودن از URL اشتراک\n\n"
    "⚠️ این لینک مختص شماست. آن را به کس دیگری ندهید."
)


async def create_config_and_deliver(
    order_id: str,
    plan_gb: int,
    days: int,
    price_toman: int,
    telegram_id: int,
    bot: Bot,
    db: DB,
    panel: PasarGuardClient,
    settings: Settings,
) -> bool:
    """
    کانفیگ می‌سازه. True = موفق، False = شکست (موجودی برگشت داده شد).
    ۳ بار با backoff تلاش می‌کنه.
    """
    username = f"peech_{secrets.token_hex(4)}"
    last_err: Exception | None = None

    for attempt in range(3):
        try:
            result = await panel.create_user(
                username=username,
                data_limit_gb=plan_gb,
                duration_days=days,
                order_id=order_id,
            )
            sub_link = result["subscription_url"]
            db.deliver_order(order_id, result["username"], sub_link)
            db.increment_purchases(telegram_id)
            await bot.send_message(
                telegram_id,
                MSG_SUCCESS.format(sub_link=sub_link),
                parse_mode="HTML",
            )
            log.info("order %s delivered — panel_user=%s", order_id, result["username"])
            return True
        except PasarGuardError as e:
            last_err = e
            log.warning(
                "config attempt %d/3 failed for order %s: %s",
                attempt + 1, order_id, e,
            )
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)

    # همه تلاش‌ها شکست خورد — برگردوندن موجودی
    db.fail_order(order_id)
    db.add_balance(telegram_id, price_toman)
    log.error("delivery permanently failed for order %s: %s", order_id, last_err)

    try:
        await bot.send_message(
            telegram_id,
            f"متأسفانه در ساخت سرویس مشکلی پیش اومد 😔\n\n"
            f"مبلغ {fa(f'{price_toman:,}')} تومان به کیف پولت برگشت.\n"
            f"لطفاً دوباره تلاش کن یا با پشتیبانی تماس بگیر.",
        )
    except Exception:
        log.exception("could not notify user about delivery failure")

    try:
        await bot.send_message(
            settings.admin_telegram_id,
            f"⚠️ خطا در ساخت کانفیگ\n"
            f"سفارش: <code>{order_id}</code>\n"
            f"کاربر: {telegram_id}\n"
            f"پلن: {plan_gb} گیگ\n"
            f"خطا: {last_err}",
            parse_mode="HTML",
        )
    except Exception:
        log.exception("could not notify admin")

    return False
