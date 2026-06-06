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
| Lead finding — primary B2B contacts | Snov.io free tier (50 credits/month) | €0 |
| Lead finding — European contacts | Lusha free tier (40 credits/month) | €0 |
| Lead finding — LinkedIn-based | GetProspect free tier (50 credits/month) | €0 |
| Lead finding — company + contact enrichment | People Data Labs free tier (100 lookups/month) | €0 |
| Email resolution | Hunter.io free tier (50 searches/month) | €0 |
| Company discovery — local/SMB | Google Maps Places API | €0 |
| Company discovery — ad-active companies | Facebook Ad Library (public) | €0 |
| Company discovery — industry directories | Vertical scrapers (Playwright) | €0 |
| Ad spend signal | Homepage pixel check + Facebook Transparency | €0 |
| LinkedIn contact data | Playwright public scraper | €0 |
| CRM | Google Sheets API | €0 |
| AI | Claude API — claude-haiku-4-5 | ~€0.02/campaign |
| Email sending | Gmail SMTP + custom domain | €0 |
| Dashboard | Flask + Jinja2 + vanilla CSS | €0 |
| State | SQLite | €0 |

**Apollo.io note:** Apollo free tier does NOT include API access — web UI only. Apollo is kept in the codebase as a paid upgrade path (~$49/month for Basic with API access) but is NOT used as an active source. Do not call Apollo API on free tier — it returns 403.

**Combined free contact bank: ~290 API credits/month + unlimited directory + unlimited Google Maps/Facebook**

| Source | Type | Credits/month | Strength |
|---|---|---|---|
| Snov.io | API | 50 | Primary B2B contact finder, email resolution |
| Lusha | API | 40 | Strongest for European/DACH contacts |
| GetProspect | API | 50 | LinkedIn-based contact extraction |
| People Data Labs | API | 100 | Company + contact enrichment, strong B2B database |
| Hunter | API | 50 | Domain-based email resolution, high accuracy |
| Google Maps | Unlimited | ∞ | Company discovery by vertical + city |
| Facebook Ad Library | Unlimited | ∞ | Active advertiser discovery |
| Industry directories | Scraped | ∞ | Pre-qualified ICP companies, vertical-specific |
| Apollo | Paid upgrade only | — | Activate when paying ~$49/month |

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
│   ├── icp_analyzer.py        # Structured wizard inputs → search params
│   ├── lead_finder.py         # Two-phase architecture: Discovery → Contact Resolution
│   ├── lead_enricher.py       # Email validation + weighted lead buyer scoring
│   ├── buying_signal_checker.py # Homepage pixel check + Facebook Transparency check
│   ├── strategy_generator.py  # AI outreach strategy generation
│   ├── copywriter.py          # 4-email sequence (SPIN-informed Email 1, break-up Email 4)
│   └── reply_analyzer.py      # Thread reconstruction + human vs automated classification
│
├── integrations/
│   ├── apollo.py              # Apollo.io — PAID UPGRADE ONLY, 403 on free tier
│   ├── hunter.py              # Hunter.io API — 50 search/month hard stop
│   ├── lusha.py               # Lusha API — 40 credit/month hard stop (European contacts)
│   ├── snov.py                # Snov.io API — 50 credit/month hard stop (PRIMARY source)
│   ├── getprospect.py         # GetProspect API — 50 credit/month hard stop (LinkedIn-based)
│   ├── people_data_labs.py    # PDL API — 100 lookup/month hard stop (company + contact enrichment)
│   ├── google_sheets.py       # Bidirectional CRM sync — update in place, no duplicates
│   ├── gmail_smtp.py          # Email sending — daily limit enforced
│   ├── instantly.py           # Warmup only — free trial, switches off via config flag
│   ├── linkedin_scraper.py    # Playwright, 2-5s delays, max 50/session
│   ├── facebook_ads.py        # Facebook Ad Library + Page Transparency scraper
│   └── google_maps.py         # Places API for company discovery
│
├── scrapers/                  # Vertical-specific industry directory scrapers
│   ├── base_scraper.py        # Shared Playwright setup, rate limiting, standard output format
│   ├── solar_de.py            # BSW-Solar member directory (Germany)
│   ├── solar_uk.py            # Solar Energy UK member directory
│   ├── home_improvement_uk.py # FMB (Federation of Master Builders) directory
│   ├── finance_uk.py          # NACFB broker directory (UK)
│   └── finance_de.py          # BdB member directory (Germany)
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
- Apollo: **75**/month (PAID UPGRADE ONLY — do not use on free tier)
- Hunter: **50**/month
- Lusha: 40/month
- Snov.io: 50/month
- GetProspect: 50/month
- People Data Labs: 100/month

