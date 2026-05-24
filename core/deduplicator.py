"""Cross-source lead deduplication."""

import logging
from core.database import get_lead_by_email

logger = logging.getLogger(__name__)


def is_duplicate(lead: dict) -> bool:
    """Return True if this lead already exists (email primary key)."""
    email = (lead.get("email") or "").strip().lower()
    if not email:
        return False
    existing = get_lead_by_email(email)
    if existing:
        logger.debug("Duplicate lead skipped: %s", email)
        return True
    return False


def deduplicate_batch(leads: list[dict]) -> list[dict]:
    """Filter a batch, removing duplicates against the DB and within the batch."""
    seen_emails: set[str] = set()
    unique = []
    for lead in leads:
        email = (lead.get("email") or "").strip().lower()
        if not email:
            continue
        if email in seen_emails:
            continue
        if is_duplicate(lead):
            continue
        seen_emails.add(email)
        unique.append(lead)
    removed = len(leads) - len(unique)
    if removed:
        logger.info("Deduplication removed %d leads from batch", removed)
    return unique
