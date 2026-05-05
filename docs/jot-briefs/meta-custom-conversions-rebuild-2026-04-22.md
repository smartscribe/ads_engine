---
title: "Meta Custom Conversions Rebuild: v2 with Cents-Unit Fix + Multi-Event Limit Confirmed"
date: 2026-04-22
author: Nate + Claude
memory_target: Long-term memory
scope: Diagnosis and fix of the two bugs in the Apr 20 Custom Conversions (whitespace + cents unit), the Apr 16 restructure as root cause of the CpFN collapse, v2 rebuild methodology, and Meta's hard limit on differential-weight multi-event optimization for OUTCOME_SALES + VALUE campaigns
confidence: high
supersedes: docs/jot-briefs/meta-custom-conversions-values-2026-04-20.md (the CC setup it describes was broken; this brief replaces it)
sources:
  - conversation: Nate and Claude, 2026-04-22 evening ads-engineering session
  - meta_api: Pixel /stats, Ads Insights, Custom Conversion CRUD, AdSet promoted_object probing
  - changelog: ads_engine/CHANGELOG.md 2026-04-22 entry
  - brief: docs/jot-briefs/meta-ads-snapshot-2026-04-21.md (account state before tonight)
  - brief: docs/jot-briefs/meta-custom-conversions-values-2026-04-20.md (the now-superseded CC setup)
---

# Meta Custom Conversions Rebuild: v2 with Cents-Unit Fix + Multi-Event Limit Confirmed

**Date:** 2026-04-22
**Memory target:** Long-term memory
**Scope:** Two compounding bugs in the Apr 20 Custom Conversions explain 7 days of wasted spend; v2 rebuild lands real value signal; Meta's multi-event differential-weight optimization is structurally unavailable for OUTCOME_SALES + VALUE and we should stop trying to build it
**Status:** Canonical as of 2026-04-22. Value signal now live; 24-48h window to confirm `conversion_values` populate in ad insights.

---

## TL;DR

The Apr 20 Custom Conversions (FirstNote, SignUpConfirm, CalendarScheduled) that were supposed to give Meta real dollar signal for VALUE optimization never fired a single matching event over the 50 hours they were live. Two compounding bugs caused this: whitespace in the `event_type` rule value so the matcher never matched, and `default_conversion_value` stored in cents instead of dollars so `$100` rendered as `$1.00` in the UI. Together they explain the CpFN collapse after the Apr 16 restructure: Meta has been optimizing on a zero-dollar signal for 7 straight days. Tonight we rebuilt all three as v2 with clean rules and correct cent values, forced the ad set to rebind to the new FirstNote (Valued) v2, renamed the v1 CCs with `_archived_` prefix, and unpaused the ad set. The multi-event differential-weight portfolio optimization Nate wanted (FN $100 + SU $5 + Cal $15) is NOT available for our OUTCOME_SALES + VALUE campaign type, confirmed via exhaustive API probing and GUI inspection; single-event $100 FN is the de facto maximum capability. GDN-789 (frontend dataLayer enrichment) and CAPI remain separate unfixed workstreams.

---

## What Jot Should Commit to Memory

1. **Meta's `default_conversion_value` on Custom Conversions is stored in CENTS, not the currency's main unit.** Passing `100` via the Create endpoint stored as 100 and rendered in Meta's UI as `$1.00`. To get `$100.00` you must pass `10000`. This contradicts what Meta's docs imply and there is no public acknowledgment of the unit convention. **Always pass `dollars * 100` and always eyeball the Meta UI after create.** API-level success is insufficient; the API readback reports the same integer that was sent, so the bug is invisible at the API layer alone.

2. **Meta Custom Conversion rule values must be whitespace-clean.** If the `event_type.eq` string has a leading/trailing space (or any hidden whitespace), Meta's matcher treats it as a different event name from the actual pixel event. The CC stays Inactive ("Never received event") despite real events firing nonstop. Meta's UI raises a warning banner "There is a blank space at the beginning or end of one or more of the rules" when this occurs. Build rule strings via `json.dumps` on explicit Python dicts with `strip()`ed values to eliminate the class.

