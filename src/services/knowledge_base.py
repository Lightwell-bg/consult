import asyncio
import logging
from datetime import datetime
from typing import Optional

from .google_sheets import GoogleSheetsClient, SheetRow

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """In-memory cache of KB entries fetched from Google Sheets."""

    def __init__(self, sheets_client: GoogleSheetsClient):
        self._client = sheets_client
        self._entries: list[SheetRow] = []
        self._last_sync: Optional[datetime] = None
        self._lock = asyncio.Lock()

    @property
    def entries(self) -> list[SheetRow]:
        return self._entries

    @property
    def last_sync(self) -> Optional[datetime]:
        return self._last_sync

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def is_loaded(self) -> bool:
        return len(self._entries) > 0

    async def sync(self, spreadsheet_id: str) -> int:
        """Fetch fresh data from Google Sheets. Thread-safe."""
        async with self._lock:
            loop = asyncio.get_event_loop()
            rows = await loop.run_in_executor(
                None, self._client.fetch_rows, spreadsheet_id
            )
            self._entries = rows
            self._last_sync = datetime.now()
            logger.info("KnowledgeBase synced: %d entries.", len(rows))
            return len(rows)

    async def get_source_metadata(self, spreadsheet_id: str) -> dict[str, str]:
        """Drive file metadata (modifiedTime, name) for sync diagnostics."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._client.get_drive_file_info, spreadsheet_id
        )

    def load_from_rows(self, rows: list[SheetRow]) -> None:
        """Load KB from a pre-built list (used in tests)."""
        self._entries = list(rows)
        self._last_sync = datetime.now()
