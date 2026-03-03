from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

from telegram import Chat, ChatMember, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from . import texts
from .config import Settings
from .db import Database, utcnow
from .membership import ban_user_from_chats


def start_keyboard(button_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(button_text, callback_data="subscribe")]]
    )


def subscribe_keyboard(button_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(button_text, callback_data="cancel")]])


async def _message_text(db: Database, key: str, **kwargs: Any) -> str:
    template = await db.get_bot_message_template(key)
    return texts.render_template(template, **kwargs)


async def format_info(db: Database, user: dict[str, Any]) -> str:
    status_key = (
        "info_status_subscribed"
        if user.get("subscription_status") == "subscribed"
        else "info_status_not_subscribed"
    )
    status = await db.get_bot_message_template(status_key)
    start_date = _fmt_dt(user.get("subscription_start_at"))
    end_date = _fmt_dt(user.get("subscription_end_at"))

    username = user.get("username")
    username_line = f"@{username}" if username else "-"

    return await _message_text(
        db,
        "info_template",
        full_name=user.get("full_name", "-"),
        username=username_line,
        user_id=user.get("user_id", "-"),
        status=status,
        start_date=start_date,
        end_date=end_date,
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
    disable_web_page_preview: bool = True,
) -> None:
    await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode=parse_mode,
        disable_web_page_preview=disable_web_page_preview,
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

    text = await _message_text(db, "start_template", first_name=first_name)
    start_button_text = await db.get_bot_message_template("start_button_text")
    await send_and_log(context, db, user_id, text, reply_markup=start_keyboard(start_button_text))


async def subscribe_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    user_id = await ensure_user(update, db)
    if user_id is None:
        return

    if update.message:
        await db.log_dialog(user_id, "in", update.message.text or "/subscribe")

    await db.set_awaiting_receipt(user_id, hours=5)
    subscribe_text = await db.get_bot_message_template("subscribe_text")
    cancel_button_text = await db.get_bot_message_template("cancel_button_text")
    await send_and_log(
        context,
        db,
        user_id,
        subscribe_text,
        reply_markup=subscribe_keyboard(cancel_button_text),
    )


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

    await send_and_log(context, db, user_id, await format_info(db, user))


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
        subscribe_text = await db.get_bot_message_template("subscribe_text")
        cancel_button_text = await db.get_bot_message_template("cancel_button_text")
        await send_and_log(
            context,
            db,
            user_id,
            subscribe_text,
            reply_markup=subscribe_keyboard(cancel_button_text),
        )
        return

    if query.data == "cancel":
        await db.clear_awaiting_receipt(user_id)
        msg = await db.get_bot_message_template("subscription_flow_canceled_text")
        start_button_text = await db.get_bot_message_template("start_button_text")
        await send_and_log(context, db, user_id, msg, reply_markup=start_keyboard(start_button_text))
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
            await db.get_bot_message_template("subscribe_first_before_receipt_text"),
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
            await db.get_bot_message_template("receipt_window_expired_text"),
        )
        return

    if not file_id:
        await send_and_log(
            context,
            db,
            user_id,
            await db.get_bot_message_template("receipt_unreadable_text"),
        )
        return

    payment_id = await db.create_payment(
        user_id=user_id,
        file_id=file_id,
        file_type=file_type,
        caption=caption or None,
    )
    await db.clear_awaiting_receipt(user_id)

    await send_and_log(context, db, user_id, await db.get_bot_message_template("receipt_accepted_text"))

    admin_url = f"{settings.public_admin_url}/admin?payment_id={payment_id}"
    receipt_text = _truncate(caption or "Not provided", 400)
    admin_caption = await _message_text(
        db,
        "admin_new_payment_template",
        payment_id=payment_id,
        full_name=user.get("full_name") or "-",
        username=("@"+user.get("username")) if user.get("username") else "-",
        user_id=user_id,
        admin_url=admin_url,
        receipt_text=receipt_text,
    )
    admin_caption = _truncate(admin_caption, 1024)
    admin_button_text = await db.get_bot_message_template("open_admin_panel_button_text")
    admin_markup = InlineKeyboardMarkup([[InlineKeyboardButton(admin_button_text, url=admin_url)]])
    open_admin_panel_text = await _message_text(db, "open_admin_panel_message_template", admin_url=admin_url)

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
                text=open_admin_panel_text,
                reply_markup=admin_markup,
                disable_web_page_preview=True,
            )
        except Exception as btn_exc:
            print(
                f"WARNING: failed to send admin panel button for payment {payment_id}: {btn_exc}"
            )
            await context.bot.send_message(
                chat_id=settings.admin_telegram_id,
                text=open_admin_panel_text,
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
        await db.get_bot_message_template("default_help_text"),
    )


def _is_active_chat_member(member: ChatMember) -> bool:
    if member.status in {"creator", "administrator", "member"}:
        return True
    if member.status == "restricted":
        return bool(getattr(member, "is_member", False))
    return False


