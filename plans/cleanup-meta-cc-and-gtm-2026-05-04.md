# Plan: Cleanup Meta Custom Conversions + GTM container for grokkability

**Date:** 2026-05-04
**Status:** plan, awaiting execution
**Owner:** Nate (decision approval), Claude (API execution)
**Related:** [purchase-conversion-rebuild-2026-05-04.md](purchase-conversion-rebuild-2026-05-04.md) (ships the canonical Purchase signal this cleanup leaves standing)

---

## Governing thought

Collapse the Meta Custom Conversions + GTM container surface area to the minimum needed to optimize on three valued events (FirstNote $150 / SignUp $25 / Calendar $5) via the single canonical Purchase signal. Rename everything that survives so it's clear what's active versus archived versus dead. Leave nothing in the surface that requires explanation by a person who wasn't here for the saga.

## Why this is needed

After the purchase-conversion-rebuild ships, the Meta CC list contains 19 entries (only 1 active, the rest various flavors of failed/superseded/dead from 2024-2026) and the GTM container contains 33 tags (most active, 4 paused, several from sub-flows that are confusing without context). New person looking at either list right now would have no idea what's load-bearing. That ambiguity IS the misattribution risk: someone (Nate, Marcus, future-Claude) makes a change against the wrong artifact and it silently breaks a campaign.

## What's getting touched

- **Meta Custom Conversions** on ad account `act_1582817295627677` (all 19)
- **GTM container** `GTM-KL9RPN9V` (workspace 26 → publish as v23)

## What's explicitly NOT getting touched

