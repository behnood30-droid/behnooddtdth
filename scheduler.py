"""تسک پس‌زمینه: چک کردن تراکنش‌های USDT هر ۳۰ ثانیه."""
import asyncio
import logging
import time
from datetime import datetime, timezone

from telegram import Bot

from config import Settings
from db import DB
from plans import fa
from wallet import check_bep20_incoming, check_trc20_incoming

log = logging.getLogger(__name__)

CHARGE_TIMEOUT = 30 * 60  # ۳۰ دقیقه


async def _check_once(bot: Bot, db: DB, settings: Settings) -> None:
    charges = db.get_pending_charges()
    if not charges:
        return

    log.debug("checking %d pending charge(s)", len(charges))
    now = int(time.time())

    for charge in charges:
        # تبدیل created_at (SQLite CURRENT_TIMESTAMP = UTC بدون zone info)
        try:
            dt = datetime.fromisoformat(charge.created_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            created_ts = int(dt.timestamp())
        except Exception:
            created_ts = now

        # چک timeout
        if now - created_ts > CHARGE_TIMEOUT:
            db.expire_charge(charge.charge_id)
            log.info("charge %s expired", charge.charge_id)
            try:
                await bot.send_message(
                    charge.telegram_id,
                    "⏱ مهلت پرداخت منقضی شد.\n"
                    "برای شارژ مجدد دوباره «💰 افزایش موجودی» رو بزن.",
                )
            except Exception:
                log.exception("expire notify failed")
            continue

        # گرفتن تراکنش‌های ورودی
        try:
            if charge.network == "BEP20":
                txs = await check_bep20_incoming(
                    settings.usdt_bep20_address,
                    settings.bscscan_api_key,
                    after_ts=created_ts - 60,
                )
            else:
                txs = await check_trc20_incoming(
                    settings.usdt_trc20_address,
                    after_ts=created_ts - 60,
                )
        except Exception:
            log.exception("tx fetch failed for charge %s", charge.charge_id)
            continue

        for tx in txs:
            if not tx.get("hash"):
                continue
            if db.tx_hash_used(tx["hash"]):
                continue
            # مطابقت مبلغ (تولرانس ۰.۰۰۰۵)
            if abs(tx["amount"] - charge.unique_amount) < 0.0005:
                db.confirm_charge(charge.charge_id, tx["hash"])
                new_bal = db.add_balance(charge.telegram_id, charge.amount_toman)
                log.info(
                    "charge %s confirmed — tx=%s toman=%d",
                    charge.charge_id, tx["hash"][:12], charge.amount_toman,
                )
                try:
                    await bot.send_message(
                        charge.telegram_id,
                        f"✅ پرداخت تأیید شد!\n\n"
                        f"💰 {fa(f'{charge.amount_toman:,}')} تومان به کیف پولت اضافه شد.\n"
                        f"💳 موجودی فعلی: {fa(f'{int(new_bal):,}')} تومان",
                    )
                except Exception:
                    log.exception("confirm notify failed")
                break


async def charge_monitor_loop(bot: Bot, db: DB, settings: Settings) -> None:
    """حلقه‌ای که هر ۳۰ ثانیه تراکنش‌ها رو چک می‌کنه."""
    log.info("charge monitor started")
    while True:
        await asyncio.sleep(30)
        try:
            await _check_once(bot, db, settings)
        except Exception:
            log.exception("charge monitor unexpected error")
