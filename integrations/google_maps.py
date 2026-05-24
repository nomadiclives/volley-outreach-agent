"""Google Maps Places API client for local/SMB business discovery."""

import logging
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)
PLACES_URL = "https://maps.googleapis.com/maps/api/place"


class GoogleMapsClient:
    def __init__(self, config: dict):
        self.api_key = config["google"].get("maps_api_key", "")
        if not self.api_key:
            logger.warning("Google Maps API key not set — searches will be skipped")

    @retry(stop=stop_after_attempt(2), wait=wait_exponential(min=1, max=5))
    def text_search(self, query: str, location: str = "", limit: int = 20) -> list[dict]:
        """Search for businesses by query string and location."""
        if not self.api_key:
            return []

        params = {
            "query": f"{query} {location}".strip(),
            "key": self.api_key,
            "fields": "name,website,formatted_address,international_phone_number,types",
        }
        try:
            resp = requests.get(f"{PLACES_URL}/textsearch/json", params=params, timeout=15)
            resp.raise_for_status()
            results = resp.json().get("results", [])[:limit]
        except Exception as e:
            logger.error("Google Maps search failed: %s", e)
            return []

        leads = []
        for r in results:
            domain = ""
            website = r.get("website", "")
            if website:
                domain = website.replace("https://", "").replace("http://", "").split("/")[0]

            leads.append({
                "company_name": r.get("name", ""),
                "domain": domain,
                "industry": ", ".join(r.get("types", [])[:3]),
                "city": location,
                "country": "",
                "first_name": "",
                "last_name": "",
                "title": "",
                "email": "",
                "linkedin_url": "",
                "employee_count": "",
                "source": "google_maps",
                "email_verified": 0,
                "icp_score": 0,
                "status": "new",
                "notes": f"Address: {r.get('formatted_address', '')}",
            })

        logger.info("Google Maps returned %d places for '%s'", len(leads), query)
        return leads
