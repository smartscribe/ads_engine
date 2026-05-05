---
title: "Meta Custom Conversions v3: event vs event_type Field Bug Fix"
date: 2026-04-23
author: Nate + Claude
memory_target: Long-term memory
scope: The third bug in the FirstNote/SignUp/Calendar CC stack. v1 (Apr 20) and v2 (Apr 22) both used rule field `event_type` which Meta's matcher silently ignores. v3 rebuild uses `event` paired with a URL condition, matching the UI-created CC shape that has been firing on this account since 2024.
confidence: high
supersedes: docs/jot-briefs/meta-custom-conversions-rebuild-2026-04-22.md (the v2 CCs it describes never matched a single event; v3 replaces them)
sources:
  - api_probing: 3 rule shapes tested against Meta CC create endpoint 2026-04-23
  - readback: existing UI-created CC "Page View" first_fired_time=2024-04-12, proves `event` format works
  - pixel_stats: 2 FirstNote + 6 SignUpConfirm pixel fires since v2 creation, zero matches on v2 CCs
---

# Meta Custom Conversions v3: event vs event_type Field Bug Fix

**Date:** 2026-04-23
**Memory target:** Long-term memory
**Scope:** Third bug in the CC stack discovered. `event_type` is not the correct rule field for event-name matching. Correct field is `event`, paired with a URL condition.
**Status:** Canonical as of 2026-04-23. v3 CCs live, ad set rebound, v2 renamed `_archived_*`. Same 24-48h monitoring window as before: watch for `offsite_conversion.custom.1755976485786147` in ad insights.

---

## TL;DR

The v2 CCs shipped 2026-04-22 also never matched a single pixel event over the 18h they were live. Pixel fired 2 FirstNote + 6 SignUpConfirm fires in that window; v2 CCs counted zero. Diagnosis: the rule field `event_type` is not what Meta's matcher keys on for event names. Correct field is `event`. Meta's create endpoint accepts either without error, but only `event` gets evaluated at match time. Verified by inspecting the account's UI-created CCs: seven live CCs all use `{"and":[{"event":{"eq":"..."}},{"or":[{"URL":{"i_contains":"..."}}]}]}`, including "Page View" which has been firing since 2024-04-12. Meta also rejects `event` alone (subcode 1760020), so a URL condition is required. v3 rebuild promoted an API probe CC to `FirstNote (Valued) v3` via rename, created SignUp v3 and Calendar v3 with the correct shape, PATCHed the ad set's `pixel_rule` to byte-match v3's FirstNote rule, and renamed v2 CCs to `_archived_*`. Three silent failure modes down (whitespace, cents, field name); the v3 state is the first actually-functional VALUE signal this account has had since the Apr 16 restructure.

---

## What Jot Should Commit to Memory

1. **Meta Custom Conversion rules use `event` for event-name matching, not `event_type`.** Both v1 (Apr 20) and v2 (Apr 22) used `event_type` and never matched. Meta's API accepts `event_type` at create with no error, no warning, and `is_custom_event_type_predicted: "0"` returned, but the matcher ignores rules keyed on `event_type`. The correct key is `event`. Verified against every UI-created CC on the account, and confirmed by "Page View" CC (rule uses `event`, first_fired 2024-04-12, last_fired 2026-04-14).

2. **Meta rejects `{"and":[{"event":{"eq":"X"}}]}` alone with subcode 1760020, "A conversion rule is required at creation time."** A URL condition must be paired with `event`. Canonical shape for a pure-custom event CC on this account: `{"and":[{"event":{"eq":"<EventName>"}},{"or":[{"URL":{"i_contains":"jotpsych"}}]}]}`. The URL filter is permissive enough to cover any pixel fire on *.jotpsych.com while satisfying Meta's schema requirement.

3. **`{"and":[{"event_name":{"eq":"X"}}]}` is also accepted at create but unverified.** API probe 2026-04-23 accepted it but we did not bind an ad set or wait for match signal. Treat as unknown. Prefer `event` + URL because it's empirically proven on this account.

4. **Always mimic the shape of a known-working UI-created CC before using API-only references.** Meta's API docs are incomplete on rule schema specifics. The account's own UI-created CCs are authoritative by existence: if they fire, the shape is right. Inspect first, build second.

5. **Three silent-failure failure modes now documented for Meta CC creation.** All three return API 200 success at create and leave the CC in "Never received event" forever:
   - v1: whitespace in rule value (UI warning banner catches this)
   - v2: cents vs dollars on `default_conversion_value` (UI render catches this)
   - v3-fix: wrong rule field name (`event_type` vs `event`), with no UI signal, silent forever
   The third mode is the nastiest because there is no UI signal. The only diagnostic is `first_fired_time: null` on the CC plus pixel stats showing actual fires.

