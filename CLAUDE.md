# Volley — Claude Code Project Memory

## What This Project Is

Volley is a production-ready automated outreach agent for a pay-per-lead lead generation agency. It finds prospective lead buyers, scores them against a qualification framework, generates AI-powered email sequences, gets human approval via a web dashboard, and executes campaigns automatically.

**This is a real operational tool — not a demo. Everything built must work in production.**

---

## Repository & Runtime

- **Repo:** `github.com/nomadiclives/volley-outreach-agent` (private)
- **Runtime:** GitHub Codespaces (Python 3.11+)
- **Dashboard:** Flask web server at `localhost:5000`
- **Entry point:** `python main.py` — starts web server + background scheduler together
- **Database:** SQLite (`volley.db`) — all operational state lives here
- **Secrets:** `config.yaml` and `credentials.json` — both gitignored, never commit

**Codespaces constraint:** Codespaces stops after 30 minutes idle. The scheduler must resume gracefully from SQLite state on restart — never assume a clean start.

---

## Tech Stack

| Layer | Tool | Cost |
|---|---|---|
| Lead finding — B2B contacts | Apollo.io free tier (75 credits/month) | €0 |
| Lead finding — European contacts | Lusha free tier (40 credits/month) | €0 |
| Lead finding — email finding | Snov.io free tier (50 credits/month) | €0 |
| Lead finding — LinkedIn-based | GetProspect free tier (50 credits/month) | €0 |
| Email resolution | Hunter.io free tier (50 searches/month) | €0 |
| Local/SMB company discovery | Google Maps Places API | €0 |
| Ad spend signal | Facebook Ad Library (public) + homepage pixel check | €0 |
| LinkedIn contact data | Playwright public scraper | €0 |
| CRM | Google Sheets API | €0 |
| AI | Claude API — claude-haiku-4-5 | ~€0.02/campaign |
| Email sending | Gmail SMTP + custom domain | €0 |
| Dashboard | Flask + Jinja2 + vanilla CSS | €0 |
| State | SQLite | €0 |

**Combined free credit bank: ~215 verified contacts/month across all sources**

| Source | Credits | Strength |
|---|---|---|
| Apollo | 75/month | B2B contacts with titles + emails, broad database |
| Lusha | 40/month | European contacts, strongest for DACH region |
| Snov.io | 50/month | Email finder, good Apollo complement |
| GetProspect | 50/month | LinkedIn-based contact extraction, good titles |
| Hunter | 50/month | Domain-based email resolution, high accuracy |
| Google Maps | Unlimited | Local/SMB company discovery |
| Facebook Ad Library | Unlimited | Ad spend signal, active advertiser discovery |

**Philosophy: free or near-free everywhere. Never add a paid dependency without flagging it.**

---

## Project Structure

