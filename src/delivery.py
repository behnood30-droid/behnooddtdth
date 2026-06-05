"""منطق مشترک تحویل سفارش: از پنل کاربر می‌سازد و پیام می‌فرستد."""

import logging
import secrets

from telegram import Bot

from .config import Settings, find_plan
from .db import DB, Order
from .pasarguard import PasarGuardClient, PasarGuardError

log = logging.getLogger(__name__)


def _gen_username(order_id: int) -> str:
    # username پنل: ترکیب شناسه سفارش + رشته تصادفی کوتاه
    return f"u{order_id}_{secrets.token_hex(3)}"


async def deliver_order(
    order_id: int,
    bot: Bot,
    db: DB,
    panel: PasarGuardClient,
    settings: Settings,
) -> None:
    """برای یک سفارش پرداخت‌شده، کاربر پنل را می‌سازد و لینک ساب را می‌فرستد."""
    order = db.get_order(order_id)
    if order is None:
        log.warning("deliver: order %s not found", order_id)
        return
    if order.status == "delivered":
        log.info("deliver: order %s already delivered", order_id)
        return
    if order.status != "paid":
        log.warning("deliver: order %s status=%s, skipping", order_id, order.status)
        return

    plan = find_plan(settings, order.plan_id)
    if plan is None:
        log.error("deliver: plan %s not found for order %s", order.plan_id, order_id)
        await bot.send_message(
            order.tg_user_id,
            "خطا در تحویل سفارش — لطفاً با پشتیبانی تماس بگیرید.",
        )
        return

    username = _gen_username(order_id)
    try:
        created = await panel.create_user(
            username=username,
            data_limit_gb=plan.data_limit_gb,
            duration_days=plan.duration_days,
            note=f"order:{order_id} tg:{order.tg_user_id}",
        )
    except PasarGuardError as e:
        log.exception("create_user failed for order %s: %s", order_id, e)
        await bot.send_message(
            order.tg_user_id,
            "پرداخت تأیید شد ولی ساخت کانفیگ با خطا مواجه شد. "
            "لطفاً به پشتیبانی پیام بدید.",
        )
        return

    sub_url = created["subscription_url"]
    db.mark_delivered(order_id, username, sub_url)

    text = settings.messages["payment_done"].format(sub_url=sub_url)
    await bot.send_message(
        order.tg_user_id,
        text,
        parse_mode="Markdown",
    )
