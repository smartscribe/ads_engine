"""Pull all raw facts for the FB funnel report from Metabase → JSON on disk.

Every query here is a fact extraction, not a transform. Compute logic lives in compute.py.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .config import (
    COHORT_DAYS, NOTES_CAP, PAID_CHANNELS, RAW_DIR,
    TRIAL_NOMINAL_DAYS, TRIAL_CAP_DAYS,
)
from .metabase import run_sql


# ----------------------------------------------------------------------------
# Shared SQL fragments (CTEs) — used by multiple queries
# ----------------------------------------------------------------------------

_COHORT_CTE = f"""
cohort AS (
  SELECT u.user_id AS auth0,
    u.create_datetime,
    u.user_data->>'payment_status' AS status,
    u.user_data->>'discovery_channel' AS channel
  FROM public.users u
  WHERE u.create_datetime >= NOW() - INTERVAL '{COHORT_DAYS} days'
    AND u.user_id IS NOT NULL
),
trial_end AS (
  SELECT e.user_id, MIN(e.event_timestamp) AS ts
  FROM public.events e JOIN cohort c ON c.auth0 = e.user_id
  WHERE e.event_type = 'PAYMENT_STATUS_CHANGED'
    AND e.event_data->>'previous_status' = 'trialing'
    AND e.event_timestamp > c.create_datetime
  GROUP BY 1
),
user_trial AS (
  SELECT c.auth0, c.status, c.channel, c.create_datetime,
    LEAST(
      COALESCE(te.ts, c.create_datetime + INTERVAL '{TRIAL_NOMINAL_DAYS} days'),
      c.create_datetime + INTERVAL '{TRIAL_CAP_DAYS} days'
    ) AS trial_end
  FROM cohort c LEFT JOIN trial_end te ON te.user_id = c.auth0
),
notes AS (
  SELECT e.user_id, COUNT(*) AS notes
  FROM public.events e JOIN user_trial ut ON ut.auth0 = e.user_id
  WHERE e.event_type = 'NOTE_CREATED'
    AND e.event_timestamp >= ut.create_datetime
    AND e.event_timestamp < ut.trial_end
  GROUP BY 1
),
joined AS (
  SELECT ut.auth0, ut.status, ut.channel, ut.create_datetime,
    date_trunc('week', ut.create_datetime)::date AS cohort_week,
    COALESCE(n.notes, 0) AS notes,
    (ut.status = 'active')::int AS converted,
    (ut.create_datetime < NOW() - INTERVAL '14 days') AS matured
  FROM user_trial ut LEFT JOIN notes n ON n.user_id = ut.auth0
)
"""


def _paid_bucket_expr(channel_col: str = "channel") -> str:
    """SQL expression that collapses channel into the paid-focus taxonomy."""
    paid_list = ",".join(f"'{c}'" for c in PAID_CHANNELS)
    return (
        f"CASE WHEN {channel_col} IN ({paid_list}) "
        f"THEN {channel_col} ELSE 'rest' END"
    )


# ----------------------------------------------------------------------------
# Individual queries — each produces one raw JSON file
# ----------------------------------------------------------------------------

def pull_per_note() -> List[Dict[str, Any]]:
    """Per-note conversion for matured cohort (rate model training data)."""
    sql = f"""
    WITH {_COHORT_CTE}
    SELECT LEAST(notes, {NOTES_CAP}) AS notes,
           COUNT(*) AS n,
           SUM(converted) AS active
    FROM joined WHERE matured
    GROUP BY 1 ORDER BY 1
    """
    return run_sql(sql)


def pull_weekly_paid_grid() -> List[Dict[str, Any]]:
    """cohort_week × paid-channel × notes → (signups, actual conversions).

    Carries both ``n`` (total users in the cell) and ``active`` (users who
    are currently ``payment_status='active'``) so compute can derive both
    the forecast (weighted by the rolling rate) and the true outcome.
    """
    sql = f"""
    WITH {_COHORT_CTE}
    SELECT cohort_week::text AS cohort_week,
           {_paid_bucket_expr("COALESCE(channel, 'null')")} AS channel,
           LEAST(notes, {NOTES_CAP}) AS notes,
           COUNT(*) AS n,
           SUM(converted) AS active,
           SUM(matured::int) AS matured_n
    FROM joined
    GROUP BY cohort_week, channel, LEAST(notes, {NOTES_CAP})
    ORDER BY cohort_week, channel, notes
    """
    return run_sql(sql)


def pull_biweekly_discovery() -> List[Dict[str, Any]]:
    """biweek × discovery_channel → first-note trialer count (all 11 channels including null)."""
    sql = f"""
    WITH {_COHORT_CTE},
    with_note AS (
      SELECT DISTINCT auth0 FROM joined WHERE notes >= 1
    ),
    bucketed AS (
      SELECT (
        date_trunc('week', j.create_datetime)
        - (EXTRACT(week FROM j.create_datetime)::int %% 2) * INTERVAL '1 week'
      )::date AS biweek,
      COALESCE(j.channel, 'null') AS channel
      FROM joined j JOIN with_note w ON w.auth0 = j.auth0
    )
    SELECT biweek::text AS biweek, channel, COUNT(*) AS n
    FROM bucketed GROUP BY biweek, channel ORDER BY biweek, channel
    """
    # Note: %% escapes % for any SQL clients that treat % as a param marker.
    # Metabase's /api/dataset does not, but keeping the escape is harmless.
    sql = sql.replace("%%", "%")
    return run_sql(sql)


def pull_cohort_counts() -> List[Dict[str, Any]]:
    """Sanity totals: total L6M users, by status. Used by QC."""
    sql = f"""
    WITH {_COHORT_CTE}
    SELECT status, COUNT(*) AS n, SUM(converted) AS active
    FROM joined GROUP BY status
    ORDER BY 2 DESC
    """
    return run_sql(sql)


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------

_QUERIES = {
    "per_note": pull_per_note,
    "weekly_paid_grid": pull_weekly_paid_grid,
    "biweekly_discovery": pull_biweekly_discovery,
    "cohort_counts": pull_cohort_counts,
}


def pull_all(out_dir: Path = RAW_DIR) -> Dict[str, Path]:
    """Run every query and write results to out_dir/<name>.json. Returns map of name → path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "cohort_days": COHORT_DAYS,
        "notes_cap": NOTES_CAP,
        "paid_channels": PAID_CHANNELS,
        "files": {},
    }
    paths: Dict[str, Path] = {}
    for name, fn in _QUERIES.items():
        print(f"  pulling {name}...")
        rows = fn()
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(rows, default=str, indent=2))
        manifest["files"][name] = {"path": str(path.relative_to(out_dir.parent)), "rows": len(rows)}
        paths[name] = path
        print(f"    → {len(rows)} rows")

    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    paths["manifest"] = manifest_path
    return paths


if __name__ == "__main__":
    pull_all()
