import re
from dataclasses import dataclass

from .google_sheets import SheetRow

# Слишком общие для продаж — совпадение только по ним не считается релевантным вопросом.
_GENERIC_TOKENS = {
    "клиент", "клиенту", "клиента", "клиенты", "клиентов",
    "делать", "дела", "дело", "дел",
    "нужно", "можно", "быть", "есть", "будет", "было",
    "сказать", "ответить", "ответ", "говорит", "говорить", "сказал",
    "помочь", "помощь", "подскажите", "подскажи", "расскажи",
    "работа", "работе", "работу",
}

_STOP_WORDS = {
    "и", "в", "на", "с", "по", "к", "для", "от", "из", "что", "как",
    "это", "не", "но", "а", "или", "то", "же", "бы", "ли", "у", "о",
    "за", "при", "об", "до", "со", "без", "под", "над", "про", "через",
    "все", "так", "он", "она", "они", "мы", "вы", "я", "его", "её",
    "ее", "их", "есть", "был", "была", "были", "быть", "там", "тут",
    "здесь", "который", "которая", "которые", "которого",
    "кто", "такой", "такая", "такое", "такие", "таким", "такого",
    "если", "ли", "бы", "уже", "ещё", "еще", "вот", "ну",
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in",
}

_TOKEN_SUFFIXES = (
    "ения", "ение", "овать", "ить", "ать", "еть", "ишь", "ите",
    "ому", "ему", "ами", "ями", "ого", "его", "ной", "ную", "ных",
)


def _normalize_text(text: str) -> str:
    return re.sub(r"[^\wа-яё]+", " ", text.lower()).strip()


def _normalize_token(token: str) -> str:
    """Crude Russian stem for matching different word forms (клиенту ≈ клиент)."""
    t = token.lower()
    if len(t) <= 3:
        return t
    for suffix in _TOKEN_SUFFIXES:
        if t.endswith(suffix) and len(t) - len(suffix) >= 4:
            return t[: -len(suffix)]
    return t


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[а-яёa-z0-9]+", text.lower())) - _STOP_WORDS


def _tokens_match(query_token: str, entry_token: str) -> bool:
    if query_token == entry_token:
        return True
    if _normalize_token(query_token) == _normalize_token(entry_token):
        return True
    if len(query_token) >= 4 and len(entry_token) >= 4:
        return query_token[:4] == entry_token[:4]
    return False


def _distinctive_tokens(query_tokens: set[str]) -> set[str]:
    return {t for t in query_tokens if t not in _GENERIC_TOKENS and len(t) >= 4}


def _has_distinctive_question_match(query_tokens: set[str], question: str) -> bool:
    """True if a non-generic query token matches the KB question text."""
    distinctive = _distinctive_tokens(query_tokens)
    if not distinctive:
        return True
    entry_tokens = _tokenize(question)
    return any(
        any(_tokens_match(qt, et) for et in entry_tokens) for qt in distinctive
    )


def _overlap_ratio(query_tokens: set[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    entry_tokens = _tokenize(text)
    matched = sum(
        1
        for qt in query_tokens
        if any(_tokens_match(qt, et) for et in entry_tokens)
    )
    return matched / len(query_tokens)


@dataclass
class SearchResult:
    entry: SheetRow
    score: float
    question_overlap: float = 0.0


def search(
    query: str,
    entries: list[SheetRow],
    top_k: int = 8,
    threshold: float = 0.1,
) -> list[SearchResult]:
    """
    Score each KB entry against the query using weighted token overlap.

    Weights:
        question match  × 3.0  (most important — directly addresses the query)
        section match   × 1.5  (topic-level match)
        answer match    × 1.0  (broad coverage)

    Returns the top_k results with score >= threshold (relative to query size).
    Returns empty list when no entry meets the threshold.
    """
    if not entries:
        return []

    query_tokens = _tokenize(query)
    query_norm = _normalize_text(query)
    if not query_tokens and not query_norm:
        return []

    n = max(len(query_tokens), 1)
    results: list[SearchResult] = []

    for entry in entries:
        q_overlap = _overlap_ratio(query_tokens, entry.question)
        s_overlap = _overlap_ratio(query_tokens, entry.section)
        a_overlap = _overlap_ratio(query_tokens, entry.answer)

        score = q_overlap * 3.0 + s_overlap * 1.5 + a_overlap * 1.0

        entry_norm = _normalize_text(entry.question)
        if query_norm and entry_norm:
            if query_norm == entry_norm:
                score += 10.0
            elif query_norm in entry_norm or entry_norm in query_norm:
                score += 5.0
            else:
                query_words = [w for w in query_norm.split() if len(w) >= 5]
                entry_words = set(entry_norm.split())
                shared = sum(1 for w in query_words if w in entry_words)
                if shared >= 2:
                    score += 2.0
                elif shared == 1:
                    score += 1.0

        if score > 0:
            results.append(
                SearchResult(
                    entry=entry,
                    score=score,
                    question_overlap=q_overlap,
                )
            )

    results.sort(key=lambda r: r.score, reverse=True)
    top = results[:top_k]

    if not top or top[0].score < threshold:
        return []

    return top


def is_confident_match(
    results: list[SearchResult],
    min_score: float = 1.0,
    *,
    query: str = "",
    min_question_overlap: float = 0.55,
) -> bool:
    """
    True when search found a reasonably relevant KB entry.

    Помимо общего score, проверяем пересечение с полем «Вопрос» и наличие
    совпадения по содержательным (не общим) словам запроса — иначе «клиент +
    что делать» ложно совпадает с нерелевантными строками БЗ.
    """
    if not results:
        return False
    top = results[0]
    if top.score < min_score:
        return False
    if top.question_overlap < min_question_overlap:
        return False
    if top.score >= 5.0:
        return True
    if top.question_overlap >= 0.75:
        return True
    query_tokens = _tokenize(query)
    return _has_distinctive_question_match(query_tokens, top.entry.question)
