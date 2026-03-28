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

### 2026-03-28 — Cursor Cloud Agent
**Development environment setup**

- Created `AGENTS.md` with Cursor Cloud specific instructions for future agents
- Verified full dev environment: Python 3.12, pip dependencies, Playwright Chromium
- Confirmed FastAPI server starts cleanly with `uvicorn dashboard.api.app:app --reload`
- Tested API endpoints (`/api/review`, `/api/performance`, `/api/variants`, `/api/review/submit`) and dashboard UI

---

### 2026-03-28 — Aryan
**ROADMAP.md rewritten as step-by-step agent implementation guide**

- `ROADMAP.md` — Full rewrite. Previous version tracked P0 completion status for the creative excellence loop. New version is an exhaustive step-by-step guide an agent can follow to finish everything remaining. Includes: architecture quick reference, current state summary table (26 subsystems with exact status), 5 priority tiers (P0 bugs → P4 future), 16 detailed tasks each with exact steps/files/code/acceptance criteria, recommended execution order with time estimates, and comprehensive completed features reference table. Based on full codebase audit: identified concept SSE endpoint ImportError (P0.1), Slack webhook not wired (P1.1), 3 missing dashboard pages (performance, insights, bulk export), scheduler not started, Google deployer/tracker stubbed, and AI image generation roadmap.

---

### 2026-03-28 — Aryan
**Human-centric hypothesis loop: feedback → extract → generate → track → report**

- `engine/models.py` — Added `hypothesis_id` to `AdVariant` for linking variants to hypotheses. Expanded `CreativeHypothesis` with provenance fields (`source`, `source_context`), direct performance tracking (`variant_ids`, `total_spend`, `treatment_cpfn`, `baseline_cpfn`, `lift_pct`), and `human_summary` for plain English status
- `engine/store.py` — Added `get_variants_by_hypothesis()` helper; fixed missing `date` import in `load_hypotheses`
- `engine/tracking/hypothesis_extractor.py` — New file. Claude-powered extraction of testable claims from natural language. Auto-maps freeform text to MECE taxonomy features so humans never need to know feature codes. Includes human-readable feature labels
- `engine/tracking/hypothesis_tracker.py` — Added direct A/B performance tracking (`update_performance`) comparing hypothesis variant CpFN against baseline. Added `generate_human_summary` for Claude-written plain English status. Added `get_hypothesis_performance` endpoint helper. Kept regression-based evaluation as secondary signal
- `engine/orchestrator.py` — Added `test_hypothesis()` method that generates ads to test a hypothesis via the standard intake pipeline, tags variants with `hypothesis_id`. Expanded daily cycle to update hypothesis performance and generate summaries
- `engine/notifications.py` — Enriched `notify_hypothesis_update` with spend/CpFN/lift data and "promising" status. Added `notify_hypothesis_created` for when new hypotheses spawn ad generation
- `dashboard/api/app.py` — Four new endpoints: `POST /api/hypotheses/extract` (Claude extraction), `POST /api/hypotheses/confirm` (create + optionally generate), `POST /api/hypotheses/{id}/test` (trigger generation), `GET /api/hypotheses/{id}/performance` (direct A/B data). Modified `POST /api/review/submit` and `POST /api/review/monologue` to auto-extract hypothesis candidates from freeform feedback
- `dashboard/frontend/pages/hypotheses.html` — New page. "What do you want to test?" input with Claude extraction, active hypothesis cards with metrics/gauge/summary, resolved section. Matches existing dark theme
- `dashboard/frontend/pages/review.html` — Added hypothesis suggestion modal that appears after freeform review feedback. Added "Hypotheses" nav tab
- `dashboard/frontend/pages/portfolio.html` — Added "Hypotheses" nav tab
- Design principle: zero taxonomy knowledge required from the human. They say "I think urgency works better" and the system handles feature mapping, ad generation, deployment tracking, and plain English reporting

---