```
volley/
├── main.py                    # Entry point — web server + scheduler
├── config.yaml                # All secrets and config (GITIGNORED)
├── credentials.json           # Google service account (GITIGNORED)
├── requirements.txt
├── setup_codespace.sh         # First-launch setup script
│
├── agents/
│   ├── claude_client.py       # ALL Claude API calls go through here — cost tracking wrapper
│   ├── icp_analyzer.py        # Structured wizard inputs → Apollo search params
│   ├── lead_finder.py         # Two-phase architecture: Discovery → Contact Resolution
│   ├── lead_enricher.py       # Email validation + weighted lead buyer scoring
│   ├── buying_signal_checker.py # Homepage pixel check + Facebook Transparency check
│   ├── strategy_generator.py  # AI outreach strategy generation
│   ├── copywriter.py          # 4-email sequence (SPIN-informed Email 1, break-up Email 4)
│   └── reply_analyzer.py      # Thread reconstruction + human vs automated classification
│
├── integrations/
│   ├── apollo.py              # Apollo.io API — 75 credit/month hard stop
│   ├── hunter.py              # Hunter.io API — 50 search/month hard stop
│   ├── lusha.py               # Lusha API — 40 credit/month hard stop (European contacts)
│   ├── snov.py                # Snov.io API — 50 credit/month hard stop (email finder)
│   ├── getprospect.py         # GetProspect API — 50 credit/month hard stop (LinkedIn-based)
│   ├── google_sheets.py       # Bidirectional CRM sync — update in place, no duplicates
│   ├── gmail_smtp.py          # Email sending — daily limit enforced
│   ├── instantly.py           # Warmup only — free trial, switches off via config flag
│   ├── linkedin_scraper.py    # Playwright, 2-5s delays, max 50/session
│   ├── facebook_ads.py        # Facebook Ad Library + Page Transparency scraper
│   └── google_maps.py         # Places API for local/SMB sourcing
│
├── core/
│   ├── database.py            # SQLite schema + all CRUD
│   ├── deduplicator.py        # PRE-SEARCH dedup — checks DB before spending credits
│   ├── credit_manager.py      # Centralised credit gate for ALL sources — check_and_spend(provider) method
│   ├── email_validator.py     # MX check + format validation
│   ├── scheduler.py           # Background send engine — resumes from SQLite on restart
│   └── reply_handler.py       # CRITICAL: human reply → immediate sequence cancellation
│
├── web/
│   ├── app.py                 # Flask factory
│   ├── routes/
│   │   ├── dashboard.py       # Home — stats, notifications, warmup status, credit bank
│   │   ├── campaigns.py       # Campaign management + 6-step ICP wizard + approval flow
│   │   ├── leads.py           # Lead CRM — score breakdown, filters, bulk actions
│   │   ├── sequences.py       # Email viewer/editor
│   │   └── analytics.py       # Funnel, time series, deliverability health
│   └── templates/             # Jinja2 — dark sidebar, white content, no CSS framework
│
├── tracking/
│   └── pixel.py               # Open tracking pixel
│
└── scripts/
    ├── setup.py               # One-command first-time setup
    ├── migrate_lead_scores.py # DB migration — scoring columns (already run)
    └── dns_checker.py         # SPF/DKIM/DMARC verification
```

---

## Critical Behaviours — Never Break These

### 1. Human Reply = Sequence Stops Immediately
`core/reply_handler.py` polls Gmail every 15 minutes. On detecting a human reply:
1. Mark `reply_is_human = 1` in outreach_log
2. Set ALL future scheduled steps for that lead to `status = 'cancelled'`
3. Update lead status to `'replied'`
4. Sync to Google Sheets
5. Create dashboard notification

**When in doubt, classify as HUMAN.** False positive (cancelled sequence) is fine. False negative (spamming someone who replied) is not.

OOO patterns to recognise as NOT human: "out of office", "away from", "on vacation", "annual leave", "will be back", "automatic reply", "auto-reply", "autoreply", "on holiday", mailer-daemon, postmaster.

### 2. All Claude API Calls Go Through the Cost Wrapper
Every Claude call must use the wrapper in `agents/claude_client.py`. It:
- Checks monthly spend against `claude.monthly_cost_limit_usd` in config (default: $4.00)
- Logs every call to `api_usage` table (tokens in/out, cost, purpose)
- Raises a clear error if the soft limit is hit
- Never calls the Anthropic API directly from any other module

### 3. Every Email Logged Before Sending
Log to `outreach_log` BEFORE the SMTP call. If the process crashes mid-send, no duplicate sends on restart.

### 4. API Credit Hard Stops — All Sources
Every integration must call `core/credit_manager.check_and_spend(provider)` before every API call. This is the single credit gate for all sources — never implement per-integration credit checks independently.

Current limits (never change without confirming with operator):
- Apollo: **75**/month
- Hunter: **50**/month
- Lusha: 40/month
- Snov.io: 50/month
- GetProspect: 50/month

`check_and_spend()` checks remaining credits against the monthly limit in config, raises `CreditLimitReached` if hit, logs the spend to `api_usage` on success.

### 5. Unsubscribe Is Absolute
Any reply containing "unsubscribe", "remove me", "stop emailing", "opt out" → immediately cancel all scheduled steps, mark lead as `unsubscribed`, never contact again. This cannot be reversed by the operator.

---

## Two-Phase Lead Finding Architecture

Lead finding operates in two distinct phases. Never merge them.

### Phase 1 — Company Discovery
Find companies that match the ICP. Sources used in order:

1. **Apollo** — B2B companies with known contacts. Best quality, preserve credits.
2. **Google Maps** — Local/SMB companies by vertical + city. Unlimited, use freely.
3. **Facebook Ad Library** — Companies actively running ads in a vertical. Free, high buying signal value. Search by vertical keyword, extract company names and domains.

Output of Phase 1: a list of companies (name + domain) with no contact person yet.

