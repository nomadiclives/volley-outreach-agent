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
| Lead finding | Apollo.io free tier (75 credits/month) | €0 |
| Email finding | Hunter.io free tier (50 searches/month) | €0 |
| Local businesses | Google Maps Places API | €0 |
| LinkedIn | Playwright public scraper | €0 |
| CRM | Google Sheets API | €0 |
| AI | Claude API — claude-haiku-4-5 | ~€0.02/campaign |
| Email sending | Gmail SMTP + custom domain | €0 |
| Dashboard | Flask + Jinja2 + vanilla CSS | €0 |
| State | SQLite | €0 |

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
│   ├── lead_finder.py         # Apollo → Hunter → Google Maps → LinkedIn waterfall
│   ├── lead_enricher.py       # Email validation + weighted lead buyer scoring
│   ├── strategy_generator.py  # AI outreach strategy generation
│   ├── copywriter.py          # 4-email sequence (SPIN-informed Email 1, break-up Email 4)
│   └── reply_analyzer.py      # Thread reconstruction + human vs automated classification
│
├── integrations/
│   ├── apollo.py              # Apollo.io API — 75 credit/month hard stop
│   ├── hunter.py              # Hunter.io API — 50 search/month hard stop
│   ├── google_sheets.py       # Bidirectional CRM sync
│   ├── gmail_smtp.py          # Email sending — daily limit enforced
│   ├── instantly.py           # Warmup only — free trial, switches off via config flag
│   ├── linkedin_scraper.py    # Playwright, 2-5s delays, max 50/session
│   └── google_maps.py         # Places API for local/SMB sourcing
│
├── core/
│   ├── database.py            # SQLite schema + all CRUD
│   ├── deduplicator.py        # Cross-source deduplication
│   ├── email_validator.py     # MX check + format validation
│   ├── scheduler.py           # Background send engine — resumes from SQLite on restart
│   └── reply_handler.py       # CRITICAL: human reply → immediate sequence cancellation
│
├── web/
│   ├── app.py                 # Flask factory
│   ├── routes/
│   │   ├── dashboard.py       # Home — stats, notifications, warmup status
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
    ├── migrate_lead_scores.py # DB migration — adds scoring columns to leads table
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

### 4. API Credit Hard Stops
- Apollo: hard stop at `apollo.monthly_credit_limit` (default 75)
- Hunter: hard stop at `hunter.monthly_search_limit` (default 50)
- Both tracked in `api_usage` table, checked before every call

### 5. Unsubscribe Is Absolute
Any reply containing "unsubscribe", "remove me", "stop emailing", "opt out" → immediately cancel all scheduled steps, mark lead as `unsubscribed`, never contact again. This cannot be reversed by the operator.

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
  monthly_credit_limit: 75

hunter:
  api_key: ""
  monthly_search_limit: 50

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

## Pending Tasks (as of last session)

### Completed ✅
- DB migration (`scripts/migrate_lead_scores.py`) — all scoring columns added
- Lead scorer (`agents/lead_enricher.py`) — weighted 100-point framework implemented
- ICP wizard — 6-step structured wizard built and working

### Immediate — implement via Claude Code (next session)

**Change A — Soft vs hard filter logic**
Update `agents/lead_finder.py` and `agents/lead_enricher.py` so that only hard gates exclude leads (employee <5, solo operator, red flag verticals, unverifiable email). All other wizard selections (buying signals, multi-location, title match) affect the score only — never exclude. A lead scoring 45 should appear in yellow, not be filtered out.

Files: `agents/lead_finder.py`, `agents/lead_enricher.py`

**Change B — Lead limit input on Step 6**
Add a numeric input to the Step 6 wizard screen (visible when "Find Leads Only" or "Do Both" is selected). Default: 10. Maximum: remaining Apollo credits (calculated from api_usage table: 75 minus credits used this month). Show remaining credits as helper text next to the input.

Files: `web/templates/campaigns.html`, `web/routes/campaigns.py`

**Change C — Three action buttons on Step 6**
Replace the single "Generate Strategy & Sequence" button with three clearly labelled action buttons:
- **Find Leads Only** → triggers `/campaigns/find-leads` route
- **Generate Strategy & Sequence Only** → triggers `/campaigns/generate-sequence` route  
- **Do Both** → triggers `/campaigns/find-and-generate` route

Each button should have a one-line description underneath it explaining what it does and what it costs (credits/API). Each route must work fully independently.

Files: `web/templates/campaigns.html`, `web/routes/campaigns.py`, `main.py`

### Claude Code prompt to use (run all three as one instruction):
> "Make three changes to the ICP wizard Step 6 and the campaign routes. First: update lead_finder.py and lead_enricher.py so that only hard gates exclude leads (employee count <5, solo operators, red flag verticals, Hunter confidence <70% with no verified email) — all other wizard selections affect score only, never filter out leads. Second: add a lead limit numeric input to Step 6 (default 10, max = remaining Apollo credits from api_usage table, show credits remaining as helper text) that appears when Find Leads Only or Do Both is selected. Third: replace the single Generate Strategy & Sequence button with three action buttons — Find Leads Only, Generate Strategy & Sequence Only, and Do Both — each with a one-line description and cost note, each triggering a separate backend route that works fully independently."

### Pending setup (not blocking code work)
- Buy outreach domain (~€10) — needed before any emails can send
- Set up Cloudflare DNS (SPF, DKIM, DMARC, MX, Vercel CNAME)
- Sign up for Instantly free trial (warmup)
- Share Google Sheet with service account email from credentials.json
- Run `python scripts/dns_checker.py --domain yourdomain.com`

### Open decisions
- Final brand/domain name (ProspectCore GbR dissolution in progress — partners consulted, awaiting one response)
- Einstiegsgeld meeting in ~10 days — do NOT register Gewerbe before then

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
