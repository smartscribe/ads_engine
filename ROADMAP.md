# Ads Engine — Roadmap & Implementation Guide

> **How to use this doc:** This is a step-by-step implementation guide. An agent should be able to pick up any task below and execute it end-to-end. Each task includes: what to do, which files to touch, exact function signatures or endpoints to create, acceptance criteria, and dependencies. Reference the CHANGELOG for what was built previously and METHODOLOGY.md for design rationale.

---

## Architecture Quick Reference

```
engine/
├── orchestrator.py          # Main pipeline controller, CLI entry point
├── models.py                # All Pydantic models (brief, variant, taxonomy, regression, hypothesis)
├── store.py                 # Flat JSON persistence (data/ directory)
├── brand.py                 # JotPsych brand kit (colors, fonts, voice)
├── notifications.py         # Slack notifications (currently stdout-only)
├── intake/
│   ├── parser.py            # Free-text → CreativeBrief via Claude
│   └── concept_expander.py  # Concept → 20 diverse briefs via Claude
├── analysis/
│   └── analyzer.py          # Meta export, Claude taxonomy tagging, playbook generation
├── generation/
│   ├── generator.py         # Copy generation orchestration (templates only, no AI images)
│   ├── copy_agents.py       # HeadlineAgent, BodyCopyAgent, CTAAgent (slot-based)
│   ├── quality_filter.py    # AI-tell + generic phrase detection
│   ├── variant_matrix.py    # Explore/exploit variant selection with regression scoring
│   ├── template_renderer.py # HTML → PNG via Playwright
│   ├── template_selector.py # Taxonomy → template + color scheme mapping
│   ├── scene_library.py     # 27 image + video scene descriptions
│   ├── video_renderer.py    # CSS animation → MP4 (exists, not wired)
│   └── templates/           # HTML/CSS ad templates (9 templates, 4 color schemes)
├── review/
│   ├── reviewer.py          # Approve/reject, chips, structured feedback
│   ├── monologue_parser.py  # Voice/text monologue → per-variant verdicts
│   └── chips.py             # 12 rejection + 5 approval chip taxonomy mappings
├── regression/
│   └── model.py             # WLS regression, holdout, bootstrap, confidence tiers
├── memory/
│   ├── models.py            # Three-layer memory dataclasses
│   ├── builder.py           # Assembles memory from regression + reviews + deployments
│   ├── playbook_translator.py # Coefficients → natural language PlaybookRules
│   └── creative_memory.py   # Legacy CreativeMemoryManager (v1)
├── decisions/
│   └── engine.py            # Scale/kill/wait logic per variant
├── deployment/
│   └── deployer.py          # MetaDeployer (implemented), GoogleDeployer (stubbed)
└── tracking/
    ├── tracker.py            # MetaTracker (implemented), GoogleTracker (stubbed)
    ├── hypothesis_tracker.py # Evaluate hypotheses against regression + A/B data
    └── hypothesis_extractor.py # Claude-powered hypothesis extraction from text

dashboard/
├── api/app.py               # FastAPI backend (30+ endpoints)
└── frontend/pages/
    ├── review.html           # Tinder/gallery review, scoreboard, learnings
    ├── portfolio.html        # Bubble chart of all ad performance
    └── hypotheses.html       # Hypothesis testing interface

config/settings.py            # Pydantic settings loaded from .env
```

---

## Current State Summary

| Subsystem | Status | Notes |
|-----------|--------|-------|
| Analysis (export + tag + playbook) | ✅ Complete | 432 Meta ads exported and tagged |
| Regression (WLS + validation) | ✅ Complete | Holdout, bootstrap CI, stability, confidence tiers |
| Memory (3-layer + decay) | ✅ Complete | Statistical + editorial + market memory |
| Generation — Copy (slot-based agents) | ✅ Complete | HeadlineAgent, BodyCopyAgent, CTAAgent |
| Generation — Templates (HTML → PNG) | ✅ Complete | 9 templates, 4 color schemes |
| Generation — Variant Matrix | ✅ Complete | Explore/exploit, fatigue penalty, diversity caps |
| Concept → 20 Variants | ✅ Complete | ConceptExpander + CLI + API |
| Review (Tinder + gallery + chips) | ✅ Complete | Monologue parser, voice notes, scoreboard |
| Hypothesis Tracking | ✅ Complete | Extractor, tracker, dashboard page |
| Portfolio Visualization | ✅ Complete | Bubble chart, zoom, top performers |
| Meta Deploy (API) | ✅ Implemented | Needs write-access API keys to use |
| Meta Track (API) | ✅ Implemented | Needs deployed ads to pull data for |
| Decision Engine | ✅ Implemented | Needs live performance data |
| Concept SSE Endpoint | ❌ Broken | ImportError: `AdCampaignOrchestrator` doesn't exist |
| Slack Notifications | 🔶 Stdout only | `_send()` prints instead of POSTing to webhook |
| Scheduler | ⬜ Not started | APScheduler for daily cycle |
| Bulk Creative Export | ⬜ Not started | ZIP download of approved variants |
| Performance Dashboard | ⬜ Not started | Per-variant metrics table |
| Regression Insights Dashboard | ⬜ Not started | Coefficient visualization |
| Budget Pacing | ⬜ Not started | Spend tracking vs monthly budget |
| Google Deploy | 🚧 Stubbed | `NotImplementedError` on all methods |
| Google Track | 🚧 Stubbed | `NotImplementedError` |
| Google Conversion Tag Fix | ⬜ Not started | Server-side Measurement Protocol |
| Attribution Deduplication | ⬜ Not started | Meta + Google + survey reconciliation |
| AI Image Generation | ⬜ Removed (Phase 2) | Gemini/DALL-E code stripped in favor of templates |
| Video Generation | 🔶 Exists, not wired | `video_renderer.py` present but not called |

---

## Priority Legend

| Label | Meaning |
|-------|---------|
| **P0** | Bug fixes and broken functionality. Do these first. |
| **P1** | Production readiness — dashboard features, UX, export. Needed before showing to the team. |
| **P2** | Close the feedback loop — deploy, track, daily cycle automation. Needed before spending real money. |
| **P3** | Expand capabilities — Google, budget pacing, attribution. Needed for scale. |
| **P4** | Future capture — AI images, video, LoRA, LinkedIn. Worth noting, not scheduling. |

**Status icons:** ✅ Done · 🔄 In Progress · ⬜ Not Started · ❌ Broken · 🚧 Stubbed

---

## P0 — Bug Fixes (Do First)

---

### P0.1 Fix Concept SSE Endpoint ImportError

**Status:** ❌ Broken
**Priority:** Critical — blocks the concept-to-20-variants workflow from the dashboard

