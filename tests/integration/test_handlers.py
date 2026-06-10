"""
Integration tests for bot handler logic.
We test the handler functions directly with mock Message/CallbackQuery objects,
avoiding the need for a running aiogram Dispatcher.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiogram.types import Message, User as TGUser, Chat


def _make_message(
    text: str = "test",
    user_id: int = 12345,
    chat_id: int = 12345,
) -> MagicMock:
    msg = MagicMock(spec=Message)
    msg.text = text
    msg.from_user = MagicMock(spec=TGUser)
    msg.from_user.id = user_id
    msg.chat = MagicMock(spec=Chat)
    msg.chat.id = chat_id
    msg.answer = AsyncMock()
    msg.bot = AsyncMock()
    msg.bot.send_chat_action = AsyncMock()
    return msg


# ------------------------------------------------------------------ /whoami

async def test_whoami_returns_user_id():
    from src.bot.handlers.common import cmd_whoami

    msg = _make_message(user_id=987654321)
    await cmd_whoami(msg)

    msg.answer.assert_called_once()
    response_text = msg.answer.call_args[0][0]
    assert "987654321" in response_text


# ------------------------------------------------------------------ /start

async def test_start_sends_greeting():
    from unittest.mock import AsyncMock
    from src.bot.handlers.common import cmd_start

    msg = _make_message()
    repo = AsyncMock()
    repo.get_user = AsyncMock(return_value=None)
    await cmd_start(msg, repo=repo)

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "консультант" in text.lower() or "продаж" in text.lower()


# ------------------------------------------------------------------ /help

async def test_help_mentions_commands():
    from src.bot.handlers.common import cmd_help

    msg = _make_message()
    await cmd_help(msg)

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "/start" in text
    assert "/status" in text


# ------------------------------------------------------------------ /status

async def test_status_shows_kb_state():
    from src.bot.handlers.common import cmd_status
    from src.services.knowledge_base import KnowledgeBase
    from unittest.mock import MagicMock

    msg = _make_message()

    kb = MagicMock(spec=KnowledgeBase)
    kb.is_loaded.return_value = True
    kb.entry_count = 42
    kb.last_sync = None

    repo = AsyncMock()
    repo.get_setting = AsyncMock(side_effect=lambda key, default="": {
        "sync_mode": "scheduled",
        "spreadsheet_id": "test_id",
        "sync_interval_minutes": "10",
    }.get(key, default))

    await cmd_status(msg, kb=kb, repo=repo)

    msg.answer.assert_called_once()
    text = msg.answer.call_args[0][0]
    assert "42" in text
    assert "test_id" in text


# ------------------------------------------------------------------ chat

async def test_chat_calls_ai_and_replies():
    from unittest.mock import patch
    from src.bot.handlers.chat import handle_chat
    from src.services.google_sheets import SheetRow
    from src.services.knowledge_base import KnowledgeBase
    from src.services.anthropic_client import AnthropicClient

    msg = _make_message(text="Расскажи про арабику")

    kb = MagicMock(spec=KnowledgeBase)
    kb.is_loaded.return_value = True
    kb.entries = [
        SheetRow("FAQ", "Расскажи про арабику", "Арабика — мягкий сорт кофе."),
    ]

    repo = AsyncMock()
    repo.get_setting = AsyncMock(return_value="8")
    repo.get_recent_messages = AsyncMock(return_value=[])
    repo.add_message = AsyncMock()
    repo.trim_messages = AsyncMock()

    ai_client = AsyncMock(spec=AnthropicClient)
    ai_client.ask = AsyncMock(return_value="## ☕ Арабика\n\n**Мягкий** сорт кофе.")

    with patch("src.bot.handlers.chat.send_formatted", new_callable=AsyncMock) as mock_send:
        with patch(
            "src.bot.handlers.chat.notify_admins_kb_miss", new_callable=AsyncMock
        ) as mock_notify:
            await handle_chat(msg, repo=repo, kb=kb, ai_client=ai_client)

    mock_send.assert_called_once_with(msg, "## ☕ Арабика\n\n**Мягкий** сорт кофе.")
    ai_client.ask.assert_called_once()
    mock_notify.assert_not_awaited()


async def test_chat_uses_fallback_when_no_kb_results():
    from unittest.mock import patch
    from src.bot.handlers.chat import handle_chat
    from src.services.knowledge_base import KnowledgeBase
    from src.services.anthropic_client import AnthropicClient

    msg = _make_message(text="Что такое квантовый компьютер")

    kb = MagicMock(spec=KnowledgeBase)
    kb.is_loaded.return_value = True
    kb.entries = []  # Empty → search returns nothing → fallback

    repo = AsyncMock()
    repo.get_setting = AsyncMock(return_value="8")
    repo.get_recent_messages = AsyncMock(return_value=[])
    repo.add_message = AsyncMock()
    repo.trim_messages = AsyncMock()

    ai_client = AsyncMock(spec=AnthropicClient)
    ai_client.ask = AsyncMock(return_value="Нет данных в базе знаний.")

    with patch("src.bot.handlers.chat.send_formatted", new_callable=AsyncMock):
        with patch(
            "src.bot.handlers.chat.notify_admins_kb_miss", new_callable=AsyncMock
        ) as mock_notify:
            await handle_chat(msg, repo=repo, kb=kb, ai_client=ai_client)

    mock_notify.assert_awaited_once()
    # Verify fallback=True was passed
    call_kwargs = ai_client.ask.call_args[1]
    assert call_kwargs.get("use_fallback") is True


async def test_chat_handles_ai_error_gracefully():
    from unittest.mock import patch
    from src.bot.handlers.chat import handle_chat
    from src.services.knowledge_base import KnowledgeBase
    from src.services.anthropic_client import AnthropicClient

    msg = _make_message(text="Вопрос")

    kb = MagicMock(spec=KnowledgeBase)
    kb.is_loaded.return_value = True
    kb.entries = []

    repo = AsyncMock()
    repo.get_setting = AsyncMock(return_value="8")
    repo.get_recent_messages = AsyncMock(return_value=[])
    repo.add_message = AsyncMock()
    repo.trim_messages = AsyncMock()

    ai_client = AsyncMock(spec=AnthropicClient)
    ai_client.ask = AsyncMock(side_effect=Exception("Network error"))

    with patch("src.bot.handlers.chat.send_formatted", new_callable=AsyncMock) as mock_send:
        await handle_chat(msg, repo=repo, kb=kb, ai_client=ai_client)

    mock_send.assert_called_once()
    error_msg = mock_send.call_args[0][1]
    assert "ошибка" in error_msg.lower()


# ------------------------------------------------------------------ admin access

async def test_admin_no_access_message():
    from src.bot.handlers.common import cmd_admin_no_access

    msg = _make_message(text="/reload")
    await cmd_admin_no_access(msg)

    msg.answer.assert_called_once()
    assert "администратор" in msg.answer.call_args[0][0].lower()
