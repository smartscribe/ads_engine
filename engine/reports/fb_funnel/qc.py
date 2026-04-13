"""Independent QC — re-derives every model number from raw JSON without
importing compute.py. If compute and QC disagree, the model is wrong.

Exits non-zero if any check fails so the pipeline aborts before rendering.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .config import (
    ARPU_MONTHLY, MODEL_PATH, NOTES_CAP, PAID_CHANNELS, RAW_DIR,
    REST_LABEL, ROLLING_WINDOW,
)


TOLERANCE_PCT = 0.1       # percentage points tolerance for rate checks
TOLERANCE_DOLLARS = 1.0   # dollar rounding tolerance
TOLERANCE_COUNT = 0       # integer counts must match exactly


# ---------------------------------------------------------------------------
# Load raw + model independently
# ---------------------------------------------------------------------------

def _load_raw(name: str) -> List[Dict[str, Any]]:
    return json.loads((RAW_DIR / f"{name}.json").read_text())


def _load_model() -> Dict[str, Any]:
    return json.loads(Path(MODEL_PATH).read_text())


def _int(x: Any) -> int:
    return int(x) if x is not None else 0


# ---------------------------------------------------------------------------
# Independent re-derivations (deliberately not importing compute.py)
# ---------------------------------------------------------------------------

def rederive_rolling_rate(per_note_raw: List[Dict[str, Any]]) -> Dict[int, float]:
    """Re-derive the 5-point weighted rolling rate from scratch."""
    rows = sorted(per_note_raw, key=lambda r: _int(r["notes"]))
    half = ROLLING_WINDOW // 2
    out: Dict[int, float] = {}
    for i in range(len(rows)):
        lo = max(0, i - half)
        hi = min(len(rows), i + half + 1)
        a = sum(_int(rows[k]["active"]) for k in range(lo, hi))
        n = sum(_int(rows[k]["n"]) for k in range(lo, hi))
        out[_int(rows[i]["notes"])] = (a / n) if n else 0.0
    return out


def rederive_weekly(grid_raw: List[Dict[str, Any]], rate: Dict[int, float]) -> Dict[str, Dict[str, float]]:
    agg: Dict[str, Dict[str, float]] = {}
    for row in grid_raw:
        wk = str(row["cohort_week"])[:10]
        notes = _int(row["notes"])
        n = _int(row["n"])
        rec = agg.setdefault(wk, {"signups": 0, "expected": 0.0})
        rec["signups"] += n
        rec["expected"] += n * rate.get(notes, 0.0)
    return agg


def rederive_weekly_by_channel(
    grid_raw: List[Dict[str, Any]], rate: Dict[int, float]
) -> Dict[str, Dict[str, Dict[str, float]]]:
    agg: Dict[str, Dict[str, Dict[str, float]]] = {}
    for row in grid_raw:
        wk = str(row["cohort_week"])[:10]
        ch = row["channel"]
        notes = _int(row["notes"])
        n = _int(row["n"])
        week = agg.setdefault(wk, {})
        cell = week.setdefault(ch, {"signups": 0, "expected": 0.0})
        cell["signups"] += n
        cell["expected"] += n * rate.get(notes, 0.0)
    return agg


def rederive_biweekly(biweekly_raw: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    agg: Dict[str, Dict[str, int]] = {}
    for row in biweekly_raw:
        bw = str(row["biweek"])[:10]
        ch = row["channel"]
        agg.setdefault(bw, {}).setdefault(ch, 0)
        agg[bw][ch] += _int(row["n"])
    return agg


# ---------------------------------------------------------------------------
# Check framework
# ---------------------------------------------------------------------------

class Checks:
    def __init__(self) -> None:
        self.results: List[Tuple[str, bool, str]] = []

    def ok(self, name: str, cond: bool, detail: str = "") -> None:
        self.results.append((name, bool(cond), detail))

    def eq_int(self, name: str, a: int, b: int) -> None:
        self.ok(name, a == b, f"{a} == {b}" if a == b else f"{a} != {b}")

    def eq_float(self, name: str, a: float, b: float, tol: float) -> None:
        diff = abs(a - b)
        self.ok(name, diff <= tol, f"{a:.4f} vs {b:.4f}  Δ={diff:.4f}  tol={tol}")

    def all_pass(self) -> bool:
        return all(r[1] for r in self.results)

    def report(self) -> str:
        lines = []
        passed = sum(1 for r in self.results if r[1])
        total = len(self.results)
        for name, ok, detail in self.results:
            mark = "✓" if ok else "✗"
            lines.append(f"  {mark}  {name}  ({detail})")
        lines.append("")
        lines.append(f"QC: {passed}/{total} checks passed")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Actual checks
# ---------------------------------------------------------------------------

def run_checks() -> Checks:
    c = Checks()

    per_note_raw = _load_raw("per_note")
    grid_raw = _load_raw("weekly_paid_grid")
    biweekly_raw = _load_raw("biweekly_discovery")
    cohort_raw = _load_raw("cohort_counts")
    model = _load_model()

    # ---- 1. Rolling rate matches ---------------------------------------
    rate = rederive_rolling_rate(per_note_raw)
    for row in model["per_note"]:
        notes = row["notes"]
        c.eq_float(
            f"rolling_rate[{notes}]",
            100 * rate[notes],
            row["smooth_pct"],
            TOLERANCE_PCT,
        )

    # ---- 2. Overall base rate vs raw per_note sum ----------------------
    tot_n = sum(_int(r["n"]) for r in per_note_raw)
    tot_a = sum(_int(r["active"]) for r in per_note_raw)
    base_expected = round(100 * tot_a / tot_n, 2) if tot_n else 0.0
    c.eq_float("overall_base_pct", model["overall_base_pct"], base_expected, 0.01)

    # ---- 3. Weekly signups + expected match re-derivation ---------------
    qc_weekly = rederive_weekly(grid_raw, rate)
    by_wk_model = {w["week"]: w for w in model["weekly"]}
    c.eq_int("weekly count", len(model["weekly"]), len(qc_weekly))
    for wk, rec in qc_weekly.items():
        m = by_wk_model.get(wk)
        c.ok(f"week {wk} present in model", m is not None)
        if not m:
            continue
        c.eq_int(f"week {wk} signups", m["signups"], rec["signups"])
        c.eq_float(f"week {wk} expected", m["expected"], rec["expected"], 0.01)
        c.eq_float(f"week {wk} mrr", m["mrr"], rec["expected"] * ARPU_MONTHLY, TOLERANCE_DOLLARS)

    # ---- 4. Channel sums equal weekly totals (strict additivity) --------
    # With full-precision cells and round-at-the-end, these should be exact
    # to the 4-decimal precision we store. Anything looser means the two
    # charts can drift visually.
    for wk_rec in model["weekly_by_channel"]:
        wk = wk_rec["week"]
        channels = wk_rec["channels"]
        ch_signups = sum(v["signups"] for v in channels.values())
        ch_expected = sum(v["expected"] for v in channels.values())
        total = by_wk_model.get(wk)
        if total:
            c.eq_int(f"week {wk} Σchannel signups == total", ch_signups, total["signups"])
            c.eq_float(
                f"week {wk} Σchannel expected == total (strict)",
                round(ch_expected, 4), round(total["expected"], 4), 0.0001,
            )

    # ---- 5. Channel order includes only expected labels ----------------
    expected_channels = set(PAID_CHANNELS + [REST_LABEL])
    for wk_rec in model["weekly_by_channel"]:
        c.ok(
            f"week {wk_rec['week']} channel labels",
            set(wk_rec["channels"].keys()) == expected_channels,
            f"{sorted(wk_rec['channels'].keys())}",
        )

    # ---- 6. Biweekly discovery per-bucket sums ------------------------
    qc_bw = rederive_biweekly(biweekly_raw)
    model_bw = {b["biweek"]: b for b in model["biweekly_discovery"]}
    c.eq_int("biweekly count", len(model["biweekly_discovery"]), len(qc_bw))
    for bw, channels in qc_bw.items():
        m = model_bw.get(bw)
        c.ok(f"biweek {bw} present", m is not None)
        if not m:
            continue
        for ch, n in channels.items():
            c.eq_int(f"biweek {bw} {ch}", m["channels"].get(ch, 0), n)

    # ---- 7. Cohort total cross-check -----------------------------------
    raw_cohort_total = sum(_int(r["n"]) for r in cohort_raw)
    raw_cohort_active = sum(_int(r["active"] or 0) for r in cohort_raw)
    model_cohort_total = model["cohort"]["total"]
    c.eq_int("cohort total", model_cohort_total, raw_cohort_total)

    # Weekly signups should also sum to cohort total.
    wk_signup_sum = sum(w["signups"] for w in model["weekly"])
    c.eq_int("Σweekly signups == cohort total", wk_signup_sum, raw_cohort_total)

    # Weekly actuals should sum to cohort active count.
    wk_actual_sum = sum(w["actual"] for w in model["weekly"])
    c.eq_int("Σweekly actual == cohort active", wk_actual_sum, raw_cohort_active)

    # Every per-channel actual must sum to the week total.
    for wk_rec in model["weekly_by_channel"]:
        wk = wk_rec["week"]
        ch_actual = sum(v["actual"] for v in wk_rec["channels"].values())
        wk_total = by_wk_model.get(wk, {}).get("actual", 0)
        c.eq_int(f"week {wk} Σchannel actual == total", ch_actual, wk_total)

    # ---- 8. Per-note n matches matured portion of cohort ---------------
    matured_n = sum(row["n"] for row in model["per_note"])
    # The matured filter in compute excludes last 14d; matured_n should be ≤ cohort_total.
    c.ok(
        "per_note n ≤ cohort total",
        matured_n <= raw_cohort_total,
        f"per_note n={matured_n}, cohort={raw_cohort_total}",
    )

    # ---- 9. Rolling rate sanity: 0-bucket rate should be the lowest ----
    rates_by_notes = {row["notes"]: row["smooth_pct"] for row in model["per_note"]}
    zero_rate = rates_by_notes.get(0, 100)
    c.ok(
        "rate[0] is near-minimum",
        zero_rate <= min(rates_by_notes.values()) + 1.0,
        f"rate[0]={zero_rate}, min={min(rates_by_notes.values())}",
    )

    return c


def main() -> int:
    c = run_checks()
    print(c.report())
    return 0 if c.all_pass() else 1


if __name__ == "__main__":
    sys.exit(main())
