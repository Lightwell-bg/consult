import aiosqlite
from datetime import datetime
from typing import Optional

from .models import User, Message, LogEntry


def _row_to_user(row: tuple) -> User:
    # telegram_id, is_admin, name, created_at
    if len(row) == 3:
        return User(
            telegram_id=row[0],
            is_admin=bool(row[1]),
            name="",
            created_at=datetime.fromisoformat(row[2]),
        )
    return User(
        telegram_id=row[0],
        is_admin=bool(row[1]),
        name=row[2] or "",
        created_at=datetime.fromisoformat(row[3]),
    )


class Repository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # ------------------------------------------------------------------ users

    async def get_user(self, telegram_id: int) -> Optional[User]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT telegram_id, is_admin, name, created_at FROM users WHERE telegram_id = ?",
                (telegram_id,),
            ) as cur:
                row = await cur.fetchone()
        if row:
            return _row_to_user(row)
        return None

    async def add_user(
        self, telegram_id: int, is_admin: bool = False, name: str = ""
    ) -> User:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (telegram_id, is_admin, name) VALUES (?, ?, ?)",
                (telegram_id, int(is_admin), name.strip()),
            )
            await db.commit()
        user = await self.get_user(telegram_id)
        assert user is not None
        return user

    async def set_admin(self, telegram_id: int, is_admin: bool) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET is_admin = ? WHERE telegram_id = ?",
                (int(is_admin), telegram_id),
            )
            await db.commit()

    async def set_name(self, telegram_id: int, name: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "UPDATE users SET name = ? WHERE telegram_id = ?",
                (name.strip(), telegram_id),
            )
            await db.commit()
            return (cur.rowcount or 0) > 0

    async def remove_user(self, telegram_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "DELETE FROM users WHERE telegram_id = ?", (telegram_id,)
            )
            await db.commit()
            return (cur.rowcount or 0) > 0

    async def is_user_allowed(self, telegram_id: int) -> bool:
        return await self.get_user(telegram_id) is not None

    async def is_admin(self, telegram_id: int) -> bool:
        user = await self.get_user(telegram_id)
        return user is not None and user.is_admin

    async def list_users(self) -> list[User]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT telegram_id, is_admin, name, created_at FROM users ORDER BY name, created_at"
            ) as cur:
                rows = await cur.fetchall()
        return [_row_to_user(r) for r in rows]

    async def list_admins(self) -> list[User]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT telegram_id, is_admin, name, created_at FROM users "
                "WHERE is_admin = 1 ORDER BY name, created_at"
            ) as cur:
                rows = await cur.fetchall()
        return [_row_to_user(r) for r in rows]

    async def count_admins(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE is_admin = 1"
            ) as cur:
                row = await cur.fetchone()
        return int(row[0]) if row else 0

    # --------------------------------------------------------------- settings

    async def get_setting(self, key: str, default: str = "") -> str:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ) as cur:
                row = await cur.fetchone()
        return row[0] if row else default

    async def set_setting(self, key: str, value: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )
            await db.commit()

    async def get_all_settings(self) -> dict[str, str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT key, value FROM settings") as cur:
                rows = await cur.fetchall()
        return {r[0]: r[1] for r in rows}

    # --------------------------------------------------------------- messages

    async def get_recent_messages(
        self, telegram_id: int, limit: int
    ) -> list[Message]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT id, telegram_id, role, content, created_at
                   FROM messages
                   WHERE telegram_id = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (telegram_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        messages = [
            Message(
                id=r[0],
                telegram_id=r[1],
                role=r[2],
                content=r[3],
                created_at=datetime.fromisoformat(r[4]),
            )
            for r in rows
        ]
        return list(reversed(messages))

    async def add_message(
        self, telegram_id: int, role: str, content: str
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO messages (telegram_id, role, content) VALUES (?, ?, ?)",
                (telegram_id, role, content),
            )
            await db.commit()

    async def trim_messages(self, telegram_id: int, keep: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """DELETE FROM messages
                   WHERE telegram_id = ?
                     AND id NOT IN (
                         SELECT id FROM messages
                         WHERE telegram_id = ?
                         ORDER BY created_at DESC
                         LIMIT ?
                     )""",
                (telegram_id, telegram_id, keep),
            )
            await db.commit()

    async def clear_user_messages(self, telegram_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM messages WHERE telegram_id = ?", (telegram_id,)
            )
            await db.commit()

    # ------------------------------------------------------------------ logs

    async def add_log(self, level: str, message: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO logs (level, message) VALUES (?, ?)",
                (level, message[:2000]),
            )
            await db.commit()

    async def get_recent_logs(self, limit: int = 25) -> list[LogEntry]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """SELECT id, level, message, created_at
                   FROM logs
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [
            LogEntry(
                id=r[0],
                level=r[1],
                message=r[2],
                created_at=datetime.fromisoformat(r[3]),
            )
            for r in rows
        ]

    async def purge_old_logs(self, retention_days: int) -> int:
        if retention_days < 1:
            return 0
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """DELETE FROM logs
                   WHERE created_at < datetime('now', ?)""",
                (f"-{retention_days} days",),
            )
            await db.commit()
            return cur.rowcount or 0

    async def count_logs(self) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM logs") as cur:
                row = await cur.fetchone()
        return int(row[0]) if row else 0
