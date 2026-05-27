"""Lead enrichment: email validation, deduplication, and ICP scoring.

Scoring engine: deterministic 7-criterion framework (0–100 points).

Each criterion is scored independently from structured lead data:
  Title match         20 pts
  Company size        15 pts
  Multi-location      15 pts
  Ad spend signal     20 pts
  High-LTV vertical   15 pts
  Marketing roles     10 pts
  Data completeness    5 pts
  ─────────────────── ─────
  TOTAL              100 pts

── HARD GATES vs SOFT SCORING ───────────────────────────────────────────────

Hard gates (stored as auto_rejected=1, hidden from approval queue):
  - Fewer than 5 employees
  - Solo operator (title or employee-count signal)
  - Vertical is ACA / Medicare / car insurance (unless ICP allows it)
  - No email found AND Hunter confidence < 70%

These are the ONLY four reasons a lead can be excluded. A lead that misses
every other criterion — no ads detected, single location, partial title match
— still enters the CRM and scores low (yellow). The operator decides.

Soft scoring (affect icp_score only, never exclude):
  - Buying signals (ads, lead forms, TCPA, etc.)
  - Multi-location presence
  - Title match quality
  - High-LTV vertical
  - Data completeness (email verified, LinkedIn, domain)
  - Company size fit within ideal range

Claude is NOT used for the numeric scores — scoring is deterministic.
Claude IS used for the one-line score_rationale (optional, falls back
gracefully if the API is unavailable or over budget).
"""

import json
import logging
from typing import Optional

from core.email_validator import validate_email

logger = logging.getLogger(__name__)

# ── Scoring weights ────────────────────────────────────────────────────────────

SCORE_WEIGHTS: dict[str, int] = {
    "title":              20,
    "company_size":       15,
    "multi_location":     15,
    "ad_spend":           20,
    "ltv_vertical":       15,
    "marketing_roles":    10,
    "data_completeness":   5,
}

# ── Reference lists ───────────────────────────────────────────────────────────

# Default target titles from the ICP wizard spec (lower-cased for comparison)
DEFAULT_TARGET_TITLES: list[str] = [
    "marketing manager",
    "head of marketing",
    "vp marketing",
    "vp of marketing",
    "vice president marketing",
    "vice president of marketing",
    "director of marketing",
    "marketing director",
    "affiliate manager",
    "affiliate marketing manager",
    "partnerships manager",
    "partner manager",
    "head of partnerships",
    "media buyer",
    "paid media manager",
    "head of growth",
    "growth manager",
    "growth lead",
    "cmo",
    "chief marketing officer",
    "ceo",
    "chief executive officer",
    "founder",
    "co-founder",
    "owner",
]

# Keywords that indicate a marketing-focused title (partial match)
MARKETING_KEYWORDS: list[str] = [
    "marketing",
    "growth",
    "affiliate",
    "media buyer",
    "acquisition",
    "demand gen",
    "demand generation",
    "partnerships",
    "digital",
    "brand",
    "performance",
]

# Executive titles that only count for small companies (≤50 employees)
SENIOR_EXEC_TITLES: set[str] = {"ceo", "chief executive officer", "founder", "co-founder", "owner"}

# Verticals that qualify as high-LTV (insurance, legal, healthcare, home services, solar)
HIGH_LTV_VERTICALS: list[str] = [
    "insurance",
    "legal",
    "law",
    "attorney",
    "lawyer",
    "financial",
    "finance",
    "financial services",
    "wealth management",
    "investment",
    "medical",
    "healthcare",
    "health",
    "clinic",
    "dental",
    "home services",
    "roofing",
    "hvac",
    "plumbing",
    "pest control",
    "landscaping",
    "remodel",
    "solar",
    "solar energy",
    "real estate",
    "mortgage",
    "property management",
]

# Verticals that are automatically rejected (unless icp overrides)
AUTO_REJECT_VERTICALS: list[str] = [
    "aca",
    "affordable care act",
    "medicare",
    "medicaid",
    "car insurance",
    "auto insurance",
    "vehicle insurance",
]

# Solo-operator keywords in a title signal a likely individual / non-buyer
SOLO_OPERATOR_KEYWORDS: list[str] = [
    "freelance",
    "freelancer",
    "self-employed",
    "independent contractor",
    "sole proprietor",
    "solopreneur",
    "consultant",          # not always — scored conservatively
]

# ── Parsing helpers ────────────────────────────────────────────────────────────


def _parse_employee_count(emp_str) -> Optional[int]:
    """Parse employee-count field to an integer.

    Handles: "75", "10-50", "50 to 200", "200+", "1,000-5,000", etc.
    Returns None when the value cannot be determined.
    """
    if emp_str is None:
        return None
    s = str(emp_str).strip().replace(",", "").replace("+", "").lower()
    for sep in [" to ", "–", "-"]:
        if sep in s:
            parts = s.split(sep, 1)
            try:
                lo = int(parts[0].strip())
                hi = int(parts[1].strip())
                return (lo + hi) // 2
            except (ValueError, IndexError):
                pass
    try:
        return int(s)
    except ValueError:
        return None


def _parse_signals(lead: dict) -> dict:
    """Return the buying_signals dict from a lead, handling JSON strings."""
    raw = lead.get("buying_signals")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            result = json.loads(raw)
            return result if isinstance(result, dict) else {}
        except json.JSONDecodeError:
            pass
    return {}


def _norm(text: Optional[str]) -> str:
    """Lower-case and strip a string; return '' if None."""
    return (text or "").lower().strip()


# ── Per-criterion scoring functions (SOFT SCORING — affect score only, never exclude) ──


def _score_title(lead: dict, icp: dict) -> int:
    """Score title match against ICP target titles (max 20 pts).

    Exact / near-exact match   → 20
    Partial keyword match      → 10
    No match                   → 0

    CEO / Founder only scores for companies with ≤50 employees.
    """
    title = _norm(lead.get("title"))
    if not title:
        return 0

    target_titles = [_norm(t) for t in (icp or {}).get("target_titles") or DEFAULT_TARGET_TITLES]
    emp = _parse_employee_count(lead.get("employee_count"))
    is_small = emp is None or emp <= 50  # unknown size → benefit of the doubt

    for target in target_titles:
        if target in title or title in target:
            if any(exec_kw in target for exec_kw in SENIOR_EXEC_TITLES) and not is_small:
                continue  # CEO/Founder only counts for small companies
            return 20

    # Partial: a marketing keyword in the title
    for kw in MARKETING_KEYWORDS:
        if kw in title:
            return 10

    return 0


def _score_company_size(lead: dict, icp: dict) -> int:
    """Score company size against ICP employee range (max 15 pts).

    Ideal range (default 10–200)  → 15
    Adjacent range (5–9 or 201–500) → 8
    < 5 employees                  → 0 (also triggers auto-reject)
    > 500 employees                → 3
    Unknown                        → 7 (partial credit)
    """
    emp = _parse_employee_count(lead.get("employee_count"))
    if emp is None:
        return 7  # Unknown — give partial credit

    icp_range = (icp or {}).get("employee_range") or [10, 200]
    lo, hi = int(icp_range[0]), int(icp_range[1])

    if lo <= emp <= hi:
        return 15
    if emp < 5:
        return 0  # Will also be auto-rejected
    if emp < lo:
        return 8  # Slightly below ideal, but still viable
    if emp <= 500:
        return 8  # Slightly above ideal
    return 3  # Large company — not ideal for this type of outreach


def _score_multi_location(signals: dict) -> int:
    """Score multi-location indicator (max 15 pts).

    Checks buying_signals for any multi-location flag.
    """
    ml_keys = ["multi_location", "multi-location", "multiple_locations", "multilocation"]
    return 15 if any(signals.get(k) for k in ml_keys) else 0


def _score_ad_spend(signals: dict) -> int:
    """Score ad-spend signal (max 20 pts).

    Checks buying_signals for any paid advertising indicator.
    """
    ad_keys = [
        "running_ads", "meta_ads", "google_ads", "youtube_ads",
        "paid_ads", "advertising", "ads", "ppc", "paid_media",
    ]
    return 20 if any(signals.get(k) for k in ad_keys) else 0


def _score_ltv_vertical(lead: dict, icp: dict) -> int:
    """Score high-LTV vertical match (max 15 pts).

    Checks both the lead's industry and the ICP vertical.
    """
    industry = _norm(lead.get("industry"))
    icp_vertical = _norm((icp or {}).get("vertical"))

    for ltv in HIGH_LTV_VERTICALS:
        if ltv in industry or (icp_vertical and ltv in icp_vertical):
            return 15

    return 0


def _score_marketing_roles(lead: dict, signals: dict) -> int:
    """Score presence of dedicated marketing/growth roles (max 10 pts).

    A lead whose own title is a marketing role earns full points —
    they themselves are the dedicated marketing function.
    Explicit buying_signals also count.
    """
    if signals.get("dedicated_marketing_roles") or signals.get("marketing_roles"):
        return 10

    title = _norm(lead.get("title"))
    for kw in MARKETING_KEYWORDS:
        if kw in title:
            return 10

    return 0


def _score_data_completeness(lead: dict) -> int:
    """Score data completeness (max 5 pts).

    Verified email (+2), unverified email (+1),
    LinkedIn URL (+1.5), domain (+1.5).
    """
    score = 0.0
    if lead.get("email"):
        score += 2.0 if lead.get("email_verified") else 1.0
    if lead.get("linkedin_url"):
        score += 1.5
    if lead.get("domain"):
        score += 1.5
    return min(round(score), 5)


# ── Auto-reject logic ─────────────────────────────────────────────────────────


def _check_auto_reject(lead: dict, icp: dict) -> tuple[bool, str]:
    """Return (should_reject, reason).

    Applies the four HARD GATES only. Everything else is soft scoring.
    ICP can set allow_excluded_verticals=True to bypass gate 3.
    """
    emp = _parse_employee_count(lead.get("employee_count"))
    title = _norm(lead.get("title"))
    industry = _norm(lead.get("industry"))
    allow_excluded = bool((icp or {}).get("allow_excluded_verticals", False))

    # ── Hard gate 1: fewer than 5 employees ───────────────────────────────────
    if emp is not None and emp < 5:
        return True, f"Fewer than 5 employees (found: {emp})"

    # ── Hard gate 2: solo operator ────────────────────────────────────────────
    for kw in SOLO_OPERATOR_KEYWORDS:
        if kw in title:
            return True, f"Solo operator (title: '{lead.get('title')}')"

    # ── Hard gate 3: excluded vertical ────────────────────────────────────────
    if not allow_excluded:
        for v in AUTO_REJECT_VERTICALS:
            if v in industry:
                return True, f"Excluded vertical: {v}"

    # ── Hard gate 4: no email AND Hunter confidence < 70% ─────────────────────
    # A lead without an email is only rejected when Hunter's confidence is also
    # below 70% — meaning there is no reliable path to reach them. If Hunter
    # confidence is ≥70%, the lead is kept and scores lower on data completeness;
    # the operator decides whether to pursue manual outreach.
    if not lead.get("email"):
        hunter_confidence = lead.get("hunter_confidence") or 0
        if hunter_confidence < 70:
            return True, f"No email found and Hunter confidence too low ({hunter_confidence}%)"

    return False, ""


# ── Rationale builder ─────────────────────────────────────────────────────────

_CRITERION_LABELS: dict[str, tuple[str, int]] = {
    "title":             ("Title match",        20),
    "company_size":      ("Company size",       15),
    "multi_location":    ("Multi-location",     15),
    "ad_spend":          ("Ad spend signals",   20),
    "ltv_vertical":      ("High-LTV vertical",  15),
    "marketing_roles":   ("Marketing roles",    10),
    "data_completeness": ("Data completeness",   5),
}


def _build_rationale(sub_scores: dict[str, int], auto_rejected: bool, reject_reason: str) -> str:
    """Build a concise, human-readable rationale from sub-scores.

    Does NOT call Claude — this is always available even when the API is down.
    """
    if auto_rejected:
        return f"Auto-rejected: {reject_reason}"

    total = sum(sub_scores.values())
    strengths: list[str] = []
    gaps: list[str] = []

    for key, (label, max_pts) in _CRITERION_LABELS.items():
        pts = sub_scores.get(key, 0)
        if pts >= max_pts:
            strengths.append(label)
        elif pts == 0 and max_pts >= 15:
            gaps.append(label)

    parts: list[str] = []
    if strengths:
        parts.append("Strong: " + ", ".join(strengths[:3]))
    if gaps:
        parts.append("Gaps: " + ", ".join(gaps[:3]))

    if not parts:
        if total >= 70:
            parts.append("Solid across all criteria")
        elif total >= 40:
            parts.append("Partial fit — some criteria unverified")
        else:
            parts.append("Weak fit — most qualifying signals absent")

    return "; ".join(parts)


