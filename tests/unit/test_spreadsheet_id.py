from src.bot.handlers.admin import _extract_spreadsheet_id


def test_extract_plain_id():
    assert _extract_spreadsheet_id("15wtvU9GVkfNaCC3tMmAjJBqfmxtXQu7S") == (
        "15wtvU9GVkfNaCC3tMmAjJBqfmxtXQu7S"
    )


def test_extract_from_sheets_url():
    url = "https://docs.google.com/spreadsheets/d/abc123XYZ/edit#gid=0"
    assert _extract_spreadsheet_id(url) == "abc123XYZ"


def test_reject_command_like_text():
    assert _extract_spreadsheet_id("/start") is None
    assert _extract_spreadsheet_id("/cancel") is None
