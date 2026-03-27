# Ads Engine — Roadmap & Feature Backlog

> **How to use this doc:** Reference it before every session. Update status inline when things ship. Add new items at the bottom of their priority section. Cross-reference the CHANGELOG for what was built and why.

---

## Current Sprint Focus

**Phase 1 — Creative Excellence Loop**
Make the regress → memory → analysis → generation pipeline excellent *before* deploying anything at scale. Mediocre creative at scale wastes money. The loop needs to produce human-quality, brand-consistent, insight-driven ads that Nate and Jackson would approve without hesitation.

**Phase 2 — Close the Feedback Loop** *(unlocks when Phase 1 output is strong)*
Deploy → track → feed real performance data back into regression → memory gets smarter over cycles.

**Phase 3 — Automation & Scale** *(unlocks when Phase 2 is running)*
Scheduler, multi-channel, budget automation, full hands-off daily cycle.

---

## Quick Status

| Stage | Quality | Status |
|-------|---------|--------|
| Analysis (existing ads → insights) | 🔶 Good skeleton, needs depth | ✅ Running |
| Brief / Intake (idea → structured brief) | 🔶 Works, briefs are thin | ✅ Running |
| Generation — Copy (brief → headlines/body/CTA) | 🔶 Works, quality unverified | ✅ Running |
| Generation — Images (brief → visuals) | 🔴 Likely AI-looking | 🔄 In Progress |
| Generation — Templates (HTML → PNG) | 🔶 3 templates, unaudited | 🔄 In Progress |
| Generation — Video (brief → Veo clips) | 🔴 Untested end-to-end | 🔄 In Progress |
| Regression (perf data → coefficients) | 🔶 Good model, thin data (141 obs) | ✅ Running |
| Memory (compounding knowledge system) | 🔶 Architecture done, untested live | ✅ Running |
| Review (gallery + approve/reject) | 🔶 Works, needs UI polish | 🔄 Partial |
| Deploy (variants → Meta/Google) | — | 🚧 Stubbed |
| Track (pull daily metrics) | — | 🚧 Stubbed |
| Notifications (Slack) | — | 🚧 Stubbed |

---

## Priority Legend

| Label | Meaning |
|-------|---------|
| **P0** | Phase 1 — makes the creative loop excellent. Current focus. |
| **P1** | Phase 2 — closes the feedback loop; unlocks real regression data. |
| **P2** | Phase 3 — automation, scale, infrastructure. |
| **P3** | Future capture — worth noting, not scheduling yet. |

**Status icons:** ✅ Done · 🔄 In Progress · ⬜ Not Started · 🚧 Stubbed

**Owners:** Aryan · Alex · Daniel · Adam · Jenna (Google)

---

## P0 — Creative Excellence Loop

> The output of this stage must be something we'd be proud to show Adam and the team before we ever think about deploying. Build for quality, not coverage.

---

### ANALYSIS STAGE

### A1. Taxonomy Quality Audit — are Claude's tags actually accurate?
- **Status:** ⬜ Not Started
- **Owner:** Aryan + Alex
- **Why it matters:** The entire regression and memory system is built on taxonomy tags. If Claude is mislabeling `hook_type` or conflating `tone` dimensions, every downstream coefficient is noise.
- **What's needed:**
  - [ ] Sample 50 tagged ads from `data/existing_creative/` — manually review taxonomy vs actual creative
  - [ ] For each dimension (hook_type, message_type, tone, visual_style, subject_matter, cta_type), check: Are the labels MECE? Are they granular enough? Are they being assigned correctly?
  - [ ] Document errors/gaps → refine taxonomy enum values in `engine/models.py` (`CreativeTaxonomy`)
  - [ ] Re-tag any ads where labels changed
  - [ ] Add tagging confidence score to `CreativeTaxonomy` — Claude reports how confident it is per field
- **Reference:** `engine/models.py` (`CreativeTaxonomy`), `engine/analysis/analyzer.py` (`_tag_batch`), `data/existing_creative/`

---

