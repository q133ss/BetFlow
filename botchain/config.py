from __future__ import annotations

import os
from dataclasses import dataclass


def _getenv_clean(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        value = os.getenv(f"\ufeff{name}")
    if value is None:
        value = default
    return value.strip()


@dataclass(slots=True)
class Settings:
    telegram_bot_token: str
    admin_telegram_id: int
    public_admin_url: str
    admin_web_username: str
    admin_web_password: str
    admin_session_secret: str
    premium_folder_link: str
    db_path: str
    api_host: str
    api_port: int
    managed_chat_ids: list[int]
    subscription_sweep_seconds: int

    @classmethod
    def from_env(cls) -> "Settings":
        token = _getenv_clean("TELEGRAM_BOT_TOKEN")
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        admin_raw = _getenv_clean("ADMIN_TELEGRAM_ID")
        if not admin_raw:
            raise ValueError("ADMIN_TELEGRAM_ID is required")

        public_admin_url = _getenv_clean("PUBLIC_ADMIN_URL", "http://localhost:8080").rstrip("/")
        admin_username = _getenv_clean("ADMIN_WEB_USERNAME")
        admin_password = _getenv_clean("ADMIN_WEB_PASSWORD")
        admin_session_secret = _getenv_clean("ADMIN_SESSION_SECRET")
        if not admin_username or not admin_password:
            raise ValueError("ADMIN_WEB_USERNAME and ADMIN_WEB_PASSWORD are required")
        if not admin_session_secret:
            raise ValueError("ADMIN_SESSION_SECRET is required")

        managed_chat_ids_raw = _getenv_clean("MANAGED_CHAT_IDS", "")
        managed_chat_ids: list[int] = []
        if managed_chat_ids_raw:
            for chunk in managed_chat_ids_raw.split(","):
                value = chunk.strip()
                if not value:
                    continue
                try:
                    managed_chat_ids.append(int(value))
                except ValueError as exc:
                    raise ValueError("MANAGED_CHAT_IDS must contain comma-separated integer chat ids") from exc

        sweep_raw = _getenv_clean("SUBSCRIPTION_SWEEP_SECONDS", "60")
        try:
            subscription_sweep_seconds = max(30, int(sweep_raw))
        except ValueError as exc:
            raise ValueError("SUBSCRIPTION_SWEEP_SECONDS must be an integer") from exc

        return cls(
            telegram_bot_token=token,
            admin_telegram_id=int(admin_raw),
            public_admin_url=public_admin_url,
            admin_web_username=admin_username,
            admin_web_password=admin_password,
            admin_session_secret=admin_session_secret,
            premium_folder_link=_getenv_clean("PREMIUM_FOLDER_LINK", "https://t.me/+replace_me"),
            db_path=_getenv_clean("DB_PATH", "./botchain.db"),
            api_host=_getenv_clean("API_HOST", "0.0.0.0"),
            api_port=int(_getenv_clean("API_PORT", "8080")),
            managed_chat_ids=managed_chat_ids,
            subscription_sweep_seconds=subscription_sweep_seconds,
        )
