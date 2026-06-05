import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Plan:
    id: str
    title: str
    data_limit_gb: int
    duration_days: int
    price_toman: int
    price_usdt: float


@dataclass
class Settings:
    telegram_token: str
    admin_ids: list[int]

    pasarguard_base_url: str
    pasarguard_username: str
    pasarguard_password: str
    pasarguard_default_group_ids: list[int]

    tetrapay_api_key: str
    tetrapay_base_url: str
    tetrapay_webhook_secret: str
    public_base_url: str

    webhook_host: str
    webhook_port: int

    db_path: str

    plans: list[Plan]
    messages: dict


def _split_ints(value: str) -> list[int]:
    return [int(x.strip()) for x in value.split(",") if x.strip()]


def load_settings(config_path: str = "config.yaml") -> Settings:
    cfg_file = Path(config_path)
    with cfg_file.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    plans = [Plan(**p) for p in raw["plans"]]

    return Settings(
        telegram_token=os.environ["TELEGRAM_BOT_TOKEN"],
        admin_ids=_split_ints(os.getenv("TELEGRAM_ADMIN_IDS", "")),
        pasarguard_base_url=os.environ["PASARGUARD_BASE_URL"].rstrip("/"),
        pasarguard_username=os.environ["PASARGUARD_USERNAME"],
        pasarguard_password=os.environ["PASARGUARD_PASSWORD"],
        pasarguard_default_group_ids=_split_ints(
            os.getenv("PASARGUARD_DEFAULT_GROUP_IDS", "1")
        ),
        tetrapay_api_key=os.environ["TETRAPAY_API_KEY"],
        tetrapay_base_url=os.environ["TETRAPAY_BASE_URL"].rstrip("/"),
        tetrapay_webhook_secret=os.getenv("TETRAPAY_WEBHOOK_SECRET", ""),
        public_base_url=os.environ["PUBLIC_BASE_URL"].rstrip("/"),
        webhook_host=os.getenv("WEBHOOK_HOST", "0.0.0.0"),
        webhook_port=int(os.getenv("WEBHOOK_PORT", "8080")),
        db_path=os.getenv("DB_PATH", "./data.db"),
        plans=plans,
        messages=raw["messages"],
    )


def find_plan(settings: Settings, plan_id: str) -> Plan | None:
    return next((p for p in settings.plans if p.id == plan_id), None)
