"""وب‌سرور aiohttp برای دریافت callback تتراپی."""

import logging

from aiohttp import web
from telegram import Bot

from .config import Settings
from .db import DB
from .delivery import deliver_order
from .pasarguard import PasarGuardClient
from .tetrapay import TetrapayClient

log = logging.getLogger(__name__)


def _extract_invoice_id(payload: dict) -> str | None:
    for key in ("invoice_id", "id", "order_id"):
        val = payload.get(key)
        if val is not None:
            return str(val)
    return None


def _extract_status(payload: dict) -> str:
    status = (payload.get("status") or payload.get("state") or "").lower()
    return status


def build_app(
    settings: Settings,
    db: DB,
    tetrapay: TetrapayClient,
    panel: PasarGuardClient,
    bot: Bot,
) -> web.Application:
    async def health(_request):
        return web.json_response({"ok": True})

    async def callback(request: web.Request) -> web.Response:
        raw = await request.read()
        signature = request.headers.get("X-Signature") or request.headers.get(
            "X-Tetrapay-Signature"
        )
        if not tetrapay.verify_webhook(raw, signature):
            log.warning("webhook: invalid signature")
            return web.json_response({"ok": False}, status=401)

        try:
            payload = await request.json()
        except Exception:
            return web.json_response({"ok": False, "error": "bad json"}, status=400)

        invoice_id = _extract_invoice_id(payload)
        status = _extract_status(payload)
        log.info("webhook: invoice=%s status=%s", invoice_id, status)
        if not invoice_id:
            return web.json_response({"ok": False, "error": "no invoice id"}, status=400)

        order = db.get_order_by_invoice(invoice_id)
        if order is None:
            log.warning("webhook: no local order for invoice %s", invoice_id)
            return web.json_response({"ok": True})  # 200 تا تتراپی دوباره نزند

        if status in ("paid", "success", "completed", "confirmed"):
            # اگر امضا غیرفعال بود، یک بار از API تتراپی هم تأیید بگیریم
            if not settings.tetrapay_webhook_secret:
                info = await tetrapay.get_invoice(invoice_id)
                if _extract_status(info) not in (
                    "paid",
                    "success",
                    "completed",
                    "confirmed",
                ):
                    log.warning(
                        "webhook: status mismatch from get_invoice for %s", invoice_id
                    )
                    return web.json_response({"ok": False}, status=400)
            if order.status == "pending":
                db.mark_paid(order.id)
            await deliver_order(order.id, bot, db, panel, settings)
        elif status in ("failed", "expired", "canceled", "cancelled"):
            db.mark_failed(order.id)
            try:
                await bot.send_message(
                    order.tg_user_id, settings.messages["payment_failed"]
                )
            except Exception:
                log.exception("failed to notify user")

        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_post("/tetrapay/callback", callback)
    return app
