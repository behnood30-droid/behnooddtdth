"""نقطه ورود: PTB polling + FastAPI webhook + scheduler."""
import asyncio
import logging
import signal

import uvicorn
from telegram.ext import Application

from bot import register_handlers
from config import load_settings
from db import DB
from pasarguard import PasarGuardClient
from pirooz import PiroozClient
from scheduler import charge_monitor_loop
from webhook import create_webhook_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("main")


async def run() -> None:
    settings = load_settings()
    db = DB(settings.db_path)

    panel = PasarGuardClient(
        base_url=settings.pasarguard_url,
        username=settings.pasarguard_username,
        password=settings.pasarguard_password,
        group_id=settings.pasarguard_group_id,
    )

    pirooz = PiroozClient(
        api_key=settings.pirooz_api_key,
        provider_key=settings.pirooz_provider_key,
        base_url=settings.pirooz_base_url,
    )

    tg_app: Application = Application.builder().token(settings.telegram_token).build()
    tg_app.bot_data.update({
        "settings": settings,
        "db": db,
        "panel": panel,
        "pirooz": pirooz,
    })
    register_handlers(tg_app)

    # FastAPI for Pirooz webhook
    fastapi_app = create_webhook_app(db, settings, pirooz, panel, tg_app.bot)
    uv_config = uvicorn.Config(
        fastapi_app,
        host="0.0.0.0",
        port=settings.webhook_port,
        log_level="warning",
        access_log=False,
    )
    uv_server = uvicorn.Server(uv_config)

    # Scheduler
    monitor_task = asyncio.create_task(
        charge_monitor_loop(tg_app.bot, db, settings, pirooz, panel)
    )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async with tg_app:
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)
        log.info("Bot started (polling mode)")

        # Run uvicorn alongside PTB
        uv_task = asyncio.create_task(uv_server.serve())
        log.info("Webhook server started on port %d", settings.webhook_port)

        await stop.wait()

        log.info("Shutting down...")
        uv_server.should_exit = True
        await uv_task

        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        await tg_app.updater.stop()
        await tg_app.stop()

    await panel.close()
    log.info("Bye.")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass
