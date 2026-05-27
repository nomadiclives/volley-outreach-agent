"""SQLite schema + all CRUD operations for Volley outreach agent."""

import sqlite3
import json
import logging
from contextlib import contextmanager
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "volley.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    domain TEXT,
    industry TEXT,
    employee_count TEXT,
    city TEXT,
    country TEXT,
    first_name TEXT,
    last_name TEXT,
    title TEXT,
    email TEXT UNIQUE,
    email_verified INTEGER DEFAULT 0,
    linkedin_url TEXT,
    source TEXT,
    icp_score INTEGER,
    score_title INTEGER,
    score_company_size INTEGER,
    score_multi_location INTEGER,
    score_ad_spend INTEGER,
    score_ltv_vertical INTEGER,
    score_marketing_roles INTEGER,
    score_data_completeness INTEGER,
    score_rationale TEXT,
    buying_signals TEXT,
    auto_rejected INTEGER DEFAULT 0,
    auto_reject_reason TEXT,
    status TEXT DEFAULT 'new',
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    icp_description TEXT,
    vertical TEXT,
    geo TEXT,
    strategy_json TEXT,
    status TEXT DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER REFERENCES campaigns(id),
    step_number INTEGER NOT NULL,
    subject TEXT NOT NULL,
    body_text TEXT NOT NULL,
    delay_days INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS outreach_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER REFERENCES leads(id),
    campaign_id INTEGER REFERENCES campaigns(id),
    sequence_id INTEGER REFERENCES sequences(id),
    step_number INTEGER,
    scheduled_at TIMESTAMP,
    sent_at TIMESTAMP,
    opened_at TIMESTAMP,
    replied_at TIMESTAMP,
    reply_is_human INTEGER DEFAULT 0,
    reply_classification TEXT,
    message_id TEXT,
    status TEXT DEFAULT 'scheduled'
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    message TEXT NOT NULL,
    read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS api_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT,
    model TEXT,
    purpose TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS send_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER REFERENCES leads(id),
    campaign_id INTEGER REFERENCES campaigns(id),
    sequence_id INTEGER REFERENCES sequences(id),
    step_number INTEGER,
    scheduled_at TIMESTAMP,
    attempts INTEGER DEFAULT 0,
    last_error TEXT,
    status TEXT DEFAULT 'pending'
);
"""


def get_connection() -> sqlite3.Connection:
    """Return a connection with row_factory set."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db():
    """Context manager that commits on success, rolls back on error."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with db() as conn:
        conn.executescript(SCHEMA)
    logger.info("Database initialised at %s", DB_PATH)


# ── Leads ────────────────────────────────────────────────────────────────────

def insert_lead(lead: dict) -> Optional[int]:
    """Insert a lead; return new id or None if duplicate email.

    Accepts all scoring sub-score fields produced by lead_enricher.score_lead().
    Unknown keys in the dict are ignored — safe to pass the full enriched lead.
    """
    sql = """
        INSERT OR IGNORE INTO leads
            (company_name, domain, industry, employee_count, city, country,
             first_name, last_name, title, email, email_verified, linkedin_url,
             source, icp_score,
             score_title, score_company_size, score_multi_location,
             score_ad_spend, score_ltv_vertical, score_marketing_roles,
             score_data_completeness, score_rationale, buying_signals,
             auto_rejected, auto_reject_reason,
             status, notes)
        VALUES
            (:company_name, :domain, :industry, :employee_count, :city, :country,
             :first_name, :last_name, :title, :email, :email_verified, :linkedin_url,
             :source, :icp_score,
             :score_title, :score_company_size, :score_multi_location,
             :score_ad_spend, :score_ltv_vertical, :score_marketing_roles,
             :score_data_completeness, :score_rationale, :buying_signals,
             :auto_rejected, :auto_reject_reason,
             :status, :notes)
    """
    # Provide defaults for all scoring fields so callers don't have to set them
    row = {
        "company_name":           lead.get("company_name", ""),
        "domain":                 lead.get("domain"),
        "industry":               lead.get("industry"),
        "employee_count":         lead.get("employee_count"),
        "city":                   lead.get("city"),
        "country":                lead.get("country"),
        "first_name":             lead.get("first_name"),
        "last_name":              lead.get("last_name"),
        "title":                  lead.get("title"),
        "email":                  lead.get("email"),
        "email_verified":         lead.get("email_verified", 0),
        "linkedin_url":           lead.get("linkedin_url"),
        "source":                 lead.get("source"),
        "icp_score":              lead.get("icp_score"),
        "score_title":            lead.get("score_title"),
        "score_company_size":     lead.get("score_company_size"),
        "score_multi_location":   lead.get("score_multi_location"),
        "score_ad_spend":         lead.get("score_ad_spend"),
        "score_ltv_vertical":     lead.get("score_ltv_vertical"),
        "score_marketing_roles":  lead.get("score_marketing_roles"),
        "score_data_completeness": lead.get("score_data_completeness"),
        "score_rationale":        lead.get("score_rationale"),
        "buying_signals":         (
            json.dumps(lead["buying_signals"])
            if isinstance(lead.get("buying_signals"), dict)
            else lead.get("buying_signals")
        ),
        "auto_rejected":          lead.get("auto_rejected", 0),
        "auto_reject_reason":     lead.get("auto_reject_reason"),
        "status":                 lead.get("status", "new"),
        "notes":                  lead.get("notes"),
    }
    with db() as conn:
        cur = conn.execute(sql, row)
        return cur.lastrowid if cur.rowcount else None


def get_lead(lead_id: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return dict(row) if row else None


def get_lead_by_email(email: str) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM leads WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None


def update_lead_status(lead_id: int, status: str):
    """Update a lead's status field."""
    with db() as conn:
        conn.execute(
            "UPDATE leads SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, lead_id),
        )