**The bug:** `dashboard/api/app.py` has a `POST /api/intake/concept` endpoint that imports `AdCampaignOrchestrator` from `engine.orchestrator`. That class does not exist — the actual class is `Orchestrator`. The endpoint will crash with `ImportError` whenever called.

**Steps:**

1. Open `dashboard/api/app.py`
2. Find the concept endpoint (search for `AdCampaignOrchestrator`)
3. The import/reference appears inside the SSE streaming function. Change it to `Orchestrator` (which is the actual class name in `engine/orchestrator.py`)
4. Verify the endpoint works by running the server and POSTing to `/api/intake/concept` with a test concept string

**Files:** `dashboard/api/app.py`

**Acceptance criteria:**
- `POST /api/intake/concept` with `{"concept": "famous movie psychiatrists", "num_variants": 4}` returns an SSE stream of generation progress without crashing
- No references to `AdCampaignOrchestrator` anywhere in the codebase

---

### P0.2 Fix CORS for Production

**Status:** ⬜ Not Started
**Priority:** Low for dev, required before any external access

**Current state:** `dashboard/api/app.py` has `allow_origins=["*"]` in the CORS middleware.

**Steps:**

1. Open `dashboard/api/app.py`
2. Find the `CORSMiddleware` setup
3. For now, keep `["*"]` but add a `# TODO: restrict to dashboard origin in production` comment
4. When deploying, change to the actual dashboard origin URL

**Files:** `dashboard/api/app.py`

**Acceptance criteria:** Comment added. No functional change until deployment is configured.

---

## P1 — Production Readiness

> These features make the dashboard presentable for the first team review session with Nate + Jackson. Nothing here requires Meta API write access.

---

### P1.1 Wire Slack Notifications (Replace stdout with real webhook)

**Status:** 🔶 Stdout only
**Priority:** High — team needs notifications for deploys, kills, hypothesis updates

**Current state:** `engine/notifications.py` has a `SlackNotifier` class with full message formatting for 7 event types (variants generated, daily decisions, regression update, deployment, hypothesis updates/created, budget alert). The `_send()` method only prints to stdout. `SLACK_WEBHOOK_URL` exists in `config/settings.py` but is never used.

**Steps:**

1. Open `engine/notifications.py`
2. Find the `_send()` method on the `SlackNotifier` class
3. Replace the print-only implementation with:
   ```python
   def _send(self, channel: str, text: str, blocks: list[dict] | None = None):
       if not self.webhook_url:
           print(f"[SLACK → #{channel}] {text}")
           return
       
       payload = {"channel": channel, "text": text}
       if blocks:
           payload["blocks"] = blocks
       
       import requests
       resp = requests.post(self.webhook_url, json=payload, timeout=10)
       if resp.status_code != 200:
           print(f"[SLACK ERROR] {resp.status_code}: {resp.text}")
   ```
4. In `__init__`, read the webhook URL from settings:
   ```python
   def __init__(self, settings):
       self.webhook_url = getattr(settings, 'SLACK_WEBHOOK_URL', None) or None
       self.channel = getattr(settings, 'SLACK_CHANNEL', '#ads-engine') or '#ads-engine'
   ```
5. Check how `SlackNotifier` is constructed in `engine/orchestrator.py` — make sure settings are passed
6. Verify existing callers still work (all `notify_*` methods should pass through `_send`)

**Files:** `engine/notifications.py`, `engine/orchestrator.py` (if constructor needs updating)

**Env setup needed:** User must set `SLACK_WEBHOOK_URL` in `.env`. Instructions:
- Go to https://api.slack.com/apps → Create App → Incoming Webhooks → Add to channel
- Copy webhook URL → paste into `.env` as `SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...`
- Optionally set `SLACK_CHANNEL=#ads-engine` (defaults to `#ads-engine`)

**Acceptance criteria:**
- When `SLACK_WEBHOOK_URL` is set, notifications POST to Slack and appear in the channel
- When `SLACK_WEBHOOK_URL` is empty/missing, falls back to stdout print (no crash)
- All 7 notification types produce valid Slack messages

---

### P1.2 Performance Dashboard Page

**Status:** ⬜ Not Started
**Priority:** High — team needs to see how deployed ads are performing

**What it should show:**
- Table of all deployed/active variants with columns: thumbnail, headline, spend, impressions, clicks, conversions, CpFN, days running, verdict badge (scale/kill/wait)
- Trend sparklines per variant (spend and CpFN over last 7 days)
- Summary stats: total active ads, total daily spend, average CpFN, best/worst performer
- One-click kill/scale buttons per variant → `POST /api/decisions/act`
- Filter by status (active/paused/killed), date range, CpFN range

**Steps:**

1. **Create the API endpoint** in `dashboard/api/app.py`:
   ```python
   @app.get("/api/performance/dashboard")
   async def performance_dashboard():
   ```
   This should:
   - Load all variants with `status in ["deployed", "active", "graduated"]`
   - For each, load all `PerformanceSnapshot` records from `data/performance/snapshots/`
   - Compute aggregate metrics: total spend, total conversions, CpFN, CTR, days running
   - Compute 7-day trend data (daily spend + CpFN for sparklines)
   - Load latest `DecisionRecord` for each variant
   - Return sorted by CpFN ascending (best performers first)
   - Include summary stats in a `summary` key

2. **Create the action endpoint** in `dashboard/api/app.py`:
   ```python
   @app.post("/api/decisions/act")
   async def act_on_decision(variant_id: str, action: str):
   ```
   Where `action` is one of: `"scale"`, `"kill"`, `"pause"`, `"resume"`
   - For `kill`: call `deployer.pause_ad(variant.meta_ad_id)` and set variant status to `"killed"`
   - For `scale`: move variant from farm campaign to scale campaign (update campaign/adset IDs)
   - For `pause`/`resume`: toggle ad status via deployer
   - Notify via Slack

3. **Create the dashboard page** at `dashboard/frontend/pages/performance.html`:
   - Match the existing dark theme used in `review.html` and `portfolio.html`
   - Use the same nav bar with tabs: Review | Portfolio | Hypotheses | Performance
   - Table with sortable columns (click header to sort)
   - Sparklines using Chart.js (small inline line charts per row)
   - Action buttons styled as the existing approve/reject buttons
   - Auto-refresh every 60 seconds (or manual refresh button)
   - Empty state: "No deployed ads yet. Approve variants in the review queue and deploy them to see performance data here."

4. **Add nav links** to `review.html`, `portfolio.html`, `hypotheses.html` — add "Performance" tab

