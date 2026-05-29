"""
Volley Outreach Agent — main entry point.
Starts the Flask web server and background scheduler.
On startup: re-queues any missed sends from SQLite state.
"""

import logging
import os
import sys
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.table import Table

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/volley.log"),
    ],
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config.yaml") -> dict:
    """Load and validate config.yaml."""
    config_path = Path(path)
    if not config_path.exists():
        console.print(f"[red]config.yaml not found. Run: python scripts/setup.py[/red]")
        sys.exit(1)
    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Apply defaults for optional keys
    config.setdefault("claude", {}).setdefault("monthly_cost_limit_usd", 4.00)
    config.setdefault("deliverability", {}).setdefault("warmup_days_elapsed", 0)
    return config


def _recover_missed_sends(config: dict):
    """On restart: log any sends that were scheduled but not sent due to downtime."""
    from core.database import get_pending_sends
    pending = get_pending_sends()
    if pending:
        logger.info("Recovery: %d pending sends found in queue", len(pending))
        console.print(f"[yellow]Recovery: {len(pending)} pending sends will be processed.[/yellow]")


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Volley Outreach Agent — pay-per-lead outreach automation."""
    if ctx.invoked_subcommand is None:
        # Default: start web server + scheduler
        config = load_config()
        from core.database import init_db
        from integrations.google_sheets import init_sheets
        from core.scheduler import start_scheduler
        from web.app import create_app

        init_db()
        init_sheets(config)
        _recover_missed_sends(config)

        start_scheduler(config)
        console.print("[green]Scheduler started[/green]")

        app = create_app(config)
        host = config["web"]["host"]
        port = config["web"]["port"]
        console.print(f"[bold green]Volley running at http://{host}:{port}[/bold green]")
        app.run(host=host, port=port, debug=False, use_reloader=False)


@cli.command()
@click.option("--icp", required=True, help="ICP description text or @file.txt")
@click.option("--limit", default=50, help="Max leads to find")
@click.option("--dry-run", is_flag=True, help="Preview without saving")
def find(icp: str, limit: int, dry_run: bool):
    """Find leads matching an ICP and add them to the CRM."""
    config = load_config()
    from core.database import init_db
    from integrations.google_sheets import init_sheets
    init_db()
    init_sheets(config)

    # Allow @filename.txt to load ICP from file
    if icp.startswith("@"):
        icp_path = Path(icp[1:])
        if not icp_path.exists():
            console.print(f"[red]ICP file not found: {icp_path}[/red]")
            sys.exit(1)
        icp = icp_path.read_text()

    from agents.lead_finder import find_leads
    console.print(f"[bold]Finding leads[/bold] | limit={limit} | dry_run={dry_run}")
    leads = find_leads(icp_description=icp, config=config, limit=limit, dry_run=dry_run)

    table = Table(title=f"{'[DRY RUN] ' if dry_run else ''}Found {len(leads)} leads")
    table.add_column("Company")
    table.add_column("Name")
    table.add_column("Email")
    table.add_column("Score")
    table.add_column("Source")

    for lead in leads[:20]:
        table.add_row(
            lead.get("company_name", ""),
            f"{lead.get('first_name', '')} {lead.get('last_name', '')}".strip(),
            lead.get("email", ""),
            str(lead.get("icp_score", "")),
            lead.get("source", ""),
        )
    console.print(table)
    if len(leads) > 20:
        console.print(f"[dim]... and {len(leads)-20} more[/dim]")


@cli.command()
def sync():
    """Force sync SQLite ↔ Google Sheets."""
    config = load_config()
    from core.database import init_db, list_leads
    from integrations.google_sheets import init_sheets, bulk_sync_leads
    init_db()
    init_sheets(config)

    leads = list_leads(limit=10000)
    console.print(f"Syncing {len(leads)} leads to Google Sheets...")
    bulk_sync_leads(leads)
    console.print("[green]Sync complete[/green]")


@cli.command()
def status():
    """Print campaign and system status summary."""
    config = load_config()
    from core.database import init_db, list_campaigns, campaign_stats, count_sent_today, get_monthly_claude_cost
    init_db()

    campaigns = list_campaigns()
    sent_today = count_sent_today()
    cost = get_monthly_claude_cost()

    console.print(f"\n[bold]Volley Status[/bold]")
    console.print(f"  Sent today: {sent_today} / {config['email']['daily_send_limit']}")
    console.print(f"  Claude cost this month: ${cost:.4f}")
    console.print(f"  Warmup active: {config['email']['warmup_active']}")

    if campaigns:
        table = Table(title="Campaigns")
        table.add_column("ID")
        table.add_column("Name")
        table.add_column("Status")
        table.add_column("Leads")
        table.add_column("Sent")
        table.add_column("Open%")
        table.add_column("Reply%")
        for c in campaigns:
            s = campaign_stats(c["id"])
            table.add_row(
                str(c["id"]), c["name"], c["status"],
                str(s["total_leads"]), str(s["sent"]),
                f"{s['open_rate']}%", f"{s['reply_rate']}%",
            )
        console.print(table)
    else:
        console.print("  No campaigns yet.")


@cli.command()
@click.option("--campaign", required=True, type=int, help="Campaign ID")
def pause(campaign: int):
    """Pause a campaign."""
    from core.database import init_db, update_campaign_status
    init_db()
    update_campaign_status(campaign, "paused")
    console.print(f"[yellow]Campaign {campaign} paused.[/yellow]")


@cli.command()
@click.option("--campaign", required=True, type=int, help="Campaign ID")
def resume(campaign: int):
    """Resume a paused campaign."""
    from core.database import init_db, update_campaign_status
    init_db()
    update_campaign_status(campaign, "active")
    console.print(f"[green]Campaign {campaign} resumed.[/green]")


@cli.command()
@click.option("--campaign", required=True, type=int, help="Campaign ID")
def export(campaign: int):
    """Export campaign leads to CSV."""
    import csv
    from core.database import init_db, list_leads
    init_db()
    leads = list_leads(campaign_id=campaign, limit=10000)
    filename = f"leads_campaign_{campaign}.csv"
    with open(filename, "w", newline="") as f:
        if leads:
            writer = csv.DictWriter(f, fieldnames=leads[0].keys())
            writer.writeheader()
            writer.writerows(leads)
    console.print(f"[green]Exported {len(leads)} leads to {filename}[/green]")


if __name__ == "__main__":
    cli()
