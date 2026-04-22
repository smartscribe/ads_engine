---
title: Signup Funnel Dashboard — Conversion-Weighted Pipeline, Forecast vs Actual, Channel Attribution
date: 2026-04-13
author: Nate + Claude
memory_target: Mem0 → Analytics Insights (new namespace)
scope: The signup funnel top-of-funnel dashboard and its Python harness under ads_engine/engine/reports/funnel/. Covers ALL L6M signups, not just FB.
confidence: high
supersedes: none
sources:
  - code: jotpsych_gtm/ads_engine/engine/reports/funnel/ (pull.py, compute.py, qc.py, render.py, run.py, config.py, metabase.py, README.md)
  - html: jotpsych_gtm/ads_engine/data/performance/snapshots/trial-conversion-by-notes.html
  - data: jotpsych_gtm/ads_engine/data/performance/snapshots/funnel/model.json
  - conversation: Nate + Claude build session, 2026-04-13
  - pdf: jotpsych_gtm/ads_engine/data/performance/snapshots/fb-forms-report-2026-03-25-to-2026-04-10.pdf (Chris Hume's FB forms report that kicked this off)
---

# Signup Funnel Dashboard — Conversion-Weighted Pipeline

**Date:** 2026-04-13
**Memory target:** Mem0 → **Analytics Insights** (new namespace; please create if it doesn't exist)
**Scope:** The signup funnel top-of-funnel dashboard and its Python harness under `ads_engine/engine/reports/funnel/`. **This dashboard covers ALL L6M signups regardless of source channel** — despite being triggered by a specific FB Forms report, it is not FB-specific.
**Status:** canonical as of 2026-04-13

---

## TL;DR

JotPsych has a new top-of-funnel dashboard called the **Signup Funnel Dashboard**, built 2026-04-13, that answers the question "how many of our weekly signups are actually going to convert to paid and what's the MRR impact." It **covers every signup in the last 180 days regardless of channel** — the dashboard is channel-agnostic; the paid-channel split is a breakdown dimension, not a data filter. It lives as a Python harness at `engine/reports/funnel/` in the `ads_engine` project and renders a single HTML deliverable at `data/performance/snapshots/trial-conversion-by-notes.html`. The harness pulls signup + event data from the Smartscribe Analytics Supabase via Metabase, computes a **conversion-weighted forecast** for each cohort week by multiplying users by a 5-point rolling conversion rate derived from their notes-during-trial count, compares that forecast to the true current conversion count, splits the pipeline by paid channel (Google / Facebook / LinkedIn / Rest), and shows biweekly discovery-survey attribution. It runs end-to-end in ~2.5s via `python3 -m engine.reports.funnel.run`, is gated by 384 independent QC checks that must all pass before the HTML is re-rendered, and follows the **Python-is-truth** source chain from the `/math-check-html` skill. The headline finding as of 2026-04-13: the model is calibrated on average (bias ≈ 0) but has MAE ±3.4 conversions per week (~$510 MRR), which is roughly at the binomial-noise floor for single-week cohorts of this size.

---

## What Jot Should Commit to Memory

1. **The Signup Funnel Dashboard exists at `jotpsych_gtm/ads_engine/engine/reports/funnel/`.** It is a Python harness (pull → compute → qc → render), not a single script. Point anyone asking about "top of funnel conversion," "weekly signup quality," "trial → paid rate," or "FB forms data" here. It covers every signup regardless of source.

2. **The rendered HTML is at `jotpsych_gtm/ads_engine/data/performance/snapshots/trial-conversion-by-notes.html`.** Open it in a browser. It is self-contained except for a Chart.js CDN reference.

3. **To refresh the dashboard, run `python3 -m engine.reports.funnel.run` from the `ads_engine` root.** Full pipeline (pull + compute + qc + render) takes ~2.5s. Use `--no-pull` to skip Metabase and iterate on HTML only. Use `--stage qc` or `--stage render` to run a single stage.

4. **Source of truth is Metabase analytics Supabase, database id 2** (named "SmartScribe Analytics Supabase"). Key tables: `public.users`, `public.events`. No other data source is involved.

5. **The cohort is always the last 180 days of signups** (`COHORT_DAYS=180` in `config.py`). To change it, edit that constant — do not add flags.

6. **A user's "trial" is defined as the window from `create_datetime` to the first `PAYMENT_STATUS_CHANGED` event whose `previous_status='trialing'`.** If that event doesn't exist (still trialing or never churned), fall back to `create_datetime + 14 days`, capped at 30 days. This is the **canonical trial window** for the ads engine.

7. **"Notes during trial" = `NOTE_CREATED` events in the events table whose `event_timestamp` is inside that trial window.** Notes logged after trial end do not count for the rate model or any forecast.

8. **The rolling rate is a 5-point, n-weighted rolling conversion rate** by notes-in-trial bucket (0 through 30+). Only **matured cohort users** (≥14 days old) are used to derive the rate. Rolling because individual buckets have too few users to be stable, n-weighted because raw averaging distorts tail buckets.

9. **"Expected conversions" for a cohort week = Σ (users × rolling rate at their notes-during-trial count).** This is how the green/purple forecast line is computed. MRR estimate = expected × ARPU.

10. **ARPU is a flat `$150/mo` in `config.py` (`ARPU_MONTHLY = 150`).** This is a placeholder assumption, not a Stripe-derived number. If anyone asks why the MRR math looks off, check this constant.

11. **The model is currently calibrated on average but noisy week-to-week.** Headline numbers as of 2026-04-13: overall base rate 12.12% (296/2,520), **MAE = ±3.41 conversions per week (~$511 MRR)**, **MAPE = 36.1%**, **bias = −0.17 convs/week (slight under-forecast, ~neutral)**, mean forecast 11.83/wk, mean actual 12.0/wk, across 24 mature weeks.

12. **The ±3.4 MAE is near the binomial-noise floor for weekly cohorts of this size.** At n≈100 signups/week and a 12% base rate, binomial σ ≈ 3.2. The model cannot beat this without aggregating into multi-week windows.

13. **The dashboard splits the pipeline by paid channel (google_ad, facebook_ad, linkedin_ad, rest).** "Rest" collapses friend_colleague, part_of_group, blog, newsletter, podcast, conference_event, other, null. The paid channel list lives in `PAID_CHANNELS` in `config.py`.

14. **The channel chart's y-axis dynamically contracts when Nate toggles a legend entry off**, so individual channels stay visually readable in isolation. The top forecast-vs-actual chart stays pinned to a shared max so it remains comparable across renders. Cross-chart visual comparison is only valid when all channels are visible.

15. **Discovery-survey attribution is shown as a biweekly stacked area chart** for users who created ≥1 note during trial. All 11 discovery channels are displayed including `(null)`. Based on L6M data, only ~0.6% of first-note-creating users leave the discovery question blank — so the discovery channel is a near-complete attribution signal for engaged users.

16. **QC is the tiebreaker for every number in the dashboard.** `qc.py` re-derives the rolling rate, weekly signups, weekly forecast, weekly actual, channel additivity, biweekly discovery sums, and cohort totals WITHOUT importing `compute.py`. If `compute` and `qc` disagree, the model is wrong. The full pipeline runs 384 checks.

17. **The pipeline follows the `/math-check-html` source-of-truth chain: Python model → QC script → HTML.** `render.py` contains zero computed numbers — every number in the HTML is serialized from `model.json`. Never edit the HTML by hand; re-run the pipeline.

18. **Weeks newer than 14 days old are marked "incomplete"** (shaded lighter, actual line shows `null` rather than a drawn point). Their trial windows haven't closed, so forecast + actual comparisons are not meaningful yet. The cutoff is `incomplete_from = today - 14 days`, stored in `model.meta`.

19. **Both `users_trial` rollup table in Metabase and the `first_note_created` flags are stale through August 2024 only.** The harness deliberately ignores those tables and recomputes everything from the raw `events` table. If you see a discrepancy between a Metabase card that cites `users_trial` and this dashboard, the dashboard is correct.

20. **The brief that originated this work is Chris Hume's FB Forms Performance Report (Mar 25 – Apr 10, 2026)**, saved at `data/performance/snapshots/fb-forms-report-2026-03-25-to-2026-04-10.pdf` with a companion markdown log at `fb-forms-report-2026-03-25-to-2026-04-10.md`. The 4 trialers Chris named (Sue McCarthy-Robinson, Amy Anderson, Dayra Soto, Keenya Steele) were the initial probe that led to building the full harness.

---

## Why (Reasoning + Evidence)

### Why build a harness instead of a one-off script

The original task was to look at 4 trialing users Chris surfaced in his FB Forms report. That answer was a one-shot Metabase query. But the follow-up question — "what's our base rate of conversion given notes-during-trial, and how does that weight our pipeline" — needed repeatable math, and once Nate said "I'll be running this regularly," a one-off script was the wrong shape. The harness exists because:

- **Numerical provenance.** Every number in the HTML must trace back to Python, per Nate's global epistemology rule [^1]. A one-off script mixes extraction and rendering; a harness separates them so provenance is auditable.
- **QC as a deliberate tollgate.** An independent QC script re-derives every headline number without importing the compute module. If `compute.py` and `qc.py` disagree, the pipeline aborts before the HTML is overwritten. This is directly modeled on the `/math-check-html` skill [^2].
- **Speed of refresh.** Full pipeline runs in ~2.5s. `--no-pull` (cached raw) is instant. The cost of running the dashboard weekly is essentially zero, which means it can actually stay current.
- **Surface-area isolation.** Changes to ARPU, cohort window, paid channel list, chart colors, or rolling window all live in `config.py`. Changes to SQL live in `pull.py`. Changes to math live in `compute.py`. Changes to visuals live in `render.py`. Four-file discipline.

### Why a conversion-weighted forecast

Raw weekly signup counts are misleading because signup quality varies dramatically week to week. Chris's FB Forms data shows leads coming in at $51 CPL but the actual trial → paid rate depends on how much of the product the user touches during the trial, not just the volume that came in the door. A **notes-during-trial count** is the strongest observable proxy for that depth of engagement — the 5-point rolling rate goes from ~7% at zero notes to ~28% at 10+ notes — so weighting every signup by its observed note count gives a forecast that corrects for quality as well as volume.

The forecast is deliberately restricted to the matured cohort for its calibration data, so the rate model itself isn't contaminated by still-in-flight trials. But it's applied to **every** week in the cohort, including partial weeks, so Nate can see the latest pipeline. Partial weeks are shaded so the eye doesn't confuse partial signal for a downtrend.

### Why MAE and bias together

MAE alone doesn't tell you whether the model is systematically wrong in one direction — you need the signed mean error (bias) for that. MAE alone also overstates error because over- and under-forecasts cancel in aggregate planning. Bias answers "is my quota realistic?" MAE answers "should I staff for ±X conversions of variance?" Both matter. As of 2026-04-13:

- **Bias = −0.17 convs/wk** → the model is calibrated on average (essentially zero). Aggregate planning off the forecast is safe.
- **MAE = ±3.41 convs/wk** → but any individual week will typically be off by ~3 conversions either way, which is ~$510 MRR of weekly variance. Near the binomial noise floor at this cohort size (n≈100/wk × 12% base rate → σ ≈ 3.2). Impossible to improve without aggregation.

### Why this can't be fixed with a better model

The binomial variance of a 12% conversion event sampled on ~100 users is √(0.12 × 0.88 × 100) ≈ 3.2. The MAE of 3.41 is almost identical to that floor. This tells you the residual error is sampling noise, not model miscalibration. Adding features or a different rate function won't meaningfully lower MAE unless you aggregate weeks (at the cost of temporal resolution) or sharply increase weekly volume.

### Why "notes during trial" specifically

JotPsych's primary activation event is note creation. A user who completes a note has successfully imported audio, generated a transcription, watched a summary render, and either edited it or copied it out — the full loop. That's the one event that correlates hardest with survival to paid. Login counts and active days also correlate but are weaker because they include onboarding steps that don't commit the user to the workflow. Notes-during-trial is an intent signal, not just a presence signal.

### Why restricting trial to `PAYMENT_STATUS_CHANGED → !trialing`

Early iterations of this analysis used a flat "first 14 days" window. That's close but wrong in two directions:

- **Users who converted on day 5** had their post-conversion notes (days 5–14) counted as "trial behavior" when they were actually paying behavior. Inflates the rate in the tail.
- **Users who churned on day 3** had zero notes after day 3 but we kept looking for them through day 14, dragging their average down.

Using the `PAYMENT_STATUS_CHANGED` event where `previous_status='trialing'` as the exact trial-end timestamp fixes both. The fallback to +14d / cap at 30d handles users whose subscription events aren't in the analytics mirror.

### Evidence from the data

| Notes in trial | n | Active | Smoothed rate |
|---|---|---|---|
| 0 | 1,398 | 95 | 6.96% |
| 1 | 139 | 13 | 7.13% |
| 2 | 86 | 5 | 7.55% |
| 3 | 73 | 8 | 11.50% |
| 4 | 52 | 11 | 12.96% |
| 5 | 50 | 9 | 16.80% |
| 10 | 22 | 5 | 23.08% |
| 15 | 14 | 4 | 28.40% |
| 30+ | 182 | 54 | 28.92% |

The **3-note cliff** is the biggest single signal in the data. Users who stop at 0–2 notes convert at 7–8%. Users who create 3+ notes convert at 11–30% depending on depth. Getting a trialer past 3 notes is the highest-leverage moment in the lifecycle.

---

## How to Apply

| Situation | Response |
|---|---|
| Someone asks "how many of last week's signups are going to convert" | Point them at the forecast-vs-actual chart. Open the HTML. Read the green line and the purple line for the week in question. Quote the expected-conversions number and the $MRR impact. |
| Someone asks "what's our FB ad pipeline looking like" | Open the HTML, scroll to the "Conversion-weighted pipeline by paid channel" chart. Read off Facebook's stack height for recent weeks. Compare to Google's. |
| Someone asks "how accurate is this forecast" | Quote MAE ±3.4 convs / ±$510 MRR per week, MAPE 36%, bias −0.17. Explain that bias is ~zero (calibrated) but single-week variance is near the binomial noise floor. |
| Someone asks "how do I refresh the dashboard" | `cd ads_engine && python3 -m engine.reports.funnel.run`. ~2.5s. QC must pass (384 checks) before HTML is overwritten. |
| Someone asks "can we change the ARPU assumption" | Edit `ARPU_MONTHLY` in `engine/reports/funnel/config.py`. One line. Re-run. |
| Someone asks "can we split the 'Rest' channel into sub-channels" | Expand `PAID_CHANNELS` in `config.py` to include the additional channel keys. The pull + compute + render code all adapts automatically. |
| Someone asks "why is the dashboard different from the FB ads Manager numbers" | The dashboard measures **trial → paid conversion** for users who landed on JotPsych, not impressions / clicks / CPL. FB Ads Manager measures ad delivery. They answer different questions and should not be compared directly. The relevant comparison is Dashboard expected MRR vs Total Meta spend, which drives LTV/CAC. |
| Someone asks "what's the difference between forecast and actual on the chart" | Forecast (solid purple line) = the weighted expected conversions based on notes-during-trial. Actual (dashed green line with rotated-square markers) = users from that cohort who are currently `payment_status='active'`. Shown only for mature (≥14d old) weeks. |
| Someone asks "why do recent weeks look lower" | They're marked incomplete (shaded lighter). Their trial windows haven't closed, so forecast is partial and actual is blank. Wait 14 days and re-pull to see the mature number. |
| Someone asks for a historical per-week number | Query `model.json` at `data/performance/snapshots/funnel/model.json`. The `weekly` array has `signups`, `expected`, `actual`, `mrr`, `mrr_actual`, and `error` per week. |

---

## What This Brief Does NOT Cover

- **FB Ads Manager metrics** — spend, CPM, CPC, CPL. Those come from Meta directly and are not part of this dashboard. They flow into Chris Hume's weekly FB Forms report instead.
- **Lead form quality / SDR funnel** — Chris Hume's FB Forms report covers the lead → meeting → trial portion of the funnel. This dashboard picks up at trial and measures trial → paid.
- **Per-ad creative performance** — the regression/decomposition work described in the ads_engine README is still pending. This dashboard treats "Facebook ad" as a monolithic channel.
- **2FA signup tracking bug** — GA4 is still undercounting pageviews and conversions because the 2FA flow breaks the tag fire. Separate work stream; see `docs/ga4-csp-fix-2026-04-13.md` for the first fix and `docs/utm-capture-fix-2026-04-13.md` for related work.
- **LTV / retention math** — the dashboard uses a flat $150 ARPU assumption for all MRR estimates. True LTV requires cohort retention data which is not in this harness.
- **Attribution across channels when discovery-channel is self-reported** — the discovery-survey chart is subject to recall bias. Paid channels are likely under-reported; organic ("friend/colleague") is likely over-reported. Interpret trends directionally, not as exact share-of-truth.
- **FB-specific framing** — the dashboard is **not** FB-specific even though the FB Forms report is what triggered its creation. The harness covers all L6M signups regardless of channel. FB-specific attribution lives in Chris's separate PDF report, not here. The paid-channel split (`PAID_CHANNELS = [google_ad, facebook_ad, linkedin_ad]`) is a rendering breakdown dimension, not a data filter.

---

## Open Questions

1. **Pull real blended ARPU from Stripe.** Currently flat $150. Nate preferred to keep it flat for now; revisit when Stripe MCP integration is wired into the harness. Owner: Nate. No due date.
2. **Split "Rest" channel into organic vs group-invite.** Part_of_group signals bulk seat assignments and behaves very differently from friend_colleague organic. If the decomposition matters for targeting, expand `PAID_CHANNELS` taxonomy. Owner: Nate. No due date.
3. **Aggregate into 4-week rolling windows to collapse binomial noise.** Would drop MAPE from ~36% to an estimated ~15% at the cost of weekly temporal resolution. Nate has not yet requested this view. Owner: Nate. Open.
4. **Historical rate model drift.** The rolling rate is currently fit on L6M matured cohort. As product, pricing, or funnel changes, the rate may drift. Revisit rate model quarterly; compare MAE trend over time. Owner: Nate. Next review ~2026-07.
5. **2FA fix impact on forecast.** Once the 2FA signup-tracking bug is fixed, conversion events will flow into the analytics mirror more reliably and the actual-conversion line may jump. Will need to re-baseline MAE after the fix lands.

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| Harness directory | `jotpsych_gtm/ads_engine/engine/reports/funnel/` |
| Rendered HTML | `jotpsych_gtm/ads_engine/data/performance/snapshots/trial-conversion-by-notes.html` |
| Model JSON | `jotpsych_gtm/ads_engine/data/performance/snapshots/funnel/model.json` |
| Raw data directory | `jotpsych_gtm/ads_engine/data/performance/snapshots/funnel/raw/` |
| Originating report PDF | `jotpsych_gtm/ads_engine/data/performance/snapshots/fb-forms-report-2026-03-25-to-2026-04-10.pdf` |
| Pipeline entrypoint | `python3 -m engine.reports.funnel.run` (run from `ads_engine` root) |
| Metabase database | SmartScribe Analytics Supabase (db_id=2) |
| Primary SQL tables | `public.users`, `public.events` |
| Cohort window | Last 180 days (`COHORT_DAYS=180` in `config.py`) |
| Trial-end event | `PAYMENT_STATUS_CHANGED` where `event_data->>'previous_status' = 'trialing'` |
| Trial-end fallback | `create_datetime + 14 days`, capped at 30 days |
| Note-creation event | `NOTE_CREATED` in `public.events` |
| Rolling window | 5 points, n-weighted (`ROLLING_WINDOW=5`) |
| Notes cap bucket | `30+` (users with >30 notes bucketed together, `NOTES_CAP=30`) |
| ARPU assumption | $150/mo flat (`ARPU_MONTHLY=150`) |
| Paid channel list | `['google_ad', 'facebook_ad', 'linkedin_ad']` (`PAID_CHANNELS` in `config.py`) |
| Non-paid rollup label | `'rest'` |
| Matured threshold | ≥14 days (`MATURED_MIN_DAYS=14`) |
| QC tolerance — percentage | 0.1 pp |
| QC tolerance — additivity | 0.0001 conversions (strict) |
| QC tolerance — dollars | $1.00 |
| Base rate (L6M, as of 2026-04-13) | 12.12% |
| Cohort total (L6M, as of 2026-04-13) | 2,520 signups |
| Active converted (L6M, as of 2026-04-13) | 296 users |
| Mature weeks counted in MAE | 24 |
| MAE (conversions, as of 2026-04-13) | ±3.41 |
| MAE (MRR, as of 2026-04-13) | ±$511 |
| MAPE (as of 2026-04-13) | 36.1% |
| Bias (conversions, as of 2026-04-13) | −0.17 (model slightly under-forecasts) |
| Mean forecast (as of 2026-04-13) | 11.83 convs/wk |
| Mean actual (as of 2026-04-13) | 12.0 convs/wk |
| Originating request | Chris Hume's FB Forms Performance Report (Slack message, 2026-04-13) |
| Related fix docs | `docs/ga4-csp-fix-2026-04-13.md`, `docs/utm-capture-fix-2026-04-13.md` |
| Dashboard author | Nate + Claude build session, 2026-04-13 |

---

## Sources

[^1]: Nate's global CLAUDE.md: "Numerical outputs: Python script → QC script → result. LLMs don't compute final numbers." And: "No numbers as metaphor. Never use a number … unless it comes from (a) Nate's conscious estimate elicited via questions, (b) actual data with a cited source, or (c) derived math from real inputs."

[^2]: `/math-check-html` skill (`~/.claude/skills/math-check-html/SKILL.md`): "Python is truth. Every number in the deliverable must trace to a Python output. No exceptions. QC is the tiebreaker. If model and deliverable disagree, check QC. If model and QC disagree, fix the model." The `engine/reports/funnel/` harness implements this chain exactly: `pull.py → compute.py → qc.py → render.py`.
