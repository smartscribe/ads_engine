# Ads Engine — Changelog

All notable changes to this project are documented here.
Entries are listed in reverse chronological order (newest first).

---

## Format

Each entry includes:
- **Date**
- **Who** (name or initials)
- **What changed** — file(s) touched
- **Why** — the reason / intent
- **Notes** — anything relevant for the writeup (decisions made, things tried, things rejected)

---

## Log

### 2026-03-26 — Aryan
**Review dashboard rebuilt: Tinder-style focus mode, structured chip feedback, scoreboard + learnings views**

- `engine/models.py` — Added `ReviewFeedback` Pydantic model; extended `AdVariant` with `review_chips`, `review_duration_ms`, `asset_status`, `template_id`, `template_color_scheme` fields for structured feedback capture and three-tier asset rendering
- `engine/review/chips.py` (**new**) — Chip taxonomy: 12 rejection chips and 5 approval chips, each mapping to a `CreativeTaxonomy` dimension and an `implied_preferences` dict for zero-parse structured signal
- `engine/review/reviewer.py` — Added `submit_review()` (handles chips + duration, backward-compat with `review_notes`), `get_structured_feedback()` (chip frequency aggregates), `get_reviewer_impact()` (approval rate, chip coverage, avg review time per reviewer)
- `engine/generation/template_renderer.py` — Added `render_to_html()` method returning fully-substituted HTML with HTTP `/brand/` paths instead of `file://` — enables iframe-based template preview without a screenshot step
- `dashboard/api/app.py` — Added 5 new endpoints: `POST /api/review/submit`, `GET /api/template-preview/{id}`, `GET /api/feedback-chips`, `GET /api/scoreboard`, `GET /api/learnings`; updated `GET /api/review` to resolve `asset_status` per variant; added `/brand/` static mount for font/logo serving
- `dashboard/frontend/pages/review.html` (**full rewrite**) — Three-view SPA (hash routing): Review Queue, Scoreboard, Learnings. Review Queue has Tinder/Gallery mode toggle. Tinder mode: single-card focus, approve/reject in one tap or keystroke (←/→), verdict recorded instantly, chip panel slides up as optional enrichment, `review_duration_ms` tracked per card, three-tier asset rendering (PNG → iframe template → text-only fallback). Gallery mode: multi-select grid, chip modal on verdict. Scoreboard: CpFN leaderboard with trend arrows and sortable columns. Learnings: playbook rules, chip aggregate bars, reviewer impact stats.

- Core design principle: every review interaction under 3 seconds. Chips are never blocking — verdict records instantly, chips are bonus signal.
- Kept vanilla JS + single-file approach (no React, no build step) to match the existing codebase style.
- Old `POST /api/review/approve` and `POST /api/review/reject` endpoints preserved for backward compat; new `POST /api/review/submit` is the primary path from the rebuilt UI.

---

### 2026-03-26 — Aryan
**Lock generation pipeline to v2 multi-agent + HTML template rendering as the only path**

- `engine/generation/generator.py` — changed `generate()` default from `use_v2=False` to `use_v2=True`
- `engine/orchestrator.py` — `submit_idea()` now always calls `generate_with_templates(use_v2=True)`; removed the v1 fallback branch and `--v2` CLI flag (always on now). `generate_from_playbook()` likewise uses `generate_with_templates()`.
- `dashboard/api/app.py` — `/api/intake` endpoint updated to call `generate_with_templates(use_v2=True)` instead of `generate()` (which was using v1 + AI images)
- `CLAUDE.md` — added Roadmap section documenting the three-phase generation approach: Phase 1 (templates, current), Phase 2 (AI image gen integration), Phase 3 (video at scale)

Rationale: v2 (HeadlineAgent + BodyCopyAgent + CTAAgent + VariantMatrix) and template
rendering are now the only production path. v1 (single Claude call) and AI image gen
(Gemini/Veo) remain in the codebase for future use but are not called anywhere by default.

---

### 2026-03-27 — Aryan (session 8)
**Playwright template rendering pipeline — Phase 1 of phased creative generation**

