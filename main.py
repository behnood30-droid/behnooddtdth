"""نقطه ورود: ربات تلگرام + وب‌سرور FastAPI را همزمان اجرا می‌کند."""
import asyncio
import logging

import uvicorn
from telegram.ext import Application

from bot import register_handlers
from config import load_settings
from db import DB
from pasarguard import PasarGuardClient
from tetra import TetraClient
from webhook import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("main")


async def run() -> None:
    settings = load_settings()

    db = DB(settings.db_path)
    tetra = TetraClient(settings.tetra_api_key)
    panel = PasarGuardClient(
        base_url=settings.pasarguard_url,
        username=settings.pasarguard_username,
        password=settings.pasarguard_password,
        group_id=settings.pasarguard_group_id,
    )

    tg_app: Application = Application.builder().token(settings.telegram_token).build()
    tg_app.bot_data.update({
        "settings": settings,
        "db": db,
        "tetra": tetra,
        "panel": panel,
    })
    register_handlers(tg_app)

    web_app = create_app(settings, db, tetra, panel, tg_app.bot)
    uvi_config = uvicorn.Config(
        web_app,
        host="0.0.0.0",
        port=settings.webhook_port,
        log_level="info",
        access_log=True,
    )
    uvi_server = uvicorn.Server(uvi_config)

    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    log.info("Telegram bot polling started")
    log.info("FastAPI server starting on port %s", settings.webhook_port)

    try:
        await uvi_server.serve()
    finally:
        log.info("Shutting down...")
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        await tetra.close()
        await panel.close()
        log.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass
