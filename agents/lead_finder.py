"""Multi-source lead discovery orchestration."""

import logging
from agents.icp_analyzer import analyze_icp
from agents.lead_enricher import enrich_batch
from core.deduplicator import deduplicate_batch
from core.database import insert_lead
from integrations.google_sheets import sync_lead

logger = logging.getLogger(__name__)


def find_leads(
    icp_description: str,
    config: dict,
    limit: int = 50,
    dry_run: bool = False,
) -> list[dict]:
    """
    Orchestrate multi-source lead discovery.
    Source waterfall: Apollo → Hunter → Google Maps → LinkedIn

    Returns list of saved leads.
    """
    logger.info("Starting lead find: limit=%d dry_run=%s", limit, dry_run)

    # 1. Parse ICP
    icp = analyze_icp(icp_description, config)
    logger.info("ICP parsed: %s", icp.get("icp_rationale", "")[:100])

    all_leads: list[dict] = []

    # 2. Apollo (primary)
    try:
        from integrations.apollo import ApolloClient
        apollo = ApolloClient(config)
        apollo_leads = apollo.search_people(
            titles=icp.get("target_titles", []),
            seniority=icp.get("title_seniority", []),
            industries=icp.get("apollo_industry_tags", []),
            locations=[loc.get("apollo_code", loc.get("country", "")) for loc in icp.get("locations", [])],
            employee_ranges=[f"{icp['employee_range']['min']},{icp['employee_range']['max']}"]
            if icp.get("employee_range") else [],
            limit=min(limit, 25),
        )
        all_leads.extend(apollo_leads)
        logger.info("Apollo: %d leads", len(apollo_leads))
    except Exception as e:
        logger.warning("Apollo source failed: %s — falling through", e)

    # 3. Hunter (secondary) — try for domains without emails
    if len(all_leads) < limit:
        try:
            from integrations.hunter import HunterClient
            hunter = HunterClient(config)
            # Pull domains from companies that had no email from Apollo
            no_email = [l for l in all_leads if not l.get("email")]
            unique_domains = list({l["domain"] for l in no_email if l.get("domain")})[:5]
            for domain in unique_domains:
                hunter_leads = hunter.domain_search(domain, limit=5)
                all_leads.extend(hunter_leads)
        except Exception as e:
            logger.warning("Hunter source failed: %s — falling through", e)

    # 4. Google Maps (fallback for local/SMB)
    if len(all_leads) < limit // 2 and config["google"].get("maps_api_key"):
        try:
            from integrations.google_maps import GoogleMapsClient
            maps = GoogleMapsClient(config)
            for loc in icp.get("locations", [])[:2]:
                for vertical in icp.get("verticals", [])[:2]:
                    city = loc.get("cities", [loc.get("country", "")])[0]
                    maps_leads = maps.text_search(vertical, city, limit=10)
                    all_leads.extend(maps_leads)
        except Exception as e:
            logger.warning("Google Maps source failed: %s", e)

    logger.info("Total raw leads before dedup: %d", len(all_leads))

    # Deduplicate
    unique = deduplicate_batch(all_leads)
    logger.info("After dedup: %d leads", len(unique))

    # Enrich & score (limit API calls)
    to_enrich = unique[:limit]
    enriched = enrich_batch(to_enrich, icp, config)

    if dry_run:
        logger.info("[DRY RUN] Would save %d leads", len(enriched))
        return enriched

    # Save to DB + Sheets
    saved = []
    for lead in enriched:
        lead.setdefault("status", "new")
        lead.setdefault("notes", "")
        new_id = insert_lead(lead)
        if new_id:
            lead["id"] = new_id
            try:
                sync_lead(lead)
            except Exception as e:
                logger.warning("Sheets sync failed for %s: %s", lead.get("email"), e)
            saved.append(lead)

    logger.info("Saved %d new leads to database", len(saved))
    return saved
