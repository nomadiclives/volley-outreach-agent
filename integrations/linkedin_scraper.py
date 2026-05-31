"""Public LinkedIn people search scraper via Playwright (no login required).

Searches linkedin.com/search/results/people/ by company name + target title
and extracts whatever profile cards are visible before any login wall.

Rate limits: 2–5 s delay between searches, max 20 company lookups per run
(enforced by the caller via budget["linkedin"] in lead_finder.py).
"""

import logging
import random
import time
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

_SEARCH_BASE = "https://www.linkedin.com/search/results/people/"
_TIMEOUT_MS = 30_000
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# LinkedIn renders placeholder cards for hidden profiles
_PLACEHOLDER_NAMES = frozenset({"linkedin member", "linkedin user"})


def scrape_company_people(
    company_name: str,
    titles: list[str],
    limit: int = 3,
) -> list[dict]:
    """Search LinkedIn's public people search for contacts at a company.

    Tries each title in `titles` (most important first) until `limit`
    contacts are collected or all titles are exhausted. Stops immediately
    if LinkedIn redirects to a login / authwall page.

    Args:
        company_name: Company to search contacts for.
        titles:       Target job titles to search (e.g. ['Marketing Manager']).
        limit:        Maximum contacts to return across all title searches.

    Returns:
        List of dicts with keys: first_name, last_name, title, linkedin_url.
        Empty list if Playwright is unavailable, login wall is hit, or no
        public results are found.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed — skipping LinkedIn search")
        return []

    if not company_name:
        return []

    # Try at most 3 title keywords to keep the lookup fast
    titles_to_try = (titles or ["marketing manager"])[:3]
    people: list[dict] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=_UA)
            page = ctx.new_page()

            for title_kw in titles_to_try:
                if len(people) >= limit:
                    break

                query = f"{company_name} {title_kw}"
                url = f"{_SEARCH_BASE}?keywords={quote_plus(query)}&origin=GLOBAL_SEARCH_HEADER"

                try:
                    page.goto(url, timeout=_TIMEOUT_MS, wait_until="domcontentloaded")
                    time.sleep(random.uniform(2, 5))

                    # LinkedIn may redirect headless browsers to a login / authwall page
                    current = page.url
                    if any(s in current for s in ("authwall", "/login", "/signup", "checkpoint")):
                        logger.info(
                            "LinkedIn: login wall for '%s' — stopping search", company_name
                        )
                        break

                    # Primary selector: search result cards
                    cards = page.query_selector_all(
                        '[data-view-name="search-entity-result-universal-template"]'
                    )
                    # Fallback selector used in some LinkedIn A/B variants
                    if not cards:
                        cards = page.query_selector_all("li.reusable-search__result-container")

                    for card in cards:
                        if len(people) >= limit:
                            break
                        try:
                            name_el = card.query_selector("span[aria-hidden='true']")
                            title_el = card.query_selector(".entity-result__primary-subtitle")
                            link_el = card.query_selector("a.app-aware-link")

                            name = (name_el.inner_text() if name_el else "").strip()
                            extracted_title = (title_el.inner_text() if title_el else "").strip()
                            href = (link_el.get_attribute("href") if link_el else "") or ""

                            if not name or name.lower() in _PLACEHOLDER_NAMES:
                                continue

                            parts = name.split(" ", 1)
                            people.append({
                                "first_name":   parts[0],
                                "last_name":    parts[1] if len(parts) > 1 else "",
                                "title":        extracted_title,
                                "linkedin_url": href.split("?")[0],  # strip tracking params
                            })
                        except Exception as exc:
                            logger.debug("Error parsing LinkedIn card: %s", exc)

                except Exception as exc:
                    logger.debug("LinkedIn search failed for '%s': %s", query, exc)
                    break

            browser.close()

    except Exception as exc:
        logger.warning("LinkedIn scraper failed for '%s': %s", company_name, exc)

    logger.info(
        "LinkedIn search '%s': %d contact(s) found", company_name, len(people)
    )
    return people
