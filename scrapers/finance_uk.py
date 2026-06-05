"""NACFB (National Association of Commercial Finance Brokers) member directory scraper.

Target: https://www.nacfb.org/find-a-broker/
~2,000 member broker companies — UK commercial finance.

The NACFB broker finder uses a search interface. We iterate through
specialist area filters (product types) to collect a broad set of members.
Results are deduplicated by domain across all searches.
"""

import logging
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.nacfb.org"
_SEARCH_URL = "https://www.nacfb.org/find-a-broker/"

# NACFB specialist area categories to iterate through
_SPECIALIST_AREAS = [
    "commercial-mortgage",
    "development-finance",
    "bridging-finance",
    "asset-finance",
    "invoice-finance",
    "business-loan",
    "trade-finance",
    "property-finance",
]

_RESULT_SELECTORS = [
    ".broker-result",
    ".member-result",
    ".search-result",
    ".broker-card",
    ".member-card",
    ".result-item",
    "article.broker",
    "article.member",
    ".nacfb-member",
    ".finder-result",
]

_SKIP_DOMAINS = frozenset({
    "nacfb.org", "facebook.com", "twitter.com", "x.com",
    "linkedin.com", "instagram.com", "google.com",
})


class NACFBScraper(BaseScraper):
    """Scrape NACFB member directory for UK commercial finance brokers."""

    VERTICAL = "finance"
    GEO = "uk"
    DIRECTORY_URL = _SEARCH_URL
    SOURCE_FILE = "scrapers.finance_uk"

    def _do_scrape(self, page) -> list[dict]:
        results: list[dict] = []
        seen_domains: set[str] = set()

        # First: try the main search page with an empty/broad query
        self.logger.info("NACFB: trying broad search")
        broad = self._search_with_query(page, "", seen_domains)
        results.extend(broad)
        self.logger.info("NACFB broad search: %d companies", len(broad))
        self._delay(2, 4)

        # Then iterate through specialist area filters
        for area in _SPECIALIST_AREAS:
            if len(results) >= 500:
                break
            self.logger.info("NACFB: searching specialist area '%s'", area)
            area_results = self._search_with_query(page, area, seen_domains)
            results.extend(area_results)
            self.logger.info(
                "NACFB area '%s': %d companies (total %d)", area, len(area_results), len(results)
            )
            self._delay(2, 4)

        return results

    def _search_with_query(self, page, query: str, seen_domains: set[str]) -> list[dict]:
        """Submit one search and paginate through all result pages."""
        results: list[dict] = []
        page_num = 1

        url = _SEARCH_URL
        if query:
            url = f"{_SEARCH_URL}?specialist_area={query}"

        if not self._navigate(page, url):
            return results
        self._delay(2, 3)

        while True:
            try:
                page.wait_for_selector(
                    ", ".join(_RESULT_SELECTORS[:4]),
                    timeout=8_000,
                )
            except Exception:
                pass

            page_results = self._extract_from_page(page, seen_domains, url)
            results.extend(page_results)
            self.logger.debug(
                "NACFB query='%s' page %d: %d results", query, page_num, len(page_results)
            )

            # Follow pagination
            next_url = self._find_next_page(page)
            if not next_url:
                break
            if not self._navigate(page, next_url):
                break
            self._delay(2, 4)
            page_num += 1
            if page_num > 50:
                break

        return results

    def _extract_from_page(self, page, seen_domains: set[str], source_url: str) -> list[dict]:
        results: list[dict] = []

        for sel in _RESULT_SELECTORS:
            try:
                items = page.query_selector_all(sel)
                if not items:
                    continue
                self.logger.debug("NACFB: matched selector '%s' (%d items)", sel, len(items))
                for item in items:
                    company, url = self._extract_from_element(item)
                    if not company:
                        continue
                    domain = self._normalize_domain(url) if url else ""
                    key = domain or company.lower()
                    if key in seen_domains:
                        continue
                    seen_domains.add(key)
                    results.append(self._make_result(company, url or "", source_url))
                if results:
                    return results
            except Exception as exc:
                self.logger.debug("NACFB selector '%s' error: %s", sel, exc)

        # Fallback: external links
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
            if name.lower() in ("website", "visit", "click here", "more info", "read more", "www"):
                continue
            seen_domains.add(domain)
            results.append(self._make_result(name, link["href"], source_url))

        return results

    def _extract_from_element(self, element) -> tuple[str, str]:
        try:
            name = ""
            for name_sel in ("h2", "h3", "h4", "strong", ".company-name",
                             ".broker-name", ".member-name", ".name"):
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
                    if d and "nacfb.org" not in d:
                        url = href
                        break

            return name[:120], url
        except Exception:
            return "", ""

    def _find_next_page(self, page) -> str:
        for sel in ("a.next", "a[rel='next']", ".pagination .next a",
                    "a:has-text('Next')", "a:has-text('›')", "a:has-text('»')"):
            try:
                el = page.query_selector(sel)
                if el:
                    href = el.get_attribute("href") or ""
                    if href and href not in (page.url, "#", "javascript:void(0)"):
                        return href if href.startswith("http") else f"{_BASE_URL}{href}"
            except Exception:
                continue
        return ""
