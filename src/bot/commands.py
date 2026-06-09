import logging

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault

from ..db.repository import Repository

logger = logging.getLogger(__name__)

USER_COMMANDS: list[BotCommand] = [
    BotCommand(command="start", description="Запуск бота"),
    BotCommand(command="help", description="Справка по использованию"),
    BotCommand(command="whoami", description="Ваш Telegram ID"),
    BotCommand(command="status", description="Состояние бота и БЗ"),
]

ADMIN_EXTRA_COMMANDS: list[BotCommand] = [
    BotCommand(command="reload", description="Обновить базу знаний"),
    BotCommand(command="config", description="Настройки и пользователи"),
    BotCommand(command="logs", description="Журнал критических ошибок"),
]

ADMIN_COMMANDS: list[BotCommand] = USER_COMMANDS + ADMIN_EXTRA_COMMANDS


async def setup_default_commands(bot: Bot) -> None:
    """Default menu for all users (employees)."""
    await bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeDefault())
    logger.info("Default bot commands registered.")


async def setup_commands_for_user(bot: Bot, user_id: int, *, is_admin: bool) -> None:
    """Personal menu for a user in their private chat with the bot.

    Uses BotCommandScopeChat (not ChatMember — that scope is for groups only).
    """
    commands = ADMIN_COMMANDS if is_admin else USER_COMMANDS
    await bot.set_my_commands(
        commands,
        scope=BotCommandScopeChat(chat_id=user_id),
    )
    role = "admin" if is_admin else "user"
    logger.debug("Commands set for %s %s (%d commands).", role, user_id, len(commands))


async def clear_user_commands(bot: Bot, user_id: int) -> None:
    """Remove per-chat menu so the user falls back to the default scope."""
    await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=user_id))


async def sync_bot_commands(bot: Bot, repo: Repository) -> None:
    """On startup: default menu + extended menu for every admin in DB."""
    await setup_default_commands(bot)
    admins = [u for u in await repo.list_users() if u.is_admin]
    for user in admins:
        try:
            await setup_commands_for_user(bot, user.telegram_id, is_admin=True)
        except Exception as exc:
            logger.warning(
                "Could not set admin commands for %s: %s", user.telegram_id, exc
            )
    logger.info("Synced command menus for %d admin(s).", len(admins))
