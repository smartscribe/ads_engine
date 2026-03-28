"""
AI Image Generator — generates diverse ad background images via Gemini Imagen.

Architecture: Gemini generates the photo layer (no text), Playwright composites
the headline/CTA/logo on top via the image_overlay template. This gives us
photorealism from AI with brand precision from templates.

Key constraints:
- NEVER let Gemini render text (it hallucinates letterforms)
- Every prompt anchors in photorealism ("shot on Sony A7III, 35mm lens")
- Safe zones: top 20% and bottom 25% must have simple/dark background for text overlay
- All images validated: magic bytes, dimensions, file size before use
"""

from __future__ import annotations

import os
import struct
import uuid
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Photorealism anchor — prepended to every scene prompt
# ---------------------------------------------------------------------------

_PHOTO_ANCHOR = (
    "Photograph, documentary style, shot on Sony A7III, 35mm lens, f/2.8, "
    "natural lighting. "
)

# Safe zone instruction — appended to every scene prompt
_SAFE_ZONE = (
    "CRITICAL COMPOSITION: Leave the top 20% of the frame with dark or neutral "
    "simple background (for logo placement). Leave the bottom 25% of the frame "
    "with dark or neutral simple background (for text overlay). The main subject "
    "should be in the center 55% of the frame vertically. "
    "No text, no words, no letters, no numbers, no watermarks, no logos anywhere in the image."
)

# Negative prompt suffix
_NEGATIVE = (
    " Do NOT include: any text, any words, any letters, any handwriting, "
    "any signage, any screen content, any UI elements, any distorted hands, "
    "any impossible anatomy, any stock photo watermarks."
)


# ---------------------------------------------------------------------------
# Structured scene prompts — camera angle, subject, environment, lighting, mood
# ---------------------------------------------------------------------------

