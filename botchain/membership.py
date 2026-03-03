from __future__ import annotations

from typing import Sequence

from telegram import Bot


async def ban_user_from_chats(
    bot: Bot,
    chat_ids: Sequence[int],
    user_id: int,
) -> tuple[list[int], dict[int, str]]:
    removed: list[int] = []
    failed: dict[int, str] = {}
    for chat_id in chat_ids:
        try:
            await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            removed.append(int(chat_id))
        except Exception as exc:
            failed[int(chat_id)] = str(exc)
    return removed, failed


async def unban_user_in_chats(
    bot: Bot,
    chat_ids: Sequence[int],
    user_id: int,
) -> tuple[list[int], dict[int, str]]:
    unbanned: list[int] = []
    failed: dict[int, str] = {}
    for chat_id in chat_ids:
        try:
            await bot.unban_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                only_if_banned=True,
            )
            unbanned.append(int(chat_id))
        except Exception as exc:
            failed[int(chat_id)] = str(exc)
    return unbanned, failed