`check_and_spend()` checks remaining credits against the monthly limit in config, raises `CreditLimitReached` if hit, logs the spend to `api_usage` on success.

### 5. Unsubscribe Is Absolute
Any reply containing "unsubscribe", "remove me", "stop emailing", "opt out" → immediately cancel all scheduled steps, mark lead as `unsubscribed`, never contact again. This cannot be reversed by the operator.

---

## Two-Phase Lead Finding Architecture

Lead finding operates in two distinct phases. Never merge them.

### Phase 1 — Company Discovery
Find companies that match the ICP. Sources used in order:

1. **Industry Directory Scrapers** (`scrapers/`) — Pre-qualified ICP companies from vertical-specific directories. Unlimited, zero credits, highest targeting quality. Run first.
2. **Google Maps** — Companies by vertical + city. Unlimited, use freely.
3. **Facebook Ad Library** — Companies actively running ads in a vertical. Free, high buying signal value.
4. **Apollo** — PAID UPGRADE ONLY. Do not call on free tier (returns 403). Activate when Apollo Basic paid plan is purchased.

Output of Phase 1: a list of companies (name + domain) with no contact person yet.

**ICP targeting note:** Primary targets are mid-to-large operators with national/regional scale, dedicated sales teams, and existing lead buying infrastructure (e.g. Enpal, Power HRG equivalents). NOT micro-SMBs or solo tradesmen. Verticals: solar, home improvement (roofing/HVAC/windows/siding), business loans/finance. These companies have LinkedIn presence, corporate email infrastructure, and appear in B2B contact databases.

### Phase 2 — Contact & Email Resolution
For each company found in Phase 1, find the right person and their email. Sources tried in order, stopping as soon as a verified email is found:

1. **Apollo** — if Apollo found the company, it may already have a contact. Check first, no extra credit spent.
2. **Lusha** — try next, especially strong for European/DACH companies.
3. **Snov.io** — email finder by domain.
4. **People Data Labs** — company + contact enrichment, 100 lookups/month.
5. **GetProspect** — LinkedIn-based contact extraction.
6. **Hunter** — domain search as final resolver.
7. **LinkedIn scraper** — Playwright, extract contact name + title, then pass to Hunter for email.

Stop as soon as a verified email is found. Never call multiple Phase 2 sources for the same company.

### Directory Scrapers (`scrapers/`)

Vertical-specific Playwright scrapers that extract member company names and domains from industry trade association directories. These are pre-qualified ICP companies — industry members are exactly the kind of national/regional operators we want to reach.

**Base class (`scrapers/base_scraper.py`):**
- Shared Playwright setup with random user agent rotation
- Rate limiting: 2–5 second random delays between requests
- Retry logic: up to 3 attempts on failure
- Standard output format: `[{company_name, domain, country, vertical, source_url}]`
- Results cached in `directory_companies` SQLite table — never re-scrape same directory within 7 days

**Active scrapers:**

