# Meta Ads Turnaround Plan

## The Problem

Last 10 days (Apr 4–13), Farm+Scale scope:
- **$2,981 spend → 14 FirstNotes → $213 CpFN.** Scale campaign alone: $1,054 → 4 FN → $263 CpFN.
- Fresh pull today (Apr 4–13, all campaigns): **$4,596 total spend across 64 ads.** The out-of-scope campaigns (LGF, Test, Retargeting, Q226) burned another $1,615 with zero in-scope conversions.
- LPV rates are catastrophic: multiple ads showing <5% LPV from link clicks. "AI for Progress Notes Concept 3" in Scale: 303 link clicks → 3 LPVs (0.99%). That's a landing page problem, a tracking problem, or both.
- Only 1 ad approaches viability: "Audit Letter Arrives" at $96 raw CpFN (3 FN on $287). Everything else is treading water or drowning.

Two structural problems are bleeding money independent of creative quality:
1. **No audience signal.** Meta is spraying at broad BH clinicians. PMHNPs are the target. No lookalike. No NPPES enrichment. No exclusion of existing customers from targeting (Stripe sync exists but may not be attached to all ad sets).
2. **Starved optimization signal.** FirstNote is the only conversion event. At $213 CpFN, Meta gets ~1.4 conversion signals per day across the whole account. That's not enough data for the algorithm to learn. It needs more frequent, cheaper events weighted by value.

---

## Workstream 1: Audience Tightening (PMHNP Focus)

### Goal
Stop paying to show ads to people who will never convert. PMHNPs are the core ICP. Narrow targeting, exclude customers, build a lookalike from converters.

### 1A: PMHNP Custom Audience via NPPES API

NPPES has a free public REST API: `https://npiregistry.cms.hhs.gov/api/?version=2.1`
No API key required. Supports filtering by taxonomy code, returns 200 results per page with `skip` pagination.

- PMHNP taxonomy: `363LP0808X` (Psychiatric/Mental Health Nurse Practitioner)
- Related codes worth including: `363L00000X` (NP general), `2084P0800X` (Psychiatry)
- **NPPES has no emails or phone numbers.** But it has name + practice address + state + zip.
- Meta's Custom Audience API accepts `FN + LN + ST + ZIP` as a matching schema. Match rates for healthcare providers typically run 30-50% on name+location.

**Action:** Write `scripts/build-nppes-audience.py`:
1. Paginate NPPES API filtered to PMHNP taxonomy codes
2. Extract: first_name, last_name, state, zip, city
3. SHA256 hash each field per Meta's spec
4. Upload to Meta as Custom Audience "NPPES PMHNPs"
5. Use as **inclusion targeting** on Farm + Scale ad sets

Estimated size: ~50-80K PMHNPs nationally. After Meta matching: ~20-30K addressable.

### 1B: Chris's Lists (In Hand)

Two CSVs from Chris, already in `data/`:

**`Combined_Admin_Provider_List (2).csv`** — 264 rows (89 admins, 175 providers)
- 190 work emails, 251 mobile phones
- Fields: Company, Name, Job Title, Location, Domain, LinkedIn, Email, Phone, Role
- Mix of PMHNPs, psychiatrists, office managers, clinical directors

**`NPPES Top 4 Clinics Email (1).csv`** — 262 rows (129 admins, 133 providers)
- 180 work emails, 255 mobile phones
- Fields: Name, Job Title, Location, Domain, LinkedIn, ICP (admin/provider), Email, Phone

**Combined unique identifiers:** 360 emails + 495 phones. Overlap is minimal — these are largely distinct contacts.

**Action:** Write `scripts/upload-chris-lists.py`:
1. Parse both CSVs, deduplicate by email
2. SHA256 hash emails + phones per Meta spec
3. Upload as Custom Audience "Sales Prospect List - BH Clinics"
4. Use as **inclusion targeting** on Farm (direct match audience)
5. Create a **1% Lookalike** from this audience — these are hand-picked ICP contacts, so the lookalike signal quality is high even from 360 seeds
6. Also usable as a lookalike seed blended with the NPPES PMHNP audience for a larger, still-targeted expansion

### 1C: Lookalike Audience from Converters

Seed options (ranked by signal quality):
1. **FirstNote completers** — the actual conversion event. Pull from Metabase: all users who completed a first note. Likely 200-500 users. Small seed but purest signal.
2. **Stripe customers** — already synced (14K emails). Large seed, high match rate, but includes churned users and non-PMHNP segments.
3. **Blend:** FirstNote completers as primary seed, Stripe as exclusion. 1% lookalike from converters, exclude all Stripe customers.

