---
title: "Phase 1 of Purchase Conversion Rebuild Shipped: Meta Standard Purchase via pixel_rule + GTM v23 Cleanup"
date: 2026-05-04
author: Nate + Claude
memory_target: Long-term memory
scope: Canonical Meta Ads attribution stack as of end-of-day 2026-05-04. Replaces the v3 Custom Conversion architecture from Apr 23. Ad set "Nate figuring shit out" now optimizes on Meta standard `Purchase` event via `pixel_rule` binding with VALUE-based bidding. Three GTM tags fire `Purchase` from three different upstream events, each with a per-event value. Phase 2 (CAPI parity for FirstNote) is scoped for Alfred and unblocked.
confidence: high
supersedes: docs/jot-briefs/meta-custom-conversions-v3-field-fix-2026-04-23.md (v3 CCs renamed `_archived_*`; ad set now bound to standard Purchase via pixel_rule, not to FirstNote v3 CC)
related:
  - plans/purchase-conversion-rebuild-2026-05-04.md (the plan that produced this brief)
  - plans/cleanup-meta-cc-and-gtm-2026-05-04.md (cleanup pass that gave the final state its names)
  - docs/jot-briefs/signup-funnel-elegant-path-2026-04-29.md (predecessor funnel state, GDN-1174/1180 context)
  - docs/jot-briefs/meta-capi-token-2026-04-29.md (CAPI token used for Phase 2)
