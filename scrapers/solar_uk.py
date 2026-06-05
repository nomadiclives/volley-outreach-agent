"""Solar Energy UK member directory scraper.

Target: https://solarenergyuk.org/membership/our-members/
~150 member companies — UK solar trade association.

The page typically renders a grid of member logos/cards. We extract
company names and external website links from each card. If the page
uses lazy loading, we scroll to reveal all cards before extracting.
"""

import logging
from scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)

_URL = "https://solarenergyuk.org/member-directory/"

# WordPress custom post type archive — articles render after JS executes
_MEMBER_SELECTORS = [
    "article.type-member",
    "article.post-member",
    ".archives-members article",
    ".members-archive article",
    "article.member",
    ".member-card",
    ".member-item",
    ".wp-block-post",
]

_NEXT_PAGE_SELECTORS = [
    "a[rel='next']",
    "a.next",
    ".pagination .next a",
    "a:has-text('Next')",
    "a:has-text('›')",
    ".nav-links .next",
]

_SKIP_DOMAINS = frozenset({
    "solarenergyuk.org", "facebook.com", "twitter.com", "x.com",
    "linkedin.com", "youtube.com", "instagram.com",
})


class SolarEnergyUKScraper(BaseScraper):
    """Scrape Solar Energy UK member directory for UK solar companies."""

    VERTICAL = "solar"
    GEO = "uk"
    DIRECTORY_URL = _URL
    SOURCE_FILE = "scrapers.solar_uk"

    def _do_scrape(self, page) -> list[dict]:
        if not self._navigate(page, _URL):
            return []

        # Wait for JS to render member cards
        try:
            page.wait_for_selector(", ".join(_MEMBER_SELECTORS[:4]), timeout=10_000)
        except Exception:
            pass
        self._delay(2, 3)

        results: list[dict] = []
        seen_domains: set[str] = set()
        page_num = 1

        while True:
            self.logger.info("Solar Energy UK: scraping page %d", page_num)

            # Scroll to bottom to trigger lazy loading
            try:
                for _ in range(3):
                    page.evaluate("window.scrollBy(0, window.innerHeight)")
                    self._delay(0.5, 1.0)
            except Exception:
                pass

            found = self._extract_from_page(page, seen_domains)
            results.extend(found)
            self.logger.info(
                "Solar Energy UK page %d: %d companies (total %d)",
                page_num, len(found), len(results),
            )

            # Stop paginating if this page yielded nothing new (dedup exhausted)
            if not found:
                break
            next_url = self._find_next_page(page)
            if not next_url:
                break
            if not self._navigate(page, next_url):
                break
            self._delay(2, 5)
            page_num += 1
            if page_num > 20:
                break

        return results

    def _extract_from_page(self, page, seen_domains: set[str]) -> list[dict]:
        results: list[dict] = []

        # Strategy 1: structured member containers
        for sel in _MEMBER_SELECTORS:
            try:
                items = page.query_selector_all(sel)
                if not items:
                    continue
                self.logger.debug("Solar UK: matched selector '%s' (%d items)", sel, len(items))
                for item in items:
                    company, url = self._extract_from_element(item)
                    if not company:
                        continue
                    domain = self._normalize_domain(url) if url else ""
                    # Use company name as domain placeholder if no URL found
                    key = domain or company.lower()
                    if key in seen_domains:
                        continue
                    seen_domains.add(key)
                    results.append(self._make_result(company, url or ""))
                if results:
                    return results
            except Exception as exc:
                self.logger.debug("Selector '%s' error: %s", sel, exc)

        # Strategy 2: all external links on page
        self.logger.debug("Solar UK: falling back to external-link extraction")
        for link in self._extract_external_links(page):
            domain = self._normalize_domain(link["href"])
            if not domain or domain in seen_domains:
                continue
            if any(skip in domain for skip in _SKIP_DOMAINS):
                continue
            text = link["text"] or ""
            # Discard entries where the link text IS the URL — use domain as name instead
            if text.startswith("http") or text.startswith("www."):
                text = domain
            name = text or domain
            if not name or len(name) < 2 or len(name) > 120:
                continue
            seen_domains.add(domain)
            results.append(self._make_result(name, link["href"]))

        return results

    def _extract_from_element(self, element) -> tuple[str, str]:
        try:
            name = ""
            for name_sel in ("h2", "h3", "h4", "strong", ".company-name",
                             ".member-name", ".name", "img[alt]"):
                el = element.query_selector(name_sel)
                if el:
                    text = (el.get_attribute("alt") or el.inner_text() or "").strip()
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
                    if d and "solarenergyuk" not in d:
                        url = href
                        break

            return name[:120], url
        except Exception:
            return "", ""

    def _find_next_page(self, page) -> str:
        # Try link rel=next in <head> first (most reliable for WP archives)
        try:
            next_href = page.evaluate(
                "() => { const l = document.querySelector('link[rel=\"next\"]'); return l ? l.href : ''; }"
            )
            if next_href and next_href != page.url:
                return next_href
        except Exception:
            pass
        for sel in _NEXT_PAGE_SELECTORS:
            try:
                el = page.query_selector(sel)
                if el:
                    href = el.get_attribute("href") or ""
                    if href and href not in (page.url, "#", "javascript:void(0)"):
                        return href if href.startswith("http") else f"https://solarenergyuk.org{href}"
            except Exception:
                continue
        return ""