SCENE_PROMPTS = {
    "statistic": [
        (
            "Eye-level view of a therapist's wooden desk at golden hour. "
            "Subject: closed laptop, organized notepad with a quality pen, small succulent plant. "
            "Environment: warm home office, wooden furniture, soft curtains. "
            "Lighting: warm golden afternoon sun streaming through window, long shadows. "
            "Mood: peaceful, end-of-day calm."
        ),
        (
            "Close-up, shallow depth of field. Subject: analog wall clock showing 5:00 PM. "
            "Environment: cozy therapy office, blurred comfortable furniture in background. "
            "Lighting: warm ambient lamp glow mixed with fading daylight. "
            "Mood: the workday is done, relief."
        ),
        (
            "45-degree overhead angle. Subject: an open day planner showing a fully checked-off to-do list, "
            "a cup of herbal tea beside it. "
            "Environment: clean wooden desk surface, warm tones. "
            "Lighting: soft diffused natural light from above. "
            "Mood: organized, accomplished, serene."
        ),
    ],
    "question": [
        (
            "Directly overhead flat-lay. Subject: therapist's workspace items — open moleskine planner, "
            "reading glasses, ceramic coffee mug, a single houseplant leaf. "
            "Environment: warm wooden desk surface, earth tones. "
            "Lighting: soft natural light from a nearby window, no harsh shadows. "
            "Mood: contemplative, thoughtful, inviting."
        ),
        (
            "Eye-level close-up, very shallow depth of field (f/1.8). "
            "Subject: a single crumpled yellow sticky note on an otherwise clean white desk. "
            "Environment: minimalist home office, soft bokeh background. "
            "Lighting: warm desk lamp creating a spotlight effect. "
            "Mood: relatable frustration, a question hanging in the air."
        ),
        (
            "Low angle looking up. Subject: an empty therapy chair with a throw blanket draped over one arm. "
            "Environment: warm clinical office with a bookshelf and soft rug. "
            "Lighting: late afternoon sun creating warm rectangles on the wall. "
            "Mood: waiting, expectant, the space between sessions."
        ),
    ],
    "testimonial": [
        (
            "Wide angle, f/4. Subject: two comfortable therapy chairs facing each other in a warm room. "
            "Environment: small private practice — bookshelf, soft lamp, plant on windowsill. "
            "Lighting: warm incandescent glow from a floor lamp, golden hour outside window. "
            "Mood: safe, intimate, professional trust."
        ),
        (
            "Close-up, macro-like. Subject: a well-worn leather therapy notebook open to a blank page, "
            "quality fountain pen resting beside it. "
            "Environment: rich wooden desk surface, warm tones. "
            "Lighting: warm golden light from the side, gentle highlights on leather texture. "
            "Mood: years of expertise, careful attention."
        ),
        (
            "Eye-level. Subject: a small, welcoming waiting area — comfortable couch with throw pillows, "
            "a potted fiddle leaf fig, a side table with a water carafe. "
            "Environment: boutique therapy clinic, warm modern decor. "
            "Lighting: diffused natural light through frosted glass, warm and even. "
            "Mood: welcoming, you belong here."
        ),
    ],
    "scenario": [
        (
            "Eye-level, dramatic composition. Subject: left side shows a tall stack of manila patient folders, "
            "right side shows an open door revealing a golden sunset. "
            "Environment: clinical office transitioning to outdoors. "
            "Lighting: contrast between fluorescent office light (left) and warm sunset (right). "
            "Mood: the choice between paperwork and life."
        ),
        (
            "Over-the-shoulder, shallow depth of field. Subject: a laptop screen (blurred/not readable) "
            "next to a framed photo of a family at the beach (faces not visible). "
            "Environment: home office desk at dusk, warm desk lamp. "
            "Lighting: blue-hour light outside window, warm lamp on desk. "
            "Mood: longing, work-life balance tension."
        ),
        (
            "Wide shot, f/5.6. Subject: an empty therapist's office at twilight — chairs slightly pushed back, "
            "a coat still hanging on the door hook, soft light through blinds. "
            "Environment: well-appointed therapy room at day's end. "
            "Lighting: soft twilight through venetian blinds creating stripe patterns. "
            "Mood: peaceful emptiness, the day is done."
        ),
    ],
    "provocative_claim": [
        (
            "Close-up, dramatic lighting. Subject: a paper shredder mid-shred with white paper curling through it. "
            "Environment: out-of-focus office background, deep shadows. "
            "Lighting: single strong directional light from the side, high contrast. "
            "Mood: decisive destruction of the old way, bold."
        ),
        (
            "Split frame composition. Subject: left half is a cluttered desk buried in papers, coffee rings, "
            "scattered pens; right half is a pristine minimalist desk with just a closed laptop. "
            "Environment: same room, different realities. "
            "Lighting: harsh overhead fluorescent on left, warm natural light on right. "
            "Mood: dramatic before/after contrast."
        ),
        (
            "Dramatic close-up. Subject: an hourglass with sand running out, placed on a dark wooden desk. "
            "Environment: deep, moody therapy office background in soft focus. "
            "Lighting: single warm spotlight on the hourglass, dramatic shadows. "
            "Mood: urgency, time is running out, but warmly so."
        ),
    ],
    "direct_benefit": [
        (
            "Eye-level, intimate. Subject: a person's hands (only hands visible) wrapping around a warm ceramic mug, "
            "relaxed posture suggesting they're sitting comfortably at home. "
            "Environment: cozy living room, soft sofa, warm blanket visible. "
            "Lighting: warm golden evening light, window glow. "
            "Mood: comfort, being home early, relief."
        ),
        (
            "Wide establishing shot. Subject: a cozy reading nook next to a large window at dusk — "
            "an armchair with a reading lamp, a small stack of books, a throw blanket. "
            "Environment: warm residential interior, lived-in and comfortable. "
            "Lighting: blue-hour light outside, warm lamp creating an inviting glow inside. "
            "Mood: this could be your evening, instead of charting."
        ),
        (
            "Eye-level, medium shot. Subject: a park bench under a tree at golden hour, "
            "a closed laptop bag leaning against it. "
            "Environment: peaceful suburban park, autumn leaves, soft grass. "
            "Lighting: warm golden hour sun filtering through tree branches. "
            "Mood: freedom, fresh air, the workday ended early."
        ),
    ],
}

# Fallback prompts for unknown hook types
_FALLBACK_PROMPTS = [
    (
        "Eye-level, f/2.8. Subject: a warm, inviting therapy office interior with a comfortable chair "
        "and a small side table with a plant. "
        "Environment: professional but cozy clinical space, earth tones. "
        "Lighting: soft natural afternoon light through a window. "
        "Mood: calm, professional, welcoming."
    ),
]


