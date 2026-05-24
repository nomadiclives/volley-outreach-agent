"""
CRITICAL: Human reply detection and sequence cancellation.

Rules: classify as HUMAN if the reply is NOT an OOO/bounce/automated message.
When in doubt → classify as HUMAN (false positive = cancelled sequence, acceptable;
false negative = spamming a real person, unacceptable).
"""

import imaplib
import email as email_lib
import logging
import re
from datetime import datetime
from typing import Optional

from core.database import (
    get_lead_by_email,
    cancel_future_steps,
    mark_replied,
    update_lead_status,
    create_notification,
    get_outreach_log,
)
from integrations.google_sheets import sync_lead_status

logger = logging.getLogger(__name__)

# Patterns that indicate automated / OOO messages
OOO_PATTERNS = [
    r"out of office",
    r"away from",
    r"on vacation",
    r"annual leave",
    r"will be back",
    r"automatic reply",
    r"auto-?reply",
    r"autoreply",
    r"on holiday",
    r"i am currently out",
    r"i'm currently out",
    r"i will be out",
    r"currently unavailable",
    r"currently away",
]

UNSUBSCRIBE_PATTERNS = [
    r"\bunsubscribe\b",
    r"\bremove me\b",
    r"\bstop emailing\b",
    r"\bopt out\b",
    r"\btake me off\b",
    r"\bplease remove\b",
]

BOUNCE_PATTERNS = [
    r"mailer.daemon",
    r"postmaster",
    r"delivery.*failed",
    r"undelivered mail",
    r"mail delivery failure",
    r"message not delivered",
    r"5\d\d .*error",
    r"user.*does not exist",
    r"no such user",
    r"account.*disabled",
    r"mailbox.*full",
]


def _matches_any(text: str, patterns: list[str]) -> bool:
    text_lower = text.lower()
    return any(re.search(p, text_lower) for p in patterns)


def classify_reply(
    from_address: str,
    subject: str,
    body: str,
) -> tuple[bool, str]:
    """
    Returns (is_human, classification).

    classification: 'human_interested' | 'human_not_interested' | 'unsubscribe' |
                    'ooo' | 'bounce' | 'human_unknown'
    """
    from_lower = from_address.lower()
    body_lower = body.lower()

    # Bounce check — sender address
    if _matches_any(from_lower, [r"mailer.daemon", r"postmaster"]):
        return False, "bounce"

    # Bounce check — body content
    if _matches_any(body_lower, BOUNCE_PATTERNS):
        word_count = len(body.split())
        if word_count < 30:  # real bounce messages are usually short
            return False, "bounce"

    # OOO check
    if _matches_any(body_lower, OOO_PATTERNS):
        return False, "ooo"

    # Unsubscribe request — still human, but special handling
    if _matches_any(body_lower, UNSUBSCRIBE_PATTERNS):
        return True, "unsubscribe"

    # Short replies with no other signals → treat as human
    word_count = len(body.split())
    if word_count < 10 and not _matches_any(body_lower, BOUNCE_PATTERNS):
        return True, "human_unknown"

    # Default: treat as human
    positive_signals = [
        r"\binterested\b", r"\btell me more\b", r"\bsound[s]? good\b",
        r"\blet[']?s\b", r"\bcall\b", r"\bscheduled?\b", r"\byes\b",
    ]
    negative_signals = [
        r"\bnot interested\b", r"\bno thanks\b", r"\bdon[']?t contact\b",
        r"\bplease don[']?t\b", r"\bwrong person\b",
    ]

    if _matches_any(body_lower, positive_signals):
        return True, "human_interested"
    if _matches_any(body_lower, negative_signals):
        return True, "human_not_interested"

    return True, "human_unknown"


def handle_reply(
    from_address: str,
    subject: str,
    body: str,
    in_reply_to: Optional[str] = None,
    message_id: Optional[str] = None,
):
    """
    Main entry point for a detected reply. Finds the lead, classifies the reply,
    and immediately cancels future sequence steps if it's human.
    """
    is_human, classification = classify_reply(from_address, subject, body)
    logger.info(
        "Reply from %s | human=%s | classification=%s",
        from_address, is_human, classification,
    )

    lead = get_lead_by_email(from_address)
    if not lead:
        # Try to match via Message-ID / In-Reply-To
        logger.warning("Could not find lead for %s — no DB record", from_address)
        return

    lead_id = lead["id"]

    # Find the most recent sent outreach log entry for this lead
    log_entries = get_outreach_log(lead_id)
    sent_entries = [e for e in log_entries if e["status"] in ("sent", "opened")]
    if not sent_entries:
        logger.warning("Reply from %s but no sent outreach found", from_address)
        return

    latest = sent_entries[-1]
    campaign_id = latest["campaign_id"]

    # Mark the log entry as replied
    mark_replied(latest["id"], is_human, classification)

    if is_human:
        # IMMEDIATELY cancel all future steps — non-negotiable
        cancel_future_steps(lead_id, campaign_id)
        update_lead_status(lead_id, "replied")

        # Sync to Google Sheets
        try:
            sync_lead_status(lead_id, "replied")
        except Exception as e:
            logger.error("Sheets sync failed: %s", e)

        msg = f"Human reply from {from_address} [{classification}] — all future steps cancelled"
        logger.info(msg)
        create_notification(
            "human_reply",
            f"Reply from {lead.get('first_name', '')} {lead.get('last_name', '')} "
            f"<{from_address}> — {classification}. Sequence stopped.",
        )

        # Absolute unsubscribe
        if classification == "unsubscribe":
            update_lead_status(lead_id, "unsubscribed")
            sync_lead_status(lead_id, "unsubscribed")
            create_notification(
                "unsubscribe",
                f"Unsubscribe request from {from_address} — permanently removed.",
            )
            logger.info("Unsubscribe: %s permanently removed from all sequences", from_address)


# ── Gmail Inbox Poller ────────────────────────────────────────────────────────

def poll_gmail_inbox(config: dict):
    """Poll Gmail IMAP every 15 minutes for replies to handle."""
    email_cfg = config.get("email", {})
    address = email_cfg.get("address", "")
    app_password = email_cfg.get("app_password", "")

    if not address or not app_password:
        logger.warning("Gmail credentials not configured — skipping inbox poll")
        return

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(address, app_password)
        mail.select("INBOX")

        # Search for unseen messages
        _, data = mail.search(None, "UNSEEN")
        if not data or not data[0]:
            mail.logout()
            return

        msg_ids = data[0].split()
        logger.info("Inbox poll: %d unseen messages", len(msg_ids))

        for msg_id in msg_ids:
            try:
                _, msg_data = mail.fetch(msg_id, "(RFC822)")
                raw = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw)

                from_addr = email_lib.utils.parseaddr(msg.get("From", ""))[1]
                subject = msg.get("Subject", "")
                in_reply_to = msg.get("In-Reply-To", "")
                message_id = msg.get("Message-ID", "")

                # Extract plain text body
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            break
                else:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

                handle_reply(from_addr, subject, body, in_reply_to, message_id)

            except Exception as e:
                logger.error("Error processing message %s: %s", msg_id, e)

        mail.logout()

    except Exception as e:
        logger.error("Gmail IMAP poll failed: %s", e)