### 2026-03-28 — Aryan
**Ad copy diversity fix: eliminate duplication, slot-based generation, tighter filters**

- `engine/models.py` — Added `deployment_targets` field to `AdVariant` to store all format x platform pairs without creating duplicate variant objects
- `engine/generation/generator.py` — Collapsed the nested `for fmt in formats: for platform in platforms:` loop in `generate_with_templates()`. Now creates one variant per unique copy combination instead of N x |formats| x |platforms| duplicates
- `engine/generation/copy_agents.py` — Rewrote `HeadlineAgent.generate()` and `BodyCopyAgent.generate()` to use slot-based generation: separate LLM calls per hook_type/message_type with type-specific exemplars. Added `HOOK_TYPE_EXEMPLARS` and `MESSAGE_TYPE_EXEMPLARS` dicts. Removed post-hoc retry mechanism (no longer needed). This structurally guarantees diversity instead of relying on prompt instructions the LLM ignores
- `engine/generation/variant_matrix.py` — Added per-attribute caps (`ceil(n/6)` max per value) to both `_select_exploit()` and `_select_diverse_random()`. Added `tone` to the similarity check in the random path. Made `_enforce_minimums()` loop until diversity targets are met instead of single-pass
- `dashboard/api/app.py` — Enabled `use_selector=True` in concept endpoint so TemplateSelector rotates visual templates per variant
- `engine/orchestrator.py` — Enabled `use_selector=True` in submit_idea, submit_concept, and playbook generation paths
- Root causes: (1) 198 variants but only 46 unique headlines because format x platform expansion created 4x duplicates; (2) 40% of headlines were "statistic" hooks because single-call LLM anchored on statistic-heavy gold standards; (3) diversity filter only blocked combos sharing 2+ of 4 attrs, letting same-hook-type ads through

---

### 2026-03-28 — Aryan
**Portfolio analysis page revamp: zoom, bubble chart, high-res images, top performers**

- Modified `dashboard/api/app.py`: added `full_image_url` field to portfolio-scatter endpoint for both engine variants and imported existing ads, so the frontend can display full-resolution images instead of thumbnails
- Rewrote `dashboard/frontend/pages/portfolio.html` with major UX improvements:
  - Switched scatter plot to bubble chart — bubble radius scales with first notes (conversions), so proven winners visually pop
  - Added chartjs-plugin-zoom: scroll to zoom, drag to pan, double-click to reset — solves the bottom-left cluster problem
  - Added log scale toggle for x-axis to spread out ads with varying spend
  - Median CpFN reference line drawn across chart for instant above/below comparison
  - Top 5 performers highlighted as gold bubbles with labeled ranks on chart
  - New "Top Performers" card section below chart with thumbnails, CpFN, spend, notes
  - Replaced narrow side panel with full-screen modal overlay for ad inspection, large image display
  - Added total spend summary stat and cleaner filter-count display
- Why: Nathan's request for a clear visualization of every ad we've ever run with best performers obvious at a glance. The old scatter congregated everything in the bottom-left corner with no way to zoom in.

---

### 2026-03-28 — Aryan
**Pipeline verification: regression → memory → review → dashboard**

- Ran full regression pipeline end-to-end: dataset build (263 rows, 141 with CPA), WLS regression (R²=0.53, adj R²=0.14, 62 features), holdout validation (test R²=-1.0, overfit as expected with 141 obs / 62 features), bootstrap CI (100 resamples), stability check, confidence tiers (1 moderate, 61 unreliable), creative playbook, format comparison (video CpFN $62 vs static $123, p=0.0003)
- Verified memory builder: 4 approval clusters, 1 rejection rule, data quality 0.7, generation context producing 835-char prompt block
- Verified review queue: 186 pending variants (97 with rendered PNGs), 5 approved, 7 rejected
- Launched dashboard on port 8000, confirmed all API endpoints responding: `/api/review` (97 variants), `/api/regression` (model health + validation detail), format comparison, portfolio scatter
- All pipeline stages working as intended per changelog documentation

