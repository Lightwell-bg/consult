import logging
import re

from aiogram import Bot

from ..db.repository import Repository

logger = logging.getLogger(__name__)

_MAX_MESSAGE_LEN = 4096


def _asker_label(
    telegram_id: int,
    *,
    db_name: str = "",
    tg_first_name: str = "",
    tg_username: str | None = None,
) -> str:
    if db_name:
        label = db_name
    elif tg_first_name:
        label = tg_first_name
    else:
        label = str(telegram_id)
    if tg_username:
        return f"{label} (@{tg_username}, ID {telegram_id})"
    return f"{label} (ID {telegram_id})"


def _answer_for_admin_alert(answer: str) -> str:
    """Плоский текст для админа: без markdown и без дубля заголовка «Ответ ИИ»."""
    text = answer.strip()
    text = re.sub(
        r"^(?:#+\s*)?💡?\s*Ответ ИИ\s*\n*",
        "",
        text,
        count=1,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\n*---\s*\n*📌[^\n]*базе знаний нет[^\n]*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"^#{1,3}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^>\s*", "» ", text, flags=re.MULTILINE)
    text = re.sub(r"^---\s*$", "────────", text, flags=re.MULTILINE)
    text = re.sub(r"^[-•*]\s+", "• ", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _truncate_telegram_text(text: str, max_len: int = _MAX_MESSAGE_LEN) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def format_kb_miss_alert(
    question: str,
    telegram_id: int,
    *,
    db_name: str = "",
    tg_first_name: str = "",
    tg_username: str | None = None,
) -> str:
    """Режим «Только база знаний»: админу — предупреждение без текста ответа сотруднику."""
    asker = _asker_label(
        telegram_id,
        db_name=db_name,
        tg_first_name=tg_first_name,
        tg_username=tg_username,
    )
    text = (
        "⚠️ В базе знаний нет ответа на этот вопрос\n\n"
        f"Вопрос:\n{question}\n\n"
        f"Спросил: {asker}"
    )
    return _truncate_telegram_text(text)


def format_ai_assist_alert(
    question: str,
    answer: str,
    telegram_id: int,
    *,
    db_name: str = "",
    tg_first_name: str = "",
    tg_username: str | None = None,
) -> str:
    """Режим «ИИ отвечает»: админу — вопрос и ответ, который увидел сотрудник."""
    asker = _asker_label(
        telegram_id,
        db_name=db_name,
        tg_first_name=tg_first_name,
        tg_username=tg_username,
    )
    header = (
        "🤖 Ответа в базе знаний не было — сотруднику ответ сформирован с помощью ИИ\n\n"
    )
    footer = f"\n\nСпросил: {asker}"
    plain_answer = _answer_for_admin_alert(answer)
    answer_label = "Ответ для сотрудника:"
    body = f"Вопрос:\n{question}\n\n{answer_label}\n{plain_answer}"
    text = header + body + footer
    if len(text) <= _MAX_MESSAGE_LEN:
        return text
    # Сохраняем вопрос и шапку, обрезаем только блок ответа
    prefix = f"Вопрос:\n{question}\n\n{answer_label}\n"
    budget = _MAX_MESSAGE_LEN - len(header) - len(footer) - len(prefix)
    if budget < 80:
        budget = 80
    body = f"{prefix}{plain_answer[:budget]}…"
    return header + body + footer


async def notify_admins_kb_miss(
    bot: Bot,
    repo: Repository,
    *,
    question: str,
    asker_id: int,
    tg_first_name: str = "",
    tg_username: str | None = None,
) -> int:
    """
    Send a KB-miss alert to every administrator in their private chat with this bot.

    In Telegram private chats ``chat_id`` equals the user's Telegram ID — the same
    bot that answers employees can message admins directly; no second bot is needed.
    """
    asker = await repo.get_user(asker_id)
    db_name = asker.name if asker else ""
    text = format_kb_miss_alert(
        question,
        asker_id,
        db_name=db_name,
        tg_first_name=tg_first_name,
        tg_username=tg_username,
    )
    logger.info(
        "KB miss alert: asker=%s, question=%r",
        asker_id,
        question[:80],
    )
    return await _notify_admins(
        bot, repo, text, log_prefix="KB miss alert"
    )


async def _notify_admins(
    bot: Bot,
    repo: Repository,
    text: str,
    *,
    log_prefix: str,
) -> int:
    admins = await repo.list_admins()
    if not admins:
        logger.warning("%s: no admins in DB — notification skipped.", log_prefix)
        return 0

    sent = 0
    for admin in admins:
        try:
            await bot.send_message(chat_id=admin.telegram_id, text=text)
            sent += 1
            logger.info("%s sent to admin %s", log_prefix, admin.telegram_id)
        except Exception as exc:
            logger.warning(
                "%s failed for admin %s: %s",
                log_prefix,
                admin.telegram_id,
                exc,
            )
    return sent


async def notify_admins_ai_answer(
    bot: Bot,
    repo: Repository,
    *,
    question: str,
    answer: str,
    asker_id: int,
    tg_first_name: str = "",
    tg_username: str | None = None,
) -> int:
    """Notify admins that the bot answered from AI because KB had no match."""
    asker = await repo.get_user(asker_id)
    db_name = asker.name if asker else ""
    text = format_ai_assist_alert(
        question,
        answer,
        asker_id,
        db_name=db_name,
        tg_first_name=tg_first_name,
        tg_username=tg_username,
    )
    logger.info(
        "AI assist alert: asker=%s, question=%r",
        asker_id,
        question[:80],
    )
    return await _notify_admins(
        bot, repo, text, log_prefix="AI assist alert"
    )