### A2. Brief Quality Improvement — richer briefs → better variants
- **Status:** ⬜ Not Started
- **Owner:** Aryan + Alex
- **Why it matters:** `IntakeParser` converts free-form ideas into `CreativeBrief`. If the brief is thin (vague tone, generic value prop), the generator has nothing to work with. Garbage in, garbage out.
- **What's needed:**
  - [ ] Audit 10 briefs from `data/briefs/` — rate richness: does each field have specific, actionable content?
  - [ ] Improve `IntakeParser` prompt: force specificity on `emotional_register`, `proof_element`, `visual_direction`, `hook_strategy`
  - [ ] Add brief validation step — if any field is generic (e.g., tone = "professional"), force Claude to be more specific before proceeding
  - [ ] Add `target_persona_details` field to `CreativeBrief` — not just "BH clinicians" but specific archetype (e.g., "solo therapist, 8-10 patients/day, drowning in notes after 6pm")
  - [ ] Wire playbook insights into brief generation: when generating from playbook, inject winning pattern examples directly into brief fields
- **Reference:** `engine/intake/parser.py`, `engine/models.py` (`CreativeBrief`), `engine/orchestrator.py` (`submit_idea`)

---

### A3. Playbook Brief Quality — are extracted briefs actually generation-ready?
- **Status:** ⬜ Not Started
- **Owner:** Aryan
- **Why it matters:** `extract_briefs_from_playbook()` produces the briefs used in the automated `generate_from_playbook()` path. These briefs need to be as rich as hand-crafted ones.
- **What's needed:**
  - [ ] Audit the 5 briefs currently in `data/existing_creative/playbook.md` — compare richness to manually submitted ideas
  - [ ] Improve `extract_briefs_from_playbook()` prompt to force population of every `CreativeBrief` field
  - [ ] Add brief scoring step — score each extracted brief on a 1-10 richness scale before passing to generator; reject any below threshold
  - [ ] Add source attribution: which winning pattern seeded this brief? Store in brief metadata for regression feedback
- **Reference:** `engine/analysis/analyzer.py` (`extract_briefs_from_playbook`), `engine/orchestrator.py` (`generate_from_playbook`)

---

### A4. Swipe File Ingestion — more signal into analysis
- **Status:** ⬜ Not Started
- **Owner:** Alex
- **Why it matters:** 432 tagged ads is a decent dataset but it's all JotPsych history. Swipe files (competitor ads, best-in-class healthcare ads) add qualitative signal to generation context without polluting regression coefficients.
- **What's needed:**
  - [ ] `POST /api/intake/swipe` — accepts URL or image upload
  - [ ] For URL: scrape ad copy from Facebook Ad Library or Canva/Figma link; for image: run OCR + Claude description
  - [ ] Tag with taxonomy (same `_tag_batch` flow)
  - [ ] Save as `ExistingAd` with `source="swipe_file"` and `exclude_from_regression=True`
  - [ ] Wire swipe file ads into `GenerationContext` as "stylistic references" — not performance examples but aesthetic/copy inspiration
- **Reference:** `engine/analysis/analyzer.py`, `engine/models.py` (`ExistingAd`), `engine/store.py`

---

### GENERATION STAGE

### G1. Copy Quality Deep Dive — benchmark and improve headline/body/CTA agents
- **Status:** ⬜ Not Started
- **Owner:** Alex + Aryan
- **Why it matters:** We've never actually benchmarked whether the copy agents produce human-quality output. The quality filter catches obvious AI slop, but great copy requires a higher bar.
- **What's needed:**
  - [ ] Generate 20 headline sets + 20 body copy sets using current agents on 3 different briefs
  - [ ] Blind review: Aryan reads output without knowing it's AI-generated — rate on 1-5 scale: specificity, emotional resonance, brand voice adherence
  - [ ] Identify the most common failure modes (too generic, wrong emotional register, ignores brief hook strategy)
  - [ ] Rewrite `HeadlineAgent` and `BodyCopyAgent` system prompts based on audit findings
  - [ ] Add few-shot examples: the 5 best real JotPsych ads (from existing_creative) as gold standard examples in system prompt
  - [ ] Test: does `GenerationContext` memory injection actually improve output? Compare with/without memory block on same brief
- **Reference:** `engine/generation/copy_agents.py`, `engine/generation/quality_filter.py`

---

