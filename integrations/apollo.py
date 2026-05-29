"""Apollo.io API client — people search for B2B leads.

Credit gate: search_people() checks the api_usage table before every call
and raises RuntimeError if the monthly limit (default 75) is reached.
This enforces the hard stop whether Volley is called from the dashboard
or the CLI — the gate is in the client, not in the caller.
"""

import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from core.database import log_api_usage, get_monthly_api_credits

logger = logging.getLogger(__name__)
BASE_URL = "https://api.apollo.io/v1"


class ApolloClient:
    def __init__(self, config: dict):
        self.api_key = config["apollo"]["api_key"]
        self.monthly_limit = config["apollo"].get("monthly_credit_limit", 75)
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json", "Cache-Control": "no-cache"})

    def _check_credit(self):
        """Raise RuntimeError if the monthly Apollo credit limit has been reached.

        Queries the local api_usage table — no external API call needed.
        """
        used = get_monthly_api_credits("apollo")
        if used >= self.monthly_limit:
            raise RuntimeError(
                f"Apollo credit limit reached ({used}/{self.monthly_limit} credits used "
                f"this month). Resets on the 1st. "
                f"Use --dry-run to preview without spending credits."
            )
        logger.debug("Apollo credits: %d/%d used this month", used, self.monthly_limit)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _post(self, endpoint: str, payload: dict) -> dict:
        payload["api_key"] = self.api_key
        resp = self.session.post(f"{BASE_URL}/{endpoint}", json=payload, timeout=30)
        if resp.status_code == 422:
            raise ValueError(f"Apollo validation error: {resp.text}")
        resp.raise_for_status()
        return resp.json()

    def search_people(
        self,
        titles: list[str],
        seniority: list[str],
        industries: list[str],
        locations: list[str],
        employee_ranges: list[str],
        limit: int = 25,
    ) -> list[dict]:
        """Search Apollo for people matching the ICP criteria.

        Raises RuntimeError before the API call if the monthly credit limit
        is already reached. Credits are logged after the call.
        """
        self._check_credit()

        payload = {
            "person_titles": titles,
            "person_seniorities": seniority,
            "organization_industry_tag_ids": industries,
            "person_locations": locations,
            "organization_num_employees_ranges": employee_ranges,
            "per_page": min(limit, 25),
            "page": 1,
        }
        try:
            data = self._post("mixed_people/search", payload)
        except Exception as e:
            logger.error("Apollo search failed: %s", e)
            return []

        people = data.get("people", [])
        leads = []
        for p in people:
            org = p.get("organization") or {}
            email = p.get("email") or ""
            if not email or email.endswith("@email.com"):
                continue  # Skip catch-all / placeholder emails

            leads.append({
                "first_name":    p.get("first_name", ""),
                "last_name":     p.get("last_name", ""),
                "title":         p.get("title", ""),
                "email":         email,
                "linkedin_url":  p.get("linkedin_url", ""),
                "company_name":  org.get("name", ""),
                "domain":        org.get("website_url", ""),
                "industry":      org.get("industry", ""),
                "employee_count": str(org.get("num_employees", "")),
                "city":          p.get("city", ""),
                "country":       p.get("country", ""),
                "source":        "apollo",
                "email_verified": 0,
                "icp_score":     0,
                "status":        "new",
                "notes":         "",
            })

        # Log 1 search credit per call regardless of results returned
        log_api_usage(
            provider="apollo",
            model="people_search",
            purpose="lead_discovery",
            input_tokens=1,
            output_tokens=0,
            cost_usd=0.0,
        )
        logger.info("Apollo returned %d usable leads", len(leads))
        return leads

    def search_companies(self, domains: list[str]) -> list[dict]:
        """Look up company info by domain list."""
        self._check_credit()

        payload = {"q_organization_domains": "\n".join(domains), "per_page": len(domains)}
        try:
            data = self._post("organizations/bulk_enrich", payload)
            return data.get("organizations", [])
        except Exception as e:
            logger.error("Apollo company lookup failed: %s", e)
            return []
