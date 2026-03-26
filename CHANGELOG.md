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
