"""Parse ICP inputs into structured Apollo search parameters.

Supports two entry points:
  - analyze_icp()              — legacy free-text description (kept for CLI usage)
  - analyze_icp_from_wizard()  — structured 6-step wizard inputs (preferred)
  - wizard_to_icp_text()       — converts wizard data to a human-readable summary
"""

import json
import logging
from agents.claude_client import claude_call

logger = logging.getLogger(__name__)

# ── Shared output schema prompt ────────────────────────────────────────────────
_OUTPUT_SCHEMA = """
Return ONLY valid JSON — no preamble, no markdown fences, no explanation.

Required format:
{
  "verticals": ["string"],
  "apollo_industry_tags": ["string"],
  "employee_range": {"min": 10, "max": 500},
  "locations": [{"country": "string", "apollo_code": "string", "cities": ["string"]}],
  "target_titles": ["string"],
  "title_seniority": ["c_suite", "director", "vp", "manager"],
  "icp_rationale": "string",
  "pain_points": ["string"],
  "estimated_market_size": "string"
}

Apollo seniority values: c_suite, director, vp, manager, individual_contributor
Apollo industry tags use their exact tag strings (e.g. "information_technology_and_services").
Apollo country codes: US, GB, DE, AT, CH, FR, NL, BE, ES, IT, PL, SE, NO, DK, FI, AU, CA, BR, IN, SG
Pain points should describe specifically what a lead gen agency on a pay-per-lead model solves for this buyer.
"""

# ── Free-text ICP analyzer (legacy) ───────────────────────────────────────────
_FREETEXT_SYSTEM = (
    "You are a senior B2B sales strategist specialising in lead generation agencies.\n\n"
    "Your task: convert an ICP (Ideal Customer Profile) description into structured "
    "Apollo search parameters.\n" + _OUTPUT_SCHEMA
)


def analyze_icp(icp_description: str, config: dict) -> dict:
    """
    Convert a free-text ICP description into structured search criteria.

    Kept for backward compatibility with the CLI (`python main.py find --icp "..."`).
    New Campaign wizard should use analyze_icp_from_wizard() instead.

    Returns the parsed Apollo search params dict.
    """
    raw = claude_call(
        system_prompt=_FREETEXT_SYSTEM,
        user_prompt=f"ICP description:\n{icp_description}",
        purpose="icp_analysis",
        config=config,
        max_tokens=1000,
    )

    try:
        result = json.loads(raw.strip())
        logger.info(
            "ICP analysis (free-text): %d verticals, %d title types, locations=%s",
            len(result.get("verticals", [])),
            len(result.get("target_titles", [])),
            [loc["country"] for loc in result.get("locations", [])],
        )
        return result
    except json.JSONDecodeError as e:
        logger.error("ICP analyzer returned invalid JSON: %s\nRaw: %s", e, raw[:500])
        raise ValueError(f"ICP analysis failed — Claude returned non-JSON output: {e}")


# ── Wizard-based ICP analyzer ─────────────────────────────────────────────────
_WIZARD_SYSTEM = (
    "You are a senior B2B sales strategist specialising in lead generation agencies.\n\n"
    "Convert the structured ICP wizard inputs into Apollo search parameters and "
    "strategic context.  The inputs are already structured — your job is to:\n"
    "  1. Map the vertical to the correct apollo_industry_tags\n"
    "  2. Map country names to the correct Apollo 2-letter codes\n"
    "  3. Map job titles to the correct title_seniority values\n"
    "  4. Generate specific pain_points for this vertical/buyer type\n"
    "  5. Write a concise icp_rationale\n"
    "  6. Estimate the addressable market size\n\n"
    + _OUTPUT_SCHEMA
)

# Buying signal labels for the Claude prompt
_SIGNAL_LABELS = {
    "running_ads":      "Running Meta/Google/YouTube paid ads",
    "lead_forms":       "Lead capture forms on website",
    "tcpa_language":    "TCPA compliance language on website",
    "call_centre":      "Has a dedicated call centre or sales team",
    "marketing_roles":  "Has dedicated marketing/growth roles",
    "high_ltv_vertical": "Operates in a high-LTV vertical (insurance, legal, financial, home services, solar)",
    "affiliate_program": "Has an affiliate or referral program",
}


