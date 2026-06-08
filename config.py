"""خواندن تنظیمات از متغیرهای محیطی."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _req(key: str) -> str:
    v = os.getenv(key, "").strip()
    if not v:
        raise RuntimeError(f"Missing required env var: {key}")
    return v


@dataclass
class Settings:
    telegram_token: str
    admin_telegram_id: int
    pasarguard_url: str
    pasarguard_username: str
    pasarguard_password: str
    pasarguard_group_id: int
    webhook_domain: str
    webhook_port: int
    usdt_bep20_address: str
    usdt_trc20_address: str
    bscscan_api_key: str
    pirooz_api_key: str
    pirooz_provider_key: str
    pirooz_base_url: str
    support_username: str
    db_path: str


def load_settings() -> Settings:
    return Settings(
        telegram_token=_req("TELEGRAM_BOT_TOKEN"),
        admin_telegram_id=int(_req("ADMIN_TELEGRAM_ID")),
        pasarguard_url=_req("PASARGUARD_URL").rstrip("/"),
        pasarguard_username=_req("PASARGUARD_USERNAME"),
        pasarguard_password=_req("PASARGUARD_PASSWORD"),
        pasarguard_group_id=int(os.getenv("PASARGUARD_GROUP_ID", "1")),
        webhook_domain=os.getenv("WEBHOOK_DOMAIN", "").rstrip("/"),
        webhook_port=int(os.getenv("WEBHOOK_PORT", "8080")),
        usdt_bep20_address=os.getenv("USDT_BEP20_ADDRESS", ""),
        usdt_trc20_address=os.getenv("USDT_TRC20_ADDRESS", ""),
        bscscan_api_key=os.getenv("BSCSCAN_API_KEY", ""),
        pirooz_api_key=os.getenv("PIROOZ_API_KEY", ""),
        pirooz_provider_key=os.getenv("PIROOZ_PROVIDER_KEY", ""),
        pirooz_base_url=os.getenv("PIROOZ_BASE_URL", "http://178.63.207.241:8080").rstrip("/"),
        support_username=os.getenv("SUPPORT_USERNAME", "support"),
        db_path=os.getenv("DB_PATH", "./orders.db"),
    )
