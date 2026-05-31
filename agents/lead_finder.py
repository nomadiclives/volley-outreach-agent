"""Two-phase lead discovery with pre-search deduplication.

Phase 1 — Company Discovery:
    Find companies matching the ICP using Apollo, Google Maps, and Facebook Ad
    Library. Output: list of {company_name, domain, ...} dicts — no contact
    person yet. Apollo results are cached so Phase 2 can reuse them for free.

Phase 2 — Contact & Email Resolution:
    For each company found in Phase 1, try sources in order until a verified
    email is found. Stop as soon as one source succeeds.

    Order: Apollo cache (free) → Lusha → Snov.io → GetProspect → Hunter →
           LinkedIn scraper + Hunter email finder

Pre-search deduplication (before spending any credits):
    L3 — domain:    skip company if any lead for this domain is already in DB
    L2 — contact:   skip if company_name+first_name+last_name already in DB
    L1 — email:     skip if email already in leads table

Filtering philosophy:
    Hard gates and soft scoring live entirely in lead_enricher.py. Every lead
    that passes dedup is passed to enrich_batch without pre-filtering here.
"""

import json
import logging
from agents.icp_analyzer import analyze_icp
from agents.buying_signal_checker import check_buying_signals
from agents.lead_enricher import enrich_batch
from core.credit_manager import CreditManager, CreditLimitReached
from core.deduplicator import domain_exists_in_leads, contact_exists_in_leads, is_duplicate
from core.database import insert_lead
from integrations.google_sheets import sync_lead

logger = logging.getLogger(__name__)


# ── Phase 1: Company Discovery ────────────────────────────────────────────────

def _discover_companies(
    icp: dict,
    config: dict,
    limit: int,
    budget: dict,
) -> tuple[list[dict], dict]:
    """Discover companies across all Phase 1 sources.

    Returns:
        companies    — list of {company_name, domain, industry, city, country, source}
        apollo_cache — {domain: full_lead_dict} — contacts Apollo returned at no extra cost
    """
    companies: list[dict] = []
    apollo_cache: dict[str, dict] = {}
    seen_domains: set[str] = set()

    def _add(c: dict) -> None:
        domain = (c.get("domain") or "").strip().lower()
        if domain in seen_domains:
            return
        seen_domains.add(domain)
        companies.append(c)

    # ── Source 1: Apollo ─────────────────────────────────────────────────────
    if budget.get("apollo", 0) > 0:
        try:
            from integrations.apollo import ApolloClient
            apollo = ApolloClient(config)
            apollo_leads = apollo.search_people(
                titles=icp.get("target_titles", []),
                seniority=icp.get("title_seniority", []),
                industries=icp.get("apollo_industry_tags", []),
                locations=[
                    loc.get("apollo_code", loc.get("country", ""))
                    for loc in icp.get("locations", [])
                ],
                employee_ranges=[
                    f"{icp['employee_range']['min']},{icp['employee_range']['max']}"
                ] if icp.get("employee_range") else [],
                limit=min(budget.get("apollo", 25), 25),
            )
            budget["apollo"] = max(0, budget.get("apollo", 0) - 1)
            for lead in apollo_leads:
                domain = (lead.get("domain") or "").strip().lower()
                _add({
                    "company_name":   lead.get("company_name", ""),
                    "domain":         domain,
                    "industry":       lead.get("industry", ""),
                    "employee_count": lead.get("employee_count", ""),
                    "city":           lead.get("city", ""),
                    "country":        lead.get("country", ""),
                    "source":         "apollo",
                })
                if domain and lead.get("email"):
                    apollo_cache[domain] = lead
            logger.info(
                "Phase 1 Apollo: %d companies, %d with cached contacts",
                len(apollo_leads), len(apollo_cache),
            )
        except CreditLimitReached as e:
            logger.warning("Phase 1 Apollo credit limit: %s", e)
            budget["apollo"] = 0
        except Exception as e:
            logger.warning("Phase 1 Apollo failed: %s — falling through", e)

    # ── Source 2: Google Maps (unlimited, local/SMB) ──────────────────────────
    if len(companies) < limit and config.get("google", {}).get("maps_api_key"):
        try:
            from integrations.google_maps import GoogleMapsClient
            maps = GoogleMapsClient(config)
            for loc in icp.get("locations", [])[:2]:
                city = (
                    loc.get("cities", [])[0]
                    if loc.get("cities")
                    else loc.get("country", "")
                )
                for vertical in icp.get("verticals", [])[:2]:
                    for r in maps.text_search(vertical, city, limit=10):
                        _add({
                            "company_name":   r.get("company_name", ""),
                            "domain":         (r.get("domain") or "").strip().lower(),
                            "industry":       r.get("industry", ""),
                            "employee_count": "",
                            "city":           r.get("city", city),
                            "country":        r.get("country", loc.get("country", "")),
                            "source":         "google_maps",
                        })
            logger.info("Phase 1 after Google Maps: %d companies total", len(companies))
        except Exception as e:
            logger.warning("Phase 1 Google Maps failed: %s", e)

    # ── Source 3: Facebook Ad Library ────────────────────────────────────────
    try:
        from integrations.facebook_ads import FacebookAdsClient
        fb = FacebookAdsClient(config)
        for vertical in icp.get("verticals", [])[:2]:
            for c in fb.search_advertisers(vertical, limit=10):
                _add({
                    "company_name":   c.get("company_name", ""),
                    "domain":         (c.get("domain") or "").strip().lower(),
                    "industry":       vertical,
                    "employee_count": "",
                    "city":           "",
                    "country":        "",
                    "source":         "facebook_ads",
                    # Pre-populate buying signals — these companies are confirmed advertisers
                    "buying_signals": json.dumps(
                        {"running_ads": True, "fb_ads_confirmed": True}
                    ),
                })
        logger.info("Phase 1 after Facebook Ads: %d companies total", len(companies))
    except ImportError:
        logger.debug("facebook_ads not available — skipping Phase 1 source")
    except Exception as e:
        logger.warning("Phase 1 Facebook Ads failed: %s", e)

    logger.info("Phase 1 complete: %d unique companies", len(companies))
    return companies, apollo_cache