---

### 2026-03-28 — Aryan
**Features 4-8: Portfolio scatter, format comparison, Meta deploy + tracking**

- `dashboard/api/app.py` — added `GET /api/analysis/portfolio-scatter` (merges engine variants + existing ads, IQR outlier detection, top-5 ranking by CpFN), `GET /api/analysis/format-comparison` (delegates to regression model), `POST /api/deploy` (deploys approved variants to Meta via facebook_business SDK as paused ads)
- `dashboard/frontend/pages/portfolio.html` — new page: Chart.js scatter plot of all ads by spend vs CpFN, color-coded static/video, outlier highlights, click-to-inspect detail panel, format comparison summary section, min-spend filter slider
- `dashboard/frontend/pages/review.html` — added Portfolio nav tab linking to portfolio page; added "Deploy Approved" button in toolbar with campaign/adset modal; deploy JS wiring
- `engine/regression/model.py` — added `format_comparison(min_spend)` method: groups ads by video/static, computes avg/median CpFN, runs Welch's t-test, extracts regression coefficient for format_video dummy
- `engine/deployment/deployer.py` — implemented `MetaDeployer` using facebook_business SDK: `upload_asset()` uploads PNG to Meta CDN, `create_ad()` creates AdCreative + Ad (paused), `pause_ad()`/`resume_ad()`/`delete_ad()` manage status. Includes retry with exponential backoff and CTA mapping
- `engine/tracking/tracker.py` — implemented `MetaTracker` using facebook_business SDK: `pull_ad_metrics()` calls Meta Insights API for single-day ad metrics, parses actions array for first_note_completion/signup/landing_page_view conversions; `pull_all_active()` fetches all active ads in account. Includes retry with backoff
- `engine/orchestrator.py` — wired `MetaDeployer` and `MetaTracker` from settings into `__init__`: conditionally creates platform clients when `META_ACCESS_TOKEN` and `META_AD_ACCOUNT_ID` are configured; passes them to `AdDeployer` and `PerformanceTracker`
- `config/settings.py` — added `META_PAGE_ID` setting for Facebook Page ID (required by AdCreative object_story_spec)
- `requirements.txt` — uncommented `facebook-business>=19.0.0` as active dependency
- Why: Nathan wants portfolio visualization of all ad performance with outlier detection, video vs static format analysis to validate his "30% better" thesis, and ads deployed to Meta from the dashboard. Features 7+8 close the loop: deploy → track → regress → learn

---

### 2026-03-27 — Aryan
**Nathan's meeting feedback: monologue review, creative direction, diversity fix, hypothesis tracking**

