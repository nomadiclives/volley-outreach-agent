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
│   ├── solar_de.py            # BSW-Solar member directory (Germany) — BROKEN: login wall
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

**ICP targeting note:** Primary targets are mid-to-large operators with national/regional scale, dedicated sales teams, and existing lead buying infrastructure (e.g. Enpal, Power HRG equivalents). NOT micro-SMBs or solo tradesmen. Verticals: solar, home improvement (roofing/HVAC/windows/siding), business loans/finance.

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

Vertical-specific Playwright scrapers that extract member company names and domains from industry trade association directories.

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
- vertical="solar" + geo="de" → `solar_de.py`
- vertical="solar" + geo="uk" → `solar_uk.py`
- vertical="home improvement" + geo="uk" → `home_improvement_uk.py`
- vertical="finance/loans" + geo="uk" → `finance_uk.py`
- vertical="finance/loans" + geo="de" → `finance_de.py`
- Unknown vertical → skip scrapers, fall through to Google Maps

**CLI:** `python main.py scrape --vertical solar --geo de [--dry-run]`

**`directory_companies` table:** id, company_name, domain, country, vertical, source_url, source_file, scraped_at, processed (0/1). See `core/database.py` for full schema.

---

### Pre-Search Deduplication (3 levels)

Before calling ANY source in either phase, check the local DB first:

- **L1 — Email dedup:** If email already exists in leads table, skip — zero credits spent.
- **L2 — Company+contact dedup:** If `company_name + first_name + last_name` already exists, skip all Phase 2 sources.
- **L3 — Domain dedup:** If company domain already exists in leads table, skip that company across all Phase 1 sources.

Estimated credit waste from overlap: <5% (down from 20-30% without pre-search dedup).

### Credit-Aware Budget Allocation

At campaign start, `core/credit_manager.py` calculates available credits per source and allocates conservatively (≤60% of remaining per source per campaign run). The campaign wizard Step 6 shows a credit budget panel where the operator can override per-source allocation. Default is automatic. Dashboard must show live credit bank status at all times.

### Buying Signal Detection

Run for every lead after Phase 2 completes. Two checks:

**Check 1 — Homepage pixel scan (fast, runs on all leads):**
Fetch company homepage HTML. Look for: Meta Pixel, Google Ads tag, Google Tag Manager, TrustedForm, Jornaya.

**Check 2 — Facebook Page Transparency (runs on leads scoring >40):**
Fetch `https://www.facebook.com/{page_slug}/about_profile_transparency` via Playwright.
Look for text: "This page is currently running ads."

Store all results in `buying_signals` JSON field. Feeds into `_score_ad_spend()` (20pts) and `_score_multi_location()` (15pts) in `lead_enricher.py`.

---

## Email Sequence

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

The "New Campaign" form is a **6-step structured wizard**. No free-text ICP description.

**Step 1 — Vertical:** dropdown + free text
**Step 2 — Geography:** country multi-select + optional cities + **language selector**
  - Language dropdown: English, German, French, Dutch, Spanish, Italian, Portuguese, Other
  - Default: auto-detect from country (Germany/Austria/Switzerland → German, UK/US/AU → English, etc.)
  - Language applies to: all 4 emails, subject lines, strategy rationale
**Step 3 — Company Profile:** employee range slider (default 10–200) + multi-location toggle
**Step 4 — Buying Signals:** checkboxes — running ads, lead forms, TCPA language, call centre, dedicated marketing roles, high-LTV vertical, affiliate program
**Step 5 — Target Titles:** pre-populated defaults (editable):
  Marketing Manager, Head of Marketing, VP Marketing, Director of Marketing, Affiliate Manager, Partnerships Manager, Media Buyer, Head of Growth, CMO, CEO (≤50 employees), Founder (≤50 employees)
**Step 6 — Red Flag Exclusions + Summary + Action Selection:**
  - Exclusion checkboxes (overridable): <5 employees, solo operators, ACA/Medicare/car insurance
  - Campaign summary panel showing all wizard selections
  - **Lead limit input** (default 10, max capped at remaining credits)
  - **Three action buttons** — user must pick one:
    - **Find Leads Only** — runs discovery + scoring. No AI copy. No Claude cost.
    - **Generate Strategy & Sequence Only** — generates outreach strategy + 4 emails. No API credits. ~€0.02 Claude cost.
    - **Do Both** — finds leads AND generates strategy + sequence in one go.

### Filter logic — hard gates vs soft scoring

**Hard gates (always exclude):**
- Employee count < 5
- Solo operator
- Red flag verticals (unless unchecked in Step 6)
- Hunter email confidence < 70% with no verified email

**Soft scoring (affects score, never excludes):** buying signals, multi-location, title match quality, high-LTV vertical, data completeness.

A lead that doesn't match soft criteria still appears with a lower score. Operator decides. Hard gates are the only true exclusions.

---

## Lead Buyer Scoring Framework (0–100)

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
- Employee count < 5 / Solo operator
- Vertical is ACA / Medicare / car insurance (unless user explicitly overrides)
- No email found AND Hunter confidence < 70%

