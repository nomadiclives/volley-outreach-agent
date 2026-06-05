"""FMB (Federation of Master Builders) member directory scraper.

Target: https://www.fmb.org.uk/find-a-builder/
~8,000 member companies — UK home improvement / construction.

The FMB site uses a postcode/trade search form backed by an API endpoint.
We use two strategies in sequence:

  Strategy A — API endpoint:
    POST to /api/member-search (or similar) with broad parameters.
    Iterate through pages until exhausted.

  Strategy B — Form-based search:
    Navigate to the search page, submit a wildcard/broad search for each
    major UK city, collect unique results across all searches.

Both strategies deduplicate by domain to avoid counting the same company twice.
"""

import logging
import json
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.fmb.org.uk"
_SEARCH_URL = "https://www.fmb.org.uk/find-a-builder.html"

# Major UK cities to iterate through for the form-based fallback
_UK_CITIES = [
    "London", "Manchester", "Birmingham", "Leeds", "Glasgow",
    "Liverpool", "Bristol", "Sheffield", "Edinburgh", "Cardiff",
    "Leicester", "Coventry", "Bradford", "Nottingham", "Newcastle",
    "Southampton", "Portsmouth", "Brighton", "Reading", "Derby",
    "Wolverhampton", "Stoke-on-Trent", "Plymouth", "Exeter", "Oxford",
    "Cambridge", "Norwich", "Ipswich", "Peterborough", "Milton Keynes",
]

# Trade/category keywords for the FMB search
_TRADE_KEYWORDS = [
    "general builder",
    "roofing",
    "extension",
    "loft conversion",
    "kitchen",
]

# Result card selectors
_RESULT_SELECTORS = [
    ".member-result",
    ".finder-result",
    ".search-result",
    ".company-result",
    ".result-card",
    ".builder-card",
    ".member-card",
    "article.result",
    ".fmb-member",
]

_SKIP_DOMAINS = frozenset({
    "fmb.org.uk", "facebook.com", "twitter.com", "x.com",
    "linkedin.com", "instagram.com", "google.com",
})


class FMBScraper(BaseScraper):
    """Scrape FMB member directory for UK home improvement companies."""

    VERTICAL = "home_improvement"
    GEO = "uk"
    DIRECTORY_URL = _SEARCH_URL
    SOURCE_FILE = "scrapers.home_improvement_uk"

    def _do_scrape(self, page) -> list[dict]:
        results: list[dict] = []
        seen_domains: set[str] = set()

        # City-based searches — FMB is a search-only directory (no flat member list)
        self.logger.info("FMB: running city-based searches")
        for city in _UK_CITIES:
            if len(results) >= 500:
                break
            city_results = self._search_city(page, city, seen_domains)
            results.extend(city_results)
            self.logger.info(
                "FMB city '%s': %d companies (total %d)", city, len(city_results), len(results)
            )
            self._delay(2, 4)

        return results

    def _search_city(self, page, city: str, seen_domains: set[str]) -> list[dict]:
        """Submit a search for a city and extract results."""
        results: list[dict] = []

        search_url = f"{_SEARCH_URL}?location={city.replace(' ', '+')}&trade=builder"
        if not self._navigate(page, search_url):
            return results
        self._delay(2, 3)

        # Try to wait for results to load
        try:
            page.wait_for_selector(
                ", ".join(_RESULT_SELECTORS[:4]),
                timeout=8_000,
            )
        except Exception:
            pass  # Page may not use these selectors — fall through to generic extraction

        # Extract results from structured selectors
        for sel in _RESULT_SELECTORS:
            try:
                items = page.query_selector_all(sel)
                if not items:
                    continue
                self.logger.debug("FMB: matched selector '%s' (%d items) for %s", sel, len(items), city)
                for item in items:
                    company, url = self._extract_from_element(item)
                    if not company:
                        continue
                    domain = self._normalize_domain(url) if url else ""
                    key = domain or company.lower()
                    if key in seen_domains:
                        continue
                    seen_domains.add(key)
                    results.append(self._make_result(company, url or "", search_url))
                if results:
                    return results
            except Exception as exc:
                self.logger.debug("FMB selector '%s' error: %s", sel, exc)

        # Fall back to extracting external links from the page
        for link in self._extract_external_links(page):
            domain = self._normalize_domain(link["href"])
            if not domain or domain in seen_domains:
                continue
            if any(skip in domain for skip in _SKIP_DOMAINS):
                continue
            text = link["text"] or ""
            if text.startswith("http") or text.startswith("www."):
                text = domain
            name = text or domain
            if not name or len(name) < 3 or len(name) > 120:
                continue
            # Skip nav/footer links by checking link text heuristics
            if name.lower() in ("website", "visit", "click here", "more info", "read more"):
                continue
            seen_domains.add(domain)
            results.append(self._make_result(name, link["href"], search_url))

        return results

    def _extract_from_element(self, element) -> tuple[str, str]:
        try:
            name = ""
            for name_sel in ("h2", "h3", "h4", "strong", ".company-name",
                             ".member-name", ".name", ".builder-name"):
                el = element.query_selector(name_sel)
                if el:
                    text = (el.inner_text() or "").strip()
                    if text and len(text) > 1:
                        name = text
                        break
            if not name:
                name = (element.inner_text() or "").strip().split("\n")[0]

            url = ""
            for link in element.query_selector_all("a[href]"):
                href = (link.get_attribute("href") or "").strip()
                if href.startswith("http"):
                    d = self._normalize_domain(href)
                    if d and "fmb.org" not in d:
                        url = href
                        break

            return name[:120], url
        except Exception:
            return "", ""