def analyze_icp_from_wizard(wizard_data: dict, config: dict) -> dict:
    """
    Convert structured 6-step wizard inputs into Apollo search parameters.

    wizard_data keys:
      vertical (str), geo_countries (list[str]), geo_cities (str),
      employees_min (int), employees_max (int), multi_location (bool),
      buying_signals (list[str]), target_titles (list[str]),
      exclusions (dict: small_companies, solo_operators, regulated_verticals)

    Returns the same format dict as analyze_icp().
    """
    signals = wizard_data.get("buying_signals", [])
    signal_labels = [_SIGNAL_LABELS.get(s, s) for s in signals]
    exclusions = wizard_data.get("exclusions", {})

    excl_parts = []
    if exclusions.get("small_companies"):
        excl_parts.append("companies with fewer than 5 employees")
    if exclusions.get("solo_operators"):
        excl_parts.append("solo operators / freelancers")
    if exclusions.get("regulated_verticals"):
        excl_parts.append("ACA / Medicare / car insurance verticals")

    user_prompt = f"""Structured ICP wizard inputs:

Vertical: {wizard_data.get('vertical', '')}
Target countries: {', '.join(wizard_data.get('geo_countries', []))}
City focus: {wizard_data.get('geo_cities', 'not specified') or 'not specified'}
Company size: {wizard_data.get('employees_min', 10)}–{wizard_data.get('employees_max', 200)} employees
Multi-location: {'yes — prioritise multi-location/multi-region companies' if wizard_data.get('multi_location') else 'no preference'}
Buying signals confirmed: {', '.join(signal_labels) if signal_labels else 'none specified'}
Target titles: {', '.join(wizard_data.get('target_titles', []))}
Auto-reject exclusions: {', '.join(excl_parts) if excl_parts else 'none'}

Generate the Apollo search parameters and strategic context."""

    raw = claude_call(
        system_prompt=_WIZARD_SYSTEM,
        user_prompt=user_prompt,
        purpose="icp_analysis",
        config=config,
        max_tokens=1000,
    )

    try:
        result = json.loads(raw.strip())
        logger.info(
            "ICP analysis (wizard): %d verticals, %d title types, locations=%s",
            len(result.get("verticals", [])),
            len(result.get("target_titles", [])),
            [loc["country"] for loc in result.get("locations", [])],
        )
        return result
    except json.JSONDecodeError as e:
        logger.error("Wizard ICP analyzer returned invalid JSON: %s\nRaw: %s", e, raw[:500])
        raise ValueError(f"ICP analysis failed — Claude returned non-JSON output: {e}")


# ── Wizard → human-readable ICP text ─────────────────────────────────────────
def wizard_to_icp_text(wizard_data: dict) -> str:
    """
    Convert structured wizard data into a human-readable ICP description.

    This text is stored in campaigns.icp_description for display on the
    campaign detail page and in exports.
    """
    vertical = wizard_data.get("vertical", "")
    countries = wizard_data.get("geo_countries", [])
    cities = wizard_data.get("geo_cities", "")
    emp_min = wizard_data.get("employees_min", 10)
    emp_max = wizard_data.get("employees_max", 200)
    multi_location = wizard_data.get("multi_location", False)
    buying_signals = wizard_data.get("buying_signals", [])
    target_titles = wizard_data.get("target_titles", [])
    exclusions = wizard_data.get("exclusions", {})

    geo_desc = ", ".join(countries)
    if cities:
        geo_desc += f" (focus: {cities})"

    excl_parts = []
    if exclusions.get("small_companies"):
        excl_parts.append("<5 employees")
    if exclusions.get("solo_operators"):
        excl_parts.append("solo operators")
    if exclusions.get("regulated_verticals"):
        excl_parts.append("ACA/Medicare/car insurance verticals")

    signal_labels = [_SIGNAL_LABELS.get(s, s) for s in buying_signals]

    lines = [
        f"Vertical: {vertical}",
        f"Geography: {geo_desc}",
        f"Company size: {emp_min}–{emp_max} employees"
        + (" (multi-location preferred)" if multi_location else ""),
        f"Target titles: {', '.join(target_titles)}",
    ]
    if signal_labels:
        lines.append(f"Buying signals: {', '.join(signal_labels)}")
    if excl_parts:
        lines.append(f"Exclusions: {', '.join(excl_parts)}")

    lines += [
        "",
        "Model: Pay-per-lead — buyers only pay when they receive a verified lead.",
        "No retainer, no risk for the buyer.",
    ]

    return "\n".join(lines)
