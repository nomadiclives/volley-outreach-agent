"""4-email sequence generator. Plain text only.

Spam-filter contract:
  _generate_one_email() makes up to 3 Claude calls per email step.
  On each attempt, _check_spam() is run against subject + body.
  If triggers are found, the trigger words are fed back into the next
  prompt so Claude knows exactly what to avoid.

  After 3 failed attempts the email is saved with spam_warning=True and
  a dashboard notification is created. The operator must review it before
  the campaign can send. An email with spam_warning is never silently used.
"""

import json
import logging
import re
from agents.claude_client import claude_call

logger = logging.getLogger(__name__)

MAX_SPAM_ATTEMPTS = 3

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
    """Return list of spam trigger words found in text (case-insensitive)."""
    lower = text.lower()
    return [t for t in SPAM_TRIGGERS if t in lower]


def _parse_email_json(raw: str, step: int) -> dict:
    """Parse Claude's JSON response, stripping markdown fences if present."""
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Email {step} returned non-JSON: {raw[:200]}")


def _ensure_unsubscribe(body: str) -> str:
    """Append unsubscribe footer if not already present."""
    if "unsubscribe" not in body.lower():
        body += "\n\nNot relevant? Reply 'unsubscribe' and I'll remove you."
    return body


def _generate_one_email(system: str, context: str, step: int, config: dict) -> dict:
    """Generate one email with up to MAX_SPAM_ATTEMPTS retries on spam-trigger failure.

    Returns a dict with keys:
        subject       — email subject line
        body          — plain-text body with unsubscribe footer
        spam_warning  — True if all attempts still contained spam triggers
        spam_triggers — list of triggers found on the final attempt (empty if clean)
    """
    last_triggers: list[str] = []
    last_email: dict = {}

    for attempt in range(1, MAX_SPAM_ATTEMPTS + 1):
        user_prompt = context
        if attempt > 1:
            user_prompt += (
                f"\n\nIMPORTANT — REWRITE REQUIRED: Your previous draft contained "
                f"spam trigger words that will hurt email deliverability and get this "
                f"email filtered. You MUST avoid these words entirely in your rewrite: "
                f"{last_triggers}. Do not use synonyms or close variations either."
            )

        raw = claude_call(
            system_prompt=system,
            user_prompt=user_prompt,
            purpose="copywriting",
            config=config,
            max_tokens=600,
        )

        email = _parse_email_json(raw, step)
        full_text = email.get("subject", "") + " " + email.get("body", "")
        triggers = _check_spam(full_text)

        if not triggers:
            if attempt > 1:
                logger.info("Email %d passed spam check on attempt %d", step, attempt)
            email["body"] = _ensure_unsubscribe(email.get("body", ""))
            email["spam_warning"] = False
            email["spam_triggers"] = []
            return email

        logger.warning(
            "Email %d attempt %d/%d — spam triggers found: %s — regenerating",
            step, attempt, MAX_SPAM_ATTEMPTS, triggers,
        )
        last_triggers = triggers
        last_email = email

    # All attempts exhausted — save with warning flag
    logger.error(
        "Email %d still contains spam triggers after %d attempts: %s — saving with spam_warning=True",
        step, MAX_SPAM_ATTEMPTS, last_triggers,
    )
    last_email["body"] = _ensure_unsubscribe(last_email.get("body", ""))
    last_email["spam_warning"] = True
    last_email["spam_triggers"] = last_triggers
    return last_email


def generate_sequence(
    campaign_id: int,
    strategy: dict,
    icp: dict,
    config: dict,
) -> list[dict]:
    """Generate 4-email sequence for a campaign.

    Saves to DB and returns list of sequence step dicts.
    Steps with spam_warning=True are saved and a dashboard notification
    is created — the operator must review them before the campaign can send.
    """
    from core.database import delete_sequences, insert_sequence_step, create_notification

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
        logger.info("Generating email %d for campaign %d...", i, campaign_id)
        email = _generate_one_email(system, context, i, config)

        spam_warning = 1 if email.get("spam_warning") else 0
        step = {
            "campaign_id": campaign_id,
            "step_number": i,
            "subject":     email["subject"],
            "body_text":   email["body"],
            "delay_days":  delay,
            "spam_warning": spam_warning,
        }
        step_id = insert_sequence_step(step)
        step["id"] = step_id
        steps.append(step)

        if spam_warning:
            triggers = email.get("spam_triggers", [])
            create_notification(
                "spam_warning",
                f"Campaign {campaign_id} — Email {i} could not be cleaned after "
                f"{MAX_SPAM_ATTEMPTS} attempts. Spam triggers still present: "
                f"{triggers}. Review this email before approving the campaign.",
            )
            logger.warning(
                "Spam warning notification created for campaign %d email %d",
                campaign_id, i,
            )
        else:
            logger.info(
                "Email %d saved (delay_days=%d): %s", i, delay, email["subject"]
            )

    return steps
