"""
Feedback Chip Taxonomy — structured review signal mapped to CreativeTaxonomy dimensions.

Chips are always optional. The core approve/reject action is instant; chips are a
bonus enrichment step that feeds directly into creative memory without any NLP parsing.

Each chip definition has:
  - id:        Stored on the variant (review_chips list)
  - label:     Display text in the dashboard
  - category:  "rejection" | "approval"
  - dimension: Which CreativeTaxonomy field this maps to (optional)
  - implied:   Dict of taxonomy field overrides implied by this chip (optional)
               These get merged into the next generation context.
"""

from __future__ import annotations

from typing import Optional


REJECTION_CHIPS: list[dict] = [
    {
        "id": "headline_too_generic",
        "label": "Headline too generic",
        "category": "rejection",
        "dimension": "hook_type",
        "implied": {"uses_number": False},
    },
    {
        "id": "wrong_tone",
        "label": "Wrong tone",
        "category": "rejection",
        "dimension": "tone",
        "implied": {},
    },
    {
        "id": "copy_feels_ai",
        "label": "Feels AI-written",
        "category": "rejection",
        "dimension": "tone",
        "implied": {},
    },
    {
        "id": "weak_value_prop",
        "label": "Weak value prop",
        "category": "rejection",
        "dimension": "message_type",
        "implied": {},
    },
    {
        "id": "cta_unclear",
        "label": "CTA unclear",
        "category": "rejection",
        "dimension": "cta_type",
        "implied": {},
    },
    {
        "id": "visual_wrong",
        "label": "Visual off-brand",
        "category": "rejection",
        "dimension": "visual_style",
        "implied": {},
    },
    {
        "id": "too_long",
        "label": "Too long",
        "category": "rejection",
        "dimension": "text_density",
        "implied": {},
    },
    {
        "id": "needs_number",
        "label": "Needs a number",
        "category": "rejection",
        "dimension": None,
        "implied": {"uses_number": True},
    },
    {
        "id": "more_empathetic",
        "label": "More empathetic",
        "category": "rejection",
        "dimension": "tone",
        "implied": {"tone": "empathetic"},
    },
    {
        "id": "more_urgent",
        "label": "More urgent",
        "category": "rejection",
        "dimension": "tone",
        "implied": {"tone": "urgent"},
    },
    {
        "id": "show_product",
        "label": "Show the product",
        "category": "rejection",
        "dimension": "subject_matter",
        "implied": {"subject_matter": "product_ui"},
    },
    {
        "id": "needs_social_proof",
        "label": "Needs social proof",
        "category": "rejection",
        "dimension": None,
        "implied": {"uses_social_proof": True},
    },
]

APPROVAL_CHIPS: list[dict] = [
    {
        "id": "great_headline",
        "label": "Great headline",
        "category": "approval",
        "dimension": "hook_type",
        "implied": {},
    },
    {
        "id": "love_the_tone",
        "label": "Love the tone",
        "category": "approval",
        "dimension": "tone",
        "implied": {},
    },
    {
        "id": "strong_cta",
        "label": "Strong CTA",
        "category": "approval",
        "dimension": "cta_type",
        "implied": {},
    },
    {
        "id": "good_visual",
        "label": "Good visual",
        "category": "approval",
        "dimension": "visual_style",
        "implied": {},
    },
    {
        "id": "perfect_length",
        "label": "Perfect length",
        "category": "approval",
        "dimension": "text_density",
        "implied": {},
    },
]

ALL_CHIPS: list[dict] = REJECTION_CHIPS + APPROVAL_CHIPS

# Index by id for O(1) lookup
_CHIPS_BY_ID: dict[str, dict] = {chip["id"]: chip for chip in ALL_CHIPS}


def get_chip(chip_id: str) -> Optional[dict]:
    return _CHIPS_BY_ID.get(chip_id)


def get_implied_preferences(chip_ids: list[str]) -> dict:
    """
    Merge implied preference signals from a list of chip ids.
    Used to enrich the creative memory with structured signals.
    """
    merged: dict = {}
    for chip_id in chip_ids:
        chip = _CHIPS_BY_ID.get(chip_id)
        if chip and chip.get("implied"):
            merged.update(chip["implied"])
    return merged


def chips_for_api() -> dict:
    """Serializable structure for GET /api/feedback-chips."""
    return {
        "rejection": REJECTION_CHIPS,
        "approval": APPROVAL_CHIPS,
    }
