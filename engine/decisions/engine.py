"""
Decision Engine — daily scale / kill / wait recommendations.

Thinks like a quant trading desk:
- Each ad is a position
- Spend is capital deployed
- First-note completions are returns
- Kill = stop loss, Scale = increase position, Wait = hold

Decision logic uses a combination of:
1. Statistical significance of conversion rate differences
2. Cost efficiency relative to portfolio average
3. Time-in-market (learning phase protection)
4. Trend direction (improving vs declining)
5. Confidence intervals on CPA
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import numpy as np
from scipy import stats as scipy_stats

from engine.models import (
    AdVariant,
    AdStatus,
    DecisionVerdict,
    DecisionRecord,
    PerformanceSnapshot,
)
from engine.store import Store


# Configurable thresholds
MIN_SPEND_FOR_DECISION = 50.0       # Don't judge until $50 spent
MIN_DAYS_LIVE = 3                    # Learning phase protection
KILL_CPA_MULTIPLIER = 2.0           # Kill if CPA > 2x portfolio average
SCALE_CPA_MULTIPLIER = 0.7          # Scale if CPA < 0.7x portfolio average
MIN_CONVERSIONS_FOR_SIGNIFICANCE = 5 # Need at least 5 conversions to trust
CONFIDENCE_LEVEL = 0.90              # 90% confidence for decisions


class DecisionEngine:
    def __init__(self, store: Store):
        self.store = store

    def run_daily(self, report_date: Optional[date] = None) -> list[DecisionRecord]:
        """
        Run daily decision cycle for all live ads.
        Returns list of DecisionRecords with verdicts.
        """
        if report_date is None:
            report_date = date.today()

        live_variants = self.store.get_variants_by_status(AdStatus.LIVE)
        if not live_variants:
            return []

        # Calculate portfolio-level benchmarks
        portfolio_stats = self._calculate_portfolio_stats(live_variants, report_date)

        decisions = []
        for variant in live_variants:
            decision = self._evaluate_variant(variant, portfolio_stats, report_date)
            if decision:
                self.store.save_decision(decision)
                decisions.append(decision)

        return decisions

    def _calculate_portfolio_stats(self, variants: list[AdVariant], as_of: date) -> dict:
        """Calculate portfolio-wide benchmarks for comparison."""
        total_spend = 0
        total_first_notes = 0
        cpas = []

        for variant in variants:
            snapshots = self.store.get_snapshots_for_variant(variant.id)
            if not snapshots:
                continue

            v_spend = sum(s.spend for s in snapshots)
            v_notes = sum(s.first_note_completions for s in snapshots)
            total_spend += v_spend
            total_first_notes += v_notes

            if v_notes > 0:
                cpas.append(v_spend / v_notes)

        avg_cpa = total_spend / total_first_notes if total_first_notes > 0 else None
        median_cpa = float(np.median(cpas)) if cpas else None

        return {
            "total_spend": total_spend,
            "total_first_notes": total_first_notes,
            "avg_cpa": avg_cpa,
            "median_cpa": median_cpa,
        }

    def _evaluate_variant(
        self, variant: AdVariant, portfolio: dict, report_date: date
    ) -> Optional[DecisionRecord]:
        """Evaluate a single variant and return a decision."""

        snapshots = self.store.get_snapshots_for_variant(variant.id)
        if not snapshots:
            return None

        total_spend = sum(s.spend for s in snapshots)
        total_first_notes = sum(s.first_note_completions for s in snapshots)
        days_live = (report_date - snapshots[0].date).days + 1

        # Not enough data yet
        if total_spend < MIN_SPEND_FOR_DECISION or days_live < MIN_DAYS_LIVE:
            return DecisionRecord(
                ad_variant_id=variant.id,
                date=report_date,
                verdict=DecisionVerdict.WAIT,
                confidence=0.3,
                reasoning=f"Insufficient data: ${total_spend:.0f} spent over {days_live} days. Need ${MIN_SPEND_FOR_DECISION} over {MIN_DAYS_LIVE} days minimum.",
                total_spend=total_spend,
                total_first_notes=total_first_notes,
                cost_per_first_note=total_spend / total_first_notes if total_first_notes > 0 else 0,
                days_live=days_live,
                trend="insufficient_data",
            )

        cpa = total_spend / total_first_notes if total_first_notes > 0 else float("inf")
        portfolio_cpa = portfolio.get("avg_cpa")

        # Calculate trend from recent snapshots
        trend = self._calculate_trend(snapshots)

        # No conversions at all after min spend
        if total_first_notes == 0:
            return DecisionRecord(
                ad_variant_id=variant.id,
                date=report_date,
                verdict=DecisionVerdict.KILL,
                confidence=0.85,
                reasoning=f"Zero conversions after ${total_spend:.0f} spend over {days_live} days.",
                total_spend=total_spend,
                total_first_notes=0,
                cost_per_first_note=0,
                days_live=days_live,
                trend=trend,
            )

        # Not enough conversions for statistical confidence
        if total_first_notes < MIN_CONVERSIONS_FOR_SIGNIFICANCE:
            return DecisionRecord(
                ad_variant_id=variant.id,
                date=report_date,
                verdict=DecisionVerdict.WAIT,
                confidence=0.5,
                reasoning=f"Only {total_first_notes} conversions — need {MIN_CONVERSIONS_FOR_SIGNIFICANCE} for confident decision. CPA: ${cpa:.2f}",
                total_spend=total_spend,
                total_first_notes=total_first_notes,
                cost_per_first_note=cpa,
                days_live=days_live,
                trend=trend,
            )

        # Compare to portfolio
        verdict, confidence, reasoning = self._compare_to_portfolio(
            cpa, portfolio_cpa, total_first_notes, trend, days_live
        )

        return DecisionRecord(
            ad_variant_id=variant.id,
            date=report_date,
            verdict=verdict,
            confidence=confidence,
            reasoning=reasoning,
            total_spend=total_spend,
            total_first_notes=total_first_notes,
            cost_per_first_note=cpa,
            days_live=days_live,
            trend=trend,
        )

    def _compare_to_portfolio(
        self,
        cpa: float,
        portfolio_cpa: Optional[float],
        conversions: int,
        trend: str,
        days_live: int,
    ) -> tuple[DecisionVerdict, float, str]:
        """Compare variant CPA to portfolio average and decide."""

        if portfolio_cpa is None:
            return (
                DecisionVerdict.WAIT,
                0.4,
                "No portfolio benchmark available yet.",
            )

        ratio = cpa / portfolio_cpa

        # Clear winner
        if ratio <= SCALE_CPA_MULTIPLIER and conversions >= MIN_CONVERSIONS_FOR_SIGNIFICANCE:
            confidence = min(0.95, 0.7 + (conversions / 50))
            return (
                DecisionVerdict.SCALE,
                confidence,
                f"CPA ${cpa:.2f} is {ratio:.1%} of portfolio avg ${portfolio_cpa:.2f}. "
                f"{conversions} conversions, trend: {trend}. Strong performer — increase budget.",
            )

        # Clear loser
        if ratio >= KILL_CPA_MULTIPLIER and days_live >= MIN_DAYS_LIVE + 2:
            confidence = min(0.90, 0.6 + (conversions / 30))
            return (
                DecisionVerdict.KILL,
                confidence,
                f"CPA ${cpa:.2f} is {ratio:.1%} of portfolio avg ${portfolio_cpa:.2f}. "
                f"Underperforming after {days_live} days. Cut losses.",
            )

        # Middle ground
        return (
            DecisionVerdict.WAIT,
            0.5,
            f"CPA ${cpa:.2f} is {ratio:.1%} of portfolio avg ${portfolio_cpa:.2f}. "
            f"{conversions} conversions, trend: {trend}. Not enough signal — hold.",
        )

    def _calculate_trend(self, snapshots: list[PerformanceSnapshot]) -> str:
        """Calculate performance trend from recent snapshots."""
        if len(snapshots) < 3:
            return "insufficient_data"

        # Use last 7 days of CPA data
        recent = sorted(snapshots, key=lambda s: s.date)[-7:]
        cpas = []
        for s in recent:
            if s.first_note_completions > 0:
                cpas.append(s.spend / s.first_note_completions)

        if len(cpas) < 3:
            return "insufficient_data"

        # Simple linear regression on CPA over time
        x = np.arange(len(cpas))
        slope, _, _, _, _ = scipy_stats.linregress(x, cpas)

        if slope < -0.5:
            return "improving"   # CPA decreasing = good
        elif slope > 0.5:
            return "declining"   # CPA increasing = bad
        else:
            return "stable"