**Files:**
- `dashboard/api/app.py` — 2 new endpoints
- `dashboard/frontend/pages/performance.html` — new file
- `dashboard/frontend/pages/review.html` — add nav tab
- `dashboard/frontend/pages/portfolio.html` — add nav tab
- `dashboard/frontend/pages/hypotheses.html` — add nav tab

**Acceptance criteria:**
- Page loads at `/dashboard/pages/performance.html` with correct nav
- Table shows all deployed variants with metrics (or empty state if none)
- Sparklines render for each variant with 7+ days of data
- Kill/scale buttons work and update variant status
- Summary stats card shows totals at top

---

### P1.3 Regression Insights Dashboard Page

**Status:** ⬜ Not Started
**Priority:** High — team needs to see what the regression says works/doesn't

**What it should show:**
- Coefficient bar chart: horizontal bars, green for negative coefficients (lower CpFN = good), red for positive (higher CpFN = bad), sorted by absolute magnitude
- Each bar labeled with human-readable feature name and confidence tier badge
- Only show features with HIGH or MODERATE confidence (filter out UNRELIABLE by default, toggle to show all)
- Fatigue section: features whose rolling coefficient is degrading vs all-time
- Playbook rules section: natural-language rules from PlaybookTranslator with good/bad examples
- Model health card: R², adjusted R², test R², sample size, number of features, Durbin-Watson, condition number
- Format comparison card: video vs static CpFN with t-test p-value

**Steps:**

1. **The API endpoint already exists** at `GET /api/regression` — it returns `model_health`, `validation_detail`, and top features with bootstrap CIs. Check if it returns enough data for the dashboard. May need to extend it to also return:
   - All coefficients with their confidence tiers (not just top features)
   - Fatigue alerts (from memory)
   - Playbook rules (from last translation run)
   - Format comparison data

2. **Add endpoint extensions** if needed:
   ```python
   @app.get("/api/regression/coefficients")
   async def regression_coefficients():
       # Return all coefficients with tiers, CIs, human-readable names
   
   @app.get("/api/regression/fatigue")
   async def regression_fatigue():
       # Return fatigue alerts from memory
   
   @app.get("/api/regression/playbook-rules")
   async def regression_playbook_rules():
       # Return translated playbook rules
   ```

3. **Create the page** at `dashboard/frontend/pages/insights.html`:
   - Same dark theme and nav bar as other pages
   - Chart.js horizontal bar chart for coefficients
   - Color-coded by confidence tier: gold=HIGH, blue=MODERATE, gray=DIRECTIONAL, red=UNRELIABLE
   - Fatigue section with trend arrows (↗ improving, → stable, ↘ declining)
   - Playbook rules as cards with good/bad examples (styled like the learnings section in review.html)
   - Model health as a stats card at the top
   - Toggle: "Show all features" vs "Show reliable only"

4. **Add nav links** to all other pages

**Files:**
- `dashboard/api/app.py` — extend/add regression endpoints
- `dashboard/frontend/pages/insights.html` — new file
- All other dashboard pages — add nav tab

**Acceptance criteria:**
- Coefficient chart renders with correct colors and sorting
- Confidence tier filter works (toggle unreliable on/off)
- Playbook rules display as readable cards
- Model health stats match what `engine/regression/model.py` computes
- Format comparison shows video vs static with p-value

---

### P1.4 Bulk Creative Export (ZIP Download)

**Status:** ⬜ Not Started
**Priority:** Medium — bridge for manual upload while programmatic deploy is being tested

**Purpose:** Adam and Matt can manually upload approved creatives to Meta/Google while programmatic deploy is being validated. This is the interim workflow.

**Steps:**

1. **Create the API endpoint** in `dashboard/api/app.py`:
   ```python
   from fastapi.responses import StreamingResponse
   import zipfile
   import io
   
   @app.get("/api/variants/export")
   async def export_variants(status: str = "approved"):
   ```
   This should:
   - Load all variants with the requested status
   - For each variant with a valid rendered PNG:
     - Determine the format folder: `meta_feed/`, `meta_story/`, `google_display/`, etc. (from `variant.brief.formats_requested` or `variant.template_id`)
     - Add the PNG to a ZIP under that folder, named `{variant_id}.png`
   - Create a CSV file (`copy.csv`) with columns: variant_id, headline, body, cta, hook_type, message_type, tone, template_id, format
   - Stream the ZIP as a download response with `Content-Disposition: attachment; filename="approved_creatives_{date}.zip"`

2. **Add an export button** to the review dashboard (`review.html`):
   - In the toolbar/header area, add a "Download Approved" button
   - On click, trigger `window.location.href = '/api/variants/export?status=approved'`

**Files:**
- `dashboard/api/app.py` — new endpoint
- `dashboard/frontend/pages/review.html` — export button

**Acceptance criteria:**
- `GET /api/variants/export?status=approved` downloads a valid ZIP file
- ZIP contains folders organized by format with PNGs inside
- ZIP contains `copy.csv` with all variant copy and metadata
- Works with 0 approved variants (returns empty ZIP with just the CSV header)

---

### P1.5 Dashboard Navigation Consistency

**Status:** 🔶 Partial — some pages have nav tabs, not all are consistent

**Steps:**

1. Ensure every dashboard page has the same nav bar with tabs:
   - **Review** → `/dashboard/pages/review.html`
   - **Portfolio** → `/dashboard/pages/portfolio.html`
   - **Hypotheses** → `/dashboard/pages/hypotheses.html`
   - **Performance** → `/dashboard/pages/performance.html` (P1.2)
   - **Insights** → `/dashboard/pages/insights.html` (P1.3)

2. The active tab should be highlighted based on the current page

3. Each page should have a consistent header with the JotPsych logo or "Ads Engine" title

**Files:** All files in `dashboard/frontend/pages/`

**Acceptance criteria:**
- All 5 pages have identical nav bar
- Active page is highlighted
- Navigation works between all pages

---

## P2 — Close the Feedback Loop

> These tasks wire up the full deploy → track → regress → learn cycle. This is when the system starts running on real ad spend and real performance data. Requires Meta API write-access keys from Adam.

---

### P2.1 Get Meta API Write-Access Keys & Configure

**Status:** ⬜ Blocked on Adam
**Priority:** Critical — gates all of P2

**What's needed from Adam:**
- Meta Business Manager: grant the app write access to the ad account `act_1582817295627677`
- Required permissions: `ads_management`, `ads_read`, `pages_read_engagement`, `pages_manage_ads`
- The access token in `.env` (`META_ACCESS_TOKEN`) must have these permissions
- Facebook Page ID for the JotPsych page (required for `object_story_spec` when creating ad creatives)

**Steps after receiving keys:**

1. Update `.env`:
   ```
   META_ACCESS_TOKEN=<new-token-with-write-permissions>
   META_PAGE_ID=<facebook-page-id>
   ```