### G2. Concept-to-20-Variants Workflow
- **Status:** 🔄 Partial (v2 pipeline generates variants but concept → structured diversification not formalized)
- **Owner:** Alex + Aryan
- **Why it matters:** The agreed workflow (from 3/25 kickoff) is: human gives concept → engine creates 20 tactical variants. This is the core usage pattern. Right now generation produces variants but doesn't systematically explore the concept space.
- **What's needed:**
  - [ ] `ConceptExpander` class in `engine/intake/` — takes a concept string ("famous movie psychiatrists") → asks Claude to enumerate: 5 tactical angles, 3 format options, 4 emotional tones, 3 proof types → cross-product → 20 seeds
  - [ ] Each seed becomes a rich `CreativeBrief` with distinct fields (not just copy variation, but different visual direction, hook, tone)
  - [ ] Wire: `POST /api/intake/concept` → expander → 20 briefs → generate loop → return draft variants
  - [ ] Dashboard intake page: single concept textarea → triggers expander → streaming progress (how many variants generated / 20)
  - [ ] Verify: are the 20 output variants actually diverse? Check taxonomy spread across the batch
- **Reference:** `engine/intake/parser.py`, `engine/orchestrator.py` (`submit_idea`), `dashboard/api/app.py`

---

### G3. Image Quality — Prompt Engineering + Technique Pass
- **Status:** 🔄 In Progress (scene library + brand colors wired; output quality unverified)
- **Owner:** Alex + Daniel
- **Why it matters:** "No AI slop" is a hard constraint. Images that look obviously AI-generated undermine credibility and won't pass human review.
- **What's needed:**
  - [ ] **Audit first:** Generate 20 images using current prompts, rate each 1-5 on realism and brand fit
  - [ ] **Negative prompts:** Strengthen anti-AI-artifact language; document specific failure patterns from audit (e.g., wrong hands, fake UI text, generic stock-photo feel)
  - [ ] **Technique: rapid succession of stills** — generate 4-6 slight variations of same scene (camera angle, subject position) → string as slideshow for implied motion
  - [ ] **Technique: real photo modification** — take a real JotPsych product screenshot + add slight modifications (lighting, color grade) rather than generating from scratch
  - [ ] **Style differentiation:** separate prompts for UGC-style (handheld, casual) vs polished (editorial) vs product-focused (UI in frame)
  - [ ] Update `_build_image_prompt_v2()` in generator with findings
  - [ ] Document winning patterns in `scene_library.py` comments
- **Reference:** `engine/generation/generator.py`, `engine/generation/scene_library.py`, `engine/brand.py`

---

### G4. Template Renderer — Audit, Fix, Expand
- **Status:** 🔄 In Progress (3 templates; unaudited for actual visual quality)
- **Owner:** Daniel + Alex
- **Why it matters:** Templates are the most reliable path to brand-consistent, non-AI-looking static ads. They should be ready to ship.
- **What's needed:**
  - [ ] **Visual audit:** Render each template × 4 color schemes = 12 screenshots; review with Aryan; document issues
  - [ ] **Font fix:** Ensure Archivo/Inter load from `brand/fonts/` (local files), not CDN — no external dependency in rendering
  - [ ] **Typography:** Text overflow handling; line-clamp correctness; headline never wraps awkwardly
  - [ ] **Proof element zone:** Add prominent callout slot for a stat (e.g., "2 hrs saved/day") in large display type
  - [ ] **New templates:**
    - [ ] `meta_carousel_frame` (1:1, designed to be used in a 3-card series)
    - [ ] `google_728x90` leaderboard
    - [ ] `google_160x600` skyscraper
  - [ ] **Render pipeline check:** Full `render_batch()` test — 20 variants, confirm all 20 PNG files valid (not corrupt, correct dimensions)
- **Reference:** `engine/generation/template_renderer.py`, `engine/generation/templates/`

---

### G5. Video Scene Library Expansion
- **Status:** 🔄 In Progress (3 video scenes exist; needs 10+ for real coverage)
- **Owner:** Alex + Daniel
- **Why it matters:** Video is the highest-performing format per historical data. Three scenes is not enough to avoid repetition across 20 variants.
- **What's needed:**
  - [ ] Write 7 additional video scenes covering: audit prep anxiety, post-session relief, walking out on time, weekend reclaimed, voice recording in car, mid-session quick note, before/after desk state
  - [ ] Each scene needs: 5-second arc, opening frame, key action, closing frame, brand moment, negative prompts
  - [ ] Validate scenes against Veo constraints (motion complexity, faces, text in frame)
  - [ ] Add taxonomy tags to each scene so `_build_video_prompt()` matching improves
