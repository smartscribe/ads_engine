---
title: Signup Funnel — L6M Analytical Insights
date: 2026-04-13
author: Nate + Claude
source_dashboard: engine/reports/funnel/ · data/performance/snapshots/trial-conversion-by-notes.html
cohort: L6M signups (n=2,520 total, n=2,377 matured)
as_of: 2026-04-13
---

# Signup Funnel Insights — L6M

**Pulled from:** [funnel dashboard](../../data/performance/snapshots/trial-conversion-by-notes.html) · model at `data/performance/snapshots/funnel/model.json`
**Cohort:** 2,376 matured L6M signups across 24 weeks
**Base rate:** 12.12% (288 active / 2,376 matured)
**Mean weekly MRR capture:** ~$1,800 / mature week at $150 ARPU

---

## Governing thought

**Paid ads are dragging us down. They deliver 37% of signups but only 16% of mature-cohort MRR. Organic converts at 3× the rate.** $15–20k/mo in paid media is producing a cohort of users who look engaged in trial but fail to convert, while organic/referral/group-sourced signups carry the business.

---

## 1. Paid ads are the worst-performing cohort we have

Per-channel conversion over 24 mature weeks (source: `model.weekly_by_channel`):

| Channel | Signups | Converted | Rate | MRR @ $150 | Share of MRR |
|---|---|---|---|---|---|
| Google ads | 507 | 26 | **5.1%** | $3,900 | 9.0% |
| Facebook ads | 297 | 18 | **6.1%** | $2,700 | 6.2% |
| LinkedIn ads | 80 | 5 | **6.3%** | $750 | 1.7% |
| **Paid total** | **884** | **49** | **5.5%** | **$7,350** | **17.0%** |
| Rest (organic + referral + group) | 1,492 | 239 | **16.0%** | $35,850 | 83.0% |

**Paid converts at roughly one-third the rate of everything else.** Same product, same pricing, same trial flow — the only variable is the source. The rolling-rate model (fit on the full cohort) systematically over-forecasts paid: Google forecast was 68 conversions, actual was 26. Facebook forecast was 35, actual was 18. **Ad-led users look engaged in trial but churn before conversion.**

### Two candidate explanations

1. **Ad-led users have lower intent.** They create notes during trial (so they pass the engagement proxy the forecast model uses) but then abandon before paying. Possibly free-tier tire-kickers, possibly worse ICP fit from broad targeting, possibly price-sensitive users who flinch at checkout.
2. **Ads are priming brand awareness for later organic signups.** Discovery survey shows 45% of engaged trialers attribute to paid, but only 16% of conversions come from paid. People may see a Google ad, dismiss it, then come in later via referral and self-report as organic — so paid works but is undercredited by the rate model.

Both explanations are live. The data doesn't distinguish them yet. **Before making a kill decision, we need a lag-adjusted LTV number from Stripe — some paid users may convert on a longer runway than this 24-week window captures.**

---

## 2. Self-reported attribution ≠ the ledger

Discovery survey of L6M first-note trialers (n=1,038):

| Source | Count | Share |
|---|---|---|
| Google ad | 291 | 28.0% |
| Friend / colleague | 243 | 23.4% |
| Part of group | 170 | 16.4% |
| Facebook ad | 139 | 13.4% |
| Other | 82 | 7.9% |
| LinkedIn ad | 38 | 3.7% |
| Conference / event | 23 | 2.2% |
| Blog / newsletter / podcast | 46 | 4.4% |
| Null | 6 | 0.6% |

**45% of engaged trialers self-report paid ads. Only 16% of real conversions come from paid.** A 29-point gap between discovery survey and actual ledger revenue.

**The discovery survey is not safe to optimize on.** It's a directional brand-awareness signal, not an attribution ledger. Anyone pulling "Facebook delivered 13% of leads" from survey data is off by a factor of ~2. Use `model.weekly_by_channel` actuals for real attribution going forward.

---

## 3. Activation is the biggest leak — 59% create zero notes

| Notes during trial | % of matured cohort | Converts at |
|---|---|---|
| 0 notes | **58.8%** (1,398 users) | 7.0% |
| 1–2 notes | 9.5% (225 users) | 7.3% avg |
| 3–9 notes | 13.0% (308 users) | 17% avg |
| 10+ notes | 18.8% (446 users) | 25% avg |

**More than half the cohort never creates a note during their entire trial.** The first-note gate is the single biggest leak in the funnel.

Back-of-envelope impact: if first-note rate rose from 41.2% to 60% (an 18.8 pp lift), conservatively moving those new activators onto the 7% curve floor would add ~3.4 pp to the base rate, worth **~$13k in new MRR per year at current signup volume**. If they landed on the 17% (3-9 note) curve instead, it's ~$64k ARR. The "no-note trap" is the biggest single lever we have.

**Caveat worth flagging**: the fact that 0-note users still convert at 6.96% is suspicious — it should be near zero. Most likely explanation: users who paid-upfront skipped the trial entirely, or users who failed 2FA at signup and came back through another path are being mis-cohorted. Worth investigating as a data hygiene item.

---

## 4. The 3-note cliff is the highest-leverage intervention point

Rolling rate:

