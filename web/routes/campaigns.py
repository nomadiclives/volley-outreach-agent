"""Campaign management routes."""

import json
import threading
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from core.database import (
    list_campaigns, get_campaign, update_campaign_status,
    get_sequences, campaign_stats, list_leads, insert_campaign,
    update_campaign_strategy,
)

bp = Blueprint("campaigns", __name__)


@bp.route("/campaigns")
def index():
    campaigns = list_campaigns()
    stats = {}
    for c in campaigns:
        stats[c["id"]] = campaign_stats(c["id"])
    return render_template("campaigns.html", campaigns=campaigns, stats=stats)


@bp.route("/campaigns/<int:campaign_id>")
def detail(campaign_id: int):
    campaign = get_campaign(campaign_id)
    if not campaign:
        flash("Campaign not found", "error")
        return redirect(url_for("campaigns.index"))

    sequences = get_sequences(campaign_id)
    stats = campaign_stats(campaign_id)
    strategy = {}
    if campaign.get("strategy_json"):
        try:
            strategy = json.loads(campaign["strategy_json"])
        except Exception:
            pass

    return render_template(
        "campaign_detail.html",
        campaign=campaign,
        sequences=sequences,
        stats=stats,
        strategy=strategy,
    )


@bp.route("/campaigns/<int:campaign_id>/approve", methods=["POST"])
def approve(campaign_id: int):
    campaign = get_campaign(campaign_id)
    if not campaign:
        flash("Campaign not found", "error")
        return redirect(url_for("campaigns.index"))

    update_campaign_status(campaign_id, "approved")

    # Enqueue sends for all leads in this campaign
    config = current_app.config["VOLLEY_CONFIG"]
    leads = list_leads(campaign_id=campaign_id, status="approved")
    if not leads:
        leads = list_leads(campaign_id=campaign_id)

    from core.scheduler import schedule_sequence_for_lead
    for lead in leads:
        schedule_sequence_for_lead(lead["id"], campaign_id, config)

    flash(f"Campaign approved — {len(leads)} leads queued for outreach.", "success")
    return redirect(url_for("campaigns.detail", campaign_id=campaign_id))


@bp.route("/campaigns/<int:campaign_id>/reject", methods=["POST"])
def reject(campaign_id: int):
    update_campaign_status(campaign_id, "draft")
    flash("Campaign rejected — returned to draft.", "info")
    return redirect(url_for("campaigns.detail", campaign_id=campaign_id))


@bp.route("/campaigns/<int:campaign_id>/pause", methods=["POST"])
def pause(campaign_id: int):
    update_campaign_status(campaign_id, "paused")
    flash("Campaign paused.", "info")
    return redirect(url_for("campaigns.detail", campaign_id=campaign_id))


@bp.route("/campaigns/<int:campaign_id>/resume", methods=["POST"])
def resume(campaign_id: int):
    update_campaign_status(campaign_id, "active")
    flash("Campaign resumed.", "success")
    return redirect(url_for("campaigns.detail", campaign_id=campaign_id))


@bp.route("/campaigns/<int:campaign_id>/test", methods=["POST"])
def send_test(campaign_id: int):
    config = current_app.config["VOLLEY_CONFIG"]
    recipient = config["email"]["address"]

    def _send():
        from integrations.gmail_smtp import send_test_sequence
        try:
            send_test_sequence(campaign_id, recipient, config)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error("Test send failed: %s", e)

    threading.Thread(target=_send, daemon=True).start()
    flash(f"Test sequence sending to {recipient} — check your inbox in ~5 minutes.", "info")
    return redirect(url_for("campaigns.detail", campaign_id=campaign_id))


@bp.route("/campaigns/create", methods=["GET", "POST"])
def create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        icp = request.form.get("icp_description", "").strip()
        vertical = request.form.get("vertical", "").strip()
        geo = request.form.get("geo", "").strip()

        if not name or not icp:
            flash("Name and ICP description are required.", "error")
            return render_template("campaign_create.html")

        config = current_app.config["VOLLEY_CONFIG"]

        try:
            from agents.icp_analyzer import analyze_icp
            from agents.strategy_generator import generate_strategy
            from agents.copywriter import generate_sequence

            icp_data = analyze_icp(icp, config)
            strategy = generate_strategy(icp_data, name, config)

            campaign_id = insert_campaign({
                "name": name,
                "icp_description": icp,
                "vertical": vertical,
                "geo": geo,
                "strategy_json": json.dumps(strategy),
                "status": "pending_approval",
            })

            generate_sequence(campaign_id, strategy, icp_data, config)

            flash(f"Campaign '{name}' created and ready for approval.", "success")
            return redirect(url_for("campaigns.detail", campaign_id=campaign_id))
        except Exception as e:
            flash(f"Campaign creation failed: {e}", "error")
            return render_template("campaign_create.html")

    return render_template("campaign_create.html")