2. Verify read access still works:
   ```bash
   python -c "from engine.orchestrator import Orchestrator; o = Orchestrator(); print(len(o.store.get_all_existing_ads()))"
   ```

3. Verify write access works (test with a paused ad):
   ```python
   from engine.deployment.deployer import MetaDeployer
   from config.settings import Settings
   s = Settings()
   d = MetaDeployer(access_token=s.META_ACCESS_TOKEN, ad_account_id=s.META_AD_ACCOUNT_ID, page_id=s.META_PAGE_ID)
   # Upload a test image
   result = d.upload_asset(test_variant)  # Should return a hash
   ```

4. Verify the `MetaDeployer` in `engine/deployment/deployer.py` correctly uses `META_PAGE_ID`:
   - Check `create_ad()` — it creates an `AdCreative` with `object_story_spec` which requires `page_id`
   - If `page_id` is not being passed from settings through the orchestrator to the deployer, wire it through

**Files:** `.env`, potentially `engine/orchestrator.py` and `engine/deployment/deployer.py`

**Acceptance criteria:**
- `MetaDeployer.upload_asset()` successfully uploads a PNG to Meta CDN
- `MetaDeployer.create_ad()` successfully creates a paused ad in the farm campaign
- `MetaDeployer.pause_ad()` and `resume_ad()` toggle status correctly

---

### P2.2 End-to-End Deploy Flow from Dashboard

**Status:** 🔶 Endpoint exists, untested with real credentials

**Current state:** `POST /api/deploy` exists in `dashboard/api/app.py`. It builds a `MetaDeployer` from settings and deploys approved variants. The review page has a "Deploy Approved" button with a campaign/adset modal.

**Steps:**

1. **Verify the deploy endpoint** in `dashboard/api/app.py`:
   - Check that it reads `META_PAGE_ID` from settings and passes it to `MetaDeployer`
   - Check that it correctly handles the request body (should accept `campaign_id` and `adset_id` for farm campaign placement)
   - Check error handling: what happens if upload fails? if ad creation fails?

2. **Add campaign/adset configuration** to `config/settings.py`:
   ```python
   META_FARM_CAMPAIGN_ID: str = ""    # Test budget campaign
   META_FARM_ADSET_ID: str = ""       # Adset within farm campaign
   META_SCALE_CAMPAIGN_ID: str = ""   # Proven winners campaign
   META_SCALE_ADSET_ID: str = ""      # Adset within scale campaign
   ```
   These IDs come from Adam/Matt — they know the existing campaign structure.

3. **Update the deploy endpoint** to default to farm campaign if no campaign_id provided:
   ```python
   campaign_id = request.campaign_id or settings.META_FARM_CAMPAIGN_ID
   adset_id = request.adset_id or settings.META_FARM_ADSET_ID
   ```

4. **Update the deploy button UI** in `review.html`:
   - Pre-populate the campaign/adset modal with farm campaign IDs from a config endpoint
   - Show confirmation: "Deploy N approved variants to Meta as PAUSED ads in Farm campaign?"
   - After deploy, show results: success count, failure count, any errors

5. **Wire `meta_ad_id` back to variant**:
   - After successful deploy, the deployer returns the Meta ad ID
   - Save it to the variant JSON: `variant.meta_ad_id = result_ad_id`
   - This ID is needed for tracking and pause/resume/kill operations

6. **Send Slack notification** on deploy (already formatted in `notifications.py`)

**Files:**
- `dashboard/api/app.py` — verify/fix deploy endpoint
- `config/settings.py` — add campaign/adset IDs
- `dashboard/frontend/pages/review.html` — improve deploy modal UX
- `engine/deployment/deployer.py` — verify page_id flow

**Acceptance criteria:**
- Click "Deploy Approved" → variants uploaded to Meta as paused ads
- Each variant's `meta_ad_id` saved to its JSON
- Slack notification fires
- Dashboard shows success/failure count

---

### P2.3 Wire Meta Performance Tracking into Daily Cycle

**Status:** 🔶 Tracker implemented, not running automatically

**Current state:** `MetaTracker` in `engine/tracking/tracker.py` has `pull_ad_metrics()` and `pull_all_active()`. `PerformanceTracker` wraps it. The orchestrator creates them conditionally. `run_daily_cycle()` calls tracker methods.

**Steps:**

1. **Verify the tracking flow** in `engine/orchestrator.py` → `run_daily_cycle()`:
   - Confirm it calls `self.performance_tracker.pull_daily()` which iterates deployed variants
   - Confirm it creates `PerformanceSnapshot` objects and saves them via `store.save_snapshot()`
   - Confirm it then passes snapshots to the decision engine

2. **Verify `MetaTracker.pull_ad_metrics()`** parses the right conversion event:
   - Current code looks for `offsite_conversion.fb_pixel_custom` in the actions array
   - Verify this maps to first note completion (confirm with Adam)
   - If the conversion event name changed post-2FA fix, update `_parse_actions()` in `tracker.py`

3. **Add a manual tracking endpoint** to the dashboard:
   ```python
   @app.post("/api/tracking/pull")
   async def pull_tracking():
       orch = Orchestrator()
       results = orch.performance_tracker.pull_daily()
       return {"snapshots_created": len(results), "variants_tracked": [...]}
   ```

4. **Add tracking to the daily cycle flow** (verify this sequence in `run_daily_cycle()`):
   ```
   pull_daily_stats() → save_snapshots() → run_decisions() → run_regression() → build_memory() → notify()
   ```

5. **Handle edge cases:**
   - Variant deployed but not yet delivering (0 impressions) — skip, don't create empty snapshot
   - Rate limiting from Meta API — existing retry logic in tracker should handle this
   - Variant killed externally (in Meta Ads Manager, not via engine) — detect status mismatch

**Files:**
- `engine/orchestrator.py` — verify daily cycle tracking flow
- `engine/tracking/tracker.py` — verify conversion event parsing
- `dashboard/api/app.py` — add manual pull endpoint

**Acceptance criteria:**
- `pull_daily()` fetches metrics for all deployed variants with `meta_ad_id`
- Snapshots saved as JSON in `data/performance/snapshots/`
- Decision engine processes snapshots and produces verdicts
- Slack notification with daily digest

---

### P2.4 Scheduler — Automated Daily Cycle

**Status:** ⬜ Not Started
**Priority:** High — the system should run without manual intervention

**Steps:**

1. **Add APScheduler to requirements:**
   ```
   apscheduler>=3.10.0
   ```