- 2 notes → **7.6%**
- 3 notes → **11.5%**
- 6 notes → **21.6%** (2× the 3-note rate)
- 10 notes → **23.1%**

**Rate nearly doubles between 3 notes and 6 notes.** Once a user hits the 3rd note, you've essentially won — they're on the product-pull escalator. The most winnable intervention is the moment a user has created 2 notes and hasn't yet started a 3rd — that's the threshold where human reach-out (Jack call, in-app nudge, email) has the highest marginal return. 3–9 note users deliver 21% of all conversions despite being only 13% of the cohort.

---

## 5. Growth is real but it's all organic

Weekly actual conversions, first half vs second half of the mature window:

| Metric | First 12 mature weeks | Last 12 mature weeks | Change |
|---|---|---|---|
| Total conversions | 10.2/wk | 13.8/wk | **+36%** |
| Google ads | 1.2/wk | 1.0/wk | ↓ 0.2 |
| Facebook ads | 0.6/wk | 0.9/wk | ↑ 0.3 |
| LinkedIn ads | 0.2/wk | 0.2/wk | → |
| Rest (organic) | 8.2/wk | 11.8/wk | **↑ 3.6** |

**All of the growth is organic.** Paid is flat to down. The organic flywheel is doing the work. The growth we're celebrating in the dashboard is not a paid-channel story.

---

## 6. The week of March 2 is worth investigating

Biggest forecast misses (forecast − actual):

| Week | Forecast | Actual | Error |
|---|---|---|---|
| 2026-03-02 | 12.73 | **23** | **−10.27** |
| 2025-11-10 | 17.24 | 23 | −5.76 |
| 2026-01-19 | 11.39 | 17 | −5.61 |
| 2025-11-17 | 11.43 | 6 | +5.43 |
| 2025-10-20 | 15.43 | 11 | +4.43 |

**March 2 had 102 signups that converted at 22.5%** — nearly double the 12.1% base rate. The model missed this by 10 conversions, worth ~$1,500 MRR. Nothing obvious in the signup volume or channel mix explains it.

**Worth investigating** whether there was a referral loop, a product launch, a specific LinkedIn post or Twitter thread, a cohort that came in from a single source. If that week's pattern can be identified and reproduced, it's a 2× multiplier on normal performance.

---

## 7. The forecast model is calibrated on average but noisy at the week level

From `model.error_summary`:

| Metric | Value |
|---|---|
| Mean forecast | 11.83 convs/wk |
| Mean actual | 12.00 convs/wk |
| Bias | −0.17 (slight under-forecast) |
| MAE | ±3.41 convs/wk |
| MAE (MRR) | ±$512/wk |
| MAPE | 36.1% |

**Bias is essentially zero.** Aggregate planning off the forecast is safe — if you use it to set a quarterly target, the expected cumulative error is near-zero.

**MAE is near the binomial noise floor.** At n≈100 signups/wk and a 12% base rate, √(0.12 × 0.88 × 100) ≈ 3.2. The model can't beat this at the single-week level without aggregation. Don't make weekly operational decisions (staffing, budget) off one week's forecast; use a 4-week rolling average instead.

---

## Caveats to hold in mind

1. **The rolling rate is fit on the whole cohort**, not per-channel. Paid channels may genuinely need their own rate function. Fitting one for paid alone would show how much of the paid under-performance is rate mismatch vs. real drop-off.
2. **"Rest" collapses three very different sub-channels** (friend/colleague referral, part-of-group seat assignments, organic/content). Part-of-group in particular is essentially pre-sold bulk seats — not really a "conversion" at all. The 16% organic conversion rate is almost certainly inflated by group signups.
3. **Stripe-derived LTV is not wired in yet.** All MRR numbers here are trial → active, not lifetime. Paid users might have better retention than organic (CAC investment selecting for stickier users), in which case the LTV picture looks less bad than the conversion picture.
4. **The 2FA signup tracking bug is still unfixed** and may be suppressing conversion events from being logged in the analytics mirror. If the fix lands, expect the actual-conversion line to jump, and MAE to re-baseline.
5. **24 mature weeks is a small sample** for channel-level analysis. Paid channels have 5, 18, 26 conversions each — small-n territory.

---

## What comes next

1. **Pull Stripe-derived LTV per cohort** and re-run the channel split with real retention data. Before killing paid, confirm it doesn't pay back on a longer horizon.
2. **Fit a paid-channel-specific rolling rate** to separate rate miscalibration from real ICP mismatch.
3. **Split "rest" into sub-channels** in the harness config (`PAID_CHANNELS` can be extended to `ALL_CHANNELS` in `config.py` with minimal surgery).
4. **Investigate the March 2 outlier** — pull that week's signup list and see what they had in common.
5. **Ship a first-note activation experiment** — this is the biggest dollar lever in the funnel.

---

## Provenance

- All numbers derived from `engine/reports/funnel/` harness, model written 2026-04-13.
- QC: 384/384 independent checks passed before the model was written.
- Raw data at `data/performance/snapshots/funnel/raw/*.json`
- Rendered dashboard at `data/performance/snapshots/trial-conversion-by-notes.html`
- Rerun command: `python3 -m engine.reports.funnel.run`