Score breakdown must be visible per lead in the dashboard — show WHY a lead scored 72 not just the number.

---

## Database Schema

Full schema in `core/database.py`. Key tables:
- **leads** — all lead data, scoring sub-scores, buying_signals JSON, status, auto_rejected
- **campaigns** — ICP params, vertical, geo, language, strategy_json, status
- **sequences** — 4 emails per campaign: step_number, subject, body_text, delay_days
- **outreach_log** — per-send log: scheduled_at, sent_at, opened_at, replied_at, reply_is_human, status
- **api_usage** — every API + Claude call: provider, model, purpose, tokens, cost_usd
- **notifications** — dashboard alerts
- **directory_companies** — scraper output: company_name, domain, country, vertical, scraped_at, processed

Schema is additive migration on startup — never drops columns.

---

## Web Dashboard Spec

**Layout:** Dark sidebar + white content area. Vanilla CSS only — no frameworks. System font stack.

**Sidebar navigation:** Dashboard / Campaigns / Leads / Sequences / Analytics

**Dashboard (`/`):** Sent today, active campaigns, total leads, warmup status card. Campaign status panel. Notifications panel. Polls `/api/notifications` every 60s.

**Campaigns (`/campaigns`):** Table with status badges. Campaign detail: strategy panel, 4-email sequence cards, lead breakdown, action bar (Approve / Pause / Resume / Edit / Export). Approval flow: strategy review → lead quality summary → full sequence → "Send test to myself" button → Approve / Reject.

**Leads (`/leads`):** Full CRM table. Score shown as number + colour (green ≥70, yellow 40–69, red <40). Click row → detail modal with score breakdown, full outreach history. Filter by campaign / status / score range / country. Bulk approve/reject.

**Sequences (`/sequences`):** View and inline-edit all 4 emails per campaign. Validate button runs spam filter. Editable only for draft/paused campaigns.

**Analytics (`/analytics`):** Funnel chart (Found → Approved → Sent → Opened → Replied → Interested). Daily send time series (Chart.js CDN). Top subject lines by open rate. Deliverability health. API cost breakdown.

---

## Config Key Notes

Full config structure in `config.yaml` (gitignored). Key entries:
- `hunter.monthly_search_limit: 50` — CONFIRMED free tier limit, do not lower
- `apollo.monthly_credit_limit: 75` — PAID UPGRADE ONLY, free tier returns 403
- `claude.model: "claude-haiku-4-5"` + `monthly_cost_limit_usd: 4.00`
- `email.warmup_active: true` — set false after warmup to switch to Gmail SMTP
- `google.maps_api_key: ""` — fill this in to unblock Phase 1 Google Maps source
- `outreach.default_cadence_days: [0, 4, 10, 18]`
- `email.daily_send_limit: 20`, `send_weekdays_only: true`, window 09:00–18:00 Europe/Berlin

**Warmup schedule:** Week 1–2: 10–20/day warmup only; Week 3–4: hybrid; Month 2+: full Gmail SMTP. Set `warmup_active: false` to switch automatically.

---

## Build Status — Last reviewed 2026-06-06

### Column 1 — Built and complete ✅

All core infrastructure, agents, and web dashboard are code-complete:
- `core/`: database (50+ CRUD ops), credit_manager, deduplicator (3-level), email_validator, scheduler (weekday/time-window aware, restarts from SQLite), reply_handler (IMAP poller, OOO/bounce/human classifier, sequence cancellation)
- `agents/`: icp_analyzer, lead_finder (full two-phase orchestrator), lead_enricher (7-criterion scoring), buying_signal_checker (pixel scan + FB Transparency), strategy_generator, copywriter (4-email SPIN, spam filter, multi-language), reply_analyzer, claude_client (cost wrapper)
- `integrations/`: apollo (PAID UPGRADE ONLY), hunter, google_maps, google_sheets, gmail_smtp — code-complete
- `scrapers/`: base_scraper (Playwright lifecycle, 7-day cache, user-agent rotation), scraper registry + ICP routing
- `web/`: Flask factory + 6 blueprints, all 9 Jinja2 templates, full ICP wizard (6 steps), approval flow, delete/archive, CRM table, analytics routes, language selection
- `main.py`, `scripts/`, `tracking/pixel.py`, `scripts/dns_checker.py`

### Column 2 — Built but not yet tested against live systems ⚠️

| Module | Risk |
|---|---|
| `integrations/snov.py` | Medium — OAuth2 token refresh is likely failure point |
| `integrations/instantly.py` | Medium — depends on trial activation |
| `integrations/linkedin_scraper.py` | High — LinkedIn actively blocks scrapers |
| `integrations/facebook_ads.py` | Medium — consent overlay handling brittle |
| `scrapers/solar_de.py` | **Critical — CONFIRMED BROKEN** (login wall, cache polluted with garbage) |
| `scrapers/solar_uk.py`, `home_improvement_uk.py`, `finance_uk.py`, `finance_de.py` | High — login-wall risk unverified |
| `core/reply_handler.py` + `core/scheduler.py` | High — end-to-end only testable once domain + DNS + warmup are live |
| `integrations/people_data_labs.py`, `lusha.py`, `getprospect.py`, `google_maps.py`, `google_sheets.py` | Low — REST APIs, work once keys/credentials are filled in |
| `agents/copywriter.py` (non-English) | Medium — footer translations untested |
| `tracking/pixel.py` | Low — needs live hosted URL |