- **Reference:** `engine/generation/scene_library.py` (video scenes start with id prefix `video_`)

---

### G6. Generation Diversity Check
- **Status:** ⬜ Not Started
- **Owner:** Alex
- **Why it matters:** If 20 variants from the same brief are all minor copy permutations of the same idea, we're not exploring the creative space — we're just generating noise.
- **What's needed:**
  - [ ] Add `diversity_report()` to `VariantMatrix` — for a generated batch, report: unique hook_types, tone coverage, CTA coverage, visual_style coverage
  - [ ] Minimum diversity threshold: at least 4 distinct hook_types, 3 distinct tones, 3 distinct visual_styles in any batch of 20
  - [ ] If threshold not met: add forced-diversity fallback in `_select_diverse_variants()` — explicitly inject underrepresented dimensions
  - [ ] Log diversity report to `data/briefs/{brief_id}/diversity.json` per generation run
- **Reference:** `engine/generation/variant_matrix.py`

---

### REGRESSION STAGE

### R1. Model Validation — are the coefficients trustworthy?
- **Status:** ⬜ Not Started
- **Owner:** Aryan
- **Why it matters:** R²=0.34 on 141 observations with 30+ one-hot features is likely overfit. Before trusting coefficients to guide generation, we need to know which ones are real signal.
- **What's needed:**
  - [ ] Add holdout validation: 80/20 train/test split, report test-set R² alongside train R²
  - [ ] Add bootstrap confidence intervals for each coefficient (1000 resamples) — replace point estimates with (estimate, lower_ci, upper_ci)
  - [ ] Coefficient stability: run regression 10 times on random 80% subsamples — report coefficient variance; flag any coefficient with high variance as "unreliable"
  - [ ] Update `RegressionResult` model: add `coefficient_ci` dict and `stability_score` per feature
  - [ ] Update `PlaybookTranslator`: only translate coefficients with HIGH confidence tier (stability + CI not crossing zero)
- **Reference:** `engine/regression/model.py`, `engine/models.py` (`RegressionResult`), `engine/memory/playbook_translator.py`

---

### R2. Feature Engineering Review — are we capturing the right signals?
- **Status:** ⬜ Not Started
- **Owner:** Aryan
- **Why it matters:** The regression is only as good as the features it has to work with. If we're missing a key creative dimension (e.g., whether the ad includes a specific number, or whether there's a human face visible), we can't learn from it.
- **What's needed:**
  - [ ] Review `CreativeTaxonomy` dimensions against the known learnings in `CLAUDE.md` (question hooks, empathetic tone, UGC photography, "get to product fast") — are all of these represented as features?
  - [ ] Add missing dimensions to `CreativeTaxonomy`: `contains_specific_number` (bool), `shows_product_ui` (bool), `human_face_visible` (bool), `social_proof_type` (peer/testimonial/stat/none)
  - [ ] Add engineered features: `copy_length_bin` (short/medium/long), `days_since_first_run` (for fatigue modeling)
  - [ ] Re-tag existing 432 ads for new dimensions (batch Claude tagging)
  - [ ] Re-run regression with expanded features; compare R² before/after
- **Reference:** `engine/models.py` (`CreativeTaxonomy`), `engine/regression/model.py` (`_taxonomy_row`), `engine/analysis/analyzer.py`

---

### MEMORY STAGE

### M1. Memory → Generation Quality Test — does memory actually improve output?
- **Status:** ⬜ Not Started
- **Owner:** Alex + Aryan
- **Why it matters:** We built a sophisticated 3-layer memory system and inject `GenerationContext` into copy agents. We've never verified it helps. If it doesn't improve quality, we're paying Claude tokens for nothing. If it does, we should understand why and double down.
- **What's needed:**
  - [ ] Generate 10 variant batches with memory OFF (no context injection)
  - [ ] Generate 10 variant batches with memory ON (same briefs)
  - [ ] Blind review: rate copy quality without knowing which condition; measure approval rate difference
  - [ ] Check: does memory injection cause copy to be *too* constrained (all variants converge on the same winners)?
  - [ ] Tune `GenerationContext.to_prompt_block()` based on findings — maybe playbook rules should be "inspired by" not "copy exactly"
