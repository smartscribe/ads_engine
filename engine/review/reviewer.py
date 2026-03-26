"""
Review Pipeline — gallery-based approve/reject workflow.

Variants go: DRAFT → (review) → APPROVED or REJECTED
Approved variants proceed to deployment.

The web dashboard (dashboard/) provides the gallery UI.
This module handles the state transitions and feedback capture.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from engine.models import AdVariant, AdStatus
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
                "taxonomy": {
                    "message_type": v.taxonomy.message_type,
                    "hook_type": v.taxonomy.hook_type,
                    "tone": v.taxonomy.tone,
                } if v.taxonomy else None,
            }
            for v in rejected
            if v.review_notes
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
                "taxonomy": {
                    "message_type": v.taxonomy.message_type,
                    "hook_type": v.taxonomy.hook_type,
                    "tone": v.taxonomy.tone,
                } if v.taxonomy else None,
            }
            for v in approved
        ]
