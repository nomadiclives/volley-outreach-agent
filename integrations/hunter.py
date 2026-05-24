"""Hunter.io API client — email finding + verification."""

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

    def domain_search(self, domain: str, limit: int = 10) -> list[dict]:
        """Find emails for a domain."""
        try:
            data = self._get("domain-search", {"domain": domain, "limit": limit})
        except Exception as e:
            logger.error("Hunter domain search failed for %s: %s", domain, e)
            return []

        emails = data.get("data", {}).get("emails", [])
        leads = []
        for e in emails:
            if e.get("confidence", 0) < 70:
                continue
            leads.append({
                "first_name": e.get("first_name", ""),
                "last_name": e.get("last_name", ""),
                "title": e.get("position", ""),
                "email": e.get("value", ""),
                "linkedin_url": "",
                "company_name": data.get("data", {}).get("organization", ""),
                "domain": domain,
                "industry": "",
                "employee_count": "",
                "city": "",
                "country": data.get("data", {}).get("country", ""),
                "source": "hunter",
                "email_verified": 1 if e.get("verification", {}).get("status") == "valid" else 0,
                "icp_score": 0,
                "status": "new",
                "notes": f"Hunter confidence: {e.get('confidence')}%",
            })
        return leads

    def verify_email(self, email: str) -> bool:
        """Verify a single email address. Returns True if valid."""
        try:
            data = self._get("email-verifier", {"email": email})
            status = data.get("data", {}).get("status", "")
            return status == "valid"
        except Exception as e:
            logger.error("Hunter email verify failed for %s: %s", email, e)
            return False
