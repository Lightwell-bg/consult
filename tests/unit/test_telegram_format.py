from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from src.services.telegram_format import markdown_to_telegram_html, safe_edit_text


def test_header_becomes_bold():
    result = markdown_to_telegram_html("## 💬 Когда клиент говорит «дорого»")
    assert "<b>" in result
    assert "💬" in result
    assert "дорого" in result
    assert "##" not in result


def test_bold_inline():
    result = markdown_to_telegram_html("**Главный приём** — переключить разговор")
    assert "<b>Главный приём</b>" in result
    assert "**" not in result


def test_list_items_with_bullet():
    text = "- Разница за чашку — минимальна\n- При сопоставимом качестве мы дешевле"
    result = markdown_to_telegram_html(text)
    assert result.count("▫️") == 2
    assert "минимальна" in result


def test_blockquote():
    result = markdown_to_telegram_html('> «Давайте посчитаем не за кг, а за чашку»')
    assert "<blockquote>" in result
    assert "чашку" in result


def test_separator():
    result = markdown_to_telegram_html("---")
    assert "─" in result
    assert "---" not in result


def test_escapes_html_special_chars():
    result = markdown_to_telegram_html("Цена < 1000 & > 500")
    assert "&lt;" in result
    assert "&amp;" in result


@pytest.mark.asyncio
async def test_safe_edit_text_ignores_not_modified():
    msg = MagicMock()
    msg.edit_text = AsyncMock(
        side_effect=TelegramBadRequest(
            method=MagicMock(),
            message="Bad Request: message is not modified",
        )
    )
    await safe_edit_text(msg, "same text")
    msg.edit_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_safe_edit_text_reraises_other_bad_request():
    msg = MagicMock()
    msg.edit_text = AsyncMock(
        side_effect=TelegramBadRequest(
            method=MagicMock(),
            message="Bad Request: can't parse entities",
        )
    )
    with pytest.raises(TelegramBadRequest):
        await safe_edit_text(msg, "text", parse_mode="Markdown")


def test_full_example_structure():
    text = """## 💬 Когда клиент говорит «дорого»

**Главный приём** — переключить разговор.

**Логика аргумента:**
- Разница за чашку — минимальна
- В цену входит доставка

> «Давайте посчитаем за чашку»

---

📌 **Что ещё может помочь:**
- Нет денег → отсрочка"""
    result = markdown_to_telegram_html(text)
    assert "<b>" in result
    assert "▫️" in result
    assert "<blockquote>" in result
    assert "─" in result
    assert "##" not in result
    assert "**" not in result
