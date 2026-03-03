from __future__ import annotations

import hmac
import mimetypes
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from telegram import Bot

from . import texts
from .config import Settings
from .db import Database


class RejectPayload(BaseModel):
    reason: str | None = None


class LoginPayload(BaseModel):
    username: str
    password: str
    payment_id: int | None = None


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
        }

    @app.get("/api/users")
    async def users(_: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
        return await db.list_users(limit=1000)

    @app.get("/api/users/{user_id}/dialog")
    async def user_dialog(user_id: int, _: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
        return await db.get_dialog(user_id=user_id, limit=500)

    @app.get("/api/users/{user_id}/payments")
    async def user_payments(user_id: int, _: dict[str, Any] = Depends(require_admin)) -> list[dict[str, Any]]:
        return await db.list_user_payments(user_id=user_id, limit=500)

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
        reviewed = await db.approve_payment(payment_id, reviewed_by=int(admin["id"]))
        if not reviewed:
            raise HTTPException(status_code=400, detail="Payment already processed or missing")

        user_id = int(reviewed["user_id"])
        message = texts.APPROVED_TEMPLATE.format(premium_link=settings.premium_folder_link)
        await bot.send_message(
            chat_id=user_id,
            text=message,
            disable_web_page_preview=False,
        )
        await db.log_dialog(user_id, "out", message)

        return {"ok": True, "payment": reviewed}

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
        message = texts.REJECTED_TEMPLATE.format(reason=reason)
        await bot.send_message(chat_id=user_id, text=message)
        await db.log_dialog(user_id, "out", message)

        return {"ok": True, "payment": reviewed}

    return app
