---
title: Funnel Dashboard Refresh 2026-04-21
date: 2026-04-21
author: Nate + Claude
memory_target: Long-term memory
scope: Updated headline numbers for the Signup Funnel Dashboard. Architecture, methodology, and identifiers from the 2026-04-13 brief remain canonical.
confidence: high
supersedes: docs/jot-briefs/funnel-dashboard-2026-04-13.md (numbers only; architecture still canon)
sources:
  - data: jotpsych_gtm/ads_engine/data/performance/snapshots/funnel/model.json (generated 2026-04-22T01:51:55Z)
  - html: jotpsych_gtm/ads_engine/data/performance/snapshots/trial-conversion-by-notes.html
  - prior-brief: jotpsych_gtm/ads_engine/docs/jot-briefs/funnel-dashboard-2026-04-13.md
---

# Funnel Dashboard Refresh 2026-04-21

**Date:** 2026-04-21
**Memory target:** Long-term memory (update existing Signup Funnel Dashboard entry with fresh numbers; architecture unchanged)
**Scope:** Headline numbers only. Architecture, methodology, file paths, and identifiers from the 2026-04-13 parent brief remain canonical.
**Status:** canonical as of 2026-04-21

---

## TL;DR

The Signup Funnel Dashboard was rehydrated on 2026-04-21 against fresh Metabase data. All 387 QC checks passed. The model is more accurate than the last refresh: MAE dropped from ±$511 to ±$451 MRR per week, MAPE from 36.1% to 27.7%, bias stayed near zero. The underlying harness, methodology, and caveats from the 2026-04-13 brief are all unchanged. The currently-trialing cohort (113 signups across signup weeks 2026-04-13 and 2026-04-20) is forecast to produce ~$1,865 in new MRR when mature; roughly $900 has already converted, leaving ~$965 still in flight. Channel split of that in-flight forecast: 61% Rest (organic / friend-colleague / group), 17% Google Ads, 17% Facebook Ads, 5% LinkedIn. Chris Hume's Facebook Ads pipeline accounts for ~$324 of the in-flight forecast (17%, from 23 FB signups).

---

## What Jot Should Commit to Memory

1. **Refreshed headline numbers supersede the 2026-04-13 values.** All canonical identifiers, architecture, file paths, and methodology from the 2026-04-13 brief remain correct; do not overwrite those.

2. **Cohort as of 2026-04-21: 2,461 signups in last 180 days** (down from 2,520 at 2026-04-13 refresh, natural age-out as the rolling window advances). 314 still active trials (up from 296).

3. **Overall base conversion rate: 13.0%** (up from 12.12%). Still small-sample; single-decimal precision only.

4. **Forecast accuracy improved refresh-over-refresh.** MAE ±3.01 convs/±$451/wk (was ±3.41/±$511). MAPE 27.7% (was 36.1%). Bias -0.24 convs / -$36 MRR (was -0.17 / near zero). 25 mature weeks in the calibration window (was 24).

5. **In-flight forecast from weeks 2026-04-13 + 2026-04-20: $1,865 total, $900 already converted, $965 still trialing.** 113 signups across those two weeks. Channel split: rest 61%, google_ad 17%, facebook_ad 17%, linkedin_ad 5%.

6. **The 3-note cliff is unchanged as the strongest observable activation lever.** Users with 0-2 notes convert at ~7%; users with 3+ notes convert at 11-30% depending on depth. The refresh did not shift this.

---

## Why (Reasoning + Evidence)

Refresh ran at 2026-04-22T01:51Z via `python3 -m engine.reports.funnel.run`. 387 of 387 QC checks passed; HTML rewritten in place. Cohort window unchanged (last 180 days). ARPU assumption unchanged ($150/mo flat).

The MAE improvement is driven by two factors:

- One additional mature week (25 vs 24) shifts weighting away from noisier early weeks.
- The rate curve re-fit slightly: the 0-note bucket rate moved from 6.96% to 7.73%, which reduces forecast error on large-volume weeks (the 0-note bucket dominates cohort mass).

Bias drifted slightly more negative (-0.24 vs -0.17 convs/wk), meaning the model is now under-forecasting by ~$36/wk. Still neutral for planning purposes. Flag for review if it drifts past -$100/wk sustained.

### In-flight forecast table

