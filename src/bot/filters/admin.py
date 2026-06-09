from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery

from ...db.repository import Repository


class IsAdminFilter(BaseFilter):
    """Passes only for users with is_admin=True in the whitelist."""

    async def __call__(
        self,
        event: Message | CallbackQuery,
        is_admin: bool = False,
        repo: Repository | None = None,
        **kwargs,
    ) -> bool:
        if is_admin:
            return True
        user_id = event.from_user.id if event.from_user else None
        if repo and user_id:
            return await repo.is_admin(user_id)
        return False