def update_lead_scores(lead_id: int, scores: dict):
    """Write scoring sub-scores back to an existing lead row.

    Accepts the dict returned by lead_enricher.score_lead().
    Only updates the scoring columns — contact info is untouched.
    """
    with db() as conn:
        conn.execute(
            """UPDATE leads SET
                   icp_score              = :icp_score,
                   score_title            = :score_title,
                   score_company_size     = :score_company_size,
                   score_multi_location   = :score_multi_location,
                   score_ad_spend         = :score_ad_spend,
                   score_ltv_vertical     = :score_ltv_vertical,
                   score_marketing_roles  = :score_marketing_roles,
                   score_data_completeness = :score_data_completeness,
                   score_rationale        = :score_rationale,
                   auto_rejected          = :auto_rejected,
                   auto_reject_reason     = :auto_reject_reason,
                   updated_at             = CURRENT_TIMESTAMP
               WHERE id = :lead_id""",
            {**scores, "lead_id": lead_id},
        )


def list_leads(
    campaign_id: Optional[int] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 500,
    offset: int = 0,
) -> list[dict]:
    clauses, params = [], []
    if campaign_id is not None:
        clauses.append("EXISTS (SELECT 1 FROM outreach_log ol WHERE ol.lead_id = leads.id AND ol.campaign_id = ?)")
        params.append(campaign_id)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if source:
        clauses.append("source = ?")
        params.append(source)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params += [limit, offset]
    with db() as conn:
        rows = conn.execute(
            f"SELECT * FROM leads {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
        return [dict(r) for r in rows]


def leads_count() -> int:
    with db() as conn:
        return conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]


# ── Campaigns ────────────────────────────────────────────────────────────────

def insert_campaign(campaign: dict) -> int:
    sql = """
        INSERT INTO campaigns (name, icp_description, vertical, geo, strategy_json, status)
        VALUES (:name, :icp_description, :vertical, :geo, :strategy_json, :status)
    """
    with db() as conn:
        cur = conn.execute(sql, campaign)
        return cur.lastrowid


def get_campaign(campaign_id: int) -> Optional[dict]:
    with db() as conn:
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        return dict(row) if row else None