3. **Custom Conversion rule resolution from an ad set is EXACT-STRING byte-match, not semantic match.** If the ad set's `promoted_object.pixel_rule` is `{"and": [{"event_type": {"eq": "FirstNote"}}]}` (with spaces between JSON tokens) and the CC's rule is `{"and":[{"event_type":{"eq":"FirstNote"}}]}` (compact), Meta binds the ad set to whichever CC rule string matches byte-for-byte, even though the rules are semantically identical. To force rebinding, PATCH the ad set's `pixel_rule` to the desired CC's exact string.

4. **Meta rejects creating two Custom Conversions with the same rule in the same ad account.** Error `error_subcode 1760002` "Duplicate Custom Conversion Rule", even when one of them is renamed with an `_archived_` prefix. Rename alone does not release the rule slot. The only ways to ship a "fixed" CC with the same rule are: (a) PATCH the existing one in place if only the value or name needs to change, or (b) create the new one with a rule that is functionally identical but string-different (e.g., different JSON whitespace), which is the route we took for FirstNote v2 vs v1.

5. **Custom Conversion fields writable via PATCH: `name`, `description`, `default_conversion_value`. NOT writable: `rule`, `custom_event_type`, `event_source_id`, `is_archived`.** Meta accepts `is_archived=true` in the PATCH payload and returns `{"success": true}`, but silently ignores the flag; readback still shows `is_archived: false`. The only effective "archive" mechanism for a CC is renaming it with a convention like `_archived_<original_name> (reason)`.

6. **`promoted_object.custom_conversion_id` is rejected ("invalid combination of parameters", error_subcode 1885014) for OUTCOME_SALES + VALUE ad sets.** The supported `promoted_object` shape is exactly `{pixel_id, custom_event_type, pixel_rule}` (+ optional `smart_pse_enabled`). Binding an ad set to a specific CC must go through the rule string, never through direct CC ID reference.

7. **Meta's Multiple Conversion Events Optimization (differential-weight portfolio) is NOT exposed for OUTCOME_SALES + VALUE campaigns.** Confirmed via: (a) API probing: every speculative field name (`conversion_events`, `optimization_conversion_events`, `multiple_conversion_events`, `value_goal_spec`, `conversion_spec`, `pixel_rules` plural, etc.) returned "nonexisting field"; (b) GUI inspection: the ad set's "Show more settings" panel only reveals attribution window, conversion count, delivery type. The feature is restricted to Advantage+ Shopping and similar ecommerce-oriented campaign types. **Do not attempt this again without a prior check of Meta's campaign-type capabilities matrix.**

8. **A single combined Custom Conversion with an OR rule (matching multiple event types) cannot assign differential values.** The CC supports rule composition like `{"or": [{"event_type": {"eq": "FirstNote"}}, {"event_type": {"eq": "SignUpConfirm"}}]}` but `default_conversion_value` is single-scalar across the whole CC. Using a blended weighted-average value would actively mislead Meta's optimizer toward event *volume* (SignUp dominates volume at ~50/week vs FirstNote ~37/week) rather than event *value* (FirstNote at $100 dominates economic value). So this is not a valid workaround for multi-event differential weighting.

9. **The CpFN-is-sole-KPI rule (feedback memory) should be read as "prefer economic-dollar-signal optimization, which today happens to equal CpFN."** The rule's conceptual intent is the economic lens, not FirstNote specifically. If Meta ever exposes multi-event differential-weight optimization for our campaign type, portfolio optimization over correctly-calibrated dollar weights would satisfy the rule's spirit just as well as CpFN alone. Today that's a moot point because Meta doesn't support it for OUTCOME_SALES + VALUE, so CpFN remains the operational KPI by necessity rather than by choice.

10. **The Apr 16 restructure was the root cause of the CpFN collapse, not the EMQ attribution gap.** Three compounding effects: (a) paused the OUTCOME_LEADS campaigns that had been driving $144 CpFN during the Apr 3-9 "humming" week; (b) flipped the consolidated ad set to OUTCOME_SALES + VALUE optimization, which requires dollar signal on events to function; (c) the Apr 20 Custom Conversions that were supposed to provide that dollar signal were broken and never fired. Net: Meta has been optimizing on a zero-dollar signal since Apr 16. EMQ 4.0/10 is a separate real issue (attribution rate ~14%) that GDN-789 addresses, but it is NOT the proximate cause of the last 6 days of CpFN pain.

