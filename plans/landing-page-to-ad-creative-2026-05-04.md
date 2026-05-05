# Plan: `/landing-page-to-ad-creative`

**Date:** 2026-05-04
**Owner:** Nate (review) + Claude (build)
**Status:** Awaiting approval
**Trigger:** `/landing-page-to-ad-creative <path-to-landing-page.html>`

---

## Goal

A landing page goes in. Five Meta-ready static ad concepts come out, each rendered at feed (1080x1080) and story (1080x1920), each with primary text + headline + description + CTA validated against Meta API character limits, plus a manifest.json that an upload script can ingest verbatim. Two question rounds with Nate per run, no more.

## Locked decisions (confirmed 2026-05-04)

| Decision | Choice |
|---|---|
| Skill location | Global: `~/.claude/skills/landing-page-to-ad-creative/` |
| Imagery tech | Hybrid: Gemini Imagen 4 Ultra (`imagen-4.0-ultra-generate-001`) hero photo + Playwright HTML/CSS overlay for copy and brand frame |
| Output scope per run | 5 concepts x {feed 1080x1080, story 1080x1920} = 10 PNG files |
| Clinician language guide | `ads_engine/docs/clinician-language.md`, accumulating across runs, sectioned by topic with provenance |
| Best-practice-ad-formats reference | `~/.claude/skills/landing-page-to-ad-creative/best-practice-ad-formats.md` (vendored with the skill so it travels) |

## Architecture: global skill, project-bound assets

The skill is global so it can be called against any landing page in any project. But it leans on the active project's local assets when present:

- **Templates:** prefer `<project>/engine/generation/templates/meta_feed.html` and `meta_story.html` if they exist. Fall back to vendored copies in the skill folder.
- **Brand:** prefer `<project>/brand/` (logos, fonts, guidelines). Fall back to `ads_engine/brand/` resolved by absolute path (since this is the canonical brand home).
- **Output:** always writes to `<project>/data/ad-creative/<lp-slug>-<YYYY-MM-DD>/`.
- **Clinician language guide:** `<project>/docs/clinician-language.md`. Skill creates it if missing.

Skill arg parsing: `/landing-page-to-ad-creative <html-path>`. Project root is derived by walking up from the landing-page path until we find a `CLAUDE.md` or `.git`. If no project is detected, fall back to writing under `~/.claude/skills/landing-page-to-ad-creative/runs/`.

---

## Phase A: install (one-time build)

### A1. Research and write `best-practice-ad-formats.md`

**Method:** WebSearch + WebFetch across Meta Ad Library top-performing creative reports, healthcare/SaaS B2B and DTC swipe files (Foreplay, Atria, Adwise creative breakdowns), academic ad-copy literature (Heath/Heath, Caples, Sugarman, Ogilvy primary-source patterns), and BH-clinic specific creative when available.

**Deliverable shape:** 8-12 evergreen ad-format archetypes. Each entry is a self-contained record:

```
## Archetype: <name>            e.g. "Audit-fear shock"
- When to use: <signal in the landing page that this archetype fits>
- Structure: <hook -> middle -> CTA blueprint>
- Image archetype: <what the photo shows; feeds the Imagen prompt>
- Copy archetype: <primary-text scaffold with placeholders>
- Headline archetype: <40-char headline scaffold>
- BH-clinician adaptation: <how this lands for a behavioral-health admin or provider>
- Failure mode: <what makes this archetype slop>
- Real example (cited): <link or screenshot reference, with source>
```

**Question round (A1) before writing:** AskUserQuestion with four questions covering archetype count target (8 vs 10 vs 12), source weighting (swipe-file heavy vs academic-frameworks heavy vs both), audience pin (provider-only vs admin/owner vs mixed), and any archetypes Nate explicitly wants included or excluded.

**Anti-slop guardrails:** every archetype must cite a real example with provenance. No fabricated examples. Voice DNA rules apply: no em dashes, no AI tells.

### A2. Build skill scaffolding

