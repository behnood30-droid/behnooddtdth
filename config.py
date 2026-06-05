"""خواندن تنظیمات از متغیرهای محیطی."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    telegram_token: str
    tetra_api_key: str
    pasarguard_url: str
    pasarguard_username: str
    pasarguard_password: str
    pasarguard_group_id: int
    webhook_domain: str
    webhook_port: int
    admin_telegram_id: int
    db_path: str


def load_settings() -> Settings:
    return Settings(
        telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
        tetra_api_key=os.environ["TETRA_API_KEY"],
        pasarguard_url=os.environ["PASARGUARD_URL"].rstrip("/"),
        pasarguard_username=os.environ["PASARGUARD_USERNAME"],
        pasarguard_password=os.environ["PASARGUARD_PASSWORD"],
        pasarguard_group_id=int(os.getenv("PASARGUARD_GROUP_ID", "1")),
        webhook_domain=os.environ["WEBHOOK_DOMAIN"].rstrip("/"),
        webhook_port=int(os.getenv("WEBHOOK_PORT", "8080")),
        admin_telegram_id=int(os.environ["ADMIN_TELEGRAM_ID"]),
        db_path=os.getenv("DB_PATH", "./orders.db"),
    )
