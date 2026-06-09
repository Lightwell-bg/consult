import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from ...db.repository import Repository
from ...services.critical_log import format_logs_for_telegram, record_critical
from ...services.knowledge_base import KnowledgeBase
from ...services.scheduler import KBScheduler
from ..filters.admin import IsAdminFilter
from ..states.config_states import ConfigStates

logger = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())


def _config_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="usr:open")],
            [InlineKeyboardButton(text="🔗 ID таблицы Google", callback_data="cfg:spreadsheet")],
            [InlineKeyboardButton(text="🔄 Режим синхронизации", callback_data="cfg:sync_mode")],
            [InlineKeyboardButton(text="⏱ Интервал синхронизации (мин)", callback_data="cfg:interval")],
            [InlineKeyboardButton(text="💬 Контекст (макс. сообщений)", callback_data="cfg:context")],
            [InlineKeyboardButton(text="📋 Текущие настройки", callback_data="cfg:show")],
            [InlineKeyboardButton(text="🗂 Хранение логов (дней)", callback_data="cfg:log_retention")],
        ]
    )


def _sync_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="При каждом запросе", callback_data="cfg:mode:on_request")],
            [InlineKeyboardButton(text="По расписанию", callback_data="cfg:mode:scheduled")],
            [InlineKeyboardButton(text="Вручную (/reload)", callback_data="cfg:mode:manual")],
            [InlineKeyboardButton(text="← Назад", callback_data="cfg:back")],
        ]
    )


# ------------------------------------------------------------------ /reload

@router.message(Command("reload"))
async def cmd_reload(
    message: Message,
    kb: KnowledgeBase,
    repo: Repository,
) -> None:
    await message.answer("⏳ Обновляю базу знаний...")
    spreadsheet_id = await repo.get_setting("spreadsheet_id")
    try:
        count = await kb.sync(spreadsheet_id)
        await repo.set_setting("last_kb_sync", datetime.now().isoformat())
        await repo.set_setting("kb_entry_count", str(count))
        await message.answer(f"✅ База знаний обновлена. Загружено записей: {count}")
    except Exception as exc:
        await record_critical(repo, "reload", str(exc))
        await message.answer(f"❌ Ошибка при обновлении базы знаний:\n{exc}")


# ------------------------------------------------------------------ /logs

@router.message(Command("logs"))
async def cmd_logs(message: Message, repo: Repository) -> None:
    retention = int(await repo.get_setting("log_retention_days", "30"))
    total = await repo.count_logs()
    logs = await repo.get_recent_logs(25)
    text = format_logs_for_telegram(logs, retention, total)

    if len(text) <= 4096:
        await message.answer(text, parse_mode="Markdown")
        return

    chunk_size = 4000
    for i in range(0, len(text), chunk_size):
        await message.answer(text[i : i + chunk_size], parse_mode="Markdown")


# ------------------------------------------------------------------ /config

@router.message(Command("config"))
async def cmd_config(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "⚙️ *Админ-панель*\n\n"
        "Здесь можно управлять пользователями, настройками бота и базой знаний.",
        parse_mode="Markdown",
        reply_markup=_config_keyboard(),
    )


# -------------------- config callbacks

@router.callback_query(F.data == "cfg:show")
async def cfg_show(callback: CallbackQuery, repo: Repository) -> None:
    s = await repo.get_all_settings()
    text = (
        "*Текущие настройки:*\n\n"
        f"ID таблицы: `{s.get('spreadsheet_id', '—')}`\n"
        f"Режим синхронизации: `{s.get('sync_mode', '—')}`\n"
        f"Интервал (мин): `{s.get('sync_interval_minutes', '—')}`\n"
        f"Макс. контекст (сообщений): `{s.get('max_context_messages', '—')}`\n"
        f"Top-K поиска: `{s.get('search_top_k', '—')}`\n"
        f"Хранение логов (дней): `{s.get('log_retention_days', '30')}`"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=_config_keyboard())
    await callback.answer()


@router.callback_query(F.data == "cfg:back")
async def cfg_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("⚙️ Настройки бота:", reply_markup=_config_keyboard())
    await callback.answer()


@router.callback_query(F.data == "cfg:spreadsheet")
async def cfg_ask_spreadsheet(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "Введите новый ID Google Таблицы:\n"
        "_Например: `15wtvU9GVkfNaCC3tMmAjJBqfmxtXQu7S`_\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="Markdown",
    )
    await state.set_state(ConfigStates.waiting_spreadsheet_id)
    await callback.answer()


