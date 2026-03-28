"""
AI Image Generator — generates diverse ad background images via Gemini Imagen.

Used alongside HTML template rendering to produce visually distinct ads.
Each ad gets a unique AI-generated background image that matches its hook type
and messaging, with the headline/CTA text composited on top via a new
overlay template.

The regression model tracks asset_source ("template" vs "ai_generated") as a
feature, so we can measure whether AI backgrounds drive lower CpFN.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional


# Scene prompts mapped to hook types — each produces a visually distinct image
SCENE_PROMPTS = {
    "statistic": [
        "A therapist's desk at golden hour, laptop closed, organized notepad with a pen on top. Warm natural light streaming through a window. Clean, minimal composition. No text, no people visible.",
        "Close-up of a wall clock showing 5:00 PM in a cozy office with warm lighting. Blurred therapy couch in background. Soft focus, documentary style. No text.",
        "An empty comfortable therapy chair next to a small side table with a plant, bathed in warm afternoon light. Calm, inviting atmosphere. No text, no people.",
    ],
    "question": [
        "Overhead view of a therapist's workspace: open planner, coffee mug, reading glasses on a wooden desk. Warm earth tones, natural light from above. No text, no people.",
        "A crumpled sticky note on a clean desk next to a laptop, soft bokeh background of a home office. Warm, relatable. No text on the note.",
        "A phone lying face-up on a therapy office desk, afternoon light creating gentle shadows. Minimalist, warm tones. No text, no screen content visible.",
    ],
    "testimonial": [
        "A peaceful therapy room interior: two comfortable chairs facing each other, soft lamp glow, bookshelf in background. Warm, safe, professional. No text, no people.",
        "Close-up of a well-worn therapy notebook with a quality pen beside it on a wooden surface. Warm, golden hour light. Documentary photography style. No text visible.",
        "A small private practice waiting area with a comfortable couch, warm lighting, and a potted fiddle leaf fig. Welcoming atmosphere. No text, no people.",
    ],
    "scenario": [
        "Split composition: left side shows a neat stack of patient folders, right side shows an open door to a bright sunset outside an office. Contrast of work vs freedom. No text, no people.",
        "A laptop on a clean desk next to a framed family photo (faces blurred/not visible), warm desk lamp. Evening home office setting. No text.",
        "An empty therapist's office at the end of the day: chairs slightly pushed back, soft twilight through blinds. Peaceful, done-for-the-day feeling. No text, no people.",
    ],
    "provocative_claim": [
        "Close-up of a shredder destroying papers, with soft bokeh office background. Dramatic lighting. Concept of eliminating paperwork. No text.",
        "A before/after split: left side cluttered desk with papers, right side clean minimalist desk with just a laptop. Dramatic contrast. No text, no people.",
        "A dramatically lit hourglass on a desk with sand running out, therapy office blurred in background. Moody, urgent but warm. No text.",
    ],
    "direct_benefit": [
        "A clinician's hands holding a warm coffee mug, relaxed posture, blurred home background suggesting they're home early. Warm, lifestyle photography. No face visible, no text.",
        "Product screenshot concept: a clean, modern webapp interface showing organized patient notes on a bright screen. Abstract, brand-colored UI mockup. No real text, just placeholder blocks.",
        "A cozy home scene at dusk: comfortable reading chair next to a window, warm lamp glow, suggesting someone got home early. No people visible, no text.",
    ],
}

# Fallback prompts for unknown hook types
_FALLBACK_PROMPTS = [
    "A warm, inviting therapy office with natural afternoon light, comfortable furniture, soft earth tones. Professional interior photography. No text, no people, no logos.",
    "An overhead flat-lay of a therapist's organized desk: notebook, pen, plant, coffee. Clean composition, warm natural tones. No text.",
    "Soft bokeh background of a peaceful clinical office with warm lamp light and plants. Calm, professional atmosphere. No text, no people.",
]


class AIImageGenerator:
    """
    Generate diverse ad background images using Gemini Imagen 4.0.

    Each image is a high-quality background scene that matches the ad's
    hook type and messaging. Text is NOT rendered in the image — it gets
    composited later via the overlay template.
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "imagen-4.0-generate-001"):
        from google import genai
        self.api_key = api_key or os.environ.get("gemini_api", "")
        if not self.api_key:
            raise ValueError("Gemini API key required. Set gemini_api in .env or environment.")
        self.client = genai.Client(api_key=self.api_key)
        self.model = model
        self.output_dir = Path("data/creatives/rendered")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_background(
        self,
        hook_type: str = "direct_benefit",
        variant_index: int = 0,
    ) -> Optional[str]:
        """
        Generate a single background image for an ad variant.

        Args:
            hook_type: The variant's hook type (drives scene selection)
            variant_index: Index in the batch (for prompt rotation)

        Returns:
            Path to the saved PNG file, or None on failure.
        """
        from google.genai import types

        # Pick a scene prompt based on hook type + rotation
        prompts = SCENE_PROMPTS.get(hook_type, _FALLBACK_PROMPTS)
        prompt = prompts[variant_index % len(prompts)]

        # Append quality/style suffix
        prompt += " High quality, 4K resolution, professional photography, shallow depth of field."

        try:
            response = self.client.models.generate_images(
                model=self.model,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",  # Match 1080×1080 feed format
                ),
            )

            if not response.generated_images:
                print(f"[imagen] No images returned for hook_type={hook_type}")
                return None

            img_bytes = response.generated_images[0].image.image_bytes
            if len(img_bytes) < 10000:
                print(f"[imagen] Image too small ({len(img_bytes)} bytes), likely failed")
                return None

            # Save
            filename = f"ai_bg_{hook_type}_{uuid.uuid4().hex[:8]}.png"
            path = self.output_dir / filename
            path.write_bytes(img_bytes)

            return str(path)

        except Exception as e:
            print(f"[imagen] Generation failed for hook_type={hook_type}: {e}")
            return None

    def generate_batch(
        self,
        hook_types: list[str],
        max_images: int = 8,
    ) -> list[Optional[str]]:
        """
        Generate background images for a batch of variants.

        Generates up to max_images unique images, then reuses for remaining variants.
        This keeps API costs reasonable while ensuring visual diversity.
        """
        # Track prompts used per hook type to rotate
        hook_counts: dict[str, int] = {}
        results: list[Optional[str]] = []
        cache: dict[str, list[str]] = {}  # hook_type → list of generated paths

        for i, hook in enumerate(hook_types):
            if i >= max_images:
                # Reuse from cache
                cached = cache.get(hook, [])
                if cached:
                    results.append(cached[i % len(cached)])
                else:
                    # Use any cached image
                    all_cached = [p for paths in cache.values() for p in paths]
                    results.append(all_cached[i % len(all_cached)] if all_cached else None)
                continue

            idx = hook_counts.get(hook, 0)
            hook_counts[hook] = idx + 1

            path = self.generate_background(hook_type=hook, variant_index=idx)
            results.append(path)

            if path:
                cache.setdefault(hook, []).append(path)
                print(f"[imagen] [{i+1}/{min(len(hook_types), max_images)}] Generated background for {hook}")

        return results
