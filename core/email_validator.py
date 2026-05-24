"""Email format validation + MX record check."""

import re
import logging
import dns.resolver

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
_MX_CACHE: dict[str, bool] = {}


def is_valid_format(email: str) -> bool:
    return bool(_EMAIL_RE.match(email.strip()))


def has_mx_record(domain: str) -> bool:
    """Return True if domain has at least one MX record. Cached."""
    if domain in _MX_CACHE:
        return _MX_CACHE[domain]
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        result = len(answers) > 0
    except Exception:
        result = False
    _MX_CACHE[domain] = result
    return result


def validate_email(email: str) -> tuple[bool, str]:
    """Validate email format and MX. Returns (valid, reason)."""
    if not email:
        return False, "empty"
    email = email.strip().lower()
    if not is_valid_format(email):
        return False, "invalid_format"
    domain = email.split("@")[1]
    if not has_mx_record(domain):
        return False, "no_mx_record"
    return True, "ok"
