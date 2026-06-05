"""FastAPI وب‌سرور برای دریافت callback پرداخت از tetra98."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from config import Settings
from db import DB
from delivery import deliver_order
from pasarguard import PasarGuardClient
from tetra import TetraClient, TetraError

log = logging.getLogger(__name__)


def create_app(
    settings: Settings,
    db: DB,
    tetra: TetraClient,
    panel: PasarGuardClient,
    bot,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    app.state.settings = settings
    app.state.db = db
    app.state.tetra = tetra
    app.state.panel = panel
    app.state.bot = bot

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/webhook/payment")
    async def payment_callback(request: Request):
        try:
            payload = await request.json()
        except Exception:
            log.warning("payment callback: invalid JSON body")
            return JSONResponse({"ok": False, "error": "invalid json"}, status_code=400)

        status = str(payload.get("status", ""))
        hash_id = str(payload.get("hash_id", "")).upper().strip()
        authority = str(payload.get("authority", "")).strip()

        log.info(
            "payment callback received — status=%s hash_id=%s authority=%s",
            status, hash_id, authority,
        )

        if not hash_id or not authority:
            return JSONResponse(
                {"ok": False, "error": "missing hash_id or authority"},
                status_code=400,
            )

        _db: DB = request.app.state.db
        order = _db.get_order(hash_id)
        if not order:
            # ممکنه سفارش از سیستم دیگه‌ای باشه؛ 200 برمی‌گردونیم تا tetra98 دوباره نزنه
            log.warning("payment callback: no order found for hash_id=%s", hash_id)
            return JSONResponse({"ok": True})

        if order.status == "delivered":
            log.info("order %s already delivered, ignoring callback", hash_id)
            return JSONResponse({"ok": True})

        _bot = request.app.state.bot
        _settings: Settings = request.app.state.settings

        if status != "100":
            log.info("payment not successful for order %s (status=%s)", hash_id, status)
            if order.status == "pending":
                _db.mark_failed(hash_id)
            try:
                await _bot.send_message(
                    order.telegram_user_id,
                    "پرداخت شما ناموفق بود یا لغو شد ❌\n\n"
                    "اگه مبلغ از حسابت کم شده، با پشتیبانی تماس بگیر.",
                )
            except Exception:
                log.exception("could not notify user about failed payment")
            return JSONResponse({"ok": True})

        # تأیید پرداخت از tetra98
        _tetra: TetraClient = request.app.state.tetra
        try:
            verified = await _tetra.verify(authority)
        except TetraError as e:
            log.exception("tetra verify error for order %s: %s", hash_id, e)
            return JSONResponse(
                {"ok": False, "error": "verify request failed"},
                status_code=500,
            )

        if not verified:
            log.warning("tetra verify returned False for order %s", hash_id)
            _db.mark_failed(hash_id)
            try:
                await _bot.send_message(
                    order.telegram_user_id,
                    "پرداخت تأیید نشد ❌\n"
                    "اگه مبلغ از حسابت کم شده، با پشتیبانی تماس بگیر.",
                )
            except Exception:
                log.exception("could not notify user about unverified payment")
            return JSONResponse({"ok": False, "error": "payment not verified"}, status_code=400)

        # پرداخت موفق و تأیید شده
        if order.status == "pending":
            _db.mark_paid(hash_id)
            order = _db.get_order(hash_id)

        await deliver_order(order, _bot, _db, request.app.state.panel, _settings)
        return JSONResponse({"ok": True})

    return app
