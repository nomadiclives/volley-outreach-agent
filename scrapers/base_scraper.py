"""Shared Playwright setup, rate limiting, retry logic, and caching for directory scrapers.

Each subclass sets VERTICAL, GEO, DIRECTORY_URL, SOURCE_FILE and implements _do_scrape(page).
Calling run() checks the 7-day cache before launching Playwright; results are stored
in the directory_companies SQLite table.
"""

import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_CACHE_DAYS = 7

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]


class BaseScraper(ABC):
    """Abstract base for vertical directory scrapers.

    Subclasses must define class attributes:
        VERTICAL      — e.g. "solar", "home_improvement", "finance"
        GEO           — ISO-style lowercase: "de", "uk"
        DIRECTORY_URL — entry point URL for the directory
        SOURCE_FILE   — __name__ of the subclass module (used as cache key)
    """

    VERTICAL: str = ""
    GEO: str = ""
    DIRECTORY_URL: str = ""
    SOURCE_FILE: str = ""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self, dry_run: bool = False) -> list[dict]:
        """Return company dicts for this directory.

        Serves from DB cache if scraped within _CACHE_DAYS days. Otherwise
        launches Playwright, scrapes, stores, and returns fresh results.
        """
        from core.database import get_directory_last_scraped, get_directory_companies, bulk_insert_directory_companies

        last_scraped = get_directory_last_scraped(self.SOURCE_FILE)
        if last_scraped and (datetime.utcnow() - last_scraped) < timedelta(days=_CACHE_DAYS):
            cached = get_directory_companies(
                vertical=self.VERTICAL,
                country=self.GEO.upper(),
            )
            self.logger.info(
                "Cache hit (%s): %d companies, last scraped %s",
                self.SOURCE_FILE, len(cached), last_scraped.date(),
            )
            return cached

        self.logger.info("Scraping %s (cache stale or empty)", self.DIRECTORY_URL)
        results = self._scrape_with_playwright()

        if results and not dry_run:
            count = bulk_insert_directory_companies(results)
            self.logger.info(
                "%s: stored %d / %d companies", self.SOURCE_FILE, count, len(results)
            )
        elif dry_run:
            self.logger.info("[DRY RUN] %s: would store %d companies", self.SOURCE_FILE, len(results))

        return results

    # ── Playwright runner ─────────────────────────────────────────────────────

    def _scrape_with_playwright(self) -> list[dict]:
        """Launch a headless Chromium session and call _do_scrape(page)."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.logger.error("Playwright not installed — cannot run directory scraper")
            return []

        results: list[dict] = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(
                    user_agent=random.choice(_USER_AGENTS),
                    locale="en-GB",
                    viewport={"width": 1280, "height": 900},
                )
                page = ctx.new_page()
                # Skip image/font/media downloads to speed up page loads
                page.route(
                    "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf,eot,mp4,webm}",
                    lambda route: route.abort(),
                )
                try:
                    results = self._do_scrape(page)
                finally:
                    browser.close()
        except Exception as exc:
            self.logger.error("Playwright session failed for %s: %s", self.DIRECTORY_URL, exc)

        self.logger.info(
            "%s scraped %d companies from %s",
            self.__class__.__name__, len(results), self.DIRECTORY_URL,
        )
        return results

    # ── Shared helpers ────────────────────────────────────────────────────────

    def _delay(self, min_s: float = 2.0, max_s: float = 5.0):
        """Random delay between page interactions to avoid bot detection."""
        time.sleep(random.uniform(min_s, max_s))

    def _navigate(self, page, url: str, timeout: int = 30_000) -> bool:
        """Navigate to url with up to 3 retries. Returns True on success."""
        for attempt in range(1, 4):
            try:
                page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                return True
            except Exception as exc:
                self.logger.warning(
                    "Navigate attempt %d/3 to %s failed: %s", attempt, url, exc
                )
                if attempt < 3:
                    self._delay(3, 7)
        return False

    def _normalize_domain(self, raw_url: str) -> str:
        """Strip scheme, www, and path from a URL, returning a bare domain."""
        if not raw_url:
            return ""
        raw = raw_url.strip()
        if "://" not in raw:
            raw = "https://" + raw
        try:
            netloc = urlparse(raw).netloc.lower()
            # Strip leading www.
            if netloc.startswith("www."):
                netloc = netloc[4:]
            return netloc
        except Exception:
            return ""

    def _make_result(self, company_name: str, domain_or_url: str, source_url: str = "") -> dict:
        """Build a standard output dict for one company."""
        return {
            "company_name": company_name.strip(),
            "domain":       self._normalize_domain(domain_or_url),
            "country":      self.GEO.upper(),
            "vertical":     self.VERTICAL,
            "source_url":   source_url or self.DIRECTORY_URL,
            "source_file":  self.SOURCE_FILE,
        }

    def _extract_external_links(self, page) -> list[dict]:
        """JS-evaluated helper: return all external <a href> + link text pairs on current page."""
        try:
            return page.evaluate("""
                () => {
                    const results = [];
                    const seen = new Set();
                    const host = location.hostname;
                    for (const a of document.querySelectorAll('a[href]')) {
                        const href = (a.href || '').trim();
                        if (!href.startsWith('http')) continue;
                        try {
                            const u = new URL(href);
                            if (u.hostname === host || u.hostname.endsWith('.' + host)) continue;
                        } catch(e) { continue; }
                        if (seen.has(href)) continue;
                        seen.add(href);
                        const text = (a.innerText || a.textContent || '').trim().replace(/\\s+/g, ' ');
                        results.push({ href, text });
                    }
                    return results;
                }
            """) or []
        except Exception as exc:
            self.logger.debug("_extract_external_links failed: %s", exc)
            return []

    # ── Abstract method ───────────────────────────────────────────────────────

    @abstractmethod
    def _do_scrape(self, page) -> list[dict]:
        """Scrape the directory and return a list of company dicts.

        Use self._make_result(company_name, url, source_url) to build each dict.
        Call self._delay() between page navigations.
        Call self._navigate(page, url) for retry-safe navigation.
        """
        ...