11. **Pixel event firing and CC rule matching are separable failure modes.** On Apr 15-21, the pixel fired 37 FirstNote events correctly, but the v1 CCs matched zero of them (whitespace bug), and Meta's ad attribution only credited 5 of the 37 pixel fires to ads (EMQ gap). Three separate systems (pixel, CC rule, ad attribution), three separate potential failure points. Always check each independently when diagnosing VALUE optimization issues.

12. **Post-CC-fix monitoring: watch for `offsite_conversion.custom.<cc_id>` in ad insights `actions` within 24-48h after the first matching pixel event fires.** If absent after 48h, escalate. `conversion_values` should populate at the CC's configured default value per matched event. On 2026-04-22 before the fix, both fields were empty across the entire account for 7 days. That was the invisible failure state we are now resolving.

---

## Why (Reasoning + Evidence)

### The Apr 16 cascade and the 7 days of $0 signal

Weekly CpFN trajectory from Meta-attributed data[^1]:

| Week | Spend | FN attributed | CpFN | Notes |
|---|---|---|---|---|
| Apr 3-9 | $2,305 | 16 | $144 | "Humming" era (OUTCOME_LEADS) |
| Apr 10-16 | $4,550 | 12 | $379 | Pixel outages Apr 11-12, CSP fix Apr 13, restructure Apr 16 |
| Apr 17-22 (6d) | $2,042 | 5 | $408 | Post-restructure, VALUE optimization on $0 signal |

The restructure landed on 2026-04-16: paused OUTCOME_LEADS campaigns that had been producing the $144 CpFN weeks, consolidated 5 value-prop ad sets into one (`Farm: All Value Props Q226`, id `120245455503860548`), flipped it to OUTCOME_SALES + VALUE optimization. Per the Apr 21 snapshot brief[^2], this was correct structurally (learning-phase-threshold math favored consolidation) but left one gap: VALUE optimization requires dollar signal on events, and at Apr 16 no such signal existed.

The Apr 20 Custom Conversions brief[^3] documented the intended fix: three CCs (FirstNote @ $100, SignUpConfirm @ $5, CalendarScheduled @ $15) with `default_conversion_value` set via the Meta API, supposed to give Meta per-event dollar signal without engineering work. It was the right architectural move. It was also silently broken from creation.

### The two bugs in the Apr 20 CCs

**Bug 1: whitespace in the rule `event_type` value.** The API accepted the create call and the CC existed, but Meta's matcher treats `" FirstNote"` or `"FirstNote "` as different event names from `"FirstNote"`. Meta's UI (Events Manager > Custom Conversions > FirstNote (Valued)) flagged this with a warning banner: *"There is a blank space at the beginning or end of one or more of the rules for this Custom Conversion. If the blank space isn't correct, it may impact the quality and quantity of Custom Conversions received."* The CC stayed Inactive (0 events matched) over the 50 hours it was live.

**Bug 2: `default_conversion_value` in cents, not dollars.** The Apr 20 create passed `100` intending dollars; Meta stored it as 100 (treating it as cents); the UI rendered it as `$1.00`. The API readback returned `default_conversion_value: 100` identically to what was sent, making the bug invisible from API-only inspection. The bug was caught only by eyeballing the Meta UI after a first-pass v2 rebuild that also passed `100`.

Both bugs compounded to guarantee zero value signal. Even after the rule whitespace was fixed in v2, the cents bug alone would have given Meta a $1 signal instead of $100, functionally still useless.

### The v2 rebuild (tonight)

Executed via [scripts/fix-custom-conversions.py](../../scripts/fix-custom-conversions.py). Key engineering decisions:

- **Rule construction via `json.dumps` on explicit dicts** with `strip()` on the event name input, eliminating whitespace as a class of error.
- **Values passed as `dollars * 100`** (explicit cents) after the v2 first-pass confirmed the unit issue.
- **Halt-and-verify gate**: the script supports `--only <event_name>` to create one CC at a time, stop, and wait for UI eyeball before proceeding. Used to catch the cents-unit bug on the first v2 create before compounding it across three CCs.
- **Never-delete discipline**: the 3 broken v1 CCs were renamed with `_archived_<name> (whitespace+cents bug)` prefix and left in place. Never deleted.
- **PATCH-in-place pivot**: when Meta rejected creating a v3 FirstNote with value=10000 (duplicate-rule guardrail against the already-created v2 FirstNote), we PATCHed v2's `default_conversion_value` to 10000 in place. Three writable fields confirmed via this pivot: `default_conversion_value`, `name`, `description`. `is_archived` was attempted, returned success, but was silently ignored.

### Forcing the ad set to bind to v2

After creating the v2 CCs, the ad set's UI still showed the conversion event as `FirstNote (Valued) (ID 3914250848710226)`, the broken v1. Root cause: Meta resolves `promoted_object.pixel_rule` to CC via exact-string match. v1's rule `{"and": [{"event_type": {"eq": "FirstNote"}}]}` matched the ad set's rule byte-for-byte. v2's rule `{"and":[{"event_type":{"eq":"FirstNote"}}]}` (compact JSON, no inter-token spaces) did not. PATCHing the ad set's `pixel_rule` to v2's compact form forced Meta to rebind. The UI confirmed the switch: conversion event now reads `FirstNote (Valued) v2 (ID 4363987073922754)`.

Attempting `promoted_object.custom_conversion_id` to force binding directly was rejected with `error_subcode 1885014` "invalid combination of parameters", consistent with the Apr 20 note that this combo doesn't work for OUTCOME_SALES + VALUE.

### The multi-event question (differential-weight portfolio)

Nate raised an important question: if the dollar weights are correct, does the CpFN-is-sole-KPI rule still apply? Answer: the rule's intent was the economic lens, not FirstNote specifically. Dollar-weighted portfolio optimization across multiple events would satisfy the rule's spirit. So conceptually, yes, multi-event VALUE optimization is aligned with the framework.

The implementation question is where it died. Exhaustive probing found no way to configure this on our campaign type:

| Attempt | Result |
|---|---|
| GET `/adset?fields=conversion_events` | "nonexisting field" |
| GET `/adset?fields=optimization_conversion_events` | "nonexisting field" |
| GET `/adset?fields=multiple_conversion_events` | "nonexisting field" |
| GET `/adset?fields=value_goal_spec` | "nonexisting field" |
| GET `/adset?fields=conversion_spec` | "nonexisting field" |
| GET `/adset?fields=promoted_object{pixel_rules,...}` | "nonexisting field (pixel_rules)" |
| GUI "Show more settings" on ad set | Only attribution window, conversion count, delivery type |
| GET campaign `is_advantage_plus` | "nonexisting field" (campaign is OUTCOME_SALES standard, not Advantage+) |

Meta's Multiple Conversion Events Optimization feature is restricted to specific campaign types: primarily Advantage+ Shopping and similar ecommerce surfaces. OUTCOME_SALES with VALUE optimization is not on the list.

**Workarounds considered and rejected:**

- **Combined CC with OR rule, single value** (e.g., a new CC matching any of FN/SU/Cal with `default_conversion_value=$42` as a volume-weighted blend). Rejected: Meta would optimize for event volume (SignUp dominates at ~50/week) rather than event value (FirstNote at $100 dominates economic dollars), actively worse than single-event FN at $100.

- **Three parallel ad sets, one per event.** Rejected: splits our already-thin signal 3x (5 FN/week → 1.7 FN/ad set/week), none would exit learning phase.

- **Change campaign objective to Advantage+ Shopping.** Rejected: we aren't ecommerce, wrong product fit, massive blast radius.

**Outcome: we stay at single-event VALUE optimization bound to FirstNote (Valued) v2 at $100.** SignUp (Valued) v2 and Calendar (Valued) v2 still fire on pixel events and register their $5/$15 values in reporting, but do not influence bidding.

---

## How to Apply