**Action:** 
- Write `scripts/build-lookalike-audience.py`
- Pull converter emails from Metabase (need Metabase API access or a SQL export)
- Upload as "Converter Seed" Custom Audience
- Create 1% Lookalike via Meta API
- Attach as targeting on Farm + Scale

### 1D: Exclusion Hygiene

The Stripe exclusion sync (`scripts/sync-stripe-exclusions.py`) exists but:
- Last sync was 2026-04-06 (10 days stale)
- `META_ACCESS_TOKEN` env var name in the sync script doesn't match `META_ADS_ACCESS_TOKEN` in the pull script — verify both work
- **Confirm the exclusion audience is attached to ALL active ad sets**, not just some

**Action:** Run sync immediately. Audit all active ad sets via API to verify exclusion audience is applied.

---

## Workstream 2: Dollar-Weighted Conversion Optimization

### Goal
Give Meta 5-10x more conversion signal by tracking cheaper events with proportional values. Optimize for ROAS instead of a single event.

### Current State
- Only event: FirstNote ($213 CpFN = ~1.4 events/day)
- SignUpConfirm fires but isn't valued or optimized against
- No calendar/demo booking signal at all
- Meta's algorithm is starving. It needs ~50 conversions/week to exit learning phase. We're giving it ~10.

### Proposed Value Hierarchy

Only revealed preferences. No LPVs — too many AI tire-kickers inflating that number.

| Event | Value | Expected Volume (per day) | Source |
|-------|-------|--------------------------|--------|
| FirstNote | $100 | ~1.5 | Meta Pixel (already firing) |
| CalendarScheduled | $15 | ~3-5 (estimate) | Calendly redirect → Pixel |
| SignUpConfirm | $5 | ~2-3 | Meta Pixel (already firing) |

This gives Meta ~7-10 value events per day instead of ~1.5 — meaningful signal improvement while keeping every event tied to a real user action.

### How to Implement

**Step 1: Create a Meta Custom Conversion for each event with a dollar value.**
Meta supports "custom conversions" where you assign a default value to a pixel event. Alternatively, use the Conversions API (CAPI) to send events with explicit `value` and `currency` fields.

Better approach: **Use CAPI to send all events with values.** This is more reliable than pixel-only (no ad blocker issues, server-side) and lets us control the exact value per event.

**Step 2: Set up CAPI endpoint.**
Write `engine/capi/sender.py`:
- Accepts event_name, event_time, user_data (hashed email, fbp, fbc), custom_data (value, currency)
- Posts to `https://graph.facebook.com/v21.0/{PIXEL_ID}/events`
- Pixel ID: `1625233994894344` (WebApp Actions, canonical)

**Step 3: Calendly integration.**
- Calendly supports webhooks: `invitee.created` fires when someone books
- **"No credit unless all the way through"** = don't fire on booking. Fire after the meeting happens.
- Calendly webhook events: `invitee.created`, `invitee.canceled`, `invitee_no_show`
- **Implementation:** On `invitee.created`, store the booking. Run a daily job that checks: if meeting_time has passed AND no cancellation/no-show event received → fire CalendarScheduled via CAPI with $15 value.
- Alternative (simpler): Fire on `invitee.created` with $15 value, then fire a negative `-$15` event on `invitee.canceled`. Net effect is the same but gives Meta the signal faster. **Downside:** Meta doesn't support negative values cleanly. Stick with the daily-check approach.

**Step 4: Switch campaign optimization objective.**
Current: optimizing for "conversions" (FirstNote event).
New: optimize for "value" (ROAS). This tells Meta to maximize total dollar value, not count of a single event. The algorithm will seek users who generate the most combined value across all events.

In Meta Ads Manager or via API: change `optimization_goal` from `OFFSITE_CONVERSIONS` to `VALUE` on each ad set, with the pixel + custom conversion events configured.

---

## Workstream 3: Calendly → Pixel via Redirect

### Architecture

No webhooks, no cron, no Zapier. Calendly supports redirecting to a custom URL after booking.

```
Ad → Landing page → Calendly booking →
  Redirect to jotpsych.com/scheduled-confirmed?invitee_email=...&event_type_name=... →
  Meta Pixel fires CalendarScheduled event with value=$15
```

