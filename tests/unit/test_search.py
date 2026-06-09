import pytest
from src.services.google_sheets import SheetRow
from src.services.search import search, SearchResult, _tokenize


# ------------------------------------------------------------------ helpers

def make_kb() -> list[SheetRow]:
    return [
        SheetRow(
            section="15. Классификация кофе",
            question="Какие виды кофе бывают?",
            answer="Арабика и робуста. Арабика — мягкий вкус, робуста — крепкая с горчинкой.",
        ),
        SheetRow(
            section="23. Возражения и экономика",
            question="Что отвечать клиенту, если он говорит «дорого»?",
            answer="Сравните с ценой порции в кофейне. Наш пакет — 30 чашек по цене одной чашки в заведении.",
        ),
        SheetRow(
            section="19. Оборудование",
            question="Какое оборудование нужно для эспрессо?",
            answer="Эспрессо-машина с давлением 9 бар и кофемолка с жерновами.",
        ),
        SheetRow(
            section="21. Подбор продукта под клиента",
            question="Какой кофе подойдет для офиса?",
            answer="Для офиса рекомендуем купаж средней обжарки, удобный в любом способе приготовления.",
        ),
        SheetRow(
            section="Контакты",
            question="Кто отвечает за поставки?",
            answer="Иван Петров, отдел логистики, ivan@company.ru",
        ),
    ]


# ------------------------------------------------------------------ tests

def test_tokenize_russian():
    tokens = _tokenize("Какой кофе подходит для офиса")
    assert "кофе" in tokens
    assert "офиса" in tokens
    # stop words removed
    assert "для" not in tokens


def test_relevant_query_returns_results():
    kb = make_kb()
    results = search("дорого клиент", kb)
    assert len(results) > 0
    top = results[0]
    assert "дорого" in top.entry.question.lower() or "возражения" in top.entry.section.lower()


def test_coffee_types_query():
    kb = make_kb()
    results = search("виды кофе арабика", kb)
    assert len(results) > 0
    assert results[0].entry.section == "15. Классификация кофе"


def test_equipment_query():
    kb = make_kb()
    results = search("оборудование эспрессо машина", kb)
    assert len(results) > 0
    assert "Оборудование" in results[0].entry.section


def test_irrelevant_query_returns_empty():
    kb = make_kb()
    # Completely unrelated query
    results = search("прогноз погоды завтра в москве", kb)
    assert results == []


def test_top_k_limit():
    kb = make_kb()
    results = search("кофе", kb, top_k=2)
    assert len(results) <= 2


def test_threshold_filters_low_scores():
    kb = make_kb()
    # High threshold should filter everything
    results = search("кофе", kb, threshold=999.0)
    assert results == []


def test_results_are_sorted_by_score():
    kb = make_kb()
    results = search("дорого клиент кофе", kb, top_k=5)
    if len(results) > 1:
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score


def test_empty_kb_returns_empty():
    results = search("любой вопрос", [])
    assert results == []


def test_empty_query_returns_empty():
    kb = make_kb()
    results = search("", kb)
    assert results == []


def test_contact_lookup():
    kb = make_kb()
    results = search("поставки кто отвечает контакт", kb)
    assert len(results) > 0
    assert any("Контакты" in r.entry.section for r in results)


def test_putin_question_exact_match():
    kb = make_kb() + [
        SheetRow(
            section="23. Возражения и экономика",
            question="Кто такой Путин?",
            answer="Это Пал Лаич. Захватил страну 26 лет назад.",
        ),
    ]
    results = search("Кто такой путин", kb)
    assert len(results) > 0
    assert results[0].entry.question == "Кто такой Путин?"
    assert results[0].score >= 10.0
