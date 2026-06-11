"""
Tests for AnthropicClient using a mocked anthropic.Anthropic.
Verifies that the correct structure is sent to the API.
"""
import pytest
from unittest.mock import MagicMock, patch
from src.services.anthropic_client import AnthropicClient, _build_kb_block
from src.services.google_sheets import SheetRow
from src.services.search import SearchResult


def _make_client(tmp_path=None) -> AnthropicClient:
    """Build AnthropicClient with mocked underlying anthropic.Anthropic."""
    with patch("src.services.anthropic_client.anthropic.Anthropic") as MockAnthropic:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Тестовый ответ от Claude")]
        mock_api = MagicMock()
        mock_api.messages.create.return_value = mock_response
        MockAnthropic.return_value = mock_api

        client = AnthropicClient("fake-key", "claude-test")
        client._mock_api = mock_api  # keep reference for assertions
    return client


def _result(section: str, question: str, answer: str, score: float = 1.0) -> SearchResult:
    return SearchResult(
        entry=SheetRow(section=section, question=question, answer=answer),
        score=score,
    )


# ---------------------------------------------------------- _build_kb_block

def test_build_kb_block_empty():
    assert _build_kb_block([]) == ""


def test_build_kb_block_includes_section_and_answer():
    results = [_result("FAQ", "Что такое арабика?", "Мягкий сорт кофе.")]
    block = _build_kb_block(results)
    assert "FAQ" in block
    assert "Мягкий сорт кофе." in block


def test_build_kb_block_multiple_entries():
    results = [
        _result("FAQ", "Вопрос 1", "Ответ 1"),
        _result("Прайс", "Цена", "100 руб."),
    ]
    block = _build_kb_block(results)
    assert "Ответ 1" in block
    assert "100 руб." in block


# ---------------------------------------------------------- ask()

async def test_ask_returns_text():
    client = _make_client()
    with patch.object(client, "_client", client._mock_api):
        result = await client.ask("Тестовый вопрос", [], [])
    assert result == "Тестовый ответ от Claude"


async def test_ask_includes_kb_context_in_user_message():
    client = _make_client()
    results = [_result("Раздел", "Вопрос из БЗ", "Ответ из БЗ")]

    with patch.object(client, "_client", client._mock_api):
        await client.ask("Мой вопрос", results, [])

    call_kwargs = client._mock_api.messages.create.call_args[1]
    user_msg = call_kwargs["messages"][-1]["content"]
    assert "Ответ из БЗ" in user_msg
    assert "Мой вопрос" in user_msg


async def test_ask_includes_history():
    client = _make_client()
    history = [
        {"role": "user", "content": "Предыдущий вопрос"},
        {"role": "assistant", "content": "Предыдущий ответ"},
    ]

    with patch.object(client, "_client", client._mock_api):
        await client.ask("Новый вопрос", [], history)

    call_kwargs = client._mock_api.messages.create.call_args[1]
    messages = call_kwargs["messages"]
    # history (2) + current (1) = 3
    assert len(messages) == 3
    assert messages[0]["content"] == "Предыдущий вопрос"
    assert messages[-1]["content"] == "Новый вопрос"


async def test_ask_uses_fallback_system_prompt_when_flag_set():
    client = _make_client()
    client._fallback_prompt = "Fallback system prompt"
    client._system_prompt = "Normal system prompt"

    with patch.object(client, "_client", client._mock_api):
        await client.ask("Вопрос", [], [], use_fallback=True)

    call_kwargs = client._mock_api.messages.create.call_args[1]
    assert call_kwargs["system"] == "Fallback system prompt"


async def test_ask_uses_ai_assist_system_prompt():
    client = _make_client()
    client._ai_assist_prompt = "AI assist system prompt"

    with patch.object(client, "_client", client._mock_api):
        await client.ask("Вопрос", [], [], answer_mode="ai_assist")

    call_kwargs = client._mock_api.messages.create.call_args[1]
    assert call_kwargs["system"] == "AI assist system prompt"


async def test_ask_uses_normal_system_prompt_by_default():
    client = _make_client()
    client._system_prompt = "Normal system prompt"

    with patch.object(client, "_client", client._mock_api):
        await client.ask("Вопрос", [], [])

    call_kwargs = client._mock_api.messages.create.call_args[1]
    assert call_kwargs["system"] == "Normal system prompt"


async def test_ask_no_kb_data_passes_plain_question():
    client = _make_client()

    with patch.object(client, "_client", client._mock_api):
        await client.ask("Простой вопрос", [], [])

    call_kwargs = client._mock_api.messages.create.call_args[1]
    user_content = call_kwargs["messages"][-1]["content"]
    # Without KB results, message should just be the question
    assert user_content == "Простой вопрос"
