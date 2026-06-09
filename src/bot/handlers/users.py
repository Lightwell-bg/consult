import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ...db.models import User
from ...db.repository import Repository
from ..commands import clear_user_commands, setup_commands_for_user
from ..filters.admin import IsAdminFilter
from ..states.config_states import ConfigStates

logger = logging.getLogger(__name__)

router = Router(name="users")
router.message.filter(IsAdminFilter())
router.callback_query.filter(IsAdminFilter())


def _user_label(user: User, *, short: bool = False) -> str:
    if user.name:
        name = user.name if len(user.name) <= 24 else user.name[:22] + "…"
        return f"{name} ({user.telegram_id})" if not short else name
    return str(user.telegram_id)


def _users_list_keyboard(users: list[User], page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    start = page * per_page
    chunk = users[start : start + per_page]
    rows: list[list[InlineKeyboardButton]] = []

    for user in chunk:
        icon = "👑" if user.is_admin else "👤"
        rows.append([
            InlineKeyboardButton(
                text=f"{icon} {_user_label(user)}",
                callback_data=f"usr:view:{user.telegram_id}",
            )
        ])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"usr:page:{page - 1}"))
    if start + per_page < len(users):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"usr:page:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="➕ Добавить пользователя", callback_data="usr:add")])
    rows.append([InlineKeyboardButton(text="← Назад в настройки", callback_data="cfg:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _user_card_keyboard(telegram_id: int, is_admin: bool) -> InlineKeyboardMarkup:
    if is_admin:
        role_btn = InlineKeyboardButton(
            text="👤 Убрать права админа",
            callback_data=f"usr:demote:{telegram_id}",
        )
    else:
        role_btn = InlineKeyboardButton(
            text="👑 Сделать администратором",
            callback_data=f"usr:promote:{telegram_id}",
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить имя", callback_data=f"usr:edit_name:{telegram_id}")],
            [role_btn],
            [InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data=f"usr:del:{telegram_id}")],
            [InlineKeyboardButton(text="← К списку", callback_data="usr:list")],
        ]
    )


def _pick_role_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Сотрудник", callback_data="usr:pick_role:0"),
                InlineKeyboardButton(text="👑 Администратор", callback_data="usr:pick_role:1"),
            ],
            [InlineKeyboardButton(text="← Отмена", callback_data="usr:list")],
        ]
    )


async def _render_users_list(message: Message, repo: Repository, page: int = 0, *, edit: bool = False) -> None:
    users = await repo.list_users()
    if not users:
        text = "👥 *Пользователи*\n\nСписок пуст. Добавьте первого сотрудника."
    else:
        lines = [
            f"{'👑' if u.is_admin else '👤'} {_user_label(u)}"
            for u in users
        ]
        text = (
            f"👥 *Пользователи* ({len(users)})\n\n"
            + "\n".join(lines)
            + "\n\n_Нажмите на имя для редактирования._"
        )

    kb = _users_list_keyboard(users, page=page)
    if edit:
        await message.edit_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await message.answer(text, parse_mode="Markdown", reply_markup=kb)


async def _show_user_card(message: Message, telegram_id: int, repo: Repository) -> None:
    user = await repo.get_user(telegram_id)
    if not user:
        return
    role = "👑 Администратор" if user.is_admin else "👤 Сотрудник"
    name_line = user.name if user.name else "_не указано_"
    text = (
        f"*Пользователь*\n\n"
        f"Имя: {name_line}\n"
        f"Telegram ID: `{user.telegram_id}`\n"
        f"Роль: {role}\n"
        f"Добавлен: {user.created_at.strftime('%d.%m.%Y %H:%M')}"
    )
    await message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=_user_card_keyboard(user.telegram_id, user.is_admin),
    )


@router.callback_query(F.data == "usr:list")
@router.callback_query(F.data.startswith("usr:page:"))
async def users_list(callback: CallbackQuery, repo: Repository) -> None:
    page = 0
    if callback.data.startswith("usr:page:"):
        page = int(callback.data.split(":")[-1])
    await _render_users_list(callback.message, repo, page=page, edit=True)
    await callback.answer()


@router.callback_query(F.data == "usr:open")
async def users_open(callback: CallbackQuery, repo: Repository) -> None:
    await _render_users_list(callback.message, repo, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith("usr:view:"))
async def user_view(callback: CallbackQuery, repo: Repository) -> None:
    telegram_id = int(callback.data.split(":")[-1])
    if not await repo.get_user(telegram_id):
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    await _show_user_card(callback.message, telegram_id, repo)
    await callback.answer()


@router.callback_query(F.data == "usr:add")
async def user_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.message.edit_text(
        "➕ *Добавление пользователя*\n\n"
        "Шаг 1 из 2. Введите *Telegram ID* нового сотрудника.\n"
        "Узнать ID можно командой /whoami.\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="Markdown",
    )
    await state.set_state(ConfigStates.waiting_add_user_id)
    await callback.answer()


@router.message(ConfigStates.waiting_add_user_id)
async def user_add_id(message: Message, state: FSMContext, repo: Repository) -> None:
    text = (message.text or "").strip()
    try:
        telegram_id = int(text)
        if telegram_id <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите целое положительное число (Telegram ID). Или /cancel.")
        return

    existing = await repo.get_user(telegram_id)
    if existing:
        await state.clear()
        await message.answer(
            f"Пользователь `{_user_label(existing)}` уже есть в списке.\n"
            "Откройте карточку для редактирования.",
            parse_mode="Markdown",
            reply_markup=_user_card_keyboard(telegram_id, existing.is_admin),
        )
        return

    await state.update_data(new_user_id=telegram_id)
    await state.set_state(ConfigStates.waiting_add_user_name)
    await message.answer(
        f"Шаг 2 из 2. Введите *имя* сотрудника для ID `{telegram_id}`:\n\n"
        "_Например: Иван Петров_\n\n"
        "Отправьте /cancel для отмены.",
        parse_mode="Markdown",
    )