6. **PATCH rename-to-archive is still the only archive mechanism.** `is_archived=true` via PATCH silently fails, as documented in the Apr 22 brief. Confirmed again 2026-04-23 on all three v2 CCs: rename worked, `is_archived` stayed false.

7. **Duplicate-rule guardrail (subcode 1760002) still applies.** v3 FirstNote's rule (`event=FirstNote AND URL contains jotpsych`) does not collide with v2 FirstNote's rule (`event_type=FirstNote`), so create was allowed. If ever re-attempting with the same shape, the rename-then-create pattern is necessary; or PATCH the existing CC in place.

8. **The v2 brief's memory items 1-12 remain valid for their respective failure modes.** The v2 brief is SUPERSEDED on the CC-specific setup (the v2 IDs are now archived, the rule is now `event` not `event_type`), but its broader diagnoses (whitespace trap, cents unit, promoted_object binding via exact-string match, PATCH-only-some-fields, duplicate-rule guardrail, multi-event optimization not available for OUTCOME_SALES+VALUE, Apr 16 restructure as root cause of CpFN collapse) are all still canonical.

---

## Why (Reasoning + Evidence)

### The third failure mode

Pixel stats 2026-04-22 20:36 ET (v2 live) through 2026-04-23 14:00 ET:

| Event | Fires | v2 CC matches |
|---|---|---|
| FirstNote | 2 | 0 |
| SignUpConfirm | 6 | 0 |
| CalendarScheduled | 0 | N/A |

All three v2 CCs stayed "Inactive / Never received event" for 18+ hours despite live pixel traffic in the events they were supposed to match. The Apr 22 brief had predicted an `offsite_conversion.custom.<cc_id>` row to appear in insights within 24-48h; instead, zero rows.

### The diagnosis: rule field is `event`, not `event_type`

API probe 2026-04-23:

| Rule shape | Create result |
|---|---|
| `{"and":[{"event":{"eq":"FirstNote"}}]}` | **REJECTED**, subcode 1760020 "A conversion rule is required at creation time" |
| `{"and":[{"event":{"eq":"FirstNote"}},{"or":[{"URL":{"i_contains":"jotpsych"}}]}]}` | ACCEPTED (id 1755976485786147) |
| `{"and":[{"event_name":{"eq":"FirstNote"}}]}` | ACCEPTED (id 795807576658478, archived as probe) |
| `{"and":[{"event_type":{"eq":"FirstNote"}}]}` | ACCEPTED (what v1/v2 used, never matches) |

Cross-referenced with every UI-created CC on the account. The "Page View" CC is the strongest reference:
- Rule: `{"and":[{"event":{"eq":"PageView"}},{"or":[{"URL":{"eq":"https://www.jotpsych.com"}}]}]}`
- creation_time: 2024-04-12T19:25:09+0000
- **first_fired_time: 2024-04-12T19:26:06+0000** (1 minute after creation)
- last_fired_time: 2026-04-14T16:19:25+0000

Two years of matching events on `event` field. That's the authoritative proof.

### v3 build

1. Promoted API probe `PROBE_event_plus_url_B` (id 1755976485786147) to `FirstNote (Valued) v3` via PATCH on name + description. Value already correct at 10000 cents. Rule `{"and":[{"event":{"eq":"FirstNote"}},{"or":[{"URL":{"i_contains":"jotpsych"}}]}]}`.
2. Created `SignUpConfirm (Valued) v3` (id 1014486627931137, $5) and `CalendarScheduled (Valued) v3` (id 26939511482340303, $15) via [scripts/fix-custom-conversions.py](../../scripts/fix-custom-conversions.py) with updated `build_rule` (line 78) that now produces `event` + URL shape.
3. Archived API probe `PROBE_event_name_C` (id 795807576658478) via rename to `_archived_probe_event_name_field_C_2026-04-23`. Never deleted.
4. PATCHed ad set 120245455503860548 `promoted_object.pixel_rule` to `{"and":[{"event":{"eq":"FirstNote"}},{"or":[{"URL":{"i_contains":"jotpsych"}}]}]}`, byte-identical to v3 FirstNote's rule so Meta binds the ad set to v3 on exact-string match. Ad set returned `success: true`, `effective_status: IN_PROCESS` (Meta's normal re-evaluation state post-edit).
5. Renamed all three v2 CCs to `_archived_<name> (event_type field bug)` via PATCH on name. Never deleted.

---

## How to Apply

