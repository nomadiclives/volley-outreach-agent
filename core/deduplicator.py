"""Three-level pre-search deduplication.

Level 1 — Email:      skip if email already in leads table.
Level 2 — Contact:    skip if company_name+first_name+last_name already in DB.
Level 3 — Domain:     skip if any lead for this domain already in DB.

Levels are checked in ascending cost order so credits are never wasted on
companies/contacts we already have.
"""

import logging
from core.database import (
    get_lead_by_email,
    get_lead_by_company_contact,
    get_lead_by_domain,
)

logger = logging.getLogger(__name__)


# ── Level 1 — Email ───────────────────────────────────────────────────────────

def is_duplicate(lead: dict) -> bool:
    """Return True if this lead's email already exists in the DB."""
    email = (lead.get("email") or "").strip().lower()
    if not email:
        return False
    if get_lead_by_email(email):
        logger.debug("L1 dedup: email %s already in DB", email)
        return True
    return False


def deduplicate_batch(leads: list[dict]) -> list[dict]:
    """Filter a batch, removing duplicates against the DB and within the batch.

    Used for legacy single-phase callers — two-phase code uses the individual
    level functions directly.
    """
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


# ── Level 2 — Company + Contact ───────────────────────────────────────────────

def contact_exists_in_leads(company_name: str, first_name: str, last_name: str) -> bool:
    """Return True if this company+person combo is already in the DB.

    Called after a Phase 2 source returns a name, before spending the next
    source's credit or saving the lead.
    """
    if not company_name or not first_name:
        return False
    if get_lead_by_company_contact(company_name, first_name, last_name):
        logger.debug("L2 dedup: %s %s @ %s already in DB", first_name, last_name, company_name)
        return True
    return False


# ── Level 3 — Domain ─────────────────────────────────────────────────────────

def domain_exists_in_leads(domain: str) -> bool:
    """Return True if any lead for this company domain is already in the DB.

    Called before any Phase 2 source is tried for a company, so zero credits
    are spent on companies already fully covered.
    """
    if not domain:
        return False
    if get_lead_by_domain(domain):
        logger.debug("L3 dedup: domain %s already in DB", domain)
        return True
    return False
