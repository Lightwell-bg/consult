from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from ..db.repository import Repository
from .handlers import admin, chat, common, users
from .middlewares.auth import AuthMiddleware


def create_bot(token: str) -> Bot:
    return Bot(token=token)


def create_dispatcher(repo: Repository) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    # Must be outer_middleware so is_admin is set BEFORE router filters run
    dp.message.outer_middleware(AuthMiddleware(repo))
    dp.callback_query.outer_middleware(AuthMiddleware(repo))

    # Router order matters:
    # 1. admin   — handles /reload, /config and FSM states for admins only
    # 2. common  — handles /start, /help, /whoami, /status; fallback for admin cmds
    # 3. chat    — handles free text
    dp.include_router(admin.router)
    dp.include_router(users.router)
    dp.include_router(common.router)
    dp.include_router(chat.router)

    return dp