- `engine/review/monologue_parser.py` — new module: Claude-powered parser that converts freeform review monologues into per-variant approve/reject verdicts + global creative direction extraction
- `engine/tracking/hypothesis_tracker.py` — new module: evaluates creative hypotheses against regression coefficients, auto-transitions status (confirmed/rejected) based on consecutive confidence
- `engine/memory/models.py` — added `CreativeDirection` dataclass and `creative_directions` field to `CreativeMemory`; added `creative_directions` field to `GenerationContext` with priority rendering in `to_prompt_block()`
- `engine/models.py` — added `HypothesisStatus` enum and `CreativeHypothesis` Pydantic model for tracking creative hypotheses with confidence scores and evidence trails
- `engine/intake/parser.py` — `IntakeParser.parse()` now accepts `creative_direction` parameter; injected into system prompt as "HUMAN CREATIVE DIRECTION" section
- `engine/orchestrator.py` — `submit_idea()` and `submit_idea_templates()` now accept `creative_direction`; added `_build_creative_direction()` helper that merges persistent directions from memory with per-call overrides; hypothesis evaluation integrated into `run_daily_cycle()` after regression step
- `engine/memory/builder.py` — `build()` now preserves `creative_directions` across memory rebuilds (they compound); `build_generation_context()` populates active directions into `GenerationContext`
- `engine/generation/variant_matrix.py` — tightened similarity threshold from `shared >= 3` to `shared >= 2` in `_select_exploit()` and `_select_diverse()`; added `_enforce_minimums()` method to swap in underrepresented taxonomy values; `diversity_report()` thresholds now scale with batch size
- `engine/generation/copy_agents.py` — added "CRITICAL DIVERSITY RULE" constraints to HeadlineAgent (4+ hook_types) and BodyCopyAgent (3+ message_types) prompts; added post-generation diversity check with automatic re-prompt for missing types
- `engine/store.py` — added `save_hypotheses()`, `load_hypotheses()`, `get_hypothesis()` methods; updated v2 memory deserialization to handle `creative_directions`
- `engine/notifications.py` — added `notify_hypothesis_update()` for Slack alerts on hypothesis status changes
- `dashboard/api/app.py` — added `POST /api/review/monologue` and `POST /api/review/monologue-regenerate` endpoints; added `GET/POST/PATCH /api/memory/creative-directions` endpoints; added `GET/POST/PATCH/DELETE /api/hypotheses` and `/api/hypotheses/report` endpoints; fixed `POST /api/intake` to use `Orchestrator` (was `AdCampaignOrchestrator`); `IdeaInput` now accepts `creative_direction`
- `dashboard/frontend/pages/review.html` — added "Batch Review" mode with monologue textarea, parsed results display with editable verdicts, commit reviews, and regenerate-from-monologue flow
- Why: Nathan's feedback from meeting — (1) batch gallery review via monologue input with regeneration loop, (2) creative direction as a first-class input alongside memory layers, (3) ads too similar in gallery need hard diversity enforcement, (4) hypothesis tracking for "what creative works and why"

---

### 2026-03-27 — Aryan
**Pushed all local changes to remote; approved variant 50f6fb53 in review**

- `data/creatives/variants/50f6fb53-9293-4438-9310-08af8274d921.json` — status updated from `draft` → `approved`, reviewer and timestamp recorded from dashboard session
- Committed and pushed to `aryan/main` on remote

---

### 2026-03-27 — Aryan
**Created METHODOLOGY.md — detailed reasoning document for the regression-to-review loop**

- `METHODOLOGY.md` — New document explaining the full methodology of the ads engine, focused on the five stages we've built so far: Analysis (MECE taxonomy, Claude tagging, portfolio analysis), Regression (WLS, interaction terms, holdout/bootstrap/stability validation, confidence tiers), Memory (three-layer architecture, decay/archiving, playbook translation, GenerationContext), Generation (multi-agent copy, quality filter, explore/exploit variant matrix, Playwright template rendering), and Review (Tinder-style UI, structured chips, duration tracking, feedback-to-memory loop). Covers the reasoning behind every major design decision: why linear regression over ML, why templates before AI images, why chips instead of free text, why memory compounds but generation is stateless, why 80/20 explore/exploit, why build review before deploy.
- Referenced CHANGELOG.md and ROADMAP.md for historical context and evolution of decisions.

---

### 2026-03-27 — Aryan
**Fix logo loading, body truncation, browser hang, and dashboard 404**

- `engine/generation/template_renderer.py` — Root cause of broken logo in Playwright screenshots: `page.set_content()` sets the base URL to `about:blank`, and Chromium blocks loading `file://` resources from that origin. Fixed by writing the rendered HTML to a temp file and using `page.goto("file://...")` instead. Also fixed a browser hang when calling `render()` multiple times: the cached `self._browser` was bound to a previous asyncio event loop and became invalid across `_run_async()` calls. Fixed by wrapping each sync `render()` in a coroutine that opens and closes the browser within a single event loop. Added `_truncate_body()` helper that truncates at sentence boundaries (max 280 chars) so PNGs never show CSS ellipsis or mid-sentence cuts. Added `import tempfile`.
- `engine/generation/templates/meta_feed.html` — Removed `-webkit-line-clamp` from `.headline` and `.body-text`; truncation now handled in Python.
- `dashboard/api/app.py` — Added redirect routes `/dashboard/review` → `/dashboard/pages/review.html` and `/` → review page. Added `RedirectResponse` import.
- Re-rendered all 108 PNG variants: 108/108 OK, 0 failed.