2. **Create scheduler setup** in `dashboard/api/app.py` (run inside the FastAPI process):
   ```python
   from apscheduler.schedulers.asyncio import AsyncIOScheduler
   from apscheduler.triggers.cron import CronTrigger
   
   scheduler = AsyncIOScheduler()
   
   async def daily_cycle_job():
       """Run the full daily cycle: track → decide → regress → memory → notify."""
       try:
           orch = Orchestrator()
           await asyncio.to_thread(orch.run_daily_cycle)
       except Exception as e:
           print(f"[SCHEDULER ERROR] {e}")
           # Notify via Slack that the daily cycle failed
   
   @app.on_event("startup")
   async def start_scheduler():
       scheduler.add_job(
           daily_cycle_job,
           CronTrigger(hour=6, minute=0, timezone="US/Pacific"),  # 6am PT
           id="daily_cycle",
           replace_existing=True,
       )
       scheduler.start()
   
   @app.on_event("shutdown")
   async def stop_scheduler():
       scheduler.shutdown()
   ```

3. **Add manual trigger endpoint:**
   ```python
   @app.post("/api/admin/run-cycle")
   async def manual_daily_cycle():
       """Manually trigger the daily cycle."""
       import asyncio
       asyncio.create_task(daily_cycle_job())
       return {"status": "started", "message": "Daily cycle running in background"}
   ```

4. **Add cycle run logging:**
   - Log each cycle run to `data/cycles/{date}.json` with: start time, end time, results (variants tracked, decisions made, regression run, memory updated)
   - Add `GET /api/admin/cycles` endpoint to view cycle history

5. **Add a dashboard admin panel** (optional, can be simple):
   - Show last cycle run time and status
   - "Run Now" button → `POST /api/admin/run-cycle`
   - Show cycle history

**Files:**
- `requirements.txt` — add `apscheduler`
- `dashboard/api/app.py` — scheduler setup, manual trigger, cycle history
- `engine/orchestrator.py` — ensure `run_daily_cycle()` logs results to cycles dir

**Acceptance criteria:**
- Scheduler runs `daily_cycle_job()` at 6am PT daily
- `POST /api/admin/run-cycle` triggers the cycle manually
- Cycle results logged to `data/cycles/`
- Cycle failure notifies via Slack

---

### P2.5 Budget Pacing & Spend Tracking

**Status:** ⬜ Not Started
**Priority:** Medium — important for financial accountability

**Steps:**

1. **Add budget settings** to `config/settings.py`:
   ```python
   MONTHLY_BUDGET: float = 17500.0        # $15-20K/mo, midpoint
   BUDGET_ALERT_HIGH: float = 1.10         # Alert if run rate >110% of budget
   BUDGET_ALERT_LOW: float = 0.70          # Alert if run rate <70% of budget
   ```

2. **Create budget tracking function** in `engine/tracking/tracker.py` or a new `engine/tracking/budget.py`:
   ```python
   def compute_budget_pacing(snapshots: list[PerformanceSnapshot], monthly_budget: float) -> dict:
       """Compute daily/weekly/monthly spend vs budget."""
       # Group snapshots by date
       # Compute: total_spend_this_month, daily_average, projected_monthly, run_rate_pct
       # Return pacing data with alert status
   ```

3. **Add budget endpoint** to `dashboard/api/app.py`:
   ```python
   @app.get("/api/budget/pacing")
   async def budget_pacing():
       # Load all snapshots for current month
       # Compute pacing
       # Return: total_spend, daily_avg, projected, budget, pacing_pct, alert_status
   ```

4. **Wire budget alerts into daily cycle:**
   - After pulling daily stats, compute pacing
   - If run rate > 110% or < 70%, call `notifier.notify_budget_alert()`
   - The notification method already exists in `notifications.py`

5. **Add budget card to performance dashboard** (P1.2):
   - Show: spent this month / budget, daily average, projected end-of-month, pacing bar

**Files:**
- `config/settings.py` — budget settings
- `engine/tracking/tracker.py` or new `engine/tracking/budget.py`
- `dashboard/api/app.py` — budget endpoint
- `engine/orchestrator.py` — wire into daily cycle
- `dashboard/frontend/pages/performance.html` — budget card (part of P1.2)

**Acceptance criteria:**
- Budget pacing computes correctly from snapshot data
- Slack alert fires when run rate exceeds thresholds
- Dashboard shows budget status

---

## P3 — Expand Capabilities

> These features extend the system to Google, improve attribution, and introduce AI-generated images alongside templates.

---

### P3.1 Google Ads Deployer Implementation

**Status:** 🚧 Stubbed — `GoogleDeployer` in `engine/deployment/deployer.py` raises `NotImplementedError`
**Blocked on:** Google Ads API developer token, Jenna, conversion tag fix

**Steps:**

1. **Prerequisites from Jenna / Google team:**
   - Google Ads API developer token (approved for production)
   - OAuth2 client ID + secret + refresh token for API access
   - Customer ID for the JotPsych Google Ads account
   - Campaign ID for Google Display Network campaign

2. **Add `google-ads` dependency:**
   ```
   google-ads>=24.0.0
   ```

3. **Implement `GoogleDeployer`** in `engine/deployment/deployer.py`:
   ```python
   class GoogleDeployer:
       def __init__(self, developer_token, client_id, client_secret, refresh_token, customer_id):
           from google.ads.googleads.client import GoogleAdsClient
           self.client = GoogleAdsClient.load_from_dict({
               "developer_token": developer_token,
               "client_id": client_id,
               "client_secret": client_secret,
               "refresh_token": refresh_token,
               "login_customer_id": customer_id,
           })
           self.customer_id = customer_id
       
       def upload_asset(self, variant) -> str:
           """Upload image as a Google Ads MediaFile asset."""
           # Use AssetService to create ImageAsset
           # Return asset resource name
       
       def create_ad(self, variant, campaign_id, ad_group_id) -> str:
           """Create a responsive display ad."""
           # Use AdGroupAdService
           # Create ResponsiveDisplayAd with headlines, descriptions, images
           # Return ad resource name
       
       def pause_ad(self, ad_resource_name):
           """Pause an ad."""
       
       def resume_ad(self, ad_resource_name):
           """Resume a paused ad."""
   ```

4. **Wire into `AdDeployer`** in `deployer.py`:
   - Update `deploy_variant()` to route Google-platform variants to `GoogleDeployer`

5. **Wire into orchestrator:**
   - In `Orchestrator.__init__()`, conditionally create `GoogleDeployer` when Google credentials are configured
   - Pass it to `AdDeployer`

6. **Update variant model:**
   - `AdVariant` already has `meta_ad_id` — add `google_ad_resource_name: Optional[str] = None`

**Files:**
- `engine/deployment/deployer.py` — implement GoogleDeployer
- `engine/orchestrator.py` — wire GoogleDeployer
- `engine/models.py` — add google_ad_resource_name to AdVariant
- `config/settings.py` — Google settings (already has placeholder fields)
- `requirements.txt` — add google-ads

