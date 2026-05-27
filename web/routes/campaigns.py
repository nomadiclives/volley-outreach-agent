"""Campaign management routes."""

import json
import logging
import threading
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from core.database import (
    list_campaigns, get_campaign, update_campaign_status,
    get_sequences, campaign_stats, list_leads, insert_campaign,
    update_campaign_strategy, get_apollo_credits_used, link_lead_to_campaign,
)

logger = logging.getLogger(__name__)
bp = Blueprint("campaigns", __name__)

APOLLO_MONTHLY_LIMIT = 75  # free tier cap; mirrors config default


def _apollo_credits_remaining(config: dict) -> int:
    """Return remaining Apollo credits for this calendar month."""
    limit = int(config.get("apollo", {}).get("monthly_credit_limit", APOLLO_MONTHLY_LIMIT))
    used = get_apollo_credits_used()
    return max(0, limit - used)


def _parse_wizard_form(form) -> tuple[dict, list[str]]:
    """Extract and validate the 6-step wizard form fields.

    Returns (wizard_data, errors).  wizard_data is empty dict on validation failure.
    """
    errors = []

    name = form.get("name", "").strip()
    vertical = form.get("vertical", "").strip()
    if vertical == "other":
        vertical = form.get("vertical_custom", "").strip()

    geo_countries = form.getlist("geo_countries")
    geo_cities = form.get("geo_cities", "").strip()

    try:
        employees_min = int(form.get("employees_min", 10))
        employees_max = int(form.get("employees_max", 200))
    except (TypeError, ValueError):
        employees_min, employees_max = 10, 200

    multi_location = form.get("multi_location") == "yes"
    buying_signals = form.getlist("buying_signals")
    target_titles = form.getlist("target_titles")
    exclusions = {
        "small_companies":     form.get("excl_small_cos") == "on",
        "solo_operators":      form.get("excl_solo_ops") == "on",
        "regulated_verticals": form.get("excl_regulated") == "on",
    }

    try:
        lead_limit = int(form.get("lead_limit", 10))
        lead_limit = max(1, lead_limit)
    except (TypeError, ValueError):
        lead_limit = 10

    if not name:
        errors.append("Campaign name is required.")
    if not vertical:
        errors.append("Vertical is required.")
    if not geo_countries:
        errors.append("At least one target country is required.")
    if not target_titles:
        errors.append("At least one target title is required.")

    if errors:
        return {}, errors

    geo_str = ", ".join(geo_countries)
    if geo_cities:
        geo_str += f" ({geo_cities})"

    wizard_data = {
        "vertical":       vertical,
        "geo_countries":  geo_countries,
        "geo_cities":     geo_cities,
        "employees_min":  employees_min,
        "employees_max":  employees_max,
        "multi_location": multi_location,
        "buying_signals": buying_signals,
        "target_titles":  target_titles,
        "exclusions":     exclusions,
        "lead_limit":     lead_limit,
        "geo_str":        geo_str,
        "name":           name,
    }
    return wizard_data, []


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


@bp.route("/api/apollo-credits")
def apollo_credits():
    """Return remaining Apollo credits for this calendar month as JSON."""
    config = current_app.config["VOLLEY_CONFIG"]
    remaining = _apollo_credits_remaining(config)
    limit = int(config.get("apollo", {}).get("monthly_credit_limit", APOLLO_MONTHLY_LIMIT))
    return jsonify({"remaining": remaining, "limit": limit, "used": limit - remaining})


@bp.route("/campaigns/find-leads", methods=["POST"])
def find_leads_route():
    """Find and score leads from the ICP wizard. No AI copy generated, no Claude cost."""
    config = current_app.config["VOLLEY_CONFIG"]
    wizard_data, errors = _parse_wizard_form(request.form)

    if errors:
        for msg in errors:
            flash(msg, "error")
        return render_template("campaign_create.html")

    # Check Apollo credits before proceeding
    remaining = _apollo_credits_remaining(config)
    lead_limit = min(wizard_data["lead_limit"], remaining)
    if remaining <= 0:
        flash("No Apollo credits remaining this month. Use 'Generate Strategy & Sequence Only' instead.", "error")
        return render_template("campaign_create.html")

    try:
        from agents.icp_analyzer import analyze_icp_from_wizard, wizard_to_icp_text
        from agents.lead_finder import find_leads

        icp_description = wizard_to_icp_text(wizard_data)
        icp_data = analyze_icp_from_wizard(wizard_data, config)

        campaign_id = insert_campaign({
            "name":            wizard_data["name"],
            "icp_description": icp_description,
            "vertical":        wizard_data["vertical"],
            "geo":             wizard_data["geo_str"],
            "strategy_json":   None,
            "status":          "draft",
        })

        leads = find_leads(icp_description, config, limit=lead_limit, icp_data=icp_data)

        linked = 0
        for lead in leads:
            if lead.get("id"):
                link_lead_to_campaign(lead["id"], campaign_id)
                linked += 1

        flash(
            f"Found {linked} leads for '{wizard_data['name']}'. "
            f"Generate a sequence when ready to begin outreach.",
            "success",
        )
        return redirect(url_for("campaigns.detail", campaign_id=campaign_id))

    except Exception:
        logger.exception("Find leads failed")
        flash("Lead search failed — check the logs for details.", "error")
        return render_template("campaign_create.html")


