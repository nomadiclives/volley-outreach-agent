"""JSON API endpoints — polled by the dashboard JS."""

from flask import Blueprint, jsonify, request
from core.database import (
    get_unread_notifications, mark_notifications_read,
    count_sent_today, get_monthly_claude_cost,
)

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.route("/notifications")
def notifications():
    notes = get_unread_notifications()
    return jsonify({"notifications": notes, "count": len(notes)})


@bp.route("/notifications/read", methods=["POST"])
def mark_read():
    ids = request.json.get("ids", [])
    mark_notifications_read(ids)
    return jsonify({"ok": True})


@bp.route("/status")
def status():
    return jsonify({
        "sent_today": count_sent_today(),
        "monthly_claude_cost": get_monthly_claude_cost(),
    })
