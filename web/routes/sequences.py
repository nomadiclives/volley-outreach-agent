"""Sequence viewer and editor routes."""

from flask import Blueprint, render_template, request, redirect, url_for, flash
from core.database import list_campaigns, get_sequences, get_campaign, update_sequence_step

bp = Blueprint("sequences", __name__)

SPAM_TRIGGERS = [
    "free", "guaranteed", "no obligation", "act now", "limited time",
    "click here", "buy now", "earn money", "100%", "risk-free",
]


def _check_spam(text: str) -> list[str]:
    lower = text.lower()
    return [t for t in SPAM_TRIGGERS if t in lower]


@bp.route("/sequences")
def index():
    campaigns = list_campaigns()
    campaign_id = request.args.get("campaign_id", type=int)
    sequences = []
    campaign = None
    warnings = []

    if campaign_id:
        campaign = get_campaign(campaign_id)
        sequences = get_sequences(campaign_id)
        for seq in sequences:
            hits = _check_spam(seq["subject"] + " " + seq["body_text"])
            if hits:
                warnings.append(f"Step {seq['step_number']}: spam triggers: {', '.join(hits)}")

    return render_template(
        "sequences.html",
        campaigns=campaigns,
        selected_campaign=campaign,
        sequences=sequences,
        warnings=warnings,
    )


@bp.route("/sequences/<int:sequence_id>/edit", methods=["POST"])
def edit(sequence_id: int):
    subject = request.form.get("subject", "").strip()
    body = request.form.get("body_text", "").strip()
    campaign_id = request.form.get("campaign_id", type=int)

    if not subject or not body:
        flash("Subject and body are required.", "error")
    else:
        campaign = get_campaign(campaign_id) if campaign_id else None
        if campaign and campaign["status"] not in ("draft", "paused"):
            flash("Can only edit sequences for draft or paused campaigns.", "error")
        else:
            update_sequence_step(sequence_id, subject, body)
            flash("Sequence step updated.", "success")

    return redirect(url_for("sequences.index", campaign_id=campaign_id))


@bp.route("/sequences/validate", methods=["POST"])
def validate():
    """Validate all sequence steps for a campaign."""
    campaign_id = request.form.get("campaign_id", type=int)
    sequences = get_sequences(campaign_id) if campaign_id else []
    all_warnings = []
    for seq in sequences:
        hits = _check_spam(seq["subject"] + " " + seq["body_text"])
        if hits:
            all_warnings.append(f"Step {seq['step_number']}: {', '.join(hits)}")
        if "{first_name}" not in seq["body_text"]:
            all_warnings.append(f"Step {seq['step_number']}: missing {{first_name}} token")
        if "{company_name}" not in seq["body_text"]:
            all_warnings.append(f"Step {seq['step_number']}: missing {{company_name}} token")

    if all_warnings:
        for w in all_warnings:
            flash(f"Warning: {w}", "warning")
    else:
        flash("All sequence steps passed validation.", "success")

    return redirect(url_for("sequences.index", campaign_id=campaign_id))
