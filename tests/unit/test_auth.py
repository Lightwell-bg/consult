"""
Tests for the auth logic that the AuthMiddleware relies on.
We test the repository layer directly; middleware integration is covered
in tests/integration/test_handlers.py.
"""
import pytest
from src.db.repository import Repository


async def test_unknown_user_not_allowed(repo):
    assert await repo.is_user_allowed(99999) is False


async def test_known_user_is_allowed(repo):
    await repo.add_user(10101)
    assert await repo.is_user_allowed(10101) is True


async def test_regular_user_not_admin(repo):
    await repo.add_user(20202, is_admin=False)
    assert await repo.is_admin(20202) is False


async def test_admin_user_is_admin(repo):
    await repo.add_user(30303, is_admin=True)
    assert await repo.is_admin(30303) is True


async def test_nonexistent_user_not_admin(repo):
    assert await repo.is_admin(99998) is False


async def test_remove_user_blocks_access(repo):
    await repo.add_user(40404)
    assert await repo.is_user_allowed(40404) is True

    await repo.remove_user(40404)
    assert await repo.is_user_allowed(40404) is False


async def test_duplicate_add_is_idempotent(repo):
    await repo.add_user(50505)
    await repo.add_user(50505)  # should not raise
    users = await repo.list_users()
    count = sum(1 for u in users if u.telegram_id == 50505)
    assert count == 1
