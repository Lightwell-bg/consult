import io
import logging
from dataclasses import dataclass

import gspread
import openpyxl
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from gspread.exceptions import APIError, SpreadsheetNotFound

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

_MIME_GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"
_MIME_SHORTCUT = "application/vnd.google-apps.shortcut"
_OFFICE_MIMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
}

_PERMISSION_HINT = (
    "Нет доступа к файлу на Google Диске. Откройте файл → «Настройки доступа» → "
    "добавьте email сервисного аккаунта (поле client_email в JSON-ключе) "
    "с правом «Читатель». Доступ нужно выдать отдельно для каждого файла — "
    "и для .xlsx, и для Google Таблицы."
)

_OFFICE_FILE_HINT = (
    "Файл на Google Диске — Excel (.xlsx/.xls), не нативная Google Таблица. "
    "Бот читает его через Drive API. Убедитесь, что включён Google Drive API "
    "и файл расшарен на сервисный аккаунт. "
    "Либо: Файл → Сохранить как Google Таблицу и укажите новый ID в /config."
)

_DRIVE_API_HINT = (
    "Google Drive API не включён в Google Cloud Console. "
    "Нужен для чтения .xlsx и диагностики файла. "
    "API и сервисы → Библиотека → Google Drive API → Включить. "
    "Нативные Google Таблицы могут работать и без него."
)


class DriveMetadataUnavailable(Exception):
    """Drive API недоступен — используем запасной путь через Sheets API."""


@dataclass
class SheetRow:
    section: str
    question: str
    answer: str


def _map_columns(headers: list[str]) -> dict[str, int]:
    """Map column names to indices using flexible keyword matching."""
    mapping: dict[str, int] = {}
    for i, raw in enumerate(headers):
        h = raw.strip().lower()
        if "раздел" in h or "section" in h or "category" in h:
            mapping.setdefault("section", i)
        elif (
            "вопрос" in h
            or "тема" in h
            or "question" in h
            or "topic" in h
            or "тему" in h
        ):
            mapping.setdefault("question", i)
        elif (
            "ответ" in h
            or "информац" in h
            or "answer" in h
            or "info" in h
            or "текст" in h
        ):
            mapping.setdefault("answer", i)
    return mapping


def _pad_row(raw: list, min_len: int) -> list:
    """Extend a row with empty strings so column indices are always reachable."""
    if len(raw) >= min_len:
        return list(raw)
    return list(raw) + [""] * (min_len - len(raw))


def _rows_from_values(all_values: list[list[str]]) -> list[SheetRow]:
    if not all_values:
        return []

    headers = all_values[0]
    col_map = _map_columns(headers)

    if len(col_map) < 2:
        logger.warning(
            "Could not detect column mapping from headers %s; "
            "falling back to columns 0/1/2.",
            headers,
        )
        col_map = {"section": 0, "question": 1, "answer": 2}

    s_idx = col_map.get("section", 0)
    q_idx = col_map.get("question", 1)
    a_idx = col_map.get("answer", 2)
    max_idx = max(s_idx, q_idx, a_idx)

    rows: list[SheetRow] = []
    skipped_empty = 0
    for line_no, raw in enumerate(all_values[1:], start=2):
        if not any(str(cell).strip() for cell in raw):
            continue
        padded = _pad_row(raw, max_idx + 1)
        answer = str(padded[a_idx]).strip()
        if not answer:
            skipped_empty += 1
            logger.debug(
                "Skipped sheet row %d: empty answer (columns=%s).",
                line_no,
                padded[: max_idx + 1],
            )
            continue
        rows.append(
            SheetRow(
                section=str(padded[s_idx]).strip(),
                question=str(padded[q_idx]).strip(),
                answer=answer,
            )
        )

    if skipped_empty:
        logger.info(
            "Parsed %d KB rows; skipped %d rows with empty answer.",
            len(rows),
            skipped_empty,
        )
    return rows


def _mime_label(mime: str) -> str:
    if mime == _MIME_GOOGLE_SHEET:
        return "Google Таблица"
    if mime in _OFFICE_MIMES:
        return "Excel (.xlsx/.xls)"
    return mime or "неизвестно"