### Phase 2 — Contact & Email Resolution
For each company found in Phase 1, find the right person and their email. Sources tried in order, stopping as soon as a verified email is found:

1. **Apollo** — if Apollo found the company, it may already have a contact. Check first, no extra credit spent.
2. **Lusha** — try next, especially strong for European/DACH companies.
3. **Snov.io** — email finder by domain.
4. **GetProspect** — LinkedIn-based contact extraction.
5. **Hunter** — domain search as final resolver.
6. **LinkedIn scraper** — Playwright, extract contact name + title, then pass to Hunter for email.

Stop as soon as a verified email is found. Never call multiple Phase 2 sources for the same company.

### Pre-Search Deduplication (CRITICAL — prevents wasted credits)

Before calling ANY source in either phase, check the local DB first:

**Level 1 — Email dedup:**
Before spending a Phase 2 credit to find an email, check if that email already exists in the leads table. If yes, skip entirely — zero credits spent.

**Level 2 — Company+contact dedup:**
Before Phase 2 resolution, check if `company_name + first_name + last_name` already exists. If yes, skip all Phase 2 sources for that contact.

**Level 3 — Domain dedup:**
Before Phase 1 discovery, check if the company domain already exists in the leads table. If yes, skip that company across all Phase 1 sources.

This means each source only fills gaps left by previous ones. Estimated credit waste from overlap: <5% (down from 20-30% without pre-search dedup).

### Credit-Aware Budget Allocation

At the start of each campaign's lead finding run, `core/credit_manager.py` calculates available credits per source and allocates a budget:

```python
# Example allocation for a request of 30 leads:
available = {
    "apollo": 60,      # 75 - 15 used this month
    "lusha": 40,       # full month remaining
    "snov": 50,        # full month remaining
    "getprospect": 50, # full month remaining
    "hunter": 45,      # 50 - 5 used this month
}

# Allocate conservatively — never use more than 60% of remaining credits per campaign
# Spread across sources to preserve monthly budget for future campaigns
budget = {
    "apollo": 20,      # use 20 of 60 available
    "lusha": 15,
    "snov": 15,
    "getprospect": 10,
    "hunter": 10,
}
# Total budget: 70 resolution attempts for 30 leads (covers ~2.3x for misses)
```

**Manual override:** The campaign wizard Step 6 shows a credit budget panel where the operator can override per-source allocation before starting a run. Default is automatic. Override is optional.

Dashboard must show live credit bank status for all sources at all times.

### Buying Signal Detection

Run for every lead after Phase 2 completes. Two checks:

**Check 1 — Homepage pixel scan (fast, runs on all leads):**
Fetch company homepage HTML. Look for:
- Meta Pixel (`connect.facebook.net/en_US/fbevents.js`)
- Google Ads tag (`googleadservices.com` or `gtag('config', 'AW-`)
- Google Tag Manager (`googletagmanager.com/gtm.js`)
- TrustedForm (`trustedform.com`)
- Jornaya (`leadid.com`)

**Check 2 — Facebook Page Transparency (runs on leads scoring >40 after other criteria):**
Fetch `https://www.facebook.com/{page_slug}/about_profile_transparency` via Playwright.
Look for text: "This page is currently running ads."
If found: `buying_signals["running_ads"] = True`, `buying_signals["fb_ads_confirmed"] = True`

Store all results in `buying_signals` JSON field on the lead. These feed directly into `_score_ad_spend()` (20pts) and `_score_multi_location()` (15pts) in lead_enricher.py.

---

## Email Sequence Spec

**4 emails. Plain text only (no HTML — better deliverability).**

Cadence: Day 0 / Day 4 / Day 10 / Day 18

| Email | Name | Max Words | Approach |
|---|---|---|---|
| 1 | The Hook | 80 | SPIN-informed opening question. Problem → Implication → Solution teaser. Single low-friction CTA. |
| 2 | The Value Add | 70 | Different angle. Specific proof point or insight. Soft CTA. |
| 3 | The Social Proof | 100 | Reference similar company type. Concrete result. Stronger CTA. |
| 4 | The Break-up | 30 | "Should I stop reaching out?" — 3 sentences max. Permission to say no. |

Every email must:
- Include `{first_name}` and `{company_name}` tokens
- Include unsubscribe line: "Not relevant? Reply 'unsubscribe' and I'll remove you."
- Pass spam trigger word filter before finalising
- Be plain text only

---

