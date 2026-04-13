"""Transform raw Metabase pulls into the model that drives the HTML.

Every number in the final deliverable must originate here. No LLM-computed
values. QC script re-derives the same numbers independently.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from .config import (
    ARPU_MONTHLY, MODEL_PATH, NOTES_CAP, PAID_CHANNELS, RAW_DIR,
    REST_LABEL, ROLLING_WINDOW,
)


# ----------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------

def _load(name: str) -> List[Dict[str, Any]]:
    return json.loads((RAW_DIR / f"{name}.json").read_text())


def _int(x: Any) -> int:
    return int(x) if x is not None else 0


def _rate_from_rows(rows: List[Dict[str, Any]]) -> Dict[int, float]:
    """notes → raw rate (active/n). Rows from per_note.json."""
    out: Dict[int, float] = {}
    for r in rows:
        n = _int(r["n"])
        out[_int(r["notes"])] = _int(r["active"]) / n if n else 0.0
    return out


def rolling_rate(per_note_rows: List[Dict[str, Any]], window: int = ROLLING_WINDOW) -> Dict[int, float]:
    """5-point weighted-by-n rolling conversion rate, keyed by notes bucket."""
    rows = sorted(per_note_rows, key=lambda r: _int(r["notes"]))
    half = window // 2
    out: Dict[int, float] = {}
    for i, r in enumerate(rows):
        active = 0
        total = 0
        for k in range(max(0, i - half), min(len(rows), i + half + 1)):
            active += _int(rows[k]["active"])
            total += _int(rows[k]["n"])
        out[_int(r["notes"])] = (active / total) if total else 0.0
    return out


# ----------------------------------------------------------------------------
# Compute the full model
# ----------------------------------------------------------------------------

def compute_model() -> Dict[str, Any]:
    per_note = _load("per_note")
    grid = _load("weekly_paid_grid")
    biweekly = _load("biweekly_discovery")
    counts = _load("cohort_counts")

    # --- 1. Rate model ----------------------------------------------------
    raw_rate = _rate_from_rows(per_note)
    smooth = rolling_rate(per_note, window=ROLLING_WINDOW)
    per_note_out = [
        {
            "notes": _int(r["notes"]),
            "n": _int(r["n"]),
            "active": _int(r["active"]),
            "raw_pct": round(100 * raw_rate[_int(r["notes"])], 2),
            "smooth_pct": round(100 * smooth[_int(r["notes"])], 2),
        }
        for r in sorted(per_note, key=lambda x: _int(x["notes"]))
    ]
    matured_total = sum(_int(r["n"]) for r in per_note)
    matured_active = sum(_int(r["active"]) for r in per_note)
    overall_base = round(100 * matured_active / matured_total, 2) if matured_total else 0.0

    # --- 2. Weekly signups, forecast, and actual --------------------------
    # Group the grid by week, then also by (week, channel) for the paid split.
    # Forecast = Σ (n × rolling_rate). Actual = Σ (current active count).
    by_week: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"signups": 0, "expected": 0.0, "actual": 0, "matured": 0}
    )
    by_week_channel: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(
        lambda: defaultdict(lambda: {"signups": 0, "expected": 0.0, "actual": 0})
    )

    for row in grid:
        wk = str(row["cohort_week"])[:10]
        ch = row["channel"]
        notes = _int(row["notes"])
        n = _int(row["n"])
        active = _int(row["active"])
        matured_n = _int(row.get("matured_n", 0))
        rate = smooth.get(notes, 0.0)
        by_week[wk]["signups"] += n
        by_week[wk]["expected"] += n * rate
        by_week[wk]["actual"] += active
        by_week[wk]["matured"] += matured_n
        by_week_channel[wk][ch]["signups"] += n
        by_week_channel[wk][ch]["expected"] += n * rate
        by_week_channel[wk][ch]["actual"] += active

    # Channel order: paid channels first (in config order), then 'rest'.
    channel_order = PAID_CHANNELS + [REST_LABEL]

    # Build weekly and weekly_by_channel using full-precision sums, then
    # replace the weekly totals with the channel-sum so the two charts are
    # perfectly additive (no round-before-sum drift).
    weekly_by_channel = []
    for wk in sorted(by_week_channel):
        cells = by_week_channel[wk]
        record = {"week": wk, "channels": {}}
        for ch in channel_order:
            c = cells.get(ch, {"signups": 0, "expected": 0.0, "actual": 0})
            record["channels"][ch] = {
                "signups": c["signups"],
                "expected": round(c["expected"], 4),
                "actual": c["actual"],
                "mrr": round(c["expected"] * ARPU_MONTHLY, 2),
                "mrr_actual": round(c["actual"] * ARPU_MONTHLY, 2),
            }
        weekly_by_channel.append(record)

    # Derive weekly totals by summing the ALREADY-ROUNDED channel cells we
    # just stored. This guarantees that the number Chart.js adds across a
    # stacked bar is identical to the number it draws on the line above.
    weekly = []
    for wk_rec in weekly_by_channel:
        wk = wk_rec["week"]
        cells = wk_rec["channels"]
        sum_signups = sum(c["signups"] for c in cells.values())
        sum_expected = sum(c["expected"] for c in cells.values())
        sum_actual = sum(c["actual"] for c in cells.values())
        assert by_week[wk]["signups"] == sum_signups, (
            f"week {wk}: by_week signups {by_week[wk]['signups']} "
            f"!= by_week_channel sum {sum_signups}"
        )
        matured_n = by_week[wk]["matured"]
        weekly.append({
            "week": wk,
            "signups": sum_signups,
            "matured": matured_n,
            "expected": round(sum_expected, 4),
            "actual": sum_actual,
            "mrr": round(sum_expected * ARPU_MONTHLY, 2),
            "mrr_actual": round(sum_actual * ARPU_MONTHLY, 2),
            "error": round(sum_expected - sum_actual, 4),
        })

    # --- 3. Biweekly discovery attribution --------------------------------
    # Pivot: list of {biweek, channels:{name:count}} in stable channel order.
    by_biweek: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in biweekly:
        by_biweek[str(row["biweek"])[:10]][row["channel"]] += _int(row["n"])
    all_channels = sorted({row["channel"] for row in biweekly})
    biweekly_out = []
    for bw in sorted(by_biweek):
        biweekly_out.append({
            "biweek": bw,
            "channels": {ch: by_biweek[bw].get(ch, 0) for ch in all_channels},
        })

    # --- 4. Cohort totals (for QC cross-check) -----------------------------
    cohort_total = sum(_int(c["n"]) for c in counts)
    cohort_active = sum(_int(c["active"]) for c in counts)

    # --- 5. Stitch the model ---------------------------------------------
    # Mark partial weeks (< 14d matured) so the renderer can shade them.
    today = datetime.now().date().isoformat()
    incomplete_from = _iso_minus_days(today, 14)

    # Shared y-axis max so the two expected-conversions charts line up visually.
    # Needs to accommodate both the forecast line and the actual line, so take
    # the max of both peaks. Round up to nearest 5 past the peak.
    peak_expected = max((w["expected"] for w in weekly), default=1.0)
    peak_actual = max((w["actual"] for w in weekly), default=0)
    peak = max(peak_expected, peak_actual)
    y_axis_max = int(((peak * 1.12) // 5 + 1) * 5)

    # Margin-of-error summary, computed over mature weeks only (forecast is
    # only meaningful after trials have had time to resolve).
    mature_weeks = [w for w in weekly if w["week"] < incomplete_from and w["signups"] > 0]
    error_summary: Dict[str, Any] = {}
    if mature_weeks:
        errs = [w["expected"] - w["actual"] for w in mature_weeks]
        abs_errs = [abs(e) for e in errs]
        mae = sum(abs_errs) / len(abs_errs)
        mean_forecast = sum(w["expected"] for w in mature_weeks) / len(mature_weeks)
        mean_actual = sum(w["actual"] for w in mature_weeks) / len(mature_weeks)
        bias = sum(errs) / len(errs)
        mape_parts = [abs(e) / w["actual"] for e, w in zip(errs, mature_weeks) if w["actual"] > 0]
        mape = (sum(mape_parts) / len(mape_parts) * 100) if mape_parts else None
        error_summary = {
            "n_mature_weeks": len(mature_weeks),
            "mae_conversions": round(mae, 2),
            "mae_mrr": round(mae * ARPU_MONTHLY, 2),
            "mape_pct": round(mape, 1) if mape is not None else None,
            "bias_conversions": round(bias, 2),  # positive = model over-forecasts
            "bias_mrr": round(bias * ARPU_MONTHLY, 2),
            "mean_forecast": round(mean_forecast, 2),
            "mean_actual": round(mean_actual, 2),
        }

    model = {
        "meta": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "arpu_monthly": ARPU_MONTHLY,
            "notes_cap": NOTES_CAP,
            "rolling_window": ROLLING_WINDOW,
            "paid_channels": PAID_CHANNELS,
            "rest_label": REST_LABEL,
            "channel_order": channel_order,
            "discovery_channels_order": all_channels,
            "incomplete_from": incomplete_from,
            "y_axis_max": y_axis_max,
        },
        "per_note": per_note_out,
        "overall_base_pct": overall_base,
        "cohort": {
            "total": cohort_total,
            "active": cohort_active,
            "by_status": [{"status": c["status"], "n": _int(c["n"])} for c in counts],
        },
        "error_summary": error_summary,
        "weekly": weekly,
        "weekly_by_channel": weekly_by_channel,
        "biweekly_discovery": biweekly_out,
    }
    return model


def _iso_minus_days(iso: str, days: int) -> str:
    from datetime import date, timedelta
    d = date.fromisoformat(iso)
    return (d - timedelta(days=days)).isoformat()


def write_model(model: Dict[str, Any], path: Path = MODEL_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, indent=2, default=str))
    return path


if __name__ == "__main__":
    m = compute_model()
    out = write_model(m)
    print(f"model written → {out}")
    print(f"  weeks: {len(m['weekly'])}")
    print(f"  channels stacked: {m['meta']['channel_order']}")
    print(f"  biweeks: {len(m['biweekly_discovery'])}")
    print(f"  per-note rows: {len(m['per_note'])}")
    print(f"  cohort total: {m['cohort']['total']}  active: {m['cohort']['active']}  base: {m['overall_base_pct']}%")
