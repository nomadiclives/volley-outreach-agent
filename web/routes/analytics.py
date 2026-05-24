"""Analytics dashboard routes."""

import json
from flask import Blueprint, render_template
from core.database import (
    list_campaigns, campaign_stats, daily_send_volume,
    get_monthly_claude_cost, get_claude_cost_by_purpose,
)

bp = Blueprint("analytics", __name__)


@bp.route("/analytics")
def index():
    campaigns = list_campaigns()
    all_stats = {}
    total_sent = total_opened = total_replied = 0

    for c in campaigns:
        s = campaign_stats(c["id"])
        all_stats[c["id"]] = s
        total_sent += s["sent"]
        total_opened += s["opened"]
        total_replied += s["replied"]

    # Deliverability health
    overall_open_rate = round(total_opened / total_sent * 100, 1) if total_sent else 0
    overall_reply_rate = round(total_replied / total_sent * 100, 1) if total_sent else 0

    # Time series for Chart.js
    daily = daily_send_volume(30)
    chart_labels = json.dumps([d["send_date"] for d in daily])
    chart_data = json.dumps([d["count"] for d in daily])

    # API cost
    monthly_cost = get_monthly_claude_cost()
    cost_by_purpose = get_claude_cost_by_purpose()

    return render_template(
        "analytics.html",
        campaigns=campaigns,
        all_stats=all_stats,
        total_sent=total_sent,
        total_opened=total_opened,
        total_replied=total_replied,
        overall_open_rate=overall_open_rate,
        overall_reply_rate=overall_reply_rate,
        chart_labels=chart_labels,
        chart_data=chart_data,
        monthly_cost=monthly_cost,
        cost_by_purpose=cost_by_purpose,
    )