---

### 2026-03-27 — Aryan
**Regenerate 72 variants from playbook with all fixes applied**

- Ran `python -m engine.orchestrator generate` to regenerate ads from the regression playbook.
- 6 briefs extracted, 12 variants each = 72 total new variants.
- All copy generated with the em dash ban in place: 0 em dashes found across all 72 variants.
- All 72 PNGs rendered via Playwright with the fixed logo paths (~90KB each, no broken logos).
- Dashboard CSS fixes (badge positioning, iframe anchoring) will take effect on page refresh.

---

### 2026-03-27 — Aryan
**Fix "ima" badge bleedover and iframe positioning in review cards**

- `dashboard/frontend/pages/review.html` — The `.asset-badge` span ("image" / "template") had CSS only for gallery mode (`.gallery-card .asset-badge`), not tinder mode. In tinder mode, the unstyled badge was a flex sibling of the `<img>`/`<iframe>`, causing the first few chars ("ima" from "image") to bleed through at the right edge. Added `.tinder-card .asset-area .asset-badge` with absolute positioning matching gallery mode.
- Also fixed iframe positioning: iframes were flex-centered in the asset container via `justify-content: center`, but with `transform-origin: top left` scaling, this caused misalignment. Changed to `position: absolute; top: 0; left: 0;` for both tinder and gallery iframes so the scaled template anchors correctly to the top-left corner.
- Added `flex-shrink: 0` to tinder asset images to prevent the badge from stealing layout space.

---

### 2026-03-27 — Aryan
**Fix broken logo in template previews + ban em dashes from generated copy**

- `engine/generation/template_renderer.py` — Logo/font URLs in `render_to_html` used only the file basename (e.g. `/brand/Logo.png`), but the static mount serves from `brand/` and files live in subdirectories (`brand/logos/png/`, `brand/fonts/`). Changed to use `relative_to(BRAND_DIR)` so URLs resolve correctly (e.g. `/brand/logos/png/Logo.png`). Playwright rendering (`_render_async`) was unaffected since it uses `file://` absolute paths.
- `engine/generation/copy_agents.py` — Added explicit "no em dashes" rule to `JOTPSYCH_VOICE`. Replaced em dashes in `GOLD_STANDARD_BODIES` and all system prompt strings with commas/periods/colons so the LLM doesn't learn the pattern.
- `engine/generation/generator.py` — Removed em dashes from `COPY_GENERATION_PROMPT`, added em dashes to the NEVER USE list.
- `engine/brand.py` — Added "no em dashes" to `BRAND_VOICE` AVOID list, replaced em dashes in tone guidelines. This propagates via `get_brand_context_for_copy_prompt()`.
- The "—..." pattern in the dashboard was caused by generated copy containing em dashes getting CSS-truncated (`line-clamp`) right after the dash character.

---

### 2026-03-27 — Aryan
**Use median instead of average for review time in Learnings**

- `engine/review/reviewer.py` — Renamed `avg_review_duration_ms` to `median_review_duration_ms`. Calculation changed from `sum/len` to `sorted[n//2]` (lower median). Average was inflated by idle time when the screen was left open between reviews.
- `dashboard/frontend/pages/review.html` — Updated label from "Avg review time" to "Median review time", reads the new field name.

---

### 2026-03-27 — Aryan
**Fix review queue: only show variants with real images on disk**