class GoogleSheetsClient:
    def __init__(self, service_account_file: str):
        self._service_account_file = service_account_file
        self._client: gspread.Client | None = None
        self._creds: Credentials | None = None

    def _get_credentials(self) -> Credentials:
        if self._creds is None:
            self._creds = Credentials.from_service_account_file(
                self._service_account_file, scopes=_SCOPES
            )
        return self._creds

    def service_account_email(self) -> str:
        return self._get_credentials().service_account_email

    def _get_client(self) -> gspread.Client:
        if self._client is None:
            self._client = gspread.authorize(self._get_credentials())
        return self._client

    def _resolve_file_metadata(self, file_id: str) -> dict[str, str]:
        """Drive metadata; follows shortcuts to the target file."""
        service = build("drive", "v3", credentials=self._get_credentials())
        try:
            meta = service.files().get(
                fileId=file_id,
                fields="id,name,mimeType,modifiedTime,md5Checksum,shortcutDetails",
                supportsAllDrives=True,
            ).execute()
        except HttpError as exc:
            err = str(exc).lower()
            if exc.resp.status == 403 and (
                "accessnotconfigured" in err or "has not been used" in err
            ):
                raise DriveMetadataUnavailable(_DRIVE_API_HINT) from exc
            if exc.resp.status == 404 or "not found" in err:
                raise RuntimeError(
                    f"Файл с ID `{file_id}` не найден. Проверьте ID в /config."
                ) from exc
            if exc.resp.status == 403:
                raise RuntimeError(
                    f"{_PERMISSION_HINT}\n\nEmail SA: {self.service_account_email()}"
                ) from exc
            raise RuntimeError(f"Ошибка Drive API: {exc}") from exc
        except DriveMetadataUnavailable:
            raise
        except Exception as exc:
            raise RuntimeError(f"Ошибка Drive API: {exc}") from exc

        mime = meta.get("mimeType", "")
        if mime == _MIME_SHORTCUT:
            details = meta.get("shortcutDetails") or {}
            target_id = details.get("targetId")
            if not target_id:
                raise RuntimeError("Ярлык на Drive не указывает на целевой файл.")
            logger.info(
                "File %s is a shortcut; resolving target %s.",
                file_id,
                target_id,
            )
            return self._resolve_file_metadata(target_id)

        meta["sourceType"] = _mime_label(mime)
        return meta

    def _fetch_from_native_sheet(self, spreadsheet_id: str) -> list[SheetRow]:
        try:
            client = self._get_client()
            spreadsheet = client.open_by_key(spreadsheet_id)
        except SpreadsheetNotFound as exc:
            raise RuntimeError(
                f"{_PERMISSION_HINT}\n\nEmail SA: {self.service_account_email()}"
            ) from exc
        except APIError as exc:
            message = str(exc).lower()
            if "office file" in message or "not supported for this document" in message:
                raise
            if any(
                token in message
                for token in ("403", "404", "permission", "forbidden", "not found")
            ):
                raise RuntimeError(
                    f"{_PERMISSION_HINT}\n\nEmail SA: {self.service_account_email()}"
                ) from exc
            raise

        worksheets = spreadsheet.worksheets()
        best_title = ""
        best_rows: list[SheetRow] = []
        for ws in worksheets:
            values = ws.get_all_values()
            rows = _rows_from_values(values)
            logger.debug("Worksheet %r: %d KB rows.", ws.title, len(rows))
            if len(rows) > len(best_rows):
                best_title = ws.title
                best_rows = rows

        if len(worksheets) > 1 and best_title:
            logger.info(
                "Native sheet %s: using worksheet %r (%d rows).",
                spreadsheet_id,
                best_title,
                len(best_rows),
            )
        return best_rows

    def _fetch_from_office_file(self, file_id: str) -> list[SheetRow]:
        """Download .xlsx/.xls from Google Drive and parse worksheets."""
        service = build("drive", "v3", credentials=self._get_credentials())
        try:
            request = service.files().get_media(fileId=file_id)
        except Exception as exc:
            err = str(exc).lower()
            if "403" in err or "permission" in err:
                raise RuntimeError(
                    f"{_OFFICE_FILE_HINT}\n\n{_PERMISSION_HINT}\n\n"
                    f"Email SA: {self.service_account_email()}"
                ) from exc
            raise RuntimeError(f"{_OFFICE_FILE_HINT} Ошибка Drive API: {exc}") from exc

        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buffer.seek(0)

        workbook = openpyxl.load_workbook(buffer, read_only=True, data_only=True)
        best_title = ""
        best_rows: list[SheetRow] = []
        for worksheet in workbook.worksheets:
            all_values: list[list[str]] = []
            for row in worksheet.iter_rows(values_only=True):
                all_values.append([str(cell) if cell is not None else "" for cell in row])
            rows = _rows_from_values(all_values)
            if len(rows) > len(best_rows):
                best_title = worksheet.title
                best_rows = rows

        workbook.close()
        logger.info(
            "Parsed Office file %s, worksheet %r: %d rows.",
            file_id,
            best_title or "?",
            len(best_rows),
        )
        return best_rows

    def _fetch_rows_legacy(self, spreadsheet_id: str) -> list[SheetRow]:
        """Sheets API first; Office fallback — если Drive metadata недоступен."""
        try:
            rows = self._fetch_from_native_sheet(spreadsheet_id)
        except APIError as exc:
            message = str(exc)
            if "Office file" in message or "not supported for this document" in message:
                logger.info(
                    "File %s is an Office document; falling back to Drive download.",
                    spreadsheet_id,
                )
                rows = self._fetch_from_office_file(spreadsheet_id)
            else:
                raise
        else:
            logger.info(
                "Fetched %d rows from %s (Sheets API, legacy path).",
                len(rows),
                spreadsheet_id,
            )
            return rows
        logger.info(
            "Fetched %d rows from %s (Office/Drive path).",
            len(rows),
            spreadsheet_id,
        )
        return rows

    def fetch_rows(self, spreadsheet_id: str) -> list[SheetRow]:
        """Read KB rows from a native Google Sheet or an Excel file on Drive."""
        try:
            meta = self._resolve_file_metadata(spreadsheet_id)
        except DriveMetadataUnavailable as exc:
            logger.warning("Drive metadata skipped: %s", exc)
            return self._fetch_rows_legacy(spreadsheet_id)

        mime = meta.get("mimeType", "")
        name = meta.get("name", spreadsheet_id)
        logger.info(
            "KB source: %r type=%s mime=%s",
            name,
            meta.get("sourceType", "?"),
            mime,
        )

        if mime == _MIME_GOOGLE_SHEET:
            rows = self._fetch_from_native_sheet(spreadsheet_id)
        elif mime in _OFFICE_MIMES:
            rows = self._fetch_from_office_file(spreadsheet_id)
        else:
            logger.warning("Unknown mime %s; trying Sheets API then Office fallback.", mime)
            rows = self._fetch_rows_legacy(spreadsheet_id)
            return rows

        if not rows:
            logger.warning(
                "0 KB rows from %r (%s). Check columns Раздел|Вопрос|Ответ "
                "and that the «Ответ» column is filled.",
                name,
                meta.get("sourceType", mime),
            )

        logger.info("Fetched %d rows from %s.", len(rows), spreadsheet_id)
        return rows

    def get_drive_file_info(self, file_id: str) -> dict[str, str]:
        """Return Drive metadata for diagnostics (/reload)."""
        try:
            meta = self._resolve_file_metadata(file_id)
            return {
                "name": meta.get("name", ""),
                "mimeType": meta.get("mimeType", ""),
                "sourceType": meta.get("sourceType", ""),
                "modifiedTime": meta.get("modifiedTime", ""),
                "md5Checksum": meta.get("md5Checksum", ""),
            }
        except DriveMetadataUnavailable as exc:
            return {"warning": str(exc)}
        except Exception as exc:
            logger.warning("Could not fetch Drive metadata for %s: %s", file_id, exc)
            return {"error": str(exc)}
