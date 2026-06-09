import logging

from ..db.repository import Repository

logger = logging.getLogger(__name__)


async def record_critical(repo: Repository, source: str, message: str) -> None:
    """Persist a critical error to SQLite and purge entries older than retention."""
    text = f"[{source}] {message}"
    logger.error(text)
    try:
        await repo.add_log("CRITICAL", text)
        days = int(await repo.get_setting("log_retention_days", "30"))
        removed = await repo.purge_old_logs(days)
        if removed:
            logger.info("Purged %d log entries older than %d days.", removed, days)
    except Exception as exc:
        logger.error("Failed to write critical log to DB: %s", exc)


async def purge_expired_logs(repo: Repository) -> int:
    """Remove log entries older than configured retention. Call on startup."""
    days = int(await repo.get_setting("log_retention_days", "30"))
    removed = await repo.purge_old_logs(days)
    if removed:
        logger.info("Startup: purged %d expired log entries (>%d days).", removed, days)
    return removed


def format_logs_for_telegram(logs: list, retention_days: int, total_count: int) -> str:
    if not logs:
        return (
            "📋 *Журнал критических ошибок*\n\n"
            "Записей нет. Хранение: {d} дн.".format(d=retention_days)
        )

    lines = [
        f"📋 *Журнал критических ошибок* (последние {len(logs)} из {total_count})\n",
        f"_Хранение: {retention_days} дн. Старые записи удаляются автоматически._\n",
    ]
    for entry in logs:
        ts = entry.created_at.strftime("%d.%m.%Y %H:%M")
        msg = entry.message.replace("`", "'")
        if len(msg) > 300:
            msg = msg[:297] + "..."
        lines.append(f"🔴 `{ts}`\n{msg}\n")

    return "\n".join(lines)