| Week | Signups | Expected Convs | Expected MRR | Already Converted | State |
|---|---|---|---|---|---|
| 2026-04-13 | 85 | 9.70 | $1,455 | $450 | INCOMPLETE |
| 2026-04-20 | 28 | 2.73 | $410 | $450 | INCOMPLETE |
| **Total in-flight** | **113** | **12.43** | **$1,865** | **$900** | — |

### Channel split of in-flight forecast

| Channel | Signups | Expected Convs | Expected MRR | Share |
|---|---|---|---|---|
| rest | 67 | 7.5 | $1,129 | 61% |
| google_ad | 20 | 2.1 | $322 | 17% |
| facebook_ad | 23 | 2.2 | $324 | 17% |
| linkedin_ad | 3 | 0.6 | $90 | 5% |

---

## How to Apply

| Situation | Response |
|---|---|
| "What's in our current pipeline?" | $1,865 forecast MRR from the last 2 weeks of signups; $900 already converted, $965 still in flight. Plus the older tail of the 314 active trials. |
| "How much of that is Facebook?" | $324 expected MRR from 23 signups (2.2 expected conversions). 17% of the in-flight forecast. |
| "How much of that is Google?" | $322 expected MRR from 20 signups (2.1 expected conversions). 17% of the in-flight forecast. |
| "How much do I trust this?" | MAE ±$451 per mature week. Bias ~zero. Single-week forecasts carry roughly $450 of natural variance at this volume. |
| "Is the model getting better or worse?" | Better this refresh. MAE $511 to $451, MAPE 36% to 28%. Bias drifting slightly more negative but still near zero. |
| "What's the highest-leverage activation move?" | Push trialers past 3 notes. Conversion jumps from ~7% at 0-2 notes to 11-30% at 3+. Note creation is the product activation signal. |
| "How do I refresh the dashboard myself?" | `python3 -m engine.reports.funnel.run` from the `ads_engine` root. ~2.5s. QC must pass before HTML rewrites. |

---

## What This Brief Does NOT Cover

- Ad spend, CPL, CPM, CPC. Those live in Meta and Google Ads Manager and Chris's separate Facebook Forms report.
- Per-ad creative decomposition. Regression harness still pending.
- The 2FA signup-tracking bug. Tracked separately under `docs/jot-briefs/ga4-csp-fix-2026-04-13.md`.
- LTV and retention math. Dashboard still uses flat $150 ARPU. True LTV requires cohort retention data not in this harness.
- Discovery-survey attribution accuracy. Subject to self-report recall bias as noted in the 2026-04-13 brief.

---

## Open Questions

1. **Update ARPU to Stripe-derived blended number.** Still $150 flat. Owner: Nate. No due date.
2. **Watch bias drift.** -$36/wk is fine; -$100/wk sustained would warrant investigation. Re-check next refresh. Owner: Nate.
3. **The in-flight $965 number is a 2-week snapshot.** When those weeks mature (around 2026-05-04), "still in flight" will no longer apply. Always read from live `model.json` for current state.

---

## Canonical Identifiers (this refresh)

| Thing | Value |
|---|---|
| Refresh date | 2026-04-21 (data generated 2026-04-22T01:51:55Z) |
| Cohort total (L6M) | 2,461 |
| Active trials still in-flight | 314 |
| Overall base rate | 13.0% |
| Mature weeks in calibration | 25 |
| MAE (convs/wk) | ±3.01 |
| MAE (MRR/wk) | ±$451 |
| MAPE | 27.7% |
| Bias (convs/wk) | -0.24 |
| Bias (MRR/wk) | -$36 |
| Mean forecast | 12.08 convs/wk |
| Mean actual | 12.32 convs/wk |
| In-flight weeks | 2026-04-13, 2026-04-20 |
| In-flight signup count | 113 |
| In-flight expected MRR | $1,865 |
| In-flight already converted | $900 |
| In-flight still in trial | $965 |
| In-flight channel split (MRR) | rest $1,129 / facebook_ad $324 / google_ad $322 / linkedin_ad $90 |
| QC checks run | 387/387 passed |
| Parent brief (canonical architecture) | docs/jot-briefs/funnel-dashboard-2026-04-13.md |

---

## Sources

[^1]: `data/performance/snapshots/funnel/model.json`, regenerated 2026-04-22T01:51:55Z.
[^2]: `data/performance/snapshots/trial-conversion-by-notes.html`, rehydrated HTML.
[^3]: `docs/jot-briefs/funnel-dashboard-2026-04-13.md`, parent canonical brief for architecture and methodology.
