import pytest
from src.db.database import init_db
from src.db.repository import Repository


# ------------------------------------------------------------------ users

async def test_add_and_get_user(repo):
    user = await repo.add_user(111111, name="Тест")
    assert user.telegram_id == 111111
    assert user.is_admin is False
    assert user.name == "Тест"

    fetched = await repo.get_user(111111)
    assert fetched is not None
    assert fetched.telegram_id == 111111


async def test_add_admin(repo):
    user = await repo.add_user(222222, is_admin=True)
    assert user.is_admin is True


async def test_get_nonexistent_user_returns_none(repo):
    user = await repo.get_user(999999)
    assert user is None


async def test_is_user_allowed(repo):
    assert await repo.is_user_allowed(333333) is False
    await repo.add_user(333333)
    assert await repo.is_user_allowed(333333) is True


async def test_is_admin(repo):
    await repo.add_user(444444, is_admin=False)
    assert await repo.is_admin(444444) is False
    assert await repo.is_admin(999998) is False

    await repo.add_user(555555, is_admin=True)
    assert await repo.is_admin(555555) is True


async def test_promote_to_admin(repo):
    await repo.add_user(666666, is_admin=False)
    assert await repo.is_admin(666666) is False
    await repo.set_admin(666666, True)
    assert await repo.is_admin(666666) is True


async def test_remove_user(repo):
    await repo.add_user(777777)
    removed = await repo.remove_user(777777)
    assert removed is True
    assert await repo.get_user(777777) is None

    removed_again = await repo.remove_user(777777)
    assert removed_again is False


async def test_list_users(repo):
    await repo.add_user(10001)
    await repo.add_user(10002, is_admin=True)
    users = await repo.list_users()
    ids = [u.telegram_id for u in users]
    assert 10001 in ids
    assert 10002 in ids


async def test_set_name(repo):
    await repo.add_user(30001)
    assert await repo.set_name(30001, "Анна Смирнова")
    user = await repo.get_user(30001)
    assert user is not None
    assert user.name == "Анна Смирнова"


async def test_count_admins(repo):
    assert await repo.count_admins() == 0
    await repo.add_user(20001, is_admin=True)
    await repo.add_user(20002)
    assert await repo.count_admins() == 1
    await repo.add_user(20003, is_admin=True)
    assert await repo.count_admins() == 2


# --------------------------------------------------------------- settings

async def test_default_settings_exist(repo):
    spreadsheet_id = await repo.get_setting("spreadsheet_id")
    assert spreadsheet_id == "15wtvU9GVkfNaCC3tMmAjJBqfmxtXQu7S"

    sync_mode = await repo.get_setting("sync_mode")
    assert sync_mode == "scheduled"


async def test_set_and_get_setting(repo):
    await repo.set_setting("spreadsheet_id", "new_sheet_id")
    assert await repo.get_setting("spreadsheet_id") == "new_sheet_id"


async def test_get_missing_setting_returns_default(repo):
    value = await repo.get_setting("nonexistent_key", default="fallback")
    assert value == "fallback"


async def test_get_all_settings(repo):
    settings = await repo.get_all_settings()
    assert "spreadsheet_id" in settings
    assert "sync_mode" in settings
    assert "max_context_messages" in settings


# --------------------------------------------------------------- messages

async def test_add_and_get_messages(repo):
    await repo.add_message(100, "user", "Привет")
    await repo.add_message(100, "assistant", "Здравствуйте!")

    msgs = await repo.get_recent_messages(100, limit=10)
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[0].content == "Привет"
    assert msgs[1].role == "assistant"


async def test_messages_are_user_scoped(repo):
    await repo.add_message(201, "user", "Вопрос от 201")
    await repo.add_message(202, "user", "Вопрос от 202")

    msgs_201 = await repo.get_recent_messages(201, limit=10)
    msgs_202 = await repo.get_recent_messages(202, limit=10)

    assert len(msgs_201) == 1
    assert len(msgs_202) == 1
    assert msgs_201[0].content == "Вопрос от 201"


async def test_get_recent_messages_respects_limit(repo):
    for i in range(10):
        await repo.add_message(300, "user", f"msg {i}")

    msgs = await repo.get_recent_messages(300, limit=5)
    assert len(msgs) == 5
    # Should be the 5 most recent in chronological order
    assert msgs[-1].content == "msg 9"


async def test_trim_messages(repo):
    for i in range(10):
        await repo.add_message(400, "user", f"msg {i}")

    await repo.trim_messages(400, keep=4)
    remaining = await repo.get_recent_messages(400, limit=20)
    assert len(remaining) == 4
    # Kept the most recent ones
    assert remaining[-1].content == "msg 9"


async def test_clear_user_messages(repo):
    await repo.add_message(500, "user", "test")
    await repo.clear_user_messages(500)
    msgs = await repo.get_recent_messages(500, limit=10)
    assert msgs == []