Built the full Playwright-as-Python-library rendering pipeline for deterministic,
pixel-perfect ad image/video generation. No AI image generation — full control
over every pixel. This is the "caveman approach" baseline that feeds clean data
to the regression model before layering in Gemini image gen in Phase 2.

New files:
- `engine/generation/templates/feed_1080x1080/headline_hero.html` — Big headline, brand gradient, strong CTA
- `engine/generation/templates/feed_1080x1080/split_screen.html` — Two-column layout with brand cube pattern
- `engine/generation/templates/feed_1080x1080/stat_callout.html` — Giant stat number with supporting copy
- `engine/generation/templates/feed_1080x1080/testimonial.html` — Quote format with attribution line
- `engine/generation/templates/story_1080x1920/full_bleed.html` — Full-screen with CSS fade-in/slide animations
- `engine/generation/templates/story_1080x1920/swipe_up.html` — CTA-focused with bouncing arrow animation
- `engine/generation/templates/display_1200x628/responsive.html` — Google Display responsive format
- `engine/generation/template_selector.py` — Maps taxonomy tags + regression coefficients → template + color scheme
- `engine/generation/video_renderer.py` — CSS animation → MP4 via Playwright recordVideo + ffmpeg

Modified files:
- `engine/generation/template_renderer.py` — Rewritten: subdirectory template support, extended context variables (stat_number, attribution, badge_text), proper async handling (thread pool fallback for nested event loops), accent/logomark color scheme support
- `engine/generation/generator.py` — Added `generate_assets_from_selector()` (per-variant template selection via TemplateSelector + regression), updated `generate_with_templates()` with `use_selector` flag and memory/generation_context params
- `engine/orchestrator.py` — Added `submit_idea_templates()` method and `idea-templates` CLI command
- `requirements.txt` — Added ffmpeg system dependency note for video rendering

Key decisions:
- Playwright as Python library (not MCP server) — right architecture for automated pipeline
- Phase 1 is template-only to get clean regression signal before introducing AI image gen
- Story templates have CSS @keyframes animations captured via Playwright recordVideo → ffmpeg MP4
- TemplateSelector uses taxonomy dimensions (hook_type, subject_matter, text_density) to pick layout, regression coefficients to bias color scheme toward what lowers CpFN
- Templates support 4 color schemes (light/dark/warm/accent) mapped from taxonomy color_mood
- Each variant gets its own template+scheme via selector — not one-size-fits-all

---

### 2026-03-26 — Aryan
**Rewrote ROADMAP.md — reframed priorities around creative excellence loop**

- `ROADMAP.md` — major restructure to reflect current sprint focus: make regress → memory → analysis → generation excellent before closing the full deploy/track loop. Reorganized into Phase 1 (creative quality), Phase 2 (feedback loop), Phase 3 (automation). P0 now covers 13 specific tasks across Analysis (A1–A4), Generation (G1–G6), Regression (R1–R2), and Memory (M1–M3) stages. Deploy/track items moved to P1. Added quality-first framing, per-stage rationale, and concrete audit steps.

---

### 2026-03-26 — Aryan
**Created ROADMAP.md — full feature backlog with prioritization**

- `ROADMAP.md` — new document covering all open tasks, prioritized P0→P3, with status, owner, sub-tasks, and dependency tracking. Also includes a completed-features reference table and open questions section.
- Why: needed a single doc the whole team references before each session, so nothing gets lost between chats and priorities stay clear.

---

### 2026-03-27 — Aryan (session 7, part 2)
**Three-layer Creative Memory Architecture — compounding knowledge system**

Major refactor to implement the proposed three-layer memory architecture:

New modules:
- `engine/memory/models.py` — Complete dataclass-based model hierarchy:
  - `StatisticalMemory`: PatternInsight (with trend, cycles_significant, confidence_tier), coefficient_history, fatiguing_patterns, interaction_insights
  - `EditorialMemory`: ApprovalCluster (grouped by taxonomy signature), RejectionRule (generalized from multiple rejections), ReviewerProfile
  - `MarketMemory`: CombinationStats, least_tested_combinations, platform_modifiers, competitive_observations
  - `GenerationContext`: Structured prompt injection format with `to_prompt_block()` method
