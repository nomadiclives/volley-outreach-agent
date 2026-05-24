"""Open-tracking pixel endpoint."""

import base64
from flask import Blueprint, request, Response
from core.database import mark_opened

bp = Blueprint("tracking", __name__, url_prefix="/t")

# 1x1 transparent GIF
_PIXEL = base64.b64decode(
    "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
)


@bp.route("/o/<int:log_id>.gif")
def open_pixel(log_id: int):
    """Record an email open."""
    try:
        mark_opened(log_id)
    except Exception:
        pass
    return Response(_PIXEL, mimetype="image/gif", headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    })