| Situation | Response |
|---|---|
| Building a Meta Custom Conversion via API for a pure-custom event | Rule shape: `{"and":[{"event":{"eq":"<EventName>"}},{"or":[{"URL":{"i_contains":"<domain>"}}]}]}` with `custom_event_type: "OTHER"`. Never use `event_type` as the rule field. |
| A newly-created CC shows "Never received event" past 24h while pixel stats show fires | Do NOT wait longer. The rule is structurally wrong. Check `first_fired_time` via API; if null, rule never matched. Compare rule JSON to a known-working UI-created CC on the same account. |
| Inspecting an unfamiliar Meta account's CC architecture | Pull `/act_<id>/customconversions?fields=id,name,rule,first_fired_time,last_fired_time`. CCs with non-null `first_fired_time` are the gold standard for rule shape. Copy their structure for new CCs. |
| Someone proposes creating a CC matching only by event name (no URL condition) | Not possible for custom events on this account. Meta requires a URL condition. Use a permissive filter like `URL i_contains "<root-domain>"`. |
| Unpausing or restructuring a CC-dependent ad set | After any CC rebuild, PATCH the ad set's `promoted_object.pixel_rule` to the new CC rule byte-for-byte. Binding is exact-string match, not semantic. |
| Documenting a Meta API gotcha | Write it down as a memory with `Why` and `How to apply` fields. Meta's docs are incomplete and drift. |

---

## What This Brief Does NOT Cover

- **Whether `event_name` (singular) is actually a valid alternative rule field.** API accepted the probe create, but we did not bind an ad set to it or wait for a match signal before archiving it. Unknown. Prefer `event` + URL.
- **GDN-789 frontend dataLayer enrichment / EMQ fix.** Still pending Jackson/Marcus merge. Covered in [meta-pixel-gtm-architecture-correction-2026-04-20.md](meta-pixel-gtm-architecture-correction-2026-04-20.md).
- **CAPI paired FE+BE issue.** 0% CAPI event coverage still unfixed.
- **Weight recalibration.** $100/$5/$15 still Nate's rough first-pass estimates, not calibrated to actual cascade probabilities.

---

## Open Questions

- **Will `offsite_conversion.custom.1755976485786147` appear in ad insights `actions` within 24-48h?** Owner: Claude, monitor via API pull. Expected resolution 2026-04-25 PT. First real test of the v3 rebuild.
- **Will CpFN move back toward the $144 "humming" baseline over the next 7-14 days?** Owner: Nate, weekly review. Longer-horizon test of whether VALUE optimization with actually-working signal recovers performance.
- **Does the ad set exit learning?** Threshold is 50 conversions in 7 days per ad set. Our historical volume is ~5 FirstNote/week, so exit is unlikely. Accept if we stay in LEARNING; signal quality is what matters.

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| Meta Ad Account | `act_1582817295627677` |
| Meta Pixel | `1625233994894344` (WebApp Actions) |
| Active Campaign | `120245455503210548` (Farm: Testing - Q226, OUTCOME_SALES) |
| Active Ad Set | `120245455503860548` (Farm: All Value Props Q226, $200/day, VALUE) |
| **FirstNote (Valued) v3** | `1755976485786147` @ $100 (10000 cents), BOUND to ad set |
| **SignUpConfirm (Valued) v3** | `1014486627931137` @ $5 (500 cents) |
| **CalendarScheduled (Valued) v3** | `26939511482340303` @ $15 (1500 cents) |
| _archived_ FirstNote v2 | `4363987073922754` (event_type field bug) |
| _archived_ SignUpConfirm v2 | `1673233627279622` (event_type field bug) |
| _archived_ CalendarScheduled v2 | `829867779586914` (event_type field bug) |
| _archived_ FirstNote v1 | `3914250848710226` (whitespace + cents + event_type) |
| _archived_ SignUpConfirm v1 | `1960979881475090` (whitespace + cents + event_type) |
| _archived_ CalendarScheduled v1 | `1270312578633364` (whitespace + cents + event_type) |
| _archived_probe_event_name_field_C | `795807576658478` (API probe 2026-04-23) |
| Ad set's current pixel_rule (byte-match to v3 FirstNote) | `{"and":[{"event":{"eq":"FirstNote"}},{"or":[{"URL":{"i_contains":"jotpsych"}}]}]}` |
| Fix script | `scripts/fix-custom-conversions.py` |
| Manifest | `data/custom-conversions/valued-conversions-2026-04-23.json` |
| Reference UI-created CC (proof `event` works) | `1594516041309713` (Page View, first_fired 2024-04-12) |
| Meta error: rule shape rejected | `error_subcode 1760020` |
| Meta error: duplicate rule | `error_subcode 1760002` |
| CpFN baseline (humming era Apr 3-9) | $144 |
| CpFN current (Apr 17-22) | $408 |
