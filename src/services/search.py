import re
from dataclasses import dataclass

from .google_sheets import SheetRow

_STOP_WORDS = {
    "и", "в", "на", "с", "по", "к", "для", "от", "из", "что", "как",
    "это", "не", "но", "а", "или", "то", "же", "бы", "ли", "у", "о",
    "за", "при", "об", "до", "со", "без", "под", "над", "про", "через",
    "все", "так", "он", "она", "они", "мы", "вы", "я", "его", "её",
    "ее", "их", "есть", "был", "была", "были", "быть", "там", "тут",
    "здесь", "который", "которая", "которые", "которого",
    "кто", "такой", "такая", "такое", "такие", "таким", "такого",
    "the", "a", "an", "is", "are", "was", "were", "of", "to", "in",
}


def _normalize_text(text: str) -> str:
    return re.sub(r"[^\wа-яё]+", " ", text.lower()).strip()


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[а-яёa-z0-9]+", text.lower())) - _STOP_WORDS


@dataclass
class SearchResult:
    entry: SheetRow
    score: float


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
        q_overlap = len(query_tokens & _tokenize(entry.question)) / n
        s_overlap = len(query_tokens & _tokenize(entry.section)) / n
        a_overlap = len(query_tokens & _tokenize(entry.answer)) / n

        score = q_overlap * 3.0 + s_overlap * 1.5 + a_overlap * 1.0

        entry_norm = _normalize_text(entry.question)
        if query_norm and entry_norm:
            if query_norm == entry_norm:
                score += 10.0
            elif query_norm in entry_norm or entry_norm in query_norm:
                score += 5.0

        if score > 0:
            results.append(SearchResult(entry=entry, score=score))

    results.sort(key=lambda r: r.score, reverse=True)
    top = results[:top_k]

    if not top or top[0].score < threshold:
        return []

    return top


def is_confident_match(
    results: list[SearchResult],
    min_score: float = 1.5,
) -> bool:
    """True when search found a reasonably relevant KB entry."""
    return bool(results) and results[0].score >= min_score
