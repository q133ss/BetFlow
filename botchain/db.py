from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import aiosqlite

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                username TEXT,
                first_seen_at TEXT NOT NULL,
                subscription_status TEXT NOT NULL DEFAULT 'not_subscribed',
                subscription_start_at TEXT,
                subscription_end_at TEXT,
                awaiting_receipt_until TEXT
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                file_type TEXT NOT NULL,
                caption TEXT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                reviewed_at TEXT,
                reviewed_by INTEGER,
                reject_reason TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS dialog_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                direction TEXT NOT NULL,
                message_text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            """
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()

    async def upsert_user(self, user_id: int, full_name: str, username: str | None) -> None:
        assert self._db is not None
        now = utcnow().isoformat()
        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO users (user_id, full_name, username, first_seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    full_name = excluded.full_name,
                    username = excluded.username
                """,
                (user_id, full_name, username, now),
            )
            await self._db.commit()

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        assert self._db is not None
        async with self._db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def list_users(self, limit: int = 200) -> list[dict[str, Any]]:
        assert self._db is not None
        async with self._db.execute(
            "SELECT * FROM users ORDER BY first_seen_at DESC LIMIT ?", (limit,)
        ) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def set_awaiting_receipt(self, user_id: int, hours: int = 5) -> str:
        assert self._db is not None
        until = utcnow() + timedelta(hours=hours)
        async with self._lock:
            await self._db.execute(
                "UPDATE users SET awaiting_receipt_until = ? WHERE user_id = ?",
                (until.isoformat(), user_id),
            )
            await self._db.commit()
        return until.isoformat()

    async def clear_awaiting_receipt(self, user_id: int) -> None:
        assert self._db is not None
        async with self._lock:
            await self._db.execute(
                "UPDATE users SET awaiting_receipt_until = NULL WHERE user_id = ?", (user_id,)
            )
            await self._db.commit()

    async def create_payment(
        self,
        user_id: int,
        file_id: str,
        file_type: str,
        caption: str | None,
    ) -> int:
        assert self._db is not None
        now = utcnow().isoformat()
        async with self._lock:
            cur = await self._db.execute(
                """
                INSERT INTO payments (user_id, file_id, file_type, caption, created_at, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
                """,
                (user_id, file_id, file_type, caption, now),
            )
            await self._db.commit()
            return int(cur.lastrowid)

    async def get_payment(self, payment_id: int) -> dict[str, Any] | None:
        assert self._db is not None
        async with self._db.execute(
            """
            SELECT p.*, u.full_name, u.username
            FROM payments p
            JOIN users u ON u.user_id = p.user_id
            WHERE p.id = ?
            """,
            (payment_id,),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def list_payments(self, limit: int = 200, status: str | None = None) -> list[dict[str, Any]]:
        assert self._db is not None
        if status:
            query = """
                SELECT p.*, u.full_name, u.username
                FROM payments p
                JOIN users u ON u.user_id = p.user_id
                WHERE p.status = ?
                ORDER BY p.created_at DESC
                LIMIT ?
            """
            params: tuple[Any, ...] = (status, limit)
        else:
            query = """
                SELECT p.*, u.full_name, u.username
                FROM payments p
                JOIN users u ON u.user_id = p.user_id
                ORDER BY p.created_at DESC
                LIMIT ?
            """
            params = (limit,)

        async with self._db.execute(query, params) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def list_user_payments(self, user_id: int, limit: int = 200) -> list[dict[str, Any]]:
        assert self._db is not None
        async with self._db.execute(
            """
            SELECT p.*, u.full_name, u.username
            FROM payments p
            JOIN users u ON u.user_id = p.user_id
            WHERE p.user_id = ?
            ORDER BY p.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def approve_payment(self, payment_id: int, reviewed_by: int, days: int = 30) -> dict[str, Any] | None:
        assert self._db is not None
        now = utcnow()
        now_iso = now.isoformat()

        async with self._lock:
            async with self._db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)) as cur:
                payment_row = await cur.fetchone()
            if not payment_row or payment_row["status"] != "pending":
                return None

            user_id = int(payment_row["user_id"])
            async with self._db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
                user_row = await cur.fetchone()
            if not user_row:
                return None

            current_end = user_row["subscription_end_at"]
            if current_end:
                try:
                    current_end_dt = datetime.fromisoformat(current_end)
                    base = current_end_dt if current_end_dt > now else now
                except ValueError:
                    base = now
            else:
                base = now

            new_end = base + timedelta(days=days)
            start_at = user_row["subscription_start_at"] or now_iso

            await self._db.execute(
                """
                UPDATE users
                SET subscription_status = 'subscribed',
                    subscription_start_at = ?,
                    subscription_end_at = ?,
                    awaiting_receipt_until = NULL
                WHERE user_id = ?
                """,
                (start_at, new_end.isoformat(), user_id),
            )
            await self._db.execute(
                """
                UPDATE payments
                SET status = 'approved', reviewed_at = ?, reviewed_by = ?
                WHERE id = ?
                """,
                (now_iso, reviewed_by, payment_id),
            )
            await self._db.commit()

        return await self.get_payment(payment_id)

    async def reject_payment(self, payment_id: int, reviewed_by: int, reason: str | None) -> dict[str, Any] | None:
        assert self._db is not None
        now = utcnow().isoformat()

        async with self._lock:
            async with self._db.execute("SELECT * FROM payments WHERE id = ?", (payment_id,)) as cur:
                payment_row = await cur.fetchone()
            if not payment_row or payment_row["status"] != "pending":
                return None

            await self._db.execute(
                """
                UPDATE payments
                SET status = 'rejected', reviewed_at = ?, reviewed_by = ?, reject_reason = ?
                WHERE id = ?
                """,
                (now, reviewed_by, reason, payment_id),
            )
            await self._db.commit()

        return await self.get_payment(payment_id)

    async def log_dialog(self, user_id: int, direction: str, message_text: str) -> None:
        assert self._db is not None
        now = utcnow().isoformat()
        cleaned = message_text.strip() or "-"
        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO dialog_messages (user_id, direction, message_text, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, direction, cleaned[:4000], now),
            )
            await self._db.commit()

    async def get_dialog(self, user_id: int, limit: int = 200) -> list[dict[str, Any]]:
        assert self._db is not None
        async with self._db.execute(
            """
            SELECT id, user_id, direction, message_text, created_at
            FROM dialog_messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(row) for row in rows]

    async def stats(self) -> dict[str, int]:
        assert self._db is not None

        async def count(query: str) -> int:
            async with self._db.execute(query) as cur:
                row = await cur.fetchone()
            return int(row[0])

        return {
            "users": await count("SELECT COUNT(*) FROM users"),
            "payments": await count("SELECT COUNT(*) FROM payments"),
            "pending_payments": await count("SELECT COUNT(*) FROM payments WHERE status = 'pending'"),
            "active_subscriptions": await count(
                "SELECT COUNT(*) FROM users WHERE subscription_status = 'subscribed'"
            ),
        }
