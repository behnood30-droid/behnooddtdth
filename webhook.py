"""FastAPI webhooks برای پیروزچنج و Plisio."""
import logging

from fastapi import FastAPI, Header, HTTPException, Request

from config import Settings
from db import DB
from delivery import create_config_and_deliver
from pasarguard import PasarGuardClient
from plisio import PlisioClient
from pirooz import PiroozClient

log = logging.getLogger(__name__)


def create_webhook_app(
    db: DB,
    settings: Settings,
    pirooz: PiroozClient,
    plisio: PlisioClient,
    panel: PasarGuardClient,
    bot,
) -> FastAPI:
    app = FastAPI(title="Peech Bot Webhook")

    @app.post("/webhook/pirooz")
    async def pirooz_webhook(
        request: Request,
        x_signature: str | None = Header(None, alias="X-Signature"),
    ):
        body_bytes = await request.body()

        if settings.pirooz_api_key and x_signature:
            if not pirooz.verify_signature(body_bytes, x_signature):
                log.warning("pirooz webhook: invalid signature")
                raise HTTPException(status_code=401, detail="Invalid signature")

        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        order_id = data.get("order_id", "")
        status = data.get("status", "")
        tracking_code = data.get("tracking_code", "")

        log.info("pirooz webhook: order=%s status=%s", order_id, status)

        if status != "confirmed":
            return {"ok": True}

        payment = db.get_payment(order_id)
        if not payment:
            log.warning("pirooz webhook: payment not found: %s", order_id)
            return {"ok": True}

        if payment.status != "pending":
            log.info("pirooz webhook: payment already %s: %s", payment.status, order_id)
            return {"ok": True}

        db.confirm_payment(order_id, tracking_code=tracking_code)
        await create_config_and_deliver(
            payment_id=order_id,
            bot=bot,
            db=db,
            panel=panel,
            settings=settings,
        )
        return {"ok": True}

    @app.post("/webhook/plisio")
    async def plisio_webhook(request: Request):
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        order_number = data.get("order_number", "")
        status = data.get("status", "")
        txn_id = data.get("txn_id", "")

        log.info("plisio webhook: order=%s status=%s txn_id=%s", order_number, status, txn_id)

        if settings.plisio_secret_key:
            if not plisio.verify_webhook(data):
                log.warning("plisio webhook: invalid verify_hash for order=%s", order_number)
                raise HTTPException(status_code=401, detail="Invalid hash")

        if status != "completed":
            return {"status": 1}

        payment = db.get_payment(order_number)
        if not payment:
            log.warning("plisio webhook: payment not found: %s", order_number)
            return {"status": 1}

        if payment.status != "pending":
            log.info("plisio webhook: payment already %s: %s", payment.status, order_number)
            return {"status": 1}

        db.confirm_payment(order_number, tx_hash=txn_id)
        await create_config_and_deliver(
            payment_id=order_number,
            bot=bot,
            db=db,
            panel=panel,
            settings=settings,
        )
        return {"status": 1}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app
