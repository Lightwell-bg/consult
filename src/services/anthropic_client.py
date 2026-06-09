import asyncio
import logging
from pathlib import Path

import anthropic

from .search import SearchResult

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"


def _load_prompt(filename: str) -> str:
    path = _PROMPTS_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    logger.warning("Prompt file not found: %s", path)
    return ""


def _build_kb_block(results: list[SearchResult]) -> str:
    if not results:
        return ""
    lines = ["## Релевантные фрагменты из базы знаний:\n"]
    for r in results:
        section = f"[{r.entry.section}] " if r.entry.section else ""
        if r.entry.question:
            lines.append(f"**{section}{r.entry.question}**")
        lines.append(r.entry.answer)
        lines.append("")
    return "\n".join(lines)


class AnthropicClient:
    def __init__(self, api_key: str, model: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._system_prompt = _load_prompt("system.md")
        self._fallback_prompt = _load_prompt("fallback.md")

    def reload_prompts(self) -> None:
        self._system_prompt = _load_prompt("system.md")
        self._fallback_prompt = _load_prompt("fallback.md")

    async def ask(
        self,
        question: str,
        kb_results: list[SearchResult],
        history: list[dict[str, str]],
        use_fallback: bool = False,
    ) -> str:
        """
        Send a question to Claude with KB context and conversation history.

        When use_fallback=True the fallback system prompt is used (no KB data found).
        The history list contains previous {role, content} pairs (not including
        the current question).
        """
        system = self._fallback_prompt if use_fallback else self._system_prompt
        if not system:
            system = (
                "Ты помощник отдела продаж. Отвечай только на основе "
                "предоставленных данных базы знаний."
            )

        kb_block = _build_kb_block(kb_results)
        user_content = question
        if kb_block:
            user_content = f"{kb_block}\n## Вопрос сотрудника:\n{question}"

        messages = list(history) + [{"role": "user", "content": user_content}]

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=system,
                messages=messages,
            ),
        )
        return response.content[0].text
