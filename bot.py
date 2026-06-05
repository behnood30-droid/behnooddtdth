"""نقطه ورود: ربات تلگرام + وب‌سرور webhook را همزمان اجرا می‌کند."""

import asyncio
import logging

from aiohttp import web
from telegram.ext import Application

from src.config import load_settings
from src.db import DB
from src.handlers import register_handlers
from src.pasarguard import PasarGuardClient
from src.tetrapay import TetrapayClient
from src.webhook import build_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("bot")


async def main() -> None:
    settings = load_settings()
    db = DB(settings.db_path)
    panel = PasarGuardClient(
        base_url=settings.pasarguard_base_url,
        username=settings.pasarguard_username,
        password=settings.pasarguard_password,
        default_group_ids=settings.pasarguard_default_group_ids,
    )
    tetrapay = TetrapayClient(
        base_url=settings.tetrapay_base_url,
        api_key=settings.tetrapay_api_key,
        webhook_secret=settings.tetrapay_webhook_secret,
    )

    tg_app: Application = (
        Application.builder().token(settings.telegram_token).build()
    )
    tg_app.bot_data.update(
        {
            "settings": settings,
            "db": db,
            "panel": panel,
            "tetrapay": tetrapay,
        }
    )
    register_handlers(tg_app)

    web_app = build_app(settings, db, tetrapay, panel, tg_app.bot)
    runner = web.AppRunner(web_app)
    await runner.setup()
    site = web.TCPSite(runner, settings.webhook_host, settings.webhook_port)

    await tg_app.initialize()
    await tg_app.start()
    await site.start()
    await tg_app.updater.start_polling()
    log.info(
        "Bot started. Webhook on %s:%s",
        settings.webhook_host,
        settings.webhook_port,
    )

    try:
        # تا زمانی که سیگنال خاتمه نیامده، زنده بمان
        await asyncio.Event().wait()
    finally:
        log.info("Shutting down...")
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        await runner.cleanup()
        await panel.close()
        await tetrapay.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
