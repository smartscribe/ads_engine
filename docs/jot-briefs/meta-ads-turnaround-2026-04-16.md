---
title: Meta Ads Turnaround — Audience Tightening + Dollar-Weighted Optimization
date: 2026-04-16
author: Nate + Claude
memory_target: Mem0
scope: New Meta Ads audience architecture and conversion value hierarchy
confidence: high
supersedes: none
sources:
  - plan: ads_engine/plans/meta-turnaround-2026-04-16.md
  - data: ads_engine/data/ads-reports/analysis-10d-2026-04-14.json
  - data: ads_engine/data/audiences/converters-upload-2026-04-16.json
  - data: ads_engine/data/audiences/chris-lists-upload-2026-04-16.json
  - code: ads_engine/engine/capi/sender.py
  - code: ads_engine/scripts/build-nppes-audience.py
  - page: jotpsych.com/scheduled-confirmed
---

# Meta Ads Turnaround — Audience Tightening + Dollar-Weighted Optimization

**Date:** 2026-04-16
**Memory target:** Mem0
**Scope:** New Meta Ads audience architecture, conversion value hierarchy, Calendly tracking, CAPI integration
**Status:** Canonical as of 2026-04-16. NPPES audience upload in progress; optimization objective switch pending.

---

## TL;DR