- `engine/memory/builder.py` — `MemoryBuilder` class that assembles memory from all sources:
  - `_build_statistical_memory()`: Converts regression to PatternInsights with real ad examples, trend detection from coefficient history
  - `_build_editorial_memory()`: Clusters approvals by taxonomy signature, extracts generalized rejection rules
  - `_build_market_memory()`: Tracks combination deployment counts for exploration
  - `_detect_trend()`: Compares recent vs historical coefficients
  - `build_generation_context()`: Creates prompt-ready GenerationContext

Modified modules:
- `engine/orchestrator.py`:
  - Added `memory_builder` instance variable
  - `_get_generation_context()` now returns `GenerationContext` (structured) instead of raw memory
  - `run_daily_cycle()` builds memory using MemoryBuilder after regression
- `engine/generation/generator.py` — `generate()` and `generate_copy_v2()` accept `generation_context` parameter
- `engine/generation/copy_agents.py` — HeadlineAgent and BodyCopyAgent inject `context.to_prompt_block()` into system prompts
- `engine/store.py` — Added `load_memory_v2()` and `_deserialize_memory_v2()` for v2 format

Key improvements over v1:
1. **PatternInsight is unified** — trend, cycles_significant, confidence_tier all in one object
2. **Coefficient history** — tracks coefficients over multiple runs for real trend detection
3. **ApprovalCluster** — groups by taxonomy signature with representative ad, prevents redundancy
4. **RejectionRule** — generalizes from multiple rejections ("Don't combine playful + urgency")
5. **MarketMemory** — explicit tracking for explore/exploit
6. **GenerationContext** — structured injection format with `to_prompt_block()`

The memory now compounds: cycle 1 has no data, cycle 5 identifies winning patterns, cycle 15 detects interaction effects and fatigue patterns. The generator gets progressively smarter.

---

### 2026-03-27 — Aryan (session 7, part 1)
**Regression-to-Generation Loop Enhancements — six major features to close the gap between raw coefficients and smarter generation**

New modules:
- `engine/memory/__init__.py` — Memory system package init
- `engine/memory/creative_memory.py` — `CreativeMemoryManager` class handling persistent knowledge accumulation. Structures four knowledge categories: winning patterns (top 50 approved/graduated variants ranked by CpFN), reviewer preferences (synthesized rules from approval/rejection patterns per reviewer per dimension), fatigue alerts (features whose rolling coefficient degraded vs all-time), and competitive intel (manual notes). `to_agent_context()` serializes memory into structured markdown for copy agent system prompts.
- `engine/memory/playbook_translator.py` — `PlaybookTranslator` converts raw feature coefficients into actionable `PlaybookRule` objects with natural language instructions, good/bad examples from real variants. Uses Claude to translate "hook_type_statistic" into "Lead headlines with a specific number — '2 hours of charting saved' beats 'Save time on charting'".
- `engine/generation/template_renderer.py` — `TemplateRenderer` renders HTML/CSS templates to PNG using Playwright. Supports `meta_feed` (1080x1080), `meta_story` (1080x1920), `google_300x250`, `google_728x90`, `google_160x600`. Four color schemes (light, dark, warm, accent) using brand kit colors. `render_batch()` for efficient multi-variant rendering.
- `engine/generation/templates/` — Three HTML templates with inline CSS using brand fonts (Archivo/Inter) and colors (midnight, sunset glow, warm light, etc.). Responsive text handling with line-clamp, gradient accent bars, proper logo placement.

Modified modules:
- `engine/models.py`:
  - Extended `RegressionResult` with `window_days` (rolling window size) and `sample_weights_used` (decay weighting flag)
  - Added 6 new models: `WinningPattern`, `ReviewerPreference`, `FatigueAlert`, `CompetitiveIntel`, `PlaybookRule`, `CreativeMemory`