@router.callback_query(F.data == "cfg:sync_mode")
async def cfg_ask_sync_mode(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Выберите режим синхронизации базы знаний:",
        reply_markup=_sync_mode_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cfg:mode:"))
async def cfg_set_sync_mode(
    callback: CallbackQuery,
    repo: Repository,
    scheduler: KBScheduler,
    kb: KnowledgeBase,
) -> None:
    mode = callback.data.split(":")[-1]  # on_request | scheduled | manual
    await repo.set_setting("sync_mode", mode)

    if mode == "scheduled":
        interval = int(await repo.get_setting("sync_interval_minutes", "10"))
        spreadsheet_id = await repo.get_setting("spreadsheet_id")

        async def _sync() -> None:
            try:
                count = await kb.sync(spreadsheet_id)
                await repo.set_setting("last_kb_sync", datetime.now().isoformat())
                await repo.set_setting("kb_entry_count", str(count))
            except Exception as exc:
                await record_critical(repo, "scheduled_sync", str(exc))

        scheduler.schedule_sync(_sync, interval)
        if not scheduler._scheduler.running:
            scheduler.start()
    else:
        scheduler.cancel_sync()

    label = {"on_request": "при каждом запросе", "scheduled": "по расписанию", "manual": "вручную"}.get(mode, mode)
    await callback.message.edit_text(
        f"✅ Режим синхронизации: *{label}*", parse_mode="Markdown", reply_markup=_config_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "cfg:interval")
async def cfg_ask_interval(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "Введите интервал синхронизации в *минутах* (целое число, например `10`):\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="Markdown",
    )
    await state.set_state(ConfigStates.waiting_sync_interval)
    await callback.answer()


@router.callback_query(F.data == "cfg:log_retention")
async def cfg_ask_log_retention(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "Введите срок хранения *критических* логов в днях (целое число, например `30`):\n\n"
        "Записи старше этого срока удаляются автоматически.\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="Markdown",
    )
    await state.set_state(ConfigStates.waiting_log_retention_days)
    await callback.answer()


@router.callback_query(F.data == "cfg:context")
async def cfg_ask_context(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "Введите максимальное количество сообщений в контексте диалога "
        "(целое число, например `10`):\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="Markdown",
    )
    await state.set_state(ConfigStates.waiting_max_context)
    await callback.answer()


# -------------------- FSM message handlers

@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current:
        await state.clear()
        await message.answer("Отменено.", reply_markup=_config_keyboard())
    else:
        await message.answer("Нечего отменять.")


@router.message(ConfigStates.waiting_spreadsheet_id)
async def cfg_save_spreadsheet(
    message: Message,
    state: FSMContext,
    repo: Repository,
) -> None:
    value = (message.text or "").strip()
    if not value or "/" in value:
        await message.answer("Неверный формат ID. Попробуйте снова или /cancel.")
        return
    await repo.set_setting("spreadsheet_id", value)
    await state.clear()
    await message.answer(
        f"✅ ID таблицы обновлён: `{value}`",
        parse_mode="Markdown",
        reply_markup=_config_keyboard(),
    )


@router.message(ConfigStates.waiting_sync_interval)
async def cfg_save_interval(
    message: Message,
    state: FSMContext,
    repo: Repository,
    scheduler: KBScheduler,
    kb: KnowledgeBase,
) -> None:
    text = (message.text or "").strip()
    try:
        minutes = int(text)
        if minutes < 1:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое положительное число (минуты). Или /cancel.")
        return

    await repo.set_setting("sync_interval_minutes", str(minutes))

    sync_mode = await repo.get_setting("sync_mode", "scheduled")
    if sync_mode == "scheduled":
        spreadsheet_id = await repo.get_setting("spreadsheet_id")

        async def _sync() -> None:
            try:
                count = await kb.sync(spreadsheet_id)
                await repo.set_setting("last_kb_sync", datetime.now().isoformat())
                await repo.set_setting("kb_entry_count", str(count))
            except Exception as exc:
                await record_critical(repo, "scheduled_sync", str(exc))

        scheduler.schedule_sync(_sync, minutes)

    await state.clear()
    await message.answer(
        f"✅ Интервал синхронизации: {minutes} мин.",
        reply_markup=_config_keyboard(),
    )


@router.message(ConfigStates.waiting_max_context)
async def cfg_save_context(
    message: Message,
    state: FSMContext,
    repo: Repository,
) -> None:
    text = (message.text or "").strip()
    try:
        count = int(text)
        if count < 2:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число >= 2. Или /cancel.")
        return

    await repo.set_setting("max_context_messages", str(count))
    await state.clear()
    await message.answer(
        f"✅ Максимальный контекст: {count} сообщений.",
        reply_markup=_config_keyboard(),
    )


@router.message(ConfigStates.waiting_log_retention_days)
async def cfg_save_log_retention(
    message: Message,
    state: FSMContext,
    repo: Repository,
) -> None:
    text = (message.text or "").strip()
    try:
        days = int(text)
        if days < 1:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число >= 1. Или /cancel.")
        return

    await repo.set_setting("log_retention_days", str(days))
    removed = await repo.purge_old_logs(days)
    await state.clear()
    extra = f"\nУдалено устаревших записей: {removed}." if removed else ""
    await message.answer(
        f"✅ Логи хранятся {days} дн.{extra}",
        reply_markup=_config_keyboard(),
    )