# ── Main enrichment functions ─────────────────────────────────────────────────


def score_lead(lead: dict, icp: dict) -> dict:
    """Run the deterministic scoring engine against a single lead.

    Returns a dict with keys:
        icp_score, score_title, score_company_size, score_multi_location,
        score_ad_spend, score_ltv_vertical, score_marketing_roles,
        score_data_completeness, score_rationale,
        auto_rejected, auto_reject_reason

    Does NOT mutate the input lead dict.
    """
    icp = icp or {}
    signals = _parse_signals(lead)

    # Auto-reject check first
    rejected, reject_reason = _check_auto_reject(lead, icp)

    if rejected:
        return {
            "icp_score":             0,
            "score_title":           0,
            "score_company_size":    0,
            "score_multi_location":  0,
            "score_ad_spend":        0,
            "score_ltv_vertical":    0,
            "score_marketing_roles": 0,
            "score_data_completeness": 0,
            "score_rationale":       f"Auto-rejected: {reject_reason}",
            "auto_rejected":         1,
            "auto_reject_reason":    reject_reason,
        }

    sub_scores = {
        "title":             _score_title(lead, icp),
        "company_size":      _score_company_size(lead, icp),
        "multi_location":    _score_multi_location(signals),
        "ad_spend":          _score_ad_spend(signals),
        "ltv_vertical":      _score_ltv_vertical(lead, icp),
        "marketing_roles":   _score_marketing_roles(lead, signals),
        "data_completeness": _score_data_completeness(lead),
    }

    total = sum(sub_scores.values())
    rationale = _build_rationale(sub_scores, False, "")

    return {
        "icp_score":               total,
        "score_title":             sub_scores["title"],
        "score_company_size":      sub_scores["company_size"],
        "score_multi_location":    sub_scores["multi_location"],
        "score_ad_spend":          sub_scores["ad_spend"],
        "score_ltv_vertical":      sub_scores["ltv_vertical"],
        "score_marketing_roles":   sub_scores["marketing_roles"],
        "score_data_completeness": sub_scores["data_completeness"],
        "score_rationale":         rationale,
        "auto_rejected":           0,
        "auto_reject_reason":      "",
    }


def enrich_lead(lead: dict, icp: dict, config: dict) -> dict:
    """Validate email, run scoring, return enriched lead dict.

    The lead dict is mutated in-place and returned.
    Returns None if the lead should be discarded entirely (e.g. missing
    critical data beyond auto-reject threshold).
    """
    # Email validation
    email = (lead.get("email") or "").strip().lower()
    lead["email"] = email

    if email:
        valid, reason = validate_email(email)
        lead["email_verified"] = 1 if valid else 0
        if not valid:
            logger.debug("Email invalid (%s): %s", reason, email)
    else:
        lead["email_verified"] = 0

    # Run deterministic scoring engine
    scores = score_lead(lead, icp)
    lead.update(scores)

    # Log outcome
    if lead.get("auto_rejected"):
        logger.info(
            "Auto-rejected %s (%s): %s",
            lead.get("email") or lead.get("company_name"),
            lead.get("title"),
            lead.get("auto_reject_reason"),
        )
    else:
        logger.debug(
            "Scored %s — %d/100 [T:%d S:%d M:%d A:%d V:%d R:%d D:%d]",
            lead.get("email") or lead.get("company_name"),
            lead["icp_score"],
            lead["score_title"],
            lead["score_company_size"],
            lead["score_multi_location"],
            lead["score_ad_spend"],
            lead["score_ltv_vertical"],
            lead["score_marketing_roles"],
            lead["score_data_completeness"],
        )

    return lead


def enrich_batch(leads: list[dict], icp: dict, config: dict) -> list[dict]:
    """Enrich a batch of leads.

    All leads are returned — nothing is silently dropped:
    - Hard-gate failures → auto_rejected=1, icp_score=0 (shown as rejected in dashboard)
    - Low soft scores    → icp_score<40, shown in red/yellow (operator decides)
    """
    enriched: list[dict] = []
    for lead in leads:
        try:
            result = enrich_lead(lead, icp, config)
            if result is not None:
                enriched.append(result)
        except Exception as exc:
            logger.error(
                "Enrichment failed for %s: %s",
                lead.get("email") or lead.get("company_name"),
                exc,
            )
    return enriched
