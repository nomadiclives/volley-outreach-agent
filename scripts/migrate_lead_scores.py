#!/usr/bin/env python3
"""
Migration: add lead-scoring columns to the leads table.

Safe to run on an existing database — skips columns that already exist.
Does NOT drop or modify any existing data.

Usage:
    python scripts/migrate_lead_scores.py
    python scripts/migrate_lead_scores.py --db path/to/other.db   # non-default DB
    python scripts/migrate_lead_scores.py --dry-run               # preview only
"""

import argparse
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Column definitions — (name, sql_type_with_default)
# Order matters: columns are applied in this sequence.
# ---------------------------------------------------------------------------
SCORING_COLUMNS: list[tuple[str, str]] = [
    ("score_title",             "INTEGER"),
    ("score_company_size",      "INTEGER"),
    ("score_multi_location",    "INTEGER"),
    ("score_ad_spend",          "INTEGER"),
    ("score_ltv_vertical",      "INTEGER"),
    ("score_marketing_roles",   "INTEGER"),
    ("score_data_completeness", "INTEGER"),
    ("score_rationale",         "TEXT"),
    ("buying_signals",          "TEXT"),
    ("auto_rejected",           "INTEGER DEFAULT 0"),
    ("auto_reject_reason",      "TEXT"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def resolve_db_path(override: str | None) -> Path:
    """Return the DB path — override or the project default."""
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).parent.parent / "volley.db"


def existing_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """Return the set of column names currently on *table*."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row[1] for row in rows}


def check_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    """Return True if *table* exists in the database."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Core migration
# ---------------------------------------------------------------------------

def run_migration(db_path: Path, dry_run: bool) -> int:
    """
    Apply scoring columns to the leads table.

    Returns the number of columns added (0 = already up to date).
    Raises on any error — no partial state is committed.
    """
    if not db_path.exists():
        print(f"  ✗ Database not found: {db_path}")
        print("    Run `python scripts/setup.py` first to initialise the database.")
        return -1

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    try:
        if not check_table_exists(conn, "leads"):
            print("  ✗ Table 'leads' does not exist in this database.")
            print("    Run `python scripts/setup.py` first to initialise the schema.")
            return -1

        present = existing_columns(conn, "leads")
        to_add = [(col, typedef) for col, typedef in SCORING_COLUMNS if col not in present]

        if not to_add:
            print("  ✓ All scoring columns already present — nothing to do.")
            return 0

        print(f"  Found {len(to_add)} column(s) to add:\n")
        for col, typedef in to_add:
            print(f"    + {col}  {typedef}")

        if dry_run:
            print("\n  [dry-run] No changes made.")
            return len(to_add)

        print()
        for col, typedef in to_add:
            sql = f"ALTER TABLE leads ADD COLUMN {col} {typedef}"
            conn.execute(sql)
            print(f"  ✓ Added: {col}")

        conn.commit()
        return len(to_add)

    except Exception as exc:
        conn.rollback()
        raise exc
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """
    After migration, confirm all expected columns are present.
    Returns True if verification passes.
    """
    conn = sqlite3.connect(str(db_path))
    try:
        present = existing_columns(conn, "leads")
        expected = {col for col, _ in SCORING_COLUMNS}
        missing = expected - present
        if missing:
            print(f"\n  ✗ Verification failed — still missing: {', '.join(sorted(missing))}")
            return False
        print("\n  ✓ Verification passed — all scoring columns confirmed in schema.")
        return True
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate leads table: add scoring columns without touching existing data.",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        default=None,
        help="Path to volley.db (default: <repo-root>/volley.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be changed without writing to the database",
    )
    args = parser.parse_args()

    db_path = resolve_db_path(args.db)

    print()
    print("─" * 60)
    print("  Volley DB Migration — lead scoring columns")
    print("─" * 60)
    print(f"  Database : {db_path}")
    print(f"  Dry-run  : {'yes' if args.dry_run else 'no'}")
    print()

    try:
        added = run_migration(db_path, dry_run=args.dry_run)
    except Exception as exc:
        print(f"\n  ✗ Migration failed: {exc}")
        sys.exit(1)

    if added < 0:
        sys.exit(1)

    if added > 0 and not args.dry_run:
        ok = verify(db_path)
        if not ok:
            sys.exit(1)

    print()
    if args.dry_run:
        print("  Run without --dry-run to apply changes.")
    elif added == 0:
        print("  Database is already up to date.")
    else:
        print(f"  Migration complete — {added} column(s) added.")
    print()


if __name__ == "__main__":
    main()
