import pytest
from src.services.context import get_context, save_exchange


async def test_empty_context(repo):
    history = await get_context(11111, repo)
    assert history == []


async def test_save_and_retrieve_exchange(repo):
    await save_exchange(22222, "Вопрос", "Ответ", repo, max_messages=10)
    history = await get_context(22222, repo)
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "Вопрос"}
    assert history[1] == {"role": "assistant", "content": "Ответ"}


async def test_context_order_is_chronological(repo):
    await save_exchange(33333, "Q1", "A1", repo)
    await save_exchange(33333, "Q2", "A2", repo)
    history = await get_context(33333, repo, max_messages=20)
    roles = [m["role"] for m in history]
    contents = [m["content"] for m in history]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert contents[0] == "Q1"
    assert contents[-1] == "A2"


async def test_context_trimmed_to_max(repo):
    for i in range(10):
        await save_exchange(44444, f"Q{i}", f"A{i}", repo, max_messages=6)
    history = await get_context(44444, repo, max_messages=6)
    # trim_messages keeps 6 most recent rows → 3 exchanges
    assert len(history) <= 6


async def test_context_is_user_scoped(repo):
    await save_exchange(55555, "User A question", "User A answer", repo)
    await save_exchange(66666, "User B question", "User B answer", repo)

    hist_a = await get_context(55555, repo)
    hist_b = await get_context(66666, repo)

    assert all("A" in m["content"] for m in hist_a)
    assert all("B" in m["content"] for m in hist_b)