| File | Directory | Vertical | Geo | Est. Companies |
|---|---|---|---|---|
| `solar_de.py` | BSW-Solar members | Solar | Germany | ~300 |
| `solar_uk.py` | Solar Energy UK members | Solar | UK | ~150 |
| `home_improvement_uk.py` | FMB (Federation of Master Builders) | Home improvement | UK | ~8,000 |
| `finance_uk.py` | NACFB broker directory | Business loans | UK | ~2,000 |
| `finance_de.py` | BdB member directory | Finance | Germany | ~200 |

**Scraper selection logic in `lead_finder.py`:**
- Campaign vertical = "solar" + geo = "de" → run `solar_de.py`
- Campaign vertical = "solar" + geo = "uk" → run `solar_uk.py`
- Campaign vertical = "home improvement" + geo = "uk" → run `home_improvement_uk.py`
- Campaign vertical = "finance/loans" + geo = "uk" → run `finance_uk.py`
- Campaign vertical = "finance/loans" + geo = "de" → run `finance_de.py`
- Unknown vertical → skip scrapers, fall through to Google Maps

**CLI command:**
```bash
python main.py scrape --vertical solar --geo de           # Run scraper manually
python main.py scrape --vertical solar --geo de --dry-run # Preview without storing
```

**New SQLite table:**
```sql
CREATE TABLE IF NOT EXISTS directory_companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    domain TEXT,
    country TEXT,
    vertical TEXT,
    source_url TEXT,
    source_file TEXT,        -- which scraper found it
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed INTEGER DEFAULT 0  -- 1 = already sent to Phase 2
);
```

---

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
- Include unsubscribe line in the campaign language: "Not relevant? Reply 'unsubscribe' and I'll remove you." (translated appropriately)
- Pass spam trigger word filter before finalising
- Be plain text only
- Be written entirely in the campaign language — never mix languages

---

## ICP Wizard — New Campaign Flow

The "New Campaign" form is a **6-step structured wizard**. No free-text ICP description. Claude auto-generates the ICP and Apollo search params from the structured inputs.

**Step 1 — Vertical:** dropdown + free text (e.g. "Solar", "Home Services", "Insurance")
**Step 2 — Geography:** country multi-select + optional cities + **language selector**
  - Language dropdown: English, German, French, Dutch, Spanish, Italian, Portuguese, Other
  - Default: auto-detect from country selection (Germany/Austria/Switzerland → German, UK/US/AU → English, etc.)
  - Language applies to: all 4 generated emails, subject lines, strategy rationale
  - Operator can override auto-detected language at any time before generating
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

people_data_labs:
  api_key: ""
  monthly_credit_limit: 100

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

## Build Handover — Full Status Audit

Last updated: 2026-06-06. Three columns: code is complete and verified | code is written but never run against a live system | not yet written.

---

### Column 1 — Built and complete ✅

**Core infrastructure**
- SQLite schema + 50+ CRUD operations (`core/database.py`) — all tables including `directory_companies` and `send_queue`; additive migration on startup
- Credit manager — centralised gate for all 6 API sources with rolling/calendar reset windows (`core/credit_manager.py`)
- Pre-search deduplicator — 3-level: L1 email, L2 company+contact, L3 domain (`core/deduplicator.py`)
- Email format + MX validator with DNS caching (`core/email_validator.py`)
- Background send scheduler — weekday/time-window aware, resumes from SQLite on Codespaces restart (`core/scheduler.py`)
- Human reply handler — IMAP poller, rule-based OOO/bounce/unsubscribe/human classifier, sequence cancellation, Sheets sync (`core/reply_handler.py`)

