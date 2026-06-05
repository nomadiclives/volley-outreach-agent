"""Vertical directory scrapers.

Registry maps (vertical, geo) pairs to scraper classes.
Vertical names are normalised to lowercase with underscores.
Geo is the lowercase ISO-style country code: "de", "uk".

Usage:
    from scrapers import get_scrapers_for_vertical_geo, get_scrapers_for_icp

    # CLI / manual run
    scrapers = get_scrapers_for_vertical_geo("solar", "de")

    # Phase 1 discovery in lead_finder.py — pass the ICP dict
    scrapers = get_scrapers_for_icp(icp)
"""

from __future__ import annotations
import logging
import re

logger = logging.getLogger(__name__)

# ── Registry ──────────────────────────────────────────────────────────────────
# Each entry maps (normalised_vertical, geo) → scraper class (lazy import).
# Add new scrapers here — no other file needs to change.

_REGISTRY: dict[tuple[str, str], str] = {
    ("solar",            "de"): "scrapers.solar_de.BSWSolarDeScraper",
    ("solar",            "uk"): "scrapers.solar_uk.SolarEnergyUKScraper",
    ("home_improvement", "uk"): "scrapers.home_improvement_uk.FMBScraper",
    ("finance",          "uk"): "scrapers.finance_uk.NACFBScraper",
    ("finance",          "de"): "scrapers.finance_de.BdBScraper",
}

# Alternative names that map onto canonical vertical keys
_VERTICAL_ALIASES: dict[str, str] = {
    "solar":               "solar",
    "solar energy":        "solar",
    "pv":                  "solar",
    "photovoltaic":        "solar",
    "home improvement":    "home_improvement",
    "home_improvement":    "home_improvement",
    "home services":       "home_improvement",
    "roofing":             "home_improvement",
    "hvac":                "home_improvement",
    "construction":        "home_improvement",
    "building":            "home_improvement",
    "finance":             "finance",
    "loans":               "finance",
    "business loans":      "finance",
    "commercial finance":  "finance",
    "lending":             "finance",
    "banking":             "finance",
}

# Geo aliases → canonical lowercase country code
_GEO_ALIASES: dict[str, str] = {
    "de": "de", "germany": "de", "deutschland": "de",
    "at": "de", "austria": "de", "ch": "de", "switzerland": "de",
    "uk": "uk", "gb": "uk", "united kingdom": "uk", "england": "uk",
    "scotland": "uk", "wales": "uk",
}


def _normalise_vertical(raw: str) -> str:
    key = raw.strip().lower()
    return _VERTICAL_ALIASES.get(key, re.sub(r"[^a-z0-9]+", "_", key))


def _normalise_geo(raw: str) -> str:
    return _GEO_ALIASES.get(raw.strip().lower(), raw.strip().lower())


def _load_class(dotted_path: str):
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


# ── Public helpers ─────────────────────────────────────────────────────────────

def get_scrapers_for_vertical_geo(vertical: str, geo: str) -> list:
    """Return a list of instantiated scraper(s) for an exact vertical+geo pair.

    Returns [] if no scraper is registered for the combination.
    """
    norm_v = _normalise_vertical(vertical)
    norm_g = _normalise_geo(geo)
    key = (norm_v, norm_g)
    cls_path = _REGISTRY.get(key)
    if not cls_path:
        logger.debug("No scraper registered for vertical='%s' geo='%s'", norm_v, norm_g)
        return []
    try:
        cls = _load_class(cls_path)
        return [cls()]
    except Exception as exc:
        logger.warning("Failed to load scraper %s: %s", cls_path, exc)
        return []


def get_scrapers_for_icp(icp: dict) -> list:
    """Return all relevant scrapers based on an ICP dict from icp_analyzer.

    Matches on icp["verticals"] (list) × icp["locations"] (list of {country, ...}).
    """
    scrapers: list = []
    seen_keys: set[tuple[str, str]] = set()

    verticals = icp.get("verticals") or []
    locations  = icp.get("locations") or []

    for vertical in verticals:
        norm_v = _normalise_vertical(str(vertical))
        for loc in locations:
            # locations can be {country, cities, apollo_code} dicts
            country_raw = loc.get("country") or ""
            norm_g = _normalise_geo(country_raw)
            key = (norm_v, norm_g)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            instances = get_scrapers_for_vertical_geo(norm_v, norm_g)
            scrapers.extend(instances)

    return scrapers


def list_available() -> list[dict]:
    """Return a list of all registered scraper entries for display."""
    return [
        {"vertical": v, "geo": g, "class": cls}
        for (v, g), cls in _REGISTRY.items()
    ]
