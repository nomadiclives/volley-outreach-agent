"""4-email sequence generator. Plain text only."""

import json
import logging
import re
from agents.claude_client import claude_call

logger = logging.getLogger(__name__)

SPAM_TRIGGERS = [
    "free", "guaranteed", "no obligation", "act now", "limited time",
    "click here", "buy now", "earn money", "100%", "risk-free",
    "double your", "increase sales", "make money", "opportunity",
    "winner", "selected", "congratulations", "!!!",
]

# Email 1 informed by sales-discovery-coach SPIN methodology:
# opening questions should make prospects think, not just respond.
EMAIL1_SYSTEM = """You write cold outreach email #1 for a pay-per-lead agency.

Rules:
- Max 80 words in body
- Plain text only — no HTML, no formatting, no bold
- Subject line: specific question or pattern interrupt (NOT generic)
- Opening: a discovery question using SPIN methodology (Situation → Problem → Implication)
  Make the prospect think about a real problem, not just react to a pitch
- Structure: Problem → Implication → Solution teaser
- CTA: Single low-friction ask e.g. "does this make sense for {company_name}?"
- Include {first_name} and {company_name} tokens
- No buzzwords, no hype
- Unsubscribe line at end: "Not relevant? Reply 'unsubscribe' and I'll remove you."
- Return ONLY JSON: {"subject": "...", "body": "..."}
"""

EMAIL2_SYSTEM = """You write cold outreach email #2 for a pay-per-lead agency.

This is the value-add follow-up. Rules:
- Max 70 words
- Plain text only
- Subject: completely different angle from Email 1 — new frame, new hook
- Add specific proof point, result, or industry insight
- Soft CTA — no pressure
- Include {first_name} and {company_name} tokens
- Unsubscribe line at end
- Return ONLY JSON: {"subject": "...", "body": "..."}
"""

EMAIL3_SYSTEM = """You write cold outreach email #3 for a pay-per-lead agency.

This is the social proof email. Rules:
- Max 100 words
- Plain text only
- Subject: reference a similar company type (not a specific named company — keep it general)
- Include a concrete result or case study reference (e.g. "a [industry] company we work with...")
- Slightly stronger CTA than Email 2
- Include {first_name} and {company_name} tokens
- Unsubscribe line at end
- Return ONLY JSON: {"subject": "...", "body": "..."}
"""

EMAIL4_SYSTEM = """You write cold outreach email #4 — the break-up email.

Rules:
- Subject MUST be: "Should I stop reaching out, {first_name}?"
- Body: exactly 3 sentences maximum
- Classic permission-to-say-no format — no pitch, no value prop
- This email has the highest response rate: keep it ultra-short and human
- No CTA beyond "just let me know either way"
- Include {first_name} token
- Unsubscribe line at end
- Return ONLY JSON: {"subject": "...", "body": "..."}
"""

DELAY_DAYS = [0, 4, 10, 18]
SYSTEMS = [EMAIL1_SYSTEM, EMAIL2_SYSTEM, EMAIL3_SYSTEM, EMAIL4_SYSTEM]


def _check_spam(text: str) -> list[str]:
    """Return list of spam trigger words found in text."""
    lower = text.lower()
    return [t for t in SPAM_TRIGGERS if t in lower]


def _generate_one_email(system: str, context: str, step: int, config: dict) -> dict:
    raw = claude_call(
        system_prompt=system,
        user_prompt=context,
        purpose="copywriting",
        config=config,
        max_tokens=600,
    )
    try:
        email = json.loads(raw.strip())
    except json.JSONDecodeError:
        # Try to extract JSON from the response
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            email = json.loads(match.group())
        else:
            raise ValueError(f"Email {step} returned non-JSON: {raw[:200]}")

    triggers = _check_spam(email.get("subject", "") + " " + email.get("body", ""))
    if triggers:
        logger.warning("Email %d has spam triggers: %s", step, triggers)

    # Ensure unsubscribe footer
    body = email.get("body", "")
    if "unsubscribe" not in body.lower():
        body += "\n\nNot relevant? Reply 'unsubscribe' and I'll remove you."
    email["body"] = body

    return email


def generate_sequence(
    campaign_id: int,
    strategy: dict,
    icp: dict,
    config: dict,
) -> list[dict]:
    """
    Generate 4-email sequence for a campaign.
    Saves to DB and returns list of sequence step dicts.
    """
    from core.database import delete_sequences, insert_sequence_step

    context = f"""
Campaign strategy:
- Value prop: {strategy.get('value_prop', '')}
- Hook: {strategy.get('hook', '')}
- Primary signal: {strategy.get('primary_signal', '')}
- Email 1 angle: {strategy.get('email1_angle', '')}
- Email 2 angle: {strategy.get('email2_angle', '')}
- Email 3 angle: {strategy.get('email3_angle', '')}
- Email 4 angle: {strategy.get('email4_angle', '')}

ICP:
- Verticals: {', '.join(icp.get('verticals', []))}
- Target titles: {', '.join(icp.get('target_titles', []))}
- Pain points: {'; '.join(icp.get('pain_points', []))}
"""

    delete_sequences(campaign_id)
    steps = []

    for i, (system, delay) in enumerate(zip(SYSTEMS, DELAY_DAYS), start=1):
        logger.info("Generating email %d...", i)
        email = _generate_one_email(system, context, i, config)
        step = {
            "campaign_id": campaign_id,
            "step_number": i,
            "subject": email["subject"],
            "body_text": email["body"],
            "delay_days": delay,
        }
        step_id = insert_sequence_step(step)
        step["id"] = step_id
        steps.append(step)
        logger.info("Email %d saved (delay_days=%d): %s", i, delay, email["subject"])

    return steps
