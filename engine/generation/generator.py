"""
Creative Generator — takes briefs, produces ad variants with auto-taxonomy tagging.

This is the module the intern owns most heavily. The scaffolding is here;
the actual image/video generation pipeline needs to be built out.

Key decisions for the intern:
- Which image generation tool(s)? (Midjourney, Flux, DALL-E, Ideogram, etc.)
- How to ensure output doesn't look like AI slop?
- Can we do video? What tools? (Runway, Pika, Kling, etc.)
- How to maintain brand consistency across variants?
- How to generate copy variants that don't all sound the same?
"""

from __future__ import annotations

import json
from typing import Optional

from anthropic import Anthropic

from engine.models import (
    CreativeBrief,
    AdVariant,
    CreativeTaxonomy,
    AdFormat,
    AdStatus,
)


COPY_GENERATION_PROMPT = """You are a direct-response copywriter for JotPsych, a clinical documentation AI for behavioral health.

Given a creative brief, generate {num_variants} distinct ad copy variants.
Each variant must be meaningfully different — not just word swaps. Vary the:
- Hook (how it opens)
- Message angle (what benefit/pain it leads with)
- Tone (within the brief's direction)
- CTA phrasing

CRITICAL: Do NOT write like an AI. No "revolutionize", no "streamline your workflow",
no "in today's fast-paced world". Write like a human copywriter who has talked to
100 burned-out therapists. Be specific. Be real.

For each variant, also provide taxonomy tags. Output JSON array:
[
    {{
        "headline": "...",
        "primary_text": "...",
        "description": "...",
        "cta_button": "...",
        "taxonomy": {{
            "message_type": "value_prop|pain_point|social_proof|urgency|education|comparison",
            "hook_type": "question|statistic|testimonial|provocative_claim|scenario|direct_benefit",
            "cta_type": "try_free|book_demo|learn_more|see_how|start_saving_time|watch_video",
            "tone": "clinical|warm|urgent|playful|authoritative|empathetic",
            "visual_style": "photography|illustration|screen_capture|text_heavy|mixed_media|abstract",
            "subject_matter": "clinician_at_work|patient_interaction|product_ui|workflow_comparison|conceptual|data_viz",
            "color_mood": "brand_primary|warm_earth|cool_clinical|high_contrast|muted_soft|bold_saturated",
            "text_density": "headline_only|headline_subhead|detailed_copy|minimal_overlay",
            "headline_word_count": <int>,
            "uses_number": <bool>,
            "uses_question": <bool>,
            "uses_first_person": <bool>,
            "uses_social_proof": <bool>,
            "copy_reading_level": <float>
        }}
    }}
]
"""


class CreativeGenerator:
    """
    Generates ad variants from creative briefs.

    Copy generation uses Claude. Image/video generation is stubbed —
    the intern needs to wire up the actual asset generation pipeline.
    """

    def __init__(self, client: Optional[Anthropic] = None):
        self.client = client or Anthropic()

    def generate_copy(self, brief: CreativeBrief) -> list[dict]:
        """Generate copy variants with taxonomy tags from a brief."""

        prompt = COPY_GENERATION_PROMPT.format(num_variants=brief.num_variants)

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4000,
            system=prompt,
            messages=[
                {
                    "role": "user",
                    "content": f"""Creative Brief:
Target: {brief.target_audience}
Value Prop: {brief.value_proposition}
Pain Point: {brief.pain_point}
Desired Action: {brief.desired_action}
Tone: {brief.tone_direction}
Visual Direction: {brief.visual_direction}
Key Phrases: {', '.join(brief.key_phrases)}
Formats: {[f.value for f in brief.formats_requested]}
""",
                }
            ],
        )

        text = response.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        return json.loads(text.strip())

    def generate_assets(self, brief: CreativeBrief, copy_variants: list[dict]) -> list[str]:
        """
        Generate visual assets for each copy variant.

        STUB — intern implements this.

        Should return a list of file paths to generated assets.
        Consider:
        - Image generation API (Flux, Midjourney, DALL-E, Ideogram)
        - Video generation (Runway, Pika, Kling)
        - Brand consistency checks
        - Resolution/aspect ratio per platform+placement
        - Anti-AI-slop quality filter
        """
        asset_paths = []
        for i, variant in enumerate(copy_variants):
            # PLACEHOLDER: generates a manifest file instead of actual assets
            # Intern replaces this with real image/video generation
            path = f"data/creatives/{brief.id}/variant_{i}.json"
            asset_paths.append(path)
        return asset_paths

    def generate(self, brief: CreativeBrief) -> list[AdVariant]:
        """Full generation pipeline: copy → assets → tagged variants."""

        copy_variants = self.generate_copy(brief)
        asset_paths = self.generate_assets(brief, copy_variants)

        variants = []
        for copy_data, asset_path in zip(copy_variants, asset_paths):
            tax_data = copy_data["taxonomy"]

            # Fill in structural taxonomy fields from the brief
            for fmt in brief.formats_requested:
                for platform in brief.platforms:
                    taxonomy = CreativeTaxonomy(
                        **tax_data,
                        format=fmt,
                        platform=platform,
                        placement="feed",  # Default; expand per platform logic
                    )

                    variant = AdVariant(
                        brief_id=brief.id,
                        headline=copy_data["headline"],
                        primary_text=copy_data["primary_text"],
                        description=copy_data.get("description", ""),
                        cta_button=copy_data.get("cta_button", "Learn More"),
                        asset_path=asset_path,
                        asset_type="image" if fmt != AdFormat.VIDEO else "video",
                        taxonomy=taxonomy,
                        status=AdStatus.DRAFT,
                    )
                    variants.append(variant)

        return variants