sources:
  - api: GTM Tag Manager API v2 against container `GTM-KL9RPN9V` (containerId 200880687, accountId 6258528322), workspaces 24/26/27, versions 21/22/23 (2026-05-04)
  - api: Meta Marketing API v21.0 against ad set `120245858870530548`, pixel `1625233994894344`, 19 Custom Conversions on ad account `act_1582817295627677`, 18 custom audiences on same account (2026-05-04)
  - api: Meta pixel `/stats` aggregation=event for last-7d and last-30min event volumes, breakdown by event name (2026-05-04)
  - playwright: live funnel walk on jotpsych.com/start through Auth0 callback and through OnboardingView UserInfoForm + RecorderView FirstNote pushes, GTM Preview verification of all three Meta Purchase tags firing (2026-05-04)
  - git: smartscribe-companion-apps `origin/staging` HEAD `612036906` audited for `generatedFirstNote` dataLayer push sites and CompleteRegistration callback handler (2026-05-04, after `git fetch origin --prune` brought local checkout from 11-day-stale to current)
  - file: services/attribution/pixels.ts on smartscribe-companion-apps origin/staging (the GDN-1180 implementation that Phase 2 mirrors)
  - file: published-versions.log at config/gtm/published-versions.log (this session's GTM publish history with timestamps and IDs)
---

# Phase 1 of Purchase Conversion Rebuild Shipped

**Date:** 2026-05-04
**Memory target:** Long-term memory
**Scope:** Canonical Meta Ads attribution stack post-Phase-1. Architecture, identifiers, gotchas, what's open for Phase 2.
**Status:** Canonical as of 2026-05-04 evening ET. Ad set delivering on the new signal; live ingestion confirmed receiving Purchase events with correct values.

---

## TL;DR

JotPsych's Meta Ads ad set "Nate figuring shit out" (id `120245858870530548`) now optimizes on Meta standard `Purchase` event with VALUE-based bidding, replacing the custom-event SignUpConfirm signal that had been delivering effectively zero optimization data since May 2. Three GTM tags fire `fbq('track', 'Purchase')` with per-event values: First Note ($150) on `generatedFirstNote` dataLayer push, Sign Up ($25) on `signupConfirm` dataLayer push, Calendar ($5) on page view of `/scheduled-confirmed`. The ad set binds to Purchase via `pixel_rule` rather than via `custom_event_type=PURCHASE`, which sidesteps Meta's standard-event eligibility gate (needs ~50 historical Purchase events in 7 days; we have 2 so far) and unlocks VALUE optimization on day one. The April 20-23 v3 Custom Conversions are renamed `_archived_*` and inert. Legacy GTM tags 26 (Meta FirstNote) and 27 (Meta SignUpConfirm) are paused to eliminate the duplicate attribution streams that were polluting reporting. GTM container is at v23 with `[ACTIVE]`/`[ARCHIVED 2026-05-04]`/`[ORPHAN 2026-05-04]` tag-name prefixes for human-readability. Phase 2 (CAPI parity for FirstNote, the structural fix for browser-side pixel blocking that caused the May 2 production drop) is scoped and unblocked for Alfred.

---

## What Jot Should Commit to Memory

1. **The canonical Meta Ads optimization signal is now Meta standard `Purchase` event.** Active CC for reporting is `1604667127308749` "[CANONICAL] Purchase: FirstNote+SignUp+Calendar (value-based)". Ad set `120245858870530548` binds to it via `pixel_rule` field on `promoted_object`, NOT via `custom_event_type=PURCHASE`. The pixel_rule string is `{"and":[{"event":{"eq":"Purchase"}},{"or":[{"URL":{"i_contains":"jotpsych"}}]}]}`. Optimization goal is `VALUE`. Bid strategy is "Highest Value." Attribution window 7-day click + 1-day view (default; do not extend, longer windows make the calendar attribution-decay problem worse).

2. **Per-event values flow via the `value` param in fbq calls, not via the CC's `default_conversion_value`.** First Note pushes `{value: 150, currency: 'USD', content_name: 'first_note'}`, Sign Up pushes `{value: 25, currency: 'USD', content_name: 'signup'}`, Calendar pushes `{value: 5, currency: 'USD', content_name: 'calendar'}`. Meta uses fbq's per-call value over the CC default. The CC's `default_conversion_value=50` is only used as a fallback if a Purchase event arrives without a `value` param.

3. **Pixel_rule binding bypasses Meta's standard-event VALUE-eligibility gate.** Standard Purchase + VALUE optimization requires ~50 historical Purchase events in trailing 7 days before Meta's API will accept the binding (error_subcode 2446368, "Pixel isn't eligible for value optimization"). Custom Conversion bindings (via `pixel_rule`) use a looser eligibility path and are accepted immediately, even on a brand-new pixel signal. Use this trick whenever you need VALUE on a standard event before history accumulates. The CC itself does not need to exist for the binding to work — `pixel_rule` is a raw string match against the rule, evaluated against incoming pixel events. The CC `1604667127308749` was created separately for reporting visibility in Meta Events Manager UI.

4. **The three GTM tags driving Purchase firing live in container `GTM-KL9RPN9V` workspace 24 (now-archived) → workspaces 26/27 (drill-baby-drill working spaces) → live container version 23.** Tag IDs:
   - `67`: `[ACTIVE] Meta Purchase - First Note ($150)`. Trigger 15 (`_event == 'generatedFirstNote'`).
   - `68`: `[ACTIVE] Meta Purchase - Sign Up ($25)`. Trigger 17 (`_event == 'signupConfirm'`). Originally fired on trigger 65 (CompleteRegistration); rewired to 17 mid-session because "sign up confirmed" semantically matches the UserInfoForm-submission moment, not the Auth0 callback.
   - `69`: `[ACTIVE] Meta Purchase - Calendar Scheduled ($5)`. Trigger 66 (Page URL contains `/scheduled-confirmed`).
   All three are Custom HTML tags with the snippet `<script>(function(){var e="{{dlv_event_id}}";var p={value:N,currency:"USD",content_name:"X"};if(e&&e!=="undefined"&&e!==""){fbq("track","Purchase",p,{eventID:e});}else{fbq("track","Purchase",p);}})();</script>`. The `dlv_event_id` data-layer variable (id 64) reads `event_id` from the dataLayer push if present.

5. **Legacy GTM tags 26 (Meta - First Note Event, custom event `FirstNote`) and 27 (Meta - SignUp Confirm Event, custom event `SignUpConfirm`) are PAUSED.** They previously fired duplicate attribution to Meta whenever the same dataLayer events that drive the new Purchase tags fired. Both renamed with `[ARCHIVED 2026-05-04]` prefix capturing the reason and replacement tag id. Result: a single user signup now fires exactly one Meta event (Purchase), not two parallel streams. The v3 Custom Conversions that those legacy tags fed (`_archived_FirstNote v3`, `_archived_SignUpConfirm v3`) will plateau on their existing counts and stop accumulating new fires.

6. **The May 2-4 production drop in legacy custom-event pixel fires (FirstNote, SignUpConfirm) was NOT a GTM regression.** Diagnostic evidence captured in `config/gtm/snapshot-tags-2026-05-04.json`: tags 26 and 27 were ACTIVE in the live container (version 20), bound to correctly-configured triggers (15 and 17), last edited January 2025 — no recent changes. Most likely cause was browser-side blocking (ad-blockers, iOS Safari ITP) eating the `facebook.com/tr` calls, which is consistent with the same dataLayer pushes still firing in GTM Preview during the live walk. CAPI parity (Phase 2) is the structural fix because server-side fires bypass all browser-side blocking.

7. **Phase 2 ticket scope, owned by Alfred:** when the BE persists a new note, also POST to Meta CAPI (`https://graph.facebook.com/v21.0/1625233994894344/events`) with `event_name: "Purchase"`, `event_id` matching the FE dataLayer push (so Meta dedupes browser+server), full hashed user_data (em/ph/fn/ln/external_id, plus raw fbp/fbc cookies), `custom_data: {value: 150, currency: "USD", content_name: "first_note"}`. Token is `META_CAPI_ACCESS_TOKEN` already minted (Apr 29) and stored in `~/.claude/.env`. Mirror the GDN-1180 pattern at `services/attribution/pixels.ts` and `Views/AuthenticationCallback.tsx` from `smartscribe-companion-apps origin/staging`. Verified during this session: the `generatedFirstNote` dataLayer push at all four call sites (`RecorderView.tsx:315`, `EncounterView.tsx:565`, `useEncounterSubmission.ts:50`, `EncounterViewV2.tsx:2658`) does NOT currently include an `event_id` field. Phase 2 must add `event_id: crypto.randomUUID()` at all four sites and surface it to the BE request that creates the note. Recommended consolidation: extract a `services/attribution/fireFirstNoteEvent.ts` helper that generates the UUID once, pushes to dataLayer, and returns the event_id for the BE call.

8. **Operational gotchas hit during the build, store these:**
   - **GTM tag and trigger names reject colons (`:`) and em-dashes (`—`).** Use ASCII hyphens (`-`). Slashes appear OK in trigger names but not 100% verified.
   - **Meta Custom Conversions become immutable once `is_archived=true`.** Cannot rename via API after the archive flag is set (UI-archived CCs reject API rename POSTs with generic OAuthException 100). The `is_archived` PATCH itself silently fails when set via API on CCs created via API (per Apr 23 brief). So: rename CCs to `_archived_*` prefix BEFORE Meta or anyone else flips the archive flag, otherwise you lose rename access permanently.
   - **GTM workspaces lock after publish.** A workspace whose changes were published transitions to "submitted" state; further PUT/POST to its tags returns "Workspace is already submitted." Create a new workspace for next changes (`POST /accounts/{a}/containers/{c}/workspaces` with name + description). Default Workspace can be reused but only after a `:sync` operation — easier to create a fresh one each iteration.
   - **Ad set rebind to `custom_event_type=PURCHASE` requires standard-event eligibility.** Use `custom_event_type=OTHER` + `pixel_rule` (a JSON-encoded rule string) to bypass.
   - **The marketing-site `scheduled-confirmed.html` page fires a direct `fbq('trackCustom', 'CalendarScheduled')` independent of GTM.** This means Calendar v3 CC keeps accumulating fires even though the legacy GTM tag for Calendar was never set up. Killing this requires a code change to the marketing site (`site/scheduled-confirmed.html` line 111) plus a Netlify deploy. Low priority; small noise.

9. **Cleanup pass (v23) gave both surfaces human-readable prefixes.** Meta CCs sort: 1× `[CANONICAL]`, 3× `_archived_*v3*superseded`, 6× `_archived_*v1/v2*bug`, 5× `_dead_*` (pre-2026 dead funnels), 3× `[A]`-flagged or `_archived_probe`. GTM Meta tags sort: 5× `[ACTIVE]` Meta tags (3 Purchase + Pixel PageView + Pixel user_id), 3× `[ARCHIVED 2026-05-04]` (paused legacy custom event), 1× `[ARCHIVED-TEST]` (paused old test). Triggers: trigger 65 marked `[ORPHAN 2026-05-04]` (CompleteRegistration custom event, no tags bound after Tag 68 was rewired); trigger 66 marked `[ACTIVE]`. Reddit, LinkedIn, GA4, Calendly, FB CAPI wizard tags untouched (out of scope, possibly different platforms still active).

10. **Spend continues uninterrupted on the rebound ad set.** Today's metrics on `120245858870530548`: spend $224, impressions 5,890, clicks 230, 2 attributed Purchase events worth $50 (both happened to be SignUp variants at $25/each). ROAS = $50/$224 = 0.22. Meta is decaying through the existing user base on `CompleteRegistration` (488 fires/day right now, projected to settle near true new-signup rate of 10-30/day over the next 7-14 days as `first_capture` gating burns through users who logged in for the first time post-Apr-29 deploy).

---

## Why (Reasoning + Evidence)

### Why standard Purchase instead of staying on Custom Conversions

The April 20-23 attempt to optimize on FirstNote v3 CC with VALUE bidding was structurally hampered by Meta's rule that multi-event optimization is not available in OUTCOME_SALES + VALUE for Custom Conversions. The ad set could only be bound to one CC at a time (`pixel_rule` matches a single CC's rule). FirstNote v3 was the chosen single event because it had the highest LTV signal, but at ~6 fires per day it was below Meta's 50-conversions-per-week learning-phase exit threshold — the ad set never delivered cleanly. CpFN stayed at $408, never recovered toward the humming-era baseline of $144.

