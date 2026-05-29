"""Buying signal detection for leads.

Two detection methods:

  Method 1 — Homepage pixel scan (all leads with a known domain):
    Fetch the company homepage and check for ad/tracking pixels:
    Meta Pixel, Google Ads, Google Tag Manager, TrustedForm, Jornaya.

  Method 2 — Facebook Page Transparency (leads with partial score >40):
    Use Playwright to open {company_slug}/about_profile_transparency and
    check for the text "This page is currently running ads".

Output schema (stored as buying_signals JSON on the lead):
    running_ads      — True if any paid ad platform was detected
    meta_pixel       — Meta Pixel (connect.facebook.net/…/fbevents.js) found
    google_ads       — Google Ads tag or gtag AW- config found
    gtm              — Google Tag Manager found
    tcpa_signals     — TrustedForm or Jornaya (lead-gen compliance pixels) found
    fb_ads_confirmed — Facebook Page Transparency confirms active ads
    multi_location   — Multi-location keywords detected on homepage
"""

import logging
import random
import re
import time
from typing import Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

_HOMEPAGE_TIMEOUT = 8       # seconds per HTTP request
_FB_TIMEOUT = 15_000        # ms for Playwright goto

# ── Pixel / tag regex patterns ─────────────────────────────────────────────────

_META_PIXEL = re.compile(r"connect\.facebook\.net/[a-zA-Z_/]+/fbevents\.js", re.IGNORECASE)
_GOOGLE_ADS = [
    re.compile(r"googleadservices\.com", re.IGNORECASE),
    re.compile(r"""gtag\s*\(\s*['"]config['"]\s*,\s*['"]AW-""", re.IGNORECASE),
]
_GTM = re.compile(r"googletagmanager\.com/gtm\.js", re.IGNORECASE)
_GTM_CONTAINER_ID = re.compile(r"GTM-[A-Z0-9]+")
_TRUSTEDFORM = re.compile(r"trustedform\.com", re.IGNORECASE)
_JORNAYA = re.compile(r"leadid\.com", re.IGNORECASE)

# Patterns to check inside a GTM container script
_GTM_META_PIXEL = re.compile(r"fbevents|connect\.facebook\.net", re.IGNORECASE)
_GTM_GOOGLE_ADS = re.compile(r"googleadservices\.com|AW-\d{6,}", re.IGNORECASE)

# Multi-location heuristic — keywords that reliably indicate multiple physical sites
_MULTI_LOCATION_KEYWORDS: list[str] = [
    "multiple locations",
    "all locations",
    "find a location",
    "find a store",
    "our offices",
    "nationwide",
    "across the country",
    "coast to coast",
    "serving all",
]

# ── Domain normalisation ───────────────────────────────────────────────────────


def _clean_domain(raw: str) -> str:
    """Strip scheme, www. prefix, and trailing path from a domain string."""
    raw = raw.strip()
    if "//" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    host = parsed.netloc or parsed.path
    return host.lower().removeprefix("www.").split("/")[0]


# ── Homepage fetch ────────────────────────────────────────────────────────────


def _fetch_html(domain: str) -> Optional[str]:
    """Fetch homepage HTML over https then http. Returns None on failure."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    for scheme in ("https", "http"):
        url = f"{scheme}://{domain}"
        try:
            resp = requests.get(
                url,
                timeout=_HOMEPAGE_TIMEOUT,
                headers=headers,
                allow_redirects=True,
            )
            if resp.status_code < 400:
                return resp.text
        except requests.RequestException as exc:
            logger.debug("Fetch failed (%s): %s", url, exc)
    return None


# ── GTM container inspection ──────────────────────────────────────────────────


def _inspect_gtm_container(html: str) -> dict:
    """When GTM is detected, fetch the container script and check for pixel tags.

    GTM container scripts are public and contain the full tag configuration,
    including which pixels (Meta, Google Ads) are actually fired.

    Returns dict with meta_pixel and google_ads keys (both bool).
    """
    ids = _GTM_CONTAINER_ID.findall(html)
    if not ids:
        return {"meta_pixel": False, "google_ads": False}

    container_id = ids[0]
    url = f"https://www.googletagmanager.com/gtm.js?id={container_id}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, timeout=_HOMEPAGE_TIMEOUT, headers=headers)
        if resp.status_code >= 400:
            return {"meta_pixel": False, "google_ads": False}
        container_js = resp.text
        result = {
            "meta_pixel": bool(_GTM_META_PIXEL.search(container_js)),
            "google_ads": bool(_GTM_GOOGLE_ADS.search(container_js)),
        }
        logger.info(
            "GTM container [%s] meta=%s gads=%s",
            container_id,
            result["meta_pixel"],
            result["google_ads"],
        )
        return result
    except requests.RequestException as exc:
        logger.debug("GTM container fetch failed (%s): %s", container_id, exc)
        return {"meta_pixel": False, "google_ads": False}


# ── Method 1: homepage pixel scan ────────────────────────────────────────────


def _scan_homepage_pixels(domain: str) -> dict:
    """Fetch homepage HTML and detect ad/tracking pixels.

    Returns a partial signals dict (excludes fb_ads_confirmed and running_ads,
    which are computed by the caller after Method 2 runs).
    """
    out: dict = {
        "meta_pixel": False,
        "google_ads": False,
        "gtm": False,
        "tcpa_signals": False,
        "multi_location": False,
    }
    if not domain:
        return out

    html = _fetch_html(domain)
    if not html:
        logger.debug("No homepage HTML retrieved for %s", domain)
        return out

    out["meta_pixel"] = bool(_META_PIXEL.search(html))
    out["google_ads"] = any(p.search(html) for p in _GOOGLE_ADS)
    out["gtm"] = bool(_GTM.search(html))
    out["tcpa_signals"] = bool(_TRUSTEDFORM.search(html) or _JORNAYA.search(html))

    html_lower = html.lower()
    out["multi_location"] = any(kw in html_lower for kw in _MULTI_LOCATION_KEYWORDS)

    # When GTM is present and pixels weren't found inline, check the container
    # script — GTM loads pixels via JavaScript so they don't appear in raw HTML.
    if out["gtm"] and not (out["meta_pixel"] and out["google_ads"]):
        gtm_signals = _inspect_gtm_container(html)
        out["meta_pixel"] = out["meta_pixel"] or gtm_signals["meta_pixel"]
        out["google_ads"] = out["google_ads"] or gtm_signals["google_ads"]

    logger.info(
        "Pixel scan [%s] meta=%s gads=%s gtm=%s tcpa=%s ml=%s",
        domain,
        out["meta_pixel"],
        out["google_ads"],
        out["gtm"],
        out["tcpa_signals"],
        out["multi_location"],
    )
    return out


# ── Method 2: Facebook Page Transparency ──────────────────────────────────────


def _derive_fb_slug(lead: dict) -> Optional[str]:
    """Derive a likely Facebook page slug from the lead's company name."""
    name = (lead.get("company_name") or "").strip()
    if not name:
        return None
    slug = re.sub(r"[^\w\s-]", "", name.lower())
    slug = re.sub(r"\s+", "-", slug.strip())
    slug = re.sub(r"-+", "-", slug)
    for suffix in ("-llc", "-inc", "-ltd", "-gmbh", "-corp", "-co"):
        if slug.endswith(suffix):
            slug = slug[: -len(suffix)]
    return slug.strip("-") or None


