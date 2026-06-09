from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    telegram_id: int
    is_admin: bool
    name: str
    created_at: datetime


@dataclass
class LogEntry:
    id: int
    level: str
    message: str
    created_at: datetime


@dataclass
class Message:
    id: Optional[int]
    telegram_id: int
    role: str  # "user" or "assistant"
    content: str
    created_at: datetime