## ICP Wizard — New Campaign Flow

The "New Campaign" form is a **6-step structured wizard**. No free-text ICP description. Claude auto-generates the ICP and Apollo search params from the structured inputs.

**Step 1 — Vertical:** dropdown + free text (e.g. "Solar", "Home Services", "Insurance")
**Step 2 — Geography:** country multi-select + optional cities
**Step 3 — Company Profile:** employee range slider (default 10–200) + multi-location toggle
**Step 4 — Buying Signals:** checkboxes — running ads, lead forms, TCPA language, call centre, dedicated marketing roles, high-LTV vertical, affiliate program
**Step 5 — Target Titles:** pre-populated defaults (editable):
  Marketing Manager, Head of Marketing, VP Marketing, Director of Marketing, Affiliate Manager, Partnerships Manager, Media Buyer, Head of Growth, CMO, CEO (≤50 employees), Founder (≤50 employees)
**Step 6 — Red Flag Exclusions + Summary + Action Selection:**
  - Exclusion checkboxes (overridable): <5 employees, solo operators, ACA/Medicare/car insurance
  - Campaign summary panel showing all wizard selections
  - **Lead limit input** (shown when Find Leads is selected): default 10, max capped at remaining Apollo credits (read from api_usage table), with credit remaining shown as helper text
  - **Three action buttons** — user must pick one:
    - **Find Leads Only** — runs Apollo/Hunter/Maps search, scores leads, adds to CRM. No AI copy. No Claude API cost.
    - **Generate Strategy & Sequence Only** — generates outreach strategy + 4 emails using wizard inputs. No Apollo credits used. ~€0.02 Claude cost.
    - **Do Both** — finds leads AND generates strategy + sequence in one go.

### Filter logic — hard gates vs soft scoring

**Hard gates (always exclude, not configurable per lead):**
- Employee count < 5
- Solo operator
- Red flag verticals (unless unchecked in Step 6)
- Hunter email confidence < 70% with no verified email

**Soft scoring (affects score, never excludes):**
- Buying signals (running ads, lead forms, TCPA, etc.)
- Multi-location preference
- Title match quality
- High-LTV vertical
- Data completeness

A lead that doesn't match soft criteria still appears — it scores lower (e.g. 45/100) and appears in yellow. The operator decides whether to approve it. Hard gates are the only true exclusions.

This means: a solar company with no detected ads scores 55 and shows up in yellow. A solar company running Meta ads scores 85 and shows up in green. Both are visible. The operator decides.

---

## Lead Buyer Scoring Framework (0–100)

Every lead is scored against this weighted framework. Sub-scores stored individually in the DB.

| Criterion | Max Points | What Earns Full Score |
|---|---|---|
| Title match | 20 | Exact match to target titles list |
| Company size | 15 | 10–200 employees |
| Multi-location | 15 | Confirmed multi-location/region |
| Ad spend signal | 20 | Confirmed running Meta/Google/YouTube ads |
| High-LTV vertical | 15 | Insurance, legal, financial, medical, home services, solar |
| Marketing roles | 10 | Dedicated marketing/growth/affiliate role confirmed |
| Data completeness | 5 | Verified email + LinkedIn + domain |

**Auto-reject (hardcoded, stored as `auto_rejected = 1`):**
- Employee count < 5
- Solo operator
- Vertical is ACA / Medicare / car insurance (unless user explicitly overrides)
- No email found AND Hunter confidence < 70%

Score breakdown must be visible per lead in the dashboard — show WHY a lead scored 72 not just the number.

---

## Database Schema