@router.message(ConfigStates.waiting_add_user_name)
async def user_add_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 100:
        await message.answer("Введите имя (1–100 символов). Или /cancel.")
        return

    data = await state.get_data()
    telegram_id = data.get("new_user_id")
    if not telegram_id:
        await state.clear()
        await message.answer("Сессия истекла. Начните снова: /config → Пользователи → Добавить.")
        return

    await state.update_data(new_user_name=name)
    await message.answer(
        f"Выберите роль для *{name}* (`{telegram_id}`):",
        parse_mode="Markdown",
        reply_markup=_pick_role_keyboard(),
    )


@router.callback_query(F.data.startswith("usr:pick_role:"))
async def user_create(callback: CallbackQuery, state: FSMContext, repo: Repository) -> None:
    is_admin = callback.data.split(":")[-1] == "1"
    data = await state.get_data()
    telegram_id = data.get("new_user_id")
    name = (data.get("new_user_name") or "").strip()

    if not telegram_id:
        await callback.answer("Сессия истекла. Начните добавление заново.", show_alert=True)
        await state.clear()
        return

    if not name:
        await callback.answer("Сначала введите имя пользователя.", show_alert=True)
        return

    if await repo.get_user(int(telegram_id)):
        await callback.answer("Пользователь уже существует.", show_alert=True)
        await state.clear()
        return

    tid = int(telegram_id)
    await repo.add_user(tid, is_admin=is_admin, name=name)
    await setup_commands_for_user(callback.bot, tid, is_admin=is_admin)
    await state.clear()

    role = "администратор" if is_admin else "сотрудник"
    await callback.message.edit_text(
        f"✅ *{name}* (`{telegram_id}`) добавлен как {role}.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="← К списку", callback_data="usr:list")],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("usr:edit_name:"))
async def user_edit_name_start(callback: CallbackQuery, state: FSMContext, repo: Repository) -> None:
    telegram_id = int(callback.data.split(":")[-1])
    user = await repo.get_user(telegram_id)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    await state.update_data(edit_user_id=telegram_id)
    await state.set_state(ConfigStates.waiting_edit_user_name)
    current = user.name or "не указано"
    await callback.message.edit_text(
        f"✏️ *Изменение имени*\n\n"
        f"Пользователь: `{telegram_id}`\n"
        f"Текущее имя: {current}\n\n"
        f"Введите новое имя:\n\n"
        f"Отправьте /cancel для отмены.",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(ConfigStates.waiting_edit_user_name)
async def user_edit_name_save(message: Message, state: FSMContext, repo: Repository) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 100:
        await message.answer("Введите имя (1–100 символов). Или /cancel.")
        return

    data = await state.get_data()
    telegram_id = data.get("edit_user_id")
    if not telegram_id:
        await state.clear()
        await message.answer("Сессия истекла. Откройте карточку пользователя снова.")
        return

    if not await repo.set_name(int(telegram_id), name):
        await message.answer("Пользователь не найден.")
        await state.clear()
        return

    await state.clear()
    user = await repo.get_user(int(telegram_id))
    await message.answer(
        f"✅ Имя обновлено: *{name}*",
        parse_mode="Markdown",
        reply_markup=_user_card_keyboard(int(telegram_id), user.is_admin if user else False),
    )


@router.callback_query(F.data.startswith("usr:promote:"))
async def user_promote(callback: CallbackQuery, repo: Repository) -> None:
    telegram_id = int(callback.data.split(":")[-1])
    if not await repo.get_user(telegram_id):
        await callback.answer("Пользователь не найден.", show_alert=True)
        return
    await repo.set_admin(telegram_id, True)
    await setup_commands_for_user(callback.bot, telegram_id, is_admin=True)
    await callback.answer("Права администратора выданы.")
    await _show_user_card(callback.message, telegram_id, repo)


@router.callback_query(F.data.startswith("usr:demote:"))
async def user_demote(callback: CallbackQuery, repo: Repository) -> None:
    telegram_id = int(callback.data.split(":")[-1])
    actor_id = callback.from_user.id

    user = await repo.get_user(telegram_id)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    if user.is_admin and await repo.count_admins() <= 1:
        await callback.answer("Нельзя убрать последнего администратора.", show_alert=True)
        return

    if telegram_id == actor_id and user.is_admin and await repo.count_admins() <= 1:
        await callback.answer("Нельзя снять права с единственного администратора.", show_alert=True)
        return

    await repo.set_admin(telegram_id, False)
    await setup_commands_for_user(callback.bot, telegram_id, is_admin=False)
    await callback.answer("Права администратора сняты.")
    await _show_user_card(callback.message, telegram_id, repo)


@router.callback_query(F.data.startswith("usr:del:"))
async def user_delete(callback: CallbackQuery, repo: Repository) -> None:
    telegram_id = int(callback.data.split(":")[-1])
    actor_id = callback.from_user.id

    user = await repo.get_user(telegram_id)
    if not user:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    if telegram_id == actor_id:
        await callback.answer("Нельзя удалить самого себя.", show_alert=True)
        return

    if user.is_admin and await repo.count_admins() <= 1:
        await callback.answer("Нельзя удалить последнего администратора.", show_alert=True)
        return

    removed = await repo.remove_user(telegram_id)
    if not removed:
        await callback.answer("Не удалось удалить.", show_alert=True)
        return

    try:
        await clear_user_commands(callback.bot, telegram_id)
    except Exception:
        pass

    await callback.answer("Пользователь удалён.")
    await _render_users_list(callback.message, repo, edit=True)