@bp.route("/campaigns/generate-sequence", methods=["POST"])
def generate_sequence_route():
    """Generate ICP strategy + 4-email sequence. No Apollo credits used. ~€0.02 Claude cost."""
    config = current_app.config["VOLLEY_CONFIG"]
    wizard_data, errors = _parse_wizard_form(request.form)

    if errors:
        for msg in errors:
            flash(msg, "error")
        return render_template("campaign_create.html")

    try:
        from agents.icp_analyzer import analyze_icp_from_wizard, wizard_to_icp_text
        from agents.strategy_generator import generate_strategy
        from agents.copywriter import generate_sequence

        icp_description = wizard_to_icp_text(wizard_data)
        icp_data = analyze_icp_from_wizard(wizard_data, config)
        strategy = generate_strategy(icp_data, wizard_data["name"], config)

        campaign_id = insert_campaign({
            "name":            wizard_data["name"],
            "icp_description": icp_description,
            "vertical":        wizard_data["vertical"],
            "geo":             wizard_data["geo_str"],
            "strategy_json":   json.dumps(strategy),
            "status":          "pending_approval",
        })

        generate_sequence(campaign_id, strategy, icp_data, config)

        flash(
            f"Strategy and 4-email sequence generated for '{wizard_data['name']}'. "
            f"Review and approve to start outreach.",
            "success",
        )
        return redirect(url_for("campaigns.detail", campaign_id=campaign_id))

    except Exception:
        logger.exception("Generate sequence failed")
        flash("Sequence generation failed — check the logs for details.", "error")
        return render_template("campaign_create.html")


@bp.route("/campaigns/find-and-generate", methods=["POST"])
def find_and_generate_route():
    """Find leads AND generate strategy + sequence in one pass."""
    config = current_app.config["VOLLEY_CONFIG"]
    wizard_data, errors = _parse_wizard_form(request.form)

    if errors:
        for msg in errors:
            flash(msg, "error")
        return render_template("campaign_create.html")

    remaining = _apollo_credits_remaining(config)
    lead_limit = min(wizard_data["lead_limit"], remaining)
    if remaining <= 0:
        flash("No Apollo credits remaining this month. Use 'Generate Strategy & Sequence Only' instead.", "error")
        return render_template("campaign_create.html")

    try:
        from agents.icp_analyzer import analyze_icp_from_wizard, wizard_to_icp_text
        from agents.strategy_generator import generate_strategy
        from agents.copywriter import generate_sequence
        from agents.lead_finder import find_leads

        icp_description = wizard_to_icp_text(wizard_data)
        icp_data = analyze_icp_from_wizard(wizard_data, config)
        strategy = generate_strategy(icp_data, wizard_data["name"], config)

        campaign_id = insert_campaign({
            "name":            wizard_data["name"],
            "icp_description": icp_description,
            "vertical":        wizard_data["vertical"],
            "geo":             wizard_data["geo_str"],
            "strategy_json":   json.dumps(strategy),
            "status":          "pending_approval",
        })

        generate_sequence(campaign_id, strategy, icp_data, config)
        leads = find_leads(icp_description, config, limit=lead_limit, icp_data=icp_data)

        linked = 0
        for lead in leads:
            if lead.get("id"):
                link_lead_to_campaign(lead["id"], campaign_id)
                linked += 1

        flash(
            f"Campaign '{wizard_data['name']}' ready — {linked} leads found, "
            f"strategy and sequence generated. Review and approve to start outreach.",
            "success",
        )
        return redirect(url_for("campaigns.detail", campaign_id=campaign_id))

    except Exception:
        logger.exception("Find-and-generate failed")
        flash("Campaign creation failed — check the logs for details.", "error")
        return render_template("campaign_create.html")


@bp.route("/campaigns/create", methods=["GET"])
def create():
    """Render the 6-step ICP wizard form.

    Form submissions go to one of three independent routes depending on
    which action button the operator clicks:
      /campaigns/find-leads          — leads only, no AI copy
      /campaigns/generate-sequence   — strategy + sequence only, no Apollo
      /campaigns/find-and-generate   — both in one pass
    """
    config = current_app.config["VOLLEY_CONFIG"]
    apollo_remaining = _apollo_credits_remaining(config)
    return render_template("campaign_create.html", apollo_remaining=apollo_remaining)
