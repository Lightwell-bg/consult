from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message, User as TGUser

from src.bot.handlers.users import user_create, user_delete, user_demote, user_promote
from src.db.repository import Repository


def _callback(data: str, user_id: int = 999) -> MagicMock:
    cb = MagicMock(spec=CallbackQuery)
    cb.data = data
    cb.from_user = MagicMock(spec=TGUser)
    cb.from_user.id = user_id
    cb.message = MagicMock(spec=Message)
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    cb.bot = AsyncMock()
    cb.bot.set_my_commands = AsyncMock()
    cb.bot.delete_my_commands = AsyncMock()
    return cb


def _state_with(**data) -> MagicMock:
    state = MagicMock(spec=FSMContext)
    state.get_data = AsyncMock(return_value=data)
    state.clear = AsyncMock()
    return state


async def test_user_create_adds_employee_with_name(repo):
    cb = _callback("usr:pick_role:0")
    state = _state_with(new_user_id=555001, new_user_name="Petr")
    await user_create(cb, state=state, repo=repo)

    user = await repo.get_user(555001)
    assert user is not None
    assert user.is_admin is False
    assert user.name == "Petr"
    cb.message.edit_text.assert_called_once()


async def test_user_create_adds_admin_with_name(repo):
    cb = _callback("usr:pick_role:1")
    state = _state_with(new_user_id=555002, new_user_name="Admin")
    await user_create(cb, state=state, repo=repo)

    user = await repo.get_user(555002)
    assert user is not None
    assert user.is_admin is True
    assert user.name == "Admin"


async def test_user_promote_and_demote(repo):
    await repo.add_user(555003, is_admin=False, name="Сотрудник")
    await repo.add_user(555099, is_admin=True, name="Главный")
    cb = _callback("usr:promote:555003", user_id=555099)

    await user_promote(cb, repo=repo)
    assert (await repo.get_user(555003)).is_admin is True

    await user_demote(cb, repo=repo)
    assert (await repo.get_user(555003)).is_admin is False


async def test_cannot_demote_last_admin(repo):
    await repo.add_user(555004, is_admin=True, name="Один")
    cb = _callback("usr:demote:555004", user_id=555004)

    await user_demote(cb, repo=repo)
    assert (await repo.get_user(555004)).is_admin is True
    cb.answer.assert_called()
    assert "последнего" in cb.answer.call_args[0][0].lower()


async def test_cannot_delete_self(repo):
    await repo.add_user(555005, is_admin=True, name="Я")
    await repo.add_user(555006, name="Другой")
    cb = _callback("usr:del:555005", user_id=555005)

    await user_delete(cb, repo=repo)
    assert await repo.get_user(555005) is not None
    cb.answer.assert_called()
    assert "себя" in cb.answer.call_args[0][0].lower()


async def test_delete_user(repo):
    await repo.add_user(555007, name="Удаляемый")
    await repo.add_user(555008, is_admin=True, name="Админ")
    cb = _callback("usr:del:555007", user_id=555008)

    await user_delete(cb, repo=repo)
    assert await repo.get_user(555007) is None
