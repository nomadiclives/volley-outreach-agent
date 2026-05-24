"""Public LinkedIn profile scraper via Playwright (no login required)."""

import logging
import random
import time

logger = logging.getLogger(__name__)


def scrape_company_people(company_url: str, titles: list[str], limit: int = 20) -> list[dict]:
    """
    Scrape publicly visible employee info from a LinkedIn company page.
    Respectful rate limits: 2-5s delay between page loads, max 50/session.
    No login required — only accesses public data.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed — skipping LinkedIn scrape")
        return []

    leads = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()

            people_url = company_url.rstrip("/") + "/people/"
            page.goto(people_url, timeout=30000)
            time.sleep(random.uniform(2, 5))

            # Extract public profile cards
            cards = page.query_selector_all('[data-view-name="search-entity-result-universal-template"]')
            for card in cards[:min(limit, 50)]:
                try:
                    name_el = card.query_selector("span[aria-hidden='true']")
                    title_el = card.query_selector(".entity-result__primary-subtitle")
                    link_el = card.query_selector("a.app-aware-link")

                    name = name_el.inner_text().strip() if name_el else ""
                    title = title_el.inner_text().strip() if title_el else ""
                    linkedin_url = link_el.get_attribute("href") if link_el else ""

                    if not name:
                        continue

                    # Filter by target titles
                    if titles and not any(t.lower() in title.lower() for t in titles):
                        continue

                    parts = name.split(" ", 1)
                    leads.append({
                        "first_name": parts[0],
                        "last_name": parts[1] if len(parts) > 1 else "",
                        "title": title,
                        "email": "",  # Not available from public LinkedIn
                        "linkedin_url": linkedin_url,
                        "company_name": "",
                        "domain": "",
                        "industry": "",
                        "employee_count": "",
                        "city": "",
                        "country": "",
                        "source": "linkedin",
                        "email_verified": 0,
                        "icp_score": 0,
                        "status": "new",
                        "notes": "LinkedIn — email needs to be found separately",
                    })
                    time.sleep(random.uniform(2, 5))
                except Exception as e:
                    logger.debug("Error parsing LinkedIn card: %s", e)
                    continue

            browser.close()

    except Exception as e:
        logger.error("LinkedIn scrape failed: %s", e)

    logger.info("LinkedIn scraped %d profiles from %s", len(leads), company_url)
    return leads
