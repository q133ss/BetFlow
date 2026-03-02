from __future__ import annotations

import asyncio
import contextlib

from dotenv import load_dotenv
import uvicorn

from .bot import build_bot_application
from .admin_web import create_fastapi_app
from .config import Settings
from .db import Database


async def run() -> None:
    load_dotenv()
    settings = Settings.from_env()

    db = Database(settings.db_path)
    await db.init()

    telegram_app = build_bot_application(settings=settings, db=db)
    api_app = create_fastapi_app(settings=settings, db=db, bot=telegram_app.bot)

    server = uvicorn.Server(
        uvicorn.Config(api_app, host=settings.api_host, port=settings.api_port, log_level="info")
    )

    bot_initialized = False
    bot_started = False
    bot_polling = False

    server_task = asyncio.create_task(server.serve())
    bot_task = None

    async def start_bot() -> None:
        try:
            nonlocal bot_initialized, bot_started, bot_polling
            try:
                await telegram_app.initialize()
                bot_initialized = True
                await telegram_app.start()
                bot_started = True
                await telegram_app.updater.start_polling()
                bot_polling = True
            except Exception as exc:
                print(f"WARNING: Telegram bot failed to start, admin web is still available: {exc}")
                return
            await asyncio.Event().wait()
        except Exception as exc:
            print(f"WARNING: Telegram bot runtime error: {exc}")

    try:
        bot_task = asyncio.create_task(start_bot())
        await server_task
    finally:
        if bot_task:
            bot_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await bot_task
        if bot_polling:
            await telegram_app.updater.stop()
        if bot_started:
            await telegram_app.stop()
        if bot_initialized:
            await telegram_app.shutdown()
        await db.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
