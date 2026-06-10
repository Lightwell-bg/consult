import logging

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


def format_kb_miss_alert(
    question: str,
    telegram_id: int,
    *,
    db_name: str = "",
    tg_first_name: str = "",
    tg_username: str | None = None,
) -> str:
    asker = _asker_label(
        telegram_id,
        db_name=db_name,
        tg_first_name=tg_first_name,
        tg_username=tg_username,
    )
    text = (
        "⚠️ Ответ в базе знаний не найден\n\n"
        f"Вопрос:\n{question}\n\n"
        f"Спросил: {asker}"
    )
    if len(text) > _MAX_MESSAGE_LEN:
        budget = _MAX_MESSAGE_LEN - len(text) + len(question) - 20
        if budget < 50:
            budget = 50
        text = (
            "⚠️ Ответ в базе знаний не найден\n\n"
            f"Вопрос:\n{question[:budget]}…\n\n"
            f"Спросил: {asker}"
        )
    return text


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
    Send a KB-miss alert to every administrator.

    Returns the number of admins successfully notified.
    """
    admins = [u for u in await repo.list_users() if u.is_admin]
    if not admins:
        logger.warning(
            "KB miss for asker %s but no admins in DB — notification skipped.",
            asker_id,
        )
        return 0

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
        "KB miss alert: asker=%s, notifying %d admin(s), question=%r",
        asker_id,
        len(admins),
        question[:80],
    )

    sent = 0
    for admin in admins:
        try:
            await bot.send_message(admin.telegram_id, text)
            sent += 1
            logger.info("KB miss alert sent to admin %s", admin.telegram_id)
        except Exception as exc:
            logger.warning(
                "Failed to notify admin %s about KB miss: %s",
                admin.telegram_id,
                exc,
            )
    if sent == 0:
        logger.warning("KB miss alert: failed to deliver to any admin.")
    return sent