```
~/.claude/skills/landing-page-to-ad-creative/
├── SKILL.md                          # frontmatter + cycle protocol
├── best-practice-ad-formats.md       # output of A1
├── templates/
│   ├── feed-overlay.html             # vendored fallback, 1080x1080 frame
│   ├── story-overlay.html            # vendored fallback, 1080x1920 frame
│   └── brand-tokens.css              # mirrored from ads_engine/brand/
├── scripts/
│   ├── main.py                       # entrypoint; orchestrates the cycle
│   ├── ingest.py                     # parse landing-page HTML to structured brief
│   ├── copy_gen.py                   # generate 5 ad-copy concepts via Claude
│   ├── imagen_client.py              # Gemini Imagen 4 Ultra REST wrapper
│   ├── render.py                     # Playwright composite (image + overlay) -> PNG
│   ├── manifest.py                   # write Meta-ready manifest.json
│   └── review_page.py                # build review.html gallery
├── examples/
│   └── never-salt-again-2026-05-04/  # dogfooded reference run
└── README.md                         # how the skill works at a glance
```

### A3. Brand bridge

- Read `ads_engine/brand/guidelines/` for tokens (palette, typography, logo lockup rules).
- Mirror the critical tokens into `templates/brand-tokens.css` so the skill works even when the Google Drive style-guide path is offline.
- Keep `jotpsych-logo.svg` resolvable from skill or project.

---

## Phase B: per-run cycle (the actual `/landing-page-to-ad-creative` execution)

### Step 1. Ingest

- Read the landing-page HTML at the provided path.
- Parse: `<title>`, meta description, h1, hero subline, all section headings, body copy, testimonial blocks, CTA copy, OG image URL.
- Detect topical theme(s) by keyword density (e.g. SALT page surfaces: audit risk, recoupment, copy-forward, BH compliance).

**Question round 1 (Step 1) — AskUserQuestion, 3-4 questions:**
1. Target audience pin for *this* page (admin/owner vs provider vs both)
2. Must-mention angle Nate wants enforced (e.g. "always lead with audit-fear, never with productivity")
3. Terms to avoid (compliance constraints, words that flag in Meta review)
4. Urgency level (calm-authority vs alarm-bell)

### Step 2. Copy generation

- Read `best-practice-ad-formats.md`. Score each archetype against the parsed page brief plus the Step 1 answers. Pick the top 5.
- For each picked archetype: produce primary_text (<=125 chars for safe Meta truncation), headline (<=40 chars), description (<=30 chars), CTA enum (`LEARN_MORE` | `SIGN_UP` | `GET_OFFER` | `BOOK_NOW` | etc).
- Validate against `~/.claude/qc/voice-dna.md` — no em dashes, no AI tells, no numbers without provenance.
- Pull terms-of-art from the landing page testimonials and section copy where they exist (the SALT page already has L.M., LCSW quotes that should feed clinician vocabulary).

**Question round 2 (Step 2) — AskUserQuestion, presents the 5 drafts:**
- For each draft: confirm / edit / reject. "Reject" replaces with the next-best archetype from the scored list.
- Capture any term-of-art corrections. Append confirmed terms to `ads_engine/docs/clinician-language.md` with provenance:

```
### Audit risk vocabulary
- "Recoupment" — payer takes back what they already paid. Source: never-salt-again landing page, 2026-05-04. Confirmed by Nate.
- "Targeted Probe and Educate" — payer focused-review program. Source: never-salt-again landing page. Confirmed by Nate.
```

### Step 3. Image generation

- For each concept, derive an Imagen prompt from the archetype's `image archetype` field plus the landing-page subject. Example for audit-fear archetype on SALT page: `"Stack of unopened audit-notice envelopes on a clinician's desk, soft daylight, shallow depth of field, photorealistic, no text in image, no logos."`
- Call Gemini Imagen 4 Ultra (`imagen-4.0-ultra-generate-001`), 1024x1024 seed.
- Negative-prompt: text, words, logos, watermarks, hands with extra fingers.
- Save raw outputs to `data/ad-creative/<slug>-<date>/raw/<concept-slug>.png`.

