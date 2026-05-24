"""Background send scheduler — runs as a daemon thread."""

import logging
import random
import time
import threading
from datetime import datetime, timedelta

import pytz

logger = logging.getLogger(__name__)
_stop_event = threading.Event()


def _in_sending_window(config: dict) -> bool:
    """Return True if current time is within the configured sending window."""
    tz = pytz.timezone(config["outreach"]["timezone"])
    now = datetime.now(tz)
    if config["outreach"]["send_weekdays_only"] and now.weekday() >= 5:
        return False
    start = config["outreach"]["sending_window_start"]
    end = config["outreach"]["sending_window_end"]
    return start <= now.hour < end


def _process_queue(config: dict):
    """Check the send queue and fire any due items."""
    from core.database import get_pending_sends, count_sent_today, update_queue_item, mark_sent, log_outreach
    from integrations.gmail_smtp import send_email

    daily_limit = config["email"]["daily_send_limit"]
    sent_today = count_sent_today()
    if sent_today >= daily_limit:
        logger.info("Daily send limit reached (%d/%d)", sent_today, daily_limit)
        return

    if not _in_sending_window(config):
        return

    pending = get_pending_sends()
    if not pending:
        return

    for item in pending:
        if count_sent_today() >= daily_limit:
            logger.info("Daily limit hit mid-batch, stopping")
            break

        delay = random.randint(
            config["email"]["min_delay_seconds"],
            config["email"]["max_delay_seconds"],
        )

        # Personalise the email
        subject = item["subject"].replace("{first_name}", item["first_name"] or "").replace("{company_name}", item["company_name"] or "")
        body = item["body_text"].replace("{first_name}", item["first_name"] or "").replace("{company_name}", item["company_name"] or "")

        try:
            message_id = send_email(
                to_address=item["email"],
                subject=subject,
                body=body,
                config=config,
            )
            mark_sent(item["id"], message_id)
            update_queue_item(item["id"], "sent")
            logger.info("Sent step %d to %s", item["step_number"], item["email"])
        except Exception as e:
            logger.error("Send failed for %s: %s", item["email"], e)
            attempts = item.get("attempts", 0) + 1
            if attempts >= 3:
                update_queue_item(item["id"], "failed", str(e))
                from core.database import create_notification
                create_notification("send_failure", f"Failed to send to {item['email']} after 3 attempts: {e}")
            else:
                update_queue_item(item["id"], "pending", str(e))

        # Delay between sends (non-blocking if stopping)
        _stop_event.wait(delay)
        if _stop_event.is_set():
            break


def scheduler_loop(config: dict):
    """Main scheduler loop — runs every 5 minutes."""
    from core.reply_handler import poll_gmail_inbox

    reply_poll_interval = 15 * 60  # 15 minutes
    last_reply_poll = 0.0
    check_interval = 5 * 60  # 5 minutes

    logger.info("Scheduler started")
    while not _stop_event.is_set():
        try:
            _process_queue(config)
        except Exception as e:
            logger.error("Scheduler error: %s", e)

        # Poll inbox every 15 minutes
        now = time.monotonic()
        if now - last_reply_poll >= reply_poll_interval:
            try:
                poll_gmail_inbox(config)
            except Exception as e:
                logger.error("Inbox poll error: %s", e)
            last_reply_poll = now

        _stop_event.wait(check_interval)

    logger.info("Scheduler stopped")


def start_scheduler(config: dict) -> threading.Thread:
    """Start scheduler in background thread. Returns thread."""
    t = threading.Thread(target=scheduler_loop, args=(config,), daemon=True, name="volley-scheduler")
    t.start()
    return t


def stop_scheduler():
    _stop_event.set()


def schedule_sequence_for_lead(lead_id: int, campaign_id: int, config: dict):
    """Create send_queue entries for all sequence steps for a lead."""
    from core.database import get_sequences, enqueue_send, count_sent_today
    from datetime import datetime, timedelta
    import pytz

    sequences = get_sequences(campaign_id)
    if not sequences:
        logger.warning("No sequences found for campaign %d", campaign_id)
        return

    tz = pytz.timezone(config["outreach"]["timezone"])
    base_time = datetime.now(tz)
    # Start at the next sending window open
    if base_time.hour >= config["outreach"]["sending_window_end"]:
        base_time = (base_time + timedelta(days=1)).replace(
            hour=config["outreach"]["sending_window_start"], minute=0, second=0
        )
    elif base_time.hour < config["outreach"]["sending_window_start"]:
        base_time = base_time.replace(
            hour=config["outreach"]["sending_window_start"], minute=0, second=0
        )

    for seq in sequences:
        scheduled = base_time + timedelta(days=seq["delay_days"])
        enqueue_send({
            "lead_id": lead_id,
            "campaign_id": campaign_id,
            "sequence_id": seq["id"],
            "step_number": seq["step_number"],
            "scheduled_at": scheduled.strftime("%Y-%m-%d %H:%M:%S"),
        })
    logger.info("Scheduled %d steps for lead %d in campaign %d", len(sequences), lead_id, campaign_id)