Calendly automatically appends `invitee_email`, `invitee_name`, `invitee_first_name`, `invitee_last_name`, `event_type_name`, `event_start_time` as query params on the redirect URL. We can grab email and hash it for CAPI match quality boost.

### Setup
1. In each Calendly event type → "After booking" → change from "Display confirmation page" to "Redirect to an external site"
2. Enter URL: `https://www.jotpsych.com/scheduled-confirmed`
3. Check "Pass event details to your redirected page"
4. Build `/scheduled-confirmed` page on jotpsych.com with:
   - Meta Pixel `CalendarScheduled` event firing with `{value: 15, currency: 'USD'}`
   - Thank-you copy ("You're booked! We'll see you on [date].")
   - Optionally: also fire via CAPI server-side for redundancy (grab email from query param, hash, send)
5. Meeting scheduled = conversion. No-shows are acceptable noise at 80/20.

### What Nate Needs to Do
1. **Calendly setting:** Change redirect URL on each event type (2 min in Calendly admin)
2. **Confirm Calendly plan supports custom redirects** (requires paid plan)
3. We build the `/scheduled-confirmed` page + pixel event

---

## Workstream 4: Immediate Tactical Moves (This Week)

### 4A: No Kills Yet — Need More Signal First
The current data is too noisy to make kill/scale decisions. With the LPV tracking issues from
Apr 14, the pixel was underreporting for days. We need clean signal before cutting anything.
Priority is getting audience + value weighting live so the algorithm has real data to learn from.

### 4B: Fix LPV Tracking (Prerequisite for Trusting Any Data)
Multiple ads show 200+ link clicks with <5% LPV rate. Before trusting any CpFN numbers, verify:
1. Landing page loads correctly on mobile (where most Meta traffic goes)
2. Meta Pixel fires on page load (check CSP headers — known issue from Apr 14)
3. UTM parameters preserved through redirect chain
Reference: [plans/lpv-tracking-fix-2026-04-14.md](lpv-tracking-fix-2026-04-14.md)

---

## Execution Sequence

| Priority | Work | Depends On | Effort | Who |
|----------|------|-----------|--------|-----|
| P0 | Run Stripe exclusion sync (10 days stale) | Nothing | 5 min | Run existing script |
| P0 | Verify exclusions on all ad sets | Sync complete | 15 min | API audit script |
| P0 | Upload Chris's lists as Custom Audience | Nothing | 30 min | New script `upload-chris-lists.py` |
| P1 | NPPES PMHNP audience build via API | Nothing | 1 hr | New script `build-nppes-audience.py` |
| P1 | Create lookalike from Chris's list | Chris upload complete | 15 min | Meta API call |
| P1 | CAPI sender module | Nothing | 1 hr | New `engine/capi/sender.py` |
| P1 | Dollar-weighted custom conversions | CAPI sender | 30 min | Config + API calls |
| P1 | Attach new audiences to all Farm+Scale ad sets | Audiences built | 30 min | API script |
| P2 | Build `/scheduled-confirmed` page | Nothing | 30 min | HTML + pixel event |
| P2 | Calendly redirect config | Confirmation page live | 5 min | Nate in Calendly admin |
| P2 | Lookalike from Metabase converters | Metabase export | 30 min | New script |
| P2 | Switch optimization to VALUE/ROAS | Custom conversions live | 15 min | Ad set config change |
| P2 | LPV tracking fix | Nothing | See existing plan | Engineering |

---

## Resolved Questions

1. **Calendly:** Paid plan confirmed. Custom redirects available. ✅
2. **CalendarScheduled value:** $15. ✅
3. **NPPES scope:** PMHNPs + psychiatrists. Taxonomy codes: `363LP0808X`, `2084P0800X`. ✅
4. **Metabase:** API key live at `smartscribe-health.metabaseapp.com`. Users table has note count. Cross-check with events table. DB ID = 2 (Supabase). ✅
5. **Chris's lists:** In hand. 360 emails, 495 phones across two CSVs. ✅

## Still Open

1. **Calendly event types:** How many need the redirect configured? Just one demo/intro call, or multiple?
2. **LPV tracking:** Is the CSP fix from Apr 14 deployed? Pixel fires verified on mobile?
3. **Budget reallocation:** Leave out-of-scope campaigns (LGF, Test, Retargeting = $1,615 excluded spend) running, or pause to concentrate budget?
