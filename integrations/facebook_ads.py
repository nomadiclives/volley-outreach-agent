"""Facebook Ad Library integration — public scraper via Playwright.

Two methods on FacebookAdsClient:

  search_advertisers(vertical, limit):
      Search facebook.com/ads/library for active advertisers by keyword.
      Returns list of {company_name, domain, fb_page_slug}.
      Used in Phase 1 company discovery (agents/lead_finder.py).

  page_transparency_check(fb_slug):
      Fetch facebook.com/{slug}/about_profile_transparency and check for
      'This page is currently running ads'. Returns bool.
      Used in agents/buying_signal_checker.py for leads scoring > 40.

No API key required — both methods scrape public pages.
Respects 2–5 s random delays between Playwright actions.
"""

import logging
import random
import re
import time
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

_AD_LIBRARY_BASE = "https://www.facebook.com/ads/library/"
_DEFAULT_TIMEOUT_MS = 20_000

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# FB path segments that are navigation / policy pages, not company pages
_SLUG_BLOCKLIST = frozenset({
    "ads", "help", "policies", "privacy", "legal", "about", "business",
    "login", "signup", "sharer", "share", "dialog", "profile.php",
    "pages", "groups", "events", "watch", "marketplace", "gaming",
    "tos", "terms", "settings", "notifications", "recover",
})

# Cookie-consent button selectors to try before interacting with the page
_COOKIE_SELECTORS = (
    '[data-cookiebanner="accept_button"]',
    'button[title="Accept all"]',
    '[aria-label="Allow all cookies"]',
    '[aria-label="Accept all"]',
)


def _launch_page(playwright):
    """Return (browser, page) for a headless Chromium session."""
    browser = playwright.chromium.launch(headless=True)
    ctx = browser.new_context(user_agent=_UA)
    return browser, ctx.new_page()


class FacebookAdsClient:
    """Scrapes public Facebook Ad Library and Page Transparency pages."""

    def __init__(self, config: dict):
        fb_cfg = (config or {}).get("facebook", {})
        self._timeout = fb_cfg.get("page_timeout_ms", _DEFAULT_TIMEOUT_MS)

    # ── Method 1: Ad Library search ───────────────────────────────────────────

    def search_advertisers(self, vertical: str, limit: int = 10) -> list[dict]:
        """Search the Facebook Ad Library for active advertisers in a vertical.

        Returns list of dicts:
            company_name  — advertiser page name
            domain        — website domain if detected, else empty string
            fb_page_slug  — FB page slug (usable for page_transparency_check)

        Returns [] if Playwright is unavailable, if FB redirects to login,
        or if any other error occurs.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright not installed — skipping FB Ad Library search")
            return []

        params = {
            "active_status": "active",
            "ad_type": "all",
            "country": "ALL",
            "q": vertical,
            "search_type": "keyword_unordered",
            "media_type": "all",
        }
        url = _AD_LIBRARY_BASE + "?" + urlencode(params)
        results: list[dict] = []

        try:
            with sync_playwright() as p:
                browser, page = _launch_page(p)
                try:
                    page.goto(url, timeout=self._timeout, wait_until="domcontentloaded")
                    time.sleep(random.uniform(3, 5))

                    # Dismiss cookie consent if present
                    for sel in _COOKIE_SELECTORS:
                        try:
                            btn = page.query_selector(sel)
                            if btn:
                                btn.click()
                                time.sleep(1)
                                break
                        except Exception:
                            pass

                    # If FB has wall-gated the Ad Library, bail out
                    if "login" in page.url or "checkpoint" in page.url:
                        logger.warning(
                            "FB Ad Library: redirected to login — results unavailable"
                        )
                        return []

                    # Scroll to trigger lazy-loaded result cards
                    page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
                    time.sleep(random.uniform(1, 2))

                    # Extract all <a> hrefs that point at FB page slugs.
                    # We collect every slug on the page and filter out known
                    # non-company paths; false positives are cheap because
                    # Phase 2 dedup will discard anything already in the DB.
                    raw_items: list[dict] = page.evaluate("""
                        () => {
                            const results = [];
                            const seen = new Set();
                            for (const a of document.querySelectorAll('a[href]')) {
                                const href = a.href || '';
                                const m = href.match(/facebook\\.com\\/([^/?#]+)/);
                                if (!m) continue;
                                const slug = m[1];
                                if (!slug || seen.has(slug)) continue;
                                seen.add(slug);
                                const text = (a.innerText || a.textContent || '').trim();
                                results.push({slug, text});
                            }
                            return results;
                        }
                    """)

                    seen_names: set[str] = set()
                    for item in raw_items:
                        if len(results) >= limit:
                            break
                        slug = (item.get("slug") or "").strip()
                        if not slug or slug in _SLUG_BLOCKLIST or slug.isdigit():
                            continue
                        # Drop slugs containing URL special characters or dots
                        if re.search(r"[.=%&]", slug):
                            continue
                        company_name = (item.get("text") or slug).strip()
                        if len(company_name) < 2:
                            continue
                        name_key = company_name.lower()
                        if name_key in seen_names:
                            continue
                        seen_names.add(name_key)
                        results.append({
                            "company_name": company_name,
                            "domain": "",
                            "fb_page_slug": slug,
                        })
                finally:
                    browser.close()

            logger.info("FB Ad Library '%s': %d advertisers found", vertical, len(results))

        except Exception as exc:
            logger.warning("FB Ad Library search failed for '%s': %s", vertical, exc)

        return results

    # ── Method 2: Page Transparency check ────────────────────────────────────

    def page_transparency_check(self, fb_slug: str) -> bool:
        """Check if a Facebook page is currently running ads.

        Fetches facebook.com/{slug}/about_profile_transparency and looks for
        'This page is currently running ads'. Returns True if confirmed,
        False otherwise (including on Playwright errors or login walls).
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.warning("Playwright not installed — skipping FB transparency check")
            return False

        url = f"https://www.facebook.com/{fb_slug}/about_profile_transparency"
        try:
            with sync_playwright() as p:
                browser, page = _launch_page(p)
                try:
                    page.goto(url, timeout=self._timeout, wait_until="domcontentloaded")
                    time.sleep(random.uniform(2, 4))
                    content = page.content().lower()
                    running = "this page is currently running ads" in content
                finally:
                    browser.close()
            logger.info("FB transparency [%s] running_ads=%s", fb_slug, running)
            return running
        except Exception as exc:
            logger.debug("FB transparency check failed for '%s': %s", fb_slug, exc)
            return False
