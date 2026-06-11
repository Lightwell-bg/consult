import logging

from aiogram import F, Router
from aiogram.types import Message

from ...db.repository import Repository
from ...services.anthropic_client import AnthropicClient
from ...services.context import get_context, save_exchange
from ...services.knowledge_base import KnowledgeBase
from ...services.admin_notify import notify_admins_ai_answer, notify_admins_kb_miss
from ...services.kb_miss_mode import KB_MISS_MODE_AI_ASSIST, KB_MISS_MODE_KB_ONLY
from ...services.critical_log import record_critical
from ...services.search import is_confident_match, search
from ...services.telegram_format import send_formatted

logger = logging.getLogger(__name__)

router = Router(name="chat")

_AI_ERROR_ANSWER_PREFIX = "Произошла ошибка при обращении к AI"


def _is_ai_error_answer(answer: str) -> bool:
    return answer.strip().startswith(_AI_ERROR_ANSWER_PREFIX)


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
    confident_min = float(await repo.get_setting("search_confident_threshold", "1.0"))
    kb_miss = not is_confident_match(results, confident_min, query=question)
    kb_miss_mode = await repo.get_setting("kb_miss_mode", KB_MISS_MODE_KB_ONLY)
    from_user = message.from_user
    asker_first_name = (
        getattr(from_user, "first_name", "") or "" if from_user else ""
    )
    asker_username = getattr(from_user, "username", None) if from_user else None

    if kb_miss:
        if results:
            top = results[0]
            logger.info(
                "KB miss: query=%r entries=%d top_score=%.2f q_overlap=%.2f "
                "top_q=%r mode=%s",
                question,
                kb.entry_count,
                top.score,
                top.question_overlap,
                (top.entry.question or "")[:80],
                kb_miss_mode,
            )
        else:
            logger.info(
                "KB miss: query=%r entries=%d no_candidates mode=%s",
                question,
                kb.entry_count,
                kb_miss_mode,
            )
        results = []
    elif results:
        top = results[0]
        logger.debug(
            "KB hit: query=%r score=%.2f q_overlap=%.2f top_q=%r",
            question,
            top.score,
            top.question_overlap,
            (top.entry.question or "")[:80],
        )

    answer_mode = "kb"
    if kb_miss:
        if kb_miss_mode == KB_MISS_MODE_AI_ASSIST:
            answer_mode = "ai_assist"
        else:
            answer_mode = "fallback"

    # Conversation history
    max_ctx = int(await repo.get_setting("max_context_messages", "10"))
    history = await get_context(user_id, repo, max_ctx)

    # Ask Claude
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        answer = await ai_client.ask(
            question,
            results,
            history,
            use_fallback=answer_mode == "fallback",
            answer_mode=answer_mode,
        )
    except Exception as exc:
        await record_critical(repo, "anthropic", str(exc))
        answer = (
            "Произошла ошибка при обращении к AI. "
            "Попробуйте повторить запрос через несколько секунд."
        )

    await send_formatted(message, answer)

    if kb_miss:
        use_ai_assist_notify = (
            kb_miss_mode == KB_MISS_MODE_AI_ASSIST and not _is_ai_error_answer(answer)
        )
        if use_ai_assist_notify:
            sent = await notify_admins_ai_answer(
                message.bot,
                repo,
                question=question,
                answer=answer,
                asker_id=user_id,
                tg_first_name=asker_first_name,
                tg_username=asker_username,
            )
            logger.info("AI assist: admin notifications sent=%d", sent)
        else:
            sent = await notify_admins_kb_miss(
                message.bot,
                repo,
                question=question,
                asker_id=user_id,
                tg_first_name=asker_first_name,
                tg_username=asker_username,
            )
            reason = "kb_only" if kb_miss_mode == KB_MISS_MODE_KB_ONLY else "ai_error"
            logger.info("KB miss alert (%s): admin notifications sent=%d", reason, sent)

    # Persist exchange
    await save_exchange(user_id, question, answer, repo, max_ctx)
