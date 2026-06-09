"""Convert AI output to Telegram HTML and send with parse_mode=HTML."""
import html
import re
from typing import Iterable

from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

_MAX_MESSAGE_LEN = 4096


def _inline_markdown_to_html(text: str) -> str:
    """Convert **bold** and *italic* in a line that is not already HTML."""
    text = re.sub(
        r"\*\*(.+?)\*\*",
        lambda m: f"<b>{html.escape(m.group(1))}</b>",
        text,
    )
    text = re.sub(
        r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)",
        lambda m: f"<i>{html.escape(m.group(1))}</i>",
        text,
    )
    return text


def _looks_like_html(text: str) -> bool:
    return bool(re.search(r"</?(?:b|i|u|code|pre|blockquote|a)\b", text, re.I))


def prepare_telegram_html(text: str) -> str:
    """
    Normalize AI answer for Telegram HTML parse mode.

    If the model already returned HTML tags — sanitize and pass through.
    Otherwise convert common Markdown patterns (##, **, lists, blockquotes).
    """
    if _looks_like_html(text):
        return _sanitize_html(text)

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            lines.append("")
            continue

        if stripped in ("---", "***", "___"):
            lines.append("")
            continue

        if stripped.startswith("## "):
            title = stripped[3:].strip()
            lines.append(f"<b>📌 {_inline_markdown_to_html(html.escape(title))}</b>")
            continue

        if stripped.startswith("### "):
            title = stripped[4:].strip()
            lines.append(f"<b>💡 {_inline_markdown_to_html(html.escape(title))}</b>")
            continue

        if stripped.startswith("> "):
            quote = stripped[2:]
            inner = _inline_markdown_to_html(html.escape(quote))
            lines.append(f"<blockquote>{inner}</blockquote>")
            continue

        if re.match(r"^[-*•]\s+", stripped):
            item = re.sub(r"^[-*•]\s+", "", stripped)
            inner = _inline_markdown_to_html(html.escape(item))
            lines.append(f"• {inner}")
            continue

        if re.match(r"^\d+\.\s+", stripped):
            inner = _inline_markdown_to_html(html.escape(stripped))
            lines.append(inner)
            continue

        lines.append(_inline_markdown_to_html(html.escape(line)))

    return "\n".join(lines)


def _sanitize_html(text: str) -> str:
    """Remove unsupported/dangerous tags, keep Telegram-safe subset."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.I | re.S)
    text = re.sub(r"<(?!/?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|blockquote|a|tg-spoiler)\b)[^>]+>", "", text, re.I)
    return text


def split_message(text: str, limit: int = _MAX_MESSAGE_LEN) -> Iterable[str]:
    """Split long HTML text on paragraph boundaries."""
    if len(text) <= limit:
        yield text
        return

    parts: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = f"{current}\n\n{block}".strip() if current else block
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                parts.append(current)
            while len(block) > limit:
                parts.append(block[:limit])
                block = block[limit:]
            current = block
    if current:
        parts.append(current)

    for part in parts:
        yield part


async def send_formatted_answer(message: Message, text: str) -> None:
    """Send answer with Telegram HTML formatting; fall back to plain text on error."""
    html_text = prepare_telegram_html(text)
    try:
        for chunk in split_message(html_text):
            await message.answer(chunk, parse_mode=ParseMode.HTML)
    except TelegramBadRequest:
        for chunk in split_message(text):
            await message.answer(chunk)
