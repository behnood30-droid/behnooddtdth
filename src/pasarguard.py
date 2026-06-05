"""
کلاینت برای پنل PasarGuard.

مستندات API: https://github.com/PasarGuard/panel  →  /docs بعد از اجرا
مسیرهای کلیدی:
  POST /api/admin/token          → گرفتن JWT با username/password (form-urlencoded)
  POST /api/user                 → ساخت کاربر جدید
  GET  /api/user/{username}      → خواندن کاربر
"""

import time
from datetime import datetime, timedelta, timezone

import httpx


class PasarGuardError(RuntimeError):
    pass


class PasarGuardClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        default_group_ids: list[int],
    ):
        self.base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._default_group_ids = default_group_ids
        self._token: str | None = None
        self._token_exp: float = 0.0
        self._client = httpx.AsyncClient(timeout=20.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def _login(self) -> None:
        url = f"{self.base_url}/api/admin/token"
        resp = await self._client.post(
            url,
            data={"username": self._username, "password": self._password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code != 200:
            raise PasarGuardError(
                f"login failed: {resp.status_code} {resp.text[:300]}"
            )
        data = resp.json()
        self._token = data["access_token"]
        # توکن معمولا حدود ۲۴ ساعت اعتبار دارد؛ ۲۳ ساعت کش می‌کنیم
        self._token_exp = time.time() + 23 * 3600

    async def _auth_headers(self) -> dict:
        if not self._token or time.time() > self._token_exp:
            await self._login()
        return {"Authorization": f"Bearer {self._token}"}

    async def create_user(
        self,
        username: str,
        data_limit_gb: int,
        duration_days: int,
        note: str = "",
    ) -> dict:
        """کاربر را در پنل ایجاد می‌کند و دیکشنری شامل subscription_url برمی‌گرداند."""
        expire_dt = datetime.now(timezone.utc) + timedelta(days=duration_days)
        payload = {
            "username": username,
            "status": "active",
            "expire": expire_dt.isoformat(),
            "data_limit": int(data_limit_gb) * 1024 * 1024 * 1024,  # bytes
            "data_limit_reset_strategy": "no_reset",
            "group_ids": self._default_group_ids,
            "note": note,
        }
        headers = await self._auth_headers()
        resp = await self._client.post(
            f"{self.base_url}/api/user",
            json=payload,
            headers=headers,
        )
        if resp.status_code not in (200, 201):
            raise PasarGuardError(
                f"create_user failed: {resp.status_code} {resp.text[:400]}"
            )
        body = resp.json()

        # PasarGuard معمولاً subscription_url را در پاسخ برمی‌گرداند ولی در مدل
        # UserResponse با exclude=True مخفی شده. اگر برنگشت، خودمان از روی
        # subscription_token می‌سازیم یا الگوی استاندارد /sub/{token}/ را استفاده می‌کنیم.
        sub_url = body.get("subscription_url")
        if not sub_url:
            token = body.get("subscription_token") or body.get("sub_token")
            if token:
                sub_url = f"{self.base_url}/sub/{token}/"
        if not sub_url:
            # fallback: کاربر را با GET می‌خوانیم؛ معمولاً subscription_url آنجا هست
            sub_url = await self._fetch_sub_url(username)

        return {
            "username": body.get("username", username),
            "subscription_url": sub_url,
            "raw": body,
        }

    async def _fetch_sub_url(self, username: str) -> str:
        headers = await self._auth_headers()
        resp = await self._client.get(
            f"{self.base_url}/api/user/{username}", headers=headers
        )
        if resp.status_code != 200:
            raise PasarGuardError(
                f"get_user failed: {resp.status_code} {resp.text[:300]}"
            )
        body = resp.json()
        url = body.get("subscription_url")
        if url and url.startswith("/"):
            url = f"{self.base_url}{url}"
        if not url:
            raise PasarGuardError(
                "subscription_url در پاسخ پنل پیدا نشد — "
                "ساختار API را در پنل خودت چک کن."
            )
        return url
