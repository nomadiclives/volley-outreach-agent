"""Google Sheets CRM sync client."""

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


def _append_rows(tab: str, rows: list[list]):
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


def _update_cell(tab: str, row: int, col: int, value: str):
    svc = _get_service()
    if not svc or not _spreadsheet_id:
        return
    col_letter = chr(ord("A") + col - 1)
    try:
        svc.spreadsheets().values().update(
            spreadsheetId=_spreadsheet_id,
            range=f"{tab}!{col_letter}{row}",
            valueInputOption="USER_ENTERED",
            body={"values": [[value]]},
        ).execute()
    except Exception as e:
        logger.error("Sheets update failed: %s", e)


def _find_lead_row(lead_id: int) -> Optional[int]:
    """Return 1-based row index for a lead id in the Leads tab."""
    svc = _get_service()
    if not svc or not _spreadsheet_id:
        return None
    try:
        result = svc.spreadsheets().values().get(
            spreadsheetId=_spreadsheet_id,
            range=f"{TAB_LEADS}!A:A",
        ).execute()
        values = result.get("values", [])
        for i, row in enumerate(values):
            if row and str(row[0]) == str(lead_id):
                return i + 1  # 1-based
    except Exception as e:
        logger.error("Sheets row lookup failed: %s", e)
    return None


def sync_lead(lead: dict):
    """Append or update a lead row in the Leads tab."""
    row = [
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
    _append_rows(TAB_LEADS, [row])


def sync_lead_status(lead_id: int, status: str):
    """Update only the status column for an existing lead row."""
    row_num = _find_lead_row(lead_id)
    if row_num:
        # Status is column 14 (N)
        _update_cell(TAB_LEADS, row_num, 14, status)
    else:
        logger.warning("Could not find row for lead %d in Sheets", lead_id)


def ensure_headers():
    """Write header rows to all tabs if sheet is empty."""
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