- Meta pixels themselves (WebApp Actions, JotPsych Actions, ads_engine_alex datasets)
- Marketing-site direct `fbq('trackCustom', 'CalendarScheduled')` in `scheduled-confirmed.html` (open question below; requires marketing-site code change + Netlify deploy)
- Reddit / LinkedIn / Google Ads conversion infrastructure (different ad platforms; separate decisions; Nate to confirm whether they're still active)
- Calendly "Meeting Booked" tags (different sales flow, not in the Purchase signal stack)
- Phase 2 CAPI work for Alfred (separate plan)

---

## Inventory + decisions

### Meta Custom Conversions (19 total, all on the ad account)

Categorized by current state. "Decision" column says what to rename to. Per Apr 23 brief, `is_archived` PATCH silently fails so rename is the only archive mechanism for CCs.

#### Keep active (1)

| ID | Current name | Last fired | Decision |
|---|---|---|---|
| 1604667127308749 | Purchase (combined, value-based v1) | 2026-05-05 | **Rename to** `[CANONICAL] Purchase: FirstNote+SignUp+Calendar (value-based)`. Single source of truth for ad set optimization. |

#### Keep, already archived from this session (3)

These will plateau on their existing counts now that the legacy GTM tags 26/27 are paused. Calendar v3 will keep slowly accumulating from the marketing-site direct fbq call until that's removed (open question below).

| ID | Current name | Decision |
|---|---|---|
| 1755976485786147 | _archived_FirstNote (Valued) v3 (superseded by Purchase value-based 2026-05-04) | Leave name as-is; already clearly marked |
| 1014486627931137 | _archived_SignUpConfirm (Valued) v3 (superseded by Purchase value-based 2026-05-04) | Leave name as-is |
| 26939511482340303 | _archived_CalendarScheduled (Valued) v3 (superseded by Purchase value-based 2026-05-04) | Leave name as-is |

#### Keep, already archived from the v1/v2/v3 saga (6)

Failed attempts that never fired. Already prefixed clearly with the bug they hit. Leave alone.

| ID | Current name | Decision |
|---|---|---|
| 4363987073922754 | _archived_FirstNote (Valued) v2 (event_type field bug) | Leave |
| 1673233627279622 | _archived_SignUpConfirm (Valued) v2 (event_type field bug) | Leave |
| 829867779586914 | _archived_CalendarScheduled (Valued) v2 (event_type field bug) | Leave |
| 3914250848710226 | _archived_FirstNote (Valued) v1 (whitespace+cents bug) | Leave |
| 1960979881475090 | _archived_SignUpConfirm (Valued) v1 (whitespace+cents bug) | Leave |
| 1270312578633364 | _archived_CalendarScheduled (Valued) v1 (whitespace+cents bug) | Leave |

#### Keep, archived API probes/tests (3)

| ID | Current name | Decision |
|---|---|---|
| 795807576658478 | _archived_probe_event_name_field_C_2026-04-23 | Leave |
| 3545141088966373 | TEST FirstNote V3 | **Rename to** `_archived_TEST_FirstNote_V3_2026-04-22`. Clarify it's a test artifact and date it. is_archived already true (UI archive worked here for some reason). |
| 2813906782342167 | TEST FirstNote V1 | **Rename to** `_archived_TEST_FirstNote_V1_2026-04-20`. Same. |

#### Dead pre-2026 (6)

These haven't fired in over a year and reference flows (Demo, Trial Start, Page View) that no longer exist in the active funnel. Currently confusing because their names look like they could be live.

| ID | Current name | Last fired | Decision |
|---|---|---|---|
| 1594516041309713 | Page View | 2026-04-14 | **Rename to** `_dead_PageView_pre-2026-04-14_was-on-WebApp-Actions-pixel` |
| 343158638749858 | Trial Start | 2025-01-28 | **Rename to** `_dead_2025-01_TrialStart_old-funnel` |
| 812649520925814 | Demo Visit | 2024-11-18 | **Rename to** `_dead_2024-11_DemoVisit_old-funnel-1` |
| 1840242763119689 | Demo Visit | 2024-11-18 | **Rename to** `_dead_2024-11_DemoVisit_old-funnel-2` |
| 427658886698467 | Demo Schedule Success | 2024-10-23 | **Rename to** `_dead_2024-10_DemoScheduleSuccess` |
| 956970892560523 | Demo Scheduled | 2024-09-08 | **Rename to** `_dead_2024-09_DemoScheduled` (is_archived already true) |

After this pass, the CC list reads top-to-bottom as: 1 canonical (`[CANONICAL]`), 3 superseded-this-session (`_archived_*v3*superseded_*`), 6 failed (`_archived_*v1*v2*bug*`), 3 test artifacts (`_archived_TEST_*` / `_archived_probe_*`), 6 dead pre-2026 (`_dead_*`). Anyone scanning instantly knows which to ignore.

---

### GTM container `GTM-KL9RPN9V` (33 tags in workspace 26)

#### Active production canon (KEEP, rename for clarity, 9 tags)

| Tag ID | Current name | Decision | Why it earns its place |
|---|---|---|---|
| 67 | Meta Purchase - First Note | **Rename to** `[ACTIVE] Meta Purchase: First Note ($150)` | Phase 1 canonical optimization signal |
| 68 | Meta Purchase - Sign Up | **Rename to** `[ACTIVE] Meta Purchase: Sign Up ($25)` | Phase 1 canonical optimization signal |
| 69 | Meta Purchase - Calendar Scheduled | **Rename to** `[ACTIVE] Meta Purchase: Calendar Scheduled ($5)` | Phase 1 canonical optimization signal |
| 56 | FB_CONVERSIONS_API-...-Web-Tag-GA4_Config | LEAVE name (Meta wizard auto-generates) | Meta CAPI integration, fires server-side via sGTM |
| 57 | FB_CONVERSIONS_API-...-Web-Tag-GA4_Event | LEAVE name | Same |
| 58 | FB_CONVERSIONS_API-...-Web-Tag-Pixel_Event | LEAVE name | Same |
| 59 | FB_CONVERSIONS_API-...-Web-Tag-Pixel_Setup | LEAVE name | Same |
| 23 | Meta - Page Views | **Rename to** `[ACTIVE] Meta Pixel: PageView` | Base pixel pageview |
| 33 | Meta - user_id | **Rename to** `[ACTIVE] Meta Pixel: user_id (advanced matching)` | Identity match for EMQ |

#### Active non-Meta but still production (KEEP, leave alone for now, 11 tags)

GA4, Reddit, LinkedIn, Calendly, conversion linker, generic user_id. Out of scope for THIS cleanup since they're not Meta optimization, but worth confirming each is still useful in a follow-up pass.

| Tag ID | Current name |
|---|---|
| 3 | Conversion linker (Google Ads infrastructure) |
| 7 | GA4 Configure |
| 9 | user_id (generic dataLayer push, used by GA4) |
| 14 | GA4 - Checkout Success Event |
| 16 | GA4 - First Note Event |
| 18 | GA4 - SignUp Confirm Event |
| 22 | GA4 - Trial Button Click |
| 36, 37, 38, 39, 40, 41, 43 | Reddit Pixel tags (7 tags) |
| 45 | LinkedIn_First Note |
| 61, 63 | Calendly Meeting Booked tags |

Open question: are Reddit and LinkedIn ad campaigns still active? If yes, leave. If not, batch-pause in a follow-up.

#### Other Meta legacy still firing (REVIEW, 3 tags)

These fire to Meta on legacy events but aren't bound to the Purchase signal. They feed Meta's pixel data for audience modeling and lookalikes, which can be useful. Question is whether the noise outweighs the value.

| Tag ID | Current name | Decision |
|---|---|---|
| 30 | Meta - Checkout Success Event | LEAVE (it fires on `signupConfirm` trigger 13 = ? need to verify; might be redundant with Tag 68 now) |
| 32 | Meta - Trial Button Click | LEAVE (fires on link clicks, audience signal) |
| 33 | Meta - user_id | KEEP (advanced matching, listed above) |

Actually — need to verify Tag 30 trigger 13 ("Checkout Success Event"). If it fires on `signupConfirm`, it's now redundant with Tag 68 and we'd want to pause. Verify before execution.

#### Already paused (5 tags)

| Tag ID | Current name | Decision |
|---|---|---|
| 26 | Meta - First Note Event | **Rename to** `[ARCHIVED 2026-05-04] Meta - First Note Event (legacy custom event, replaced by Tag 67)`. Stay paused. |
| 27 | Meta - SignUp Confirm Event | **Rename to** `[ARCHIVED 2026-05-04] Meta - SignUp Confirm Event (legacy custom event, replaced by Tag 68)`. Stay paused. |
| 29 | Meta First Note 2 - Test | **Rename to** `[ARCHIVED-TEST] Meta First Note 2 - Test`. Stay paused. |
| 31 | Meta - Knowledge Base Clicked Event | LEAVE (already paused, low priority) |
| 20 | GA4 - Knowledge Base Clicked Event | LEAVE (already paused, low priority) |

After this pass, GTM tag list reads with `[ACTIVE]`, `[ARCHIVED]`, `[ARCHIVED-TEST]` prefixes on Meta-related tags. Non-Meta tags untouched. The 4 FB CAPI tags keep their wizard-generated names because Meta's UI overwrites custom names if you re-run the wizard.

---

### Triggers (10 total in the container)

| Trigger ID | Name | Used by | Decision |
|---|---|---|---|
| 65 | CompleteRegistration Event | (none after v22 — Tag 68 was re-triggered to 17) | **Rename to** `[ORPHAN 2026-05-04] CompleteRegistration custom event (no tags bound)`. Leave in workspace as future reference. Don't delete in case we want to re-bind something later. |
| 66 | Calendar Scheduled Page View | Tag 69 | KEEP, **rename to** `[ACTIVE] Calendar Scheduled (Page URL contains /scheduled-confirmed)` |
| 17 | SignUp Confirm Event | Tag 68 + others | KEEP, leave name |
| 15 | FirstNote Event | Tag 67 + others | KEEP, leave name |
| 13 | Checkout Success Event | Tag 30 (legacy) + others | KEEP, may need clarification rename |
| 19 | help_click Event | (paused tags only) | KEEP |
| 21 | Trial Button Click | Tag 32, 22, 40 | KEEP |
| 8 | user id trigger | Tag 9, 33, 39 | KEEP |
| 60 | Private Practice Calendly Confirmation | Tag 61 | KEEP |
| 62 | Group Practice Calendly Confirmation | Tag 63 | KEEP |
| 46 | FB_CONVERSIONS_API Web DOM Ready | Tags 56, 59 | LEAVE (Meta wizard) |
| 47 | FB_CONVERSIONS_API Web Custom Event | Tags 57, 58 | LEAVE (Meta wizard) |

Triggers I missed in the count above: more than 10 actually, around 12 with the FB CAPI ones. Will verify during execution.

---

## Execution order

All steps are safe and reversible (renames don't break wiring; paused tags stay paused; nothing deleted).

1. **Meta CC renames** (Meta Marketing API, ~15 POSTs) — independent of GTM, can run anytime
2. **GTM workspace edits** (PUT on each tag/trigger to update name; tags 26/27/29 already paused from v22, just renaming):
   - Create new workspace (per GTM, post-publish workspaces lock)
   - Update tag names + paused states
   - Update trigger names (especially trigger 65 orphan flag)
3. **Cut + publish GTM v23**
4. **Verify**:
   - Meta CC list: scan top-to-bottom, only `[CANONICAL]` is unprefixed-with-marker
   - GTM tag list: every Meta-related tag has clear `[ACTIVE]` or `[ARCHIVED]` prefix
   - Live container is v23, has all the rename changes

---

## Risks

1. **Tag 30 ("Meta - Checkout Success Event") binding to trigger 13.** If trigger 13 fires on `signupConfirm`, this tag is firing a Meta custom event "Checkout Success" alongside our new Purchase tag for the same user action. Need to verify trigger 13's condition before deciding if Tag 30 should also be paused.
2. **Reddit / LinkedIn / Calendly active campaigns.** Cleanup proposal leaves these alone. If any of those platforms are unused, that's noise that should also be cleaned in a follow-up. Not blocking this plan.
3. **Marketing-site direct fbq for CalendarScheduled** keeps firing CalendarScheduled custom event from `scheduled-confirmed.html` until the marketing-site code change happens. Calendar v3 CC will keep accumulating fires from this. Low impact but mildly polluting. Open question below.
4. **Meta CC renames silently failing.** Apr 22 brief noted Meta sometimes silently rejects CC field updates. Verify each rename via GET after PATCH.

---

## Open questions before execution

1. **Reddit + LinkedIn tags: still active ad campaigns?** If no, batch-pause them too in this cleanup. If yes, leave for now.
2. **Marketing-site direct `fbq('trackCustom', 'CalendarScheduled')`:** kill it now (5-min Netlify deploy) or leave for later? Killing it eliminates the last source of double-firing for Calendar.
3. **Trigger 13 condition (used by legacy Tag 30 "Meta - Checkout Success Event"):** verify before execution. If it fires on `signupConfirm`, also pause Tag 30 to remove redundant Meta custom event for the same user action.
4. **Tag 9 / Tag 33 (user_id) and Tag 32 (Trial Button Click):** legacy custom events that fire on every page; useful for audience modeling but contribute zero to the Purchase optimization signal. Leave as-is or pause? Recommendation: leave (they enrich Meta's audience profile without polluting the optimization signal).

---

## Out of scope

- Meta pixel deactivation (JotPsych Actions, ads_engine_alex orphaned datasets) — separate decision
- Reddit / LinkedIn pixel inventory cleanup — separate platform, separate cleanup pass
- Marketing-site code changes — handled separately if needed
- Phase 2 CAPI for FirstNote (Alfred's ticket from purchase-conversion-rebuild plan)
- Renaming the "Nate figuring shit out" campaign / ad set — cosmetic; can be done anytime in Meta Ads Manager UI

---

## What "done" looks like

After this cleanup, when Nate or anyone else opens:

- **Meta Custom Conversions list:** sorted top-to-bottom, the first row is `[CANONICAL] Purchase: FirstNote+SignUp+Calendar (value-based)` and the rest are clearly prefixed `_archived_*` or `_dead_*`. No ambiguity about which CC is live.
- **GTM container tag list:** active Meta-stack tags clearly tagged `[ACTIVE] Meta Purchase: ...` etc. Paused/archived tags tagged `[ARCHIVED 2026-05-04]` with the reason embedded in the name. Non-Meta platforms (GA4, Reddit, LinkedIn, Calendly) untouched.
- **GTM trigger list:** orphan trigger 65 marked `[ORPHAN]` so future-self knows it's not driving anything.

The whole stack should be groqquable in 30 seconds without a tour guide.
