"""Reply classification agent — uses thread reconstruction logic."""

import json
import logging
from agents.claude_client import claude_call

logger = logging.getLogger(__name__)

# Informed by the engineering-email-intelligence-engineer agent:
# thread reconstruction, quoted reply deduplication, and participant detection.
SYSTEM_PROMPT = """You are an email intelligence analyst. Classify a reply to a cold outreach email.

Your rules:
1. Reconstruct the thread — strip all quoted text below the first "On ... wrote:" line
2. Classify based only on the NEW content written by the responder
3. If forwarded or CC'd to a different person, note that in participant_note
4. Never classify based on the quoted outreach email — only the reply content

Classification labels:
- "interested" — positive signal: wants more info, open to a call, asking questions
- "not_interested" — explicit no: not the right time, not relevant, already have a solution
- "unsubscribe" — any form of remove/unsubscribe/stop request
- "referral" — directing you to another person ("talk to X")
- "ooo" — out of office, vacation, leave
- "bounce" — delivery failure, no such user
- "unknown" — ambiguous, too short to classify

Return ONLY JSON:
{
  "classification": "interested",
  "confidence": 0.9,
  "is_human": true,
  "clean_reply": "the reply text stripped of quoted content",
  "participant_note": "if forwarded/CC'd — who else is involved",
  "action": "one-sentence recommended action for the operator"
}
"""


def _strip_quoted_content(body: str) -> str:
    """Remove quoted email chains from reply body."""
    # Common quote delimiters
    delimiters = [
        "On ", "-----Original Message-----", "From:", "> ", "__________",
    ]
    for delimiter in delimiters:
        idx = body.find(delimiter)
        if idx > 50:  # Only strip if there's substantial content before it
            body = body[:idx].strip()
            break
    return body


def classify_reply_with_ai(
    from_address: str,
    subject: str,
    body: str,
    config: dict,
) -> dict:
    """
    Full AI classification for ambiguous replies.
    Falls back to rule-based classifier on error.
    """
    clean_body = _strip_quoted_content(body)

    user_prompt = f"""
From: {from_address}
Subject: {subject}
Reply body (may include quoted content to strip):
---
{body[:2000]}
---
Clean reply text (pre-stripped):
{clean_body[:500]}

Classify this reply.
"""
    try:
        raw = claude_call(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            purpose="reply_classification",
            config=config,
            max_tokens=400,
        )
        result = json.loads(raw.strip())
        logger.info(
            "AI classified reply from %s: %s (confidence=%.2f)",
            from_address,
            result.get("classification"),
            result.get("confidence", 0),
        )
        return result
    except Exception as e:
        logger.error("AI reply classification failed: %s — using rule-based", e)
        # Fallback to rule-based
        from core.reply_handler import classify_reply
        is_human, classification = classify_reply(from_address, subject, body)
        return {
            "classification": classification,
            "confidence": 0.7,
            "is_human": is_human,
            "clean_reply": clean_body,
            "participant_note": "",
            "action": "Review and respond manually" if is_human else "No action needed",
        }