- **Reference:** `engine/memory/models.py` (`GenerationContext`), `engine/generation/copy_agents.py`

---

### M2. Voice Notes → Reviewer Preferences
- **Status:** ⬜ Not Started
- **Owner:** Aryan + Alex (Nate + Jackson as weekly reviewers)
- **Why it matters:** `EditorialMemory.reviewer_profiles` is the most direct signal about what Nate and Jackson actually want. Right now it's empty because there's no capture mechanism. Weekly review sessions are planned but preferences aren't being extracted.
- **What's needed:**
  - [ ] `POST /api/review/voice-note` — audio upload → Whisper transcription → store in `data/memory/voice_notes/`
  - [ ] `POST /api/review/synthesize-preferences` — runs all voice note transcripts + written review notes through Claude → extracts structured `ReviewerPreference` objects (dimension + rule + example + confidence)
  - [ ] Wire into `MemoryBuilder._build_editorial_memory()` — include reviewer_profiles in next memory build
  - [ ] Dashboard: reviewer preference cards visible in review page sidebar during approval sessions
  - [ ] Schedule: run synthesis after every review session (not per-note — batch weekly)
- **Reference:** `engine/memory/builder.py` (`_build_editorial_memory`), `engine/memory/models.py` (`ReviewerProfile`, `EditorialMemory`)

---

### M3. Memory Persistence + Reset Strategy
- **Status:** ⬜ Not Started
- **Owner:** Aryan
- **Why it matters:** Memory grows indefinitely. Old patterns may become stale (creative fatigue, seasonal shifts). We need a strategy for when to weight down or archive old memory vs keep it.
- **What's needed:**
  - [ ] Add `memory_snapshot_date` to persisted memory — when was each insight last updated?
  - [ ] Decay old statistical memory: PatternInsights older than 60 days get confidence_tier downgraded
  - [ ] Archive strategy: move patterns with <LOW confidence + >90 days old to `data/memory/archive/`
  - [ ] Add `GET /api/memory/status` endpoint — reports memory age, pattern count, confidence distribution
  - [ ] Retention policy documented in code comments
- **Reference:** `engine/memory/builder.py`, `engine/store.py` (`save_memory`, `load_memory`)

---

## P1 — Close the Feedback Loop

> These are needed to get real performance data back into the regression. Without real variant-level spend + conversion data, the regression is seeded only from existing ads (not engine-generated ones). Build these once Phase 1 creative quality is proven.

### 1. Meta Ads Write API — deploy variants programmatically
- **Status:** 🚧 Stubbed (`engine/deployment/deployer.py`)
- **Owner:** Alex + Adam (needs write-access API keys)
- **What's needed:**
  - [ ] Use raw `requests` (consistent with read path — no SDK needed)
  - [ ] `MetaDeployer.upload_asset(variant)` — POST to `/act_{id}/adimages` or `/advideos`
  - [ ] `MetaDeployer.create_ad_creative(variant)` — POST to `/act_{id}/adcreatives`
  - [ ] `MetaDeployer.create_ad(variant)` — POST to `/act_{id}/ads` with farm campaign/adset IDs
  - [ ] `MetaDeployer.pause_ad()`, `resume_ad()` — status toggle
  - [ ] Wire campaign/adset IDs from `settings.py` (farm = test budget, scale = proven winners)
  - [ ] Update `AdVariant.meta_ad_id` on successful deploy
- **Dependencies:** Adam's write-access keys; Phase 1 creative quality approved by Nate/Jackson

---

### 2. Meta Performance Tracker — pull daily metrics
- **Status:** 🚧 Stubbed (`engine/tracking/tracker.py`)
- **Owner:** Alex + Adam
- **What's needed:**
  - [ ] `MetaTracker.pull_daily_stats()` — GET `/act_{id}/insights` by `ad_id`, fields: `spend`, `impressions`, `clicks`, `actions`
  - [ ] Map `offsite_conversion.fb_pixel_custom` → `conversions` (confirmed conversion event from analysis run)
  - [ ] Create `PerformanceSnapshot` → `store.save_snapshot()`
  - [ ] Reuse exponential backoff rate limit handling from `analyzer.py`
