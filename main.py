"""نقطه ورود: ربات تلگرام + scheduler پس‌زمینه."""
import asyncio
import logging
import signal

from telegram.ext import Application

from bot import register_handlers
from config import load_settings
from db import DB
from pasarguard import PasarGuardClient
from scheduler import charge_monitor_loop

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

    tg_app: Application = (
        Application.builder().token(settings.telegram_token).build()
    )
    tg_app.bot_data.update({"settings": settings, "db": db, "panel": panel})
    register_handlers(tg_app)

    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    log.info("Bot started (polling)")

    # اجرای scheduler به صورت پس‌زمینه
    monitor_task = asyncio.create_task(
        charge_monitor_loop(tg_app.bot, db, settings)
    )

    # صبر برای سیگنال خاتمه
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()

    log.info("Shutting down...")
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

    await tg_app.updater.stop()
    await tg_app.stop()
    await tg_app.shutdown()
    await panel.close()
    log.info("Bye.")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass
