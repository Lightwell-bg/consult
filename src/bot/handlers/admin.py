import logging
import re
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
from ...services.telegram_format import safe_edit_text
from ...services.knowledge_base import KnowledgeBase
from ...services.kb_miss_mode import (
    KB_MISS_MODE_AI_ASSIST,
    KB_MISS_MODE_KB_ONLY,
    label_for_mode,
)
from ...services.scheduler import KBScheduler
from ..filters.admin import IsAdminFilter
from ..states.config_states import ConfigStates

logger = logging.getLogger(__name__)

router = Router(name="admin")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())

_SPREADSHEET_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{10,}$")
_SPREADSHEET_URL_RE = re.compile(
    r"/spreadsheets/d/([a-zA-Z0-9_-]+)|open\?id=([a-zA-Z0-9_-]+)"
)


def _extract_spreadsheet_id(raw: str) -> str | None:
    """ID из строки или ссылки Google Таблицы / файла на Диске."""
    value = raw.strip()
    if not value:
        return None
    if _SPREADSHEET_ID_RE.fullmatch(value):
        return value
    match = _SPREADSHEET_URL_RE.search(value)
    if match:
        return match.group(1) or match.group(2)
    return None


_FSM_TEXT = F.text & ~F.text.startswith("/")


def _config_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="usr:open")],
            [InlineKeyboardButton(text="🔗 ID таблицы Google", callback_data="cfg:spreadsheet")],
            [InlineKeyboardButton(text="🔄 Режим синхронизации", callback_data="cfg:sync_mode")],
            [InlineKeyboardButton(text="⏱ Интервал синхронизации (мин)", callback_data="cfg:interval")],
            [InlineKeyboardButton(text="💬 Контекст (макс. сообщений)", callback_data="cfg:context")],
            [InlineKeyboardButton(text="🔎 Top-K поиска", callback_data="cfg:search_top_k")],
            [
                InlineKeyboardButton(
                    text="🧠 Режим при отсутствии в БЗ",
                    callback_data="cfg:kb_miss_mode",
                )
            ],
            [InlineKeyboardButton(text="📋 Текущие настройки", callback_data="cfg:show")],
            [InlineKeyboardButton(text="🗂 Хранение логов (дней)", callback_data="cfg:log_retention")],
        ]
    )


def _kb_miss_mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Только база знаний",
                    callback_data="cfg:kb_miss:kb_only",
                )
            ],
            [
                InlineKeyboardButton(
                    text="ИИ отвечает, если в БЗ нет",
                    callback_data="cfg:kb_miss:ai_assist",
                )
            ],
            [InlineKeyboardButton(text="← Назад", callback_data="cfg:back")],
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
    prev_count = int(await repo.get_setting("kb_entry_count", "0"))
    try:
        meta = await kb.get_source_metadata(spreadsheet_id)
        count = await kb.sync(spreadsheet_id)
        await repo.set_setting("last_kb_sync", datetime.now().isoformat())
        await repo.set_setting("kb_entry_count", str(count))
        lines = [f"✅ База знаний обновлена. Загружено записей: {count}"]
        if prev_count and prev_count != count:
            delta = count - prev_count
            sign = "+" if delta > 0 else ""
            lines.append(f"Изменение: {sign}{delta} (было {prev_count})")
        if meta.get("name"):
            type_label = meta.get("sourceType") or meta.get("mimeType", "")
            lines.append(f"📁 Файл: {meta['name']}")
            if type_label:
                lines.append(f"📄 Тип: {type_label}")
        if meta.get("modifiedTime"):
            lines.append(f"🕒 Изменён на Drive: {meta['modifiedTime']}")
        if meta.get("warning"):
            lines.append(f"⚠️ {meta['warning']}")
        if meta.get("error"):
            lines.append(f"❌ {meta['error']}")
        if count == 0 and not meta.get("error"):
            lines.append(
                "⚠️ 0 записей — проверьте столбцы Раздел|Вопрос|Ответ и доступ SA к файлу."
            )
        await message.answer("\n".join(lines))
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
        f"Режим при отсутствии в БЗ: `{label_for_mode(s.get('kb_miss_mode', KB_MISS_MODE_KB_ONLY))}`\n"
        f"Хранение логов (дней): `{s.get('log_retention_days', '30')}`"
    )
    await safe_edit_text(
        callback.message, text, parse_mode="Markdown", reply_markup=_config_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "cfg:back")
async def cfg_back(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_edit_text(
        callback.message, "⚙️ Настройки бота:", reply_markup=_config_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "cfg:spreadsheet")
async def cfg_ask_spreadsheet(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_edit_text(
        callback.message,
        "Введите новый ID Google Таблицы:\n"
        "_Например: `15wtvU9GVkfNaCC3tMmAjJBqfmxtXQu7S`_\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="Markdown",
    )
    await state.set_state(ConfigStates.waiting_spreadsheet_id)
    await callback.answer()


@router.callback_query(F.data == "cfg:sync_mode")
async def cfg_ask_sync_mode(callback: CallbackQuery) -> None:
    await safe_edit_text(
        callback.message,
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
    await safe_edit_text(
        callback.message,
        f"✅ Режим синхронизации: *{label}*",
        parse_mode="Markdown",
        reply_markup=_config_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "cfg:interval")
async def cfg_ask_interval(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_edit_text(
        callback.message,
        "Введите интервал синхронизации в *минутах* (целое число, например `10`):\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="Markdown",
    )
    await state.set_state(ConfigStates.waiting_sync_interval)
    await callback.answer()


@router.callback_query(F.data == "cfg:log_retention")
async def cfg_ask_log_retention(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_edit_text(
        callback.message,
        "Введите срок хранения *критических* логов в днях (целое число, например `30`):\n\n"
        "Записи старше этого срока удаляются автоматически.\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="Markdown",
    )
    await state.set_state(ConfigStates.waiting_log_retention_days)
    await callback.answer()


@router.callback_query(F.data == "cfg:context")
async def cfg_ask_context(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_edit_text(
        callback.message,
        "Введите максимальное количество сообщений в контексте диалога "
        "(целое число, например `10`):\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="Markdown",
    )
    await state.set_state(ConfigStates.waiting_max_context)
    await callback.answer()


@router.callback_query(F.data == "cfg:kb_miss_mode")
async def cfg_ask_kb_miss_mode(callback: CallbackQuery) -> None:
    await safe_edit_text(
        callback.message,
        "Выберите, что делать, если в базе знаний *нет подходящего ответа*:\n\n"
        "• *Только база знаний* — сотруднику «нет в БЗ»; админу предупреждение и вопрос (без ответа).\n"
        "• *ИИ отвечает* — сотруднику ответ ИИ; админу вопрос и полный текст этого ответа.",
        parse_mode="Markdown",
        reply_markup=_kb_miss_mode_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cfg:kb_miss:"))
async def cfg_set_kb_miss_mode(callback: CallbackQuery, repo: Repository) -> None:
    mode = callback.data.split(":")[-1]
    if mode not in (KB_MISS_MODE_KB_ONLY, KB_MISS_MODE_AI_ASSIST):
        await callback.answer("Неизвестный режим.", show_alert=True)
        return
    await repo.set_setting("kb_miss_mode", mode)
    await safe_edit_text(
        callback.message,
        f"✅ Режим при отсутствии в БЗ: *{label_for_mode(mode)}*",
        parse_mode="Markdown",
        reply_markup=_config_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "cfg:search_top_k")
async def cfg_ask_search_top_k(callback: CallbackQuery, state: FSMContext) -> None:
    await safe_edit_text(
        callback.message,
        "Введите *Top-K поиска* — сколько фрагментов базы знаний "
        "передавать в AI (целое число, например `8`):\n\n"
        "_Чем больше число, тем больше подсказок из таблицы; "
        "обычно достаточно 6–10._\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="Markdown",
    )
    await state.set_state(ConfigStates.waiting_search_top_k)
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


@router.message(ConfigStates.waiting_spreadsheet_id, _FSM_TEXT)
async def cfg_save_spreadsheet(
    message: Message,
    state: FSMContext,
    repo: Repository,
) -> None:
    value = _extract_spreadsheet_id(message.text or "")
    if not value:
        await message.answer(
            "Неверный формат ID. Вставьте ID или ссылку на таблицу.\n"
            "Или /cancel для отмены."
        )
        return
    await repo.set_setting("spreadsheet_id", value)
    await state.clear()
    await message.answer(
        f"✅ ID таблицы обновлён: `{value}`",
        parse_mode="Markdown",
        reply_markup=_config_keyboard(),
    )


@router.message(ConfigStates.waiting_sync_interval, _FSM_TEXT)
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


@router.message(ConfigStates.waiting_max_context, _FSM_TEXT)
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


@router.message(ConfigStates.waiting_search_top_k, _FSM_TEXT)
async def cfg_save_search_top_k(
    message: Message,
    state: FSMContext,
    repo: Repository,
) -> None:
    text = (message.text or "").strip()
    try:
        top_k = int(text)
        if top_k < 1 or top_k > 20:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое число от 1 до 20. Или /cancel.")
        return

    await repo.set_setting("search_top_k", str(top_k))
    await state.clear()
    await message.answer(
        f"✅ Top-K поиска: {top_k} фрагмент(ов) из базы знаний.",
        reply_markup=_config_keyboard(),
    )


@router.message(ConfigStates.waiting_log_retention_days, _FSM_TEXT)
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
