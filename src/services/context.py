from ..db.repository import Repository


async def get_context(
    telegram_id: int,
    repo: Repository,
    max_messages: int = 10,
) -> list[dict[str, str]]:
    """Return recent conversation history as a list of {role, content} dicts."""
    messages = await repo.get_recent_messages(telegram_id, max_messages)
    return [{"role": m.role, "content": m.content} for m in messages]


async def save_exchange(
    telegram_id: int,
    user_text: str,
    assistant_text: str,
    repo: Repository,
    max_messages: int = 10,
) -> None:
    """Persist one question/answer pair and trim the history."""
    await repo.add_message(telegram_id, "user", user_text)
    await repo.add_message(telegram_id, "assistant", assistant_text)
    await repo.trim_messages(telegram_id, max_messages)
