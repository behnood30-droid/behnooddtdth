"""تسک پس‌زمینه: چک پرداخت‌ها هر ۳۰ ثانیه."""
import asyncio
import logging
from datetime import datetime, timezone

from config import Settings
from db import DB
from delivery import create_config_and_deliver
from pirooz import PiroozClient

log = logging.getLogger(__name__)

PAYMENT_TIMEOUT = 30 * 60  # ۳۰ دقیقه


async def _check_once(bot, db: DB, settings: Settings, pirooz: PiroozClient, panel) -> None:
    pending = db.get_pending_payments()
    if not pending:
        return

    log.info("Checking %d pending payments", len(pending))
    now = datetime.now(timezone.utc)

    for payment in pending:
        try:
            created = datetime.fromisoformat(payment.created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
        except Exception:
            created = now

        # منقضی شده؟
        if (now - created).total_seconds() > PAYMENT_TIMEOUT:
            db.expire_payment(payment.payment_id)
            log.info("payment expired: %s", payment.payment_id)
            try:
                await bot.send_message(
                    payment.telegram_id,
                    f"⏰ مهلت پرداخت سفارش منقضی شد.\n"
                    f"🆔 شناسه: `{payment.payment_id}`\n\n"
                    f"برای خرید مجدد از منو استفاده کن.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            continue

        try:
            if payment.payment_method == "pirooz":
                log.info("Checking pirooz order: %s", payment.payment_id)
                data = await pirooz.check_status(payment.payment_id)
                pirooz_status = data.get("status", "")
                log.info("pirooz response for %s: status=%r full=%s",
                         payment.payment_id, pirooz_status, data)
                if pirooz_status in ("approved", "paid", "success", "completed", "confirmed"):
                    tracking = data.get("tracking_code", "")
                    db.confirm_payment(payment.payment_id, tracking_code=tracking)
                    log.info("MATCHED! payment_id=%s, method=pirooz, status=%s, tracking=%s",
                             payment.payment_id, pirooz_status, tracking)
                    await create_config_and_deliver(
                        payment_id=payment.payment_id,
                        bot=bot, db=db, panel=panel, settings=settings,
                    )
            # plisio پرداخت‌ها از طریق webhook تأیید میشن — نیازی به polling نیست

        except Exception:
            log.exception("error checking payment %s", payment.payment_id)


async def charge_monitor_loop(bot, db: DB, settings: Settings, pirooz: PiroozClient, panel) -> None:
    log.info("payment monitor started")
    while True:
        await asyncio.sleep(30)
        try:
            await _check_once(bot, db, settings, pirooz, panel)
        except Exception:
            log.exception("payment monitor unexpected error")
