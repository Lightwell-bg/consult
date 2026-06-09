from src.services.telegram_format import markdown_to_telegram_html


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
