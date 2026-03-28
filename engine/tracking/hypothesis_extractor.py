"""
Hypothesis Extractor — Claude-powered extraction of testable claims from natural language.

Takes free-form text (review feedback, monologue, voice transcript, or dedicated input)
and returns structured hypothesis candidates with auto-mapped MECE taxonomy features.
The human never needs to know feature names — they just talk naturally.
"""

from __future__ import annotations

import json
from typing import Optional

from anthropic import Anthropic

from config.settings import get_settings
from engine.models import CreativeTaxonomy


VALID_VALUES = CreativeTaxonomy.VALID_VALUES

FEATURE_LABELS: dict[str, str] = {
    "message_type_value_prop": "value proposition messaging",
    "message_type_pain_point": "pain point messaging",
    "message_type_social_proof": "social proof messaging",
    "message_type_urgency": "urgency messaging",
    "message_type_education": "educational messaging",
    "message_type_comparison": "comparison messaging",
    "hook_type_question": "question-based hooks",
    "hook_type_statistic": "statistic-based hooks",
    "hook_type_testimonial": "testimonial hooks",
    "hook_type_provocative_claim": "provocative claim hooks",
    "hook_type_scenario": "scenario-based hooks",
    "hook_type_direct_benefit": "direct benefit hooks",
    "cta_type_try_free": "try-free CTA",
    "cta_type_book_demo": "book-demo CTA",
    "cta_type_learn_more": "learn-more CTA",
    "cta_type_see_how": "see-how CTA",
    "cta_type_start_saving_time": "start-saving-time CTA",
    "cta_type_watch_video": "watch-video CTA",
    "tone_clinical": "clinical tone",
    "tone_warm": "warm tone",
    "tone_urgent": "urgent tone",
    "tone_playful": "playful tone",
    "tone_authoritative": "authoritative tone",
    "tone_empathetic": "empathetic tone",
    "visual_style_photography": "photography visuals",
    "visual_style_illustration": "illustration visuals",
    "visual_style_screen_capture": "screen capture visuals",
    "visual_style_text_heavy": "text-heavy visuals",
    "visual_style_mixed_media": "mixed media visuals",
    "visual_style_abstract": "abstract visuals",
    "subject_matter_clinician_at_work": "clinician-at-work imagery",
    "subject_matter_patient_interaction": "patient interaction imagery",
    "subject_matter_product_ui": "product UI imagery",
    "subject_matter_workflow_comparison": "workflow comparison imagery",
    "subject_matter_conceptual": "conceptual imagery",
    "subject_matter_data_viz": "data visualization imagery",
    "color_mood_brand_primary": "brand primary colors",
    "color_mood_warm_earth": "warm earth colors",
    "color_mood_cool_clinical": "cool clinical colors",
    "color_mood_high_contrast": "high contrast colors",
    "color_mood_muted_soft": "muted soft colors",
    "color_mood_bold_saturated": "bold saturated colors",
    "text_density_headline_only": "headline-only text",
    "text_density_headline_subhead": "headline + subhead text",
    "text_density_detailed_copy": "detailed copy",
    "text_density_minimal_overlay": "minimal overlay text",
    "uses_number": "using specific numbers",
    "uses_question": "using questions",
    "uses_first_person": "first-person language",
    "uses_social_proof": "social proof elements",
    "shows_product_ui": "showing product UI",
    "human_face_visible": "visible human faces",
    "contains_specific_number": "specific number callouts",
}

EXTRACTION_SYSTEM_PROMPT = """You are an expert at identifying testable advertising hypotheses from natural language feedback.

You work for JotPsych, an AI clinical note-taking tool for behavioral health clinicians.
Your job: when a human gives feedback about ads, extract any testable claims about what works or doesn't work.

A testable hypothesis is a claim that can be validated by generating ads with specific creative elements and measuring performance (cost per first note completion).

TAXONOMY FEATURES available for mapping:
{taxonomy_json}

BOOLEAN FEATURES: uses_number, uses_question, uses_first_person, uses_social_proof, shows_product_ui, human_face_visible, contains_specific_number

RULES:
- Only extract claims that are genuinely testable through ad creative changes
- Map each hypothesis to 1-3 related_features using the format "dimension_value" (e.g. "tone_urgent", "hook_type_question")
- For boolean features, use the feature name directly (e.g. "uses_number", "shows_product_ui")
- Skip vague sentiment ("I don't like these") — only extract directional claims
- Rewrite the hypothesis as a clear, concise statement a non-marketer could understand
- Set confidence (0.0-1.0) based on how clearly the text states a testable claim
- Return an empty list if there are no testable hypotheses

Return JSON array:
[
  {{
    "hypothesis_text": "Clear, concise statement of what to test",
    "related_features": ["feature_name_1", "feature_name_2"],
    "confidence": 0.85,
    "reasoning": "Why this is testable and how we'd measure it"
  }}
]"""


def _build_taxonomy_json() -> str:
    lines = []
    for dimension, values in VALID_VALUES.items():
        features = [f"{dimension}_{v}" for v in values]
        lines.append(f"  {dimension}: {values}")
        lines.append(f"    → features: {features}")
    return "\n".join(lines)


class HypothesisExtractor:
    """Extracts testable hypothesis candidates from natural language."""

    def __init__(self):
        settings = get_settings()
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def extract(self, text: str, context: str = "") -> list[dict]:
        """
        Extract testable hypothesis candidates from natural language.

        Args:
            text: The natural language feedback, monologue, or idea
            context: Optional context like "review feedback on ad variant" or "voice note"

        Returns:
            List of hypothesis candidate dicts with hypothesis_text, related_features,
            confidence, and reasoning. Empty list if no testable claims found.
        """
        if not text or len(text.strip()) < 10:
            return []

        taxonomy_json = _build_taxonomy_json()
        system = EXTRACTION_SYSTEM_PROMPT.format(taxonomy_json=taxonomy_json)

        user_message = text
        if context:
            user_message = f"[Context: {context}]\n\n{text}"

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]

            candidates = json.loads(raw)
            if not isinstance(candidates, list):
                return []

            valid = []
            for c in candidates:
                if not isinstance(c, dict):
                    continue
                if not c.get("hypothesis_text") or not c.get("related_features"):
                    continue
                valid.append({
                    "hypothesis_text": c["hypothesis_text"],
                    "related_features": c["related_features"],
                    "confidence": float(c.get("confidence", 0.5)),
                    "reasoning": c.get("reasoning", ""),
                })
            return valid

        except Exception as e:
            print(f"Hypothesis extraction failed: {e}")
            return []

    def get_feature_label(self, feature: str) -> str:
        """Convert a feature code to a human-readable label."""
        return FEATURE_LABELS.get(feature, feature.replace("_", " "))
