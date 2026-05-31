"""Dashboard / home route."""

from flask import Blueprint, render_template, current_app
from core.database import (
    list_campaigns,
    count_sent_today,
    get_unread_notifications,
    daily_send_volume,
    leads_count,
)
from core.credit_manager import CreditManager

bp = Blueprint("dashboard", __name__)

_PROVIDER_ORDER = ["apollo", "hunter", "lusha", "snov", "getprospect"]


@bp.route("/")
def index():
    config = current_app.config["VOLLEY_CONFIG"]
    campaigns = list_campaigns()

    active = [c for c in campaigns if c["status"] == "active"]
    pending_approval = [c for c in campaigns if c["status"] == "pending_approval"]

    status_counts = {}
    for c in campaigns:
        status_counts[c["status"]] = status_counts.get(c["status"], 0) + 1

    sent_today = count_sent_today()
    daily_limit = config["email"]["daily_send_limit"]
    warmup_active = config["email"]["warmup_active"]
    warmup_day = config["deliverability"].get("warmup_days_elapsed", 0)

    notifications = get_unread_notifications()
    human_replies = [n for n in notifications if n["type"] == "human_reply"]

    raw_balances = CreditManager(config).get_all_balances()
    credit_bank = {p: raw_balances[p] for p in _PROVIDER_ORDER if p in raw_balances}

    return render_template(
        "dashboard.html",
        campaigns=campaigns,
        active_count=len(active),
        pending_count=len(pending_approval),
        status_counts=status_counts,
        sent_today=sent_today,
        daily_limit=daily_limit,
        remaining=max(0, daily_limit - sent_today),
        warmup_active=warmup_active,
        warmup_day=warmup_day,
        notifications=notifications,
        human_replies=human_replies,
        total_leads=leads_count(),
        credit_bank=credit_bank,
    )