# ── Phase 2: Contact & Email Resolution ───────────────────────────────────────

def _resolve_contact(
    company: dict,
    icp: dict,
    config: dict,
    budget: dict,
    apollo_cache: dict,
) -> dict | None:
    """Find the right contact and verified email for a single company.

    Sources tried in order, stopping on first verified email found.
    All three dedup levels are checked before returning a result.
    Returns a merged company+contact dict, or None.
    """
    domain = (company.get("domain") or "").strip().lower()
    company_name = company.get("company_name", "")
    titles = icp.get("target_titles", [])

    # Level 3: skip entire company if domain already covered in DB
    if domain and domain_exists_in_leads(domain):
        logger.debug("L3 dedup skip: %s", domain)
        return None

    def _merge(contact: dict) -> dict | None:
        """Apply L2+L1 dedup then return merged company+contact, or None."""
        fn, ln = contact.get("first_name", ""), contact.get("last_name", "")
        email = (contact.get("email") or "").strip()
        if not email:
            return None
        if fn and contact_exists_in_leads(company_name, fn, ln):
            logger.debug("L2 dedup skip: %s %s @ %s", fn, ln, company_name)
            return None
        if is_duplicate({"email": email}):
            logger.debug("L1 dedup skip: %s", email)
            return None
        return {**company, **contact}

    # ── 1. Apollo cache — free, no extra credit ───────────────────────────────
    if domain in apollo_cache:
        result = _merge(apollo_cache[domain])
        if result:
            logger.debug("Phase 2 Apollo cache hit: %s", domain)
            return result

    # ── 2. Lusha ──────────────────────────────────────────────────────────────
    if budget.get("lusha", 0) > 0:
        try:
            from integrations.lusha import LushaClient
            contact = LushaClient(config).find_contact_at_company(
                company_name, domain, titles
            )
            budget["lusha"] -= 1  # credit already logged inside LushaClient
            if contact:
                result = _merge(contact)
                if result:
                    return result
        except CreditLimitReached:
            budget["lusha"] = 0
        except Exception as e:
            logger.warning("Lusha failed for %s: %s", company_name, e)

    # ── 3. Snov.io ────────────────────────────────────────────────────────────
    if budget.get("snov", 0) > 0 and domain:
        try:
            from integrations.snov import SnovClient
            contacts = SnovClient(config).find_contacts_at_domain(domain, titles)
            budget["snov"] -= 1
            for contact in contacts:
                result = _merge(contact)
                if result:
                    return result
        except CreditLimitReached:
            budget["snov"] = 0
        except Exception as e:
            logger.warning("Snov failed for %s: %s", domain, e)

    # ── 4. GetProspect ────────────────────────────────────────────────────────
    if budget.get("getprospect", 0) > 0 and domain:
        try:
            from integrations.getprospect import GetProspectClient
            contacts = GetProspectClient(config).find_contacts_at_domain(
                domain, company_name, titles
            )
            budget["getprospect"] -= 1
            for contact in contacts:
                result = _merge(contact)
                if result:
                    return result
        except CreditLimitReached:
            budget["getprospect"] = 0
        except Exception as e:
            logger.warning("GetProspect failed for %s: %s", domain, e)

    # ── 5. Hunter domain search ───────────────────────────────────────────────
    if budget.get("hunter", 0) > 0 and domain:
        try:
            from integrations.hunter import HunterClient
            hunter = HunterClient(config)
            hunter_leads = hunter.domain_search(domain, limit=5)
            budget["hunter"] -= 1
            # Prefer a lead whose title matches; fall back to first result
            best = next(
                (l for l in hunter_leads
                 if any(t.lower() in l.get("title", "").lower() for t in titles)),
                hunter_leads[0] if hunter_leads else None,
            )
            if best:
                result = _merge(best)
                if result:
                    return result
        except CreditLimitReached:
            budget["hunter"] = 0
        except Exception as e:
            logger.warning("Hunter domain_search failed for %s: %s", domain, e)

    # ── 6. LinkedIn scraper → Hunter email finder ─────────────────────────────
    if budget.get("hunter", 0) > 0:
        try:
            from integrations.linkedin_scraper import scrape_company_people
            from integrations.hunter import HunterClient

            li_url = company.get("linkedin_url", "")
            if not li_url and domain:
                slug = domain.split(".")[0]
                li_url = f"https://www.linkedin.com/company/{slug}"

            people = scrape_company_people(li_url, titles, limit=3)
            if people and domain:
                hunter = HunterClient(config)
                for person in people:
                    contact = hunter.email_finder(
                        domain,
                        person.get("first_name", ""),
                        person.get("last_name", ""),
                    )
                    if contact:
                        budget["hunter"] -= 1
                        merged = _merge({**person, **contact})
                        if merged:
                            return merged
                        if budget.get("hunter", 0) <= 0:
                            break
        except CreditLimitReached:
            budget["hunter"] = 0
        except Exception as e:
            logger.warning("LinkedIn+Hunter failed for %s: %s", company_name, e)

    return None


