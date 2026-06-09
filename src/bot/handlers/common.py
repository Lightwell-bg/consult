from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ...db.repository import Repository
from ...services.knowledge_base import KnowledgeBase
from ..commands import setup_commands_for_user

router = Router(name="common")


@router.message(Command("start"))
async def cmd_start(message: Message, repo: Repository) -> None:
    user_id = message.from_user.id if message.from_user else None
    if user_id:
        user = await repo.get_user(user_id)
        if user:
            await setup_commands_for_user(
                message.bot, user_id, is_admin=user.is_admin
            )

    await message.answer(
        "Привет! Я AI-консультант отдела продаж.\n\n"
        "Задайте любой вопрос свободным текстом — про продукт, цены, "
        "условия работы, скрипты продаж или возражения клиентов.\n\n"
        "Команды:\n"
        "/help — инструкция\n"
        "/whoami — ваш Telegram ID\n"
        "/status — состояние бота"
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Как пользоваться ботом:\n\n"
        "Просто напишите вопрос. Например:\n"
        "• Сколько стоит такой-то кофе?\n"
        "• Что отвечать клиенту, если он говорит «дорого»?\n"
        "• Какие условия для оптовиков?\n"
        "• Кто отвечает за поставки?\n"
        "• Какие аргументы по продукту?\n\n"
        "Бот ответит на основе базы знаний компании. "
        "Если данных нет — честно скажет об этом.\n\n"
        "Команды:\n"
        "/start — приветствие\n"
        "/help — эта справка\n"
        "/whoami — ваш Telegram ID\n"
        "/status — состояние бота"
    )


@router.message(Command("whoami"))
async def cmd_whoami(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else "unknown"
    await message.answer(
        f"Ваш Telegram ID: `{user_id}`",
        parse_mode="Markdown",
    )


@router.message(Command("status"))
async def cmd_status(
    message: Message,
    kb: KnowledgeBase,
    repo: Repository,
) -> None:
    last_sync = kb.last_sync
    sync_str = last_sync.strftime("%Y-%m-%d %H:%M:%S") if last_sync else "никогда"
    sync_mode = await repo.get_setting("sync_mode", "scheduled")
    spreadsheet_id = await repo.get_setting("spreadsheet_id", "—")
    interval = await repo.get_setting("sync_interval_minutes", "10")

    mode_label = {
        "on_request": "при каждом запросе",
        "scheduled": f"по расписанию (каждые {interval} мин.)",
        "manual": "вручную (/reload)",
    }.get(sync_mode, sync_mode)

    kb_status = "✅ загружена" if kb.is_loaded() else "⚠️ не загружена"

    await message.answer(
        f"*Статус бота*\n\n"
        f"База знаний: {kb_status}\n"
        f"Записей в базе: {kb.entry_count}\n"
        f"Последняя синхронизация: {sync_str}\n"
        f"Режим синхронизации: {mode_label}\n"
        f"ID таблицы: `{spreadsheet_id}`",
        parse_mode="Markdown",
    )


# Fallback for admin commands sent by non-admins
@router.message(Command("reload", "config", "logs"))
async def cmd_admin_no_access(message: Message) -> None:
    await message.answer("Эта команда доступна только администраторам.")
