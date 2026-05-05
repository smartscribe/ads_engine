# Signup Funnel Report

Pull → compute → QC → render pipeline for the L6M top-of-funnel HTML deliverable at `data/performance/snapshots/trial-conversion-by-notes.html`.

Despite the fact that a specific FB Forms push is what kicked this off, the harness is **channel-agnostic** — it covers every signup in the last 180 days regardless of source. The paid-channel split in the rendered view is a breakdown dimension, not a data filter.

## Run it

```bash
# From ads_engine/ root. Full pipeline (hits Metabase, ~2-3s):
python3 -m engine.reports.funnel.run

# Render-only from cached raw data (instant, for iterating on the HTML):
python3 -m engine.reports.funnel.run --no-pull

# Just one stage:
python3 -m engine.reports.funnel.run --stage qc
```

`--stage` can be `pull`, `compute`, `qc`, or `render`. QC exits non-zero on failure so the pipeline aborts before overwriting a broken HTML.

## Structure

| File | Role |
|---|---|
| `config.py` | All tunable constants: ARPU, cohort window, paid channel list, paths, colors |
| `metabase.py` | Tiny native-SQL client against the analytics Supabase (db_id=2). Reads `METABASE_URL` / `METABASE_API_KEY` from `~/.claude/.env` |
| `pull.py` | Four Metabase queries → raw JSON in `data/performance/snapshots/funnel/raw/` |
| `compute.py` | Raw → `model.json`. Computes rolling rate, weekly totals, weekly-by-channel, biweekly discovery |
| `qc.py` | **Independent** re-derivation of every model number. Does not import `compute.py`. |
| `render.py` | `model.json` → HTML. Pure serialization, no math |
| `run.py` | Orchestrator |

## Source of truth chain

```
Metabase  →  raw/*.json  →  model.json  →  HTML
                 ↑              ↑
              pull.py         compute.py
                              QC re-derives from raw,
                              cross-checks against model
```

Every number in the HTML must trace back to `model.json`. The render script contains zero hardcoded numbers — it serializes model fields into JS literals consumed by Chart.js.

## QC philosophy (math-check-html alignment)

`qc.py` is the tiebreaker. It:

1. Re-derives the rolling rate from raw `per_note.json` using its own loop
2. Re-derives weekly signups and expected conversions by looping over the raw grid
3. Checks that `Σ channel expected == total expected` for every week (additivity)
4. Checks that `Σ weekly signups == cohort total` from the independent `cohort_counts` query
5. Checks that biweekly discovery channel sums match the raw pivot
6. Spot-checks rate sanity: rate[0] should be near the minimum

If any check fails, render is skipped and the old HTML stays intact.

## Editing the model

- **Change ARPU**: edit `ARPU_MONTHLY` in `config.py`
- **Change cohort window**: edit `COHORT_DAYS`
- **Change what counts as "paid"**: edit `PAID_CHANNELS` list in `config.py`
- **Add a new chart or metric**: add the raw query in `pull.py`, aggregate in `compute.py`, cross-check in `qc.py`, serialize in `render.py`. Four-file discipline keeps provenance clean.

## Gotchas

- Uses `requests` for the Metabase call because system Python 3.9 can't verify the certificate chain without it.
- `trial_end` heuristic: first `PAYMENT_STATUS_CHANGED` where `previous_status='trialing'`, else signup + 14d, capped at 30d. This may miss edge cases for users whose subscription events aren't in the analytics mirror — worth revisiting when we stand up Stripe-derived truth.
- Weeks newer than 14 days old are shaded as "incomplete" in the chart. The model includes them anyway so recent data is visible.
- The `manifest.json` in `raw/` records pull time and row counts — check it if charts look stale.

## Data freshness cadence

Re-run weekly, or whenever anyone asks for a current top-of-funnel number. The pull takes ~2s. Cached raw data is safe to ship around — it's a point-in-time snapshot.
