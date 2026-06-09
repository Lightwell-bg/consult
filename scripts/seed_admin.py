#!/usr/bin/env python
"""
Adds a Telegram user to the whitelist (optionally as admin).

Usage:
    python scripts/seed_admin.py <telegram_id> [--admin] [--name "Имя Фамилия"]

Examples:
    python scripts/seed_admin.py 123456789
    python scripts/seed_admin.py 123456789 --admin
    python scripts/seed_admin.py 123456789 --admin --name "Иван Петров"
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from src.db.database import init_db
from src.db.repository import Repository


def _parse_args(args: list[str]) -> tuple[int, bool, str]:
    if not args:
        print(__doc__)
        sys.exit(1)

    try:
        telegram_id = int(args[0])
    except ValueError:
        print(f"Error: '{args[0]}' is not a valid integer Telegram ID.")
        sys.exit(1)

    is_admin = "--admin" in args
    name = ""
    if "--name" in args:
        idx = args.index("--name")
        if idx + 1 < len(args):
            name = args[idx + 1].strip()
    return telegram_id, is_admin, name


async def main() -> None:
    telegram_id, is_admin, name = _parse_args(sys.argv[1:])

    db_path = os.getenv("DATABASE_PATH", "data/bot.db")
    await init_db(db_path)
    repo = Repository(db_path)

    existing = await repo.get_user(telegram_id)
    if existing:
        if is_admin and not existing.is_admin:
            await repo.set_admin(telegram_id, True)
            print(f"User {telegram_id} promoted to admin.")
        if name and name != existing.name:
            await repo.set_name(telegram_id, name)
            print(f"Name updated: {name}")
        if not is_admin and not name:
            print(f"User {telegram_id} already exists. is_admin={existing.is_admin}")
        return

    user = await repo.add_user(telegram_id, is_admin=is_admin, name=name)
    role = "admin" if user.is_admin else "regular user"
    label = f"{user.name} ({telegram_id})" if user.name else str(telegram_id)
    print(f"Added {role}: {label}")


if __name__ == "__main__":
    asyncio.run(main())
