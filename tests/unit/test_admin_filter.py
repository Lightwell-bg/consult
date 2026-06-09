from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.types import Message, User

from src.bot.filters.admin import IsAdminFilter


def _message(user_id: int) -> Message:
    msg = MagicMock(spec=Message)
    msg.from_user = MagicMock(spec=User)
    msg.from_user.id = user_id
    return msg


async def test_admin_filter_passes_when_is_admin_in_data():
    filt = IsAdminFilter()
    assert await filt(_message(449466944), is_admin=True) is True


async def test_admin_filter_checks_repo_fallback():
    filt = IsAdminFilter()
    repo = AsyncMock()
    repo.is_admin = AsyncMock(return_value=True)

    assert await filt(_message(449466944), is_admin=False, repo=repo) is True
    repo.is_admin.assert_called_once_with(449466944)


async def test_admin_filter_rejects_non_admin():
    filt = IsAdminFilter()
    repo = AsyncMock()
    repo.is_admin = AsyncMock(return_value=False)

    assert await filt(_message(111), is_admin=False, repo=repo) is False
