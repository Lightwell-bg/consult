import logging

from aiogram import F, Router
from aiogram.types import Message

from ...db.repository import Repository
from ...services.anthropic_client import AnthropicClient
from ...services.context import get_context, save_exchange
from ...services.knowledge_base import KnowledgeBase
from ...services.critical_log import record_critical
from ...services.search import search
from ...services.telegram_format import send_formatted

logger = logging.getLogger(__name__)

router = Router(name="chat")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_chat(
    message: Message,
    repo: Repository,
    kb: KnowledgeBase,
    ai_client: AnthropicClient,
) -> None:
    question = (message.text or "").strip()
    if not question:
        return

    user_id = message.from_user.id  # guaranteed by auth middleware

    # Sync on-request if configured
    sync_mode = await repo.get_setting("sync_mode", "scheduled")
    if sync_mode == "on_request":
        spreadsheet_id = await repo.get_setting("spreadsheet_id")
        try:
            await kb.sync(spreadsheet_id)
        except Exception as exc:
            logger.warning("on_request sync failed: %s", exc)

    # Lazy initial load when the cache is empty
    if not kb.is_loaded():
        spreadsheet_id = await repo.get_setting("spreadsheet_id")
        try:
            await kb.sync(spreadsheet_id)
        except Exception as exc:
            await record_critical(repo, "knowledge_base", str(exc))

    # Search KB
    top_k = int(await repo.get_setting("search_top_k", "8"))
    threshold = float(await repo.get_setting("search_threshold", "0.1"))
    results = search(question, kb.entries, top_k=top_k, threshold=threshold)
    use_fallback = len(results) == 0
    if use_fallback:
        logger.info(
            "KB search miss: query=%r entries=%d threshold=%s",
            question,
            kb.entry_count,
            threshold,
        )

    # Conversation history
    max_ctx = int(await repo.get_setting("max_context_messages", "10"))
    history = await get_context(user_id, repo, max_ctx)

    # Ask Claude
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        answer = await ai_client.ask(question, results, history, use_fallback=use_fallback)
    except Exception as exc:
        await record_critical(repo, "anthropic", str(exc))
        answer = (
            "Произошла ошибка при обращении к AI. "
            "Попробуйте повторить запрос через несколько секунд."
        )

    await send_formatted(message, answer)

    # Persist exchange
    await save_exchange(user_id, question, answer, repo, max_ctx)
