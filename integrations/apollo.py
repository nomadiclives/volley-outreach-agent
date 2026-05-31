"""Apollo.io API client — people search and company discovery.

Credit gate: search_people() and search_organizations() both call
CreditManager.check_and_spend("apollo") before every API call, which enforces
the hard monthly stop whether called from the dashboard or the CLI.
"""

import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from core.credit_manager import CreditManager, CreditLimitReached

logger = logging.getLogger(__name__)
BASE_URL = "https://api.apollo.io/v1"


class ApolloClient:
    def __init__(self, config: dict):
        self.api_key = config["apollo"]["api_key"]
        self.credits = CreditManager(config)
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
            "X-Api-Key": self.api_key,
        })

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def _post(self, endpoint: str, payload: dict) -> dict:
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
        """Search Apollo for people matching ICP criteria.

        Raises CreditLimitReached (via CreditManager) before the API call if
        the monthly limit is already reached. 1 credit logged per call.
        """
        self.credits.check_and_spend("apollo", purpose="lead_discovery")

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
                continue

            leads.append({
                "first_name":     p.get("first_name", ""),
                "last_name":      p.get("last_name", ""),
                "title":          p.get("title", ""),
                "email":          email,
                "linkedin_url":   p.get("linkedin_url", ""),
                "company_name":   org.get("name", ""),
                "domain":         org.get("website_url", ""),
                "industry":       org.get("industry", ""),
                "employee_count": str(org.get("num_employees", "")),
                "city":           p.get("city", ""),
                "country":        p.get("country", ""),
                "source":         "apollo",
                "email_verified": 0,
                "icp_score":      0,
                "status":         "new",
                "notes":          "",
            })

        logger.info("Apollo returned %d usable leads", len(leads))
        return leads

    def search_organizations(
        self,
        industries: list[str],
        locations: list[str],
        employee_ranges: list[str],
        limit: int = 25,
    ) -> list[dict]:
        """Phase 1 company discovery — returns company-level dicts without contacts.

        1 credit logged per call regardless of result count.
        """
        self.credits.check_and_spend("apollo", purpose="company_discovery")

        payload = {
            "organization_industry_tag_ids": industries,
            "organization_locations": locations,
            "organization_num_employees_ranges": employee_ranges,
            "per_page": min(limit, 25),
            "page": 1,
        }
        try:
            data = self._post("organizations/search", payload)
        except Exception as e:
            logger.error("Apollo org search failed: %s", e)
            return []

        orgs = data.get("organizations", [])
        companies = []
        for org in orgs:
            domain = (org.get("website_url") or "").replace("https://", "").replace("http://", "").split("/")[0]
            companies.append({
                "company_name":   org.get("name", ""),
                "domain":         domain.lower(),
                "industry":       org.get("industry", ""),
                "employee_count": str(org.get("num_employees", "")),
                "city":           (org.get("city") or ""),
                "country":        (org.get("country") or ""),
                "source":         "apollo",
            })

        logger.info("Apollo org search returned %d companies", len(companies))
        return companies

    def search_companies(self, domains: list[str]) -> list[dict]:
        """Look up company info by domain list."""
        self.credits.check_and_spend("apollo", purpose="company_lookup")

        payload = {"q_organization_domains": "\n".join(domains), "per_page": len(domains)}
        try:
            data = self._post("organizations/bulk_enrich", payload)
            return data.get("organizations", [])
        except Exception as e:
            logger.error("Apollo company lookup failed: %s", e)
            return []