Meta Ads were burning $300/day with a $213 CpFN because the algorithm had no audience signal (spraying at broad BH clinicians) and was starving on ~1.4 conversion events per day. We built a layered audience system (NPPES PMHNPs + psychiatrists, Chris's 509 sales contacts, 2,000 converter-seeded lookalike, 14K Stripe exclusion) and a dollar-weighted value hierarchy (FirstNote=$100, CalendarScheduled=$15, SignUpConfirm=$5) to give Meta 7-10x more optimization signal. Calendly now redirects to a jotpsych.com confirmation page that fires the CalendarScheduled pixel event. Next step is attaching all audiences to ad sets and switching optimization from event count to value/ROAS.

---

## What Jot Should Commit to Memory

1. **Meta Ads now use a layered audience system, not broad BH targeting.** Six audiences: NPPES PMHNPs + Psychiatrists (inclusion, ~40K+ providers via public API), Sales Prospect List (inclusion, 509 contacts from Chris), Lookalike - BH Clinic Prospects 1% (inclusion), Converters - First Note Completers (exclusion, 2,000 users), Lookalike - First Note Converters 1% (inclusion), Stripe Customers (exclusion, 14,130).

2. **The conversion value hierarchy is: FirstNote=$100, CalendarScheduled=$15, SignUpConfirm=$5.** No LPVs — Nate rejected landing page views as too noisy ("too many AI tire-kickers"). Only revealed preferences (actions requiring real commitment) get dollar values. This hierarchy feeds Meta's ROAS optimization.

3. **Calendly bookings now fire a CalendarScheduled pixel event with $15 value.** Both Calendly event types redirect to `jotpsych.com/scheduled-confirmed` after booking. The page fires the Meta pixel event and grabs `invitee_email` from Calendly query params for match quality. Meeting scheduled = conversion; no-shows are acceptable noise at 80/20.

4. **CAPI (Conversions API) is live for server-side event delivery.** Module at `engine/capi/sender.py`, pixel ID `1625233994894344`. Tested and receiving events. Enables sending conversion events with dollar values independent of client-side pixel.

5. **NPPES is a free public API for provider targeting.** Endpoint `https://npiregistry.cms.hhs.gov/api/?version=2.1`, no key required. PMHNP taxonomy `363LP0808X`, Psychiatry `2084P0800X`. Returns name + practice address — matched to Meta via FN+LN+ST+ZIP schema (30-50% match rate). Script at `scripts/build-nppes-audience.py`.

6. **Metabase converter data lives in `provider_segments` table.** Email is `provider_segments.email`, note count is `provider_segments.notes_created_count`. DB ID 2 on `smartscribe-health.metabaseapp.com`. The `users` table has `user_notes_created_count` but no email column directly.

7. **No kill/scale decisions until audience + value weighting are live.** The Apr 4-13 data had LPV tracking issues from the Apr 14 CSP fix — pixel was underreporting. Clean signal needed before cutting any ads.

---

## Why (Reasoning + Evidence)

### The Performance Problem

The 10-day window (Apr 4-13) showed Farm+Scale at $2,981 spend, 14 FirstNotes, $213 CpFN[^1]. The Scale campaign alone was at $263 CpFN. Only one ad — "Audit Letter Arrives" — approached viability at $96 raw CpFN.

### Why Audiences Matter

Meta was targeting broad "behavioral health clinicians" with no narrowing. PMHNPs are the core ICP. Without audience constraints, the algorithm optimizes for cheap clicks from anyone loosely interested in healthcare — not for clinicians who will complete a first note.

The NPPES database provides a clean, free, complete list of every NPI-registered PMHNP and psychiatrist in the US. Combined with Chris's hand-curated sales prospect list and a lookalike seeded from actual converters, this gives Meta three layers of targeting signal it didn't have before.

### Why Dollar-Weighted Optimization

At $213 CpFN, Meta receives ~1.4 conversion events per day. Meta's algorithm needs ~50 conversions per week to exit learning phase[^2]. By adding CalendarScheduled ($15) and SignUpConfirm ($5) as weighted events, we increase to ~7-10 value events per day (~50-70/week), crossing the learning threshold.

Nate explicitly rejected LPVs as a value signal — "too many AI tire-kickers" inflating the number. The principle: only events requiring revealed preference (real user commitment) get dollar values.

### Why Calendly Redirect (Not Webhooks)

Initial design proposed Calendly webhooks → CAPI with daily cron to filter no-shows. Nate's feedback: "way too complicated." Calendly natively supports redirect-after-booking to a custom URL with query params. A simple confirmation page with a pixel fire achieves the same outcome with zero infrastructure. No-shows are acceptable noise — the 80/20 applies.

---

## How to Apply

| Situation | Response |
|---|---|
| Someone asks about Meta audience targeting | Six audiences: NPPES (inclusion), Chris's list (inclusion), BH Clinic Lookalike (inclusion), Converter Lookalike (inclusion), Converters (exclusion), Stripe (exclusion) |
| Someone asks about conversion events | Three weighted events: FirstNote=$100, CalendarScheduled=$15, SignUpConfirm=$5. No LPVs. |
| Someone asks about Calendly tracking | Both event types redirect to jotpsych.com/scheduled-confirmed. Pixel fires CalendarScheduled with $15 value. |
| Ad performance discussion — should we kill ads? | Not until audience + value weighting are live and have 7+ days of clean data. The pre-fix data is unreliable. |
| Someone needs to add a new Calendly event type | Must configure redirect to `https://www.jotpsych.com/scheduled-confirmed` with "Pass event details" checked |
| Stripe exclusion seems stale | Run `scripts/sync-stripe-exclusions.py` — uses `META_ADS_ACCESS_TOKEN` env var (was fixed from old `META_ACCESS_TOKEN` on 2026-04-16) |
| Need to refresh NPPES audience | Run `scripts/build-nppes-audience.py` — paginates full NPPES API, takes ~10 min |

---

## What This Brief Does NOT Cover

- Creative strategy or regression model updates (separate workstream)
- Google Ads (paused except branded)
- The LPV tracking fix (separate plan at `plans/lpv-tracking-fix-2026-04-14.md`)
- The optimization objective switch from conversions → value/ROAS (pending, will be a separate action)
- Audience performance measurement (need 7+ days of post-change data)

---

## Open Questions

- **Budget reallocation:** Should out-of-scope campaigns (LGF, Test, Retargeting = $1,615/10d excluded spend) be paused to concentrate budget? Owner: Nate. No deadline.
- **LPV tracking:** Is the CSP fix from Apr 14 deployed and verified on mobile? Owner: Engineering.
- **NPPES refresh cadence:** Monthly? Quarterly? The NPPES database updates monthly. Owner: Nate.

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| Meta Ad Account | `act_1582817295627677` |
| Meta Pixel (canonical) | `1625233994894344` (WebApp Actions) |
| Stripe Exclusion Audience | `120245449143920548` (14,130 customers, synced 2026-04-16) |
| Sales Prospect List Audience | `120245449291240548` (509 contacts) |
| Lookalike - BH Clinic Prospects 1% | `120245449291800548` |
| Converters Audience | `120245449282160548` (2,000 first-note completers) |
| Lookalike - First Note Converters 1% | `120245449282540548` |
| NPPES PMHNPs + Psychiatrists Audience | Pending (upload in progress) |
| PMHNP Taxonomy Code | `363LP0808X` |
| Psychiatry Taxonomy Code | `2084P0800X` |
| NPPES API | `https://npiregistry.cms.hhs.gov/api/?version=2.1` |
| Metabase DB ID | 2 (Smartscribe Analytics Supabase) |
| Metabase converter table | `provider_segments` (email + notes_created_count) |
| Calendly Event 1 | `calendly.com/d/cnvt-6cm-724/is-jotpsych-right-for-you-and-your-clinic` |
| Calendly Event 2 | `calendly.com/ekaiser-jotpsych/jotstart-an-introduction` |
| Confirmation Page | `https://www.jotpsych.com/scheduled-confirmed` |
| CAPI Module | `engine/capi/sender.py` |
| Plan Doc | `plans/meta-turnaround-2026-04-16.md` |

---

## Sources

[^1]: Meta Ads API pull 2026-04-16, analysis at `data/ads-reports/analysis-10d-2026-04-14.json`. Farm+Scale scope only.
[^2]: Meta Business Help Center — "About the learning phase": ad sets need approximately 50 optimization events per week to exit learning phase.