def _fb_transparency_check(fb_slug: str) -> bool:
    """Check Facebook Page Transparency for active ads via Playwright.

    Returns True if 'this page is currently running ads' is found.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("Playwright not installed — skipping FB transparency check")
        return False

    url = f"https://www.facebook.com/{fb_slug}/about_profile_transparency"
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            )
            page = ctx.new_page()
            try:
                page.goto(url, timeout=_FB_TIMEOUT, wait_until="domcontentloaded")
                time.sleep(random.uniform(2, 4))
                content = page.content().lower()
                running = "this page is currently running ads" in content
            finally:
                browser.close()
        logger.info("FB transparency [%s] running_ads=%s", fb_slug, running)
        return running
    except Exception as exc:
        logger.debug("FB transparency failed for slug '%s': %s", fb_slug, exc)
        return False


# ── Partial score (threshold gate for Method 2) ────────────────────────────────


def _partial_score(lead: dict) -> int:
    """Score the lead on signal-independent criteria only.

    Used to decide whether to run the expensive FB transparency check.
    Computes: title + company_size + ltv_vertical + marketing_roles + data_completeness
    Maximum: 65 pts.
    """
    # Late import avoids circular dependency at module load time
    from agents.lead_enricher import (
        _score_company_size,
        _score_data_completeness,
        _score_ltv_vertical,
        _score_marketing_roles,
        _score_title,
    )
    icp: dict = {}
    no_signals: dict = {}
    return (
        _score_title(lead, icp)
        + _score_company_size(lead, icp)
        + _score_ltv_vertical(lead, icp)
        + _score_marketing_roles(lead, no_signals)
        + _score_data_completeness(lead)
    )


# ── Public API ────────────────────────────────────────────────────────────────


def check_buying_signals(lead: dict) -> dict:
    """Run all buying signal checks for a single lead.

    Method 1 (homepage pixel scan) runs on every lead with a known domain.
    Method 2 (Facebook Page Transparency) runs only when the partial score
    (title + size + ltv + marketing + data_completeness) exceeds 40 pts.

    Returns a buying_signals dict ready to be JSON-serialised and stored on
    the lead. The caller is responsible for storing it:
        lead["buying_signals"] = json.dumps(check_buying_signals(lead))

    Keys in returned dict:
        running_ads, meta_pixel, google_ads, gtm, tcpa_signals,
        fb_ads_confirmed, multi_location
    """
    raw_domain = (lead.get("domain") or "").strip()
    domain = _clean_domain(raw_domain) if raw_domain else ""

    # Method 1 — homepage pixel scan (always)
    signals = _scan_homepage_pixels(domain)

    # Method 2 — FB transparency (only for promising leads)
    fb_ads_confirmed = False
    if _partial_score(lead) > 40:
        fb_slug = _derive_fb_slug(lead)
        if fb_slug:
            fb_ads_confirmed = _fb_transparency_check(fb_slug)

    signals["fb_ads_confirmed"] = fb_ads_confirmed

    # Aggregate: any paid platform detected → running_ads = True
    signals["running_ads"] = (
        signals["meta_pixel"] or signals["google_ads"] or fb_ads_confirmed
    )

    return signals