- **Dependencies:** Deployed ads (item 1 above)

---

### 3. Scheduler — automated daily cycle
- **Status:** ⬜ Not Started
- **Owner:** Alex
- **What's needed:**
  - [ ] APScheduler inside FastAPI process — single service, no external cron
  - [ ] Run `run_daily_cycle()` at 6am PT
  - [ ] `POST /api/admin/run-cycle` for manual trigger
  - [ ] Log cycle run summaries to `data/cycles/`
- **Dependencies:** Items 1 + 2

---

### 4. Slack Webhook — real notifications
- **Status:** 🚧 Stubbed (`engine/notifications.py`)
- **Owner:** Aryan
- **What's needed:**
  - [ ] Create Slack app + incoming webhook
  - [ ] Set `SLACK_WEBHOOK_URL` in `.env`
  - [ ] Implement `SlackNotifier._send()` — POST JSON payload to webhook
  - [ ] Test all message types: daily digest, kill alert, scale alert, deploy confirmation
- **Dependencies:** None (standalone, can do anytime)

---

### 5. Bulk Creative Export / Download
- **Status:** ⬜ Not Started
- **Owner:** Alex
- **Why:** Bridge gap — Adam/Matt can manually upload approved creatives while programmatic deploy is being built
- **What's needed:**
  - [ ] `GET /api/variants/export?status=approved` → stream ZIP with images/videos + CSV of copy
  - [ ] Organize by format in ZIP: `meta_feed/`, `meta_story/`, `google_display/`
- **Dependencies:** None

---

## P2 — Automation & Scale

*Build after Phase 2 (real data flowing)*

### Performance Dashboard
- **Status:** ⬜ Not Started — `dashboard/frontend/pages/performance.html`
- Per-variant table: thumbnail, headline, spend, CpFN, days running, verdict badge
- Trend sparklines (Chart.js)
- One-click kill/scale → `POST /api/decisions/act`

### Regression Insights Dashboard
- **Status:** ⬜ Not Started — `dashboard/frontend/pages/insights.html`
- Coefficient bar chart (green/red by impact direction)
- Fatigue section (features degrading over rolling window)
- Playbook rule cards with confidence tiers

### Budget Pacing & Spend Tracking
- Daily/weekly spend vs $15-20K/mo budget
- Alert: run rate >110% or <70% → Slack alert
- Requires: tracker running (P1 item 2)

### Google Conversion Tag Fix
- Known issue: 2 in-platform vs 15 Metabase UTMs
- Likely fix: server-side Google Measurement Protocol, bypass client-side tag broken by 2FA
- Owner: Aryan + Jenna

### Attribution Deduplication Model
- Reconcile Meta + Google + discovery survey → single deduplicated conversion count
- Ground truth: discovery survey as canonical, use as calibration
- Requires: Google tag fix

### Google Ads Write API
- Deploy approved display ads (300x250, 728x90, 160x600) to Google Display Network
- `GoogleDeployer` already stubbed in `deployer.py`
- Requires: Jenna, Google Ads API developer token, conversion tracking fixed

### Meta Lead Form Integration
- Pull lead submissions → route to Chris for SDR follow-up
- Track lead → signup → first note completion funnel per ad
- Owner: Alex + Adam + Chris

---

## P3 — Future Capture

### LoRA Model Integration *(Daniel's workstream)*
- Fine-tune image model on JotPsych brand aesthetics
- Collect training images → train on Stable Diffusion → `LoRAGenerator` backend in `generator.py`
- A/B quality test: LoRA vs Gemini vs Template Renderer

### UGC-Style Video *(non-Veo)*
- Talking-head / screen-recording style — historically highest performing format
- Options: HeyGen AI avatar, voice clone, or source real clinician UGC
- Can't fully automate yet; requires human or avatar model

### Competitive Intelligence Scraper
- Monitor Facebook Ad Library for mental health / EHR competitors
- Tag with taxonomy → feed `MarketMemory.competitive_observations`
- Requires: Meta Ad Library API (public), competitor account IDs

