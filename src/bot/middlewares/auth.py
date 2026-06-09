import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from ...db.repository import Repository

logger = logging.getLogger(__name__)

_ACCESS_DENIED = (
    "У вас нет доступа к этому внутреннему боту. "
    "Обратитесь к администратору."
)


class AuthMiddleware(BaseMiddleware):
    """
    Whitelist middleware.

    - Blocks unknown users (not in the users table).
    - Injects is_admin=True/False into handler data for authorised users.
    - /whoami is exempt so anyone can look up their Telegram ID.
    """

    def __init__(self, repo: Repository) -> None:
        self.repo = repo

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            # /whoami bypasses auth so users can find their ID
            text = (event.text or "").strip().lower()
            if text.startswith("/whoami"):
                return await handler(event, data)

            user_id = event.from_user.id if event.from_user else None
            if user_id is None:
                return None

            user = await self.repo.get_user(user_id)
            if user is None:
                logger.info("Blocked unknown user %s.", user_id)
                await event.answer(_ACCESS_DENIED)
                return None

            data["is_admin"] = user.is_admin

        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            if user_id is None:
                return None

            user = await self.repo.get_user(user_id)
            if user is None:
                await event.answer(_ACCESS_DENIED, show_alert=True)
                return None

            data["is_admin"] = user.is_admin

        return await handler(event, data)
