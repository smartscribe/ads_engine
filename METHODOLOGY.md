# Ads Engine — Methodology

> How and why every piece of this system was designed. Written for anyone joining the project, evaluating the approach, or trying to understand the reasoning behind the technical decisions.

---

## Table of Contents

1. [The Problem](#the-problem)
2. [The Core Thesis](#the-core-thesis)
3. [System Overview — The Loop](#system-overview--the-loop)
4. [Stage 1: Analysis — Turning Historical Ads Into Signal](#stage-1-analysis--turning-historical-ads-into-signal)
5. [Stage 2: Regression — Finding What Actually Works](#stage-2-regression--finding-what-actually-works)
6. [Stage 3: Memory — Making Knowledge Compound](#stage-3-memory--making-knowledge-compound)
7. [Stage 4: Generation — From Insight to Ad Variant](#stage-4-generation--from-insight-to-ad-variant)
8. [Stage 5: Review — Human Judgment as Structured Data](#stage-5-review--human-judgment-as-structured-data)
9. [Why This Order Matters](#why-this-order-matters)
10. [Design Principles](#design-principles)
11. [What We Deliberately Did Not Build](#what-we-deliberately-did-not-build)
12. [Known Limitations and Open Problems](#known-limitations-and-open-problems)

---

## The Problem

JotPsych runs paid ads on Meta and Google targeting behavioral health clinicians. The product helps therapists, psychiatrists, and counselors automate their clinical documentation. The core conversion event is a user completing their first clinical note.

Before this engine existed, ad performance looked like this:

| Week | Spend | First Notes | Cost per First Note |
|------|-------|-------------|---------------------|
| Jan 25–31 | $4,158 | 22 | $189 |
| Feb 1–7 | $4,243 | 16 | $265 |
| Feb 8–14 | $4,503 | 23 | $196 |
| Feb 15–21 | $4,247 | 12 | $354 |
| Feb 22–Mar 1 | $3,863 | 20 | $193 |
| Mar 1–7 | $3,434 | 18 | $191 |

CpFN (Cost per First Note) swings between $189 and $354 week to week. There's no consistent trend. The team has intuitions about what works ("UGC-style video performs better," "question hooks are strong") but no systematic decomposition of *why* certain ads win and others don't.

Creative assets are scattered across Google Drive, email, Meta Ads Manager, and Figma. There's no single source of truth. When someone asks "what kind of ads should we make next?", the answer is a guess informed by vibes.

The advertising budget is $15-20K/month — meaningful enough that waste matters, small enough that every dollar needs to work. Meta and Google handle audience optimization. The only lever the team controls is the creative itself.

---

## The Core Thesis

**Ad performance is decomposable.** Every ad is a bundle of discrete creative elements: a hook type, a message strategy, a tone, a visual style, a CTA, color choices, text density. If you can tag each element consistently, you can run a regression and isolate which elements actually drive lower cost-per-conversion. Then you can feed those learnings back into the next round of creative generation, and the system gets smarter over time.

This is the same logic behind factor-based investing in quantitative finance. Instead of picking stocks (ads) on gut feel, you decompose returns (performance) into exposure to underlying factors (creative elements). You figure out which factors carry positive expected value. Then you systematically tilt your portfolio toward those factors.

The engine is a closed loop:

```
Regress → Learn what works → Generate ads biased toward what works → Review → Deploy → Measure → Regress again
```

Each cycle, the regression has more data. The memory system accumulates knowledge. The generator gets better prompts. The ads get better. That's the thesis.

---

## System Overview — The Loop

The engine has seven logical stages. This document focuses on the five we've built and refined so far — the stages from regression through to dashboard review. Deploy and track remain stubbed, waiting for write-access API keys and proven creative quality.

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│   ┌──────────┐    ┌──────────┐    ┌────────────┐    ┌─────────┐ │
│   │ ANALYSIS │───▶│REGRESSION│───▶│   MEMORY   │───▶│GENERATION│ │
│   │          │    │          │    │            │    │         │ │
│   │ Tag ads  │    │ Find     │    │ Translate  │    │ Create  │ │
│   │ with MECE│    │ what     │    │ coeffs to  │    │ variants│ │
│   │ taxonomy │    │ drives   │    │ actionable │    │ biased  │ │
│   │          │    │ CpFN     │    │ rules      │    │ toward  │ │
│   │          │    │          │    │            │    │ winners │ │
│   └──────────┘    └──────────┘    └────────────┘    └────┬────┘ │
│        ▲                                                 │      │
│        │           ┌──────────┐                          │      │
│        │           │  REVIEW  │◀─────────────────────────┘      │
│        │           │          │                                  │
│        │           │ Human    │                                  │
│        └───────────│ approve/ │                                  │
│                    │ reject   │                                  │
│                    └──────────┘                                  │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

What we focused on first, and why: the inner loop (regression → memory → generation → review) needs to be excellent before we hook up the outer loop (deploy → track → measure). Deploying mediocre creative at scale wastes money and poisons the regression with bad data. We want the first batch of engine-generated ads that go live to be genuinely good, so the performance data that flows back in is clean signal, not noise from sloppy creative.

---

## Stage 1: Analysis — Turning Historical Ads Into Signal

### What it does

Before the engine can generate anything intelligent, it needs to understand what JotPsych has already run. The analysis stage exports all historical ad data from Meta, tags every ad with a structured creative taxonomy, and produces a portfolio analysis identifying patterns.

### The MECE Taxonomy

The most important design decision in the entire system is the taxonomy. It defines the feature space for the regression. If the taxonomy is wrong — if categories overlap, if important dimensions are missing, if labels are inconsistent — then every coefficient downstream is noise.

The taxonomy decomposes every ad into orthogonal dimensions:

**Message layer** (what the ad says):
- `message_type`: value_prop, pain_point, social_proof, urgency, education, comparison
- `hook_type`: question, statistic, testimonial, provocative_claim, scenario, direct_benefit
- `cta_type`: try_free, book_demo, learn_more, see_how, start_saving_time, watch_video
- `tone`: clinical, warm, urgent, playful, authoritative, empathetic

**Visual layer** (how the ad looks):
- `visual_style`: photography, illustration, screen_capture, text_overlay, mixed_media, ugc_style
- `subject_matter`: clinician_at_desk, patient_interaction, product_ui, abstract_concept, lifestyle, before_after
- `color_mood`: brand_primary, warm_earth, cool_clinical, high_contrast, muted_natural, bold_accent
- `text_density`: headline_only, headline_subhead, detailed_copy

**Extended dimensions** (added after the first regression run revealed gaps):
- `contains_specific_number`: bool — "2 hours saved" vs "save time"
- `shows_product_ui`: bool — is the actual JotPsych interface visible?
- `human_face_visible`: bool — does a person appear?
- `social_proof_type`: peer, testimonial, stat, none
- `copy_length_bin`: short, medium, long

Each dimension is MECE — Mutually Exclusive, Collectively Exhaustive. An ad's hook type is *one* of those six values, not two. This is enforced in the taxonomy prompt with explicit boundary rules: "statistic wins over direct_benefit if a specific number is present," "warm = warm-colleague energy; empathetic = I-feel-your-pain energy," "patient_interaction requires a patient visibly present in the scene."

### Why Claude does the tagging, not a rules engine

Every ad gets tagged by Claude (Anthropic's language model) in batches of 15. The prompt includes the full taxonomy definitions, the MECE boundary rules, and the `VALID_VALUES` enum for each field. We considered a rules-based classifier — regex for numbers, keyword matching for tone — but ad creative is inherently ambiguous. A headline like "Your patients deserve your full presence" could be a value_prop or a pain_point depending on context. Claude resolves these ambiguities using judgment, which is what we want.

The risk is inconsistency. Claude might tag the same ad differently on two runs. We mitigate this three ways:

1. **VALID_VALUES enforcement.** The `CreativeTaxonomy` model has a `VALID_VALUES` dict and a `validate_values()` method. After Claude returns tags, any out-of-vocabulary value gets logged and corrected via `TAXONOMY_CORRECTIONS` (a hardcoded mapping of common Claude drift patterns).

2. **Tagging confidence scoring.** Claude reports a 0.0–1.0 confidence for each dimension. The regression can filter out rows where tag confidence is below a threshold, ensuring only cleanly-tagged ads contribute to coefficients. In practice we haven't needed to use this filter yet because confidence is consistently high on the core dimensions, but the infrastructure is there for when it matters.

3. **Audit tooling.** `scripts/audit_taxonomy.py` samples 50 tagged ads, exports them as a CSV with one row per ad and one column per taxonomy dimension, and generates a distribution report. This is for manual MECE review — a human checking whether Claude's labels match reality.

### The initial export

The first run exported 432 ads from Meta's Graph API. Of those, 144 had conversion data. Total historical spend: $304K. The export enriches each ad with copy from `asset_feed_spec.bodies/titles` (not the deprecated `creative.title/body` fields — this was a bug that initially left 390 ads without headlines). Rate limiting is handled with exponential backoff.

These 432 tagged ads seed the regression. They're the starting corpus from which all initial learnings emerge.

### Portfolio analysis and playbook generation

After tagging, Claude analyzes the full tagged corpus to produce a portfolio analysis: the top 5 performing creative patterns, the 5 worst, 6 untested combinations, and 5 concrete creative briefs for the next batch. This is saved as `data/existing_creative/playbook.md` — a human-readable document that captures the state of creative knowledge at any point in time.

The playbook serves two roles: it's a reference document for the team, and it's machine-readable input for the brief extraction step in generation.

---

## Stage 2: Regression — Finding What Actually Works

### What it does

The regression model takes the tagged ads with their performance data and runs a linear regression to isolate which creative elements drive lower cost-per-first-note. The output is a set of coefficients: "ads with `hook_type=statistic` cost $X less per conversion than the baseline," "ads with `tone=playful` cost $Y more."

### Why linear regression and not something fancier

We chose OLS/WLS linear regression deliberately, despite having access to gradient boosted trees, neural nets, or any other model. Three reasons:

1. **Interpretability.** The entire downstream pipeline — memory, playbook rules, generation prompts — needs to consume regression output as human-readable insights. "hook_type_statistic has coefficient -42.3" means "ads with statistical hooks cost $42.30 less per conversion." A random forest feature importance score doesn't tell you direction, magnitude, or interaction effects in a way that translates to copy instructions.

2. **Small sample size.** With 141 observations (ads with enough spend and impressions to be meaningful) and ~60 one-hot features, we're already in dangerous overfitting territory. A more complex model would memorize the training data. Linear regression with proper validation (holdout, bootstrap, VIF) at least makes overfitting visible and quantifiable.

3. **Coefficient stability matters more than prediction accuracy.** We don't need the model to predict CpFN for a new ad to three decimal places. We need it to reliably tell us that statistical hooks outperform direct benefit hooks. Stability of rank ordering matters more than R² on a test set.

### Feature encoding

Categorical features (`hook_type`, `tone`, `message_type`, etc.) are one-hot encoded with `drop_first=True`. This means one category per dimension is the implicit baseline. The coefficient for `hook_type_statistic` is the marginal effect of using a statistic hook *relative to the dropped baseline category*. Boolean features (`uses_number`, `shows_product_ui`, etc.) are passed through directly. Numerical features (`days_since_first_run`) are included as-is. Zero-variance columns are dropped before fitting.

### Weighted Least Squares with temporal decay

Ad performance data has a temporal dimension. A creative element that worked six months ago may not work today — audience fatigue, seasonal effects, and competitive dynamics all shift. Raw OLS treats a January ad and a March ad as equally informative. That's wrong.

We use Weighted Least Squares (WLS) with exponential decay weights:

```
weight(ad) = exp(-λ × days_since_last_activity)
```

where λ is calibrated from a half-life parameter (default 30 days). An ad that ran yesterday gets full weight. An ad from 30 days ago gets half weight. An ad from 90 days ago contributes almost nothing. Weights are normalized to sum to n (the sample size) so the effective sample size interpretation is preserved.

The implementation transforms both X and y by `sqrt(weights)` — this is the standard WLS formulation that converts the weighted problem into an unweighted OLS problem on the transformed data.

### Interaction terms

Creative elements don't work in isolation. A statistical hook might work beautifully with an empathetic tone but terribly with a playful tone. Main effects alone can't capture this. The model generates interaction terms — products of boolean features with categorical dummies (e.g., `uses_number × hook_type_statistic`) and boolean-boolean pairs.

But interactions explode the feature space. With 60 base features, all pairwise interactions would be ~1800 columns on 141 rows. Unworkable. So we cap at 20 interaction terms, selected by absolute correlation with the target variable. This is a deliberate simplicity constraint: only the interactions that show the strongest univariate signal get included.

### Rolling window regression for fatigue detection

In addition to the main WLS regression, we run a separate OLS regression on only the last 30 days of data (no decay weights — everyone in the window is weighted equally). This produces a "recent-only" coefficient set that we compare against the all-time coefficients.

If a feature's recent coefficient is substantially worse than its all-time coefficient, that's a fatigue signal. The creative element is wearing out. This comparison powers the `FatigueAlert` system in memory.

### Validation: why we don't trust raw R²

The initial regression on 432 ads produced R² = 0.34. That sounds okay until you realize there are ~60 features on 141 usable observations. Adjusted R² was 0.14. Test-set R² (80/20 holdout) was -1.0 — the model was worse than predicting the mean. The model was massively overfit.

This is expected and fine. The point of running regression on sparse data isn't to build a predictive model. It's to identify which coefficients are stable enough to act on, and which are noise. The validation infrastructure exists to separate signal from noise, not to optimize prediction accuracy.

**Holdout validation.** 80/20 train/test split (fixed `random_state=42` for reproducibility). The model is fit on the training set, and test-set R² is reported. If test R² < 0.15, the playbook translator returns empty — the system falls back to editorial memory (human reviewer preferences) rather than trusting statistical coefficients.

**Bootstrap confidence intervals.** 1000 resamples with replacement. For each feature, we collect the coefficient from each resample and compute the 2.5th and 97.5th percentile. If the 95% CI excludes zero, the feature has a statistically meaningful effect. If the CI spans zero, the feature might be noise.

**Coefficient stability.** 10 runs on random 80% subsamples. For each feature, we compute the standard deviation of its coefficient across runs. High variance = unreliable. We flag features where std > 30% of the absolute coefficient as unstable.

**Confidence tiers.** These three validation checks combine into a four-tier confidence system:

| Tier | Criteria | Downstream treatment |
|------|----------|---------------------|
| **High** | Bootstrap CI excludes 0 AND stability std < 30% of |coeff| | Flows into playbook rules and generation context |
| **Moderate** | Bootstrap CI excludes 0 (but less stable) | Flows into playbook rules with caveat |
| **Directional** | p-value < 0.10 | Visible in dashboards, not used for generation |
| **Unreliable** | Everything else | Excluded from all downstream use |

This tier system is the bridge between raw statistics and safe downstream action. We'd rather miss a real insight (false negative) than act on a spurious one (false positive), because acting on noise wastes ad budget.

### Diagnostics

The regression reports Durbin-Watson (serial correlation in residuals), condition number (multicollinearity severity), and per-feature VIF (Variance Inflation Factor). High VIF on a feature means it's collinear with other features and its individual coefficient can't be trusted — even if the overall model fits well.

---

## Stage 3: Memory — Making Knowledge Compound

### The problem memory solves

Without memory, every generation cycle starts from scratch. The regression produces coefficients, but coefficients are numbers — they don't tell a copywriter (or a language model acting as one) *how* to write better ads. And the regression only captures statistical relationships; it doesn't capture the editorial preferences of the specific humans reviewing the ads.

Memory is the translation layer. It turns raw signal (regression coefficients, review verdicts, deployment history) into structured context that the generation pipeline can actually use.

### Three-layer architecture

We split memory into three distinct layers because they have different data sources, different update cadences, and different failure modes.

#### Layer 1: Statistical Memory

**Source:** Regression coefficients, performance data.

**Contains:**
- `PatternInsight` — one per significant feature. Includes the coefficient value, confidence tier, trend direction (improving/stable/declining, computed by comparing recent vs. historical coefficients), number of cycles the pattern has been significant, and 2-3 example ads that exhibit the pattern.
- `FatigueAlert` — features whose recent (30-day rolling window) coefficient is substantially worse than their all-time coefficient. This is how the system detects creative wear-out.
- `InteractionInsight` — significant interaction terms translated to "X works well with Y" or "X works poorly with Y."
- Coefficient history — each regression run's coefficients are logged, enabling trend detection across cycles.

**Why trends matter:** A feature might have a significant negative coefficient (good for CpFN) but be trending toward zero. That means it's losing effectiveness — possibly due to audience fatigue. The system catches this before the coefficient crosses zero and the damage is done.

#### Layer 2: Editorial Memory

**Source:** Human review decisions (approvals, rejections, review chips, voice notes).

**Contains:**
- `ApprovalCluster` — groups of approved ads that share a common taxonomy signature (same hook_type + message_type + tone). Instead of storing every approved ad individually, we cluster them to find patterns. Each cluster has a representative ad and a count. "Nate has approved 8 ads with question hooks + empathetic tone + warm visuals" is more useful to the generator than a list of 8 individual ads.
- `RejectionRule` — generalized rules extracted from repeated rejections. If multiple ads with `tone=playful` and `message_type=urgency` get rejected, the system infers a general rule: "Don't combine playful tone with urgency messaging." This is more actionable than individual rejection notes.
- `ReviewerProfile` — per-reviewer patterns. Nate's preferences might differ from Jackson's. The profile tracks approval rates per taxonomy dimension, common rejection reasons, and explicit preferences extracted from voice notes.
- Synthesized preferences from voice notes — weekly review sessions are recorded, transcribed via Whisper, and run through Claude to extract structured preferences. These accumulate in the editorial memory over time.

**Why editorial memory is separate from statistical memory:** A reviewer might reject an ad that the regression says should perform well. That's not a contradiction — it means the ad has a quality problem that performance data hasn't caught yet (maybe it looks AI-generated, or it's off-brand, or the tone is subtly wrong). Editorial memory captures *quality* judgments. Statistical memory captures *performance* outcomes. Both feed into generation, but they're independent signals.

#### Layer 3: Market Memory

**Source:** Deployment history, competitive observations.

**Contains:**
- `CombinationStats` — how many times each creative combination (hook_type + tone + cta_type) has been deployed. This powers the explore/exploit logic in variant selection.
- `least_tested_combinations` — combinations that have been deployed fewer than 3 times. These are candidates for exploration.
- `PlatformModifier` — platform-specific adjustments (e.g., "Meta story format prefers bold visuals").
- `CompetitiveObservation` — manual notes about competitor creative strategy.

**Why track deployment counts:** If you've run `question + empathetic + learn_more` 15 times and it always works, that's great — but you've saturated that combination. Continuing to generate more of it risks fatigue and misses the opportunity to discover other winning combinations. Market memory prevents the system from converging on a single winning formula.

### Memory decay and archiving

Knowledge has a shelf life. An insight from 90 days ago may reflect a market that no longer exists. The memory system implements two mechanisms:

1. **Confidence tier decay.** Pattern insights older than 60 days get their confidence tier downgraded one step (high → moderate → directional → unreliable). This means old insights gradually lose influence over generation without being deleted.

2. **Archiving.** Patterns that are both old (>90 days) and low confidence (unreliable or insignificant) get moved to `data/memory/archive/`. They're not deleted — they're preserved for historical analysis — but they no longer influence generation.

The decay parameters (60-day downgrade, 90-day archive) are calibrated to our ad cycle cadence. At $15-20K/month spend, the creative portfolio turns over roughly every 60-90 days anyway.

### The GenerationContext: how memory becomes a prompt

All three memory layers get flattened into a single `GenerationContext` object with a `to_prompt_block()` method. This produces a structured markdown block that gets injected into the copy agent system prompts:

```
## Creative Intelligence Context

### What works (from regression — act on these):
- [HIGH confidence] Statistical hooks lower CpFN by ~$40. Lead with a specific number.
  Example: "2 hours of charting — gone. Every day."

### What to avoid:
- [MODERATE confidence] Playful tone + urgency messaging increases CpFN.
- Reviewer Nate has rejected 4 ads with generic "revolutionize" language.

### Fatigue warnings:
- "question hook + empathetic tone" has been declining over the last 3 cycles.

### Exploration opportunities:
- "provocative_claim + warm + see_how" has never been tested.

### Reviewer preferences:
- Jackson prefers short headlines (<8 words) with specific numbers.
- Nate dislikes any ad that leads with the product name.
```

The framing is deliberately "inspired by, don't copy verbatim." Early versions used directive language ("USE these patterns") which caused the generator to produce repetitive variants that all converged on the same winning formula. The current framing treats insights as creative input, not rigid constraints.

### The Playbook Translator: coefficients to human language

Raw coefficients are useless to a language model writing ad copy. "hook_type_statistic: -42.3" means nothing to the HeadlineAgent. The `PlaybookTranslator` calls Claude to convert each significant coefficient into a `PlaybookRule` — a natural-language instruction with a good example, a bad example, and the underlying reasoning.

For instance, the coefficient `hook_type_statistic: -42.3` becomes:

> **Rule:** Lead headlines with a specific number — "2 hours of charting saved" beats "Save time on charting."
> **Good example:** "83% of therapists say paperwork is their biggest frustration"
> **Bad example:** "Are you tired of paperwork?"
> **Confidence:** HIGH

The translator only runs on high and moderate confidence features. Directional and unreliable features are excluded. If the regression's test R² is below 0.15, the translator returns nothing — the system acknowledges it doesn't have reliable statistical knowledge yet and falls back to editorial memory only.

Playbook translation runs once per regression cycle, not per generation request. Claude API calls are expensive, and the insights don't change between individual generation runs within the same cycle.

---

## Stage 4: Generation — From Insight to Ad Variant

### Overview

Generation takes a creative brief and produces a set of ad variants — each with a headline, body copy, CTA, taxonomy tags, and a rendered image. The pipeline has four components: copy agents, quality filter, variant matrix, and template rendering.

### Multi-agent copy generation

Copy is generated by three specialized Claude agents, each responsible for a different element:

- **HeadlineAgent** — produces 40-character Meta-optimized headlines. System prompt includes JotPsych brand voice guidelines, gold standard headline examples from the best-performing historical ads, the brief's hook strategy and emotional register, and the `GenerationContext` prompt block.
- **BodyCopyAgent** — produces primary text (up to ~280 chars after truncation). Same context injection pattern.
- **CTAAgent** — produces 20-character button text. Simpler prompt; primarily brief-driven.

**Why three agents instead of one?** Early versions (v1) used a single Claude call to generate the entire ad — headline, body, CTA, and image prompt all at once. The output was mediocre across the board. Splitting into specialists lets each agent focus on its constraint (headline must be punchy and short; body can be longer and more explanatory; CTA must be a clear action verb). Each agent also gets tailored few-shot examples that wouldn't fit in a single monolithic prompt.

The agents are injected with `GenerationContext.to_prompt_block()` — the structured memory output described above. This is how regression insights, reviewer preferences, and fatigue warnings flow into actual copy output. A headline agent that knows "statistical hooks lower CpFN by $40" will generate more headlines like "2 hours saved daily" and fewer like "Transform your practice."

### Gold standard examples

Each copy agent's system prompt includes 5-10 examples of the best real JotPsych ad copy, pulled from historical ads with the lowest CpFN. These serve as a quality anchor. Without them, Claude drifts toward generic marketing language. With them, the output stays closer to what has actually worked for this specific product and audience.

The gold standards are hardcoded in `copy_agents.py` (not dynamically loaded) because they change rarely and need careful curation. We don't want the regression to automatically promote a statistically good headline into the gold standards if it's stylistically wrong.

### Quality filter

Every generated copy line passes through `CopyQualityFilter` before reaching the variant matrix. The filter catches:

- **AI tells** — 23 patterns that signal AI-generated text: "revolutionize," "leverage," "streamline," "cutting-edge," "game-changer," "empower," "unlock," etc. These are words real clinicians never use and that immediately signal "this is an ad written by a machine."
- **Generic phrases** — 12 patterns that are technically correct but convey nothing specific: "take your practice to the next level," "the future of healthcare," "don't miss out," etc.
- **Character limits** — headline ≤ 40 chars, CTA ≤ 20 chars. Body copy has no hard limit (Meta allows ~2200 chars) but gets truncated at sentence boundaries at render time.

The filter was initially too aggressive — it rejected all body copy over 125 characters, which is the above-the-fold visible length on Meta but not a real constraint. We relaxed the body limit and kept the filter focused on genuine quality signals.

### Variant matrix: explore/exploit

Given a set of generated headlines, bodies, and CTAs, the variant matrix selects which combinations to actually produce as final variants. This is where the regression coefficients directly influence which ads get made.

**The explore/exploit framework.** 80% of variant slots are exploit (use what we know works). 20% are explore (try things we haven't tested). This ratio is hardcoded as `EXPLOIT_RATIO = 0.8`.

**Exploit selection.** For each possible headline × body × CTA combination, the matrix computes a predicted score using the regression coefficients. The score is the sum of main effect coefficients for the taxonomy features present in the variant, plus any interaction term coefficients that match. Higher predicted score = lower expected CpFN.

But predicted score alone would cause all exploit variants to be the same combination — whichever one has the best regression prediction. Two safeguards prevent this:

1. **Diversity cap.** If a variant shares 3 or more of its 4 core taxonomy dimensions (hook, message, tone, CTA) with an already-selected variant, it's deprioritized.
2. **Fatigue penalty.** Features that have been heavily deployed recently get a penalty of 15% per recent cycle. This is additive to the predicted CpFN (higher CpFN = worse), so frequently-used elements gradually lose their exploit advantage and make room for alternatives. The penalty is per-cycle, not per-deployment, so running a feature in many ads within one cycle counts as one cycle of usage.

**Explore selection.** The remaining 20% of slots go to combinations that maximize an exploration score — defined as the count of taxonomy features in the combination that have been deployed fewer than 3 times total. This isn't random exploration. It's systematic: we specifically seek out the least-tested corners of the creative space.

**Fallback.** When no regression data exists (cold start), the matrix falls back to `_select_diverse_random()`, which enforces taxonomy diversity without any scoring.

### Template rendering: Playwright, not AI

Ad images are rendered from HTML/CSS templates using Playwright (headless Chromium), not generated by an AI image model. This was a deliberate Phase 1 decision.

**Why templates instead of AI images:**

1. **Determinism.** A template produces the exact same image every time given the same inputs. There's no randomness, no "this looks slightly off today" problem. This gives the regression clean data — when an ad's performance changes, we know it's not because the image was rendered differently.

2. **Brand consistency.** The templates use JotPsych's actual brand fonts (Archivo for headings, Inter for body), exact brand colors (midnight #1C1E85, sunset glow #FD96C9, warm light #FFF2F5), and real logo assets. An AI-generated image uses *approximate* brand colors and can't render a specific typeface.

3. **Speed.** Rendering an HTML template takes ~200ms. Generating an AI image takes 5-30 seconds and costs money per generation. For rapid iteration on copy variants, templates are dramatically faster.

4. **No AI slop.** The hard constraint from the team is that creative must not look AI-generated. Current image models (Gemini, DALL-E, Midjourney) can produce impressive images, but they have failure modes that are obvious to a human reviewer: wrong hand anatomy, fake UI text, uncanny lighting. Templates eliminate this entire category of risk.

**Template system design.** There are 9 template variants across 3 format families:

- **Meta feed (1080x1080):** headline_hero, split_screen, stat_callout, testimonial
- **Meta story (1080x1920):** full_bleed, swipe_up (with CSS @keyframes animations)
- **Google Display (1200x628):** responsive
- **Additional:** carousel card (1080x1080), leaderboard (728x90), skyscraper (160x600)

Each template supports 4 color schemes (light, dark, warm, accent) mapped from the taxonomy's `color_mood` dimension. The `TemplateSelector` maps taxonomy tags to templates — statistical hooks get stat_callout, testimonial hooks get the testimonial template, etc. — and regression coefficients can override the color scheme selection toward whichever `color_mood` has the best coefficient.

**Rendering pipeline details.** The template renderer writes the fully-substituted HTML to a temp file, navigates Playwright to `file://` path (not `page.set_content()`, which sets the origin to `about:blank` and blocks local file loading), captures a screenshot, and returns the PNG path. Body copy is truncated at sentence boundaries (max 280 chars) before rendering to prevent CSS overflow artifacts. Each `render()` call opens and closes its own browser context to avoid stale asyncio event loop references.

AI image generation (Gemini Imagen, DALL-E, Flux) is scaffolded for Phase 2 but intentionally not active. The regression will eventually tell us whether template-rendered or AI-generated images perform better — but we need clean template baselines first.

---

## Stage 5: Review — Human Judgment as Structured Data

### The core problem

The review stage needs to accomplish two things simultaneously:

1. **Filter.** Nate and Jackson decide which ads are good enough to deploy. This is a quality gate.
2. **Learn.** Every approval and rejection is training data for the memory system. The system needs to extract *why* an ad was approved or rejected, not just the binary verdict.

These goals are in tension. If the review UI is too complex (asking for detailed reasons on every ad), reviewers will stop using it. If it's too simple (just approve/reject), the system can't learn.

### The Tinder-style review interface

We solved this by making the core interaction as fast as possible — under 3 seconds per ad — and making the enrichment step optional.

**Tinder mode** presents one ad variant at a time, full-screen. The reviewer sees the rendered ad image (PNG from template, or an iframe preview of the live HTML template), the headline, body copy, and CTA. They swipe left (reject) or right (approve) — or press ← / → on keyboard. The verdict records instantly. No modal, no form, no friction.

After the verdict records, a chip panel slides up from the bottom. These are the optional enrichment chips — predefined reasons for the verdict that map directly to taxonomy dimensions:

**Rejection chips (12):**
- "Headline too generic" → maps to `hook_type`, implies `uses_number: False`
- "Wrong tone" → maps to `tone`
- "Feels AI-written" → maps to `tone`
- "Weak value prop" → maps to `message_type`
- "CTA unclear" → maps to `cta_type`
- "Visual off-brand" → maps to `visual_style`
- "Too long" → maps to `text_density`
- "Needs a number" → implies `uses_number: True`
- "More empathetic" → implies `tone: empathetic`
- "More urgent" → implies `tone: urgent`
- "Show the product" → implies `subject_matter: product_ui`
- "Needs social proof" → implies `uses_social_proof: True`

**Approval chips (5):**
- "Great headline" → `hook_type`
- "Love the tone" → `tone`
- "Strong CTA" → `cta_type`
- "Good visual" → `visual_style`
- "Perfect length" → `text_density`

### Why chips instead of free text

Free-text review notes require NLP to parse. "The headline is boring and generic" needs to be mapped to `hook_type` by a language model, which introduces latency, cost, and error. Chips provide structured signal for free — each chip has a `dimension` field linking it to a taxonomy dimension and an `implied` dict specifying taxonomy field overrides.

When a reviewer taps "Needs a number," the system immediately knows: this ad should have had `uses_number: True` in its taxonomy. That's a direct signal to the memory builder: the reviewer prefers ads with specific numbers. No NLP required. No ambiguity.

Chips are additive, not exclusive. The reviewer can tap none (just the verdict), one, or several. Each chip adds one data point. Over hundreds of reviews, the chip frequency distributions build a detailed reviewer preference profile.

### Review duration tracking

Every review card tracks `review_duration_ms` — from when the card first renders to when the verdict is submitted. This serves two purposes:

1. **Quality signal.** Ads that take longer to evaluate might be ambiguous or confusing. Consistently long review times for a particular taxonomy combination could indicate a creative problem.
2. **System calibration.** We report median review time (not average — average was inflated by idle time when reviewers left the tab open between sessions). This tells us whether the review UI is actually achieving the "under 3 seconds" goal.

### Gallery mode as alternative

Not everyone prefers the one-at-a-time Tinder experience. Gallery mode shows a multi-select grid of ad cards. Reviewers can scan the full queue, select multiple ads, and batch-approve or batch-reject with a single action. Chips are presented in a modal after the batch verdict.

Gallery mode is better for experienced reviewers who can quickly scan and identify the obvious winners and losers. Tinder mode is better for careful evaluation of each variant individually.

### Three-tier asset rendering

The review UI handles three rendering states for each variant:

1. **PNG available.** The template renderer produced a valid image file (>1KB, real image extension, file exists on disk). Display the PNG directly.
2. **Template preview via iframe.** No PNG, but the variant has a `template_id`. The renderer produces a fully-substituted HTML string with HTTP `/brand/` paths (not `file://`), which is served by the dashboard and displayed in a scaled iframe. The reviewer sees the live template at the correct dimensions.
3. **Text-only fallback.** Neither PNG nor template available (legacy variants, corrupt assets). Display headline + body + CTA as formatted text with a styled placeholder icon.

This three-tier approach was necessary because the asset pipeline evolved during development. Early variants had corrupt Gemini images (356-byte files). Some had video paths. The review UI needed to handle all of these gracefully rather than showing broken image icons.

### How review data flows back into the system

Approved and rejected variants are saved with their verdicts, chips, reviewer ID, and review duration. On the next generation cycle, the memory builder picks up these signals:

1. **Approval clustering.** Groups approved ads by their taxonomy signature (hook_type + message_type + tone + uses_number). If 6 approved ads share a signature, that's an `ApprovalCluster` with count=6 — strong signal that this combination works.

2. **Rejection rules.** If multiple rejected ads share a tone × message_type combination, and they have review notes or chips, the system extracts a generalized `RejectionRule`: "Don't combine playful tone with urgency messaging."

3. **Reviewer profiles.** Per-reviewer chip frequency distributions. If Nate consistently taps "Needs a number" on rejections, his profile records a preference for `uses_number: True`. This feeds into the `GenerationContext` as reviewer-specific guidance.

4. **Direct feedback injection.** The most recent approved ads (with full copy + taxonomy) are included as positive examples in the copy agent prompts: "Generate more like these." Recent rejections are included as negative examples: "Avoid these patterns."

This is how the loop closes. Review verdicts → memory → generation context → better ads → review verdicts → richer memory → even better ads.

---

## Why This Order Matters

We built and refined these stages in a specific order, and the ordering was deliberate.

### Regression first, not generation first

The natural instinct is to start building the generator and iterate on output quality. We resisted this. Without the regression and taxonomy infrastructure, there's no way to know *what* makes a good ad versus a bad one. You're iterating on vibes. We wanted quantitative signal driving generation decisions from day one.

### Memory before deployment

Most ad systems close the loop at the deploy/track level — deploy ads, check performance, make more of what works. That's a slow feedback loop (days to weeks for statistical significance). Memory makes the loop faster by incorporating human review signal immediately, within the same cycle. A reviewer rejects 5 ads in 10 minutes, and the next generation run already knows to avoid those patterns. No deployment required.

### Templates before AI images

This was the most counterintuitive decision. The project brief explicitly mentioned AI image generation (DALL-E, Gemini Imagen) as a core capability. But we pushed it to Phase 2 because:

1. AI image quality was inconsistent and frequently failed the "no AI slop" constraint
2. Templates give the regression clean, controlled data — isolating copy effects from image-quality noise
3. Template rendering is 100x faster than API image generation
4. Fixing a template bug takes minutes; fixing an AI generation bug requires prompt archaeology

Once the regression has clean baselines from template-rendered ads, we can introduce AI images as a controlled experiment and measure whether they improve performance. Without baselines, we'd never know.

### Review UI before API integration

We built a polished review dashboard before wiring up Meta/Google write APIs. This seems backwards — why build a review UI when there's nothing deployed to review? Because:

1. The review UI is how we validate generation quality before deploying anything
2. Review verdicts feed memory, which improves generation, creating a self-improvement loop that runs without any deployed ads
3. Getting the review interaction design right (chips, Tinder mode, duration tracking) before launch means we capture structured signal from the very first real review session

---

## Design Principles

### Interpretability over accuracy

Every technical choice prioritizes understanding over prediction power. Linear regression over gradient boosting. Confidence tiers over p-value thresholds. Natural language playbook rules over raw coefficients. The system is designed for humans to understand why it's making the recommendations it makes.

### Fail safe, not fail silent

When the regression can't be trusted (test R² < 0.15, not enough observations for validation), the system falls back to editorial memory rather than using unreliable coefficients. When a taxonomy tag has low confidence, it's flagged but still included — the regression's confidence tier system will naturally downweight features built from noisy tags. When a template renders incorrectly, the review UI shows an iframe fallback or text-only mode rather than a broken image.

### Structured signal wherever possible

Free text is expensive to parse. Every user-facing interaction is designed to produce structured data: chips map to taxonomy dimensions, verdicts are binary, review duration is a number. Voice notes are the one exception — they're unstructured — but even those get batch-synthesized into structured `ReviewerPreference` objects.

### Memory compounds, generation adapts

The system is designed so that the *memory* gets smarter over time, and the *generator* is stateless — it's a function from (brief + context) → variants. The intelligence lives in the context, not in the generator's architecture. This means the generator can be swapped out (different LLM, different prompting strategy, different rendering engine) without losing accumulated knowledge.

### Creative divergence, not convergence

The hardest failure mode for a learning system is convergence — you find one winning formula and keep making variations of it until the audience gets bored. Every mechanism in the system pushes against convergence:

- **Explore/exploit 80/20 ratio** forces 20% of variants to test untested combinations
- **Fatigue penalty** taxes heavily-deployed features at 15% per cycle
- **Market memory** tracks deployment counts to identify over-tested areas
- **Confidence tier decay** downgrades old insights so they don't permanently dominate
- **"Inspired by" framing** in the generation context tells the LLM to use insights as inspiration, not as templates to copy

---

## What We Deliberately Did Not Build

### No real-time bidding or budget optimization

Meta and Google have better data and better algorithms for audience targeting and bid optimization than we could build. We accepted their black boxes and focused exclusively on the creative lever — the one thing the platforms can't optimize because they don't understand the product.

### No database (yet)

All data is stored as flat JSON files in `data/`. This is a conscious simplicity choice. At our current volume (~500 ads, ~100 variants per generation cycle), file I/O is instant and debugging is trivial (you can `cat` any file and see exactly what the system knows). We'll migrate to PostgreSQL when concurrent writes or volume demands it, but the store layer has a clean interface that makes the swap straightforward.

### No auto-deploy

Even when the Meta write API is wired up, the plan is human-in-the-loop for deployment decisions until we trust the model. An ad the regression predicts will perform well might still be off-brand or tactically wrong. The review gate exists to catch these.

### No creative testing infrastructure beyond A/B

We don't have multi-armed bandits, Thompson sampling, or sophisticated experimental design. The meta/Google platforms handle ad-level optimization internally. Our "testing" is the natural variation from generating 12+ variants per brief and letting the platforms' delivery algorithms allocate impressions.

---

## Known Limitations and Open Problems

### Overfitting at current data volume

141 usable observations with ~60 features is underpowered. The confidence tier system makes this *safe* (we don't act on unreliable coefficients) but not *useful* (most coefficients are unreliable). This resolves naturally as more ads are deployed and tracked. Every deployed ad adds a row to the regression.

### Attribution uncertainty

The primary conversion event (first note completion) is tracked via Meta's pixel and Google's tag, but 2FA broke Google's tag, and Meta's view-through attribution double-counts with Google. The discovery survey is treated as canonical but it's self-reported. The regression inherits whatever attribution errors exist in the underlying data.

### Taxonomy consistency across time

If Claude drifts in how it interprets taxonomy boundaries (tagging something as `warm` today that it would have tagged `empathetic` yesterday), the regression sees noise. The `TAXONOMY_CORRECTIONS` dict and `VALID_VALUES` enforcement help, but don't guarantee perfect consistency. The audit tooling exists to detect drift; using it regularly is an operational discipline, not an automated check.

### No causal identification

The regression finds correlations, not causal effects. If `hook_type_statistic` has a negative coefficient, it might be because statistical hooks genuinely cause lower CpFN, or because the ads with statistical hooks happened to run during a week with better audience conditions. We can't instrument randomized experiments within the engine — the platforms' delivery algorithms introduce confounding. We mitigate this by using temporal decay (recent data weighted more, reducing seasonal confounding) and interaction terms (identifying which combinations work, not just individual elements), but true causal identification would require a randomized controlled trial at the campaign level.

### Creative quality is hard to quantify

The quality filter catches obvious AI slop, but there's a huge gap between "not obviously AI-written" and "genuinely good copy." The review gate is the quality floor. The system has no automated metric for creative quality beyond "did it pass the filter" and "did a human approve it." Building a quality scoring model is a potential future workstream but requires a substantial corpus of human-rated examples.

---

*Last updated: 2026-03-27*
*Authors: Aryan Jain*
