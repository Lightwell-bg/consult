from datetime import datetime, timedelta

import pytest

from src.db.repository import Repository
from src.services.critical_log import format_logs_for_telegram, purge_expired_logs, record_critical


async def test_record_critical_writes_to_db(repo):
    await record_critical(repo, "test", "Something broke")
    logs = await repo.get_recent_logs(10)
    assert len(logs) == 1
    assert logs[0].level == "CRITICAL"
    assert "[test]" in logs[0].message
    assert "Something broke" in logs[0].message


async def test_purge_old_logs(repo):
    await repo.add_log("CRITICAL", "old entry")
    # Manually insert old record
    import aiosqlite
    old_date = (datetime.now() - timedelta(days=40)).strftime("%Y-%m-%d %H:%M:%S")
    async with aiosqlite.connect(repo.db_path) as db:
        await db.execute(
            "INSERT INTO logs (level, message, created_at) VALUES (?, ?, ?)",
            ("CRITICAL", "very old", old_date),
        )
        await db.commit()

    await repo.set_setting("log_retention_days", "30")
    removed = await repo.purge_old_logs(30)
    assert removed >= 1
    remaining = await repo.count_logs()
    assert remaining >= 1  # recent entry still there


async def test_purge_expired_logs_on_startup(repo):
    await repo.set_setting("log_retention_days", "7")
    removed = await purge_expired_logs(repo)
    assert removed >= 0


def test_format_logs_empty():
    text = format_logs_for_telegram([], retention_days=30, total_count=0)
    assert "нет" in text.lower() or "Записей" in text


def test_format_logs_with_entries(repo):
    from src.db.models import LogEntry

    logs = [
        LogEntry(
            id=1,
            level="CRITICAL",
            message="[anthropic] API error",
            created_at=datetime(2026, 6, 9, 12, 0, 0),
        )
    ]
    text = format_logs_for_telegram(logs, retention_days=30, total_count=1)
    assert "anthropic" in text
    assert "09.06.2026" in text