**Agents**
- ICP analyzer — legacy free-text path + structured 6-step wizard path; JSON validation, fence stripping (`agents/icp_analyzer.py`)
- Lead finder — full two-phase orchestrator: Phase 1 (scrapers → Apollo → Maps → FB Ads), Phase 2 (7-source resolution chain), buying signal injection, enrich pipeline, DB + Sheets save (`agents/lead_finder.py`)
- Lead enricher — deterministic 7-criterion scoring (title 20 + company_size 15 + multi_location 15 + ad_spend 20 + ltv_vertical 15 + marketing_roles 10 + data_completeness 5); hard auto-reject gates; rationale builder (`agents/lead_enricher.py`)
- Buying signal checker — homepage pixel scan (Meta/Google Ads/GTM/TrustedForm/Jornaya) + Facebook Page Transparency Playwright check (`agents/buying_signal_checker.py`)
- Strategy generator — Claude-powered JSON outreach strategy, multi-language (`agents/strategy_generator.py`)
- Copywriter — 4-email SPIN sequence (80/70/100/30 words), spam-trigger filter, unsubscribe footer, multi-language with translated footer (`agents/copywriter.py`)
- Reply analyzer — AI classification with rule-based fallback, thread reconstruction, quoted-text stripping (`agents/reply_analyzer.py`)
- Claude client — cost wrapper for all Anthropic API calls; monthly $4 budget enforcement; `api_usage` logging (`agents/claude_client.py`)

**Integrations**
- Apollo.io — people search with full parameter mapping; **PAID UPGRADE ONLY** (free tier returns 403, intentionally no-ops) (`integrations/apollo.py`)
- Hunter.io — domain search + name-based email finder + verify; confidence threshold 70 (`integrations/hunter.py`)
- Google Maps — Places API text search for company discovery (`integrations/google_maps.py`)
- Google Sheets — bidirectional CRM sync, email-key upsert, no duplicates (`integrations/google_sheets.py`)
- Gmail SMTP — full email construction with headers, threading, retry (`integrations/gmail_smtp.py`)

**Scrapers**
- Base scraper — Playwright lifecycle, 7-day result caching, user-agent rotation, retry, standard output format (`scrapers/base_scraper.py`)
- Scraper registry and ICP-to-scraper routing (`scrapers/__init__.py`)
- NOTE: All 5 vertical scrapers were moved to Column 2 — BSW-Solar confirmed broken (login wall); others unverified

**Web dashboard**
- Flask factory + all 6 blueprints registered (`web/app.py`, `web/routes/api.py`)
- Dashboard — stats, notifications, credit bank widget, warmup status (`web/routes/dashboard.py`)
- Campaigns — 6-step ICP wizard, strategy + sequence generation, approval flow, delete/archive with confirmation, "Show archived" toggle (`web/routes/campaigns.py`)
- Leads — CRM table, score breakdown, filters, bulk approve/reject, CSV export, outreach history modal (`web/routes/leads.py`)
- Sequences — inline email editor, spam-trigger validator, token checker, status-gated edits (`web/routes/sequences.py`)
- Analytics — funnel stats, daily send chart (Chart.js), subject line rates, API cost breakdown (`web/routes/analytics.py`)
- All 9 Jinja2 templates — dark sidebar, white content, vanilla CSS (`web/templates/`)
- Language selection — Step 2 dropdown, auto-detect from country, stored on `campaigns.language` column

**Other**
- Open tracking pixel (`tracking/pixel.py`)
- First-time setup wizard (`scripts/setup.py`)
- DNS record checker — SPF/DKIM/DMARC/MX (`scripts/dns_checker.py`)
- CLI entry point — all commands: default (server+scheduler), `find`, `scrape`, `sync`, `status`, `pause`, `resume`, `export` (`main.py`)

---

### Column 2 — Built but not yet tested against live systems ⚠️

These modules are code-complete but have never been exercised with real credentials, real network traffic, or real HTML page structures. They may work on first run or may need selector/auth fixes.