**Cost math:** ~$0.05/image at Imagen 4 Ultra (verify at A2 install time). 5 images per run = ~$0.25/run. If Nate runs this on 4 landing pages a week, that is $1/week in image gen. Negligible.

**Fallback:** for archetypes where text and visual are inseparable (e.g. before/after split), test `gemini-3-pro-image-preview` at install time. If it produces clean integrated text, allow that as an opt-in archetype renderer. Otherwise, hybrid pipeline only.

### Step 4. Composite render

- Playwright opens the appropriate overlay HTML template (`feed-overlay.html` or `story-overlay.html`).
- Inject hero image (from Step 3), eyebrow tag, headline, sub-line, logo, CTA button.
- Render at exact dimensions: 1080x1080 for feed, 1080x1920 for story.
- Save to `data/ad-creative/<slug>-<date>/final/<concept-slug>-feed.png` and `<concept-slug>-story.png`.

### Step 5. Manifest + review

**`manifest.json`** (one record per concept, designed to be Meta-API-ready):

```json
{
  "run_id": "never-salt-again-2026-05-04",
  "source_landing_page": "/abs/path/never-salt-again.html",
  "source_url": "https://jotpsych.com/never-salt-again",
  "concepts": [
    {
      "slug": "audit-fear-shock",
      "archetype": "Audit-fear shock",
      "primary_text": "...",
      "headline": "...",
      "description": "...",
      "call_to_action": "LEARN_MORE",
      "creatives": {
        "feed_1080x1080": "final/audit-fear-shock-feed.png",
        "story_1080x1920": "final/audit-fear-shock-story.png"
      },
      "imagen_prompt": "...",
      "imagen_model": "imagen-4.0-ultra-generate-001",
      "char_counts": {"primary_text": 122, "headline": 38, "description": 28}
    }
  ]
}
```

**`review.html`:** single-page gallery, 5 concept rows, each row shows feed + story side by side with the copy fields rendered as a Meta mockup card. Click to enlarge. Open with the OS default. This is what Nate looks at to approve.

**Skill terminal output (final):**
```
Done.
- 5 concepts rendered, 10 PNGs total.
- Review: open <abs path to review.html>
- Manifest ready for Meta API: <abs path to manifest.json>
- Clinician language updated: 7 new terms appended to <abs path>.
```

---

## Phase C: explicitly out of scope (document, don't build)

- C1. Meta API upload — lives in ads_engine main pipeline, ingests `manifest.json`. Different skill / different cycle.
- C2. Regression element-tagging — manifest already records archetype + prompts, sufficient for downstream MECE coding when ads_engine regression pipeline exists.
- C3. Video extension via Veo — Phase 3 of ads_engine roadmap.
- C4. Carousel ads — single-image only for v1. Carousel structure has different copy logic and deserves its own skill.

---

## Meta API field mapping (so v1 is upload-ready)

| Manifest key | Meta API field | Limit | Validation |
|---|---|---|---|
| `primary_text` | `body` | 125 chars (safe) | Hard-fail above 125; warn 90-125 |
| `headline` | `title` | 40 chars (safe) | Hard-fail above 40 |
| `description` | `link_description` | 30 chars (safe) | Hard-fail above 30 |
| `call_to_action` | `call_to_action.type` | enum | Whitelist from Meta's CTA list |
| `creatives.feed_1080x1080` | image upload at 1:1 | 1080x1080 | dimension check |
| `creatives.story_1080x1920` | image upload at 9:16 | 1080x1920 | dimension check |

Limits use Meta's "fully visible without truncation" thresholds, not the hard upper bounds (which are 2200 / 255 / 200 but truncate aggressively in feed).

---

## File deliverables this build creates

