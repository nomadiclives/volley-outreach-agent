"""Leads CRM routes."""

import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, Response
from core.database import list_leads, get_lead, update_lead_status, get_outreach_log, list_campaigns

bp = Blueprint("leads", __name__)


@bp.route("/leads")
def index():
    campaign_id = request.args.get("campaign_id", type=int)
    status = request.args.get("status", "")
    source = request.args.get("source", "")
    search = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    per_page = 50
    offset = (page - 1) * per_page

    leads = list_leads(
        campaign_id=campaign_id,
        status=status or None,
        source=source or None,
        limit=per_page,
        offset=offset,
    )

    # Simple search filter (client-side deferred — filter here for non-JS)
    if search:
        leads = [
            l for l in leads
            if search.lower() in (l.get("email") or "").lower()
            or search.lower() in (l.get("company_name") or "").lower()
        ]

    campaigns = list_campaigns()
    return render_template(
        "leads.html",
        leads=leads,
        campaigns=campaigns,
        page=page,
        per_page=per_page,
        filters={"campaign_id": campaign_id, "status": status, "source": source, "q": search},
    )


@bp.route("/leads/<int:lead_id>")
def detail(lead_id: int):
    lead = get_lead(lead_id)
    if not lead:
        flash("Lead not found", "error")
        return redirect(url_for("leads.index"))
    history = get_outreach_log(lead_id)
    return render_template("lead_detail.html", lead=lead, history=history)


@bp.route("/leads/bulk_action", methods=["POST"])
def bulk_action():
    action = request.form.get("action")
    lead_ids = request.form.getlist("lead_ids", type=int)

    if not lead_ids:
        flash("No leads selected.", "warning")
        return redirect(url_for("leads.index"))

    status_map = {"approve": "approved", "reject": "rejected"}
    if action in status_map:
        for lid in lead_ids:
            update_lead_status(lid, status_map[action])
        flash(f"{len(lead_ids)} leads {action}d.", "success")

    return redirect(url_for("leads.index"))


@bp.route("/leads/export")
def export():
    campaign_id = request.args.get("campaign_id", type=int)
    leads = list_leads(campaign_id=campaign_id, limit=10000)

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "company_name", "first_name", "last_name", "title",
        "email", "domain", "industry", "employee_count", "city", "country",
        "source", "icp_score", "status", "email_verified", "notes", "created_at",
    ])
    writer.writeheader()
    for lead in leads:
        writer.writerow({k: lead.get(k, "") for k in writer.fieldnames})

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=leads_export.csv"},
    )
