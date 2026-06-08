"""کلاینت پنل PasarGuard (فورک Marzban)."""
import logging
import time

import httpx

log = logging.getLogger(__name__)


class PasarGuardError(RuntimeError):
    pass


class PasarGuardClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        group_id: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._group_id = group_id
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._client = httpx.AsyncClient(timeout=20.0, verify=False)

    async def close(self) -> None:
        await self._client.aclose()

    async def _login(self) -> None:
        resp = await self._client.post(
            f"{self.base_url}/api/admin/token",
            data={"username": self._username, "password": self._password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise PasarGuardError(f"login failed {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        self._token = data["access_token"]
        self._token_exp = time.time() + 23 * 3600

    async def _auth(self) -> dict:
        if not self._token or time.time() >= self._token_exp:
            await self._login()
        return {"Authorization": f"Bearer {self._token}"}

    async def create_user(
        self,
        username: str,
        data_limit_gb: int,
        duration_days: int,
        order_id: str = "",
    ) -> dict:
        expire_ts = int(time.time()) + duration_days * 86400
        payload = {
            "username": username,
            "status": "active",
            "expire": expire_ts,
            "data_limit": data_limit_gb * 1_073_741_824,
            "data_limit_reset_strategy": "no_reset",
            "group_ids": [self._group_id],
            "note": f"Order: {order_id}",
        }
        headers = await self._auth()
        resp = await self._client.post(
            f"{self.base_url}/api/user",
            json=payload,
            headers=headers,
        )
        if resp.status_code not in (200, 201):
            raise PasarGuardError(
                f"create_user failed {resp.status_code}: {resp.text[:400]}"
            )
        body = resp.json()
        sub_url = body.get("subscription_url", "")
        if not sub_url:
            token = body.get("subscription_token") or body.get("sub_token")
            if token:
                sub_url = f"{self.base_url}/sub/{token}/"
        if not sub_url:
            sub_url = await self._fetch_sub_url(body.get("username", username))
        return {"username": body.get("username", username), "subscription_url": sub_url}

    async def _fetch_sub_url(self, username: str) -> str:
        headers = await self._auth()
        resp = await self._client.get(
            f"{self.base_url}/api/user/{username}", headers=headers
        )
        if resp.status_code != 200:
            raise PasarGuardError(
                f"get_user failed {resp.status_code}: {resp.text[:300]}"
            )
        body = resp.json()
        url = body.get("subscription_url", "")
        if url.startswith("/"):
            url = f"{self.base_url}{url}"
        if not url:
            raise PasarGuardError("subscription_url در پاسخ پنل یافت نشد.")
        return url
