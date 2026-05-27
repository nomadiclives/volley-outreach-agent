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
    """
    New Campaign — structured 6-step ICP wizard.

    Wizard steps:
      1. Vertical       — campaign name + industry dropdown
      2. Geography      — multi-select countries + optional cities
      3. Company        — employee range sliders + multi-location toggle
      4. Buying Signals — checkbox signal cards
      5. Target Titles  — default chips (all pre-checked) + custom additions
      6. Exclusions     — auto-reject rules (pre-checked, overridable)

    ICP description text is auto-generated from the wizard inputs via
    wizard_to_icp_text(). Apollo search params are produced by
    analyze_icp_from_wizard() which calls Claude once per campaign.
    """
    if request.method == "POST":
        # ── Step 1 ─────────────────────────────────────────────────────────
        name = request.form.get("name", "").strip()
        vertical = request.form.get("vertical", "").strip()
        vertical_custom = request.form.get("vertical_custom", "").strip()

        # If user chose "Other", use the custom text field
        if vertical == "other":
            vertical = vertical_custom

        # ── Step 2 ─────────────────────────────────────────────────────────
        geo_countries = request.form.getlist("geo_countries")   # multi-value
        geo_cities    = request.form.get("geo_cities", "").strip()

        # ── Step 3 ─────────────────────────────────────────────────────────
        try:
            employees_min = int(request.form.get("employees_min", 10))
            employees_max = int(request.form.get("employees_max", 200))
        except (TypeError, ValueError):
            employees_min, employees_max = 10, 200
        multi_location = request.form.get("multi_location") == "yes"

        # ── Step 4 ─────────────────────────────────────────────────────────
        buying_signals = request.form.getlist("buying_signals")  # multi-value

        # ── Step 5 ─────────────────────────────────────────────────────────
        target_titles = request.form.getlist("target_titles")    # multi-value

        # ── Step 6 ─────────────────────────────────────────────────────────
        exclusions = {
            "small_companies":     request.form.get("excl_small_cos") == "on",
            "solo_operators":      request.form.get("excl_solo_ops")  == "on",
            "regulated_verticals": request.form.get("excl_regulated") == "on",
        }

        # ── Validation ─────────────────────────────────────────────────────
        errors = []
        if not name:
            errors.append("Campaign name is required.")
        if not vertical:
            errors.append("Vertical is required.")
        if not geo_countries:
            errors.append("At least one target country is required.")
        if not target_titles:
            errors.append("At least one target title is required.")

        if errors:
            for msg in errors:
                flash(msg, "error")
            return render_template("campaign_create.html")

        # ── Bundle wizard data ──────────────────────────────────────────────
        wizard_data = {
            "vertical":      vertical,
            "geo_countries": geo_countries,
            "geo_cities":    geo_cities,
            "employees_min": employees_min,
            "employees_max": employees_max,
            "multi_location": multi_location,
            "buying_signals": buying_signals,
            "target_titles":  target_titles,
            "exclusions":     exclusions,
        }

        # Compact geo string for campaigns.geo column
        geo_str = ", ".join(geo_countries)
        if geo_cities:
            geo_str += f" ({geo_cities})"

        config = current_app.config["VOLLEY_CONFIG"]

        try:
            from agents.icp_analyzer import analyze_icp_from_wizard, wizard_to_icp_text
            from agents.strategy_generator import generate_strategy
            from agents.copywriter import generate_sequence

            # Auto-generate the ICP description text from wizard inputs
            icp_description = wizard_to_icp_text(wizard_data)

            # Get structured Apollo params via Claude
            icp_data = analyze_icp_from_wizard(wizard_data, config)

            # Generate outreach strategy
            strategy = generate_strategy(icp_data, name, config)

            # Persist campaign
            campaign_id = insert_campaign({
                "name":            name,
                "icp_description": icp_description,
                "vertical":        vertical,
                "geo":             geo_str,
                "strategy_json":   json.dumps(strategy),
                "status":          "pending_approval",
            })

            # Generate 4-email sequence
            generate_sequence(campaign_id, strategy, icp_data, config)

            flash(f"Campaign '{name}' created and ready for approval.", "success")
            return redirect(url_for("campaigns.detail", campaign_id=campaign_id))

        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Campaign creation failed")
            flash(f"Campaign creation failed: {e}", "error")
            return render_template("campaign_create.html")

    return render_template("campaign_create.html")
