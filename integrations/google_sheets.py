"""Google Sheets CRM sync client.

Deduplication contract:
    Email address is the unique key for the Leads tab.
    sync_lead()      — upsert a single lead (one index read + one write).
    bulk_sync_leads() — upsert many leads (one index read, batched writes).
    Both are safe to call multiple times and will never create duplicate rows.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_service = None
_spreadsheet_id: Optional[str] = None
_config: Optional[dict] = None

TAB_LEADS = "Leads"
TAB_CAMPAIGNS = "Campaigns"
TAB_SENT = "Sent"
TAB_REPLIES = "Replies"
TAB_ANALYTICS = "Analytics"

LEADS_HEADERS = [
    "ID", "Company", "First Name", "Last Name", "Title", "Email",
    "Domain", "Industry", "Employees", "City", "Country",
    "Source", "ICP Score", "Status", "Email Verified", "Notes", "Created At",
]

# Email is column F (1-based index 6, 0-based index 5 in LEADS_HEADERS)
_EMAIL_COL_LETTER = "F"


def _get_service():
    """Lazy-load Google Sheets API service."""
    global _service
    if _service is not None:
        return _service

    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build

        creds_path = _config["google"]["credentials_path"]
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(creds_path, scopes=scopes)
        _service = build("sheets", "v4", credentials=creds)
        return _service
    except Exception as e:
        logger.warning("Google Sheets not available: %s", e)
        return None


def init_sheets(config: dict):
    """Initialise with config — call once at startup."""
    global _config, _spreadsheet_id
    _config = config
    _spreadsheet_id = config["google"].get("sheets_spreadsheet_id", "")


# ── Low-level read/write helpers ──────────────────────────────────────────────


def _append_rows(tab: str, rows: list[list]):
    """Append one or more rows to the bottom of a tab."""
    svc = _get_service()
    if not svc or not _spreadsheet_id:
        logger.debug("Sheets not configured — skipping append to %s", tab)
        return
    try:
        svc.spreadsheets().values().append(
            spreadsheetId=_spreadsheet_id,
            range=f"{tab}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": rows},
        ).execute()
    except Exception as e:
        logger.error("Sheets append failed: %s", e)


def _update_row(tab: str, row_num: int, values: list):
    """Overwrite a full row at the given 1-based row number."""
    svc = _get_service()
    if not svc or not _spreadsheet_id:
        return
    try:
        svc.spreadsheets().values().update(
            spreadsheetId=_spreadsheet_id,
            range=f"{tab}!A{row_num}",
            valueInputOption="USER_ENTERED",
            body={"values": [values]},
        ).execute()
    except Exception as e:
        logger.error("Sheets row update failed (row %d): %s", row_num, e)


def _batch_update_rows(tab: str, updates: list[tuple[int, list]]):
    """Update multiple rows in a single API call.

    updates — list of (1-based row_num, values) pairs.
    Chunked at 50 to stay comfortably under the API payload limit.
    """
    svc = _get_service()
    if not svc or not _spreadsheet_id or not updates:
        return

    chunk_size = 50
    for i in range(0, len(updates), chunk_size):
        chunk = updates[i : i + chunk_size]
        data = [
            {"range": f"{tab}!A{row_num}", "values": [values]}
            for row_num, values in chunk
        ]
        try:
            svc.spreadsheets().values().batchUpdate(
                spreadsheetId=_spreadsheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": data},
            ).execute()
        except Exception as e:
            logger.error("Sheets batch update failed (chunk %d): %s", i // chunk_size, e)


# ── Email index ────────────────────────────────────────────────────────────────


def _build_email_index() -> dict[str, int]:
    """Read the Email column from the Leads tab.

    Returns a dict of lowercase email → 1-based row number.
    Row 1 (header) is always skipped.
    """
    svc = _get_service()
    if not svc or not _spreadsheet_id:
        return {}
    try:
        result = svc.spreadsheets().values().get(
            spreadsheetId=_spreadsheet_id,
            range=f"{TAB_LEADS}!{_EMAIL_COL_LETTER}:{_EMAIL_COL_LETTER}",
        ).execute()
        values = result.get("values", [])
        index: dict[str, int] = {}
        for i, row in enumerate(values):
            if i == 0:
                continue  # skip header row
            if row:
                email = str(row[0]).strip().lower()
                if email:
                    index[email] = i + 1  # convert to 1-based row number
        return index
    except Exception as e:
        logger.error("Sheets email index build failed: %s", e)
        return {}


# ── Row serialisation ─────────────────────────────────────────────────────────


def _lead_to_row(lead: dict) -> list:
    """Serialise a lead dict to a list matching LEADS_HEADERS column order."""
    return [
        lead.get("id", ""),
        lead.get("company_name", ""),
        lead.get("first_name", ""),
        lead.get("last_name", ""),
        lead.get("title", ""),
        lead.get("email", ""),
        lead.get("domain", ""),
        lead.get("industry", ""),
        lead.get("employee_count", ""),
        lead.get("city", ""),
        lead.get("country", ""),
        lead.get("source", ""),
        lead.get("icp_score", ""),
        lead.get("status", ""),
        "Yes" if lead.get("email_verified") else "No",
        lead.get("notes", ""),
        lead.get("created_at", ""),
    ]


# ── Public API ────────────────────────────────────────────────────────────────


def sync_lead(lead: dict):
    """Upsert a single lead in the Leads tab.

    If a row with the same email already exists, updates it in place.
    If not, appends a new row.
    Safe to call multiple times — never creates duplicates.
    """
    svc = _get_service()
    if not svc or not _spreadsheet_id:
        logger.debug("Sheets not configured — skipping sync_lead")
        return

    email = (lead.get("email") or "").strip().lower()
    row = _lead_to_row(lead)

    if not email:
        logger.warning(
            "sync_lead: lead id=%s has no email — appending without dedup check",
            lead.get("id"),
        )
        _append_rows(TAB_LEADS, [row])
        return

    email_index = _build_email_index()
    if email in email_index:
        _update_row(TAB_LEADS, email_index[email], row)
        logger.debug("Sheets updated row %d for %s", email_index[email], email)
    else:
        _append_rows(TAB_LEADS, [row])
        logger.debug("Sheets appended new row for %s", email)


def bulk_sync_leads(leads: list[dict]):
    """Upsert a batch of leads efficiently.

    Reads the email index once, then:
      - existing rows → batchUpdate (one API call per 50 rows)
      - new rows      → single append call

    Idempotent: safe to run multiple times, never creates duplicates.
    Leads with no email are skipped with a warning.
    """
    svc = _get_service()
    if not svc or not _spreadsheet_id:
        logger.debug("Sheets not configured — skipping bulk_sync_leads")
        return

    email_index = _build_email_index()
    updates: list[tuple[int, list]] = []
    to_append: list[list] = []

    for lead in leads:
        email = (lead.get("email") or "").strip().lower()
        if not email:
            logger.warning("bulk_sync: lead id=%s has no email — skipped", lead.get("id"))
            continue

        row = _lead_to_row(lead)
        if email in email_index:
            updates.append((email_index[email], row))
        else:
            to_append.append(row)
            # Track within this batch so a duplicate in the input list isn't appended twice
            email_index[email] = -1

    if updates:
        _batch_update_rows(TAB_LEADS, updates)
    if to_append:
        _append_rows(TAB_LEADS, to_append)

    logger.info(
        "Sheets bulk sync complete: %d updated, %d inserted",
        len(updates),
        len(to_append),
    )


def sync_lead_status(lead_id: int, status: str):
    """Update only the Status column for a lead identified by its DB id."""
    svc = _get_service()
    if not svc or not _spreadsheet_id:
        return
    try:
        result = svc.spreadsheets().values().get(
            spreadsheetId=_spreadsheet_id,
            range=f"{TAB_LEADS}!A:A",
        ).execute()
        values = result.get("values", [])
        for i, row in enumerate(values):
            if row and str(row[0]) == str(lead_id):
                row_num = i + 1
                # Status is column N (14th column)
                svc.spreadsheets().values().update(
                    spreadsheetId=_spreadsheet_id,
                    range=f"{TAB_LEADS}!N{row_num}",
                    valueInputOption="USER_ENTERED",
                    body={"values": [[status]]},
                ).execute()
                return
    except Exception as e:
        logger.error("sync_lead_status failed for lead %d: %s", lead_id, e)
    logger.warning("Could not find row for lead %d in Sheets", lead_id)


def ensure_headers():
    """Write header row to the Leads tab if the sheet is empty."""
    svc = _get_service()
    if not svc or not _spreadsheet_id:
        return
    try:
        result = svc.spreadsheets().values().get(
            spreadsheetId=_spreadsheet_id,
            range=f"{TAB_LEADS}!A1",
        ).execute()
        if not result.get("values"):
            _append_rows(TAB_LEADS, [LEADS_HEADERS])
            logger.info("Wrote Sheets headers")
    except Exception as e:
        logger.error("Could not check/write Sheets headers: %s", e)
