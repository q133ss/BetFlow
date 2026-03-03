from __future__ import annotations

import asyncio
import contextlib

from dotenv import load_dotenv
from telegram import Update
import uvicorn

from .bot import build_bot_application, subscription_expiry_loop
from .admin_web import create_fastapi_app
from .config import Settings
from .db import Database


async def run() -> None:
    load_dotenv()
    settings = Settings.from_env()

    db = Database(settings.db_path)
    await db.init()
    seeded_chats = await db.seed_managed_chats(settings.managed_chat_ids)
    if seeded_chats:
        print(f"INFO: seeded {seeded_chats} managed chats from MANAGED_CHAT_IDS")

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
    expiry_task = None

    async def start_bot() -> None:
        try:
            nonlocal bot_initialized, bot_started, bot_polling, expiry_task
            try:
                await telegram_app.initialize()
                bot_initialized = True
                await telegram_app.start()
                bot_started = True
                await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
                bot_polling = True
                try:
                    startup_text = await db.get_bot_message_template("bot_online_text")
                    await telegram_app.bot.send_message(
                        chat_id=settings.admin_telegram_id,
                        text=startup_text,
                    )
                except Exception as exc:
                    print(f"WARNING: failed to send startup admin message: {exc}")
                expiry_task = asyncio.create_task(subscription_expiry_loop(telegram_app))
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
        if expiry_task:
            expiry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await expiry_task
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
