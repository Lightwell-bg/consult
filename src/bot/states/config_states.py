from aiogram.fsm.state import State, StatesGroup


class ConfigStates(StatesGroup):
    waiting_spreadsheet_id = State()
    waiting_sync_mode = State()
    waiting_sync_interval = State()
    waiting_max_context = State()
    waiting_add_user_id = State()
    waiting_add_user_name = State()
    waiting_edit_user_name = State()
    waiting_log_retention_days = State()
