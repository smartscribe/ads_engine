"""
Hypothesis Tracker — evaluates creative hypotheses against regression results.

After each regression run, active hypotheses are checked against the latest
coefficients. Confidence scores are updated, and hypotheses are auto-transitioned
to confirmed/rejected when evidence is strong enough.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from engine.models import CreativeHypothesis, HypothesisStatus, RegressionResult

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

    def generate_report(self) -> dict:
        """Summary of all hypotheses with current confidence and trends."""
        hypotheses = self.store.load_hypotheses()

        by_status = {
            "active": [],
            "confirmed": [],
            "rejected": [],
            "inconclusive": [],
        }

        for h in hypotheses:
            entry = {
                "id": h.id,
                "text": h.hypothesis_text,
                "confidence": h.confidence,
                "created_by": h.created_by,
                "evaluation_count": h.evaluation_count,
                "last_evaluated": h.last_evaluated.isoformat() if h.last_evaluated else None,
                "related_features": h.related_features,
            }

            # Determine trend from evidence
            if h.evaluation_count >= 2:
                prev_conf = h.evidence[-2].split("confidence=")[-1] if len(h.evidence) >= 2 else None
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
