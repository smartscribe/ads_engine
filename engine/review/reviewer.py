"""
Review Pipeline — gallery-based approve/reject workflow.

Variants go: DRAFT → (review) → APPROVED or REJECTED
Approved variants proceed to deployment.

The web dashboard (dashboard/) provides the gallery UI.
This module handles the state transitions and feedback capture.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Optional

from engine.models import AdVariant, AdStatus, ReviewFeedback
from engine.review.chips import get_chip, get_implied_preferences
from engine.store import Store


class ReviewPipeline:
    def __init__(self, store: Store):
        self.store = store

    def get_pending_review(self) -> list[AdVariant]:
        """Get all variants awaiting review."""
        return self.store.get_variants_by_status(AdStatus.DRAFT)

    def approve(self, variant_id: str, reviewer: str, notes: Optional[str] = None) -> AdVariant:
        """Approve a variant for deployment."""
        variant = self.store.get_variant(variant_id)
        variant.status = AdStatus.APPROVED
        variant.reviewer = reviewer
        variant.review_notes = notes
        variant.reviewed_at = datetime.utcnow()
        self.store.save_variant(variant)
        return variant

    def reject(self, variant_id: str, reviewer: str, notes: str) -> AdVariant:
        """Reject a variant. Notes are required — they train the generator."""
        variant = self.store.get_variant(variant_id)
        variant.status = AdStatus.REJECTED
        variant.reviewer = reviewer
        variant.review_notes = notes
        variant.reviewed_at = datetime.utcnow()
        self.store.save_variant(variant)
        return variant

    def submit_review(self, feedback: ReviewFeedback) -> AdVariant:
        """
        Process a structured review submission from the dashboard.
        Verdict is applied immediately; chips and notes are optional enrichment.
        Backward compatible — freeform_note still populates review_notes.
        """
        variant = self.store.get_variant(feedback.variant_id)
        variant.reviewer = feedback.reviewer
        variant.reviewed_at = datetime.utcnow()
        variant.review_notes = feedback.freeform_note
        variant.review_chips = feedback.chips
        variant.review_duration_ms = feedback.review_duration_ms

        if feedback.verdict in ("approved", "approve"):
            variant.status = AdStatus.APPROVED
        else:
            variant.status = AdStatus.REJECTED

        self.store.save_variant(variant)
        return variant

    def batch_approve(self, variant_ids: list[str], reviewer: str) -> list[AdVariant]:
        """Approve multiple variants at once."""
        return [self.approve(vid, reviewer) for vid in variant_ids]

    def batch_reject(self, variant_ids: list[str], reviewer: str, notes: str) -> list[AdVariant]:
        """Reject multiple variants with shared feedback."""
        return [self.reject(vid, reviewer, notes) for vid in variant_ids]

    def get_rejection_feedback(self) -> list[dict]:
        """
        Collect all rejection notes with the actual copy + taxonomy that was rejected.
        This feeds back into the generator as negative examples.
        """
        rejected = self.store.get_variants_by_status(AdStatus.REJECTED)
        return [
            {
                "variant_id": v.id,
                "headline": v.headline,
                "body": v.primary_text,
                "cta": v.cta_button,
                "notes": v.review_notes,
                "chips": v.review_chips,
                "implied_preferences": get_implied_preferences(v.review_chips),
                "taxonomy": {
                    "message_type": v.taxonomy.message_type,
                    "hook_type": v.taxonomy.hook_type,
                    "tone": v.taxonomy.tone,
                } if v.taxonomy else None,
            }
            for v in rejected
            if v.review_notes or v.review_chips
        ]

    def get_approval_feedback(self) -> list[dict]:
        """
        Collect approved variants with copy + taxonomy + optional notes.
        Feeds into the generator as positive examples to emulate.
        """
        approved = self.store.get_variants_by_status(AdStatus.APPROVED)
        return [
            {
                "variant_id": v.id,
                "headline": v.headline,
                "body": v.primary_text,
                "cta": v.cta_button,
                "notes": v.review_notes,
                "chips": v.review_chips,
                "taxonomy": {
                    "message_type": v.taxonomy.message_type,
                    "hook_type": v.taxonomy.hook_type,
                    "tone": v.taxonomy.tone,
                } if v.taxonomy else None,
            }
            for v in approved
        ]

    def get_structured_feedback(self) -> dict:
        """
        Aggregate chip-level structured feedback across all reviewed variants.
        Returns chip frequency counts by verdict, by reviewer, and by taxonomy dimension.
        """
        all_variants = self.store.get_all_variants()
        reviewed = [
            v for v in all_variants
            if v.status in (AdStatus.APPROVED, AdStatus.REJECTED) and v.review_chips
        ]

        rejection_chip_counts: Counter = Counter()
        approval_chip_counts: Counter = Counter()
        by_reviewer: dict[str, Counter] = {}

        for v in reviewed:
            reviewer = v.reviewer or "unknown"
            if reviewer not in by_reviewer:
                by_reviewer[reviewer] = Counter()

            for chip_id in v.review_chips:
                chip = get_chip(chip_id)
                if not chip:
                    continue
                by_reviewer[reviewer][chip_id] += 1
                if v.status == AdStatus.REJECTED:
                    rejection_chip_counts[chip_id] += 1
                else:
                    approval_chip_counts[chip_id] += 1

        return {
            "rejection_chips": dict(rejection_chip_counts.most_common()),
            "approval_chips": dict(approval_chip_counts.most_common()),
            "by_reviewer": {r: dict(c.most_common()) for r, c in by_reviewer.items()},
            "total_reviewed_with_chips": len(reviewed),
            "total_reviewed": sum(
                1 for v in all_variants
                if v.status in (AdStatus.APPROVED, AdStatus.REJECTED)
            ),
        }

    def get_reviewer_impact(self, reviewer: str) -> dict:
        """
        Compute 'what you taught the system' stats for a specific reviewer.
        Shows their chip usage, approval rate, and chip coverage rate.
        """
        all_variants = self.store.get_all_variants()
        their_reviews = [
            v for v in all_variants
            if v.reviewer == reviewer
            and v.status in (AdStatus.APPROVED, AdStatus.REJECTED)
        ]

        if not their_reviews:
            return {
                "reviewer": reviewer,
                "total_reviews": 0,
                "approval_rate": 0.0,
                "chip_coverage_rate": 0.0,
                "top_rejection_chips": [],
                "top_approval_chips": [],
                "median_review_duration_ms": 0,
            }

        approvals = [v for v in their_reviews if v.status == AdStatus.APPROVED]
        rejections = [v for v in their_reviews if v.status == AdStatus.REJECTED]
        with_chips = [v for v in their_reviews if v.review_chips]

        rejection_chip_counts: Counter = Counter()
        approval_chip_counts: Counter = Counter()
        for v in their_reviews:
            for chip_id in v.review_chips:
                if v.status == AdStatus.REJECTED:
                    rejection_chip_counts[chip_id] += 1
                else:
                    approval_chip_counts[chip_id] += 1

        durations = [v.review_duration_ms for v in their_reviews if v.review_duration_ms > 0]

        return {
            "reviewer": reviewer,
            "total_reviews": len(their_reviews),
            "total_approvals": len(approvals),
            "total_rejections": len(rejections),
            "approval_rate": len(approvals) / len(their_reviews),
            "chip_coverage_rate": len(with_chips) / len(their_reviews),
            "top_rejection_chips": rejection_chip_counts.most_common(5),
            "top_approval_chips": approval_chip_counts.most_common(5),
            "median_review_duration_ms": int(sorted(durations)[len(durations) // 2]) if durations else 0,
        }
