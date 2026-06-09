"""
Integration-style tests for GoogleSheetsClient using a fully mocked gspread.
No real network calls are made.
"""
import pytest
from unittest.mock import MagicMock, patch
from src.services.google_sheets import GoogleSheetsClient, _map_columns


def _mock_worksheet(values: list[list[str]]):
    ws = MagicMock()
    ws.get_all_values.return_value = values
    return ws


def _mock_spreadsheet(worksheet):
    sp = MagicMock()
    sp.get_worksheet.return_value = worksheet
    return sp


def _make_client_with_data(values: list[list[str]]) -> GoogleSheetsClient:
    client = GoogleSheetsClient("fake_credentials.json")
    mock_gc = MagicMock()
    mock_gc.open_by_key.return_value = _mock_spreadsheet(_mock_worksheet(values))
    client._client = mock_gc
    return client


# ------------------------------------------------------------------ tests

def test_fetch_rows_standard_headers():
    values = [
        ["Раздел", "Вопрос / тема", "Ответ / информация"],
        ["FAQ", "Что такое арабика?", "Сорт кофе с мягким вкусом."],
        ["Прайс", "Цена 200г?", "350 рублей."],
    ]
    client = _make_client_with_data(values)
    rows = client.fetch_rows("fake_id")

    assert len(rows) == 2
    assert rows[0].section == "FAQ"
    assert rows[0].question == "Что такое арабика?"
    assert rows[0].answer == "Сорт кофе с мягким вкусом."
    assert rows[1].section == "Прайс"


def test_fetch_rows_skips_empty_answer():
    values = [
        ["Раздел", "Вопрос / тема", "Ответ / информация"],
        ["FAQ", "Пустой вопрос", ""],       # no answer → skip
        ["FAQ", "С ответом", "Ответ есть"],
    ]
    client = _make_client_with_data(values)
    rows = client.fetch_rows("fake_id")
    assert len(rows) == 1
    assert rows[0].question == "С ответом"


def test_fetch_rows_empty_sheet():
    client = _make_client_with_data([])
    rows = client.fetch_rows("fake_id")
    assert rows == []


def test_fetch_rows_only_header():
    client = _make_client_with_data([["Раздел", "Вопрос / тема", "Ответ"]])
    rows = client.fetch_rows("fake_id")
    assert rows == []


def test_fetch_rows_fallback_column_order():
    """When column headers are unrecognised, fallback to 0/1/2."""
    values = [
        ["ColA", "ColB", "ColC"],          # unknown headers
        ["S1", "Q1", "A1"],
    ]
    client = _make_client_with_data(values)
    rows = client.fetch_rows("fake_id")
    assert len(rows) == 1
    assert rows[0].section == "S1"
    assert rows[0].answer == "A1"


def test_fetch_rows_strips_whitespace():
    values = [
        ["  Раздел  ", "  Вопрос / тема  ", "  Ответ  "],
        ["  FAQ  ", "  Вопрос  ", "  Ответ с пробелами  "],
    ]
    client = _make_client_with_data(values)
    rows = client.fetch_rows("fake_id")
    assert rows[0].section == "FAQ"
    assert rows[0].answer == "Ответ с пробелами"


def test_fetch_rows_english_headers():
    values = [
        ["Section", "Question", "Answer"],
        ["Coffee", "What is espresso?", "A strong concentrated coffee."],
    ]
    client = _make_client_with_data(values)
    rows = client.fetch_rows("fake_id")
    assert len(rows) == 1
    assert rows[0].answer == "A strong concentrated coffee."


def test_fetch_rows_office_file_fallback():
    """When gspread fails with Office file error, fall back to Drive + openpyxl."""
    from unittest.mock import patch
    from gspread.exceptions import APIError
    from src.services.google_sheets import SheetRow

    client = GoogleSheetsClient("fake_credentials.json")

    office_error = APIError(
        response=type(
            "R",
            (),
            {
                "json": lambda self: {
                    "error": {
                        "code": 400,
                        "message": "This operation is not supported for this document. "
                        "The document must not be an Office file.",
                        "status": "FAILED_PRECONDITION",
                    }
                },
                "text": "Office file",
            },
        )()
    )

    fallback_rows = [
        SheetRow(section="FAQ", question="Q", answer="A"),
    ]

    with patch.object(client, "_fetch_from_native_sheet", side_effect=office_error):
        with patch.object(client, "_fetch_from_office_file", return_value=fallback_rows):
            rows = client.fetch_rows("fake_office_id")

    assert len(rows) == 1
    assert rows[0].answer == "A"