**Acceptance criteria:**
- Google Display ads created programmatically
- Assets uploaded as Google Media assets
- Pause/resume works
- Variant stores google_ad_resource_name

---

### P3.2 Google Ads Performance Tracker

**Status:** 🚧 Stubbed — `GoogleTracker` in `engine/tracking/tracker.py` raises `NotImplementedError`

**Steps:**

1. **Implement `GoogleTracker`** in `engine/tracking/tracker.py`:
   ```python
   class GoogleTracker:
       def __init__(self, client, customer_id):
           self.client = client
           self.customer_id = customer_id
       
       def pull_ad_metrics(self, ad_resource_name, date_str) -> dict:
           """Pull metrics for a single ad on a single day using GAQL."""
           ga_service = self.client.get_service("GoogleAdsService")
           query = f"""
               SELECT
                   ad_group_ad.ad.id,
                   metrics.impressions,
                   metrics.clicks,
                   metrics.cost_micros,
                   metrics.conversions,
                   metrics.conversions_value
               FROM ad_group_ad
               WHERE ad_group_ad.ad.resource_name = '{ad_resource_name}'
               AND segments.date = '{date_str}'
           """
           # Parse response, compute CpFN
           # Return dict matching PerformanceSnapshot fields
   ```

2. **Wire into `PerformanceTracker`:**
   - `pull_daily()` should check variant platform and route to the correct tracker
   - Google variants use `google_ad_resource_name` instead of `meta_ad_id`

3. **Handle the conversion event mapping:**
   - Google conversion action for first note completion (get name from Jenna)
   - Map to the same `conversions` field in PerformanceSnapshot

**Files:**
- `engine/tracking/tracker.py` — implement GoogleTracker
- `engine/orchestrator.py` — wire GoogleTracker

**Acceptance criteria:**
- Google ad metrics pulled successfully
- PerformanceSnapshot created from Google data
- Feeds into the same regression pipeline as Meta data

---

### P3.3 Google Conversion Tag Fix (Server-Side Measurement Protocol)

**Status:** ⬜ Not Started
**Priority:** Medium — Google showing 2 conversions vs 15 real

**Context:** The Google Analytics tag on the JotPsych web app is broken — likely because 2FA (SMS verification) interrupts the client-side tag firing during signup. The fix is server-side tracking.

**Steps:**

1. **Set up Google Measurement Protocol:**
   - Get the Measurement ID (G-XXXXXXXX) and API secret from Google Analytics
   - The server-side endpoint is: `POST https://www.google-analytics.com/mp/collect?measurement_id=G-XXX&api_secret=YYY`

2. **Fire conversion event server-side** from the JotPsych backend:
   - When a user completes their first note, fire the event from the server instead of (or in addition to) the client-side tag
   - Include `client_id` (from the GA cookie `_ga`) in the payload
   - This bypasses the 2FA redirect that breaks client-side tracking

3. **Verify conversion data:**
   - Compare Google Analytics conversions with Metabase UTM data
   - They should now align (was 2 vs 15 before fix)

**Note:** This is a JotPsych backend change, not an ads engine change. Coordinate with the engineering team. Once fixed, Google Ads conversion tracking will work correctly for the regression model.

**Acceptance criteria:**
- Google Analytics shows conversion counts matching Metabase UTM data
- Google Ads in-platform conversions align with reality

---

### P3.4 Attribution Deduplication Model

**Status:** ⬜ Not Started
**Priority:** Low — can proceed without it, nice to have for accurate CpFN

**Context:** Meta and Google both take credit for the same conversions (view-through overlap). The discovery survey is treated as canonical but is self-reported.

**Steps:**

1. **Create `engine/attribution/deduplicator.py`:**
   ```python
   class AttributionDeduplicator:
       def deduplicate(self, meta_conversions, google_conversions, survey_responses) -> dict:
           """Reconcile conversion counts across platforms."""
           # Use discovery survey as ground truth calibration
           # Apply fractional attribution: if both platforms claim a conversion,
           # split 50/50 or use last-click as tiebreaker
           # Return deduplicated conversion count per platform per ad
   ```

2. **Feed deduplicated counts into regression:**
   - Replace raw platform-reported conversions with deduplicated counts
   - This changes CpFN calculations for all ads

3. **Add dashboard visualization:**
   - Show attribution overlap: Venn diagram or table of Meta-only, Google-only, overlap counts

**Files:**
- `engine/attribution/deduplicator.py` — new module
- `engine/regression/model.py` — use deduplicated data
- Dashboard page — attribution visualization

**Acceptance criteria:**
- Deduplicated conversion counts produced
- Regression uses corrected CpFN
- Dashboard shows attribution breakdown

---

### P3.5 AI Image Generation (Phase 2 of Generation Pipeline)

**Status:** ⬜ Removed in current codebase (Gemini/DALL-E code stripped)
**Priority:** Medium — unlocks photorealistic ad images alongside templates

**Context:** Phase 1 uses HTML/CSS templates rendered via Playwright. Phase 2 adds AI-generated images as an alternative. The regression will tell us which approach produces lower CpFN. Both paths coexist — templates for brand-consistent layouts, AI images for photorealistic scenes.

**Steps:**

1. **Choose the image generation API:**
   - Options: Gemini Imagen 3 (Google), DALL-E 3 (OpenAI), Flux (Replicate), Ideogram
   - Recommendation: Start with Gemini Imagen 3 since we already have a `gemini_api` key in settings and the Google ecosystem has strong image quality
   - Add the API client dependency

2. **Create `engine/generation/image_generator.py`** (new, separate from `generator.py`):
   ```python
   class AIImageGenerator:
       def __init__(self, api_key: str, model: str = "imagen-3.0-generate-002"):
           # Initialize Gemini/other client
       
       def generate(self, variant: AdVariant, scene: dict) -> str:
           """Generate a single image from a scene description."""
           prompt = self._build_prompt(variant, scene)
           # Call API
           # Validate response (MIME type, file size, magic bytes)
           # Save to data/creatives/rendered/
           # Return path
       
       def _build_prompt(self, variant, scene) -> str:
           """Build image prompt from variant taxonomy + scene library + brand context."""
           # Use scene_library.py for scene descriptions
           # Inject brand colors and visual style from brand.py
           # Add negative prompts (no AI artifacts, no fake text, etc.)
       
       def _validate_image(self, data: bytes) -> bool:
           """Validate image is real (size, format, not corrupt)."""
   ```