# ---------------------------------------------------------------------------
# Image validation
# ---------------------------------------------------------------------------

def _validate_image(data: bytes, min_size: int = 50_000) -> tuple[bool, str]:
    """
    Validate a generated image meets quality standards.

    Checks:
    1. Magic bytes — is it actually a PNG or JPEG?
    2. File size — >50KB for 1080×1080 (anything smaller is likely corrupt)
    3. Dimensions — at least 512×512

    Returns (is_valid, reason).
    """
    if len(data) < min_size:
        return False, f"Too small: {len(data)} bytes (min {min_size})"

    # Check PNG magic bytes
    is_png = data[:8] == b'\x89PNG\r\n\x1a\n'
    # Check JPEG magic bytes
    is_jpeg = data[:2] == b'\xff\xd8'

    if not is_png and not is_jpeg:
        return False, f"Not a valid image (magic bytes: {data[:4].hex()})"

    # Check dimensions for PNG
    if is_png and len(data) > 24:
        try:
            width = struct.unpack('>I', data[16:20])[0]
            height = struct.unpack('>I', data[20:24])[0]
            if width < 512 or height < 512:
                return False, f"Too small: {width}×{height} (min 512×512)"
        except struct.error:
            return False, "Could not read PNG dimensions"

    return True, "OK"


class AIImageGenerator:
    """
    Generate diverse ad background images using Gemini Imagen 4.0.

    Architecture:
    1. Select a structured scene prompt based on hook_type
    2. Prepend photorealism anchor ("shot on Sony A7III, 35mm...")
    3. Append safe zone instructions for text overlay areas
    4. Generate via Imagen API
    5. Validate output (magic bytes, dimensions, file size)
    6. Return path — Playwright composites text on top via image_overlay template
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

        Returns path to the saved PNG file, or None on failure.
        """
        from google.genai import types

        # Pick and build the structured prompt
        prompts = SCENE_PROMPTS.get(hook_type, _FALLBACK_PROMPTS)
        scene = prompts[variant_index % len(prompts)]

        # Assemble: anchor + scene + safe zone + negative
        full_prompt = _PHOTO_ANCHOR + scene + " " + _SAFE_ZONE + _NEGATIVE

        try:
            response = self.client.models.generate_images(
                model=self.model,
                prompt=full_prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                ),
            )

            if not response.generated_images:
                print(f"[imagen] No images returned for hook_type={hook_type}")
                return None

            img_bytes = response.generated_images[0].image.image_bytes

            # Validate the image
            is_valid, reason = _validate_image(img_bytes)
            if not is_valid:
                print(f"[imagen] Validation failed for hook_type={hook_type}: {reason}")
                return None

            # Save
            filename = f"ai_bg_{hook_type}_{uuid.uuid4().hex[:8]}.png"
            path = self.output_dir / filename
            path.write_bytes(img_bytes)

            print(f"[imagen] Generated {len(img_bytes):,} bytes → {filename}")
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

        Generates up to max_images unique images, then reuses for remaining.
        This keeps API costs reasonable (~$0.03/image) while ensuring diversity.
        """
        hook_counts: dict[str, int] = {}
        results: list[Optional[str]] = []
        cache: dict[str, list[str]] = {}

        for i, hook in enumerate(hook_types):
            if i >= max_images:
                # Reuse from cache
                cached = cache.get(hook, [])
                if cached:
                    results.append(cached[i % len(cached)])
                else:
                    all_cached = [p for paths in cache.values() for p in paths]
                    results.append(all_cached[i % len(all_cached)] if all_cached else None)
                continue

            idx = hook_counts.get(hook, 0)
            hook_counts[hook] = idx + 1

            path = self.generate_background(hook_type=hook, variant_index=idx)
            results.append(path)

            if path:
                cache.setdefault(hook, []).append(path)
                print(f"[imagen] [{i+1}/{min(len(hook_types), max_images)}] ✓ {hook}")
            else:
                print(f"[imagen] [{i+1}/{min(len(hook_types), max_images)}] ✗ {hook} (failed, will use template fallback)")

        return results
