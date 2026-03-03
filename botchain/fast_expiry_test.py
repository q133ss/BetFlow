from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta as real_timedelta

from dotenv import load_dotenv
from telegram import Update

from .bot import (
    build_bot_application,
    process_expired_subscriptions,
    process_subscription_expiry_reminders,
)
from . import bot as bot_module
from .config import Settings
from .db import Database

# Time compression for testing:
# 1 production "day" in reminder math equals 10 real seconds.
SECONDS_PER_PROD_DAY = 10
FAST_SWEEP_SECONDS = 1


def _scaled_timedelta(*args, **kwargs):
    # Keep timedelta API shape, but reinterpret "days" as seconds for fast tests.
    values = [0, 0, 0, 0, 0, 0, 0]
    for idx, value in enumerate(args[:7]):
        values[idx] = value

    days = kwargs.pop("days", values[0])
    seconds = kwargs.pop("seconds", values[1])
    microseconds = kwargs.pop("microseconds", values[2])
    milliseconds = kwargs.pop("milliseconds", values[3])
    minutes = kwargs.pop("minutes", values[4])
    hours = kwargs.pop("hours", values[5])
    weeks = kwargs.pop("weeks", values[6])
    if kwargs:
        raise TypeError(f"Unexpected timedelta kwargs: {', '.join(kwargs.keys())}")

    return real_timedelta(
        weeks=weeks,
        hours=hours,
        minutes=minutes,
        seconds=seconds + (days * SECONDS_PER_PROD_DAY),
        milliseconds=milliseconds,
        microseconds=microseconds,
    )


async def subscription_expiry_loop_fast(app) -> None:
    while True:
        try:
            await process_subscription_expiry_reminders(app)
            await process_expired_subscriptions(app)
        except Exception as exc:
            print(f"ERROR: fast subscription expiry sweep failed: {exc}")
        await asyncio.sleep(FAST_SWEEP_SECONDS)


async def run() -> None:
    load_dotenv()
    settings = Settings.from_env()

    db = Database(settings.db_path)
    await db.init()
    seeded_chats = await db.seed_managed_chats(settings.managed_chat_ids)
    if seeded_chats:
        print(f"INFO: seeded {seeded_chats} managed chats from MANAGED_CHAT_IDS")

    telegram_app = build_bot_application(settings=settings, db=db)
    bot_initialized = False
    bot_started = False
    bot_polling = False
    fast_task: asyncio.Task[None] | None = None
    original_timedelta = bot_module.timedelta

    try:
        bot_module.timedelta = _scaled_timedelta
        await telegram_app.initialize()
        bot_initialized = True
        await telegram_app.start()
        bot_started = True
        await telegram_app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        bot_polling = True

        try:
            await telegram_app.bot.send_message(
                chat_id=settings.admin_telegram_id,
                text=(
                    "FAST expiry test mode enabled (prod logic).\n"
                    "Time compression: 1 production day = 10 seconds.\n"
                    "Reminder windows: 30/20/10 seconds before end (as 3d/2d/1d).\n"
                    "Sweep interval: 1 second."
                ),
            )
        except Exception as exc:
            print(f"WARNING: failed to send fast-mode startup message: {exc}")

        fast_task = asyncio.create_task(subscription_expiry_loop_fast(telegram_app))
        await asyncio.Event().wait()
    finally:
        bot_module.timedelta = original_timedelta
        if fast_task:
            fast_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await fast_task
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
