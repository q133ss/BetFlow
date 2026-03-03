from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings
from .db import Database, utcnow
from .membership import ban_user_from_chats
from . import texts


def start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Subscribe", callback_data="subscribe")]]
    )


def subscribe_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="cancel")]])


def format_info(user: dict[str, Any]) -> str:
    status = "Subscribed" if user.get("subscription_status") == "subscribed" else "Not Subscribed"
    start_date = _fmt_dt(user.get("subscription_start_at"))
    end_date = _fmt_dt(user.get("subscription_end_at"))

    username = user.get("username")
    username_line = f"@{username}" if username else "-"

    return (
        "✨ User Details ✨\n\n"
        f"Full Name: {user.get('full_name', '-')}\n\n"
        f"Username: {username_line}\n\n"
        f"User ID: {user.get('user_id', '-')}\n\n"
        "Subscription Details:\n\n"
        f"Status: {status}\n\n"
        f"⏳ Start Date:\n{start_date}\n\n"
        f"End Date:\n{end_date}"
    )


def _fmt_dt(value: str | None) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


async def ensure_user(update: Update, db: Database) -> int | None:
    user = update.effective_user
    if not user:
        return None
    full_name = " ".join(part for part in [user.first_name, user.last_name] if part).strip() or "Unknown"
    await db.upsert_user(user.id, full_name=full_name, username=user.username)
    return user.id


async def send_and_log(
    context: ContextTypes.DEFAULT_TYPE,
    db: Database,
    user_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> None:
    await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        disable_web_page_preview=True,
    )
    await db.log_dialog(user_id, "out", text)


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)] + "…"


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    user_id = await ensure_user(update, db)
    if user_id is None:
        return

    first_name = (update.effective_user.first_name if update.effective_user else None) or "Alexey"
    if update.message:
        await db.log_dialog(user_id, "in", update.message.text or "/start")

    text = texts.START_TEMPLATE.format(first_name=first_name)
    await send_and_log(context, db, user_id, text, reply_markup=start_keyboard())


async def subscribe_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    user_id = await ensure_user(update, db)
    if user_id is None:
        return

    if update.message:
        await db.log_dialog(user_id, "in", update.message.text or "/subscribe")

    await db.set_awaiting_receipt(user_id, hours=5)
    await send_and_log(context, db, user_id, texts.SUBSCRIBE_TEXT, reply_markup=subscribe_keyboard())


async def info_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    user_id = await ensure_user(update, db)
    if user_id is None:
        return

    if update.message:
        await db.log_dialog(user_id, "in", update.message.text or "/info")

    user = await db.get_user(user_id)
    if not user:
        return

    await send_and_log(context, db, user_id, format_info(user))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    query = update.callback_query
    if not query or not update.effective_user:
        return

    await query.answer()
    user_id = update.effective_user.id
    await ensure_user(update, db)
    await db.log_dialog(user_id, "in", f"button:{query.data}")

    if query.data == "subscribe":
        await db.set_awaiting_receipt(user_id, hours=5)
        await send_and_log(context, db, user_id, texts.SUBSCRIBE_TEXT, reply_markup=subscribe_keyboard())
        return

    if query.data == "cancel":
        await db.clear_awaiting_receipt(user_id)
        msg = "Subscription flow canceled. Send /subscribe when you're ready."
        await send_and_log(context, db, user_id, msg, reply_markup=start_keyboard())
        return