def list_campaigns() -> list[dict]:
    with db() as conn:
        rows = conn.execute("SELECT * FROM campaigns ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def update_campaign_status(campaign_id: int, status: str):
    with db() as conn:
        extra = ", approved_at = CURRENT_TIMESTAMP" if status == "approved" else ""
        conn.execute(
            f"UPDATE campaigns SET status = ?{extra} WHERE id = ?",
            (status, campaign_id),
        )


def update_campaign_strategy(campaign_id: int, strategy_json: str):
    with db() as conn:
        conn.execute(
            "UPDATE campaigns SET strategy_json = ? WHERE id = ?",
            (strategy_json, campaign_id),
        )


# ── Sequences ────────────────────────────────────────────────────────────────

def insert_sequence_step(step: dict) -> int:
    sql = """
        INSERT INTO sequences (campaign_id, step_number, subject, body_text, delay_days)
        VALUES (:campaign_id, :step_number, :subject, :body_text, :delay_days)
    """
    with db() as conn:
        cur = conn.execute(sql, step)
        return cur.lastrowid


def get_sequences(campaign_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM sequences WHERE campaign_id = ? ORDER BY step_number",
            (campaign_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_sequence_step(sequence_id: int, subject: str, body_text: str):
    with db() as conn:
        conn.execute(
            "UPDATE sequences SET subject = ?, body_text = ? WHERE id = ?",
            (subject, body_text, sequence_id),
        )


def delete_sequences(campaign_id: int):
    with db() as conn:
        conn.execute("DELETE FROM sequences WHERE campaign_id = ?", (campaign_id,))


# ── Outreach Log ─────────────────────────────────────────────────────────────

def log_outreach(entry: dict) -> int:
    sql = """
        INSERT INTO outreach_log
            (lead_id, campaign_id, sequence_id, step_number, scheduled_at, status)
        VALUES
            (:lead_id, :campaign_id, :sequence_id, :step_number, :scheduled_at, :status)
    """
    with db() as conn:
        cur = conn.execute(sql, entry)
        return cur.lastrowid


def mark_sent(log_id: int, message_id: str):
    with db() as conn:
        conn.execute(
            "UPDATE outreach_log SET sent_at = CURRENT_TIMESTAMP, message_id = ?, status = 'sent' WHERE id = ?",
            (message_id, log_id),
        )


def mark_opened(log_id: int):
    with db() as conn:
        conn.execute(
            "UPDATE outreach_log SET opened_at = CURRENT_TIMESTAMP, status = 'opened' WHERE id = ?",
            (log_id,),
        )


def mark_replied(log_id: int, is_human: bool, classification: str):
    with db() as conn:
        conn.execute(
            """UPDATE outreach_log
               SET replied_at = CURRENT_TIMESTAMP,
                   reply_is_human = ?,
                   reply_classification = ?,
                   status = 'replied'
               WHERE id = ?""",
            (1 if is_human else 0, classification, log_id),
        )


def cancel_future_steps(lead_id: int, campaign_id: int):
    """Cancel all future scheduled/pending steps for this lead in this campaign."""
    with db() as conn:
        conn.execute(
            """UPDATE outreach_log
               SET status = 'cancelled'
               WHERE lead_id = ? AND campaign_id = ?
               AND status IN ('scheduled', 'pending')
               AND sent_at IS NULL""",
            (lead_id, campaign_id),
        )
        conn.execute(
            """UPDATE send_queue
               SET status = 'cancelled'
               WHERE lead_id = ? AND campaign_id = ?
               AND status = 'pending'""",
            (lead_id, campaign_id),
        )


def get_outreach_log(lead_id: int) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM outreach_log WHERE lead_id = ? ORDER BY step_number",
            (lead_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_pending_sends() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT sq.*, l.first_name, l.last_name, l.email, l.company_name,
                      s.subject, s.body_text,
                      c.name as campaign_name
               FROM send_queue sq
               JOIN leads l ON l.id = sq.lead_id
               JOIN sequences s ON s.id = sq.sequence_id
               JOIN campaigns c ON c.id = sq.campaign_id
               WHERE sq.status = 'pending' AND sq.scheduled_at <= CURRENT_TIMESTAMP
               ORDER BY sq.scheduled_at""",
        ).fetchall()
        return [dict(r) for r in rows]


def count_sent_today() -> int:
    with db() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM outreach_log WHERE date(sent_at) = date('now') AND status = 'sent'"
        ).fetchone()[0]


def enqueue_send(entry: dict) -> int:
    sql = """
        INSERT INTO send_queue (lead_id, campaign_id, sequence_id, step_number, scheduled_at)
        VALUES (:lead_id, :campaign_id, :sequence_id, :step_number, :scheduled_at)
    """
    with db() as conn:
        cur = conn.execute(sql, entry)
        return cur.lastrowid


def update_queue_item(queue_id: int, status: str, error: Optional[str] = None):
    with db() as conn:
        conn.execute(
            "UPDATE send_queue SET status = ?, last_error = ?, attempts = attempts + 1 WHERE id = ?",
            (status, error, queue_id),
        )


# ── Notifications ─────────────────────────────────────────────────────────────

def create_notification(type_: str, message: str):
    with db() as conn:
        conn.execute(
            "INSERT INTO notifications (type, message) VALUES (?, ?)",
            (type_, message),
        )


def get_unread_notifications() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE read = 0 ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def mark_notifications_read(ids: list[int]):
    if not ids:
        return
    placeholders = ",".join("?" * len(ids))
    with db() as conn:
        conn.execute(f"UPDATE notifications SET read = 1 WHERE id IN ({placeholders})", ids)


# ── API Usage ─────────────────────────────────────────────────────────────────

def log_api_usage(provider: str, model: str, purpose: str,
                  input_tokens: int, output_tokens: int, cost_usd: float):
    with db() as conn:
        conn.execute(
            """INSERT INTO api_usage (provider, model, purpose, input_tokens, output_tokens, cost_usd)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (provider, model, purpose, input_tokens, output_tokens, cost_usd),
        )


def get_monthly_claude_cost() -> float:
    with db() as conn:
        row = conn.execute(
            """SELECT COALESCE(SUM(cost_usd), 0) FROM api_usage
               WHERE provider = 'anthropic'
               AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"""
        ).fetchone()
        return row[0]


def get_claude_cost_by_purpose() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT purpose, SUM(cost_usd) as total_cost, COUNT(*) as calls
               FROM api_usage WHERE provider = 'anthropic'
               AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
               GROUP BY purpose ORDER BY total_cost DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


# ── Analytics ─────────────────────────────────────────────────────────────────

def campaign_stats(campaign_id: int) -> dict:
    with db() as conn:
        total = conn.execute(
            "SELECT COUNT(DISTINCT lead_id) FROM outreach_log WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()[0]
        sent = conn.execute(
            "SELECT COUNT(*) FROM outreach_log WHERE campaign_id = ? AND status IN ('sent','opened','replied')",
            (campaign_id,),
        ).fetchone()[0]
        opened = conn.execute(
            "SELECT COUNT(*) FROM outreach_log WHERE campaign_id = ? AND opened_at IS NOT NULL",
            (campaign_id,),
        ).fetchone()[0]
        replied = conn.execute(
            "SELECT COUNT(*) FROM outreach_log WHERE campaign_id = ? AND reply_is_human = 1",
            (campaign_id,),
        ).fetchone()[0]
        return {
            "total_leads": total,
            "sent": sent,
            "opened": opened,
            "replied": replied,
            "open_rate": round(opened / sent * 100, 1) if sent else 0,
            "reply_rate": round(replied / sent * 100, 1) if sent else 0,
        }


def daily_send_volume(days: int = 30) -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """SELECT date(sent_at) as send_date, COUNT(*) as count
               FROM outreach_log WHERE sent_at IS NOT NULL
               AND sent_at >= date('now', ?)
               GROUP BY send_date ORDER BY send_date""",
            (f"-{days} days",),
        ).fetchall()
        return [dict(r) for r in rows]
