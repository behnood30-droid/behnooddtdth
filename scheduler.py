"""تسک پس‌زمینه: چک پرداخت‌ها هر ۳۰ ثانیه."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from config import Settings
from db import DB
from delivery import create_config_and_deliver
from pirooz import PiroozClient
from usdt import check_bep20, check_trc20

log = logging.getLogger(__name__)

PAYMENT_TIMEOUT = 30 * 60  # ۳۰ دقیقه


async def _check_once(bot, db: DB, settings: Settings, pirooz: PiroozClient, panel) -> None:
    pending = db.get_pending_payments()
    if not pending:
        return

    log.info("Checking %d pending payments", len(pending))
    now = datetime.now(timezone.utc)
    bep20_txs: list | None = None
    trc20_txs: list | None = None

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
                if data.get("status") == "approved":
                    tracking = data.get("tracking_code", "")
                    db.confirm_payment(payment.payment_id, tracking_code=tracking)
                    log.info("MATCHED! payment_id=%s, method=pirooz, tracking=%s",
                             payment.payment_id, tracking)
                    await create_config_and_deliver(
                        payment_id=payment.payment_id,
                        bot=bot, db=db, panel=panel, settings=settings,
                    )

            elif payment.payment_method == "usdt_bep20":
                log.info("Checking BEP20 charge: %s, amount: %s",
                         payment.payment_id, payment.unique_amount)
                if bep20_txs is None:
                    after_ts = int((now - timedelta(hours=1)).timestamp())
                    bep20_txs = await check_bep20(
                        settings.usdt_bep20_address,
                        settings.bscscan_api_key,
                        after_ts,
                    )
                for tx in bep20_txs:
                    if not tx.get("hash"):
                        continue
                    if db.tx_hash_used(tx["hash"]):
                        continue
                    if abs(tx["amount"] - (payment.unique_amount or 0)) <= 0.001:
                        log.info("MATCHED! payment_id=%s, method=usdt_bep20, tx=%s",
                                 payment.payment_id, tx["hash"])
                        db.confirm_payment(payment.payment_id, tx_hash=tx["hash"])
                        await create_config_and_deliver(
                            payment_id=payment.payment_id,
                            bot=bot, db=db, panel=panel, settings=settings,
                        )
                        break

            elif payment.payment_method == "usdt_trc20":
                log.info("Checking TRC20 charge: %s, amount: %s",
                         payment.payment_id, payment.unique_amount)
                if trc20_txs is None:
                    after_ts = int((now - timedelta(hours=1)).timestamp())
                    trc20_txs = await check_trc20(
                        settings.usdt_trc20_address,
                        after_ts,
                    )
                for tx in trc20_txs:
                    if not tx.get("hash"):
                        continue
                    if db.tx_hash_used(tx["hash"]):
                        continue
                    if abs(tx["amount"] - (payment.unique_amount or 0)) <= 0.001:
                        log.info("MATCHED! payment_id=%s, method=usdt_trc20, tx=%s",
                                 payment.payment_id, tx["hash"])
                        db.confirm_payment(payment.payment_id, tx_hash=tx["hash"])
                        await create_config_and_deliver(
                            payment_id=payment.payment_id,
                            bot=bot, db=db, panel=panel, settings=settings,
                        )
                        break

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