Meta standard `Purchase` event removes this constraint: all three valued events (FirstNote, SignUp, Calendar) fire as the same Meta `Purchase` event with different `value` and `content_name` parameters. Combined volume clears the learning threshold (~14-84/week depending on browser-blocking severity). Per-event value differentiation is preserved via the `value` param on each fbq call. Single optimization signal, multi-event input, value-weighted bidding.

### Why pixel_rule binding instead of custom_event_type=PURCHASE

When the rebind was attempted via `promoted_object={pixel_id, custom_event_type=PURCHASE}`, Meta returned `error_subcode 2446368`: "Pixel isn't eligible for value optimization. The pixel you've selected isn't eligible for value optimization." The standard-event eligibility gate requires roughly 50 historical Purchase events in the trailing 7 days for VALUE bidding to be accepted. The pixel had received exactly 2 Purchase events (the first ones from the new tags, fired ~30 minutes prior).

Pixel_rule binding goes through Meta's Custom Conversion path even when the rule's event matches a Meta standard event name like `Purchase`. The eligibility check on `pixel_rule` is the looser custom-event-VALUE rule (which allows the binding speculatively, with no historical-volume requirement). The same JSON rule string `{"and":[{"event":{"eq":"Purchase"}},{"or":[{"URL":{"i_contains":"jotpsych"}}]}]}` was accepted on first POST, ad set went IN_PROCESS for ~5 minutes, transitioned to ACTIVE, started delivering. No CC needed to exist for the binding to work — pixel_rule is byte-matched against incoming events at evaluation time.