```sql
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

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT,
    message TEXT,
    read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Web Dashboard Spec

**Layout:** Dark sidebar + white content area. Vanilla CSS only — no frameworks. System font stack.

**Sidebar navigation:**
- 🏠 Dashboard
- 📋 Campaigns
- 👥 Leads
- ✉️ Sequences
- 📊 Analytics

**Dashboard (`/`):** Sent today, active campaigns, total leads, warmup status card. Campaign status panel. Notifications panel. Recent activity feed. Polls `/api/notifications` every 60s.

**Campaigns (`/campaigns`):** Table with status badges. Campaign detail: strategy panel, 4-email sequence cards, lead breakdown, action bar (Approve / Pause / Resume / Edit / Export). Approval flow: strategy review → lead quality summary → full sequence → "Send test to myself" button → Approve / Reject.

**Leads (`/leads`):** Full CRM table. Score shown as number + colour (green ≥70, yellow 40–69, red <40). Click row → detail modal with score breakdown (each sub-score visible), full outreach history. Filter by campaign / status / score range / country. Bulk approve/reject.

**Sequences (`/sequences`):** View and inline-edit all 4 emails per campaign. Validate button runs spam filter. Editable only for draft/paused campaigns.

**Analytics (`/analytics`):** Funnel chart (Found → Approved → Sent → Opened → Replied → Interested). Daily send time series (Chart.js CDN). Top subject lines by open rate. Deliverability health with threshold colour coding. API cost breakdown (Claude spend by purpose, current month vs limit).

---

## Config Structure

```yaml
apollo:
  api_key: ""
  monthly_credit_limit: 75  # CONFIRMED: Apollo free tier = 75 credits/month

hunter:
  api_key: ""
  monthly_search_limit: 50  # CONFIRMED: Hunter free tier = 50 searches/month

lusha:
  api_key: ""
  monthly_credit_limit: 40

snov:
  user_id: ""
  api_secret: ""
  monthly_credit_limit: 50

getprospect:
  api_key: ""
  monthly_credit_limit: 50

claude:
  api_key: ""
  model: "claude-haiku-4-5"
  max_tokens: 2000
  monthly_cost_limit_usd: 4.00

google:
  sheets_spreadsheet_id: ""
  credentials_path: "credentials.json"
  maps_api_key: ""

email:
  warmup_provider: "instantly"   # "instantly" | "lemwarm" | "manual"
  warmup_active: true             # Set false after warmup — switches to Gmail SMTP
  instantly_api_key: ""
  instantly_campaign_id: ""
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  address: ""
  app_password: ""
  daily_send_limit: 20
  min_delay_seconds: 180
  max_delay_seconds: 600

outreach:
  default_touchpoints: 4
  default_cadence_days: [0, 4, 10, 18]
  timezone: "Europe/Berlin"
  sending_window_start: 9
  sending_window_end: 18
  send_weekdays_only: true
  unsubscribe_footer: true

tracking:
  pixel_base_url: ""
  enabled: false

web:
  host: "127.0.0.1"
  port: 5000
  secret_key: ""

deliverability:
  warmup_daily_limit: 10
  warmup_days_elapsed: 0
