from unittest.mock import AsyncMock, MagicMock

import pytest

from src.bot.commands import (
    ADMIN_COMMANDS,
    USER_COMMANDS,
    setup_commands_for_user,
    setup_default_commands,
    sync_bot_commands,
)
from src.db.repository import Repository


async def test_user_commands_count():
    assert len(USER_COMMANDS) == 4
    names = {c.command for c in USER_COMMANDS}
    assert names == {"start", "help", "whoami", "status"}


async def test_admin_commands_include_extra():
    assert len(ADMIN_COMMANDS) == 7
    names = {c.command for c in ADMIN_COMMANDS}
    assert {"reload", "config", "logs"}.issubset(names)


async def test_setup_default_commands():
    bot = AsyncMock()
    await setup_default_commands(bot)
    bot.set_my_commands.assert_called_once()
    commands, = bot.set_my_commands.call_args.args
    assert len(commands) == 4


async def test_setup_commands_for_admin():
    bot = AsyncMock()
    await setup_commands_for_user(bot, 12345, is_admin=True)
    bot.set_my_commands.assert_called_once()
    commands, = bot.set_my_commands.call_args.args
    assert len(commands) == 7


async def test_setup_commands_for_user_ignores_chat_not_found():
    from aiogram.exceptions import TelegramBadRequest

    bot = AsyncMock()
    bot.set_my_commands = AsyncMock(
        side_effect=TelegramBadRequest(
            method=MagicMock(),
            message="Bad Request: chat not found",
        )
    )
    await setup_commands_for_user(bot, 99999, is_admin=False)
    bot.set_my_commands.assert_awaited_once()


async def test_sync_bot_commands_sets_admins(repo):
    await repo.add_user(90001, is_admin=True, name="Admin")
    await repo.add_user(90002, is_admin=False, name="User")

    bot = AsyncMock()
    await sync_bot_commands(bot, repo)

    assert bot.set_my_commands.await_count == 2  # default + 1 admin