| Module | What needs live testing | Risk |
|---|---|---|
| `integrations/people_data_labs.py` | PDL Person Search + Company Enrich API — API key just wired in, no real call made yet | Low — standard REST API, PDL docs are stable |
| `integrations/lusha.py` | Lusha API v2 — credentials in config, no real contact lookup run | Low — REST API |
| `integrations/snov.py` | Snov.io OAuth2 token flow + domain search — credentials in config, not exercised | Medium — OAuth token refresh is the likely failure point |
| `integrations/getprospect.py` | GetProspect domain search — API key in config, not exercised | Low — simple REST API |
| `integrations/instantly.py` | Warmup status check + pool addition — free trial not started | Medium — depends on trial activation |
| `integrations/linkedin_scraper.py` | Playwright public people search — bot detection, LinkedIn layout changes | High — LinkedIn actively blocks scrapers; user-agent rotation may not be enough |
| `integrations/facebook_ads.py` | Playwright Ad Library + Page Transparency — page structure can change, cookie-consent pop-up handling | Medium — consent overlay handling is brittle |
| `integrations/google_maps.py` | Places API — key not yet filled in `config.yaml` | Low — well-documented API |
| `integrations/google_sheets.py` | CRM sync — service account credentials.json not yet shared with the target spreadsheet | Low — auth works once credentials.json is placed and sheet is shared |
| `scrapers/solar_de.py` | **CONFIRMED BROKEN** — BSW-Solar requires login; scraper hits redirect and saves nav links as fake companies. Cache polluted with 12 garbage records in `directory_companies` table — must be purged before next run. | Critical |
| `scrapers/solar_uk.py` | Solar Energy UK actual page — accessibility unverified | High — assume login-wall risk until checked |
| `scrapers/home_improvement_uk.py` | FMB builder finder — accessibility unverified | High |
| `scrapers/finance_uk.py` | NACFB broker finder — accessibility unverified | High |
| `scrapers/finance_de.py` | BdB member directory — accessibility unverified | High |
| `core/reply_handler.py` + `core/scheduler.py` | Full email send → reply cycle — no live email flow has ever run | High — end-to-end only testable once domain + DNS + warmup are live |
| `agents/copywriter.py` (non-English) | German/French/Dutch/Spanish/Italian/Portuguese output — code supports it, no real output reviewed | Medium — Claude follows language instruction well but footer translations untested |
| `tracking/pixel.py` | Open event recording — needs a live hosted URL to embed in emails | Low once domain is live |
| Analytics charts | Chart.js funnel + time-series — needs real campaign data to render non-empty | Low — renders empty gracefully |

---

### Column 3 — Not yet built ❌

