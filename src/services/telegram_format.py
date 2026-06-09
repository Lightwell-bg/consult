"""Convert AI markdown output to Telegram HTML and send safely."""

import html
import re

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

_HEADER_RE = re.compile(r"^(#{1,3})\s+(.+)$")
_LIST_RE = re.compile(r"^[-•*]\s+(.+)$")
_INLINE_RE = re.compile(r"(\*\*(.+?)\*\*|\*(.+?)\*|`(.+?)`)")


def _inline_format(text: str) -> str:
    """Convert **bold**, *italic*, `code` to Telegram HTML."""
    parts: list[str] = []
    last = 0
    for match in _INLINE_RE.finditer(text):
        parts.append(html.escape(text[last : match.start()]))
        if match.group(2) is not None:
            parts.append(f"<b>{html.escape(match.group(2))}</b>")
        elif match.group(3) is not None:
            parts.append(f"<i>{html.escape(match.group(3))}</i>")
        elif match.group(4) is not None:
            parts.append(f"<code>{html.escape(match.group(4))}</code>")
        last = match.end()
    parts.append(html.escape(text[last:]))
    return "".join(parts)


def markdown_to_telegram_html(text: str) -> str:
    """Convert common markdown patterns to Telegram-compatible HTML."""
    lines = text.split("\n")
    output: list[str] = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            output.append("")
            continue

        if stripped in ("---", "***", "___"):
            output.append("──────────────")
            continue

        header = _HEADER_RE.match(stripped)
        if header:
            output.append(f"<b>{_inline_format(header.group(2))}</b>")
            continue

        if stripped.startswith(">"):
            quote = stripped[1:].strip()
            output.append(f"<blockquote>{_inline_format(quote)}</blockquote>")
            continue

        list_match = _LIST_RE.match(stripped)
        if list_match:
            output.append(f"▫️ {_inline_format(list_match.group(1))}")
            continue

        output.append(_inline_format(stripped))

    return "\n".join(output)


async def send_formatted(message: Message, text: str) -> None:
    """Send text with HTML formatting; fall back to plain text on parse error."""
    formatted = markdown_to_telegram_html(text)
    try:
        await message.answer(formatted, parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        await message.answer(text)
