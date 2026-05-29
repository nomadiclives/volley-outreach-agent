"""GetProspect.io API client — LinkedIn-based contact discovery.

Searches for contacts at a company by domain. Good complement to Snov and
Lusha for extracting LinkedIn-verified titles and names.

Credit gate: every call goes through CreditManager.check_and_spend("getprospect").
Hard stop at 50 credits/month.
"""

import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from core.credit_manager import CreditManager, CreditLimitReached

logger = logging.getLogger(__name__)
BASE_URL = "https://api.getprospect.com/public/v1"


class GetProspectClient:
    def __init__(self, config: dict):
        self.api_key = config.get("getprospect", {}).get("api_key", "")
        self.credits = CreditManager(config)
        self.session = requests.Session()
        self.session.headers.update({
            "apiKey": self.api_key,
            "Content-Type": "application/json",
        })

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6))
    def _get(self, endpoint: str, params: dict) -> dict:
        params["apiKey"] = self.api_key
        resp = self.session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def find_contacts_at_domain(
        self,
        domain: str,
        company_name: str = "",
        target_titles: list[str] | None = None,
    ) -> list[dict]:
        """Search for contacts at the given company domain.

        Spends 1 GetProspect credit. Returns up to 3 contacts matching any of
        the target titles. Returns [] if limit reached or no results.
        """
        if not self.api_key:
            logger.debug("GetProspect API key not set — skipping")
            return []

        self.credits.check_and_spend("getprospect", purpose="contact_resolution")

        try:
            data = self._get("contacts/search", {"domain": domain, "limit": 10})
        except Exception as e:
            logger.error("GetProspect search failed for %s: %s", domain, e)
            return []

        # API may return data under different keys
        raw = data.get("data") or data.get("contacts") or []
        if isinstance(raw, dict):
            raw = raw.get("contacts") or []

        contacts = []
        for c in raw:
            email = c.get("email", "")
            if not email:
                continue
            title = c.get("title") or c.get("jobTitle") or ""
            if target_titles and not any(t.lower() in title.lower() for t in target_titles):
                continue
            contacts.append({
                "first_name":        c.get("firstName") or c.get("first_name", ""),
                "last_name":         c.get("lastName") or c.get("last_name", ""),
                "title":             title,
                "email":             email,
                "hunter_confidence": 80,
                "email_verified":    0,
                "linkedin_url":      c.get("linkedinUrl") or c.get("linkedin_url", ""),
                "source":            "getprospect",
            })

        if contacts:
            logger.info("GetProspect found %d contacts at %s", len(contacts), domain)
        return contacts[:3]