**Phase A (one-time, this build):**
- `~/.claude/skills/landing-page-to-ad-creative/SKILL.md`
- `~/.claude/skills/landing-page-to-ad-creative/best-practice-ad-formats.md`
- `~/.claude/skills/landing-page-to-ad-creative/templates/feed-overlay.html`
- `~/.claude/skills/landing-page-to-ad-creative/templates/story-overlay.html`
- `~/.claude/skills/landing-page-to-ad-creative/templates/brand-tokens.css`
- `~/.claude/skills/landing-page-to-ad-creative/scripts/{main,ingest,copy_gen,imagen_client,render,manifest,review_page}.py`
- `~/.claude/skills/landing-page-to-ad-creative/README.md`
- `~/.claude/skills/landing-page-to-ad-creative/examples/never-salt-again-2026-05-04/` (full dogfood run)
- `ads_engine/docs/clinician-language.md` (initial scaffolding, populated by the dogfood run)

**Phase B (created on every skill invocation):**
- `<project>/data/ad-creative/<slug>-<YYYY-MM-DD>/raw/*.png`
- `<project>/data/ad-creative/<slug>-<YYYY-MM-DD>/final/*.png`
- `<project>/data/ad-creative/<slug>-<YYYY-MM-DD>/manifest.json`
- `<project>/data/ad-creative/<slug>-<YYYY-MM-DD>/review.html`
- `<project>/data/ad-creative/<slug>-<YYYY-MM-DD>/prompts.json` (audit trail of Imagen calls)

---

## Acceptance criteria (what done looks like)

1. Running `/landing-page-to-ad-creative /abs/path/never-salt-again.html` produces 10 PNGs and a manifest.json in under 5 minutes (Imagen latency is the long pole).
2. Every PNG is exact dimensions (1080x1080 or 1080x1920) and has the JotPsych logo + brand colors visible.
3. Every copy field passes voice-dna validation (no em dashes, no AI tells) and Meta char limits.
4. `review.html` renders all 5 concepts in a gallery without manual fixup.
5. `clinician-language.md` gains net-new entries with provenance.
6. The dogfood run on `never-salt-again.html` produces ad creative Nate would approve to upload (subjective, Nate-judged).

---

## Cycle-time expectations

| Step | Time |
|---|---|
| Step 1 ingest + Q round 1 | 1 min Claude + Nate's read time |
| Step 2 copy gen + Q round 2 | 1-2 min Claude + Nate's review |
| Step 3 image gen | 30-60 sec (5 parallel Imagen calls) |
| Step 4 composite render | 10-20 sec (Playwright) |
| Step 5 manifest + review | 5 sec |
| **Total wall-clock** | **3-5 min + Nate's review attention** |

---

## Open decisions for Nate before kickoff

1. **A1 archetype count target:** 8, 10, or 12? More archetypes means more diversity in scoring but diminishing returns past ~10.
2. **A1 source weighting:** swipe-file-heavy (real Meta Ad Library examples), academic-framework-heavy (Heath, Caples, Sugarman, Ogilvy), or balanced?
3. **CTA enum default:** is `LEARN_MORE` the right default, or do we want `BOOK_NOW` / `SIGN_UP` / page-specific? (Currently planned: archetype-driven, with `LEARN_MORE` fallback.)
4. **Dogfood landing page:** confirm `never-salt-again.html` is the right install-time test, or pick a different one?
5. **Phase A1 questions to Nate during research:** I'll surface these via AskUserQuestion when execution begins. Listed in A1 above so there are no surprises.

---

## What I am explicitly NOT doing in this plan

- Not picking copy on Nate's behalf. Step 2 always confirms with him.
- Not generating video. Static only.
- Not uploading to Meta. Manifest hands off to a separate Meta-upload skill or script.
- Not tagging creative elements for regression. Archetype + Imagen prompt are recorded in the manifest; element-level MECE tagging is a downstream concern.
- Not building a web dashboard. `review.html` opens locally; no server.
- Not persisting any state outside the skill folder + project's `data/ad-creative/`.

---

## Approval checklist

- [ ] Plan structure approved
- [ ] Open decisions answered (5 items above)
- [ ] Greenlight to execute Phase A

Once approved, I'll invoke `/drill-baby-drill` and build it cleanly.
