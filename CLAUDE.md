# Volley — Build Guide

Step-by-step from zero to first campaign. Written for someone comfortable in the terminal but not a full-time developer.

---

## ✅ WHERE YOU ARE NOW

**Date of last update:** Current session

The core application is built and running. Here is the exact status:

| Component | Status | Notes |
|---|---|---|
| GitHub repo | ✅ Done | `github.com/nomadiclives/volley-outreach-agent` (private) |
| Codespaces environment | ✅ Done | Python venv, dependencies installed |
| Flask dashboard | ✅ Done | Runs at localhost:5000 |
| Database schema | ✅ Done | Including all scoring columns |
| ICP wizard (6 steps) | ✅ Done | Working in dashboard |
| Lead scoring (100pt framework) | ✅ Done | Sub-scores stored in DB |
| 4-email sequence generation | ✅ Done | SPIN-informed, spam filter applied |
| Reply handler | ✅ Done | Human reply = sequence stops immediately |
| Scheduler | ✅ Done | Resumes from SQLite on restart |
| Apollo, Hunter, Lusha, Snov, GetProspect integrations | ✅ Built | Apollo API not available on free tier — see note below |
| Two-phase lead finder + pre-search dedup | ✅ Done | |
| Credit manager (centralised gate) | ✅ Done | |
| Buying signal checker | ✅ Done | |
| Facebook Ad Library | ✅ Done | |
| LinkedIn wired as Phase 2 fallback | ✅ Done | |
| Manual credit override + dashboard credit widget | ✅ Done | |
| Phase 5 fixes (all 7) | ✅ Done | |
| JSON parsing + Apollo auth + button loading state | ✅ Done | |
| **Vertical directory scrapers** | **⏳ Not built** | **Phase 7.5 — build next** |
| API cost tracking + spend limit | ✅ Done | $4 soft cap, $5 Anthropic hard cap |
| Three action buttons on wizard (Find Only / Strategy Only / Do Both) | ✅ Done | |
| DB migration script | ✅ Done | Already run |
| .gitignore protecting secrets | ✅ Done | config.yaml, credentials.json safe |

**⚠️ Apollo API note:** Apollo free tier does NOT include API access — returns 403. Apollo is kept in the codebase as a paid upgrade path (~$49/month for Basic). Do not attempt to use Apollo API on free tier. All lead finding currently runs through Snov.io (primary), Lusha, GetProspect, Hunter, Google Maps, and Facebook Ad Library.

**🎯 Current execution point: Phase 7.5 — Vertical Directory Scrapers**

| Gap | Impact | Priority |
|---|---|---|
| Buying signals never populated | 35/100 score points always = 0 | 🔴 Fix first |
| Google Sheets sync duplicates rows | Don't run `python main.py sync` until fixed | 🔴 Fix first |
| Hunter confidence not structured field | Some good leads auto-rejected wrongly | 🟡 Fix soon |
| Spam filter warns but doesn't block | Spam-trigger emails still get sent | 🟡 Fix soon |
| Apollo CLI credit gate missing | CLI bypasses credit check | 🟡 Fix soon |
| Hunter monthly limit not enforced | Could over-use credits silently | 🟡 Fix soon |
| Weekend cadence drift | Day 10 can land on a Sunday silently | 🟡 Fix soon |
| LinkedIn dead code | Not called in waterfall | 🟢 Nice to have |
| AI reply classifier not connected | Falls back to rule-based only | 🟢 Nice to have |
| Funnel chart not built | Analytics page incomplete | 🟢 Nice to have |

**What's pending setup (outside codebase):**

| Item | Status | Blocks |
|---|---|---|
| Outreach domain | ⏳ Not bought yet | All email sending |
| Cloudflare DNS setup | ⏳ Waiting on domain | All email sending |
| Instantly free trial | ⏳ Not signed up | Warmup |
| Lusha free tier | ⏳ Not signed up | Extended credit bank |
| Snov.io free tier | ⏳ Not signed up | Extended credit bank |
| GetProspect free tier | ⏳ Not signed up | Extended credit bank |
| Google Sheets credentials shared | ⏳ Not done | Sheets CRM sync |

---

## 🎯 WHERE TO START EXECUTING FROM

**You are here → Phase 5: Fix Known Gaps**

Phases 1–4 are complete. Skip straight to Phase 5 below.

