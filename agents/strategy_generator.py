"""AI-powered outreach strategy generator."""

import json
import logging
from agents.claude_client import claude_call

logger = logging.getLogger(__name__)

# Informed by the sales-outbound-strategist agent: research-driven outreach,
# signal-based prospecting, and the "research not volume" philosophy.
SYSTEM_PROMPT = """You are a senior B2B cold outreach strategist for a pay-per-lead agency.

The agency's model: we deliver pre-qualified leads on a pay-per-lead basis.
Zero retainer. Zero risk for the buyer. They only pay when they receive a lead.

Your approach:
- Research-driven outreach, not volume spray
- Every strategy is built around the buyer's specific pain, not generic pitches
- You identify the single most compelling hook before writing a word of copy
- You think in signals: what recent events, growth patterns, or business changes make THIS buyer need leads NOW?
- Multi-touch sequences, but each touch adds value — never just "following up"

Generate a complete outreach strategy for the given ICP.
Return ONLY valid JSON — no preamble, no markdown.

Required format:
{
  "value_prop": "one crisp sentence — what the buyer gets",
  "hook": "the single most compelling angle for this ICP",
  "primary_signal": "what triggers a buyer to be in-market for leads right now",
  "sequence_rationale": "why this 4-email cadence works for this buyer type",
  "email1_angle": "specific angle for first email",
  "email2_angle": "specific angle for second email — must differ from email1",
  "email3_angle": "social proof angle — similar company type reference",
  "email4_angle": "break-up email framing",
  "risk_factors": ["what could undermine this campaign"],
  "success_metrics": {"target_open_rate": "X%", "target_reply_rate": "X%", "target_positive_rate": "X%"},
  "ab_test_ideas": ["idea 1", "idea 2"]
}
"""


def generate_strategy(icp: dict, campaign_name: str, config: dict) -> dict:
    """
    Generate an outreach strategy for the given ICP.
    Returns parsed strategy dict.
    """
    user_prompt = f"""
Campaign: {campaign_name}
ICP summary:
- Verticals: {', '.join(icp.get('verticals', []))}
- Target titles: {', '.join(icp.get('target_titles', []))}
- Employee range: {icp.get('employee_range', {})}
- Locations: {', '.join(loc.get('country', '') for loc in icp.get('locations', []))}
- Pain points: {'; '.join(icp.get('pain_points', []))}
- ICP rationale: {icp.get('icp_rationale', '')}
- Estimated market: {icp.get('estimated_market_size', '')}

Generate the outreach strategy.
"""
    raw = claude_call(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        purpose="strategy_generation",
        config=config,
        max_tokens=1500,
    )

    try:
        result = json.loads(raw.strip())
        logger.info("Strategy generated: hook=%s", result.get("hook", "")[:80])
        return result
    except json.JSONDecodeError as e:
        logger.error("Strategy generator invalid JSON: %s\nRaw: %s", e, raw[:500])
        raise ValueError(f"Strategy generation failed: {e}")
