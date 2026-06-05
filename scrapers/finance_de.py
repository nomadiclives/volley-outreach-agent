"""BdB (Bankenverband / Association of German Banks) member directory scraper.

Target: https://bankenverband.de/mitglieder/
~200 member banks — German private banking sector.

The page typically renders a list of member banks, each with a name and
an external website link. We extract all of these, handling any
letter-based (A–Z) filtering by iterating if needed.
"""

import logging
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

_BASE_URL = "https://bankenverband.de"
_MEMBERS_URL = "https://bankenverband.de/ueber-uns/mitglieder"

_MEMBER_SELECTORS = [
    ".mitglieder-list .mitglied",
    ".members-list .member",
    ".member-item",
    ".mitglied",
    ".bank-item",
    "article.member",
    ".views-row",
    "li.member",
    "tr.mitglied",
    ".entry",
    "ul.members li",
    "table.members tr",
]

_SKIP_DOMAINS = frozenset({
    "bankenverband.de", "facebook.com", "twitter.com", "x.com",
    "linkedin.com", "xing.com", "youtube.com", "instagram.com",
    "bundesbank.de", "bafin.de",
})

# German alphabet letters for letter-filter pagination (A–Z)
import string
_LETTERS = list(string.ascii_uppercase)


class BdBScraper(BaseScraper):
    """Scrape BdB member directory for German banking/finance companies."""

    VERTICAL = "finance"
    GEO = "de"
    DIRECTORY_URL = _MEMBERS_URL
    SOURCE_FILE = "scrapers.finance_de"

    def _do_scrape(self, page) -> list[dict]:
        results: list[dict] = []
        seen_domains: set[str] = set()

        # First: load the main members page
        if not self._navigate(page, _MEMBERS_URL):
            return results
        self._delay(2, 4)

        # Scroll to trigger lazy loading
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            self._delay(1, 2)
        except Exception:
            pass

        # Try to extract from main page
        main_results = self._extract_from_page(page, seen_domains, _MEMBERS_URL)
        results.extend(main_results)
        self.logger.info("BdB main page: %d companies", len(main_results))

        # If we got very few results, check for letter-based filtering
        if len(results) < 20:
            self.logger.info("BdB: few results on main page, trying letter-filter URLs")
            for letter in _LETTERS:
                if len(results) >= 300:
                    break
                # Try Drupal view filter patterns
                for url_pattern in (
                    f"{_MEMBERS_URL}?field_alpha={letter}",
                    f"{_MEMBERS_URL}?filter={letter}",
                    f"{_MEMBERS_URL}?letter={letter}",
                ):
                    if not self._navigate(page, url_pattern):
                        continue
                    self._delay(1, 3)
                    letter_results = self._extract_from_page(page, seen_domains, url_pattern)
                    results.extend(letter_results)
                    if letter_results:
                        self.logger.debug("BdB letter '%s': %d companies", letter, len(letter_results))
                        break

        # Pagination fallback
        page_num = 2
        while len(results) < 300 and page_num <= 20:
            paginated_url = f"{_MEMBERS_URL}?page={page_num}"
            if not self._navigate(page, paginated_url):
                break
            self._delay(1, 3)
            page_results = self._extract_from_page(page, seen_domains, paginated_url)
            if not page_results:
                break
            results.extend(page_results)
            self.logger.debug("BdB page %d: %d companies (total %d)", page_num, len(page_results), len(results))
            page_num += 1

        return results

    def _extract_from_page(self, page, seen_domains: set[str], source_url: str) -> list[dict]:
        results: list[dict] = []

        # Strategy 1: structured member selectors
        for sel in _MEMBER_SELECTORS:
            try:
                items = page.query_selector_all(sel)
                if not items:
                    continue
                self.logger.debug("BdB: matched selector '%s' (%d items)", sel, len(items))
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
                self.logger.debug("BdB selector '%s' error: %s", sel, exc)

        # Strategy 2: external links fallback
        self.logger.debug("BdB: falling back to external-link extraction on %s", source_url)
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
            if not name or len(name) < 2 or len(name) > 120:
                continue
            seen_domains.add(domain)
            results.append(self._make_result(name, link["href"], source_url))

        return results

    def _extract_from_element(self, element) -> tuple[str, str]:
        try:
            name = ""
            for name_sel in ("h2", "h3", "h4", "strong", ".bank-name",
                             ".company-name", ".name", ".title", "a"):
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
                    if d and "bankenverband" not in d:
                        url = href
                        break

            return name[:120], url
        except Exception:
            return "", ""
