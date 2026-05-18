# NFSO Attribution Decomposition

Campaign: **Nate figuring shit out** (`120245858870520548`)
Ad set: `120245858870530548`
Last updated: 2026-05-11

---

## Optimization Goal

The ad set is configured with `optimization_goal: VALUE` (not `CONVERSIONS`). Meta is
maximizing expected purchase value per impression, not event count. Because FirstNote
at $150 dominates, Meta's EAR estimate is effectively "probability this person completes
a first note," which is the right signal.

Confirmed 2026-05-11 via API:
```json
{
  "optimization_goal": "VALUE",
  "promoted_object": {
    "pixel_id": "1625233994894344",
    "custom_event_type": "OTHER",
    "pixel_rule": "{\"and\":[{\"event\":{\"eq\":\"Purchase\"}},{\"or\":[{\"URL\":{\"i_contains\":\"jotpsych\"}},{\"URL\":{\"i_contains\":\"smartscribe\"}}]}]}"
  }
}
```

---

## CAPI vs GTM Value Alignment

Browser (GTM) and server (CAPI) must send identical values per event, or deduplication
produces inconsistent totals and the decomposition math breaks.

| Event | GTM (canonical) | CAPI before 2026-05-11 | CAPI after fix |
|-------|----------------|------------------------|----------------|
| FirstNote | $150 | $100 | $150 |
| SignUpConfirm | $25 | $5 | $25 |
| CalendarScheduled | $5 | $15 | $5 |

All three were wrong. Fixed in `engine/capi/sender.py` `EVENT_VALUES` on 2026-05-11.

Meta dedup behavior: when both browser and CAPI fire the same event_id, Meta deduplicates
and uses the browser value. So mismatched CAPI values only affected events where the browser
pixel missed (e.g., ad blocker, app-side signups) — but those events would have been
sending wrong value signals to the VALUE optimizer. Fixed.

---

## The Bundle Problem

The canonical conversion event `[CANONICAL] Purchase: FirstNote+SignUp+Calendar`
(`1604667127308749`) aggregates three sub-events into a single "Purchase" signal.
Ads Manager shows one Results number and one value total — no sub-breakdown by default.

Per-event values (as of Purchase rebuild 2026-05-05):

| Event | Value | GTM Tag |
|-------|-------|---------|
| FirstNote | $150 | Tag 67, trigger `generatedFirstNote` |
| SignUpConfirm | $25 | Tag 68, trigger `signupConfirm` |
| CalendarScheduled | $5 | Tag 69, page view `/scheduled-confirmed` |

---

## The Decomposition Method

### Step 1: Read CalendarScheduled count from the archived CC

`_archived_CalendarScheduled (Valued) v3` (`26939511482340303`) still fires because
`site/scheduled-confirmed.html` calls `fbq('trackCustom', 'CalendarScheduled')` directly,
independent of GTM. This gives an isolated count of Z.

Pull it from the `actions` field in Insights:

```
offsite_conversion.custom.26939511482340303 = Z (CalendarScheduled count)
```

### Step 2: Isolate FirstNote + SignUpConfirm

```
X + Y = total_purchases - Z
```

### Step 3: Solve the system

```
400 = 150X + 25Y      (total value minus cal portion)
X + Y = total - Z     (remaining event count)
```

Substituting Y = (total - Z) - X:

```
value - (5 * Z) = 150X + 25((total - Z) - X)
value - 5Z = 125X + 25(total - Z)
X = (value - 5Z - 25(total - Z)) / 125
Y = (total - Z) - X
```

### Example (2026-05-06, 9 purchases, $415)

```
Z = 3 (from archived CalendarScheduled v3)
Total value from canonical = $415
Cal value = 3 × $5 = $15
Remaining value = $415 - $15 = $400
Remaining count = 9 - 3 = 6

400 = 150X + 25Y
X + Y = 6

→ X = 2 FirstNotes ($300)
→ Y = 4 SignUpConfirms ($100)
```

Check: $300 + $100 + $15 = $415. Clean.

---

## What to Pull from the API

```python
r = requests.get(
    f"https://graph.facebook.com/v21.0/{campaign_id}/insights",
    params={
        "fields": "spend,actions,conversions,action_values",
        "time_range": json.dumps({"since": "...", "until": "..."}),
        "level": "campaign",
        "access_token": token
    }
)
```

Key fields to read:

| Field | What it gives you |
|-------|------------------|
| `actions[offsite_conversion.fb_pixel_purchase]` | Total purchase count |
| `action_values[offsite_conversion.custom.1604667127308749]` | Total canonical value |
| `actions[offsite_conversion.custom.26939511482340303]` | Z (CalendarScheduled count) |

---

## Do Not Remove These

**`_archived_CalendarScheduled (Valued) v3` (`26939511482340303`):** The probe that
makes decomposition possible. Renaming or disabling it kills the Z signal.

**`site/scheduled-confirmed.html` direct fbq call (line 111):** The source that keeps
the probe alive. Do not remove this line. It fires `fbq('trackCustom', 'CalendarScheduled')`
independently of GTM, which is why the archived CC continues to count even after the
GTM-based CalendarScheduled tag was superseded.

---

## Canonical Identifiers

| Thing | Value |
|-------|-------|
| Campaign | `120245858870520548` |
| Ad set | `120245858870530548` |
| Canonical Purchase CC | `1604667127308749` |
| CalendarScheduled probe CC | `26939511482340303` |
| Meta Pixel | `1625233994894344` |
| GTM Container | `GTM-KL9RPN9V` |
