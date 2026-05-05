---
title: "Meta Custom Conversions Assign Dollar Values Natively — No Engineering Required"
date: 2026-04-20
author: Nate + Claude
memory_target: Long-term memory
scope: Meta VALUE optimization can be unblocked entirely via the /customconversions API without any pixel-side changes
confidence: high
supersedes: meta-match-quality-fix-2026-04-16.md (the "engineering must ship value params" half is no longer true; match-quality half still stands)
sources:
  - api: Meta Marketing API /customconversions endpoint (graph.facebook.com/v21.0)
  - manifest: data/custom-conversions/valued-conversions-2026-04-20.json
  - brief: docs/jot-briefs/meta-pixel-gtm-architecture-correction-2026-04-20.md
  - brief: docs/jot-briefs/meta-match-quality-fix-2026-04-16.md
  - conversation: Nate + Claude, 2026-04-20 — "i'm just shocked that meta can't assign values on its side"
---

# Meta Custom Conversions Assign Dollar Values Natively — No Engineering Required

**Date:** 2026-04-20
**Memory target:** Long-term memory
**Scope:** Meta platform capability that makes VALUE optimization possible without any pixel code changes
**Status:** Canonical as of 2026-04-20. Three Custom Conversions live and bound to Farm: Testing - Q226 ad set.

---

## TL;DR

Meta Custom Conversions accept a `default_conversion_value` and a `currency` at creation time. When a pixel event matches the conversion's rule, Meta attributes the default value to that event — even if the raw pixel fire carried no value param. This makes VALUE optimization workable without any engineering change to the app's pixel events. Three Custom Conversions were created today via API (FirstNote $100, SignUpConfirm $5, CalendarScheduled $15) and the Farm: Testing - Q226 ad set's `promoted_object.pixel_rule` was switched to point at the FirstNote rule. Meta now has dollar signals to optimize on. GDN-789 is still needed for match-quality (EMQ 4→6) but is no longer the blocker on value signal — those are two separate problems that were previously conflated.

---

## What Jot Should Commit to Memory

1. **Meta Custom Conversions support `default_conversion_value` at creation time.** When a matching pixel event fires, Meta counts it at that value automatically. No pixel-side code changes required. This is a native platform capability, not a workaround.

2. **VALUE optimization and Event Match Quality (EMQ) are two independent problems.** Custom Conversions solve the value-signal problem. They do nothing for match quality. Advanced matching (hashed email, `_fbc`, `_fbp`, IP, User-Agent via dataLayer → GTM → pixel, or via CAPI) is still required for EMQ. Never again conflate them.

3. **Before recommending engineering work for any Meta-related gap, exhaust native Meta capabilities first.** Custom Conversions, value rules, audience automation, Advantage+ placements, conversion-location settings — Meta has many server-side levers. Ask "can Meta do this" before asking "can engineering do this." Matches the global CLAUDE.md rule: engineering asks are last resort.

4. **The promoted_object API for custom-conversion-based optimization uses `pixel_rule` (JSON rule string), NOT `custom_conversion_id`.** Meta rejects every combination of `custom_conversion_id` + `pixel_id` + `custom_event_type`. The working combo is: `{pixel_id, pixel_rule (JSON string matching the Custom Conversion's rule), custom_event_type}`. The rule string goes in verbatim — not the Custom Conversion's ID.

5. **Custom Conversion creation requires `event_source_id` (not `pixel_id`) in the API call.** Meta renamed the parameter. Also requires a valid `rule` at creation time — an empty rule returns "A conversion rule is required at creation time."

6. **The custom_event_type field on Custom Conversions should be `OTHER` for non-standard events** (like our FirstNote, SignUpConfirm, CalendarScheduled). PURCHASE or LEAD would misclassify these. OTHER preserves our custom taxonomy while still enabling value tracking.

