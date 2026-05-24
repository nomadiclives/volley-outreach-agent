#!/usr/bin/env python3
"""Verify SPF, DKIM, DMARC, and MX records for your sending domain."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import click
import dns.resolver

try:
    from rich.console import Console
    console = Console()
except ImportError:
    class Console:
        def print(self, *a, **k): print(*a)
    console = Console()


def check(label: str, ok: bool, detail: str = ""):
    status = "[green]✓[/green]" if ok else "[red]✗[/red]"
    console.print(f"  {status} {label}" + (f"\n      → {detail}" if detail else ""))


def resolve_txt(domain: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(domain, "TXT", lifetime=8)
        return ["".join(r.strings[i].decode() for i in range(len(r.strings))) for r in answers]
    except Exception:
        return []


def resolve_mx(domain: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=8)
        return [str(r.exchange) for r in answers]
    except Exception:
        return []


@click.command()
@click.option("--domain", required=True, help="Your sending domain e.g. outreach.yourdomain.com")
def main(domain: str):
    """Check DNS records for email deliverability."""
    console.print(f"\n[bold]DNS Check for {domain}[/bold]\n")

    # MX
    mx = resolve_mx(domain)
    check("MX records", bool(mx), ", ".join(mx) if mx else "No MX found — set up Cloudflare Email Routing or Google MX")

    # SPF
    txts = resolve_txt(domain)
    spf = [t for t in txts if t.startswith("v=spf1")]
    if spf:
        has_google = "_spf.google.com" in spf[0] or "include:_spf.google.com" in spf[0]
        check("SPF record", True, spf[0])
        check("SPF includes Google", has_google, "Add: include:_spf.google.com" if not has_google else "")
    else:
        check("SPF record", False, "Missing — add TXT: v=spf1 include:_spf.google.com ~all")

    # DMARC
    dmarc_txts = resolve_txt(f"_dmarc.{domain}")
    dmarc = [t for t in dmarc_txts if t.startswith("v=DMARC1")]
    if dmarc:
        check("DMARC record", True, dmarc[0])
    else:
        check("DMARC record", False, "Missing — add TXT _dmarc: v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com")

    # DKIM (check common selector)
    for selector in ["google", "mail", "dkim", "default"]:
        dkim_txts = resolve_txt(f"{selector}._domainkey.{domain}")
        dkim = [t for t in dkim_txts if "v=DKIM1" in t or "k=rsa" in t]
        if dkim:
            check(f"DKIM ({selector} selector)", True, dkim[0][:80] + "…")
            break
    else:
        check("DKIM record", False,
              "Not found with common selectors (google/mail/dkim/default). "
              "Set up via Google Workspace or Cloudflare DKIM signing.")

    console.print()
    console.print("[bold]Recommended checks after sending:[/bold]")
    console.print("  • mail-tester.com — send a test email, get deliverability score")
    console.print("  • mxtoolbox.com — full blacklist check")
    console.print("  • dmarcanalyzer.com — DMARC report viewer")


if __name__ == "__main__":
    main()