---

## Phase 1 — Get Your Accounts ✅ DONE

Core accounts already created. Still needed for expanded credit bank:

### 1.1 Apollo.io ✅
- Free tier: **75 credits/month**, 1 credit = 1 contact with email
- Key already in config.yaml

### 1.2 Hunter.io ✅
- Free tier: **50 searches/month**
- Key already in config.yaml

### 1.3 Anthropic ✅
- Spend limit set at $5/month
- Key already in config.yaml

### 1.4 Google Cloud ✅
- Sheets + Drive API enabled
- credentials.json downloaded

### 1.5 Gmail App Password ✅
- In config.yaml

### 1.6 Warmup Tool ⏳ PENDING
**Option A — Instantly free trial (recommended):**
- [instantly.ai](https://instantly.ai) → Start free trial (14 days, no credit card)
- After trial ends: set `warmup_active: false` in config → auto-switches to Gmail SMTP

**Option B — Lemwarm free tier (ongoing, free):**
- [lemwarm.com](https://lemwarm.com) → Free plan → 1 inbox

### 1.7 Extended Credit Bank ⏳ PENDING (sign up now, get API keys ready)

Sign up for all three free tiers — takes 15 minutes total:

| Tool | URL | Free Credits | Strength |
|---|---|---|---|
| Lusha | [lusha.com](https://lusha.com) | 40/month | Best for European/DACH contacts |
| Snov.io | [snov.io](https://snov.io) | 50/month | Email finder, Apollo complement |
| GetProspect | [getprospect.com](https://getprospect.com) | 50/month | LinkedIn-based contacts |

Once you have API keys, add them to config.yaml:
```yaml
lusha:
  api_key: "YOUR_KEY"
  monthly_credit_limit: 40

snov:
  user_id: "YOUR_API_USER_ID"
  api_secret: "YOUR_API_SECRET"
  monthly_credit_limit: 50

getprospect:
  api_key: "YOUR_KEY"
  monthly_credit_limit: 50
```

**Combined credit bank once all signed up: ~265 verified contacts/month at zero cost**

---

## Phase 2 — Buy Your Domain ⏳ PENDING

**Do this as soon as brand name is confirmed.** The warmup clock starts here — every day you delay is a day you can't send real emails.

- Where to buy: Namecheap or Porkbun (~€8–10/year for .com)
- Buy a domain separate from any personal domain
- Brand decision still open (ProspectCore GbR dissolution in progress)

---

## Phase 3 — Domain & DNS Setup ⏳ PENDING (waiting on Phase 2)

~30 minutes once you have the domain. Do all of this in one sitting.

### 3.1 — Add Domain to Cloudflare (Free)
1. [cloudflare.com](https://cloudflare.com) → Sign up free → Add a site → enter your domain
2. Copy the two nameservers Cloudflare gives you
3. At Namecheap/Porkbun → Nameservers → replace with Cloudflare's two
4. Wait 5–30 minutes for propagation

### 3.2 — Connect Website (Vercel → Your Domain)
In Cloudflare DNS:
```
Type: CNAME    Name: @      Content: cname.vercel-dns.com
Type: CNAME    Name: www    Content: cname.vercel-dns.com
```
In Vercel: Project Settings → Domains → add your domain.

### 3.3 — Email Receiving (Cloudflare Email Routing — Free)
1. Cloudflare → Email → Email Routing → Enable
2. Add rule: `outreach@yourdomain.com` → your personal Gmail
3. MX records added automatically

### 3.4 — SPF + DMARC
```
Type: TXT    Name: @       Content: v=spf1 include:_spf.google.com ~all
Type: TXT    Name: _dmarc  Content: v=DMARC1; p=none; rua=mailto:dmarc@yourdomain.com
```

### 3.5 — Add Sending Address to Gmail
1. Gmail → Settings → Accounts and Import → Send mail as → Add another email
2. `outreach@yourdomain.com`, SMTP: `smtp.gmail.com`, Port `587`, App Password from Phase 1
3. Click verification link Gmail sends

### 3.6 — DKIM
Cloudflare Email Routing → Settings → DKIM → Enable. Cloudflare adds DNS record automatically.

### 3.7 — Verify Everything
```bash
python scripts/dns_checker.py --domain yourdomain.com
```
All green = ready. Any red = it prints the exact fix.

### 3.8 — Google Postmaster Tools
1. [postmaster.google.com](https://postmaster.google.com) → Add domain → verify
2. Check every few days during warmup — shows domain reputation + spam rate

---

## Phase 4 — Initial Build ✅ DONE

Repo created, Codespaces running, Claude Code built the application, dashboard loads. Nothing to do here.

---

## Phase 5 — Fix Known Gaps 🎯 START HERE

Open Codespaces, activate environment, open Claude Code:

```bash
source venv/bin/activate
python main.py   # confirm dashboard still loads at localhost:5000
claude           # open Claude Code
```

Run these prompts in order. Wait for each to complete and test before moving to the next.

---

### Fix 1 — Buying Signals (🔴 Most Important)

> "Build agents/buying_signal_checker.py with two detection methods. Method 1 (homepage pixel scan — run on all leads): fetch the company homepage HTML and check for presence of: Meta Pixel (connect.facebook.net/en_US/fbevents.js), Google Ads tag (googleadservices.com or gtag config with AW- prefix), Google Tag Manager (googletagmanager.com/gtm.js), TrustedForm (trustedform.com), Jornaya (leadid.com). Method 2 (Facebook Page Transparency — run only on leads scoring above 40 on other criteria): use Playwright to fetch https://www.facebook.com/{company_slug}/about_profile_transparency and check for the text 'This page is currently running ads'. Store all results as a structured dict in the buying_signals JSON field on the lead: {running_ads: bool, meta_pixel: bool, google_ads: bool, gtm: bool, tcpa_signals: bool, fb_ads_confirmed: bool, multi_location: bool}. Connect this to _score_ad_spend() and _score_multi_location() in lead_enricher.py so these score criteria actually populate instead of returning 0. Call buying_signal_checker after Phase 2 contact resolution in lead_finder.py."

**Test:** Run a dry-run search, check that buying_signals field is populated on leads and ad_spend sub-score is no longer always 0.

---

### Fix 2 — Google Sheets Sync Deduplication (🔴 Must Fix Before Using Sync)

> "Fix integrations/google_sheets.py so that sync_lead() updates existing rows rather than appending new ones. Use email address as the unique key — if a row with that email already exists in the Leads sheet, update it in place. Only insert a new row if the email doesn't exist. Also fix the main sync command so that running python main.py sync multiple times is safe and idempotent — it must never create duplicate rows."

**Test:** Add a test lead, run sync twice, confirm only one row in the sheet.

---

### Fix 3 — Hunter Confidence as Structured Field (🟡)

> "In integrations/hunter.py, extract the confidence score as a structured integer field hunter_confidence (0-100) on the lead dict returned by domain_search() and email_finder(). It is currently buried in a notes string as 'Hunter confidence: 82%' — parse it out and store it as a proper field. Update the hard gate check in lead_enricher.py to read lead.get('hunter_confidence', 100) correctly — default to 100 (pass) for Apollo/Maps leads that were never processed by Hunter, so they are not incorrectly auto-rejected."

---

### Fix 4 — Spam Filter Blocks Instead of Warns (🟡)

> "In agents/copywriter.py, update the spam filter so that if _check_spam() finds trigger words in a generated email, it rejects the draft and asks Claude to regenerate — up to 3 attempts. If after 3 attempts the email still contains spam triggers, save it with a 'spam_warning' flag set to True and surface a warning notification in the dashboard rather than silently saving and using it. Never save and use an email that failed spam checks without the operator seeing a warning."

---

### Fix 5 — Apollo + Hunter CLI Credit Gates (🟡)

> "Move the Apollo credit check into ApolloClient.search_people() directly in integrations/apollo.py — not just in the web routes. Before every API call, query the api_usage table for Apollo credits used this calendar month and raise a clear exception if the limit of 75 has been reached. Do the same for HunterClient in integrations/hunter.py — check monthly usage against the limit of 50 before every API call. This ensures the credit gates work whether Volley is called from the dashboard or the CLI."

---

### Fix 6 — Weekend Cadence Drift (🟡)

> "In core/scheduler.py, when schedule_sequence_for_lead() calculates the send date for each step by adding delay_days to the base timestamp, advance the resulting date forward to the next Monday if it falls on a Saturday or Sunday. Log the adjustment as 'Cadence adjusted: step N moved from [weekend date] to [Monday date] to avoid weekend send'. This ensures the Day 4 / Day 10 / Day 18 cadence never silently drifts due to weekend days."

---

### Fix 7 — Commit All Fixes

```bash
git add .
git commit -m "Fix buying signals, Sheets dedup, Hunter confidence, spam filter, credit gates, weekend drift"
git push
```

---

## Phase 6 — Two-Phase Lead Architecture + New Integrations ✅ DONE

Build after Phase 5 fixes are stable and tested.

### 6.1 — Two-Phase Lead Finder Rebuild

> "Rebuild agents/lead_finder.py with a two-phase architecture. Phase 1 (Company Discovery): find companies matching the ICP using Apollo, Google Maps, and Facebook Ad Library as sources — output is a list of companies (name + domain), no contact person yet. Phase 2 (Contact & Email Resolution): for each company found in Phase 1, find the right contact and email by trying sources in order — Apollo (if it already has the contact, no extra credit), Lusha, Snov.io, GetProspect, Hunter, LinkedIn scraper — stop as soon as a verified email is found. Implement pre-search deduplication at three levels before spending any credits: Level 1 — check if email already exists in leads table; Level 2 — check if company+first_name+last_name combination exists; Level 3 — check if domain already exists in leads table. Build core/credit_manager.py with a reusable check_and_spend(provider, cost=1) method that: checks remaining credits for the named provider against its monthly limit in config, raises a clear CreditLimitReached exception if the limit is hit, logs the spend to api_usage on success. Every integration — Apollo, Hunter, Lusha, Snov, GetProspect — must call credit_manager.check_and_spend() before every API call. This is the single credit gate for all sources. Add a manual override panel to the wizard Step 6 where the operator can see live credit balances per source and optionally override the automatic allocation."

### 6.2 — Lusha Integration

> "Build integrations/lusha.py — a Lusha API client with search_people(name, company, domain) method. Before every API call, use core/credit_manager.check_and_spend('lusha') to enforce the 40 credit/month hard stop from config. Log every call to api_usage with provider='lusha'. Return standardised lead dict with a structured confidence field (0-100). Wire into Phase 2 contact resolution in lead_finder.py as the second source tried after Apollo."

### 6.3 — Snov.io Integration

> "Build integrations/snov.py — a Snov.io API client using user_id and api_secret from config to generate an OAuth2 access token before each request. Implement find_email(first_name, last_name, domain) and domain_search(domain) methods. Before every API call, use core/credit_manager.check_and_spend('snov') to enforce the 50 credit/month hard stop. Log to api_usage with provider='snov'. Return standardised lead dict. Wire into Phase 2 as third source after Lusha."

### 6.4 — GetProspect Integration

> "Build integrations/getprospect.py — a GetProspect API client. Implement search_by_linkedin(linkedin_url) and search_people(name, company) methods. Before every API call, use core/credit_manager.check_and_spend('getprospect') to enforce the 50 credit/month hard stop. Log to api_usage with provider='getprospect'. Return standardised lead dict. Wire into Phase 2 as fourth source after Snov.io."

### 6.5 — Commit

```bash
git add .
git commit -m "Two-phase lead architecture, Lusha + Snov + GetProspect integrations"
git push
```

---

## Phase 7 — Complete Lead Intelligence Layer ✅ DONE

All Phase 7 items are complete:
- ✅ Facebook Ad Library integration (integrations/facebook_ads.py)
- ✅ LinkedIn wired as Phase 2 final fallback
- ✅ Manual credit override on Step 6
- ✅ Dashboard credit bank widget

---

## Phase 7.5 — Scrapers + Language Support + Campaign Management 🎯 NEXT

Three changes to build in this phase. Run them in order.

---

### 7.5a — Language Selection in Wizard

**What's missing:** Campaigns targeting Germany generate emails in English. There's no way to specify language.

**What to build:** Language dropdown on Step 2 of the ICP wizard. Auto-detects from country but is overridable. All generated content — strategy, all 4 emails, unsubscribe footer — written entirely in the selected language.

**Claude Code prompt:**
> "Add a language dropdown to Step 2 of the ICP wizard with options: English, German, French, Dutch, Spanish, Italian, Portuguese, Other. Auto-detect the default from country selection (Germany/Austria/Switzerland → German, UK/AU/US → English, Netherlands → Dutch, France → French, Spain → Spanish, Italy → Italian, Portugal/Brazil → Portuguese) but allow manual override. Add a language column to the campaigns table in core/database.py. Pass the selected language to agents/strategy_generator.py and agents/copywriter.py — all generated strategy text and all 4 emails must be written entirely in the selected language. The unsubscribe footer must also be translated: German = 'Nicht relevant? Antworten Sie mit Abmelden und ich entferne Sie sofort.', French = 'Pas pertinent? Répondez Désabonner et je vous retire immédiatement.' etc."

**Test:** Create a new campaign, select Germany, confirm language auto-sets to German. Generate a sequence and verify all 4 emails are in German.

---

### 7.5b — Campaign Delete / Archive

**What's missing:** Test campaigns and failed attempts pile up in the Campaigns view with no way to remove them.

**What to build:** Delete button per campaign row. Hard-delete for drafts, soft-archive for active/completed.

**Claude Code prompt:**
> "Add campaign deletion and archiving to the Campaigns table in web/templates/campaigns.html and web/routes/campaigns.py. Each campaign row should have a Delete button alongside the existing View/Review buttons. Draft and pending_approval campaigns: show a confirmation dialog then hard-delete the campaign and all associated sequences and outreach_log records. Active, paused, and completed campaigns: soft-archive only — set status to 'archived', never hard-delete (preserves outreach history). Add a 'Show archived' toggle button above the campaigns table — default view hides archived campaigns, toggle reveals them with a visual indicator (greyed out rows). All delete/archive actions require a confirmation dialog with campaign name shown."

**Test:** Create a draft campaign, delete it, confirm it disappears. Create another, archive it, confirm the toggle shows/hides it.

---

### 7.5c — Vertical Directory Scrapers

This is the highest-leverage free addition to replace Apollo volume. Adds unlimited, pre-qualified company discovery for your core verticals.

**Estimated company pool:**

| Directory | Vertical | Geo | Est. Companies |
|---|---|---|---|
| BSW-Solar | Solar | Germany | ~300 |
| Solar Energy UK | Solar | UK | ~150 |
| FMB | Home improvement | UK | ~8,000 |
| NACFB | Business loans | UK | ~2,000 |
| BdB | Finance | Germany | ~200 |
| **Total** | | | **~10,650** |

**Claude Code prompt:**
> "Create a new directory `scrapers/` in the project. Build a base class `scrapers/base_scraper.py` with shared Playwright setup, rate limiting (2-5 second delays), retry logic, and a standard output format: list of dicts with company_name, domain, country, vertical, source_url. Then build the following vertical scrapers, each as a separate file:
>
> 1. `scrapers/solar_de.py` — scrape BSW-Solar member directory at https://www.solarwirtschaft.de/verbraucher/mitglieder/ — extract company names and websites
> 2. `scrapers/solar_uk.py` — scrape Solar Energy UK member directory at https://solarenergyuk.org/membership/our-members/ — extract company names and websites
> 3. `scrapers/home_improvement_uk.py` — scrape FMB (Federation of Master Builders) directory at https://www.fmb.org.uk/find-a-builder/ — search by trade category, extract company names and websites
> 4. `scrapers/finance_uk.py` — scrape NACFB member directory at https://www.nacfb.org/find-a-broker/ — extract broker company names and websites
> 5. `scrapers/finance_de.py` — scrape BdB member directory at https://bankenverband.de/mitglieder/ — extract company names and websites
>
> Wire all scrapers into `agents/lead_finder.py` Phase 1 company discovery as a new source type 'directory_scraper'. Run scrapers at campaign start if the vertical matches. Store discovered companies in the `directory_companies` SQLite table to avoid re-scraping same directory within 7 days. Add CLI command `python main.py scrape --vertical solar --geo de` to run scrapers manually. Each scraper must handle: pagination, missing data gracefully, bot detection (randomise user agent, delays), and log results to the standard logger."

**Test:**
```bash
python main.py scrape --vertical solar --geo de --dry-run
sqlite3 volley.db "SELECT COUNT(*), vertical, country FROM directory_companies GROUP BY vertical, country;"
```

### Commit

```bash
git add .
git commit -m "Phase 7.5 — language selection, campaign delete/archive, directory scrapers"
git push
```

---

This is the highest-leverage remaining code task. Adds unlimited, free, pre-qualified company discovery for your core verticals — directly replacing Apollo's volume.

**Why this matters:**
Without Apollo API access, Phase 1 company discovery relies on Google Maps and Facebook Ad Library. These are good but not targeted to your specific ICP. Industry trade association directories contain exactly the kind of national/regional operators you want — solar installers, home improvement companies, finance brokers — all pre-qualified as industry members.

**Estimated company pool once built:**

| Directory | Vertical | Geo | Est. Companies |
|---|---|---|---|
| BSW-Solar | Solar | Germany | ~300 |
| Solar Energy UK | Solar | UK | ~150 |
| FMB | Home improvement | UK | ~8,000 |
| NACFB | Business loans | UK | ~2,000 |
| BdB | Finance | Germany | ~200 |
| **Total** | | | **~10,650** |

### Claude Code Prompt

Open Claude Code and paste this:

> "Create a new directory `scrapers/` in the project. Build a base class `scrapers/base_scraper.py` with shared Playwright setup, rate limiting (2-5 second delays), retry logic, and a standard output format: list of dicts with company_name, domain, country, vertical, source_url. Then build the following vertical scrapers, each as a separate file:
>
> 1. `scrapers/solar_de.py` — scrape BSW-Solar member directory at https://www.solarwirtschaft.de/verbraucher/mitglieder/ — extract company names and websites
> 2. `scrapers/solar_uk.py` — scrape Solar Energy UK member directory at https://solarenergyuk.org/membership/our-members/ — extract company names and websites
> 3. `scrapers/home_improvement_uk.py` — scrape FMB (Federation of Master Builders) directory at https://www.fmb.org.uk/find-a-builder/ — search by trade category, extract company names and websites
> 4. `scrapers/finance_uk.py` — scrape NACFB member directory at https://www.nacfb.org/find-a-broker/ — extract broker company names and websites
> 5. `scrapers/finance_de.py` — scrape BdB member directory at https://bankenverband.de/mitglieder/ — extract company names and websites
>
> Wire all scrapers into `agents/lead_finder.py` Phase 1 company discovery as a new source type 'directory_scraper'. Run scrapers at campaign start if the vertical matches — solar campaigns use solar scrapers, finance campaigns use finance scrapers. Store discovered companies in the `directory_companies` SQLite table (columns: id, company_name, domain, country, vertical, source_url, source_file, scraped_at, processed) to avoid re-scraping same directory within 7 days. Add CLI command `python main.py scrape --vertical solar --geo de` to run scrapers manually. Each scraper must handle: pagination, missing data gracefully, bot detection (randomise user agent, delays), and log results to the standard logger."

### Testing After Build

```bash
# Test one scraper manually first
python main.py scrape --vertical solar --geo de --dry-run

# If dry-run looks good, run for real
python main.py scrape --vertical solar --geo de

# Check what was stored
sqlite3 volley.db "SELECT COUNT(*), vertical, country FROM directory_companies GROUP BY vertical, country;"
```

### Commit

```bash
git add .
git commit -m "Phase 7.5 — vertical directory scrapers for solar, home improvement, finance"
git push
```

---

Build these after Phase 6 is stable. They complete the buying signal detection and dashboard visibility.

### 7.1 — Facebook Ad Library Integration

> "Build integrations/facebook_ads.py with two methods. Method 1 (Ad Library search): use Playwright to search Facebook Ad Library (https://www.facebook.com/ads/library) by keyword/vertical and extract company names and domains of active advertisers — this feeds Phase 1 company discovery as a source of companies that are confirmed ad spenders. Method 2 (Page Transparency check): given a company's Facebook page slug, fetch https://www.facebook.com/{slug}/about_profile_transparency and check for 'This page is currently running ads' — store result in buying_signals['fb_ads_confirmed']. Wire Method 1 into Phase 1 discovery in lead_finder.py as a third source alongside Apollo and Google Maps. Wire Method 2 into buying_signal_checker.py to be called on leads scoring above 40 on other criteria."

### 7.2 — LinkedIn Properly Wired

> "Connect integrations/linkedin_scraper.py as the final fallback in Phase 2 contact resolution in lead_finder.py — after GetProspect, before giving up. For each company that reaches LinkedIn fallback: use Playwright to search LinkedIn for the company name + target title, extract contact name and title from public search results (no login required), then pass the domain to Hunter to find the email. Respect rate limits: 2–5 second delays between requests, max 20 LinkedIn lookups per run."

### 7.3 — Manual Credit Override on Step 6

> "Add a collapsible credit budget panel to wizard Step 6, shown below the lead limit input. It should display live credit balances for all sources (Apollo, Hunter, Lusha, Snov, GetProspect) with their monthly limits and remaining credits. By default the panel shows 'Automatic allocation' — credit_manager handles the split. If the operator expands the panel they can override the per-source budget for this specific run using numeric inputs. Store the override values and pass them to find_leads() so credit_manager respects them."

### 7.4 — Dashboard Credit Bank Widget

> "Add a credit bank status widget to the dashboard home page (web/routes/dashboard.py and dashboard.html). Show all sources in a compact table: Source | Used This Month | Remaining | Resets In (days until 1st of next month). Colour-code remaining: green (>50% left), yellow (20–50% left), red (<20% left). Query api_usage table grouped by provider for current calendar month. This widget should be visible without scrolling on the dashboard — put it in the top stat cards row or immediately below it."

### 7.5 — Commit

```bash
git add .
git commit -m "Facebook Ad Library, LinkedIn wired, credit override, dashboard credit widget"
git push
```

---

## Phase 8 — Polish & Analytics (after first real campaigns)

Build these when the core is fully working and you have real campaign data to look at.

### 8.1 — Funnel Chart in Analytics

> "Build a funnel visualisation in web/routes/analytics.py and analytics.html using Chart.js. The funnel shows: Found → Approved → Contacted → Opened → Replied → Interested. Assemble the funnel data in the analytics route by querying: leads table for Found/Approved counts, outreach_log for Contacted/Opened counts, outreach_log where reply_is_human=1 for Replied, outreach_log where reply_classification='interested' for Interested. Show both absolute numbers and conversion rates between each stage."

### 8.2 — Top Subject Lines by Open Rate

> "In web/routes/analytics.py, add a query that joins outreach_log to sequences, groups by subject line, and ranks by open rate (opened_at is not null / total sent). Display the top 5 subject lines per campaign and in aggregate in analytics.html. Minimum 10 sends before a subject line appears in rankings to avoid statistical noise."

### 8.3 — Per-Lead Score Breakdown in Detail Modal

> "Verify that lead_detail.html renders all individual sub-scores visually, not just the total ICP score. Each sub-score (score_title, score_company_size, score_multi_location, score_ad_spend, score_ltv_vertical, score_marketing_roles, score_data_completeness) should show as a labelled bar or number with its max value (e.g. 'Ad spend signal: 15/20'). Also display score_rationale as a text explanation. Display buying_signals as a list of detected signals with checkmarks."

### 8.4 — AI Reply Classifier Connected

> "In core/reply_handler.py, update handle_reply() so that for replies classified as 'human_unknown' by the rule-based classifier, it calls agents/reply_analyzer.py classify_reply_with_ai() to get a more precise classification. The rule-based classifier handles clear cases (OOO, bounce, unsubscribe) — AI handles ambiguous ones. Log which classifier was used for each reply to outreach_log."

### 8.5 — Warmup Auto-Switch Logic

> "In core/scheduler.py, increment warmup_days_elapsed in config.yaml by 1 each day the scheduler runs. Use this value to automatically enforce the warmup schedule: days 1-14 cap at warmup_daily_limit (10), days 15-21 cap at 20, days 22-28 cap at 30, day 29+ use daily_send_limit from config. When warmup_active is set to false in config, switch email routing to Gmail SMTP automatically and log 'Warmup complete — switched to Gmail SMTP'. Show current warmup day and schedule on the dashboard warmup status card."

### 8.6 — Commit

```bash
git add .
git commit -m "Funnel chart, subject line analytics, score breakdown, AI reply classifier, warmup auto-switch"
git push
```

---

## Phase 9 — Start Warmup ⏳ (waiting on domain)

Once domain is bought and DNS is verified green:

1. Connect `outreach@yourdomain.com` to Instantly (or Lemwarm)
2. Add to warmup campaign
3. Check Google Postmaster Tools the next day

**Warmup schedule:**

| Period | Daily Limit | Config Setting |
|---|---|---|
| Week 1–2 | 10–20/day | `warmup_daily_limit: 10` |
| Week 3 | 30/day | `daily_send_limit: 20` |
| Week 4 | 40/day | `daily_send_limit: 30` |
| Month 2+ | 50–80/day | `warmup_active: false` |

When Instantly trial ends: set `warmup_active: false` in config.yaml — Volley switches to Gmail SMTP automatically.

---

## Phase 10 — First Real Campaign

Once Phase 5 fixes are done and warmup is running (Week 3):

### Step 1 — Start Volley
```bash
source venv/bin/activate
python main.py
# Open localhost:5000
```

### Step 2 — Create Campaign via Wizard
- Go through all 6 steps
- Select "Strategy & Sequence Only" first (free, no Apollo credits) — review the generated emails
- If happy with the copy, come back and run "Find Leads Only" with limit set to 10

### Step 3 — Review Leads
- Green (70+): approve
- Yellow (40–69): review individually
- Red (<40): reject
- **DO NOT run `python main.py sync` until the Sheets dedup fix (Phase 5, Fix 2) is applied**

### Step 4 — Approve Campaign
Campaigns → click campaign → Review & Approve:
1. Read all 4 emails carefully
2. Click "Send Test to Myself" — check inbox placement
3. Click Approve

### Step 5 — Monitor
Check dashboard daily:
- Human replies → handle personally within 24 hours
- Bounce rate > 5% → pause campaign immediately
- Spam rate in Postmaster > 0.1% → stop everything, fix DNS

---

## Monitoring — Key Numbers

| Metric | Healthy | Warning | Stop & Fix |
|---|---|---|---|
| Open rate | >30% | 20–30% | <20% |
| Reply rate | >4% | 2–4% | <2% |
| Bounce rate | <2% | 2–5% | >5% |
| Spam rate | <0.05% | 0.05–0.1% | >0.1% |

Spam rate is only visible in Google Postmaster Tools — not in Volley's dashboard.

---

## Common Issues

**Emails landing in spam**
`python scripts/dns_checker.py --domain yourdomain.com` — 9/10 times it's SPF/DMARC misconfiguration.

**Apollo returning 0 results**
Too narrow. Broaden employee range, add countries, add title variations. Use dry-run to see what's being sent.

**Gmail SMTP authentication failed**
App Password was not used — go to Google Account → Security → App Passwords → generate new one.

**Bounce rate spiking**
Pause campaign from dashboard immediately. Bad emails in the list — Hunter confidence was below threshold.

**"Instantly trial expired"**
Expected after 14 days. Set `warmup_active: false` in config.yaml — auto-switches to Gmail SMTP.

**Human reply still getting follow-ups**
Check logs — reply should be classified within 15 minutes. If not, check reply_handler.py is running (scheduler must be active).

**Google Sheets showing duplicate rows**
Do not run sync again. Apply Phase 5 Fix 2 first, then manually delete duplicates in the Sheet.

---

## Quick Reference

```bash
# Start Volley (dashboard + scheduler)
source venv/bin/activate
python main.py

# Find leads (use dashboard instead — CLI bypasses credit gate until Fix 5 applied)
python main.py find --icp "description" --limit 10 --dry-run

# Sync Sheets (DO NOT run until Fix 2 applied)
python main.py sync

# Campaign management
python main.py pause --campaign 1
python main.py resume --campaign 1
python main.py export --campaign 1

# DNS check
python scripts/dns_checker.py --domain yourdomain.com

# DB migration (already run — do not run again)
python scripts/migrate_lead_scores.py --dry-run
```

Dashboard always at: **localhost:5000**

---

## Credit Bank Reference

| Source | Free Limit | Strength |
|---|---|---|
| Apollo | **75/month** | B2B contacts with titles + emails |
| Hunter | **50/month** | Domain-based email resolution |
| Lusha | 40/month | European/DACH contacts ⏳ pending signup |
| Snov.io | 50/month | Email finder ⏳ pending signup |
| GetProspect | 50/month | LinkedIn-based contacts ⏳ pending signup |
| Google Maps | Unlimited | Local/SMB company discovery |
| Facebook Ad Library | Unlimited | Active advertiser discovery |
| **Total once all active** | **~265 verified contacts/month** | |