- `dashboard/api/app.py` — Rewrote `/api/review` filter. Previous `asset_type == "video"` check was insufficient because many legacy variants had `asset_type = "image"` with placeholder paths, `.mp4` paths, or missing files. New filter: only include variants where `asset_path` has an image extension (`.png`/`.jpg`/`.jpeg`/`.webp`), the file exists on disk, and is >1KB. Falls through to `template_available` for iframe previews. Queue went from 94 broken variants → 31 with real images.

---

### 2026-03-27 — Aryan
**Remove video + Gemini/Veo AI generation — Playwright-only rendering**

- `engine/models.py` — Changed `CreativeBrief.formats_requested` default from `[SINGLE_IMAGE, VIDEO]` to `[SINGLE_IMAGE]`.
- `engine/generation/generator.py` — Removed the entire Gemini/Veo AI generation path: `generate_assets()`, `_generate_image()`, `_generate_video()`, `_build_image_prompt()`, `_build_video_prompt()`, `IMAGE_PROMPT_TEMPLATE`, `VIDEO_PROMPT_TEMPLATE`, and all `google.genai` / `requests` / `base64` imports. `generate()` now delegates to `generate_with_templates()`. `generate_assets_from_selector()` no longer imports `VideoRenderer` or branches on `is_video`. `generate_with_templates()` always sets `asset_type="image"`.
- `engine/generation/template_selector.py` — Removed `is_video` and `video_duration_ms` from `TemplatePlan`. Removed story/video format detection from `select()`. Removed `_select_story_template()`.
- `engine/orchestrator.py` — `regenerate_assets()` now uses `generate_assets_from_template()` instead of the removed `generate_assets()`. Also checks for `.placeholder` suffix when detecting missing assets.
- `dashboard/api/app.py` — `/api/review` now filters out `asset_type == "video"` variants so legacy video data doesn't appear in the review queue.
- `dashboard/frontend/pages/review.html` — Removed `<video>` rendering branch from `buildAssetHtml()`.

Why: Only 24 of 126 variants had working images — all from the Playwright template pipeline. The remaining 102 were broken placeholders, corrupt Gemini images, or Veo videos. Simplifying to Playwright-only gives deterministic, brand-consistent output. AI image generation can be re-added later (Phase 2) once quality bar is met.

---

### 2026-03-27 — Aryan
**End-to-end pipeline test: regression → review loop. Fixed 7 bugs found during first live run.**

- `engine/regression/model.py` — Sanitize NaN/inf values in p_values, vif_scores, and confidence_intervals before building RegressionResult. Pydantic `dict[str, float]` fields fail on None which appears when interaction term VIFs or t-stat SE calculations produce nan.
- `engine/intake/parser.py` — Fixed `SYSTEM_PROMPT.format(playbook_context=...)` crashing with KeyError because the JSON example block in the prompt contains literal `{` `}` curly braces. Switched to `str.replace("{playbook_context}", ...)` instead.
- `engine/memory/builder.py` — Fixed `self.store.base_path` AttributeError. Store exposes `self.base` (a `Path`), not `self.base_path`. Two locations fixed.
- `engine/orchestrator.py` — Same `store.base_path → store.base` fix in `_log_diversity_report`.
- `engine/generation/variant_matrix.py` — Fixed `TypeError: cannot use 'tuple' as a set element (unhashable type: 'dict')`. `combo` tuples contain dicts, which are unhashable. Switched to `id()`-based set for deduplication between exploit and explore selection.
- `engine/review/reviewer.py` — `submit_review` was checking `verdict == "approved"` but the dashboard sends `"approve"`. Fixed to accept both `"approve"` and `"approved"`.
- `requirements.txt` — Added `python-multipart>=0.0.9` (required by FastAPI for form data; was causing dashboard startup crash). Also installed `scikit-learn` and `playwright` which were in requirements but not installed in venv.

Pipeline verified end-to-end: regression (R²=0.53, n=141, all features unreliable at this data volume) → idea → 24 variants generated with Playwright HTML rendering → dashboard shows variants → approve/reject via API → memory builder picks up 2 approval clusters + 1 rejection rule → context injected into next generation.