async def receipt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    settings: Settings = context.application.bot_data["settings"]

    user_id = await ensure_user(update, db)
    if user_id is None or not update.message:
        return

    caption = (update.message.caption or "").strip()
    file_type = "unknown"
    file_id = ""

    if update.message.photo:
        file_type = "photo"
        file_id = update.message.photo[-1].file_id
        await db.log_dialog(user_id, "in", f"[photo receipt] {caption}".strip())
    elif update.message.document:
        file_type = "document"
        file_id = update.message.document.file_id
        await db.log_dialog(user_id, "in", f"[document receipt] {caption}".strip())

    user = await db.get_user(user_id)
    if not user:
        return

    awaiting_until = user.get("awaiting_receipt_until")
    if not awaiting_until:
        await send_and_log(
            context,
            db,
            user_id,
            "Please send /subscribe first, then upload your receipt.",
        )
        return

    try:
        deadline = datetime.fromisoformat(awaiting_until)
    except ValueError:
        deadline = utcnow()

    if utcnow() > deadline:
        await db.clear_awaiting_receipt(user_id)
        await send_and_log(
            context,
            db,
            user_id,
            "Receipt window expired. Send /subscribe to request a new payment session.",
        )
        return

    if not file_id:
        await send_and_log(
            context,
            db,
            user_id,
            "Could not read the receipt. Please send it as a photo or document.",
        )
        return

    payment_id = await db.create_payment(
        user_id=user_id,
        file_id=file_id,
        file_type=file_type,
        caption=caption or None,
    )
    await db.clear_awaiting_receipt(user_id)

    await send_and_log(context, db, user_id, texts.RECEIPT_ACCEPTED_TEXT)

    admin_url = f"{settings.public_admin_url}/admin?payment_id={payment_id}"
    receipt_text = _truncate(caption or "Not provided", 400)
    admin_caption = (
        "New payment request.\n\n"
        f"Payment ID: {payment_id}\n"
        f"User: {user.get('full_name')}\n"
        f"Username: {('@' + user.get('username')) if user.get('username') else '-'}\n"
        f"User ID: {user_id}\n\n"
        f"Admin panel link: {admin_url}\n\n"
        f"Receipt text:\n{receipt_text}"
    )
    admin_markup = InlineKeyboardMarkup([[InlineKeyboardButton("Open admin panel", url=admin_url)]])

    try:
        if file_type == "photo":
            await context.bot.send_photo(
                chat_id=settings.admin_telegram_id,
                photo=file_id,
                caption=admin_caption,
            )
        else:
            await context.bot.send_document(
                chat_id=settings.admin_telegram_id,
                document=file_id,
                caption=admin_caption,
            )
        try:
            await context.bot.send_message(
                chat_id=settings.admin_telegram_id,
                text=f"Open admin panel: {admin_url}",
                reply_markup=admin_markup,
                disable_web_page_preview=True,
            )
        except Exception as btn_exc:
            print(
                f"WARNING: failed to send admin panel button for payment {payment_id}: {btn_exc}"
            )
            await context.bot.send_message(
                chat_id=settings.admin_telegram_id,
                text=f"Open admin panel: {admin_url}",
                disable_web_page_preview=True,
            )
        await db.log_dialog(user_id, "system", f"admin_notified:payment_id={payment_id}")
    except Exception as exc:
        # Avoid breaking receipt flow if admin notification fails.
        print(f"ERROR: failed to notify admin for payment {payment_id}: {exc}")
        await db.log_dialog(user_id, "system", f"admin_notify_failed:payment_id={payment_id};error={exc}")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    user_id = await ensure_user(update, db)
    if user_id is None or not update.message:
        return

    incoming = update.message.text or "[non-text]"
    await db.log_dialog(user_id, "in", incoming)

    if incoming.startswith("/"):
        return

    await send_and_log(
        context,
        db,
        user_id,
        "Send /subscribe to buy access or /info to view your subscription details.",
    )


def _format_chat_op_log(prefix: str, removed: list[int], failed: dict[int, str]) -> str:
    removed_part = ",".join(str(chat_id) for chat_id in removed) if removed else "-"
    failed_part = ";".join(f"{chat_id}:{error}" for chat_id, error in failed.items()) if failed else "-"
    return f"{prefix};removed={removed_part};failed={failed_part}"[:4000]


def _format_username(username: str | None) -> str:
    return f"@{username}" if username else "-"


def _format_chat_ids(chat_ids: list[int]) -> str:
    return ",".join(str(chat_id) for chat_id in chat_ids) if chat_ids else "-"


