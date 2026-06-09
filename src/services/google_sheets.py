import io
import logging
from dataclasses import dataclass

import gspread
import openpyxl
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from gspread.exceptions import APIError

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

_OFFICE_FILE_HINT = (
    "Файл на Google Диске загружен как Excel (.xlsx), а не как Google Таблица. "
    "Откройте файл в Google Диске → Файл → Сохранить как Google Таблицу, "
    "либо убедитесь, что бот имеет доступ к файлу через Service Account."
)


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
    for raw in all_values[1:]:
        if len(raw) <= max_idx:
            continue
        answer = str(raw[a_idx]).strip()
        if not answer:
            continue
        rows.append(
            SheetRow(
                section=str(raw[s_idx]).strip(),
                question=str(raw[q_idx]).strip(),
                answer=answer,
            )
        )
    return rows


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

    def _get_client(self) -> gspread.Client:
        if self._client is None:
            self._client = gspread.authorize(self._get_credentials())
        return self._client

    def _fetch_from_native_sheet(self, spreadsheet_id: str) -> list[SheetRow]:
        client = self._get_client()
        spreadsheet = client.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.get_worksheet(0)
        all_values: list[list[str]] = worksheet.get_all_values()
        return _rows_from_values(all_values)

    def _fetch_from_office_file(self, file_id: str) -> list[SheetRow]:
        """Download .xlsx from Google Drive and parse the first worksheet."""
        service = build("drive", "v3", credentials=self._get_credentials())
        request = service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        buffer.seek(0)

        workbook = openpyxl.load_workbook(buffer, read_only=True, data_only=True)
        worksheet = workbook.active
        all_values: list[list[str]] = []
        for row in worksheet.iter_rows(values_only=True):
            all_values.append([str(cell) if cell is not None else "" for cell in row])

        workbook.close()
        logger.info("Parsed Office file %s from Google Drive.", file_id)
        return _rows_from_values(all_values)

    def fetch_rows(self, spreadsheet_id: str) -> list[SheetRow]:
        """Read all data rows from the first worksheet (native Sheet or .xlsx on Drive)."""
        try:
            rows = self._fetch_from_native_sheet(spreadsheet_id)
        except APIError as exc:
            message = str(exc)
            if "Office file" in message or "not supported for this document" in message:
                logger.info(
                    "File %s is an Office document; falling back to Drive download.",
                    spreadsheet_id,
                )
                try:
                    rows = self._fetch_from_office_file(spreadsheet_id)
                except Exception as drive_exc:
                    raise RuntimeError(
                        f"{_OFFICE_FILE_HINT} Ошибка Drive API: {drive_exc}"
                    ) from drive_exc
            else:
                raise

        logger.info("Fetched %d rows from %s.", len(rows), spreadsheet_id)
        return rows