- `engine/store.py`:
  - Added `memory_dir` (data/memory/) with `save_memory()` and `load_memory()` for persistent CreativeMemory
  - Added `get_recent_deployed_taxonomies(n_cycles)` for explore/exploit scoring
- `engine/regression/model.py`:
  - Added `_compute_decay_weights()` — exponential decay with configurable half-life (default 30 days)
  - Rewrote `run()` to support WLS (weighted least squares) with decay, rolling window filtering, and interaction terms
  - Added `add_interaction_terms()` — generates boolean×categorical products, caps at 20 by target correlation
  - Added `run_rolling(window_days=30)` — separate OLS on recent data for fatigue detection
  - `build_dataset()` now includes `last_activity_date` column for temporal weighting
- `engine/generation/variant_matrix.py`:
  - Replaced simple diversity selection with explore/exploit framework: 80% exploit slots (best predicted scores with fatigue penalty), 20% explore slots (maximize novel under-tested features)
  - Added `_compute_fatigue_penalty()` — 15% penalty per cycle for heavily-used features
  - Added `_compute_exploration_score()` — counts features with <3 total deployments
  - Output now includes `strategy` ("exploit"/"explore") and `fatigue_penalty` fields
  - `_predict_score()` handles interaction term coefficients (e.g., `uses_number_x_hook_type_statistic`)
- `engine/generation/copy_agents.py`:
  - `HeadlineAgent.generate()` and `BodyCopyAgent.generate()` now accept optional `memory` parameter
  - When memory provided, injects full creative memory context (playbook rules with examples, fatigue warnings, winning patterns, reviewer preferences) instead of raw feature names
- `engine/generation/generator.py`:
  - Added `generate_assets_from_template()` — renders variants using HTML templates instead of AI
  - Added `generate_with_templates()` — full pipeline using template rendering for static ads
  - `generate()` and `generate_copy_v2()` now accept `memory` parameter
- `engine/orchestrator.py`:
  - Added `memory_manager` and `playbook_translator` instance variables
  - Rewrote `_get_generation_context()` to build and return `CreativeMemory` object
  - Updated `submit_idea()` and `generate_from_playbook()` to pass memory to generator
  - Enhanced `run_daily_cycle()` to: run WLS regression with decay, run 30-day rolling regression, detect fatigue alerts, translate playbook rules, save updated memory

Dependencies:
- `requirements.txt` — added `playwright>=1.40.0`

Why: The regression model produced coefficients, but the generator couldn't act on them effectively. "hook_type_statistic is good" doesn't help a copywriter — "Lead with a specific number in the headline: '2 hours of charting' beats 'Save time'" does. The six enhancements create a true learning loop: temporal decay ensures recent data matters more, rolling regression catches fatigue before it hurts, interaction terms find powerful combinations, explore/exploit prevents creative stagnation, playbook translation makes insights actionable, and HTML templates enable rapid brand-consistent iteration without AI slop.

Key design decisions:
- Memory is a single growing JSON document, not per-variant — simpler persistence, single source of truth
- Fatigue penalty is additive to predicted CpFN (higher = worse) rather than multiplicative — more interpretable
- Explore slots use under-tested feature count, not random — ensures systematic coverage
- Templates use Playwright async but expose sync interface — simpler integration, handles event loop internally
- Playbook translation runs once per regression cycle, not per generation — Claude calls are expensive

---

### 2026-03-26 — Aryan (session 6)
**Brand kit integration — colors, typography, voice, and product identity wired into all generators**

