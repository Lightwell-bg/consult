import pytest
from unittest.mock import MagicMock
from src.services.google_sheets import SheetRow, GoogleSheetsClient, _map_columns
from src.services.knowledge_base import KnowledgeBase


# ---------------------------------------------------------- column mapping

def test_map_columns_russian_headers():
    headers = ["Раздел", "Вопрос / тема", "Ответ / информация"]
    mapping = _map_columns(headers)
    assert mapping["section"] == 0
    assert mapping["question"] == 1
    assert mapping["answer"] == 2


def test_map_columns_english_headers():
    headers = ["Section", "Question", "Answer"]
    mapping = _map_columns(headers)
    assert mapping["section"] == 0
    assert mapping["question"] == 1
    assert mapping["answer"] == 2


def test_map_columns_mixed_case():
    headers = ["  РАЗДЕЛ  ", "  вопрос  ", "  ОТВЕТ  "]
    mapping = _map_columns(headers)
    assert "section" in mapping
    assert "question" in mapping
    assert "answer" in mapping


def test_map_columns_partial_match():
    # Only 2 known columns
    headers = ["Раздел", "Описание", "Ответ"]
    mapping = _map_columns(headers)
    assert "section" in mapping
    assert "answer" in mapping


# ---------------------------------------------------------- KnowledgeBase

def _make_mock_sheets_client(rows: list[SheetRow]) -> GoogleSheetsClient:
    client = MagicMock(spec=GoogleSheetsClient)
    client.fetch_rows.return_value = rows
    return client


async def test_sync_loads_entries():
    rows = [
        SheetRow(section="FAQ", question="Что такое кофе?", answer="Напиток"),
        SheetRow(section="Прайс", question="Цена?", answer="100 руб."),
    ]
    client = _make_mock_sheets_client(rows)
    kb = KnowledgeBase(client)

    assert kb.is_loaded() is False
    count = await kb.sync("fake_sheet_id")

    assert count == 2
    assert kb.is_loaded() is True
    assert kb.entry_count == 2
    assert kb.last_sync is not None
    client.fetch_rows.assert_called_once_with("fake_sheet_id")


async def test_sync_replaces_cache():
    initial = [SheetRow(section="A", question="Q1", answer="A1")]
    updated = [
        SheetRow(section="A", question="Q1", answer="A1 updated"),
        SheetRow(section="B", question="Q2", answer="A2"),
    ]
    client = _make_mock_sheets_client(initial)
    kb = KnowledgeBase(client)

    await kb.sync("sheet")
    assert kb.entry_count == 1

    client.fetch_rows.return_value = updated
    await kb.sync("sheet")
    assert kb.entry_count == 2
    assert kb.entries[0].answer == "A1 updated"


async def test_sync_empty_sheet():
    client = _make_mock_sheets_client([])
    kb = KnowledgeBase(client)
    count = await kb.sync("sheet")
    assert count == 0
    assert kb.is_loaded() is False


def test_load_from_rows():
    rows = [SheetRow(section="S", question="Q", answer="A")]
    client = MagicMock(spec=GoogleSheetsClient)
    kb = KnowledgeBase(client)
    kb.load_from_rows(rows)
    assert kb.is_loaded() is True
    assert kb.entry_count == 1
    client.fetch_rows.assert_not_called()


async def test_sync_error_propagates():
    client = MagicMock(spec=GoogleSheetsClient)
    client.fetch_rows.side_effect = Exception("API error")
    kb = KnowledgeBase(client)

    with pytest.raises(Exception, match="API error"):
        await kb.sync("sheet")

    # Cache stays empty on error
    assert kb.is_loaded() is False
