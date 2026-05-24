"""Parse an ICP description into structured Apollo search parameters."""

import json
import logging
from agents.claude_client import claude_call

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior B2B sales strategist specialising in lead generation agencies.

Your task: convert an ICP (Ideal Customer Profile) description into structured search parameters.

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
Pain points should describe specifically what a lead gen agency on pay-per-lead model solves for this buyer.
"""


def analyze_icp(icp_description: str, config: dict) -> dict:
    """
    Convert a free-text ICP description into structured search criteria.
    Returns parsed dict.
    """
    raw = claude_call(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=f"ICP description:\n{icp_description}",
        purpose="icp_analysis",
        config=config,
        max_tokens=1000,
    )

    try:
        result = json.loads(raw.strip())
        logger.info(
            "ICP analysis: %d verticals, %d title types, locations=%s",
            len(result.get("verticals", [])),
            len(result.get("target_titles", [])),
            [loc["country"] for loc in result.get("locations", [])],
        )
        return result
    except json.JSONDecodeError as e:
        logger.error("ICP analyzer returned invalid JSON: %s\nRaw: %s", e, raw[:500])
        raise ValueError(f"ICP analysis failed — Claude returned non-JSON output: {e}")
