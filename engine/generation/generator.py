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

import base64
import json
import os
import time
from pathlib import Path
from typing import Optional

import requests

from anthropic import Anthropic
from google import genai
from google.genai import types as genai_types

from config.settings import get_settings
from engine.models import (
    CreativeBrief,
    AdVariant,
    CreativeTaxonomy,
    AdFormat,
    AdStatus,
)


IMAGE_PROMPT_TEMPLATE = """Create a high-quality Meta/Facebook ad image for JotPsych, a clinical AI documentation tool for therapists and behavioral health clinicians.

Ad context:
- Headline: {headline}
- Value prop: {value_proposition}
- Tone: {tone_direction}
- Visual direction: {visual_direction}
- Target audience: behavioral health clinicians and therapists

Visual style requirements:
- Photo-realistic, human-quality — NOT stock photo generic
- Warm, professional clinical environment
- Show real people or product UI in action (not abstract)
- 1:1 square crop suitable for Meta feed
- No text overlaid on the image (copy is added separately)
- No AI-obvious artifacts, no uncanny valley faces
- Negative: no cheesy stock photos, no generic corporate imagery, no watermarks

{extra_direction}"""

VIDEO_PROMPT_TEMPLATE = """Create a short 5-second ad video for JotPsych, a clinical AI documentation tool for behavioral health clinicians.

Ad context:
- Headline: {headline}
- Value prop: {value_proposition}
- Tone: {tone_direction}
- Visual direction: {visual_direction}
- Target audience: therapists and behavioral health clinicians

Video style requirements:
- Cinematic, human-quality footage — NOT stock video generic
- Warm professional clinical environment, natural lighting
- Show a real moment: therapist with patient, or clinician at a desk finishing notes quickly
- Motion should feel authentic and documentary-style, not posed
- Vertical 9:16 aspect ratio for mobile feed
- No text overlaid (copy is added separately)
- Pacing: natural, not hyper-cut

{extra_direction}"""


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
        if client is None:
            settings = get_settings()
            self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        else:
            self.client = client

    def generate_copy(self, brief: CreativeBrief) -> list[dict]:
        """Generate copy variants with taxonomy tags from a brief."""

        prompt = COPY_GENERATION_PROMPT.format(num_variants=brief.num_variants)

        response = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
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

    def _generate_image(
        self,
        gemini: genai.Client,
        variant: dict,
        brief: CreativeBrief,
        out_path: Path,
    ) -> bool:
        """Generate a single image via Gemini. Returns True on success."""
        subject = variant.get("taxonomy", {}).get("subject_matter", "")
        extra = f"Subject matter focus: {subject}." if subject else ""
        prompt = IMAGE_PROMPT_TEMPLATE.format(
            headline=variant.get("headline", ""),
            value_proposition=brief.value_proposition,
            tone_direction=brief.tone_direction,
            visual_direction=brief.visual_direction,
            extra_direction=extra,
        )
        response = gemini.models.generate_content(
            model="gemini-3.1-flash-image-preview",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                out_path.write_bytes(base64.b64decode(part.inline_data.data))
                return True
        return False

    def _generate_video(
        self,
        gemini: genai.Client,
        variant: dict,
        brief: CreativeBrief,
        out_path: Path,
    ) -> bool:
        """Generate a single video via Veo. Returns True on success."""
        settings = get_settings()
        subject = variant.get("taxonomy", {}).get("subject_matter", "")
        extra = f"Subject matter focus: {subject}." if subject else ""
        prompt = VIDEO_PROMPT_TEMPLATE.format(
            headline=variant.get("headline", ""),
            value_proposition=brief.value_proposition,
            tone_direction=brief.tone_direction,
            visual_direction=brief.visual_direction,
            extra_direction=extra,
        )
        operation = gemini.models.generate_videos(
            model="veo-3.0-fast-generate-001",
            prompt=prompt,
            config=genai_types.GenerateVideosConfig(
                aspectRatio="9:16",
                numberOfVideos=1,
            ),
        )
        # Poll until done (Veo jobs take ~60–120s)
        while not operation.done:
            time.sleep(10)
            operation = gemini.operations.get(operation)

        videos = operation.response or operation.result
        generated = getattr(videos, "generated_videos", None) or []
        if not generated:
            return False

        video = generated[0].video
        if video.video_bytes:
            out_path.write_bytes(video.video_bytes)
            return True
        elif video.uri:
            # Veo returns a download URI — fetch it with the API key
            resp = requests.get(video.uri, params={"key": settings.gemini_api}, timeout=60)
            resp.raise_for_status()
            out_path.write_bytes(resp.content)
            return True
        return False

    def generate_assets(self, brief: CreativeBrief, copy_variants: list[dict]) -> list[str]:
        """
        Generate visual assets using Gemini (images) and Veo (video).

        Images  → gemini-3.1-flash-image-preview → .png
        Videos  → veo-3.0-fast-generate-001      → .mp4

        Saves to data/creatives/{brief_id}/ and returns file paths.
        Idempotent — skips already-generated files on re-run.
        """
        settings = get_settings()
        out_dir = Path("data/creatives") / brief.id
        out_dir.mkdir(parents=True, exist_ok=True)

        if not settings.gemini_api:
            return [str(out_dir / f"variant_{i}.placeholder") for i in range(len(copy_variants))]

        gemini = genai.Client(api_key=settings.gemini_api)
        asset_paths = []

        for i, variant in enumerate(copy_variants):
            # Determine format from taxonomy (video vs image)
            fmt = variant.get("taxonomy", {}).get("visual_style", "")
            is_video = "video" in fmt.lower() or brief.formats_requested and any(
                f.value == "video" for f in brief.formats_requested
            )
            # Alternate: even-indexed variants → image, odd → video
            # (gives both types in the gallery without doubling API cost)
            is_video = (i % 2 == 1)

            ext = "mp4" if is_video else "png"
            out_path = out_dir / f"variant_{i}.{ext}"

            if out_path.exists():
                asset_paths.append(str(out_path))
                continue

            try:
                if is_video:
                    success = self._generate_video(gemini, variant, brief, out_path)
                else:
                    success = self._generate_image(gemini, variant, brief, out_path)

                if not success:
                    print(f"[generator] No output from API for variant {i}")
                    out_path = out_dir / f"variant_{i}.placeholder"
            except Exception as e:
                print(f"[generator] Asset generation failed for variant {i}: {e}")
                out_path = out_dir / f"variant_{i}.placeholder"

            asset_paths.append(str(out_path))

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
                        asset_type="video" if asset_path.endswith(".mp4") else "image",
                        taxonomy=taxonomy,
                        status=AdStatus.DRAFT,
                    )
                    variants.append(variant)

        return variants
