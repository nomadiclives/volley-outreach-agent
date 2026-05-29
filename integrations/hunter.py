"""Hunter.io API client — email finding + verification.

Credit tracking: every domain_search() and email_finder() call counts
against the monthly search limit. The hard stop is enforced before each
call via _check_credit().
"""

import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)
BASE_URL = "https://api.hunter.io/v2"


class HunterClient:
    def __init__(self, config: dict):
        self.api_key = config["hunter"]["api_key"]
        self.monthly_limit = config["hunter"].get("monthly_search_limit", 25)
        self.session = requests.Session()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    def _get(self, endpoint: str, params: dict) -> dict:
        params["api_key"] = self.api_key
        resp = self.session.get(f"{BASE_URL}/{endpoint}", params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def _check_credit(self) -> bool:
        """Return False and log a warning if the monthly search limit is reached."""
        try:
            data = self._get("account", {})
            used = data.get("data", {}).get("requests", {}).get("searches", {}).get("used", 0)
            if used >= self.monthly_limit:
                logger.warning(
                    "Hunter monthly limit reached (%d/%d) — skipping call",
                    used, self.monthly_limit,
                )
                return False
        except Exception as e:
            logger.warning("Hunter credit check failed: %s — proceeding anyway", e)
        return True

    def domain_search(self, domain: str, limit: int = 10) -> list[dict]:
        """Find emails for a domain. Returns leads with hunter_confidence as a structured int field."""
        if not self._check_credit():
            return []

        try:
            data = self._get("domain-search", {"domain": domain, "limit": limit})
        except Exception as e:
            logger.error("Hunter domain search failed for %s: %s", domain, e)
            return []

        emails = data.get("data", {}).get("emails", [])
        leads = []
        for e in emails:
            confidence = int(e.get("confidence") or 0)
            if confidence < 70:
                continue
            leads.append({
                "first_name":        e.get("first_name", ""),
                "last_name":         e.get("last_name", ""),
                "title":             e.get("position", ""),
                "email":             e.get("value", ""),
                "hunter_confidence": confidence,
                "linkedin_url":      "",
                "company_name":      data.get("data", {}).get("organization", ""),
                "domain":            domain,
                "industry":          "",
                "employee_count":    "",
                "city":              "",
                "country":           data.get("data", {}).get("country", ""),
                "source":            "hunter",
                "email_verified":    1 if e.get("verification", {}).get("status") == "valid" else 0,
                "icp_score":         0,
                "status":            "new",
                "notes":             "",
            })
        logger.info("Hunter domain_search [%s]: %d leads (confidence ≥70)", domain, len(leads))
        return leads

    def email_finder(self, domain: str, first_name: str, last_name: str) -> dict | None:
        """Find a specific person's email by name + domain.

        Returns a lead dict with hunter_confidence set, or None if not found
        or confidence is below 70.
        Used in Phase 2 contact resolution as a fallback after Lusha/Snov.
        """
        if not self._check_credit():
            return None

        try:
            data = self._get(
                "email-finder",
                {"domain": domain, "first_name": first_name, "last_name": last_name},
            )
        except Exception as e:
            logger.error(
                "Hunter email_finder failed for %s %s @ %s: %s",
                first_name, last_name, domain, e,
            )
            return None

        result = data.get("data", {})
        email = result.get("email", "")
        # Hunter email-finder uses 'score' (0-100) rather than 'confidence'
        confidence = int(result.get("score") or 0)

        if not email or confidence < 70:
            logger.debug(
                "Hunter email_finder: no result for %s %s @ %s (score=%d)",
                first_name, last_name, domain, confidence,
            )
            return None

        logger.info(
            "Hunter email_finder [%s %s @ %s]: %s (score=%d)",
            first_name, last_name, domain, email, confidence,
        )
        return {
            "first_name":        first_name,
            "last_name":         last_name,
            "title":             "",
            "email":             email,
            "hunter_confidence": confidence,
            "linkedin_url":      "",
            "company_name":      "",
            "domain":            domain,
            "industry":          "",
            "employee_count":    "",
            "city":              "",
            "country":           "",
            "source":            "hunter",
            "email_verified":    0,
            "icp_score":         0,
            "status":            "new",
            "notes":             "",
        }

    def verify_email(self, email: str) -> bool:
        """Verify a single email address. Returns True if valid."""
        try:
            data = self._get("email-verifier", {"email": email})
            status = data.get("data", {}).get("status", "")
            return status == "valid"
        except Exception as e:
            logger.error("Hunter email verify failed for %s: %s", email, e)
            return False