3. **Wire into generator:**
   - In `engine/generation/generator.py`, add a `generate_with_ai_images()` path alongside `generate_with_templates()`
   - The variant matrix decides which path each variant takes (based on taxonomy or A/B split)
   - Variants track `asset_source: "template" | "ai_generated"` for regression

4. **Add quality gate:**
   - AI images must pass human review before being deployed
   - Add `ai_image_quality_score` field to variant (reviewer rates 1-5 during review)
   - Auto-reject images rated below 3

5. **A/B testing:**
   - For each brief, generate some variants with templates and some with AI images
   - The regression will eventually show which `asset_source` produces better CpFN
   - Track this as a feature in the regression

6. **Scene library integration:**
   - The 27 scenes in `scene_library.py` were designed for AI image generation
   - Each scene has detailed descriptions, camera angles, lighting, and negative prompts
   - The image generator matches scenes to variants using the same priority scoring

**Files:**
- `engine/generation/image_generator.py` — new module
- `engine/generation/generator.py` — add AI image path
- `engine/models.py` — add `asset_source` to AdVariant
- `config/settings.py` — image gen API settings (already has `IMAGE_GEN_*` placeholders)

**Acceptance criteria:**
- AI images generated from scene library descriptions
- Images pass validation (real images, correct dimensions, >10KB)
- Variants track whether they used template or AI image
- Both asset sources flow through the same review → deploy → track → regress pipeline

---

### P3.6 Video Generation Pipeline

**Status:** 🔶 `video_renderer.py` exists but not wired
**Priority:** Low — video is highest performing format historically, but template-based video is limited

**Context:** `engine/generation/video_renderer.py` uses Playwright `recordVideo` + ffmpeg to capture CSS animations as MP4. The scene library has 10 video-specific scenes. Veo (Google video AI) code was removed with the rest of AI generation.

**Steps:**

1. **Wire `video_renderer.py` into the generation pipeline:**
   - In `generator.py`, add a video generation path for story templates (`full_bleed`, `swipe_up`) that have CSS animations
   - Use `VideoRenderer.render()` to capture the animation as MP4
   - Save to `data/creatives/rendered/{variant_id}.mp4`

2. **Update the review UI** to handle video previews:
   - Add `<video>` tag rendering back to `review.html` for `.mp4` assets
   - Autoplay, muted, loop for review

3. **Track video vs static in regression:**
   - `AdVariant.asset_type` already supports `"video"`
   - The regression model's `format_comparison()` already groups by video/static

4. **Future: Veo integration** for AI-generated video (5-15 second clips):
   - Requires Google Veo API access
   - Use video scenes from `scene_library.py`
   - Same quality gate as AI images

**Files:**
- `engine/generation/generator.py` — wire video renderer
- `engine/generation/video_renderer.py` — verify it works
- `dashboard/frontend/pages/review.html` — restore video preview

**Acceptance criteria:**
- Story template animations captured as MP4
- Videos appear in review queue and can be approved/rejected
- Format comparison in regression includes video data

---

## P4 — Future Capture

> These are real ideas worth doing eventually, but not worth scheduling now. Reference this section when looking for what to build next after P3 is done.

---

### P4.1 LoRA Model Integration (Daniel's Workstream)

**What:** Fine-tune an image model (Stable Diffusion / Flux) on JotPsych brand aesthetics using the brand guidelines, approved ad images, and product screenshots as training data.

**Why:** A LoRA model could produce images that inherently match JotPsych's visual identity without needing extensive prompt engineering. This would be the highest-quality path for AI image generation.