### Voice Note Intake *(team → ideas)*
- Record voice memo → Whisper → `IntakeParser.parse()` → brief → generation
- `POST /api/intake/voice`
- Nice ergonomic improvement; text intake already works

### LinkedIn Ads
- LinkedIn Campaign Manager API
- Activate when Meta CpFN plateaus or LinkedIn gets budget allocation

### Proper Database
- Migrate from flat JSON to PostgreSQL (Supabase) + SQLAlchemy
- Trigger: >10K variants or concurrent write pressure
- `store.py` keeps same interface, swaps backend

### Campaign Structure Automation
- Auto-create farm/scale campaign structure programmatically
- Risk: misconfiguration is expensive. Only after 3+ months stable manual operation.

---

## ✅ Completed (Reference)

| Feature | Completed | Notes |
|---------|-----------|-------|
| Intake parser (idea → brief via Claude) | 2026-03-25 | `engine/intake/parser.py` |
| Copy agents v1 (headline/body/CTA) | 2026-03-25 | `engine/generation/copy_agents.py` |
| Quality filter (23 AI-tells, 12 generic phrases) | 2026-03-25 | `engine/generation/quality_filter.py` |
| Variant matrix (regression-scored, explore/exploit 80/20) | 2026-03-25–27 | `engine/generation/variant_matrix.py` |
| Meta ads read export (432 ads, $304K spend) | 2026-03-26 | `engine/analysis/analyzer.py` |
| Claude taxonomy tagging pipeline | 2026-03-26 | Batches of 15, all 432 tagged |
| Portfolio analysis + playbook generation | 2026-03-26 | `data/existing_creative/playbook.md` |
| Regression model (WLS, decay weights, rolling window, interaction terms) | 2026-03-25–27 | `engine/regression/model.py` |
| Gemini image generation + scene library (20 scenes) | 2026-03-26 | `engine/generation/generator.py`, `scene_library.py` |
| Veo video generation (code path) | 2026-03-26 | `engine/generation/generator.py` |
| Brand kit integration (colors, typography, voice) | 2026-03-26 | `engine/brand.py` |
| Template renderer (HTML → PNG via Playwright) | 2026-03-27 | `engine/generation/template_renderer.py` |
| Review pipeline + approval/rejection feedback loop | 2026-03-26 | `engine/review/reviewer.py` |
| Review gallery dashboard UI | 2026-03-26 | `dashboard/frontend/pages/review.html` |
| Decision engine (scale/kill/wait logic) | 2026-03-25 | `engine/decisions/engine.py` |
| Three-layer creative memory (statistical/editorial/market) | 2026-03-27 | `engine/memory/` |
| Playbook translator (coefficients → human rules) | 2026-03-27 | `engine/memory/playbook_translator.py` |
| Orchestrator + full CLI | 2026-03-25–27 | `engine/orchestrator.py` |
| Dashboard API (FastAPI, 20+ endpoints) | 2026-03-25–27 | `dashboard/api/app.py` |
| Stale asset healing (startup + manual endpoint) | 2026-03-26 | `dashboard/api/app.py` |

---

## Open Questions

1. **Deploy API keys:** Adam sending Meta write-access keys — timeline? Which ad account?
2. **Campaign/adset IDs:** What are the exact IDs for farm campaign (test budget) and scale campaign to wire into deployer config?
3. **Conversion event name:** Analysis confirmed `offsite_conversion.fb_pixel_custom`. Is this definitively first note completion? What's the event name post-2FA fix?
4. **Kill/scale authority:** Auto-kill when `DecisionVerdict.KILL`, or surface recommendation for human approval first? Current leaning: human-in-the-loop until we trust the model.
5. **Google workstream:** Display network re-activation, or non-brand search? Jenna's current focus?
6. **Review cadence:** When is the first Nate + Jackson review session? This is the trigger for starting to capture voice note preferences (M2).
7. **Bulk export:** Does Adam/Matt want ZIP download of approved creatives as manual upload workaround while deploy API is being built?

---

*Last updated: 2026-03-26 — Aryan*
*Next review: Start of each sprint / major session*