def _format_chat_errors(failed: dict[int, str]) -> str:
    if not failed:
        return "-"
    return "; ".join(f"{chat_id}:{error}" for chat_id, error in failed.items())


async def process_subscription_expiry_reminders(app: Application) -> None:
    db: Database = app.bot_data["db"]
    now = utcnow()

    for days_before_end in (3, 2, 1):
        min_end_iso = (now + timedelta(days=days_before_end - 1)).isoformat()
        max_end_iso = (now + timedelta(days=days_before_end)).isoformat()
        candidates = await db.list_subscription_reminder_candidates(
            min_end_iso=min_end_iso,
            max_end_iso=max_end_iso,
            days_before_end=days_before_end,
            limit=200,
        )
        for user in candidates:
            user_id = int(user["user_id"])
            text = texts.SUBSCRIPTION_EXPIRING_TEMPLATE.format(days=days_before_end)
            try:
                await app.bot.send_message(chat_id=user_id, text=text)
                await db.log_dialog(user_id, "out", text)
                await db.mark_subscription_reminder_sent(
                    user_id=user_id,
                    days_before_end=days_before_end,
                )
            except Exception as exc:
                await db.log_dialog(
                    user_id,
                    "system",
                    (
                        "subscription_expiry_reminder_failed:"
                        f"user_id={user_id};days={days_before_end};error={exc}"
                    )[:4000],
                )


async def process_expired_subscriptions(app: Application) -> None:
    db: Database = app.bot_data["db"]
    settings: Settings = app.bot_data["settings"]
    managed_chat_ids = await db.list_managed_chat_ids(only_active=True)

    expired = await db.list_expired_subscriptions(now_iso=utcnow().isoformat(), limit=200)
    for user in expired:
        user_id = int(user["user_id"])
        removed, failed = await ban_user_from_chats(
            bot=app.bot,
            chat_ids=managed_chat_ids,
            user_id=user_id,
        )
        await db.deactivate_subscription(user_id)
        await db.log_dialog(
            user_id,
            "system",
            _format_chat_op_log("subscription_expired:auto", removed=removed, failed=failed),
        )

        try:
            await app.bot.send_message(chat_id=user_id, text=texts.SUBSCRIPTION_EXPIRED_TEMPLATE)
            await db.log_dialog(user_id, "out", texts.SUBSCRIPTION_EXPIRED_TEMPLATE)
        except Exception as exc:
            await db.log_dialog(
                user_id,
                "system",
                f"subscription_expired_notify_failed:user_id={user_id};error={exc}"[:4000],
            )

        admin_text = texts.ADMIN_SUBSCRIPTION_EXPIRED_TEMPLATE.format(
            full_name=user.get("full_name") or "-",
            username=_format_username(user.get("username")),
            user_id=user_id,
            subscription_end_at=user.get("subscription_end_at") or "-",
            removed=_format_chat_ids(removed),
            failed=_format_chat_errors(failed),
        )
        try:
            await app.bot.send_message(chat_id=settings.admin_telegram_id, text=admin_text[:4000])
        except Exception as exc:
            await db.log_dialog(
                user_id,
                "system",
                f"admin_expiry_notify_failed:user_id={user_id};error={exc}"[:4000],
            )


async def subscription_expiry_loop(app: Application) -> None:
    settings: Settings = app.bot_data["settings"]
    while True:
        try:
            await process_subscription_expiry_reminders(app)
            await process_expired_subscriptions(app)
        except Exception as exc:
            print(f"ERROR: subscription expiry sweep failed: {exc}")
        await asyncio.sleep(settings.subscription_sweep_seconds)


def build_bot_application(settings: Settings, db: Database) -> Application:
    app = Application.builder().token(settings.telegram_bot_token).build()

    app.bot_data["settings"] = settings
    app.bot_data["db"] = db

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("subscribe", subscribe_handler))
    app.add_handler(CommandHandler("info", info_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receipt_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))

    return app
