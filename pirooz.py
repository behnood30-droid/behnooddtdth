"""کلاینت API پیروزچنج."""
import hashlib
import hmac
import logging

import httpx

log = logging.getLogger(__name__)


class PiroozClient:
    def __init__(self, api_key: str, provider_key: str, base_url: str) -> None:
        self._api_key = api_key
        self._provider_key = provider_key
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        }

    async def create_payment(
        self, payment_id: str, amount_toman: int, plan_gb: int
    ) -> dict:
        """ایجاد سفارش — برمیگردونه {'deep_link': ..., 'order_id': ...}"""
        body = {
            "provider_key": self._provider_key,
            "order_id": payment_id,
            "amount": amount_toman,
            "description": f"خرید {plan_gb} گیگ - ۳۰ روزه",
        }
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            resp = await client.post(
                f"{self._base_url}/api/v1/payment/request",
                headers=self._headers,
                json=body,
            )
        resp.raise_for_status()
        return resp.json()

    async def check_status(self, payment_id: str) -> dict:
        """چک وضعیت — برمیگردونه {'status': 'approved'|'pending'|'rejected'|'expired', ...}"""
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/payment/status",
                    headers=self._headers,
                    params={"order_id": payment_id},
                )
            if resp.status_code != 200:
                log.warning("pirooz status %d for %s", resp.status_code, payment_id)
                return {"status": "unknown"}
            return resp.json()
        except Exception as e:
            log.warning("pirooz check_status error: %s", e)
            return {"status": "unknown"}

    def verify_signature(self, body_bytes: bytes, signature: str) -> bool:
        """اعتبارسنجی X-Signature (HMAC-SHA256 با کلید API_KEY)."""
        if not self._api_key or not signature:
            return False
        expected = hmac.new(
            self._api_key.encode(), body_bytes, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature.lower())