| Situation | Response |
|---|---|
| Someone proposes creating a Meta Custom Conversion with a `default_conversion_value` | Pass the value in CENTS (dollars × 100). Confirm the UI renders the correct dollar amount before proceeding. API-level readback is insufficient. |
| A Custom Conversion says "Inactive" / "Never received event" despite live pixel traffic for the event it should match | Check Meta's UI for a whitespace warning banner on the CC's rule page. If present, the rule value has hidden whitespace and needs rebuild (rules cannot be edited post-create). |
| Creating a "fixed" CC with the same rule as an existing one | Meta will reject with `error_subcode 1760002`. Either PATCH the existing CC in place (if fixing value/name/description only) or accept that the new CC must have a string-different rule from the original. |
| Adjusting an ad set's CC binding | Update the ad set's `promoted_object.pixel_rule` string to byte-match the target CC's rule. Do not attempt `promoted_object.custom_conversion_id`; it's rejected for OUTCOME_SALES + VALUE. |
| Archiving a broken Custom Conversion | Rename to `_archived_<original_name> (reason)` via PATCH on `name`. The `is_archived` PATCH field returns success but is silently ignored. |
| Someone asks to set up multi-event differential-weight VALUE optimization | Not available for our OUTCOME_SALES + VALUE campaign type. Single-event is the operational maximum. Do not re-research this unless Meta documents a new feature for our campaign type specifically. |
| Someone asks if SignUp (Valued) v2 or Calendar (Valued) v2 are being "optimized toward" | No. They fire and register their values in reporting, but the ad set's bidding is driven exclusively by the FirstNote (Valued) v2 CC. They're instrumentation, not optimization. |
| Someone asks about CpFN vs portfolio value as the KPI | The rule is "economic lens first." Today that equals CpFN because Meta doesn't expose multi-event differential weighting for our campaign type. If that changes in the future, portfolio-weighted optimization would satisfy the same rule. |
| Diagnosing "why aren't my ads converting" in VALUE-optimized campaigns | Check three systems in order: (1) pixel event firing (Events Manager > Pixel > event count), (2) Custom Conversion rule-match (CC status "Active" vs "Inactive"), (3) ad attribution (`actions` + `conversion_values` in Ads Insights API). Any of the three can fail independently. |
| Evaluating a Meta API gotcha discovery | Write it down. Meta's docs are incomplete and drift; our memory is the institutional record. |

---

## What This Brief Does NOT Cover

- **GDN-789 frontend dataLayer enrichment / EMQ fix.** Verified 2026-04-22 but awaits merge by Jackson or Marcus. Covered in [meta-pixel-gtm-architecture-correction-2026-04-20.md](meta-pixel-gtm-architecture-correction-2026-04-20.md) and [gdn-789-frontend-verified-2026-04-22.md](gdn-789-frontend-verified-2026-04-22.md).
- **CAPI paired FE+BE issue.** 0% CAPI event coverage remains. Blocked on FE/BE architectural decision between Jackson and Marcus.
- **Weight calibration.** The $100/$5/$15 weights are Nate's rough first-pass values, not calibrated to actual cascade probabilities (SU→FN, Cal→paying). Recalibration would be a future exercise if multi-event ever becomes available, or if the single-event weight of $100 FN proves to be miscalibrated.
- **Exit from learning phase.** The ad set just entered learning fresh as of 2026-04-22 with 0 conversions. Whether it exits (50 events in 7 days per ad set threshold) given our ~5 FN/week volume is an open question; the more likely outcome is that it stays in learning and we accept that state.
- **Campaign objective change (to a type that supports multi-event).** Not evaluated. Would be a much larger decision with downstream effects on audience, bidding, and reporting.

---

## Open Questions

