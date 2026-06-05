"""People Data Labs API client — company + contact enrichment.

Two methods:
    find_person(name, company, domain)   — Person Search API (POST)
    enrich_company(domain)               — Company Enrich API (GET)

Credit gate: every call goes through CreditManager.check_and_spend("people_data_labs")
before the request. Hard stop at 100 lookups/month.

PDL docs: https://docs.peopledatalabs.com/docs/person-search-api
         https://docs.peopledatalabs.com/docs/company-enrichment-api
"""

import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from core.credit_manager import CreditManager, CreditLimitReached

logger = logging.getLogger(__name__)

PERSON_SEARCH_URL = "https://api.peopledatalabs.com/v5/person/search"
COMPANY_ENRICH_URL = "https://api.peopledatalabs.com/v5/company/enrich"


class PeopleDataLabsClient:
    def __init__(self, config: dict):
        self.api_key = config.get("people_data_labs", {}).get("api_key", "")
        self.credits = CreditManager(config)
        self.session = requests.Session()
        self.session.headers.update({
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        })

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6))
    def _post(self, url: str, payload: dict) -> dict:
        resp = self.session.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=6))
    def _get(self, url: str, params: dict) -> dict:
        params["api_key"] = self.api_key
        resp = self.session.get(url, params=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def _confidence_score(self, person: dict, domain: str) -> int:
        """Derive a 0–100 confidence score from a PDL person record.

        Logic mirrors how Hunter.io's confidence score is used in the rest of
        the codebase — this field gates whether a lead is accepted (≥70).
        """
        work_email = (person.get("work_email") or "").lower()
        emails = person.get("emails") or []
        all_addresses = [
            (e.get("address") or "").lower()
            for e in emails
            if e.get("address")
        ]

        if work_email and domain and work_email.endswith(f"@{domain.lstrip('www.')}"):
            # Work email confirmed on the exact company domain — highest confidence
            return 90

        if work_email:
            # Work email found but domain mismatch or unknown
            return 80

        # Any professional/current email found
        professional_email = next(
            (e["address"].lower() for e in emails
             if e.get("type") in ("current_professional", "professional", "work")),
            None,
        )
        if professional_email:
            return 75

        if all_addresses:
            return 65

        return 0

    def find_person(
        self,
        name: str = "",
        company: str = "",
        domain: str = "",
        target_titles: list[str] | None = None,
    ) -> list[dict]:
        """Search PDL for contacts at a given company.

        Spends 1 credit per call regardless of result count.
        Returns up to 3 contacts matching target_titles, or [] on failure.
        Confidence threshold: returns only results with score ≥ 70.
        """
        if not self.api_key:
            logger.debug("PDL API key not set — skipping")
            return []
        if not domain and not company:
            logger.debug("PDL find_person called with neither domain nor company — skipping")
            return []

        self.credits.check_and_spend("people_data_labs", purpose="contact_resolution")

        # Build Elasticsearch bool query
        must_clauses: list[dict] = []
        if domain:
            clean_domain = domain.lstrip("www.").lower()
            must_clauses.append({"term": {"job_company_website": clean_domain}})
        if company and not domain:
            must_clauses.append({"match": {"job_company_name": company}})
        if name:
            must_clauses.append({"match": {"full_name": name}})
        if target_titles:
            must_clauses.append({
                "bool": {
                    "should": [
                        {"match": {"job_title": t}} for t in target_titles[:10]
                    ],
                    "minimum_should_match": 1,
                }
            })

        payload = {
            "query": {"bool": {"must": must_clauses}},
            "size": 5,
            "dataset": "all",
        }

        try:
            data = self._post(PERSON_SEARCH_URL, payload)
        except Exception as e:
            logger.error("PDL person search failed for domain=%s company=%s: %s", domain, company, e)
            return []

        if data.get("status") != 200:
            logger.warning("PDL person search non-200 for %s: %s", domain, data.get("error"))
            return []

        raw_people = data.get("data") or []
        results: list[dict] = []

        for person in raw_people:
            work_email = (person.get("work_email") or "").strip()
            emails = person.get("emails") or []

            # Pick the best available email address
            email = work_email
            if not email:
                email = next(
                    (e["address"].strip() for e in emails
                     if e.get("type") in ("current_professional", "professional", "work")
                     and e.get("address")),
                    None,
                )
            if not email:
                email = next(
                    (e["address"].strip() for e in emails if e.get("address")),
                    None,
                )

            if not email:
                continue

            confidence = self._confidence_score(person, domain)
            if confidence < 70:
                continue

            title = (
                person.get("job_title")
                or person.get("inferred_salary")  # sometimes miskeyed
                or ""
            )
            # Reject if title filtering is requested and this person doesn't match
            if target_titles and title and not any(
                t.lower() in title.lower() for t in target_titles
            ):
                continue

            results.append({
                "first_name":        person.get("first_name") or "",
                "last_name":         person.get("last_name") or "",
                "title":             title,
                "email":             email,
                "hunter_confidence": confidence,
                "email_verified":    1 if work_email and confidence >= 90 else 0,
                "linkedin_url":      person.get("linkedin_url") or "",
                "source":            "people_data_labs",
            })

        if results:
            logger.info("PDL found %d contacts at %s", len(results), domain or company)
        else:
            logger.debug("PDL: no usable contacts at %s", domain or company)

        return results[:3]

    def enrich_company(self, domain: str) -> dict | None:
        """Enrich a company record from its domain.

        Spends 1 credit. Returns a dict with company fields, or None on failure.
        """
        if not self.api_key:
            logger.debug("PDL API key not set — skipping company enrich")
            return None
        if not domain:
            return None

        self.credits.check_and_spend("people_data_labs", purpose="company_enrichment")

        try:
            data = self._get(COMPANY_ENRICH_URL, {
                "website": domain.lstrip("www.").lower(),
                "pretty": "false",
            })
        except Exception as e:
            logger.error("PDL company enrich failed for %s: %s", domain, e)
            return None

        if data.get("status") != 200:
            logger.warning("PDL company enrich non-200 for %s: %s", domain, data.get("error"))
            return None

        raw_size = data.get("size") or ""
        employee_count = _parse_employee_count(raw_size)

        result = {
            "company_name":   data.get("name") or "",
            "domain":         domain,
            "industry":       data.get("industry") or "",
            "employee_count": employee_count,
            "city":           data.get("location_locality") or "",
            "country":        data.get("location_country") or "",
            "linkedin_url":   data.get("linkedin_url") or "",
        }
        logger.info("PDL company enrich [%s]: %s", domain, result.get("company_name"))
        return result


def _parse_employee_count(size_range: str) -> str:
    """Normalise PDL size ranges like '51-200' into a human-readable string."""
    size_range = (size_range or "").strip()
    if not size_range:
        return ""
    # PDL returns strings like "11-50", "51-200", "201-500", "1001-5000"
    # Keep as-is — lead_enricher.py parses ranges fine.
    return size_range