```

---

## Warmup Schedule

```
Week 1:   10/day  — warmup only
Week 2:   20/day  — warmup only
Week 3:   30/day  — 20 warmup + 10 real prospects
Week 4:   40/day  — 10 warmup + 30 real prospects
Month 2:  50-80/day — warmup off, full Gmail SMTP
```

Switch: set `warmup_active: false` in config — agent switches to Gmail SMTP automatically.

---

## Agency Agents Integration

Agent personalities from [agency-agents](https://github.com/msitarzewski/agency-agents) inform the system prompt design for each module. These are **design-time resources only** — not runtime dependencies.

| Agent | Informs |
|---|---|
| `sales-outbound-strategist` | `agents/strategy_generator.py` system prompt |
| `engineering-email-intelligence-engineer` | `agents/reply_analyzer.py` + `core/reply_handler.py` |
| `sales-discovery-coach` | `agents/copywriter.py` Email 1 hook question design |
| `sales-pipeline-analyst` | `web/routes/analytics.py` health scoring logic |
| `specialized-agents-orchestrator` | `main.py` multi-agent coordination pattern |

---

## Pending Tasks

### Fix Now — Before First Real Campaign

These are bugs or gaps that make current output unreliable:

**1. Buying signals never populated (35pts always = 0)**
Build `agents/buying_signal_checker.py`. Homepage pixel scan on all leads. Facebook Transparency check on leads scoring >40. Store in `buying_signals` JSON field. Connect to `_score_ad_spend()` and `_score_multi_location()` in lead_enricher.py.

**2. Hunter confidence not a structured field**
In `integrations/hunter.py`, extract confidence as integer field on the lead dict (not buried in notes string). Update hard gate check in lead_enricher.py to read `lead["hunter_confidence"]` correctly.

**3. Google Sheets sync duplicates rows**
Fix `integrations/google_sheets.py` — match on email as unique key, update row in place if found, insert only if new. Never append blindly. Do NOT run `python main.py sync` until this is fixed.

**4. Spam filter blocks instead of warns**
In `agents/copywriter.py`, if `_check_spam()` finds triggers, reject the draft and regenerate (up to 3 attempts). If still failing after 3 attempts, flag for human review — do not save and use.

**5. Weekend cadence drift**
In `core/scheduler.py`, when scheduling future steps, advance the target date forward to the next weekday if it falls on Saturday or Sunday. Log the adjustment.

**6. Apollo CLI credit gate**
Move credit check into `integrations/apollo.py` `search_people()` method directly — not just in the web routes. CLI `python main.py find` must also enforce the limit.

**7. Hunter monthly limit never enforced**
Add pre-call credit check in `integrations/hunter.py` — same pattern as Apollo.

### Build Next — Adds Real Capability

**8. Two-phase lead finding architecture**
Rebuild `agents/lead_finder.py` with Phase 1 (company discovery) and Phase 2 (contact resolution) separation. Implement pre-search dedup at all three levels (email, company+contact, domain). Add `core/credit_manager.py` for budget allocation.

**9. New integrations: Lusha, Snov.io, GetProspect**
Build in this order:
- `integrations/lusha.py` — 40 credits/month, strongest for European contacts
- `integrations/snov.py` — 50 credits/month, email finder
- `integrations/getprospect.py` — 50 credits/month, LinkedIn-based
Each must hard-stop at monthly limit, log to api_usage table.

**10. Facebook Ad Library integration**
Build `integrations/facebook_ads.py` — Playwright scraper for Ad Library search by keyword/vertical + Facebook Page Transparency check. Feed results into buying_signals.

**11. LinkedIn properly wired**
Connect `integrations/linkedin_scraper.py` as the final fallback in Phase 2 contact resolution. Extract name + title, pass domain to Hunter for email.

**12. Manual credit override on Step 6**
Add credit budget panel to wizard Step 6 showing live per-source credit remaining. Allow operator to override per-source allocation before starting run. Default is automatic allocation from credit_manager.

**13. Dashboard credit bank widget**
Add live credit bank status to dashboard home — all sources, credits remaining this month, resets on 1st of month.

### Polish Later

**14. Funnel chart in analytics**
Found → Approved → Sent → Opened → Replied → Interested. Assemble funnel data in analytics.py route.

**15. Top subject lines by open rate**
In analytics.py, query outreach_log joined to sequences, group by subject, rank by open rate.

**16. Per-lead score breakdown in detail modal**
Verify lead_detail.html renders individual sub-scores visually, not just the total.

**17. AI reply classifier connected**
In reply_handler.py, call `classify_reply_with_ai()` for ambiguous replies instead of defaulting to "human_unknown".

**18. Warmup auto-switch logic**
Increment `warmup_days_elapsed` daily in scheduler. Auto-advance warmup limits per schedule. Auto-switch to Gmail SMTP when warmup_active set to false.

### Pending Setup (not blocking code work)
- Buy outreach domain (~€10) — needed before any emails can send
- Set up Cloudflare DNS (SPF, DKIM, DMARC, MX, Vercel CNAME)
- Sign up for Instantly free trial (warmup)
- Sign up for Lusha, Snov.io, GetProspect free tiers → get API keys
- Share Google Sheet with service account email from credentials.json
- Run `python scripts/dns_checker.py --domain yourdomain.com`

### Open Decisions
- Final brand/domain name (ProspectCore GbR dissolution in progress)
- Einstiegsgeld meeting — do NOT register Gewerbe before then

---

## CLI Reference

```bash
python main.py                              # Start dashboard + scheduler
python main.py find --icp "..." --limit 10 # Find leads
python main.py find --dry-run              # Preview without using credits
python main.py sync                         # Force Sheets sync
python main.py status                       # Campaign status summary
python main.py pause --campaign <id>
python main.py resume --campaign <id>
python main.py export --campaign <id>
python scripts/setup.py                     # First-time setup
python scripts/migrate_lead_scores.py       # Run DB migration
python scripts/dns_checker.py --domain x    # Check DNS records
```

---

## Quality Standards

- Every function has a docstring
- Every API call has specific, actionable error handling
- Every email logged to SQLite BEFORE sending
- All secrets in config.yaml only — never hardcoded
- `--dry-run` flag available on find and send commands
- Human reply detection tested against: OOO, bounce, interested reply, not interested reply, one-word reply, forwarded email
- Web UI readable without JavaScript for core views (progressive enhancement)