- **Will `offsite_conversion.custom.4363987073922754` appear in ad insights `actions` within 48h of the first matching FirstNote event post-unpause?** Owner: Claude, monitoring via API pull. Expected resolution by 2026-04-24 PT.
- **Will `conversion_values` populate at $100/FirstNote in ad insights after the first match?** Same monitoring window. This is the ultimate confirmation that the value signal is live and reaching Meta's optimizer.
- **Will CpFN move back toward the $144 "humming" baseline over the next 7 days?** The long-horizon test of whether VALUE optimization with proper signal + current ad creative + current audience recovers performance. Owner: Nate, weekly review.
- **Will GDN-789 ship this week?** Depends on Jackson/Marcus merge bandwidth. Not blocking tonight's fix, but a compound improvement if it lands on top.
- **Does Meta eventually expose multi-event optimization for OUTCOME_SALES + VALUE?** Watch Meta's product announcements. Not a near-term dependency.

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| Meta Ad Account | `act_1582817295627677` |
| Meta Pixel | `1625233994894344` (WebApp Actions) |
| Active Campaign | `120245455503210548` (Farm: Testing - Q226, OUTCOME_SALES) |
| Active Ad Set | `120245455503860548` (Farm: All Value Props Q226, $200/day, VALUE) |
| FirstNote (Valued) v2 | `4363987073922754` @ $100 (10000 cents) |
| SignUpConfirm (Valued) v2 | `1673233627279622` @ $5 (500 cents) |
| CalendarScheduled (Valued) v2 | `829867779586914` @ $15 (1500 cents) |
| _archived_ FirstNote (Valued) v1 | `3914250848710226` (whitespace + cents bugs) |
| _archived_ SignUpConfirm (Valued) v1 | `1960979881475090` (whitespace + cents bugs) |
| _archived_ CalendarScheduled (Valued) v1 | `1270312578633364` (whitespace + cents bugs) |
| Ad set's current pixel_rule (compact form) | `{"and":[{"event_type":{"eq":"FirstNote"}}]}` |
| v1 whitespace rule (whatever Meta silently stored) | Semantically `{"and": [{"event_type": {"eq": "FirstNote<whitespace>"}}]}` |
| Fix script | `scripts/fix-custom-conversions.py` |
| Manifest | `data/custom-conversions/valued-conversions-2026-04-22.json` |
| CHANGELOG entry | `ads_engine/CHANGELOG.md` 2026-04-22 entry |
| Meta error: duplicate rule | `error_subcode 1760002` |
| Meta error: invalid promoted_object combo | `error_subcode 1885014` |
| Attribution window | 7-day click, 1-day view |
| Learning stage post-unpause | LEARNING, conversions=0 |
| CpFN baseline (humming era Apr 3-9) | $144 |
| CpFN current (Apr 17-22) | $408 |
| Pixel FN fires Apr 15-21 | 37 |
| Meta-attributed FN Apr 15-21 | 5 (13.5% attribution) |

---

## Sources

[^1]: Meta Ads Insights API pull, 2026-04-22, account `act_1582817295627677`, `time_range=2026-03-20..2026-04-22`, `level=account`, `time_increment=1`. Daily spend, impressions, actions, conversions, conversion_values.

[^2]: [docs/jot-briefs/meta-ads-snapshot-2026-04-21.md](meta-ads-snapshot-2026-04-21.md). Account state snapshot documenting the Apr 16 consolidation, the 7-day no-touch window, and the Advantage+ audience configuration.

[^3]: [docs/jot-briefs/meta-custom-conversions-values-2026-04-20.md](meta-custom-conversions-values-2026-04-20.md). The original (now superseded) brief that documented the Apr 20 CC creation as the value-signal fix. The CCs it describes are the broken v1 batch renamed `_archived_*` on 2026-04-22.

[^4]: Meta Pixel Graph API pull, 2026-04-22, pixel `1625233994894344`, `/stats?aggregation=event&start_time=2026-04-15&end_time=2026-04-22`. Pixel-side event fire counts: 37 FirstNote, 50 SignUpConfirm, 14 CalendarScheduled, plus noise (userID 1.1M, UserID 585K).

[^5]: Meta Custom Conversion Graph API readbacks, 2026-04-22. API returned `default_conversion_value: 100` for v1 CCs that rendered as `$1.00` in UI. Same integer returned for v2 FirstNote (value=100) that also rendered $1.00. After PATCHing to `default_conversion_value: 10000`, UI rendered `$100.00`. Confirms cents unit.

[^6]: AdSet `promoted_object` field probing, 2026-04-22. GET requests with speculative multi-event field names all returned `(#100) Tried accessing nonexisting field`. GUI "Show more settings" revealed only attribution window, conversion count, delivery type.

[^7]: `ads_engine/CHANGELOG.md` 2026-04-22 entry. Full technical record of tonight's rebuild with rollback instructions, IDs, and diagnostic evidence.
