"""Snov.io email finder API client.

Good complement to Apollo — finds emails by domain when the person's name is
known (from LinkedIn or GetProspect), or does domain-level discovery when no
name is available.

Credit gate: every call goes through CreditManager.check_and_spend("snov").
Hard stop at 50 credits/month.

Auth: OAuth2 client credentials (user_id + api_secret from config).
"""

import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from core.credit_manager import CreditManager, CreditLimitReached

logger = logging.getLogger(__name__)
AUTH_URL = "https://api.snov.io/v1/oauth/access_token"
BASE_URL = "https://api.snov.io/v1"


class SnovClient:
    def __init__(self, config: dict):
        snov_cfg = config.get("snov", {})
        self.user_id = snov_cfg.get("user_id", "")
        self.api_secret = snov_cfg.get("api_secret", "")
        self.credits = CreditManager(config)
        self._token: str | None = None
        self.session = requests.Session()

    def _get_token(self) -> str:
        """Obtain OAuth2 access token via client credentials flow."""
        if self._token:
            return self._token
        resp = self.session.post(
            AUTH_URL,
            json={
                "grant_type":    "client_credentials",
                "client_id":     self.user_id,
                "client_secret": self.api_secret,
            },
            timeout=15,
        )
        resp.raise_for_status()
        self._token = resp.json().get("access_token", "")
        return self._token

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6))
    def _post(self, endpoint: str, payload: dict) -> dict:
        token = self._get_token()
        payload["access_token"] = token
        resp = self.session.post(f"{BASE_URL}/{endpoint}", json=payload, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def find_email_by_name(
        self,
        domain: str,
        first_name: str,
        last_name: str,
    ) -> dict | None:
        """Find a person's work email given their name and company domain.

        Spends 1 Snov credit. Returns a contact dict or None if not found /
        confidence below 70.
        """
        if not self.user_id or not self.api_secret:
            logger.debug("Snov credentials not set — skipping")
            return None

        self.credits.check_and_spend("snov", purpose="email_resolution")

        try:
            data = self._post(
                "get-emails-from-names",
                {"firstName": first_name, "lastName": last_name, "domain": domain},
            )
        except Exception as e:
            logger.error("Snov email_finder failed for %s %s @ %s: %s",
                         first_name, last_name, domain, e)
            return None

        emails = data.get("data", {}).get("emails", []) or []
        if not emails:
            return None

        best = max(emails, key=lambda e: e.get("confidence", 0))
        email = best.get("email", "")
        confidence = int(best.get("confidence", 0))

        if not email or confidence < 70:
            return None

        logger.info("Snov found %s %s <%s> at %s (confidence=%d)",
                    first_name, last_name, email, domain, confidence)
        return {
            "first_name":        first_name,
            "last_name":         last_name,
            "title":             "",
            "email":             email,
            "hunter_confidence": confidence,
            "email_verified":    1 if confidence >= 90 else 0,
            "linkedin_url":      "",
            "source":            "snov",
        }

    def find_contacts_at_domain(
        self,
        domain: str,
        target_titles: list[str] | None = None,
    ) -> list[dict]:
        """Find contacts at a domain when no specific person name is known.

        Spends 1 Snov credit. Returns up to 3 contacts filtered by target
        titles. Used when Lusha returns nothing and we need to discover a name.
        """
        if not self.user_id or not self.api_secret:
            return []

        self.credits.check_and_spend("snov", purpose="email_resolution")

        try:
            data = self._post(
                "get-domain-emails-with-info",
                {"domain": domain, "type": "personal", "limit": 10},
            )
        except Exception as e:
            logger.error("Snov domain search failed for %s: %s", domain, e)
            return []

        contacts = []
        for e in data.get("data", {}).get("emails", []) or []:
            email = e.get("email", "")
            confidence = int(e.get("confidence", 0))
            if not email or confidence < 70:
                continue
            title = e.get("job_title", "") or ""
            if target_titles and not any(t.lower() in title.lower() for t in target_titles):
                continue
            contacts.append({
                "first_name":        e.get("first_name", ""),
                "last_name":         e.get("last_name", ""),
                "title":             title,
                "email":             email,
                "hunter_confidence": confidence,
                "email_verified":    1 if confidence >= 90 else 0,
                "linkedin_url":      "",
                "source":            "snov",
            })

        logger.info("Snov domain search [%s]: %d contacts found", domain, len(contacts))
        return contacts[:3]