The CC `1604667127308749` ("[CANONICAL] Purchase: FirstNote+SignUp+Calendar (value-based)") was created separately for reporting visibility in the Meta Events Manager UI Custom Conversions list. It has the same rule string. Its `default_conversion_value=50` is a fallback that does not get used because every fbq call from the new tags includes a `value` param.

### Why Tag 68 fires on signupConfirm not CompleteRegistration

Originally wired to trigger 65 (`CompleteRegistration`, the dataLayer event from `pixels.ts` that fires on Auth0 callback). Rewired to trigger 17 (`signupConfirm`, the dataLayer event from `OnboardingView.tsx:77` that fires when the user submits the UserInfoForm).

Two reasons:
1. "Sign up confirmed" lexically and semantically matches the UserInfoForm-submission moment — the user has committed to filling out their profile — not the earlier Auth0 callback (where they've just verified their email).
2. CompleteRegistration is currently over-firing at ~488/day due to GDN-1180's `first_capture=true` gate firing for every existing user the first time they log in post-Apr-29 deploy (essentially a backfill burning down through the active user base). Until that decay completes, binding optimization to it would inflate the value signal artificially. SignupConfirm fires only on real new-user UserInfoForm submissions, which is the cleaner signal.

Trade-off accepted: signupConfirm production volume is low (0-4/day in the May 2-4 window, likely browser-blocked from the legacy fbq tag — true volume is presumably higher, recoverable when CAPI ships).

### Why the legacy custom-event tags 26 and 27 are paused

Both were ACTIVE through the migration window, firing the legacy custom events `FirstNote` and `SignUpConfirm` to Meta whenever the corresponding dataLayer events fired. With the new Purchase tags also firing on the same dataLayer events, every user signup or first-note action fired TWO Meta events (Purchase + the legacy custom event), which the v3 CCs were matching as separate attribution rows.

This was visible in today's ad set Insights: the same 2 user actions appeared three times (`purchase` action with $50 total value, `offsite_conversion.custom.1014486627931137` for SignUpConfirm v3 CC at $10, `offsite_conversion.custom.1755976485786147` for FirstNote v3 CC at $200). Optimization was clean (only Purchase drove bidding via the pixel_rule binding), but reporting was triple-counting.

Pausing tags 26 and 27 eliminates the legacy custom event fires entirely. A user signup now produces exactly one Meta event (Purchase), one attribution row, one truth. The v3 CCs stop accumulating new fires; their existing counts plateau as historical record.

Audience-impact check confirmed safe before pausing: of 18 custom audiences on the ad account, only one (`Website traffic_sans 1st note_L30D`, id 120219902594670548) references the `FirstNote` custom event in its rule. That audience has 20 people in it, was last updated 2025-03-03 (year+ stale), and is not targeted by any active ad set's targeting spec. Pausing the tags causes it to stop refreshing; functionally no-op since it's already abandoned.

### Why the May 2-4 production drop was not a GTM regression

Pre-publish snapshot of the live container (version 20, "Updated with Calendly Event") showed:
- Tag 26 (Meta - First Note Event): ACTIVE, bound to trigger 15 (`_event == 'generatedFirstNote'`), Custom Event Name `FirstNote`, last edited 2025-01-29 (fingerprint `1738160653063`)
- Tag 27 (Meta - SignUp Confirm Event): ACTIVE, bound to trigger 17 (`_event == 'signupConfirm'`), Custom Event Name `SignUpConfirm`, last edited 2025-01-29 (fingerprint `1738157325269`)
- Triggers 15 and 17: correctly configured to match the React app's dataLayer pushes, last edited 2025-01-24

No recent edits, no paused state, no orphaned trigger references. Container in version 20 was the same one the marketing site and webapp loaded daily. Yet pixel-level fires for the custom events `SignUpConfirm` and `FirstNote` dropped from 5-15/day (Apr 20-29) to 0-4/day (May 2-4).

Most likely explanation, supported by the live Playwright walk where both legacy tags fired correctly in GTM Preview but `facebook.com/tr` calls were intermittently blocked: browser-side ad-blocking and iOS Safari ITP eating the pixel call payloads before they reach Meta. Same root cause as the broader EMQ problem (~3-4 EMQ score on a pixel that should be at 7+).

The structural fix is CAPI parity (Phase 2). Server-to-server fires bypass all browser-side blocking and ITP restrictions. The GDN-1180 work shipped this for `CompleteRegistration` (Apr 29); Phase 2 ships it for `Purchase` triggered by FirstNote.

---

## How to Apply

| Situation | Response |
|---|---|
| Building a new ad set in this account that needs VALUE optimization on Meta standard event | Bind via `pixel_rule` not `custom_event_type=<STANDARD>` whenever the pixel hasn't accumulated 50 events in 7 days. Pixel_rule binding sidesteps the standard-event eligibility gate. The rule is just a JSON string; no CC needs to exist. |
| Adding a new event to the canonical Purchase signal (e.g. paid plan upgrade) | Add a new Custom HTML tag in GTM that fires `fbq('track', 'Purchase', {value: X, currency: 'USD', content_name: 'new_event_name'}, {eventID: {{dlv_event_id}}})` on the appropriate dataLayer event or page-view trigger. Update the canonical CC's description to add the new content_name to the list. |
| Recalibrating per-event values (post-30-days cohort data) | Edit the value in each tag's HTML in GTM workspace, publish a new version. Recalibration does not reset Meta's learning phase (only optimization-event changes do). |
| Diagnosing "why isn't event X firing" | Three layers to check, in order: (a) GTM Preview to confirm the dataLayer push happens and the tag fires; (b) browser network tab for `facebook.com/tr` request reaching Meta; (c) Meta Events Manager > Test Events panel for the event arriving with correct values. If (a) passes but (b) or (c) fails, browser blocking is eating the call — CAPI parity is the fix. |
| Adding a Meta CC that wraps a standard event | Set `custom_event_type` to the matching standard event enum (PURCHASE for Purchase, COMPLETE_REGISTRATION for CompleteRegistration, etc.) — Meta rejects with subcode 1760021 if you set OTHER. Required `event_source_id` parameter (the pixel ID); easy to forget. |
| Renaming a Meta CC to archive it | Rename via POST to `/{cc_id}` with `name=_archived_<old_name>_<reason>_<date>`. Avoid setting `is_archived=true` flag — silently fails when set via API on API-created CCs, AND makes the CC immutable to future renames. Rename-prefix is the canonical archive mechanism for CCs. |
| Editing a GTM tag after a publish | Don't try to PUT against the published workspace — returns "Workspace is already submitted." Create a new workspace (`POST /accounts/{a}/containers/{c}/workspaces` with name + description), make edits there, version + publish from the new workspace. |
| Picking a tag/trigger name in GTM | Use ASCII hyphens, no colons or em-dashes. The container's existing convention is `Platform - Event Name` (e.g. "GA4 - First Note Event"). For visibility-prefixed renames use `[ACTIVE]`, `[ARCHIVED YYYY-MM-DD]`, `[ORPHAN YYYY-MM-DD]`, `[ARCHIVED-TEST]`. |
| Investigating attribution discrepancies in Meta Ads Manager Insights | The optimization signal (`purchase` action_type) and reporting signals (`offsite_conversion.custom.<id>` action_types from any active CCs) are separate. Sum the `purchase` row's value alone for true ROAS. Custom conversion rows show the same user actions counted again from a different angle — do not sum. After v23 cleanup, the only live custom conversion row that should appear is the Calendar v3 CC continuing to accumulate from the marketing-site direct fbq. |

---

## What This Brief Does NOT Cover

- **Phase 2 (CAPI for FirstNote) detailed implementation.** Scope is in the plan doc `purchase-conversion-rebuild-2026-05-04.md` Phase 2 section. Owned by Alfred.
- **Google Ads conversion tracking parity.** Out of scope for Phase 1; the same GTM dataLayer events can drive Google Ads conversion tags using the same content_name distinction. Separate playbook for whenever Nate is ready to mirror.
- **Reddit / LinkedIn / Calendly tag inventory.** Untouched in v23 cleanup. Possibly all still active, possibly some are legacy. Worth a follow-up audit pass with whoever owns those platforms.
- **The marketing-site `scheduled-confirmed.html` direct fbq call.** Still firing, still feeding the Calendar v3 CC. Removing it is a one-line edit + Netlify deploy that will eliminate the last source of double-counting for Calendar. Low priority.
- **Recalibration of per-event values from cohort data.** Phase 3 of the plan; trigger is 30 days post-publish. Manual cohort pull from BE source of truth, calculate Calendar→FirstNote and SignUp→FirstNote conversion rates, multiply by FirstNote LTV.
- **Audit of why CompleteRegistration is still ~488/day.** Decay theory says it's `first_capture=true` firing once per existing user. If volume hasn't decayed to 10-30/day by 2026-05-14, file a follow-up to audit `first_capture` gating in `AuthenticationCallback.tsx`.
- **Whether CpFN actually recovers from $408 toward humming-era $144.** Open question; depends on whether the Apr 16 restructure damage is the underlying cause (in which case attribution improvements alone won't fix it) or whether the broken signal was the primary driver. Re-evaluate at day 30.

---

## Open Questions

| Question | Owner | Resolution date |
|---|---|---|
| Does CompleteRegistration daily volume decay to true new-signup rate (~10-30/day) by 2026-05-14? | Nate (monitoring) / Alfred (audit if not) | 2026-05-14 |
| Does action_values populate in ad set Insights within 24-48h of publish? (Verification gate 4) | Nate | 2026-05-06 |
| Does the ad set exit learning phase within 7-14 days at current spend? (Verification gate 7) | Nate | 2026-05-18 |
| Does CpFN return toward humming-era $144 over 30 days, or stay elevated indicating restructure damage is the real cause? | Nate | 2026-06-04 |
| What is the actual real-new-signup count per day from BE source of truth? Used to validate gate 5 expectations. | Alfred (BE query) | When convenient |
| When does Phase 2 (CAPI for FirstNote) ship? | Alfred | Per his bandwidth |

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| Meta Ad Account | `act_1582817295627677` |
| Meta Pixel | `1625233994894344` (WebApp Actions) |
| Meta Business | `1462697704319496` (JotPsych) |
| GTM Container | `GTM-KL9RPN9V` (Web app) |
| GTM containerId | `200880687` |
| GTM accountId | `6258528322` |
| Live container version (post-cleanup) | `23` ("cleanup-renames-v1 (CC + GTM grokkability pass)") |
| Active campaign | `120245858870520548` ("Nate figuring shit out", OUTCOME_SALES, ACTIVE) |
| Active ad set | `120245858870530548` ("Nate figuring shit out", VALUE optimization, ACTIVE) |
| Ad set's `pixel_rule` | `{"and":[{"event":{"eq":"Purchase"}},{"or":[{"URL":{"i_contains":"jotpsych"}}]}]}` |
| Canonical CC (for reporting) | `1604667127308749` "[CANONICAL] Purchase: FirstNote+SignUp+Calendar (value-based)" |
| Tag 67 (FirstNote Purchase) | `[ACTIVE] Meta Purchase - First Note ($150)`, trigger 15, value 150 |
| Tag 68 (SignUp Purchase) | `[ACTIVE] Meta Purchase - Sign Up ($25)`, trigger 17, value 25 |
| Tag 69 (Calendar Purchase) | `[ACTIVE] Meta Purchase - Calendar Scheduled ($5)`, trigger 66, value 5 |
| Tag 26 (legacy FirstNote, paused) | `[ARCHIVED 2026-05-04] Meta - First Note Event (legacy custom event, replaced by Tag 67)` |
| Tag 27 (legacy SignUpConfirm, paused) | `[ARCHIVED 2026-05-04] Meta - SignUp Confirm Event (legacy custom event, replaced by Tag 68)` |
| Variable 64 (event_id reader) | `dlv_event_id`, Data Layer Variable v2, reads `event_id` |
| Trigger 15 | `FirstNote Event`, `_event == 'generatedFirstNote'` |
| Trigger 17 | `SignUp Confirm Event`, `_event == 'signupConfirm'` |
| Trigger 65 (orphan) | `[ORPHAN 2026-05-04] CompleteRegistration custom event (no tags bound after Tag 68 re-trigger)` |
| Trigger 66 (Calendar) | `[ACTIVE] Calendar Scheduled - Page URL i_contains scheduled-confirmed` |
| Archived v3 CCs (still tracked, plateau-ing) | `1755976485786147` (FirstNote v3), `1014486627931137` (SignUpConfirm v3), `26939511482340303` (CalendarScheduled v3) |
| GDN-1180 implementation file | `services/attribution/pixels.ts` on smartscribe-companion-apps origin/staging |
| Auth0 callback handler | `Views/AuthenticationCallback.tsx` on same |
| FirstNote dataLayer push sites (4) | `RecorderView.tsx:315`, `EncounterView.tsx:565`, `useEncounterSubmission.ts:50`, `EncounterViewV2.tsx:2658` |
| Marketing-site Calendar fbq | `site/scheduled-confirmed.html:111` (direct fbq, not via GTM) |
| META_CAPI_ACCESS_TOKEN | persisted in `~/.claude/.env`; minted 2026-04-29 via Events Manager UI |
| Plan doc | `plans/purchase-conversion-rebuild-2026-05-04.md` |
| Cleanup plan doc | `plans/cleanup-meta-cc-and-gtm-2026-05-04.md` |
| GTM publish log | `config/gtm/published-versions.log` |
| Pre-publish container snapshot | `config/gtm/snapshot-{tags,triggers,variables}-2026-05-04.json` |
| Apply scripts | `config/gtm/apply.py` (initial), `/tmp/cleanup_drill_v2.py` (cleanup) |
| Eligibility gate error | `error_subcode 2446368` "Pixel isn't eligible for value optimization" |
| CC type-mismatch error | `error_subcode 1760021` "The event Purchase should map to the category Purchase" |
| GTM workspace lock error | HTTP 400 "Workspace is already submitted" |
| GTM invalid-character errors | colon and em-dash both rejected; ASCII hyphen accepted |

---

## Sources

1. Meta Marketing API GET against ad set `120245858870530548` (2026-05-04, post-rebind): confirms `effective_status: ACTIVE`, `optimization_goal: VALUE`, `promoted_object.pixel_rule` matches the canonical rule string.
2. Meta Marketing API POST against same ad set with `promoted_object={pixel_id, custom_event_type: PURCHASE}`: returns `error_subcode 2446368` confirming standard-event VALUE eligibility gate.
3. Meta Marketing API POST against same ad set with `promoted_object={pixel_id, custom_event_type: OTHER, pixel_rule}`: returns `success: true`, transitions to `effective_status: IN_PROCESS` then ACTIVE within minutes — confirms pixel_rule binding bypasses the gate.
4. Meta pixel `/stats?aggregation=event` for last 30 min (2026-05-04 evening ET): shows 2 Purchase events plus 7 CompleteRegistration plus thousands of PageView/userID — confirms new Purchase tags reaching Meta from the live container.
5. GTM Tag Manager API GET against tags 26, 27 in workspace 24 pre-publish: shows ACTIVE state, correct trigger bindings, fingerprints from January 2025 — confirms May 2-4 drop is not a GTM regression.
6. Live GTM Preview walk on jotpsych.com → Auth0 → app.jotpsych.com → manual dataLayer pushes for `generatedFirstNote` and `CompleteRegistration` plus visit to `/scheduled-confirmed`: all three new Purchase tags fired with "Custom HTML - Succeeded" status (screenshots captured during session).
7. Meta API GET on 18 custom audiences on `act_1582817295627677` plus rule analysis: only `Website traffic_sans 1st note_L30D` (id 120219902594670548) references legacy `FirstNote` custom event; size 20, stale since 2025-03-03, not in any active ad set's targeting — confirms safe to pause legacy tags.
8. `git log origin/staging` on smartscribe-companion-apps post-fetch (2026-05-04): commit `b5c1a4cd5` ("feat: Capture jp_attribution cookie + fire signup pixels on Auth0 callback (gdn-1180)"), `bd745fd31` ("GDN-1305: stop GA4 sign_up over-firing"), `e413c13eb` ("fix(auth): pass connection + login_hint params through /signup (GDN-1360)") — confirm Marcus's Apr 29 + Apr 30 + later work.
9. `git grep` on origin/staging for `generatedFirstNote`: confirms 4 push sites all push `{event: 'generatedFirstNote', platform}` (or just `{event: 'generatedFirstNote'}` in v2) with no `event_id` field — Phase 2 prerequisite.