Regression note: with 141 observations and ~60 one-hot features, the model is overfit (adj R²=0.14, test R²=-1.0). No playbook rules are produced yet. Expected — will improve as more live ad data comes in. Bootstrap validation and confidence tier infrastructure is in place.

---

### 2026-03-27 — Aryan (P0 Creative Excellence Loop)
**Full P0 implementation: 16 workstreams across Regression, Analysis, Generation, and Memory stages**

#### Regression Stage
- `engine/models.py` — `RegressionResult`: added `test_r_squared`, `bootstrap_ci`, `coefficient_stability`, `confidence_tiers` for holdout + bootstrap validation
- `engine/regression/model.py` — Added `run_with_validation()`: 80/20 holdout, 1000-resample bootstrap CIs, 10-subsample stability scoring, 4-tier confidence classification (high/moderate/directional/unreliable). Added 5 new taxonomy features to `CATEGORICAL_FEATURES`/`BOOLEAN_FEATURES` (`social_proof_type`, `copy_length_bin`, `contains_specific_number`, `shows_product_ui`, `human_face_visible`) and `days_since_first_run` numerical feature. Excluded `exclude_from_regression` ads from dataset
- `engine/memory/playbook_translator.py` — `translate()` now filters to high/moderate confidence tiers only when `confidence_tiers` available
- `engine/memory/builder.py` — `_build_pattern_insight()` uses regression confidence tiers; added `_apply_memory_decay()` (60-day downgrade, 90-day archive), `_archive_patterns()`, `build_generation_context()` now populates `stylistic_references` from swipe files
- `dashboard/api/app.py` — `/api/regression` returns `model_health`, `validation_detail`, bootstrap CIs for top features

#### Analysis Stage
- `engine/models.py` — `CreativeTaxonomy`: 5 new fields with `VALID_VALUES` dict, `validate_values()`, `low_confidence_fields()`, `tagging_confidence` dict. `CreativeBrief`: 6 new fields (`emotional_register`, `proof_element`, `hook_strategy`, `target_persona_details`, `brief_richness_score`, `source_pattern_id`). `ExistingAd`: `source` and `exclude_from_regression` fields
- `engine/analysis/analyzer.py` — `TAXONOMY_PROMPT` updated with 5 new dimensions, MECE boundary rules, tagging confidence scoring; added `TAXONOMY_CORRECTIONS` auto-correction dict; `tag_ads()` applies corrections + validates after tagging; `extract_briefs_from_playbook()` rebuilt with rich brief fields, richness scoring, per-brief retry below threshold
- `engine/intake/parser.py` — Rewritten: `SYSTEM_PROMPT` with richness rules, `validate_brief()`, re-prompt logic (max 1 retry), playbook rule injection into system prompt
- `dashboard/api/app.py` — `POST /api/intake/swipe` endpoint for URL/image swipe file ingestion, tagged and saved as `exclude_from_regression=True`
- `engine/memory/models.py` — `GenerationContext`: added `stylistic_references` field and rendering in `to_prompt_block()`; `winning_rules` framing changed from "use these" to "inspired by — adapt, don't copy verbatim"
- `engine/orchestrator.py` — `submit_idea()` + `submit_idea_templates()` now inject playbook rules into parser; `_get_playbook_rules()` helper added; `_log_diversity_report()` added

