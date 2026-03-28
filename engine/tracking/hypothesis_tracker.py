"""
Hypothesis Tracker — evaluates creative hypotheses against real performance data.

Two evaluation paths:
1. Direct A/B (primary): compare CpFN of hypothesis-tagged variants vs baseline
2. Regression (secondary): check related feature coefficients after each regression run

The human sees plain English summaries, never raw statistics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Optional

from anthropic import Anthropic

from config.settings import get_settings
from engine.models import AdStatus, CreativeHypothesis, HypothesisStatus, RegressionResult

if TYPE_CHECKING:
    from engine.store import Store


CONFIRM_THRESHOLD = 0.8
REJECT_THRESHOLD = 0.2
CONSECUTIVE_REQUIRED = 3


@dataclass
class HypothesisEvaluation:
    hypothesis_id: str
    hypothesis_text: str
    old_confidence: float
    new_confidence: float
    old_status: str
    new_status: str
    evidence_added: str


class HypothesisTracker:
    def __init__(self, store: "Store"):
        self.store = store

    def evaluate_all(self, regression: RegressionResult) -> list[HypothesisEvaluation]:
        """
        Evaluate all active hypotheses against the latest regression results.
        Updates confidence, appends evidence, and auto-transitions status.
        """
        hypotheses = self.store.load_hypotheses()
        active = [h for h in hypotheses if h.status == HypothesisStatus.ACTIVE]

        if not active:
            return []

        evaluations = []
        for hypothesis in active:
            evaluation = self._evaluate_one(hypothesis, regression)
            evaluations.append(evaluation)

        self.store.save_hypotheses(hypotheses)
        return evaluations

    def _evaluate_one(
        self,
        hypothesis: CreativeHypothesis,
        regression: RegressionResult,
    ) -> HypothesisEvaluation:
        old_confidence = hypothesis.confidence
        old_status = hypothesis.status.value

        coefficients = regression.coefficients or {}
        p_values = regression.p_values or {}

        feature_scores = []
        evidence_parts = []

        for feature in hypothesis.related_features:
            if feature not in coefficients:
                evidence_parts.append(f"{feature}: not in model")
                continue

            coef = coefficients[feature]
            p = p_values.get(feature, 1.0)

            if p < 0.05:
                feature_scores.append(0.9)
                evidence_parts.append(
                    f"{feature}: coef={coef:.2f}, p={p:.3f} (significant)"
                )
            elif p < 0.10:
                feature_scores.append(0.6)
                evidence_parts.append(
                    f"{feature}: coef={coef:.2f}, p={p:.3f} (moderate)"
                )
            elif p < 0.20:
                feature_scores.append(0.3)
                evidence_parts.append(
                    f"{feature}: coef={coef:.2f}, p={p:.3f} (weak)"
                )
            else:
                feature_scores.append(0.1)
                evidence_parts.append(
                    f"{feature}: coef={coef:.2f}, p={p:.3f} (not significant)"
                )

        if feature_scores:
            new_confidence = sum(feature_scores) / len(feature_scores)
        else:
            new_confidence = 0.0
            evidence_parts.append("No related features found in regression model")

        # Smooth with previous confidence (exponential moving average)
        if hypothesis.evaluation_count > 0:
            new_confidence = 0.6 * new_confidence + 0.4 * old_confidence

        evidence_str = (
            f"[{date.today()}] R²={regression.r_squared:.3f}, "
            f"n={regression.n_observations}: "
            + "; ".join(evidence_parts)
        )

        hypothesis.confidence = round(new_confidence, 3)
        hypothesis.evidence.append(evidence_str)
        hypothesis.last_evaluated = date.today()
        hypothesis.evaluation_count += 1

        # Auto-transition status
        new_status = old_status
        if hypothesis.evaluation_count >= CONSECUTIVE_REQUIRED:
            recent_confident = self._check_consecutive_confidence(hypothesis)
            if recent_confident == "high":
                hypothesis.status = HypothesisStatus.CONFIRMED
                new_status = "confirmed"
            elif recent_confident == "low":
                hypothesis.status = HypothesisStatus.REJECTED
                new_status = "rejected"

        return HypothesisEvaluation(
            hypothesis_id=hypothesis.id,
            hypothesis_text=hypothesis.hypothesis_text,
            old_confidence=old_confidence,
            new_confidence=hypothesis.confidence,
            old_status=old_status,
            new_status=new_status,
            evidence_added=evidence_str,
        )

    def _check_consecutive_confidence(self, hypothesis: CreativeHypothesis) -> str:
        """
        Check if the last N evaluations consistently show high or low confidence.
        Returns "high", "low", or "mixed".
        """
        if hypothesis.confidence >= CONFIRM_THRESHOLD:
            return "high"
        elif hypothesis.confidence <= REJECT_THRESHOLD:
            return "low"
        return "mixed"

    # ------------------------------------------------------------------
    # Direct performance tracking (primary signal)
    # ------------------------------------------------------------------

    def update_performance(self, hypothesis: CreativeHypothesis) -> None:
        """
        Update hypothesis with direct A/B performance data from PerformanceSnapshot.
        Compares CpFN of hypothesis-tagged variants vs all other variants (baseline).
        """
        if not hypothesis.variant_ids:
            return

        all_snapshots = self.store.get_all_snapshots()
        all_variants = self.store.get_all_variants()

        hypothesis_variant_set = set(hypothesis.variant_ids)

        treatment_spend = 0.0
        treatment_notes = 0
        baseline_spend = 0.0
        baseline_notes = 0

        for snap in all_snapshots:
            if snap.ad_variant_id in hypothesis_variant_set:
                treatment_spend += snap.spend
                treatment_notes += snap.first_note_completions
            else:
                variant = next((v for v in all_variants if v.id == snap.ad_variant_id), None)
                if variant and variant.status in (AdStatus.LIVE, AdStatus.GRADUATED, AdStatus.PAUSED, AdStatus.KILLED):
                    baseline_spend += snap.spend
                    baseline_notes += snap.first_note_completions

        hypothesis.total_spend = round(treatment_spend, 2)

        if treatment_notes > 0:
            hypothesis.treatment_cpfn = round(treatment_spend / treatment_notes, 2)
        else:
            hypothesis.treatment_cpfn = None

        if baseline_notes > 0:
            hypothesis.baseline_cpfn = round(baseline_spend / baseline_notes, 2)
        else:
            hypothesis.baseline_cpfn = None

        if hypothesis.treatment_cpfn and hypothesis.baseline_cpfn and hypothesis.baseline_cpfn > 0:
            hypothesis.lift_pct = round(
                ((hypothesis.baseline_cpfn - hypothesis.treatment_cpfn) / hypothesis.baseline_cpfn) * 100, 1
            )
        else:
            hypothesis.lift_pct = None

    def generate_human_summary(self, hypothesis: CreativeHypothesis) -> str:
        """
        Generate a plain English summary of hypothesis status.
        Uses Claude to write a 1-2 sentence update a non-marketer can understand.
        Falls back to template-based summary if Claude is unavailable.
        """
        variant_count = len(hypothesis.variant_ids)
        spend = hypothesis.total_spend
        t_cpfn = hypothesis.treatment_cpfn
        b_cpfn = hypothesis.baseline_cpfn
        lift = hypothesis.lift_pct

        if spend < 50 and variant_count == 0:
            summary = "No ads generated yet. Ready to test."
            hypothesis.human_summary = summary
            return summary

        if spend < 100:
            summary = (
                f"{variant_count} ads created, ${spend:.0f} spent so far. "
                f"Too early to tell — need more spend for a meaningful read."
            )
            hypothesis.human_summary = summary
            return summary

        try:
            settings = get_settings()
            client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

            prompt = (
                f"Write a 1-2 sentence plain English summary of this ad hypothesis test result. "
                f"Be direct and conversational — like telling a colleague over coffee.\n\n"
                f"Hypothesis: \"{hypothesis.hypothesis_text}\"\n"
                f"Ads testing it: {variant_count}\n"
                f"Total spend: ${spend:.0f}\n"
                f"Cost per first note (treatment): {'$' + f'{t_cpfn:.0f}' if t_cpfn else 'no conversions yet'}\n"
                f"Cost per first note (baseline): {'$' + f'{b_cpfn:.0f}' if b_cpfn else 'unknown'}\n"
                f"Lift: {f'{lift:+.0f}%' if lift is not None else 'not enough data'}\n"
                f"Status: {hypothesis.status.value}\n\n"
                f"Rules: No jargon. No 'CpFN'. Say 'cost per conversion' or just describe the result. "
                f"If lift is positive, it means the hypothesis ads are cheaper (better). "
                f"If negative, they're more expensive (worse)."
            )

            response = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}],
            )
            summary = response.content[0].text.strip()

        except Exception:
            if lift is not None and t_cpfn is not None:
                direction = "better" if lift > 0 else "worse"
                summary = (
                    f"After ${spend:.0f} spent across {variant_count} ads, "
                    f"this is performing {abs(lift):.0f}% {direction} than baseline "
                    f"(${t_cpfn:.0f} vs ${b_cpfn:.0f} per conversion)."
                )
            else:
                summary = (
                    f"${spend:.0f} spent across {variant_count} ads. "
                    f"Not enough conversions yet to compare against baseline."
                )

        hypothesis.human_summary = summary
        return summary

    def get_hypothesis_performance(self, hypothesis_id: str) -> Optional[dict]:
        """Get full performance data for a single hypothesis."""
        hypothesis = self.store.get_hypothesis(hypothesis_id)
        if not hypothesis:
            return None

        self.update_performance(hypothesis)

        return {
            "id": hypothesis.id,
            "hypothesis_text": hypothesis.hypothesis_text,
            "status": hypothesis.status.value,
            "confidence": hypothesis.confidence,
            "variant_count": len(hypothesis.variant_ids),
            "total_spend": hypothesis.total_spend,
            "treatment_cpfn": hypothesis.treatment_cpfn,
            "baseline_cpfn": hypothesis.baseline_cpfn,
            "lift_pct": hypothesis.lift_pct,
            "human_summary": hypothesis.human_summary,
            "evaluation_count": hypothesis.evaluation_count,
            "created_at": hypothesis.created_at.isoformat(),
            "created_by": hypothesis.created_by,
            "source": hypothesis.source,
        }

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def generate_report(self) -> dict:
        """Summary of all hypotheses with current confidence, trends, and performance."""
        hypotheses = self.store.load_hypotheses()

        by_status = {
            "active": [],
            "confirmed": [],
            "rejected": [],
            "inconclusive": [],
        }

        for h in hypotheses:
            self.update_performance(h)

            entry = {
                "id": h.id,
                "text": h.hypothesis_text,
                "confidence": h.confidence,
                "created_by": h.created_by,
                "source": h.source,
                "evaluation_count": h.evaluation_count,
                "last_evaluated": h.last_evaluated.isoformat() if h.last_evaluated else None,
                "related_features": h.related_features,
                "variant_count": len(h.variant_ids),
                "total_spend": h.total_spend,
                "treatment_cpfn": h.treatment_cpfn,
                "baseline_cpfn": h.baseline_cpfn,
                "lift_pct": h.lift_pct,
                "human_summary": h.human_summary,
            }

            if h.evaluation_count >= 2:
                if h.confidence > 0.6:
                    entry["trend"] = "strengthening"
                elif h.confidence < 0.3:
                    entry["trend"] = "weakening"
                else:
                    entry["trend"] = "stable"
            else:
                entry["trend"] = "new"

            by_status[h.status.value].append(entry)

        return {
            "total": len(hypotheses),
            "active": len(by_status["active"]),
            "confirmed": len(by_status["confirmed"]),
            "rejected": len(by_status["rejected"]),
            "hypotheses": by_status,
        }
