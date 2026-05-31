"""Lusha API client — European/DACH B2B contact finder.

Strongest for DACH-region companies. Credit gate: every call goes through
CreditManager.check_and_spend("lusha") before the request. Hard stop at
40 credits/month.
"""

import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from core.credit_manager import CreditManager, CreditLimitReached

logger = logging.getLogger(__name__)
BASE_URL = "https://api.lusha.com/v2"


def _is_valid_domain(domain: str | None) -> bool:
    """Return True only if domain looks like a real web domain.

    Rejects: empty/None, strings with spaces (person names, city names),
    strings with no dot, and strings whose TLD is not 2–6 alpha chars.
    """
    if not domain or not isinstance(domain, str):
        return False
    d = domain.strip().lower()
    if not d or " " in d:
        return False
    parts = d.split(".")
    if len(parts) < 2:
        return False
    tld = parts[-1]
    if not tld.isalpha() or not (2 <= len(tld) <= 6):
        return False
    # Label before TLD must be at least 2 chars
    if len(parts[-2]) < 2:
        return False
    return True


class LushaClient:
    def __init__(self, config: dict):
        self.api_key = config.get("lusha", {}).get("api_key", "")
        self.credits = CreditManager(config)
        self.session = requests.Session()
        self.session.headers.update({
            "api_key": self.api_key,
            "Content-Type": "application/json",
        })

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6))
    def _post(self, endpoint: str, payload: dict) -> dict:
        resp = self.session.post(f"{BASE_URL}/{endpoint}", json=payload, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def find_contact_at_company(
        self,
        company_name: str,
        domain: str,
        target_titles: list[str] | None = None,
    ) -> dict | None:
        """Find the most relevant marketing/decision-maker contact at a company.

        Spends 1 Lusha credit regardless of result. Returns a contact dict
        with first_name, last_name, title, email, or None if not found.
        """
        if not self.api_key:
            logger.debug("Lusha API key not set — skipping")
            return None

        if not _is_valid_domain(domain):
            logger.debug(
                "Lusha: skipping %s — domain %r failed validation",
                company_name, domain,
            )
            return None

        self.credits.check_and_spend("lusha", purpose="contact_resolution")

        payload: dict = {"company": {"website": domain.strip().lower()}}

        if target_titles:
            payload["jobTitles"] = target_titles[:5]

        try:
            data = self._post("people/search", payload)
        except Exception as e:
            logger.error("Lusha search failed for %s/%s: %s", company_name, domain, e)
            return None

        # Lusha may return data in different shapes depending on API version
        raw = data.get("data") or {}
        contacts = (
            raw.get("contacts")
            or raw.get("people")
            or (raw if isinstance(raw, list) else [])
        )
        if not contacts:
            logger.debug("Lusha: no contacts at %s", domain or company_name)
            return None

        c = contacts[0]
        emails = c.get("emails") or []
        email = next((e.get("email") for e in emails if e.get("email")), "")
        if not email:
            return None

        logger.info(
            "Lusha found: %s %s <%s> at %s",
            c.get("firstName", ""), c.get("lastName", ""), email, company_name or domain,
        )
        return {
            "first_name":        c.get("firstName", ""),
            "last_name":         c.get("lastName", ""),
            "title":             c.get("jobTitle", ""),
            "email":             email,
            "email_verified":    1,
            "linkedin_url":      c.get("linkedinUrl", ""),
            "source":            "lusha",
            "hunter_confidence": 90,
        }
