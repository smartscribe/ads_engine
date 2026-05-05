---
title: NPPES → Meta Custom Audience Build Methodology
date: 2026-04-21
author: Nate + Claude
memory_target: Long-term memory
scope: How to build a high-fidelity Meta Custom Audience from NPPES — API quirks, pagination workarounds, upload pattern
confidence: high
supersedes: none
sources:
  - file: scripts/build-nppes-audience.py
  - file: scripts/backfill-nppes-capped.py
  - file: scripts/retry-nppes-failed.py
  - file: scripts/attach-audiences-to-adsets.py
  - file: data/audiences/nppes-upload-2026-04-21.json
  - file: data/audiences/nppes-backfill-upload-2026-04-21.json
  - file: data/audiences/nppes-retry-upload-2026-04-21.json
  - log: /tmp/nppes-run.log (2026-04-21 pull)
  - log: /tmp/nppes-backfill.log (2026-04-21 backfill)
  - api: https://npiregistry.cms.hhs.gov/api/ (NPPES v2.1)
  - api: https://graph.facebook.com/v21.0 (Meta Graph API)
---

# NPPES → Meta Custom Audience Build Methodology

**Date:** 2026-04-21
**Memory target:** Long-term memory
**Scope:** How to build a high-fidelity Meta Custom Audience from NPPES — API quirks, pagination workarounds, upload pattern
**Status:** canonical as of 2026-04-21

---

## TL;DR

The public NPPES provider registry is the strongest deterministic audience source we have for BH clinicians, but its API has three non-obvious constraints that must be handled or the resulting audience will be silently truncated to a fraction of its true size. `taxonomy_description` is a substring match, not a prefix match. The `skip` parameter is hard-capped at 1000, so populous states lose everyone past that. `last_name` prefix matching requires a minimum of 2 characters plus a trailing `*`. The correct full-pull flow is: two non-overlapping substring queries (`Psychiatry` + `Psych/Mental`) state-by-state, then a 2-letter last-name-prefix backfill for every (query, state) pair that hit the skip cap, then a rate-limit retry pass. Result: 120,367 unique PMHNPs + psychiatrists in Meta audience `120245691436380548`, with a 1% lookalike `120245691499170548` attached to 6 active Farm+Scale ad sets.

---

## What Jot Should Commit to Memory

1. **NPPES `taxonomy_description` is substring-matched, not prefix-matched.** Example: the query `taxonomy_description=Psych` returns providers with `Psychiatry & Neurology, Psychiatry` AND providers with `Nurse Practitioner, Psych/Mental Health`, because "Psych" appears as a substring in both. Context: when reasoning about what a NPPES query will cover, do not assume it only matches descriptions that start with the query string.

2. **NPPES `skip` is hard-capped at 1000.** Requests with `skip >= 1000` either return empty, error, or silently return bogus data. Every query must be designed to return ≤1000 rows, or narrowed further. Context: when a per-state taxonomy pull exceeds 1000 raw rows, you WILL lose the overflow unless you slice by another parameter (last_name prefix is the cleanest).

3. **NPPES `last_name` prefix matching requires ≥2 characters + trailing `*`.** `last_name=A` returns 0. `last_name=A*` returns 0. `last_name=Aa*` works. `last_name=Smit*` works. Context: for last-name slicing, enumerate `aa*..zz*` (676 prefixes) per (query, state), not 26 single-letter prefixes.

4. **NPPES rate-limits heavy concurrent loads with HTTP 403.** With 8-worker ThreadPoolExecutor on 34K requests, ~3% failed with 403 near the tail of the run. Serial retry at 0.4s delay recovered all of them. Context: for bulk pulls, either cap concurrency at ~4 workers with ~0.3s per-call sleep, or accept that a serial retry pass is required to close the gap.

5. **For BH-clinician audiences specifically, use two substring queries in parallel:** `taxonomy_description=Psychiatry` (catches code 2084P0800X, `Psychiatry & Neurology, Psychiatry`) and `taxonomy_description=Psych/Mental` (catches code 363LP0808X, `Nurse Practitioner, Psych/Mental Health`). These cover the two NPI-1 taxonomies we care about without overlapping. Context: do not use a broader query like `Psych` alone — it pulls pharmacists, psychologists, and students, wasting the 1000-skip budget on providers we don't want.

6. **Meta Custom Audiences accept appends via `POST /{audience_id}/users`** with `schema: ["FN", "LN", "ST", "ZIP"]` and SHA256-hashed lowercase-stripped values. Meta dedupes on hash server-side, so re-uploading overlapping batches is safe. Context: the correct build pattern is "create audience once, append in multiple passes as you discover more records" — not "build one big list, one upload."