| Feature | Where it belongs | Notes |
|---|---|---|
| Funnel chart (Found → Approved → Sent → Opened → Replied → Interested) | `web/routes/analytics.py` + `analytics.html` | Data queries exist; Chart.js frontend wiring not done |
| Top subject lines by open rate | `web/routes/analytics.py` | Needs real opened_at data before it's meaningful |
| AI reply classifier upgrade | `agents/reply_analyzer.py` | Rule-based fallback works; AI path exists but ambiguous replies (e.g. "maybe later") not confidently classified |
| Warmup auto-increment | `core/scheduler.py` | `warmup_days_elapsed` in config is manually set; daily auto-increment not implemented |
| Apollo paid activation toggle | `integrations/apollo.py` | Currently always raises 403; needs a `paid_tier: true` config flag to re-enable real API calls |
| Test suite | `tests/` (doesn't exist) | Zero test files anywhere in the repo — no unit, integration, or end-to-end tests |
| A/B sequence split-test runner | `core/scheduler.py` + `web/routes/campaigns.py` | Strategy JSON includes A/B ideas but no infrastructure to send variant A to half the list |
| Lead import from CSV | `web/routes/leads.py` | No manual upload path — leads only come from automated Phase 1/2 discovery |
| Config.yaml validation on startup | `main.py` or `scripts/setup.py` | No schema check; missing keys cause runtime errors with unclear messages |
| **Phase 1 company discovery redesign** | `agents/lead_finder.py` + `scrapers/` | All current Phase 1 sources are broken or missing API keys. Operator to define new approach — see Known Issues section above. Do not build until approach is agreed. |
| Wizard Step 6 — separate submit CTA + background job + redirect | `web/routes/campaigns.py`, `web/templates/campaigns.html` | See Known Issues section — 504 timeout fix depends on this |
| Dashboard credit bank widget — remove Apollo, reflect real source list | `web/routes/dashboard.py`, `web/templates/dashboard.html` | |
| Full Apollo language audit in wizard | `web/routes/campaigns.py`, `web/templates/campaigns.html` | Remove all Apollo references from Step 6 UI |

---

### Real-world blockers (not code — nothing to build until these are resolved)

| Blocker | Unblocks |
|---|---|
| Buy outreach domain (~€10) — **single biggest blocker** | Everything email-related |
| Set up Cloudflare DNS — SPF, DKIM, DMARC, MX, pixel CNAME | Email deliverability, open tracking |
| Sign up for Instantly.ai free trial | Inbox warmup (weeks 1–4) |
| Share Google Sheet with service account email from `credentials.json` | CRM sync |
| Run `python scripts/dns_checker.py --domain yourdomain.com` | DNS verification |
| Einstiegsgeld meeting — do NOT register Gewerbe before this | Legal/business entity |
| Finalise brand/domain name — ProspectCore GbR dissolution in progress (one partner pending) | Domain purchase |

---

### Apollo status reminder

Apollo free tier does NOT include API access — returns 403. Apollo code is kept in the codebase as a paid upgrade path (~$49/month for Basic). Do not attempt to activate Apollo until the paid plan is purchased. All other Phase 2 sources (Lusha, Snov.io, GetProspect, PDL, Hunter) work on free tiers.

---

## CLI Reference

```bash
python main.py                              # Start dashboard + scheduler
python main.py find --icp "..." --limit 10 # Find leads
python main.py find --dry-run              # Preview without using credits
python main.py scrape --vertical solar --geo de           # Run directory scraper
python main.py scrape --vertical solar --geo de --dry-run # Preview scraper output
python main.py sync                         # Force Sheets sync
python main.py status                       # Campaign status summary
python main.py pause --campaign <id>
python main.py resume --campaign <id>
python main.py export --campaign <id>
python scripts/setup.py                     # First-time setup
python scripts/migrate_lead_scores.py       # Run DB migration (already done)
python scripts/dns_checker.py --domain x    # Check DNS records
```

---

## Known Issues & Open Backlog — Last reviewed 2026-06-06

Issues found during first end-to-end test of the live dashboard. Prioritised by severity.

---

### CRITICAL — Phase 1 company discovery is completely broken

**Root cause:** Every Phase 1 source is currently non-functional:

| Source | Status | Reason |
|---|---|---|
| BSW-Solar scraper (`scrapers/solar_de.py`) | Broken | The member directory at `solarwirtschaft.de/verbraucher/mitglieder/` requires a login. The scraper hits the login redirect, falls back to "extract all external links", and saves nav links as fake companies ("Mehr", "Shop", `bee-ev.de`, etc.). The 7-day cache then locks in this garbage for the week. |
| All other vertical scrapers | Untested | Assumed broken or inaccessible until verified — same login-wall risk applies |
| Google Maps | Skipped | `maps_api_key` is blank in config.yaml |
| Facebook Ads | Unreliable | Playwright hits consent/bot detection in headless Codespaces environment |
| Apollo | Disabled | Paid upgrade only — intentional |

**Consequence:** Phase 2 resolution sources (Lusha, Snov, Hunter, PDL, GetProspect) are working correctly but have nothing to work on. Every campaign run returns zero leads.

**Phase 2 sources are resolvers, not discoverers** — they answer "who works at enpal.de?" not "which companies should I target?". They cannot substitute for a broken Phase 1.

**What needs to happen:** Phase 1 requires a complete redesign. The operator should come back with a decision on the new approach before any code is written. Options to consider:
- Replace BSW-Solar URL with a publicly accessible German solar directory (needs research)
- Wire up Google Maps as the primary Phase 1 source (just needs the API key filled in — low effort, high impact)
- Add a manual company seed list — operator pastes in known target domains, Phase 2 resolves contacts
- PDL company search as a Phase 1 discovery source (PDL has company search endpoints, not just person lookup)
- Rethink scraper targets: verify each directory is publicly accessible BEFORE building the scraper

**Immediate quick win while redesign is decided:** Fill in `google.maps_api_key` in config.yaml. Google Maps is already coded and working — it just needs the key. This alone would give Phase 1 a real discovery source for any vertical + geo.

---

### Dashboard — Credit bank widget still shows Apollo as primary source

The credit bank section on the main dashboard (`/`) lists Apollo, Hunter, Lusha, Snov, GetProspect as the lead sources. This was the original source list before the waterfall logic was updated. The widget does not reflect the current Phase 2 source order (Lusha → Snov → PDL → GetProspect → Hunter) and still presents Apollo as if it were active.

**File to fix:** `web/routes/dashboard.py` and `web/templates/dashboard.html`

---

### ICP Wizard Step 6 — Apollo language and logic throughout

Two separate problems in Step 6:

1. **Lead Limits / Credit Budget panel** still references Apollo credits and presents Apollo as the primary lead source. All Apollo-specific language and credit logic should be replaced to reflect the actual active sources.

2. **Action buttons** ("Find Leads", "Generate Strategy & Sequence Only", "Do Both") also reference Apollo credits in their helper text.

**File to fix:** `web/routes/campaigns.py` and `web/templates/campaigns.html` — audit every reference to Apollo in the wizard flow.

---

### ICP Wizard Step 6 — UX: no clear submission CTA, no feedback after submit

Current behaviour:
- The three action buttons ("Find Leads", "Generate Strategy…", "Do Both") act as both the selection AND the submit trigger. This is confusing — the user doesn't know if clicking selects the option or fires the request.
- After clicking, the screen hangs. A small "Working…" text appears inside the button that was clicked but is easy to miss.
- There is no redirect, no progress indication, no ETA, no confirmation that the request was received.

Required behaviour:
- Add a separate "Let's Go" / "Submit" CTA button at the bottom of Step 6. The three action buttons should be selection controls only, not submit triggers.
- On submit: immediately redirect to the Campaigns list page. Show a banner/notification: "Campaign created — [find leads / strategy / both] in progress. Estimated time: X minutes."
- The 504 timeout the user saw is a Codespaces port forwarding timeout (30s) on long-running requests. The operation completes server-side but the browser gives up. Redirect on submit (before the work finishes) is the fix — the work runs in the background and the dashboard polls for completion.

**File to fix:** `web/routes/campaigns.py`, `web/templates/campaigns.html`

---

### 504 timeout on long-running requests

When "Find Leads" or "Do Both" is submitted, the browser tab shows a 504 after ~30 seconds. The Codespaces port forwarding proxy has a 30s idle timeout on HTTP responses. The lead-finding job can take 2–5 minutes. The fix is to return an immediate HTTP response (redirect or 202 Accepted) and run the job in the background, not in the request thread. The scheduler architecture already supports background jobs — lead finding should be queued the same way.

**File to fix:** `web/routes/campaigns.py` — move `find_leads()` call off the request thread into a background task.

---

## Quality Standards

- Every function has a docstring
- Every API call has specific, actionable error handling
- Every email logged to SQLite BEFORE sending
- All secrets in config.yaml only — never hardcoded
- `--dry-run` flag available on find and send commands
- Human reply detection tested against: OOO, bounce, interested reply, not interested reply, one-word reply, forwarded email
- Web UI readable without JavaScript for core views (progressive enhancement)