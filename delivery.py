"""منطق تحویل سفارش: ساخت کاربر در پنل و ارسال لینک به مشتری."""
import asyncio
import logging
import secrets

from telegram import Bot

from config import Settings
from db import DB, Order
from pasarguard import PasarGuardClient, PasarGuardError

log = logging.getLogger(__name__)

MSG_SUCCESS = (
    "🎉 پرداخت تأیید شد!\n\n"
    "لینک اشتراک VPN شما آماده‌ست:\n"
    "<code>{sub_link}</code>\n\n"
    "📱 <b>آموزش اتصال:</b>\n"
    "• <b>اندروید:</b> نصب <b>v2rayNG</b> ← + ← Import config from clipboard\n"
    "• <b>iOS:</b> نصب <b>Streisand</b> یا <b>Shadowrocket</b> ← + ← از URL وارد کن\n"
    "• <b>ویندوز:</b> نصب <b>v2rayN</b> ← سرورها ← افزودن از لینک اشتراک\n"
    "• <b>macOS:</b> نصب <b>V2Box</b> یا <b>Hiddify</b> ← افزودن از URL اشتراک\n\n"
    "⚠️ این لینک مختص شماست. آن را به کس دیگری ندهید.\n"
    "در صورت مشکل /support را بزنید."
)

MSG_DELIVERY_FAILED = (
    "پرداخت شما تأیید شد ولی در ساخت کانفیگ مشکلی پیش اومد 😔\n\n"
    "شماره سفارش: <code>{order_id}</code>\n\n"
    "این شماره رو به پشتیبانی بدید تا کانفیگ برات ارسال بشه."
)


async def deliver_order(
    order: Order,
    bot: Bot,
    db: DB,
    panel: PasarGuardClient,
    settings: Settings,
) -> None:
    if order.status == "delivered":
        log.info("order %s already delivered, skipping", order.order_id)
        return
    if order.status != "paid":
        log.warning("order %s has status=%s, cannot deliver", order.order_id, order.status)
        return

    username = f"peech_{secrets.token_hex(4)}"
    last_err: Exception | None = None

    for attempt in range(3):
        try:
            result = await panel.create_user(
                username=username,
                data_limit_gb=order.plan_gb,
                duration_days=order.days,
                order_id=order.order_id,
            )
            sub_link = result["subscription_url"]
            db.mark_delivered(order.order_id, result["username"], sub_link)
            await bot.send_message(
                order.telegram_user_id,
                MSG_SUCCESS.format(sub_link=sub_link),
                parse_mode="HTML",
            )
            log.info(
                "order %s delivered — user=%s tg=%s",
                order.order_id,
                result["username"],
                order.telegram_user_id,
            )
            return
        except PasarGuardError as e:
            last_err = e
            log.warning(
                "delivery attempt %d/3 failed for order %s: %s",
                attempt + 1,
                order.order_id,
                e,
            )
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)

    # همه ۳ تلاش ناموفق بود
    db.mark_failed(order.order_id)
    log.error("delivery permanently failed for order %s: %s", order.order_id, last_err)

    try:
        await bot.send_message(
            order.telegram_user_id,
            MSG_DELIVERY_FAILED.format(order_id=order.order_id),
            parse_mode="HTML",
        )
    except Exception:
        log.exception("could not notify user about delivery failure")

    try:
        await bot.send_message(
            settings.admin_telegram_id,
            f"⚠️ خطا در تحویل سفارش\n"
            f"سفارش: <code>{order.order_id}</code>\n"
            f"کاربر: {order.telegram_user_id}"
            + (f" (@{order.telegram_username})" if order.telegram_username else "")
            + f"\nپلن: {order.plan_gb} گیگ\n"
            f"خطا: {last_err}",
            parse_mode="HTML",
        )
    except Exception:
        log.exception("could not notify admin about delivery failure")
