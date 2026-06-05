"""
کلاینت Tetrapay برای ساخت فاکتور USDT و تأیید پرداخت.

⚠️ نکته: نام دقیق فیلدها/مسیرها رو از مستندات تتراپی که داری چک کن و
در صورت نیاز پایین رو تطبیق بده. ساختار زیر یک الگوی متداول REST هست.

مسیرهای فرضی:
  POST {base}/invoice/create
      body: { amount, currency, order_id, callback_url, return_url }
      → { id, payment_url, status, ... }
  GET  {base}/invoice/{id}
      → { id, status, amount, ... }   (status ∈ pending|paid|expired|failed)

برای webhook هم انتظار داریم تتراپی این بدنه را POST کند:
  { invoice_id, status, amount, signature }
امضا (signature) اگر بود با HMAC-SHA256 روی body با کلید TETRAPAY_WEBHOOK_SECRET
بررسی می‌شود.
"""

import hashlib
import hmac

import httpx


class TetrapayError(RuntimeError):
    pass


class TetrapayClient:
    def __init__(self, base_url: str, api_key: str, webhook_secret: str = ""):
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._webhook_secret = webhook_secret
        self._client = httpx.AsyncClient(timeout=20.0)

    async def close(self) -> None:
        await self._client.aclose()

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def create_invoice(
        self,
        amount_usdt: float,
        order_id: int,
        callback_url: str,
        return_url: str = "",
        description: str = "",
    ) -> dict:
        payload = {
            "amount": amount_usdt,
            "currency": "USDT",
            "order_id": str(order_id),
            "callback_url": callback_url,
            "return_url": return_url,
            "description": description,
        }
        resp = await self._client.post(
            f"{self.base_url}/invoice/create",
            json=payload,
            headers=self._headers(),
        )
        if resp.status_code not in (200, 201):
            raise TetrapayError(
                f"create_invoice failed: {resp.status_code} {resp.text[:400]}"
            )
        body = resp.json()
        invoice_id = str(body.get("id") or body.get("invoice_id") or "")
        pay_url = body.get("payment_url") or body.get("pay_url") or body.get("url")
        if not invoice_id or not pay_url:
            raise TetrapayError(
                f"پاسخ تتراپی فیلدهای لازم رو نداشت: {body}"
            )
        return {"invoice_id": invoice_id, "pay_url": pay_url, "raw": body}

    async def get_invoice(self, invoice_id: str) -> dict:
        resp = await self._client.get(
            f"{self.base_url}/invoice/{invoice_id}",
            headers=self._headers(),
        )
        if resp.status_code != 200:
            raise TetrapayError(
                f"get_invoice failed: {resp.status_code} {resp.text[:300]}"
            )
        return resp.json()

    def verify_webhook(self, raw_body: bytes, signature: str | None) -> bool:
        """صحت‌سنجی امضای webhook.

        اگر secret ست نشده باشد، صحت‌سنجی غیرفعال می‌شود (برای تست).
        در پروداکشن حتماً secret را ست کن.
        """
        if not self._webhook_secret:
            return True
        if not signature:
            return False
        expected = hmac.new(
            self._webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)
