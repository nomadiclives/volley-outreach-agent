"""Lead enrichment: email validation, deduplication, and ICP scoring."""

import json
import logging
from agents.claude_client import claude_call
from core.email_validator import validate_email

logger = logging.getLogger(__name__)

SCORING_PROMPT = """You are a B2B lead quality analyst for a pay-per-lead agency.

Score this lead from 0 to 100 based on ICP fit.

ICP criteria:
{icp_json}

Lead data:
{lead_json}

Scoring rubric:
- Title match to target titles (0-30 pts)
- Seniority level match (0-20 pts)
- Company size in employee range (0-20 pts)
- Industry/vertical match (0-20 pts)
- Data completeness (0-10 pts)

Return ONLY a JSON object:
{"score": 75, "reasoning": "one sentence"}
"""


def enrich_lead(lead: dict, icp: dict, config: dict) -> dict:
    """
    Validate email, score ICP fit, return enriched lead dict.
    Returns None if the lead should be discarded.
    """
    email = (lead.get("email") or "").strip().lower()
    lead["email"] = email

    if email:
        valid, reason = validate_email(email)
        lead["email_verified"] = 1 if valid else 0
        if not valid:
            logger.debug("Email invalid (%s): %s", reason, email)
    else:
        lead["email_verified"] = 0

    # Score with Claude
    try:
        raw = claude_call(
            system_prompt=SCORING_PROMPT.format(
                icp_json=json.dumps(icp, indent=2),
                lead_json=json.dumps(lead, indent=2),
            ),
            user_prompt="Score this lead.",
            purpose="lead_scoring",
            config=config,
            max_tokens=200,
        )
        parsed = json.loads(raw.strip())
        lead["icp_score"] = int(parsed.get("score", 50))
        if not lead.get("notes"):
            lead["notes"] = parsed.get("reasoning", "")
    except Exception as e:
        logger.warning("Lead scoring failed: %s", e)
        lead["icp_score"] = 50

    return lead


def enrich_batch(leads: list[dict], icp: dict, config: dict) -> list[dict]:
    """Enrich a batch of leads. Filters out leads with no email."""
    enriched = []
    for lead in leads:
        try:
            result = enrich_lead(lead, icp, config)
            if result:
                enriched.append(result)
        except Exception as e:
            logger.error("Enrichment failed for %s: %s", lead.get("email"), e)
    return enriched
