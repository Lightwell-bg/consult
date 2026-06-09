import aiosqlite
from pathlib import Path

DEFAULT_SETTINGS: dict[str, str] = {
    "spreadsheet_id": "15wtvU9GVkfNaCC3tMmAjJBqfmxtXQu7S",
    "sync_mode": "scheduled",
    "sync_interval_minutes": "10",
    "max_context_messages": "10",
    "search_top_k": "8",
    "search_threshold": "0.1",
    "last_kb_sync": "",
    "kb_entry_count": "0",
    "log_retention_days": "30",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    is_admin    BOOLEAN NOT NULL DEFAULT 0,
    name        TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    role        TEXT    NOT NULL,
    content     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_user_time
    ON messages(telegram_id, created_at);

CREATE TABLE IF NOT EXISTS logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    level      TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


async def _migrate_users_name_column(db: aiosqlite.Connection) -> None:
    async with db.execute("PRAGMA table_info(users)") as cur:
        columns = {row[1] for row in await cur.fetchall()}
    if "name" not in columns:
        await db.execute(
            "ALTER TABLE users ADD COLUMN name TEXT NOT NULL DEFAULT ''"
        )


async def init_db(db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_SCHEMA)
        await _migrate_users_name_column(db)
        for key, value in DEFAULT_SETTINGS.items():
            await db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
        await db.commit()