7. **Meta Lookalike creation requires `origin_audience_id` as a top-level parameter, not nested inside `lookalike_spec`.** Correct body: `{name, subtype: "LOOKALIKE", origin_audience_id: <id>, lookalike_spec: {type: "similarity", country: "US", ratio: 0.01}}`. If you nest origin_audience_id inside lookalike_spec, Meta returns `Invalid key in lookalike_spec: No custom_audience ID given for lookalike cluster` (error code 2654, subcode 1870077). Context: the Graph API docs are ambiguous on this; the working call pattern is in `scripts/pull-converters-for-lookalike.py` and `scripts/upload-chris-lists.py`, line 226-240 in each.

8. **The BH-clinician audience is canonical.** Custom audience `120245691436380548` ("NPPES PMHNPs + Psychiatrists") contains 120,367 providers as of 2026-04-21. The 1% US lookalike is `120245691499170548`. These are attached as includes on all 6 active Farm+Scale ad sets. Context: when asked "do we have a provider list for Meta," the answer is yes, and these are the IDs.

9. **Run order is strict: `build-nppes-audience.py` → `backfill-nppes-capped.py` → `retry-nppes-failed.py`.** Each script is idempotent and safe to re-run; each reads from the same `data/audiences/nppes-checkpoint.json` for dedup. Context: `build` creates the audience and gets the first ~54K; `backfill` gets the capped-state tail (~65K more); `retry` cleans up rate-limit 403s (~1K more).

---

## Why (Reasoning + Evidence)

### The first pull was silently undercounting by ~55%

On 2026-04-16 the first attempt to build this audience returned 0 raw NPPES records and died. The 2026-04-21 re-run with improved error handling pulled 54,136 providers — which Nate and I initially thought was the full universe. The backfill pass then discovered **65,253 more unique providers** that the original pull had missed, more than doubling the audience[^1]. Root cause: NPPES's 1000-row cap per (query, state) silently truncated every populous state. The backfill log parser found 51 (query, state) pairs that hit the cap out of 102 total — exactly half of the pulls were incomplete[^2].

This is a specific instance of a general pattern: a bulk API pull that "completes successfully" and "returns data" is not the same as a pull that got everything. NPPES doesn't tell you it truncated; the only signal is that `len(results) == 1000` and `skip` is at its max.

### Why the two-query split works

A single broad query like `taxonomy_description=Psych` catches both target taxonomy codes via substring matching, but it also catches psychologists (`103TC0700X`), pharmacists (`1835P1300X`), psychiatric hospitals (`283Q00000X`), and students — all of which we filter out client-side but which count against the 1000-cap budget. Empirically, one state (AL) returned 1,128 raw results with "Psych" where only ~609 were targets[^3]; with the narrow split, the same state's budget is spent entirely on relevant providers.

The two narrow queries are non-overlapping:
- `Psychiatry` matches: `Psychiatry & Neurology, Psychiatry` (target), `Psychiatry & Neurology, Neurology` (non-target, filtered out), and a few rare sub-specialties.
- `Psych/Mental` matches: `Nurse Practitioner, Psych/Mental Health` (target), `Clinical Nurse Specialist, Psych/Mental Health` (non-target), `Registered Nurse, Psych/Mental Health` (non-target).

No provider has both taxonomies, so the two result sets are disjoint even before filtering.

### Why 2-letter prefix slicing beats 1-letter

NPPES `last_name` requires a minimum length when wildcarded — confirmed empirically:

| Query | Returned rows |
|---|---|
| `last_name=A` | 0 |
| `last_name=A*` | 0 |
| `last_name=A%2A` (URL-encoded `A*`) | 0 |
| `last_name=Aa*` | 1 |
| `last_name=Ab*` | 3 |
| `last_name=Smit*` | 3 |

So the smallest usable unit is two characters plus `*`. With 676 2-letter combinations per (query, state), we cover every alphabetic surname. Rare combos like `xz*`, `qj*`, `zz*` return 0 quickly, so the fan-out is cheap despite the count. For 51 capped pairs × 676 prefixes = 34,476 requests, a ThreadPoolExecutor with 8 workers completes in ~10 minutes[^4].

### Why the rate-limit retry matters

The 8-worker fan-out triggered 930 403s near the tail — about 2.7% of all requests[^5]. These clustered in 14 (query, state) pairs, heaviest in `Psychiatry/LA` (224 fails), `Psychiatry/MO` (128), and `Psychiatry/OR` (114). Without the retry pass, these gaps would quietly leave surnames starting with letters late in the alphabet under-represented in the final audience. The serial retry at 0.4s per call recovered 978 additional unique providers — small in absolute terms but structurally important because the gap was geographically concentrated.

### Lookalike parameter gotcha

First attempt at creating the 1% lookalike used the ostensibly more-correct pattern of nesting `origin_audience_id` inside `lookalike_spec`:

```json
{
  "subtype": "LOOKALIKE",
  "lookalike_spec": {
    "origin_audience_id": "120245691436380548",
    "country": "US",
    "ratio": 0.01
  }
}
```

Meta returned HTTP 400 with `(#2654) Invalid lookalike_spec parameter: Invalid key in lookalike_spec: No custom_audience ID given for lookalike cluster`. The correct pattern is to pull `origin_audience_id` up to top level and add `type: "similarity"` to `lookalike_spec`:

```json
{
  "subtype": "LOOKALIKE",
  "origin_audience_id": "120245691436380548",
  "lookalike_spec": {
    "type": "similarity",
    "country": "US",
    "ratio": 0.01
  }
}
```

Returned HTTP 200 with `{"id": "120245691499170548"}`[^6].

---

## How to Apply

| Situation | Response |
|---|---|
| Someone asks "do we have a provider list uploaded to Meta" | Yes — audience `120245691436380548` (120,367 PMHNPs + psychiatrists) + 1% lookalike `120245691499170548`, attached to all active Farm+Scale ad sets. |
| Building a new NPPES-based audience (different specialty) | Use `scripts/build-nppes-audience.py` as template. Replace `TAXONOMY_QUERIES` and `TARGET_TAXONOMY_CODES`. Expect to need the backfill + retry scripts unchanged. |
| A NPPES pull "succeeds" but feels too small | Grep the log for `WARN: \w+ hit NPPES skip cap` — if any state hit the cap, run `backfill-nppes-capped.py`. |
| Need to add more records to an existing Meta audience | POST to `{audience_id}/users` with hashed FN+LN+ST+ZIP. Meta dedupes on hash; safe to re-upload. See `upload_to_meta` in `scripts/backfill-nppes-capped.py`. |
| Meta rejects a lookalike with error 2654 | Check that `origin_audience_id` is a top-level parameter, not inside `lookalike_spec`. |
| Asked to exclude existing customers from this audience | Already handled — `attach-audiences-to-adsets.py` attaches the Stripe Customers audience and the Converters audience as exclusions. |

---

## What This Brief Does NOT Cover

- How to update the 1% lookalike's source (Meta recomputes automatically as the source grows — no action needed).
- Best practices for combining NPPES with Chris's prospect lists — that's the attach script's job and is stable.
- Creative strategy for targeting this audience — separate workstream (see the patch-cycle skill and `/ads-analysis`).
- NPPES data freshness — the CMS updates NPPES weekly; our audience is a point-in-time snapshot from 2026-04-21. Nothing auto-refreshes.

---

## Open Questions

| Item | Owner | Target |
|---|---|---|
| Cadence for re-pulling NPPES (weekly? monthly?) | Nate | TBD after a month of delivery data |
| Should Chris Hume get read-only Meta ad account access to see this audience live? | Nate | 2026-04-21 (pending this conversation) |

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| NPPES Custom Audience | `120245691436380548` |
| NPPES 1% Lookalike (US) | `120245691499170548` |
| Meta ad account | `act_1582817295627677` |
| Meta Graph API version used | `v21.0` |
| Target NPI taxonomy: Psychiatry | `2084P0800X` |
| Target NPI taxonomy: PMHNP | `363LP0808X` |
| NPPES API base | `https://npiregistry.cms.hhs.gov/api/` |
| NPPES API version param | `version=2.1` |
| NPPES skip cap | `1000` |
| NPPES page limit | `200` |
| NPPES last_name min length | `2` chars + `*` |
| Meta upload schema | `["FN", "LN", "ST", "ZIP"]` (SHA256, lowercase, stripped) |
| Meta upload batch size | `10_000` hashes |
| Build script | `scripts/build-nppes-audience.py` |
| Backfill script | `scripts/backfill-nppes-capped.py` |
| Retry script | `scripts/retry-nppes-failed.py` |
| Attach script | `scripts/attach-audiences-to-adsets.py` |
| Attached ad sets (Farm+Scale) | AI Progress Concepts `120245455505970548`, UGC / Social Proof `120245455505420548`, EHR Integration `120245455505010548`, Time Savings `120245455504270548`, Farm: All Value Props Q226 `120245455503860548`, Scale: Top 5 by CpFN `120244893374990548` |

---

## Sources

[^1]: `data/audiences/nppes-upload-2026-04-21.json` — initial build, 54,136 records. `data/audiences/nppes-backfill-upload-2026-04-21.json` — backfill, 65,253 records. `data/audiences/nppes-retry-upload-2026-04-21.json` — retry, 978 records. All three summaries show `num_invalid_entries: 0` across every batch.
[^2]: `/tmp/nppes-run.log`, WARN lines parsed into 51 (query, state) pairs: `Psychiatry` hit the cap in 27 states, `Psych/Mental` hit it in 24 states.
[^3]: `/tmp/nppes-run.log`, first pull output: `AL: 1128 raw -> 609 target providers` on the original "Psych" query before the rewrite.
[^4]: `/tmp/nppes-backfill.log` timing, 34,476 tasks completed in one run with 8-worker ThreadPoolExecutor.
[^5]: `/tmp/nppes-backfill.log` — 930 `ERROR ... 403 Client Error: Forbidden` lines out of 34,476 tasks = 2.70%.
[^6]: Response captured in terminal output during lookalike creation; audience ID persisted to `data/audiences/nppes-upload-2026-04-21.json` under `lookalike_audience_id`.
