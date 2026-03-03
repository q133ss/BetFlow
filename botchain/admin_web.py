from __future__ import annotations

import hmac
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware
from telegram import Bot

from . import texts
from .config import Settings
from .db import Database
from .membership import ban_user_from_chats, unban_user_in_chats


class RejectPayload(BaseModel):
    reason: str | None = None


class LoginPayload(BaseModel):
    username: str
    password: str
    payment_id: int | None = None


class CancelSubscriptionPayload(BaseModel):
    reason: str | None = None


class AssignSubscriptionPayload(BaseModel):
    days: int = Field(default=30, ge=1, le=3650)
    reason: str | None = None


class ManagedChatPayload(BaseModel):
    chat_id: int
    title: str | None = None
    username: str | None = None
    is_active: bool = True


class ManagedChatStatusPayload(BaseModel):
    is_active: bool


class PremiumFolderLinkPayload(BaseModel):
    value: str


class BotMessageTemplatePayload(BaseModel):
    value: str


def _is_authenticated(request: Request) -> bool:
    return bool(request.session.get("is_admin"))


def create_fastapi_app(settings: Settings, db: Database, bot: Bot) -> FastAPI:
    app = FastAPI(title="BotChain Admin Web", version="1.0.0")
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.admin_session_secret,
        same_site="lax",
        https_only=settings.public_admin_url.startswith("https://"),
    )

    admin_html_path = Path(__file__).parent / "static" / "admin.html"
    login_html_path = Path(__file__).parent / "static" / "login.html"

    async def bot_message_text(template_key: str, **kwargs: Any) -> str:
        template = await db.get_bot_message_template(template_key)
        return texts.render_template(template, **kwargs)

    async def require_admin(request: Request) -> dict[str, Any]:
        if not _is_authenticated(request):
            raise HTTPException(status_code=401, detail="Unauthorized")
        return {"id": settings.admin_telegram_id, "username": settings.admin_web_username}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/admin/login")
    async def admin_login_page(
        request: Request,
        payment_id: int | None = Query(default=None),
    ):
        if _is_authenticated(request):
            target = "/admin"
            if payment_id:
                target += f"?payment_id={payment_id}"
            return RedirectResponse(url=target, status_code=303)
        return FileResponse(login_html_path)

    @app.post("/api/admin/login")
    async def admin_login(payload: LoginPayload, request: Request) -> dict[str, Any]:
        username_ok = hmac.compare_digest(payload.username, settings.admin_web_username)
        password_ok = hmac.compare_digest(payload.password, settings.admin_web_password)
        if not (username_ok and password_ok):
            raise HTTPException(status_code=401, detail="Invalid login or password")

        request.session.clear()
        request.session["is_admin"] = True
        request.session["username"] = settings.admin_web_username

        redirect_to = "/admin"
        if payload.payment_id:
            redirect_to += f"?payment_id={payload.payment_id}"

        return {"ok": True, "redirect_to": redirect_to}

    @app.post("/api/admin/logout")
    async def admin_logout(request: Request) -> dict[str, Any]:
        request.session.clear()
        return {"ok": True}

    @app.get("/admin/logout")
    async def admin_logout_page(request: Request):
        request.session.clear()
        return RedirectResponse(url="/admin/login", status_code=303)

    @app.get("/admin")
    async def admin_page(
        request: Request,
        payment_id: int | None = Query(default=None),
    ):
        if not _is_authenticated(request):
            target = "/admin/login"
            if payment_id:
                target += f"?payment_id={payment_id}"
            return RedirectResponse(url=target, status_code=303)
        return FileResponse(admin_html_path)

    @app.get("/api/overview")
    async def overview(_: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        return {
            "stats": await db.stats(),
            "pending_payments": await db.list_payments(limit=50, status="pending"),
            "users": await db.list_users(limit=200),
            "premium_folder_link": await db.get_premium_folder_link(),
        }

    @app.patch("/api/settings/premium-folder-link")
    async def update_premium_folder_link(
        payload: PremiumFolderLinkPayload,
        _: dict[str, Any] = Depends(require_admin),
    ) -> dict[str, Any]:
        link = payload.value.strip()
        if not link:
            raise HTTPException(status_code=400, detail="Link must not be empty")
        await db.set_premium_folder_link(link)
        return {"ok": True, "premium_folder_link": link}

    @app.get("/api/settings/bot-messages")
    async def list_bot_messages(_: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
        return await db.list_bot_message_templates()

    @app.patch("/api/settings/bot-messages/{template_key}")
    async def update_bot_message(
        template_key: str,
        payload: BotMessageTemplatePayload,
        _: dict[str, Any] = Depends(require_admin),
    ) -> dict[str, Any]:
        if not texts.is_known_bot_message_key(template_key):
            raise HTTPException(status_code=404, detail="Message template not found")
        value = payload.value.strip()
        if not value:
            raise HTTPException(status_code=400, detail="Message template must not be empty")
        template = await db.set_bot_message_template(template_key=template_key, value=value)
        return {"ok": True, "template": template}

    @app.get("/api/managed-chats")
    async def managed_chats(
        only_active: bool = Query(default=False),
        _: dict[str, Any] = Depends(require_admin),
    ) -> list[dict[str, Any]]:
        return await db.list_managed_chats(only_active=only_active)

    @app.post("/api/managed-chats")
    async def managed_chats_add(
        payload: ManagedChatPayload,
        _: dict[str, Any] = Depends(require_admin),
    ) -> dict[str, Any]:
        chat = await db.add_managed_chat(
            chat_id=payload.chat_id,
            title=payload.title,
            username=payload.username,
            is_active=payload.is_active,
        )
        return {"ok": True, "chat": chat}

    @app.patch("/api/managed-chats/{chat_id}")
    async def managed_chats_patch(
        chat_id: int,
        payload: ManagedChatStatusPayload,
        _: dict[str, Any] = Depends(require_admin),
    ) -> dict[str, Any]:
        chat = await db.set_managed_chat_active(chat_id=chat_id, is_active=payload.is_active)
        if not chat:
            raise HTTPException(status_code=404, detail="Managed chat not found")
        return {"ok": True, "chat": chat}

    @app.delete("/api/managed-chats/{chat_id}")
    async def managed_chats_delete(chat_id: int, _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        deleted = await db.remove_managed_chat(chat_id=chat_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Managed chat not found")
        return {"ok": True, "chat_id": chat_id}

    @app.get("/api/users")
    async def users(_: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
        return await db.list_users(limit=1000)

    @app.get("/api/users/{user_id}/dialog")
    async def user_dialog(user_id: int, _: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
        return await db.get_dialog(user_id=user_id, limit=500)

    @app.get("/api/users/{user_id}/payments")
    async def user_payments(user_id: int, _: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
        return await db.list_user_payments(user_id=user_id, limit=500)

    @app.post("/api/users/{user_id}/cancel-subscription")
    async def cancel_subscription(
        user_id: int,
        payload: CancelSubscriptionPayload,
        admin: dict[str, Any] = Depends(require_admin),
    ) -> dict[str, Any]:
        reason = (payload.reason or "Canceled by admin").strip()
        user = await db.cancel_subscription_by_admin(user_id=user_id)
        if not user:
            raise HTTPException(status_code=400, detail="User not found or subscription already inactive")

        removed: list[int] = []
        failed: dict[int, str] = {}
        managed_chat_ids = await db.list_managed_chat_ids(only_active=True)
        if managed_chat_ids:
            removed, failed = await ban_user_from_chats(
                bot=bot,
                chat_ids=managed_chat_ids,
                user_id=user_id,
            )
            if removed:
                await db.set_user_channel_memberships(user_id=user_id, chat_ids=removed, is_member=False)

        message = await bot_message_text("canceled_by_admin_template", reason=reason)
        try:
            await bot.send_message(chat_id=user_id, text=message, disable_web_page_preview=True)
            await db.log_dialog(user_id, "out", message)
        except Exception as exc:
            await db.log_dialog(
                user_id,
                "system",
                f"cancel_subscription_notify_failed:user_id={user_id};error={exc}"[:4000],
            )

        await db.log_dialog(
            user_id,
            "system",
            (
                f"subscription_canceled_by_admin:admin_id={admin['id']};reason={reason};"
                f"removed={','.join(str(chat_id) for chat_id in removed) if removed else '-'};"
                f"failed={';'.join(f'{chat_id}:{error}' for chat_id, error in failed.items()) if failed else '-'}"
            )[:4000],
        )
        return {"ok": True, "user": user, "removed_from_chats": removed, "failed_chats": failed}

    @app.post("/api/users/{user_id}/assign-subscription")
    async def assign_subscription(
        user_id: int,
        payload: AssignSubscriptionPayload,
        admin: dict[str, Any] = Depends(require_admin),
    ) -> dict[str, Any]:
        existing_user = await db.get_user(user_id)
        should_unban = bool(
            existing_user
            and existing_user.get("subscription_status") != "subscribed"
        )

        reason = (payload.reason or "Assigned by admin").strip()
        user = await db.assign_subscription_by_admin(user_id=user_id, days=payload.days)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        unbanned: list[int] = []
        failed_unban: dict[int, str] = {}
        managed_chat_ids = await db.list_managed_chat_ids(only_active=True)
        if managed_chat_ids and should_unban:
            unbanned, failed_unban = await unban_user_in_chats(
                bot=bot,
                chat_ids=managed_chat_ids,
                user_id=user_id,
            )

        premium_folder_link = await db.get_premium_folder_link()
        message = await bot_message_text(
            "assigned_by_admin_template",
            days=payload.days,
            premium_link=premium_folder_link,
        )
        try:
            await bot.send_message(chat_id=user_id, text=message, disable_web_page_preview=False)
            await db.log_dialog(user_id, "out", message)
        except Exception as exc:
            await db.log_dialog(
                user_id,
                "system",
                f"assign_subscription_notify_failed:user_id={user_id};error={exc}"[:4000],
            )

        await db.log_dialog(
            user_id,
            "system",
            (
                f"subscription_assigned_by_admin:admin_id={admin['id']};days={payload.days};reason={reason};"
                f"unban_attempted={'1' if should_unban else '0'};"
                f"subscription_end_at={user.get('subscription_end_at') or '-'};"
                f"unbanned={','.join(str(chat_id) for chat_id in unbanned) if unbanned else '-'};"
                f"failed={';'.join(f'{chat_id}:{error}' for chat_id, error in failed_unban.items()) if failed_unban else '-'}"
            )[:4000],
        )

        return {
            "ok": True,
            "user": user,
            "unban_attempted": should_unban,
            "unbanned_chats": unbanned,
            "failed_unban": failed_unban,
        }

    @app.get("/api/payments")
    async def payments(
        status: str | None = Query(default=None),
        _: dict[str, Any] = Depends(require_admin),
    ) -> list[dict[str, Any]]:
        if status in {None, "", "all"}:
            return await db.list_payments(limit=1000, status=None)
        return await db.list_payments(limit=1000, status=status)

    @app.get("/api/payments/{payment_id}")
    async def payment(payment_id: int, _: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        data = await db.get_payment(payment_id)
        if not data:
            raise HTTPException(status_code=404, detail="Payment not found")
        return data

    @app.get("/api/payments/{payment_id}/receipt")
    async def payment_receipt(
        payment_id: int,
        _: dict[str, Any] = Depends(require_admin),
    ) -> Response:
        data = await db.get_payment(payment_id)
        if not data:
            raise HTTPException(status_code=404, detail="Payment not found")

        try:
            tg_file = await bot.get_file(str(data["file_id"]))
            payload = await tg_file.download_as_bytearray()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Failed to load receipt: {exc}") from exc

        file_path = tg_file.file_path or ""
        media_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        filename = Path(file_path).name if file_path else f"payment-{payment_id}"

        return Response(
            content=bytes(payload),
            media_type=media_type,
            headers={"Content-Disposition": 'inline; filename="{}"'.format(filename)},
        )

    @app.post("/api/payments/{payment_id}/approve")
    async def approve(payment_id: int, admin: dict[str, Any] = Depends(require_admin)) -> dict[str, Any]:
        payment_before = await db.get_payment(payment_id)
        if not payment_before:
            raise HTTPException(status_code=404, detail="Payment not found")
        user_id = int(payment_before["user_id"])
        existing_user = await db.get_user(user_id)
        should_unban = bool(
            existing_user
            and existing_user.get("subscription_status") != "subscribed"
        )

        reviewed = await db.approve_payment(payment_id, reviewed_by=int(admin["id"]))
        if not reviewed:
            raise HTTPException(status_code=400, detail="Payment already processed or missing")

        managed_chat_ids = await db.list_managed_chat_ids(only_active=True)
        if managed_chat_ids and should_unban:
            unbanned, failed_unban = await unban_user_in_chats(
                bot=bot,
                chat_ids=managed_chat_ids,
                user_id=user_id,
            )
            await db.log_dialog(
                user_id,
                "system",
                (
                    f"subscription_reactivated_unban:unban_attempted={'1' if should_unban else '0'};"
                    f"unbanned={','.join(str(chat_id) for chat_id in unbanned) if unbanned else '-'};"
                    f"failed={';'.join(f'{chat_id}:{error}' for chat_id, error in failed_unban.items()) if failed_unban else '-'}"
                )[:4000],
            )
        else:
            await db.log_dialog(
                user_id,
                "system",
                f"subscription_reactivated_unban:unban_attempted={'1' if should_unban else '0'};unbanned=-;failed=-",
            )

        premium_folder_link = await db.get_premium_folder_link()
        message = await bot_message_text("approved_template", premium_link=premium_folder_link)
        await bot.send_message(
            chat_id=user_id,
            text=message,
            disable_web_page_preview=False,
        )
        await db.log_dialog(user_id, "out", message)

        return {"ok": True, "payment": reviewed, "unban_attempted": should_unban}

    @app.post("/api/payments/{payment_id}/reject")
    async def reject(
        payment_id: int,
        payload: RejectPayload,
        admin: dict[str, Any] = Depends(require_admin),
    ) -> dict[str, Any]:
        reason = (payload.reason or "No reason provided").strip()
        reviewed = await db.reject_payment(payment_id, reviewed_by=int(admin["id"]), reason=reason)
        if not reviewed:
            raise HTTPException(status_code=400, detail="Payment already processed or missing")

        user_id = int(reviewed["user_id"])
        message = await bot_message_text("rejected_template", reason=reason)
        await bot.send_message(chat_id=user_id, text=message)
        await db.log_dialog(user_id, "out", message)

        return {"ok": True, "payment": reviewed}

    return app
