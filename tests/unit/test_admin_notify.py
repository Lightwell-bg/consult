from unittest.mock import AsyncMock, MagicMock

import pytest

from src.db.models import User
from src.services.admin_notify import format_kb_miss_alert, notify_admins_kb_miss


def test_format_kb_miss_alert_contains_question():
    text = format_kb_miss_alert(
        "Сколько стоит робуста?",
        111222,
        db_name="Иван Петров",
    )
    assert "Ответ в базе знаний не найден" in text
    assert "Сколько стоит робуста?" in text
    assert "Иван Петров" in text
    assert "111222" in text


def test_format_kb_miss_alert_truncates_long_question():
    long_q = "а" * 5000
    text = format_kb_miss_alert(long_q, 1)
    assert len(text) <= 4096
    assert "…" in text


@pytest.mark.asyncio
async def test_notify_admins_kb_miss_sends_to_all_admins():
    bot = AsyncMock()
    bot.send_message = AsyncMock()

    repo = AsyncMock()
    repo.list_users = AsyncMock(
        return_value=[
            User(telegram_id=100, is_admin=True, name="Admin1", created_at=MagicMock()),
            User(telegram_id=200, is_admin=True, name="Admin2", created_at=MagicMock()),
            User(telegram_id=300, is_admin=False, name="User", created_at=MagicMock()),
        ]
    )
    repo.get_user = AsyncMock(
        return_value=User(telegram_id=300, is_admin=False, name="Сотрудник", created_at=MagicMock())
    )

    sent = await notify_admins_kb_miss(
        bot,
        repo,
        question="Неизвестный вопрос",
        asker_id=300,
    )

    assert sent == 2
    assert bot.send_message.await_count == 2
    notified_ids = {call.args[0] for call in bot.send_message.call_args_list}
    assert notified_ids == {100, 200}
    body = bot.send_message.call_args_list[0].args[1]
    assert "Неизвестный вопрос" in body
    assert "Сотрудник" in body


@pytest.mark.asyncio
async def test_notify_admins_kb_miss_no_admins():
    bot = AsyncMock()
    repo = AsyncMock()
    repo.list_users = AsyncMock(return_value=[])

    sent = await notify_admins_kb_miss(
        bot, repo, question="Q", asker_id=1
    )

    assert sent == 0
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notify_admins_kb_miss_includes_asker_when_admin():
    bot = AsyncMock()
    bot.send_message = AsyncMock()

    repo = AsyncMock()
    repo.list_users = AsyncMock(
        return_value=[
            User(telegram_id=100, is_admin=True, name="Solo Admin", created_at=MagicMock()),
        ]
    )
    repo.get_user = AsyncMock(
        return_value=User(telegram_id=100, is_admin=True, name="Solo Admin", created_at=MagicMock())
    )

    sent = await notify_admins_kb_miss(
        bot, repo, question="Тестовый вопрос", asker_id=100
    )

    assert sent == 1
    bot.send_message.assert_awaited_once()
    assert bot.send_message.call_args.args[0] == 100
    assert "Тестовый вопрос" in bot.send_message.call_args.args[1]
