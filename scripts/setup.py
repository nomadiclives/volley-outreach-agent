#!/usr/bin/env python3
"""
Volley first-time setup wizard.
Run this once to verify configuration, initialise the database, and print next steps.
"""

import os
import sys
import subprocess
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    console = Console()
except ImportError:
    class Console:
        def print(self, *a, **k): print(*a)
        def rule(self, *a, **k): print("---")
    class Panel:
        def __init__(self, *a, **k): pass
    console = Console()


ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def check(label: str, ok: bool, detail: str = ""):
    status = "[green]✓[/green]" if ok else "[red]✗[/red]"
    console.print(f"  {status} {label}" + (f" — {detail}" if detail else ""))
    return ok


def main():
    console.rule("[bold]Volley Setup[/bold]")
    console.print()

    all_ok = True

    # Python version
    py = sys.version_info
    ok = py >= (3, 11)
    all_ok &= check(f"Python {py.major}.{py.minor}", ok, "3.11+ required" if not ok else "")

    # Config file
    config_path = ROOT / "config.yaml"
    ok = config_path.exists()
    all_ok &= check("config.yaml", ok, "not found — copy config.yaml.example" if not ok else "")

    config = {}
    if ok:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)

    # API keys
    claude_key = config.get("claude", {}).get("api_key", "")
    all_ok &= check("Claude API key", bool(claude_key and len(claude_key) > 10))

    apollo_key = config.get("apollo", {}).get("api_key", "")
    check("Apollo API key", bool(apollo_key), "optional but recommended")

    hunter_key = config.get("hunter", {}).get("api_key", "")
    check("Hunter API key", bool(hunter_key), "optional")

    gmail_addr = config.get("email", {}).get("address", "")
    gmail_pw = config.get("email", {}).get("app_password", "")
    all_ok &= check("Gmail address", bool(gmail_addr) and "@" in gmail_addr)
    all_ok &= check("Gmail app password", bool(gmail_pw) and len(gmail_pw) > 8)

    sheets_id = config.get("google", {}).get("sheets_spreadsheet_id", "")
    check("Google Sheets ID", bool(sheets_id), "optional — Sheets sync disabled if empty")

    creds_path = ROOT / config.get("google", {}).get("credentials_path", "credentials.json")
    check("Google credentials.json", creds_path.exists(), "optional — Sheets sync disabled if missing")

    # Database init
    try:
        os.chdir(ROOT)
        from core.database import init_db
        init_db()
        check("Database", True, f"volley.db initialised")
    except Exception as e:
        check("Database", False, str(e))
        all_ok = False

    # Logs dir
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    check("Logs directory", True)

    console.print()

    # Warmup schedule
    console.print("[bold]Warmup Schedule[/bold]")
    table = Table(show_header=True)
    table.add_column("Phase")
    table.add_column("Sends/day")
    table.add_column("Notes")
    table.add_row("Week 1", "10", "Warmup only — no real prospects")
    table.add_row("Week 2", "20", "Warmup only")
    table.add_row("Week 3", "30 (20 warmup + 10 real)", "First real prospects ←")
    table.add_row("Week 4", "40 (10 warmup + 30 real)", "Ramping up")
    table.add_row("Month 2+", "50–80", "Warmup off — full Gmail SMTP")
    console.print(table)
    console.print()

    # DNS setup guide
    console.print("[bold]Domain & DNS Setup (one-time, ~30 min)[/bold]")
    dns_steps = """
1. Buy domain at Namecheap or Porkbun (~$10/yr)
2. Add to Cloudflare (free) → update registrar nameservers
3. In Cloudflare DNS:
   • TXT @ → v=spf1 include:_spf.google.com ~all
   • TXT _dmarc → v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com
   • MX @ → route.mx.cloudflare.net (Cloudflare Email Routing)
4. Cloudflare Email Routing → forward outreach@yourdomain.com → your Gmail
5. Gmail Settings → Accounts → "Send mail as" → add via SMTP
6. Run: python scripts/dns_checker.py --domain yourdomain.com
"""
    console.print(dns_steps)

    # Next steps
    console.print("[bold]Next Steps[/bold]")
    steps = [
        "1. Fill in any missing keys in config.yaml",
        "2. Run: python scripts/dns_checker.py --domain yourdomain.com",
        "3. Start the agent: python main.py",
        "4. Open the dashboard: http://127.0.0.1:5000",
        "5. Create your first campaign from the dashboard",
        "6. Find leads: python main.py find --icp 'Head of Sales at B2B SaaS, 50-200 employees, DACH' --limit 25",
    ]
    for s in steps:
        console.print(f"  {s}")

    console.print()
    if all_ok:
        console.print("[bold green]✓ Setup complete — ready to run[/bold green]")
    else:
        console.print("[bold yellow]⚠ Some checks failed — review above before starting[/bold yellow]")


if __name__ == "__main__":
    main()