### Column 3 — Not yet built ❌

| Feature | Notes |
|---|---|
| Funnel chart frontend wiring | Data queries exist; Chart.js wiring not done |
| AI reply classifier upgrade | Rule-based fallback works; ambiguous replies not confidently classified |
| Warmup auto-increment | `warmup_days_elapsed` is manually set |
| Apollo paid activation toggle | Needs `paid_tier: true` config flag |
| Test suite (`tests/`) | Zero test files anywhere in the repo |
| A/B sequence split-test runner | Strategy JSON has ideas; no infrastructure |
| Lead import from CSV | Leads only come from automated discovery |
| Config.yaml validation on startup | Missing keys cause runtime errors |
| **Phase 1 company discovery redesign** | All Phase 1 sources broken/missing keys — do not build until operator decides approach |
| Wizard Step 6 — separate submit CTA + background job + redirect | 504 timeout fix depends on this |
| Dashboard credit bank widget — remove Apollo, reflect real source list | `web/routes/dashboard.py`, `web/templates/dashboard.html` |
| Full Apollo language audit in wizard | Remove all Apollo references from Step 6 UI |

### Real-world blockers (not code)

| Blocker | Unblocks |
|---|---|
| Buy outreach domain (~€10) — **single biggest blocker** | Everything email-related |
| Set up Cloudflare DNS — SPF, DKIM, DMARC, MX, pixel CNAME | Email deliverability, open tracking |
| Sign up for Instantly.ai free trial | Inbox warmup (weeks 1–4) |
| Share Google Sheet with service account email from `credentials.json` | CRM sync |
| Fill in `google.maps_api_key` in config.yaml | Phase 1 Google Maps (quickest win — already coded) |
| Einstiegsgeld meeting — do NOT register Gewerbe before this | Legal/business entity |
| Finalise brand/domain name — ProspectCore GbR dissolution in progress | Domain purchase |

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
python scripts/dns_checker.py --domain x    # Check DNS records
```

---

## Known Issues & Open Backlog — Last reviewed 2026-06-06

### CRITICAL — Phase 1 company discovery is completely broken

Every Phase 1 source is currently non-functional:

| Source | Status | Reason |
|---|---|---|
| BSW-Solar scraper | Broken | Requires login; scraper saves nav links as fake companies. 7-day cache locked in garbage — must purge `directory_companies` table before next run. |
| All other vertical scrapers | Untested | Assumed broken or inaccessible — same login-wall risk |
| Google Maps | Skipped | `maps_api_key` is blank in config.yaml |
| Facebook Ads | Unreliable | Playwright hits consent/bot detection in headless Codespaces |
| Apollo | Disabled | Paid upgrade only — intentional |

**Consequence:** Every campaign run returns zero leads. Phase 2 sources are resolvers, not discoverers — they cannot substitute for Phase 1.

**Immediate quick win:** Fill in `google.maps_api_key` in config.yaml — Google Maps is already coded and working.

**Phase 1 redesign options:** New public solar directory URL / Google Maps as primary / manual company seed list / PDL company search. Do not build until operator decides.

---

### Dashboard — Credit bank widget shows Apollo as primary source

Widget doesn't reflect current Phase 2 source order (Lusha → Snov → PDL → GetProspect → Hunter). **Fix:** `web/routes/dashboard.py` + `web/templates/dashboard.html`.

---

### ICP Wizard Step 6 — Apollo language throughout

Lead Limits panel and action button helper text still reference Apollo credits. **Fix:** Audit all Apollo references in `web/routes/campaigns.py` + `web/templates/campaigns.html`.

---

### ICP Wizard Step 6 — UX: no clear submit CTA, no feedback after submit

Current: action buttons act as both selection AND submit trigger. Screen hangs with no feedback. 504 timeout after ~30s from Codespaces port forwarding proxy.

Required: separate "Let's Go" submit button; on submit, immediately redirect to Campaigns list with banner "Campaign created — work in progress". Move `find_leads()` off the request thread into a background task.

**Fix:** `web/routes/campaigns.py`, `web/templates/campaigns.html`

---

## Quality Standards

- Every function has a docstring
- Every API call has specific, actionable error handling
- Every email logged to SQLite BEFORE sending
- All secrets in config.yaml only — never hardcoded
- `--dry-run` flag available on find and send commands
- Human reply detection tested against: OOO, bounce, interested reply, not interested reply, one-word reply, forwarded email
- Web UI readable without JavaScript for core views (progressive enhancement)