7. **Custom Conversions need at least one matching event to fire before they become selectable for optimization in the Ads Manager UI.** Via API, they can be bound to an ad set's `promoted_object` immediately — but UI selection waits for verification via a real event fire.

---

## Why (Reasoning + Evidence)

### The assumption that was wrong

The Apr 16 match-quality PRD treated two problems as one: "pixel events don't carry `{value, currency}`" and "advanced matching parameters are missing." Both were framed as engineering asks. But only the second is actually an engineering problem.

Meta's own platform answer for assigning values to events is Custom Conversions. From the API:

```
POST /act_{AD_ACCOUNT}/customconversions
  event_source_id: {PIXEL_ID}
  name: "FirstNote (Valued)"
  default_conversion_value: 100.00
  currency: "USD"
  custom_event_type: "OTHER"
  rule: {"and": [{"event_type": {"eq": "FirstNote"}}]}
```

Every time Meta sees a `FirstNote` pixel event, the matching Custom Conversion fires at $100. No app change, no dataLayer change, no GTM change.

### What got built today

Three Custom Conversions, all via API, all pointing at the WebApp Actions pixel:

| Custom Conversion | ID | Rule | Default Value |
|---|---|---|---|
| FirstNote (Valued) | `3914250848710226` | `{"and": [{"event_type": {"eq": "FirstNote"}}]}` | $100.00 USD |
| SignUpConfirm (Valued) | `1960979881475090` | `{"and": [{"event_type": {"eq": "SignUpConfirm"}}]}` | $5.00 USD |
| CalendarScheduled (Valued) | `1270312578633364` | `{"and": [{"event_type": {"eq": "CalendarScheduled"}}]}` | $15.00 USD |

The Farm: Testing - Q226 ad set (`120245455503860548`) `promoted_object` now reads:

```json
{
  "pixel_id": "1625233994894344",
  "custom_event_type": "OTHER",
  "pixel_rule": "{\"and\": [{\"event_type\": {\"eq\": \"FirstNote\"}}]}"
}
```

Meta's VALUE optimization algorithm now has:
- $100 per FirstNote event (6 fired in last 7 days)
- $5 per SignUpConfirm event (11 fired)
- $15 per CalendarScheduled event (bookings — real production volume TBD)

### What's still broken — and what isn't

**Still broken:** Event Match Quality at 4.0/10. Meta can't reliably attribute events to ad viewers. This is the GDN-789 work (dataLayer enrichment + GTM Meta tag config).

**No longer broken:** Value signal. Meta sees dollars now.

The previous framing — "engineering must ship values OR VALUE optimization is dead" — was wrong. The accurate framing is: "engineering must ship advanced matching to unlock the 18-25% CPA reduction from EMQ 4→6." That's still a meaningful ask but smaller in scope and no longer blocking the primary ads workstream.

### The meta-lesson

In one day (2026-04-20) we made two architectural corrections to the same original PRD:

1. **Morning:** Discovered the app uses GTM, not direct `fbq()` calls. "5 lines of JS" was wrong framing.
2. **Afternoon:** Discovered Meta assigns values natively via Custom Conversions. "Engineering must ship value params" was the wrong ask entirely.

Both corrections followed the same pattern: the original brief assumed engineering was required, but the platform offered a native solution we hadn't considered. Future briefs must interrogate platform capabilities before routing to engineering.

This reinforces the global rule added to CLAUDE.md today: "Engineering asks are last resort. Exhaust every API, script, config, and platform-native tool before opening a ticket."

---

## How to Apply

