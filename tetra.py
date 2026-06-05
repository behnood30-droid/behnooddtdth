"""کلاینت درگاه پرداخت tetra98."""
import logging

import httpx

TETRA_BASE = "https://tetra98.com"

log = logging.getLogger(__name__)


class TetraError(RuntimeError):
    pass


class TetraClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=20.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def create_order(
        self,
        order_id: str,
        amount_rial: int,
        callback_url: str,
    ) -> dict:
        """یک سفارش پرداخت می‌سازه و لینک‌های پرداخت رو برمی‌گردونه."""
        payload = {
            "ApiKey": self._api_key,
            "Hash_id": order_id,
            "Amount": amount_rial,
            "Description": "خرید کانفیگ V2Ray",
            "Email": "customer@peech.ir",
            "Mobile": "09120000000",
            "CallbackURL": callback_url,
        }
        resp = await self._client.post(f"{TETRA_BASE}/api/create_order", json=payload)
        if resp.status_code != 200:
            raise TetraError(f"create_order HTTP {resp.status_code}: {resp.text[:400]}")

        body = resp.json()
        log.debug("tetra create_order response: %s", body)

        if str(body.get("status")) != "100":
            raise TetraError(f"tetra98 error response: {body}")

        return {
            "authority": str(body["Authority"]),
            "payment_url_bot": str(body.get("payment_url_bot", "")),
            "payment_url_web": str(body.get("payment_url_web", "")),
            "tracking_id": str(body.get("tracking_id", "")),
        }

    async def verify(self, authority: str) -> bool:
        """پرداخت رو با tetra98 verify می‌کنه. True = موفق."""
        payload = {
            "authority": authority,
            "ApiKey": self._api_key,
        }
        resp = await self._client.post(f"{TETRA_BASE}/api/verify", json=payload)
        if resp.status_code != 200:
            raise TetraError(f"verify HTTP {resp.status_code}: {resp.text[:300]}")

        body = resp.json()
        log.debug("tetra verify response: %s", body)
        return str(body.get("status")) == "100"
