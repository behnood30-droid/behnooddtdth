"""خواندن تنظیمات از متغیرهای محیطی."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    telegram_token: str
    admin_telegram_id: int
    pasarguard_url: str
    pasarguard_username: str
    pasarguard_password: str
    pasarguard_group_id: int
    usdt_bep20_address: str
    usdt_trc20_address: str
    bscscan_api_key: str
    support_username: str
    welcome_image_path: str
    db_path: str


def load_settings() -> Settings:
    return Settings(
        telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
        admin_telegram_id=int(os.environ["ADMIN_TELEGRAM_ID"]),
        pasarguard_url=os.environ["PASARGUARD_URL"].rstrip("/"),
        pasarguard_username=os.environ["PASARGUARD_USERNAME"],
        pasarguard_password=os.environ["PASARGUARD_PASSWORD"],
        pasarguard_group_id=int(os.getenv("PASARGUARD_GROUP_ID", "1")),
        usdt_bep20_address=os.environ["USDT_BEP20_ADDRESS"],
        usdt_trc20_address=os.environ["USDT_TRC20_ADDRESS"],
        bscscan_api_key=os.environ["BSCSCAN_API_KEY"],
        support_username=os.getenv("SUPPORT_USERNAME", "support"),
        welcome_image_path=os.getenv("WELCOME_IMAGE_PATH", ""),
        db_path=os.getenv("DB_PATH", "./orders.db"),
    )