New modules:
- `engine/brand.py` — Single source of truth for JotPsych brand identity. Extracted from Brand Guidelines v1 2026 PDF. Contains: 6-color palette with hex codes (midnight #1C1E85, sunset glow #FD96C9, warm light #FFF2F5, deep night #1E125E, daylight #FFF3C4, afterglow #813FE8), typography spec (Archivo for headings, Inter for body), brand voice guidelines, product description, visual style direction, color usage rules, and logo asset paths. Exposes `get_brand_context_for_image_prompt()` and `get_brand_context_for_copy_prompt()` helper functions.

Modified modules:
- `engine/generation/generator.py` — `_build_image_prompt()` and `_build_video_prompt()` now inject brand color direction and visual style into every Gemini/Veo prompt (warm amber/cream/soft-blue color grading, lived-in environments, no cold corporate aesthetics). Updated `COPY_GENERATION_PROMPT` with full product description, brand voice rules, and expanded banned words list.
- `engine/generation/copy_agents.py` — `JOTPSYCH_VOICE` expanded from 1 sentence to full brand tone guidelines (warm colleague, empathetic, specific, no pressure tactics, explicit banned words). `JOTPSYCH_VALUE_PROPS` expanded from 4 to 7 bullet points including audit-ready docs, CPT/ICD codes, full presence with patients. Both now import from `engine.brand`.

Asset organization:
- Unzipped `JotPsych Brand.zip` into `brand/` with clean structure: `logos/png/`, `logos/svg/`, `fonts/`, `guidelines/`
- Deleted original ZIP
- 8 logo variants (primary/secondary/logomark × dark/light), 4 font files (Archivo, Inter variable fonts)

Why: Ad creative was generic — no brand identity in prompts meant images had random color grading and copy used generic AI-marketing language. Now every generated image inherits the JotPsych color palette (deep blues, warm pinks, cream accents) and every copy variant follows the brand voice (specific, empathetic, no buzzwords).

---

### 2026-03-26 — Aryan (session 5)
**Fix stale asset paths + graceful placeholder UI for missing images**

- `dashboard/api/app.py` — Added `_heal_stale_asset_paths()` that scans all variant JSONs and fixes paths pointing to deleted files by switching them to `.placeholder`. Runs automatically on server startup via `@app.on_event("startup")`. Also exposed as `POST /api/assets/heal` for manual trigger.
- `dashboard/frontend/pages/review.html` — Rewrote `renderAsset()` to handle three cases: valid image/video (renders normally with `onerror` fallback), placeholder path (shows styled SVG icon + "pending generation" text), and 404 on load (via `showAssetPlaceholder()` function triggered by `onerror`). No more broken image icons.

Why: After deleting 19 corrupt 356-byte PNGs in session 4, the variant JSON files still referenced the old `.png` paths → 404 → broken image icon in the review gallery. The startup heal catches this automatically, and the frontend `onerror` is a safety net for any future cases.

---

### 2026-03-26 — Aryan (session 4)
**Fix broken images + improve ad creative quality with scene library**

New modules:
- `engine/generation/scene_library.py` — Library of 20 detailed cinematic scene descriptions organized by taxonomy (message_type, hook_type, subject_matter, tone). Each scene includes: specific setting, time of day, lighting, props, body language, camera angle, and explicit negative prompts. Scenes cover pain points (late night documentation, weekend catchup, session gap stress), value propositions (relief moment, walking out early, family dinner), social proof (peer recommendation, conference conversation), product focus (phone recording, notes notification), comparison (two desks, calendar freedom), and conceptual (morning commute, evening reading, audit prep). Three video-specific scenes for 5-second Veo moments.

Modified modules:
- `engine/generation/generator.py`:
  - Rewrote `_generate_image()` with comprehensive validation: MIME type check (image/png or image/jpeg), file size check (>10KB), PNG/JPEG magic byte validation, auto-retry with simplified prompt on failure
  - Added `_retry_image_if_needed()` for single-retry logic with fallback scene
  - Added `_build_image_prompt()` — constructs detailed prompts from scene library based on variant taxonomy
  - Rewrote `_generate_video()` with validation: file size check (>100KB), timeout handling (5 min max), auto-retry
  - Added `_retry_video_if_needed()` and `_build_video_prompt()` for video generation
  - Added `force_regenerate` param to `generate_assets()` — deletes corrupt files and regenerates
  - Fixed model name to `gemini-3.1-flash-image-preview` (was incorrectly changed to `gemini-2.0-flash-exp`)
- `engine/orchestrator.py`:
  - Added `regenerate_assets(brief_id)` method — finds variants with missing/corrupt assets and regenerates
  - Added `regenerate-assets [brief_id]` CLI command

Cleanup:
- Deleted 19 corrupt 356-byte PNG files from `data/creatives/`

Why: All generated images were 356 bytes of corrupt data because `_generate_image` wasn't validating API responses. Also, the generic `IMAGE_PROMPT_TEMPLATE` produced AI-obvious images with unrealistic details (e.g., random "6:00" on a TV). The new scene library provides cinematically detailed, realistic scene descriptions that guide Gemini to produce believable clinical settings with appropriate props, lighting, and human moments.

Notes:
- Scene matching uses priority scoring: exact subject_matter match (10 pts), message_type match (5 pts), hook_type match (3 pts), tone match (2 pts)
- Video scenes are separate from image scenes (id prefix "video_")
- All scenes include comprehensive negative prompts to avoid AI artifacts
- Regeneration uses proper retry logic with exponential backoff and quota-aware error handling

---

### 2026-03-26 — Aryan (session 3)
**Review feedback loop — approvals and rejections train the generator**

- Added `get_approval_feedback()` to `engine/review/reviewer.py` — collects approved variants with actual copy + taxonomy, feeds into generator as positive examples
- Enriched `get_rejection_feedback()` — now includes headline, body, CTA, and taxonomy fields (not just raw notes text) so generators learn what was structurally wrong
- Threaded `approval_feedback` through full pipeline: orchestrator `_get_generation_context()` → `generator.generate()` → `generate_copy_v2()` → copy agents
- Updated HeadlineAgent and BodyCopyAgent prompts to include approved ads as "generate more like these" examples
- Rebuilt `review.html` dashboard: reviewer dropdown (Nate/Jackson/Aryan/Alex/Daniel), approval notes modal, review count stats bar (pending/approved/rejected), toast notifications, relative API URLs (no more hardcoded localhost), 1:1 aspect ratio for ad cards, video muted by default
- Added `GET /api/review/history` endpoint for review trail
- Updated approve API to accept optional notes

---

### 2026-03-26 — Aryan (session 2)
**Automated playbook-to-ads generation loop with Gemini visuals**

- Added `extract_briefs_from_playbook()` to `engine/analysis/analyzer.py` — reads the playbook markdown, sends to Claude to extract structured `CreativeBrief` objects from the "Creative Briefs for Next Batch" section
- Added `generate_from_playbook()` and `_get_generation_context()` to `engine/orchestrator.py` — reads playbook, extracts briefs, generates ads using v2 pipeline (sub-agents + quality filter + regression-scored variant matrix + Gemini images + Veo video), all without human intervention
- Fixed v2 param passthrough bug: `submit_idea()` computed `top_patterns` and `rejection_feedback` but never passed them to the generator. Now `generate()` accepts and forwards these params
- Added `generate` and `full-cycle` CLI commands; `full-cycle` chains export → analyze → generate in one invocation
- Added `POST /api/analyze/generate` endpoint to dashboard API
- Fixed `CopyQualityFilter.check_body()` — was rejecting all body copy at 125-char limit (above-fold optimal), but Meta allows ~2200 chars. Removed hard char limit for body, kept AI-tell and generic phrase checks

Test results: Generated 54 ad variants across 5 playbook briefs (39 images via Gemini, 27 videos via Veo, 12 placeholders). All in draft status, ready for review.

---

### 2026-03-26 — Aryan
**End-to-end pipeline test: export → analyze → playbook → regression**

- Fixed `ExistingAd` Pydantic ID bug (passing `id=None` instead of omitting the field for new records)
- Fixed Meta creative data extraction: most ads store copy in `asset_feed_spec.bodies/titles`, not `creative.title/body` — updated `_enrich_creative_batched()` to fetch and promote `asset_feed_spec` content, lifting headline coverage from 42 → 422 of 432 ads
- Fixed URL encoding issue in batch creative fetch — Meta's `ids` multi-get endpoint doesn't support `creative.fields()` expansion; switched to individual per-ad urllib requests
- Added rate limit retry logic (`_paginate_raw`) with exponential backoff for Meta API throttling
- Fixed indentation bug in `_tag_batch` None-defaulting block
- Added `import urllib.error` for HTTP error handling

Test results:
- Exported 432 ads, 144 with conversions, $304K total spend
- Tagged all 432 with CreativeTaxonomy (10 Claude batches of 15 ads each)
- Portfolio analysis completed (5 top patterns, 5 worst, 6 untested combos, 5 briefs)
- Playbook saved to `data/existing_creative/playbook.md` (29,168 chars)
- Regression seeded: R²=0.34, 141 observations

Key learnings from first run:
- Question hooks + empathetic tone + warm earth + UGC photography = $17-38/conv (best)
- Education messaging + text-heavy + brand primary = $0 conversions despite $4K spend (worst)
- "Learn more" CTA dominates; "try free" consistently underperforms

---

### 2026-03-25 — Aryan (session 2)
**Meta ads analysis pipeline + enhanced generation engine**

New modules:
- `engine/analysis/analyzer.py` — `MetaAdsExporter` (Graph API paginated export of all 432 ads with creative + performance data), `CreativeAnalyzer` (Claude taxonomy tagging in batches of 15, portfolio pattern analysis, markdown playbook generation)
- `engine/generation/copy_agents.py` — `HeadlineAgent` (40-char Meta headlines), `BodyCopyAgent` (125-char primary text), `CTAAgent` (20-char button text), each with rejection feedback integration and regression-informed prompts
- `engine/generation/quality_filter.py` — `CopyQualityFilter` with 23 AI-tell detections, 12 generic phrase detections, char limit enforcement
- `engine/generation/variant_matrix.py` — `VariantMatrix` with regression-scored combinatorial selection + diversity constraints

Modified modules:
- `engine/models.py` — added `ExistingAd` model for imported Meta/Google ads
- `engine/store.py` — added `existing_creative/` directory and CRUD for `ExistingAd` (save, get, list, find_by_meta_id, get_with_taxonomy)
- `engine/regression/model.py` — extended `build_dataset()` to include existing imported ads; extracted `_taxonomy_row()` helper; made `min_observations` configurable (default 10, was hardcoded 20)
- `engine/generation/generator.py` — added `generate_copy_v2()` orchestrating sub-agents + quality filter + variant matrix; `generate()` now accepts `use_v2` flag
- `engine/orchestrator.py` — added `export_meta_ads()`, `analyze_existing_ads()` methods; CLI now supports `export`, `analyze` commands and `--v2` flag on `idea`
- `dashboard/api/app.py` — added 7 endpoints: `POST /api/analyze/export`, `GET /api/analyze/status`, `POST /api/analyze/tag`, `POST /api/analyze/playbook`, `GET /api/analyze/playbook`, `GET /api/existing-ads`, `GET /api/feedback`
- `.env` — set `META_AD_ACCOUNT_ID=act_1582817295627677`
- `requirements.txt` — uncommented `requests>=2.31.0`

Why: To close the analysis→generation loop. The engine can now export all existing Meta ads, tag them with the MECE creative taxonomy via Claude, identify what patterns drive low CpFN, seed the regression model with 432 real ads, and generate new ad copy using specialized sub-agents informed by those insights.

Notes:
- Meta API confirmed working: 432 ads (381 active, 51 paused), 18 campaigns, performance data includes `offsite_conversion.fb_pixel_custom` as conversion event
- Decided against `facebook-business` SDK; raw `requests` against Graph API is simpler and already working
- Quality filter catches "revolutionize", "leverage", "streamline" etc. to enforce "no AI slop" constraint
- Variant matrix falls back to diverse random selection when no regression data exists yet

---

### 2026-03-25 — Aryan
**Initial codebase review + orientation**
- Files reviewed: all of `engine/`, `dashboard/`, `config/`, `brief.html`, `CLAUDE.md`
- Established full understanding of pipeline architecture: intake → generation → review → deploy → track → decide → regress
- Confirmed storage is flat JSON files under `data/` (no database yet)
- Identified open workstreams: asset generation (Alex), Meta/Google API integration (stubs), Slack webhook, scheduler

---

<!-- Add new entries above this line -->