| Situation | Response |
|---|---|
| Someone asks "how do we add values to Meta events without engineering?" | Custom Conversions with `default_conversion_value`. Create via `POST /act_{id}/customconversions`. Works immediately. |
| Ad set needs to optimize on a Custom Conversion | Set `promoted_object.pixel_rule` to the CC's rule string (not its ID). Include `pixel_id` and `custom_event_type`. |
| API returns "A conversion rule is required at creation time" | The `rule` field needs a valid JSON rule. Template: `{"and": [{"event_type": {"eq": "{EVENT_NAME}"}}]}`. |
| API returns "The parameter event_source_id is required" | Meta renamed `pixel_id` to `event_source_id` on /customconversions. Use the new name. |
| Someone wants to know why VALUE optimization is underperforming | Two distinct problems to check: (1) value signal — use Custom Conversions, (2) match quality — GDN-789 / advanced matching. Don't conflate. |
| Someone proposes engineering work for an ads problem | First exhaust: Custom Conversions, value rules, Advantage+, placement settings, audience automation. Engineering is the last resort. |
| Someone quotes the original Apr 16 match-quality PRD as a source of truth | Warn: two architectural corrections have superseded pieces of it. See meta-pixel-gtm-architecture-correction-2026-04-20.md and meta-custom-conversions-values-2026-04-20.md for current truth. |

---

## What This Brief Does NOT Cover

- How to migrate to value rules (per-audience bid adjustments). Related but distinct from Custom Conversions.
- The Advantage+ placements vs. manual placements decision (separate workstream).
- GDN-789 implementation details — that lives in the linear issue.
- Whether Custom Conversions affect reporting differently than raw pixel events in Ads Manager (they do — reports show both the raw event count and the Custom Conversion count; the CC is what optimization uses).

---

## Open Questions

- **When will `first_fired_time` populate on these three Custom Conversions?** Until then they exist but haven't "verified" via a matching event. FirstNote has 6 attributed events in the past 7 days so it should trigger fast. SignUpConfirm (11 events) also fast. CalendarScheduled at 0 attributed events from ads is slower — but the page fires it on every visit so it may already have validated via the test we ran earlier today.
- **Do we want to create additional Custom Conversions for `LandingPageView` or other milestone events?** Nate rejected LPVs as a value signal ("too many AI tire-kickers") — but worth checking if sub-funnel events would help learning without polluting value optimization.

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| Meta Ad Account | `act_1582817295627677` |
| Meta Pixel (canonical) | `1625233994894344` (WebApp Actions dataset) |
| Access Token env var | `META_ADS_ACCESS_TOKEN` |
| Custom Conversion: FirstNote (Valued) | `3914250848710226` |
| Custom Conversion: SignUpConfirm (Valued) | `1960979881475090` |
| Custom Conversion: CalendarScheduled (Valued) | `1270312578633364` |
| Active Ad Set | `120245455503860548` (Farm: All Value Props Q226) |
| Active Campaign | `120245455503210548` (Farm: Testing - Q226) |
| API: create CC endpoint | `POST /v21.0/act_{account_id}/customconversions` |
| API: required create param (new name) | `event_source_id` (was `pixel_id`) |
| API: ad set promoted_object field for CC | `pixel_rule` (JSON rule string, NOT the CC's ID) |
| API version | v21.0 |
| Manifest file | `data/custom-conversions/valued-conversions-2026-04-20.json` |
| Related brief (GTM correction) | `docs/jot-briefs/meta-pixel-gtm-architecture-correction-2026-04-20.md` |
| Related brief (original PRD, partially superseded) | `docs/jot-briefs/meta-match-quality-fix-2026-04-16.md` |

---

## Sources

[^1]: Meta Marketing API: [Conversions API documentation](https://developers.facebook.com/docs/marketing-api/conversions-api/), cross-referenced with direct API probing on 2026-04-20 against `act_1582817295627677`.
[^2]: Meta Custom Conversion `default_conversion_value` field confirmed in API response from `GET /3914250848710226?fields=default_conversion_value,rule,data_sources,pixel` on 2026-04-20.
[^3]: Nate's direct prompt on 2026-04-20: "i'm just shocked that meta can't assign values on its side" — the question that surfaced the wrong assumption.
[^4]: Manifest of created Custom Conversions at `data/custom-conversions/valued-conversions-2026-04-20.json`.