**Requirements:**
- 50+ high-quality training images (approved ads, brand photos, product screenshots)
- Cloud GPU for training (Daniel's workstream)
- Replicate or Hugging Face for inference API
- A/B test: LoRA vs Gemini vs Template — regression determines winner

**Files:** Would create `engine/generation/lora_generator.py`

---

### P4.2 UGC-Style Video (Non-AI)

**What:** Talking-head / screen-recording style video ads — historically the highest performing format for JotPsych.

**Why:** "UGC-style video, motion/energy, get to product fast" is documented as what works best. AI video can't do convincing talking-head content yet.

**Options:**
- HeyGen AI avatar (API-accessible, uncanny valley risk)
- Voice clone + stock footage
- Source real clinician UGC (highest quality, hardest to scale)
- Screen recording of JotPsych in action + voiceover

**Cannot fully automate** — requires human or avatar model. Best approach: create a UGC script generator that produces scripts from briefs, then a human records them.

---

### P4.3 Competitive Intelligence Scraper

**What:** Monitor Facebook Ad Library for mental health / EHR competitor ads.

**Steps:**
- Use Meta Ad Library API (public, no special access needed)
- Search for competitor ad account IDs or keywords ("EHR", "therapy notes", "clinical documentation")
- Tag competitor ads with the same MECE taxonomy
- Feed into `MarketMemory.competitive_observations`
- Surface in insights dashboard: "Competitor X is running more urgency-tone ads this month"

**Files:** Would create `engine/analysis/competitive.py`

---

### P4.4 Voice Note Intake (Team → Ideas)

**What:** Record a voice memo → Whisper transcription → `IntakeParser.parse()` → brief → generation.

**Why:** Lower friction for idea capture. Instead of typing, team members speak their concept.

**Steps:**
- Add `POST /api/intake/voice` endpoint accepting audio upload
- Transcribe via OpenAI Whisper API (already a dependency)
- Pass transcript to `IntakeParser.parse()`
- Return generated brief for confirmation

**Files:** `dashboard/api/app.py`, `engine/intake/parser.py`

---

### P4.5 LinkedIn Ads Integration

**What:** LinkedIn Campaign Manager API for B2B targeting of clinic decision-makers.

**When:** Activate when Meta CpFN plateaus or LinkedIn gets budget allocation.

**Steps:**
- LinkedIn Marketing API access
- `LinkedInDeployer` + `LinkedInTracker` following same pattern as Meta
- Different ad formats: Single Image, Carousel, Video, Text
- Different copy constraints (LinkedIn is more professional)

---

### P4.6 Proper Database Migration

**What:** Migrate from flat JSON files in `data/` to PostgreSQL (Supabase) + SQLAlchemy.

**When:** >10K variants, or concurrent write pressure from multiple users/schedulers.

**How:** `engine/store.py` already has a clean interface. Swap the file I/O methods for SQLAlchemy queries. Same interface, different backend.

**Tables:** briefs, variants, snapshots, decisions, existing_ads, memory, hypotheses, cycles

---

### P4.7 Campaign Structure Automation

**What:** Auto-create farm/scale campaign structure programmatically in Meta and Google.

**Risk:** Misconfiguration is expensive. Only after 3+ months of stable manual operation.

**Steps:**
- Create campaign with daily budget
- Create adsets with targeting (broad, let platforms optimize)
- Wire new campaign/adset IDs into deployer config

---

### P4.8 Meta Lead Form Integration

**What:** Pull lead submissions from Meta lead form ads → route to Chris Hume for SDR follow-up. Track lead → signup → first note completion funnel per ad.

**Steps:**
- Use Meta Graph API to pull leads: `GET /{ad_id}/leads`
- Create `LeadRecord` model with: lead_id, ad_id, name, email, phone, timestamp
- Webhook or polling to get new leads
- Forward to Chris via Slack or email
- Track conversion funnel: lead → signup → first note

---

## Open Questions

1. **Meta write-access keys:** Adam sending — timeline? Which ad account? What permissions?
2. **Campaign/adset IDs:** What are the exact IDs for farm (test budget) and scale (proven winners) campaigns?
3. **Conversion event name:** Post-2FA fix, is `offsite_conversion.fb_pixel_custom` still the correct conversion event? What's the exact event name for first note completion?
4. **Kill/scale authority:** Auto-kill when `DecisionVerdict.KILL`, or surface recommendation for human approval first? Current plan: human-in-the-loop until trust is established.
5. **Google workstream:** Display network re-activation, or non-brand search? Jenna's timeline?
6. **Review cadence:** When is the first Nate + Jackson review session? This triggers voice note preference capture.
7. **Bulk export:** Does Adam/Matt want ZIP download as manual upload workaround?
8. **Budget:** Current monthly budget? Is $17.5K midpoint correct?

---

## Implementation Order (Recommended Sequence)

For an agent picking this up, here's the recommended execution order:

```
P0.1  Fix concept endpoint ImportError         (5 min, unblocks concept workflow)
P1.1  Wire Slack notifications                 (30 min, enables team visibility)
P1.4  Bulk creative export                     (1 hr, enables manual ad upload)
P1.5  Dashboard navigation consistency         (30 min, polish)
P1.2  Performance dashboard page               (3 hr, major feature)
P1.3  Regression insights dashboard page       (3 hr, major feature)
P2.1  Get Meta API keys + configure            (blocked on Adam, do when available)
P2.2  End-to-end deploy flow                   (2 hr, requires P2.1)
P2.3  Wire Meta tracking                       (2 hr, requires P2.2)
P2.4  Scheduler                                (1 hr, requires P2.3)
P2.5  Budget pacing                            (1 hr, requires P2.3)
P3.1  Google deployer                          (4 hr, blocked on Jenna)
P3.2  Google tracker                           (2 hr, requires P3.1)
P3.5  AI image generation                      (6 hr, independent)
P3.6  Video generation                         (3 hr, independent)
P3.3  Google conversion tag fix                (external, coordinate with eng)
P3.4  Attribution deduplication                (4 hr, requires P3.3)
```

---

## Completed Features Reference

| Feature | Completed | Key Files |
|---------|-----------|-----------|
| Intake parser (idea → brief via Claude) | 2026-03-25 | `engine/intake/parser.py` |
| Copy agents v2 (slot-based headline/body/CTA) | 2026-03-25, rewritten 03-28 | `engine/generation/copy_agents.py` |
| Quality filter (23 AI-tells, 12 generic phrases) | 2026-03-25 | `engine/generation/quality_filter.py` |
| Variant matrix (explore/exploit 80/20, fatigue, per-attr caps) | 2026-03-25–28 | `engine/generation/variant_matrix.py` |
| Meta ads read export (432 ads, $304K spend) | 2026-03-26 | `engine/analysis/analyzer.py` |
| Claude taxonomy tagging (MECE, 13 dimensions, confidence) | 2026-03-26 | `engine/analysis/analyzer.py` |
| Portfolio analysis + playbook generation | 2026-03-26 | `data/existing_creative/playbook.md` |
| Regression model (WLS, decay, rolling, interactions, validation) | 2026-03-25–27 | `engine/regression/model.py` |
| Brand kit integration (colors, typography, voice) | 2026-03-26 | `engine/brand.py` |
| Template renderer (HTML → PNG via Playwright, 9 templates) | 2026-03-27 | `engine/generation/template_renderer.py` |
| Template selector (taxonomy → template + color scheme) | 2026-03-27 | `engine/generation/template_selector.py` |
| Review pipeline (approve/reject/chips/duration tracking) | 2026-03-26 | `engine/review/reviewer.py`, `chips.py` |
| Review dashboard (Tinder/gallery, scoreboard, learnings) | 2026-03-26 | `dashboard/frontend/pages/review.html` |
| Monologue review parser | 2026-03-27 | `engine/review/monologue_parser.py` |
| Three-layer creative memory | 2026-03-27 | `engine/memory/` |
| Memory decay + archiving | 2026-03-27 | `engine/memory/builder.py` |
| Playbook translator (coefficients → human rules) | 2026-03-27 | `engine/memory/playbook_translator.py` |
| Concept-to-20-variants expander | 2026-03-27 | `engine/intake/concept_expander.py` |
| Decision engine (scale/kill/wait) | 2026-03-25 | `engine/decisions/engine.py` |
| Meta deployer (implemented, needs keys) | 2026-03-28 | `engine/deployment/deployer.py` |
| Meta tracker (implemented, needs deployed ads) | 2026-03-28 | `engine/tracking/tracker.py` |
| Hypothesis extractor + tracker | 2026-03-28 | `engine/tracking/hypothesis_*.py` |
| Hypotheses dashboard page | 2026-03-28 | `dashboard/frontend/pages/hypotheses.html` |
| Portfolio visualization (bubble chart, zoom, top performers) | 2026-03-28 | `dashboard/frontend/pages/portfolio.html` |
| Ad copy diversity fix (slot-based, per-attr caps) | 2026-03-28 | `engine/generation/copy_agents.py`, `variant_matrix.py` |
| Orchestrator + CLI (12 commands) | 2026-03-25–28 | `engine/orchestrator.py` |
| Dashboard API (30+ endpoints) | 2026-03-25–28 | `dashboard/api/app.py` |
| Stale asset healing (startup + manual) | 2026-03-26 | `dashboard/api/app.py` |
| Scene library (27 scenes — 17 image, 10 video) | 2026-03-26 | `engine/generation/scene_library.py` |
| Swipe file ingestion (URL/image → tagged, excluded from regression) | 2026-03-27 | `dashboard/api/app.py` |
| Voice note transcription (Whisper) + preference synthesis | 2026-03-27 | `dashboard/api/app.py` |
| Creative direction as first-class input | 2026-03-27 | `engine/memory/models.py`, `engine/intake/parser.py` |

---

*Last updated: 2026-03-28 — Aryan*
*Next review: When Meta write-access keys arrive from Adam*