def _is_supported_membership_chat(chat: Chat) -> bool:
    return chat.type in {Chat.CHANNEL, Chat.SUPERGROUP, Chat.GROUP}


def _member_full_name(chat_member_update: ChatMemberUpdated) -> str:
    user = chat_member_update.new_chat_member.user
    return " ".join(part for part in [user.first_name, user.last_name] if part).strip() or "Unknown"


async def my_chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    event = update.my_chat_member
    if not event or not _is_supported_membership_chat(event.chat):
        return

    chat = await db.touch_managed_chat_from_event(
        chat_id=event.chat.id,
        title=event.chat.title,
        username=event.chat.username,
    )
    is_active = _is_active_chat_member(event.new_chat_member)

    if is_active and int(chat["is_active"]) != 1:
        await db.set_managed_chat_active(chat_id=event.chat.id, is_active=True)
    if not is_active and int(chat["is_active"]) == 1:
        await db.set_managed_chat_active(chat_id=event.chat.id, is_active=False)


async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Database = context.application.bot_data["db"]
    settings: Settings = context.application.bot_data["settings"]
    event = update.chat_member
    if not event or not _is_supported_membership_chat(event.chat):
        return

    chat = await db.touch_managed_chat_from_event(
        chat_id=event.chat.id,
        title=event.chat.title,
        username=event.chat.username,
    )
    if int(chat["is_active"]) != 1:
        return

    member_user = event.new_chat_member.user
    if member_user.is_bot:
        return

    user_id = int(member_user.id)
    await db.upsert_user(
        user_id=user_id,
        full_name=_member_full_name(event),
        username=member_user.username,
    )

    was_member = _is_active_chat_member(event.old_chat_member)
    is_member = _is_active_chat_member(event.new_chat_member)
    await db.set_user_channel_membership(user_id=user_id, chat_id=event.chat.id, is_member=is_member)

    if not (is_member and not was_member):
        return

    if await db.has_active_subscription(user_id=user_id, now_iso=utcnow().isoformat()):
        return

    removed, failed = await ban_user_from_chats(
        bot=context.bot,
        chat_ids=[event.chat.id],
        user_id=user_id,
    )
    await db.set_user_channel_membership(user_id=user_id, chat_id=event.chat.id, is_member=False)
    await db.log_dialog(
        user_id,
        "system",
        (
            "chat_join_blocked:no_active_subscription;"
            f"chat_id={event.chat.id};removed={','.join(str(chat_id) for chat_id in removed) if removed else '-'};"
            f"failed={';'.join(f'{chat_id}:{error}' for chat_id, error in failed.items()) if failed else '-'}"
        )[:4000],
    )

    if failed:
        try:
            await context.bot.send_message(
                chat_id=settings.admin_telegram_id,
                text=(
                    await _message_text(
                        db,
                        "membership_enforcement_error_template",
                        user_id=user_id,
                        chat_id=event.chat.id,
                        errors=_format_chat_errors(failed),
                    )
                )[:4000],
            )
        except Exception as notify_exc:
            await db.log_dialog(
                user_id,
                "system",
                f"membership_enforcement_admin_notify_failed:user_id={user_id};error={notify_exc}"[:4000],
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
        reminder_template = await db.get_bot_message_template("subscription_expiring_template")
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
            text = texts.render_template(reminder_template, days=days_before_end)
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
    expired_template = await db.get_bot_message_template("subscription_expired_template")
    admin_expired_template = await db.get_bot_message_template("admin_subscription_expired_template")
    managed_chat_ids = await db.list_managed_chat_ids(only_active=True)

    expired = await db.list_expired_subscriptions(now_iso=utcnow().isoformat(), limit=200)
    for user in expired:
        user_id = int(user["user_id"])
        user_chat_ids = await db.list_user_channel_chat_ids(user_id=user_id, only_active=True)
        target_chat_ids = user_chat_ids or managed_chat_ids
        removed, failed = await ban_user_from_chats(
            bot=app.bot,
            chat_ids=target_chat_ids,
            user_id=user_id,
        )
        if removed:
            await db.set_user_channel_memberships(user_id=user_id, chat_ids=removed, is_member=False)
        await db.deactivate_subscription(user_id)
        await db.log_dialog(
            user_id,
            "system",
            _format_chat_op_log("subscription_expired:auto", removed=removed, failed=failed),
        )

        try:
            await app.bot.send_message(chat_id=user_id, text=expired_template)
            await db.log_dialog(user_id, "out", expired_template)
        except Exception as exc:
            await db.log_dialog(
                user_id,
                "system",
                f"subscription_expired_notify_failed:user_id={user_id};error={exc}"[:4000],
            )

        admin_text = texts.render_template(
            admin_expired_template,
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
    app.add_handler(ChatMemberHandler(my_chat_member_handler, ChatMemberHandler.MY_CHAT_MEMBER))
    app.add_handler(ChatMemberHandler(chat_member_handler, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, receipt_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), text_handler))

    return app