# ── Main orchestrator ──────────────────────────────────────────────────────────

def find_leads(
    icp_description: str,
    config: dict,
    limit: int = 50,
    dry_run: bool = False,
    icp_data: dict = None,
    credit_budget: dict = None,
) -> list[dict]:
    """Orchestrate two-phase lead discovery.

    Pass icp_data if already resolved (avoids a redundant Claude API call).
    Pass credit_budget dict to override automatic allocation (wizard Step 6
    manual override).

    Returns list of saved leads (or unsaved dicts in dry_run mode).
    """
    logger.info("Starting lead find: limit=%d dry_run=%s", limit, dry_run)

    # 1. Parse ICP
    if icp_data is not None:
        icp = icp_data
        logger.info("ICP provided by caller, skipping analyze_icp")
    else:
        icp = analyze_icp(icp_description, config)
        logger.info("ICP parsed: %s", icp.get("icp_rationale", "")[:100])

    # 2. Allocate credit budget (manual override or auto)
    credit_manager = CreditManager(config)
    budget = credit_manager.allocate_budget(limit, override=credit_budget)
    logger.info("Credit budget for this run: %s", budget)

    # 3. Phase 1 — Company Discovery
    companies, apollo_cache = _discover_companies(icp, config, limit, budget)
    logger.info("Phase 1: %d companies, %d Apollo cached contacts",
                len(companies), len(apollo_cache))

    # 4. Phase 2 — Contact Resolution
    resolved: list[dict] = []
    for company in companies:
        if len(resolved) >= limit:
            break
        lead = _resolve_contact(company, icp, config, budget, apollo_cache)
        if lead:
            resolved.append(lead)

    logger.info(
        "Phase 2: %d leads resolved from %d companies (budget remaining: %s)",
        len(resolved), len(companies), budget,
    )

    # 5. Buying signals (skip for leads pre-populated by Facebook Ads source)
    for lead in resolved:
        if lead.get("buying_signals"):
            continue
        try:
            signals = check_buying_signals(lead)
            lead["buying_signals"] = json.dumps(signals)
        except Exception as exc:
            logger.warning(
                "Buying signal check failed for %s: %s",
                lead.get("domain") or lead.get("company_name"), exc,
            )

    # 6. Enrich & score — all leads pass through; hard gates and soft scoring
    #    live in lead_enricher, not here.
    enriched = enrich_batch(resolved, icp, config)

    if dry_run:
        logger.info("[DRY RUN] Would save %d leads", len(enriched))
        return enriched

    # 7. Save to DB + Sheets
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
