"""کلاینت Plisio برای پرداخت کریپتو."""
import hashlib
import json
import logging

import httpx

log = logging.getLogger(__name__)

PLISIO_BASE = "https://api.plisio.net/api/v1"


class PlisioError(RuntimeError):
    pass


class PlisioClient:
    def __init__(self, secret_key: str) -> None:
        self._key = secret_key

    async def create_invoice(
        self,
        payment_id: str,
        source_amount: float,
        order_name: str,
        callback_url: str,
        success_url: str,
        fail_url: str,
    ) -> dict:
        """ساخت invoice در Plisio. برمیگردونه {'txn_id': ..., 'invoice_url': ...}"""
        params = {
            "api_key": self._key,
            "currency": "USDT",
            "source_currency": "USD",
            "source_amount": str(round(source_amount, 2)),
            "order_name": order_name,
            "order_number": payment_id,
            "callback_url": callback_url,
            "success_url": success_url,
            "fail_url": fail_url,
            "language": "fa",
        }
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(f"{PLISIO_BASE}/invoices/new", params=params)
        if resp.status_code != 200:
            raise PlisioError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        body = resp.json()
        if body.get("status") != "success":
            raise PlisioError(f"Plisio error: {body}")
        data = body["data"]
        return {
            "txn_id": data.get("txn_id", ""),
            "invoice_url": data.get("invoice_url", ""),
        }

    def verify_webhook(self, payload: dict) -> bool:
        """اعتبارسنجی verify_hash = md5(api_key + sorted_json_without_hash)"""
        received = payload.get("verify_hash", "")
        data = {k: v for k, v in payload.items() if k != "verify_hash"}
        sorted_json = json.dumps(data, separators=(",", ":"), sort_keys=True)
        expected = hashlib.md5((self._key + sorted_json).encode()).hexdigest()
        return received == expected
