"""Email sending via Gmail SMTP with full deliverability headers."""

import logging
import smtplib
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


def _build_message(
    from_address: str,
    to_address: str,
    subject: str,
    body: str,
    campaign_id: int = 0,
    lead_id: int = 0,
    in_reply_to: str = "",
    references: str = "",
) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["From"] = from_address
    msg["To"] = to_address
    msg["Subject"] = subject
    msg["Message-ID"] = f"<{uuid.uuid4()}@volley>"
    msg["Reply-To"] = from_address
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
    msg["X-Campaign-ID"] = str(campaign_id)
    msg["X-Lead-ID"] = str(lead_id)
    msg.attach(MIMEText(body, "plain"))
    return msg


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=5, max=60))
def send_email(
    to_address: str,
    subject: str,
    body: str,
    config: dict,
    campaign_id: int = 0,
    lead_id: int = 0,
    in_reply_to: str = "",
    references: str = "",
) -> str:
    """
    Send a plain-text email via Gmail SMTP.
    Returns the Message-ID string.
    Raises on failure (tenacity retries up to 3x).
    """
    email_cfg = config["email"]
    from_address = email_cfg["address"]
    app_password = email_cfg["app_password"]

    msg = _build_message(
        from_address=from_address,
        to_address=to_address,
        subject=subject,
        body=body,
        campaign_id=campaign_id,
        lead_id=lead_id,
        in_reply_to=in_reply_to,
        references=references,
    )
    message_id = msg["Message-ID"]

    with smtplib.SMTP(email_cfg["smtp_host"], email_cfg["smtp_port"]) as server:
        server.ehlo()
        server.starttls()
        server.login(from_address, app_password)
        server.sendmail(from_address, [to_address], msg.as_string())

    logger.info("Sent email to %s subject=%r message_id=%s", to_address, subject, message_id)
    return message_id


def send_test_sequence(campaign_id: int, recipient: str, config: dict):
    """Send all 4 sequence emails to the operator's own address for review."""
    from core.database import get_sequences
    import time

    sequences = get_sequences(campaign_id)
    for seq in sequences:
        subject = f"[TEST] Step {seq['step_number']}: {seq['subject']}"
        body = seq["body_text"].replace("{first_name}", "Test").replace("{company_name}", "TestCo")
        try:
            send_email(to_address=recipient, subject=subject, body=body, config=config, campaign_id=campaign_id)
            logger.info("Test email %d sent to %s", seq["step_number"], recipient)
            if seq["step_number"] < len(sequences):
                time.sleep(60)  # 1-minute gap between test emails
        except Exception as e:
            logger.error("Test email send failed: %s", e)
            raise
