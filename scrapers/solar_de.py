"""BSW-Solar member directory scraper.

Target: https://www.solarwirtschaft.de/verbraucher/mitglieder/
~300 member companies — German solar industry association.

The page renders a filterable member list. We scroll through it and extract
every company name + external website link. Pagination is handled by
detecting and clicking the "next" button if present.
"""

import logging
import re
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

_URL = "https://www.solarwirtschaft.de/verbraucher/mitglieder/"

# Selectors tried in order for member list containers
_MEMBER_SELECTORS = [
    ".member-list .member",
    ".mitglieder-liste .mitglied",
    ".member-item",
    ".mitglied",
    "article.entry",
    ".views-row",          # Drupal
    "li.member",
    "tr.member-row",
    ".elementor-post",     # Elementor/WordPress
    ".wp-block-post",
]

# Selectors for the "next page" button
_NEXT_PAGE_SELECTORS = [
    "a.next",
    "a[rel='next']",
    ".pagination .next a",
    "a:has-text('Weiter')",
    "a:has-text('Nächste')",
    "a:has-text('›')",
    "a:has-text('»')",
]


class BSWSolarDeScraper(BaseScraper):
    """Scrape BSW-Solar member directory for German solar companies."""

    VERTICAL = "solar"
    GEO = "de"
    DIRECTORY_URL = _URL
    SOURCE_FILE = "scrapers.solar_de"

    def _do_scrape(self, page) -> list[dict]:
        if not self._navigate(page, _URL):
            return []

        self._delay(2, 4)

        results: list[dict] = []
        seen_domains: set[str] = set()
        page_num = 1

        while True:
            self.logger.info("BSW-Solar: scraping page %d", page_num)

            # Try scrolling to trigger lazy loads
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                self._delay(1, 2)
            except Exception:
                pass

            found_on_page = self._extract_from_page(page, seen_domains)
            results.extend(found_on_page)
            self.logger.info(
                "BSW-Solar page %d: found %d companies (total %d)",
                page_num, len(found_on_page), len(results),
            )

            # Try to go to next page
            next_url = self._find_next_page(page)
            if not next_url:
                break
            if not self._navigate(page, next_url):
                break
            self._delay(2, 5)
            page_num += 1

            if page_num > 30:  # Safety cap
                break

        return results

    def _extract_from_page(self, page, seen_domains: set[str]) -> list[dict]:
        """Extract member companies from the current page state."""
        results: list[dict] = []

        # Strategy 1: Try structured member-container selectors
        for sel in _MEMBER_SELECTORS:
            try:
                items = page.query_selector_all(sel)
                if not items:
                    continue
                self.logger.debug("BSW-Solar: matched selector '%s' (%d items)", sel, len(items))
                for item in items:
                    company, domain = self._extract_from_element(item)
                    if company and domain and domain not in seen_domains:
                        seen_domains.add(domain)
                        results.append(self._make_result(company, domain))
                if results:
                    return results
            except Exception as exc:
                self.logger.debug("Selector '%s' error: %s", sel, exc)

        # Strategy 2: Fall back to extracting all external links + adjacent text
        self.logger.debug("BSW-Solar: falling back to external-link extraction")
        links = self._extract_external_links(page)
        for link in links:
            domain = self._normalize_domain(link["href"])
            if not domain or domain in seen_domains:
                continue
            # Skip known non-member domains
            if any(skip in domain for skip in ("solarwirtschaft", "facebook", "twitter",
                                                "linkedin", "youtube", "instagram", "xing")):
                continue
            text = link["text"] or ""
            if text.startswith("http") or text.startswith("www."):
                text = domain
            name = text or domain
            if len(name) < 2 or len(name) > 100:
                continue
            seen_domains.add(domain)
            results.append(self._make_result(name, domain))

        return results

    def _extract_from_element(self, element) -> tuple[str, str]:
        """Return (company_name, website_url) from a member element, or ('', '')."""
        try:
            # Try to find company name in heading or strong tag
            name = ""
            for name_sel in ("h2", "h3", "h4", "strong", ".company-name", ".name", ".title"):
                el = element.query_selector(name_sel)
                if el:
                    text = (el.inner_text() or "").strip()
                    if text and len(text) > 1:
                        name = text
                        break
            if not name:
                name = (element.inner_text() or "").strip().split("\n")[0]

            # Find website link
            domain = ""
            for link in element.query_selector_all("a[href]"):
                href = (link.get_attribute("href") or "").strip()
                if href.startswith("http"):
                    # External link — likely the member website
                    d = self._normalize_domain(href)
                    if d and "solarwirtschaft" not in d:
                        domain = href
                        break

            return name[:120], domain
        except Exception:
            return "", ""

    def _find_next_page(self, page) -> str:
        """Return the URL of the next page, or empty string if none."""
        for sel in _NEXT_PAGE_SELECTORS:
            try:
                el = page.query_selector(sel)
                if el:
                    href = el.get_attribute("href") or ""
                    if href and href not in (page.url, "#", "javascript:void(0)"):
                        return href if href.startswith("http") else f"https://www.solarwirtschaft.de{href}"
            except Exception:
                continue
        return ""