#### Generation Stage
- `engine/generation/copy_agents.py` — Added `GOLD_STANDARD_HEADLINES` + `GOLD_STANDARD_BODIES` few-shot examples; `HeadlineAgent` and `BodyCopyAgent` now inject gold standards + richer brief context (emotional_register, hook_strategy, proof_element, target_persona_details); `CTAAgent.generate()` now accepts `generation_context` parameter (parity with headline/body agents)
- `engine/generation/generator.py` — `cta_agent.generate()` now passes `generation_context`; `_build_image_prompt()` strengthened with style differentiation (UGC/editorial/product-focused) and stronger negative prompts
- `engine/intake/concept_expander.py` (new) — `ConceptExpander` class: concept → Claude enumerates 5 angles × 3 formats × 4 tones × 3 proof types → 20 diverse `CreativeBrief` seeds; diversity-first selection algorithm
- `engine/orchestrator.py` — `submit_concept()` method; `concept` CLI command
- `dashboard/api/app.py` — `POST /api/intake/concept` with SSE streaming progress; `ConceptInput` model
- `engine/generation/templates/meta_carousel_frame/card.html` (new) — Carousel card template (1080x1080) with proof element zone and position indicator
- `engine/generation/templates/google_728x90/leaderboard.html` (new) — Google leaderboard (728x90) with compact stat callout
- `engine/generation/templates/google_160x600/skyscraper.html` (new) — Google skyscraper (160x600) with vertical proof zone
- `engine/generation/template_renderer.py` — `TEMPLATE_SIZES` updated with 3 new templates; `_resolve_template_file()` updated; `_DEFAULT_CONTEXT` defaults to "2 hrs saved/day" stat
- `engine/generation/template_selector.py` — Added `_FORMAT_TEMPLATES` for new formats; carousel selection logic
- `engine/generation/scene_library.py` — Added 7 new video scenes: `video_audit_prep_anxiety`, `video_post_session_relief`, `video_weekend_reclaimed`, `video_voice_recording_in_car`, `video_mid_session_quick_note`, `video_before_after_desk` (total: 10 video scenes, 27 total)
- `engine/generation/variant_matrix.py` — Added `diversity_report()` method with threshold tracking (4 hook_types / 3 tones / 3 visual_styles minimum)

#### Memory Stage
- `engine/memory/models.py` — `PatternInsight` + `FatigueAlert`: added `memory_snapshot_date`; fixed `CompetitiveObservation` field ordering bug
- `engine/memory/builder.py` — `build()` calls `_apply_memory_decay()`; `_build_editorial_memory()` loads synthesized preferences from voice notes; `_load_synthesized_preferences()` + `_merge_synthesized_preferences()` helpers
- `engine/store.py` — `archive_memory_patterns()`, `get_memory_status()` methods
- `dashboard/api/app.py` — `POST /api/review/voice-note` (Whisper transcription), `POST /api/review/synthesize-preferences` (Claude extraction), `GET /api/memory/status` endpoint

#### Legacy model cleanup
- `engine/models.py` — Added DEPRECATED docstrings to `WinningPattern`, `ReviewerPreference`, `FatigueAlert`, `CreativeMemory` (v1 Pydantic versions). Canonical versions are now in `engine/memory/models.py`. `PlaybookRule` remains canonical for both paths.

#### New scripts
- `scripts/retag_existing.py` — Re-tag 432 existing ads with expanded taxonomy (5 new dimensions + confidence)
- `scripts/audit_taxonomy.py` — Sample 50 tagged ads, export CSV for manual MECE review with dimension distribution report
- `scripts/benchmark_copy.py` — A/B test copy agent output: generate 20 headlines/bodies per brief with/without memory
- `scripts/audit_images.py` — Generate 20 images across UGC/editorial/product styles for visual quality scoring
- `scripts/test_memory_impact.py` — A/B test memory injection impact on copy quality with convergence detection

#### New dependencies
- `requirements.txt` — `scikit-learn>=1.4.0` (holdout validation), `openai>=1.0.0` (Whisper transcription)

Key decisions:
- Confidence tier system makes regression downstream-safe: only high/moderate features flow into playbook rules and memory context
- If test R² < 0.15, playbook translator returns empty (fall back to editorial memory only)
- Memory decay is 60-day downgrade + 90-day archive, not deletion — historical patterns preserved
- VALID_VALUES dict on CreativeTaxonomy enables both programmatic validation and prompt grounding
- GenerationContext framing changed from "do this" to "inspired by" to prevent creative convergence
- All new API endpoints tested with integration check script

---

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
