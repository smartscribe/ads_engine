"""
Budget Pacing — track spend vs monthly budget, compute run rate, fire alerts.

Called during the daily cycle after pulling performance snapshots.
Alerts via Slack when run rate exceeds or falls below configured thresholds.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from engine.models import PerformanceSnapshot


def compute_budget_pacing(
    snapshots: list[PerformanceSnapshot],
    monthly_budget: float,
    report_date: Optional[date] = None,
) -> dict:
    """
    Compute daily/weekly/monthly spend vs budget.

    Returns:
        {
            "month": "2026-03",
            "total_spend": 8500.0,
            "daily_avg": 425.0,
            "projected_monthly": 13175.0,
            "budget": 17500.0,
            "pacing_pct": 75.3,
            "run_rate_pct": 75.3,
            "days_elapsed": 20,
            "days_remaining": 10,
            "alert_status": "on_track",  # "on_track" | "over_pace" | "under_pace"
            "daily_target": 583.33,
        }
    """
    if report_date is None:
        report_date = date.today()

    year = report_date.year
    month = report_date.month

    # Filter snapshots to current month
    month_snaps = [
        s for s in snapshots
        if _snap_date(s) is not None
        and _snap_date(s).year == year
        and _snap_date(s).month == month
    ]

    # Group spend by date
    daily_spend = defaultdict(float)
    for s in month_snaps:
        d = _snap_date(s)
        if d:
            daily_spend[d.isoformat()] += s.spend

    total_spend = sum(daily_spend.values())
    days_elapsed = report_date.day
    days_in_month = _days_in_month(year, month)
    days_remaining = days_in_month - days_elapsed

    daily_avg = total_spend / max(days_elapsed, 1)
    projected_monthly = daily_avg * days_in_month
    daily_target = monthly_budget / days_in_month

    # Pacing: what % of budget have we spent so far vs what % of month is done
    expected_spend = daily_target * days_elapsed
    pacing_pct = round((total_spend / max(expected_spend, 1)) * 100, 1) if expected_spend > 0 else 0
    run_rate_pct = round((projected_monthly / monthly_budget) * 100, 1) if monthly_budget > 0 else 0

    # Alert status
    if run_rate_pct > 110:
        alert_status = "over_pace"
    elif run_rate_pct < 70:
        alert_status = "under_pace"
    else:
        alert_status = "on_track"

    return {
        "month": f"{year}-{month:02d}",
        "total_spend": round(total_spend, 2),
        "daily_avg": round(daily_avg, 2),
        "projected_monthly": round(projected_monthly, 2),
        "budget": monthly_budget,
        "pacing_pct": pacing_pct,
        "run_rate_pct": run_rate_pct,
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "days_in_month": days_in_month,
        "daily_target": round(daily_target, 2),
        "alert_status": alert_status,
        "daily_breakdown": dict(daily_spend),
    }


def _snap_date(s: PerformanceSnapshot) -> Optional[date]:
    """Extract a date object from a snapshot's date field."""
    if isinstance(s.date, date):
        return s.date
    try:
        return date.fromisoformat(str(s.date))
    except Exception:
        return None


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in a given month."""
    if month == 12:
        return (date(year + 1, 1, 1) - date(year, 12, 1)).days
    return (date(year, month + 1, 1) - date(year, month, 1)).days
