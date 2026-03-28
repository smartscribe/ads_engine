"""
AI Image Generator — Claude-directed scene prompts → Gemini Imagen backgrounds.

Architecture (three-layer quality):
  1. Claude SceneDirector crafts a bespoke image prompt per ad
     (receives headline, body, taxonomy, regression context)
  2. Gemini Imagen renders the photograph
  3. Claude Vision validates — catches text, artifacts, nonsense

The generated image is a BACKGROUND ONLY — no text, no logos.
Playwright composites headline/CTA/logo on top via image_overlay template.

This means:
- Every AI ad has a scene that visually reinforces its headline
- Regression insights (what visual styles work) flow into scene direction
- The image model can be swapped (Imagen → Flux → DALL-E) without touching assembly
"""

from __future__ import annotations

import os
import struct
import uuid
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from engine.memory.models import GenerationContext


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PHOTO_ANCHOR = (
    "Photograph, documentary style, shot on Sony A7III, 35mm lens, f/2.8, "
    "natural lighting. "
)

_COMPOSITION_SUFFIX = (
    " COMPOSITION: The top portion of the image should have simple, dark, or blurred "
    "background with open space. The bottom portion should also have darker, simpler "
    "background. Place the main subject in the center of the frame. "
    "This image will be used as a background with text overlaid on top."
)

_NEGATIVE_SUFFIX = (
    " The image must contain ABSOLUTELY NO TEXT of any kind. No words, no letters, "
    "no numbers, no percentages, no labels, no captions, no handwriting, no signage, "
    "no book titles, no brand names, no screen content, no UI elements, no watermarks. "
    "Pure photography only."
)

# System prompt for Claude SceneDirector
_SCENE_DIRECTOR_SYSTEM = """You are an expert art director writing image generation prompts for ad backgrounds.

You will receive an ad's headline, body copy, hook type, tone, and message type. Your job is to craft a SINGLE detailed scene description that:

1. VISUALLY REINFORCES the ad's message (e.g., "Third Resignation This Year?" → empty chair, packed box, departure scene)
2. Creates an EMOTIONAL response that matches the tone (empathetic → warm/soft, urgent → dramatic/tense)
3. Is DISTINCTLY DIFFERENT from generic "therapy office" or "person at desk" scenes
4. Uses SPECIFIC visual details (exact objects, materials, lighting qualities)

STRICT RULES:
- NEVER include any text, words, letters, numbers, clocks with numbers, signs, or readable content in the scene
- NEVER use percentages, fractions, or any numerical values in your description
- NEVER describe screens, monitors, or devices showing any content
- Describe the scene for a SQUARE (one-to-one) photograph
- Use this exact structure: camera angle and lens → main subject → environment/setting → lighting quality → emotional mood
- Keep the description to three to five sentences maximum
- The image will have text overlaid on top and bottom, so the main subject should be in the center

BRAND CONTEXT: JotPsych is a clinical documentation AI for behavioral health therapists. The visual world is: warm therapy offices, clinician workspaces, home-life balance, the feeling of being done with paperwork. Color palette leans warm: golden light, earth tones, deep blues, soft pinks. Documentary photography style, not stock photo polish.

OUTPUT: Return ONLY the scene description. No preamble, no explanation, no JSON."""


class SceneDirector:
    """
    Uses Claude to craft a bespoke Imagen prompt for each ad variant.

    Instead of picking from a static list of scenes, Claude writes a unique
    scene description that visually reinforces the specific ad's message.
    Regression insights about what visual styles work are injected as context.
    """

    def __init__(self, client=None):
        if client is None:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        else:
            self.client = client

    def craft_scene_prompt(
        self,
        headline: str,
        body: str,
        hook_type: str = "",
        tone: str = "",
        message_type: str = "",
        generation_context: "Optional[GenerationContext]" = None,
    ) -> str:
        """
        Claude receives the ad copy + creative strategy + regression context
        and returns a detailed, structured Imagen prompt.
        """
        # Build the user message with all context
        parts = [
            f"AD HEADLINE: {headline}",
            f"AD BODY (first 100 chars): {body[:100]}",
            f"HOOK TYPE: {hook_type}",
            f"TONE: {tone}",
            f"MESSAGE TYPE: {message_type}",
        ]

        # Inject regression insights about what visual approaches work
        if generation_context:
            visual_context = []
            for rule in generation_context.winning_rules[:3]:
                if any(kw in rule.lower() for kw in ["visual", "image", "photo", "color", "style"]):
                    visual_context.append(f"  - WINNING: {rule}")
            for rule in generation_context.losing_rules[:2]:
                if any(kw in rule.lower() for kw in ["visual", "image", "photo", "color", "style"]):
                    visual_context.append(f"  - AVOID: {rule}")
            for warning in generation_context.fatigue_warnings[:2]:
                visual_context.append(f"  - FATIGUED: {warning}")

            if visual_context:
                parts.append("\nREGRESSION INSIGHTS (what visual approaches work):")
                parts.extend(visual_context)

        parts.append("\nWrite a scene description for this ad's background image.")

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=300,
                system=_SCENE_DIRECTOR_SYSTEM,
                messages=[{"role": "user", "content": "\n".join(parts)}],
            )
            scene = response.content[0].text.strip()

            # Safety: strip any accidental numbers/percentages Claude might include
            import re
            scene = re.sub(r'\d+%', '', scene)
            scene = re.sub(r'\b\d{1,2}:\d{2}\b', '', scene)  # times like 5:00
            scene = scene.replace('  ', ' ').strip()

            return scene

        except Exception as e:
            print(f"[scene_director] Claude call failed: {e}")
            return self._fallback_scene(hook_type)

    @staticmethod
    def _fallback_scene(hook_type: str) -> str:
        """Static fallback if Claude is unavailable."""
        fallbacks = {
            "statistic": (
                "Eye-level view of a therapist's wooden desk at golden hour. "
                "Closed laptop, organized notepad with a quality pen, small succulent plant. "
                "Warm home office with wooden furniture and soft curtains. "
                "Warm golden afternoon sun streaming through window. "
                "Peaceful, end-of-day calm."
            ),
            "question": (
                "Directly overhead flat-lay of a therapist's workspace. "
                "Open moleskine planner, reading glasses, ceramic coffee mug, a single houseplant leaf. "
                "Warm wooden desk surface, earth tones. "
                "Soft natural light from a nearby window. "
                "Contemplative, thoughtful, inviting."
            ),
            "testimonial": (
                "Wide angle of two comfortable therapy chairs facing each other in a warm room. "
                "Small private practice with bookshelf, soft lamp, plant on windowsill. "
                "Warm incandescent glow from a floor lamp, golden hour outside window. "
                "Safe, intimate, professional trust."
            ),
            "scenario": (
                "Empty therapist's office at twilight. "
                "Chairs slightly pushed back, a coat still hanging on the door hook. "
                "Soft twilight through venetian blinds creating stripe patterns. "
                "Peaceful emptiness, the day is done."
            ),
            "provocative_claim": (
                "Split frame composition. "
                "Left half cluttered desk buried in papers, coffee rings, scattered pens. "
                "Right half pristine minimalist desk with just a closed laptop. "
                "Harsh overhead fluorescent on left, warm natural light on right. "
                "Dramatic before-and-after contrast."
            ),
            "direct_benefit": (
                "Cozy reading nook next to a large window at dusk. "
                "An armchair with a reading lamp, a small stack of books, a throw blanket. "
                "Warm residential interior, lived-in and comfortable. "
                "Blue-hour light outside, warm lamp glow inside. "
                "Freedom, the workday ended early."
            ),
        }
        return fallbacks.get(hook_type, fallbacks["direct_benefit"])


# ---------------------------------------------------------------------------
# Image validation
# ---------------------------------------------------------------------------

def _validate_image(data: bytes, min_size: int = 50_000) -> tuple[bool, str]:
    """Validate generated image: magic bytes, file size, dimensions."""
    if len(data) < min_size:
        return False, f"Too small: {len(data)} bytes (min {min_size})"

    is_png = data[:8] == b'\x89PNG\r\n\x1a\n'
    is_jpeg = data[:2] == b'\xff\xd8'

    if not is_png and not is_jpeg:
        return False, f"Not a valid image (magic bytes: {data[:4].hex()})"

    if is_png and len(data) > 24:
        try:
            width = struct.unpack('>I', data[16:20])[0]
            height = struct.unpack('>I', data[20:24])[0]
            if width < 512 or height < 512:
                return False, f"Too small: {width}×{height} (min 512×512)"
        except struct.error:
            return False, "Could not read PNG dimensions"

    return True, "OK"


def _vision_quality_check(image_bytes: bytes) -> tuple[bool, str]:
    """
    Claude Vision quality gate — catches text, artifacts, nonsensical elements.
    Returns (passes, reason). ~$0.002 per check.
    """
    import base64
    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

        b64 = base64.b64encode(image_bytes).decode()

        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "You are a strict quality checker for ad background images. "
                            "These images will have text overlaid on them later, so the image "
                            "itself must be COMPLETELY free of any text or symbols.\n\n"
                            "REJECT the image if you see ANY of these:\n"
                            "1. ANY visible text, words, letters, numbers, or percentages — "
                            "even small, partial, blurry, or in the background (e.g., book spines "
                            "with titles, signs, labels, screen content)\n"
                            "2. Any clock face showing numbers or time\n"
                            "3. Distorted hands, fingers, or impossible anatomy\n"
                            "4. Watermarks, stock photo logos, or brand names\n"
                            "5. Objects that defy physics or look obviously AI-generated\n"
                            "6. Any screen, monitor, or device showing readable content\n\n"
                            "Respond with EXACTLY one line:\n"
                            "PASS - if the image contains zero text/numbers and looks natural\n"
                            "FAIL: <specific reason> - if ANY problem exists\n\n"
                            "Be extremely strict. When in doubt, FAIL."
                        ),
                    },
                ],
            }],
        )

        result = response.content[0].text.strip()
        if result.upper().startswith("PASS"):
            return True, "OK"
        else:
            reason = result.replace("FAIL:", "").replace("FAIL", "").strip()
            return False, reason or "Vision check failed"

    except Exception as e:
        print(f"[vision] Quality check error (allowing image): {e}")
        return True, f"Check skipped: {e}"


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

class AIImageGenerator:
    """
    Generate diverse ad background images using Claude + Gemini Imagen.

    Pipeline:
    1. SceneDirector (Claude) crafts a bespoke scene prompt from the ad's copy
    2. Imagen generates the photograph
    3. Vision gate (Claude) validates the output
    4. Playwright composites text on top via image_overlay template
    """

    def __init__(self, api_key: Optional[str] = None, model: str = "imagen-4.0-generate-001"):
        from google import genai
        self.api_key = api_key or os.environ.get("gemini_api", "")
        if not self.api_key:
            raise ValueError("Gemini API key required. Set gemini_api in .env or environment.")
        self.client = genai.Client(api_key=self.api_key)
        self.model = model
        self.scene_director = SceneDirector()
        self.output_dir = Path("data/creatives/rendered")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_background(
        self,
        headline: str = "",
        body: str = "",
        hook_type: str = "direct_benefit",
        tone: str = "warm",
        message_type: str = "value_prop",
        variant_index: int = 0,
        generation_context: "Optional[GenerationContext]" = None,
    ) -> Optional[str]:
        """
        Generate a single background image for an ad variant.

        Claude crafts the scene prompt, Imagen renders it, Vision validates.
        Returns path to saved PNG, or None on failure.
        """
        from google.genai import types

        # Step 1: Claude crafts the scene prompt
        scene = self.scene_director.craft_scene_prompt(
            headline=headline,
            body=body,
            hook_type=hook_type,
            tone=tone,
            message_type=message_type,
            generation_context=generation_context,
        )
        print(f"[scene_director] Scene for '{headline[:40]}...': {scene[:80]}...")

        # Step 2: Assemble full Imagen prompt
        full_prompt = _PHOTO_ANCHOR + scene + _COMPOSITION_SUFFIX + _NEGATIVE_SUFFIX

        # Step 3: Generate with Imagen
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
                print(f"[imagen] No images returned")
                return None

            img_bytes = response.generated_images[0].image.image_bytes

            # Step 4: Validate format
            is_valid, reason = _validate_image(img_bytes)
            if not is_valid:
                print(f"[imagen] Validation failed: {reason}")
                return None

            # Step 5: Vision quality gate
            vision_ok, vision_reason = _vision_quality_check(img_bytes)
            if not vision_ok:
                print(f"[vision] REJECTED: {vision_reason}")
                # Retry with a fresh Claude prompt (it'll generate a different scene)
                print(f"[imagen] Retrying with fresh scene...")
                return self._retry_once(headline, body, hook_type, tone, message_type, generation_context)

            # Save
            filename = f"ai_bg_{hook_type}_{uuid.uuid4().hex[:8]}.png"
            path = self.output_dir / filename
            path.write_bytes(img_bytes)
            print(f"[imagen] ✓ {len(img_bytes):,} bytes → {filename}")
            return str(path)

        except Exception as e:
            print(f"[imagen] Generation failed: {e}")
            return None

    def _retry_once(
        self,
        headline: str, body: str, hook_type: str,
        tone: str, message_type: str,
        generation_context: "Optional[GenerationContext]",
    ) -> Optional[str]:
        """Single retry with a fresh Claude-directed scene."""
        from google.genai import types

        scene = self.scene_director.craft_scene_prompt(
            headline=headline, body=body,
            hook_type=hook_type, tone=tone, message_type=message_type,
            generation_context=generation_context,
        )
        full_prompt = _PHOTO_ANCHOR + scene + _COMPOSITION_SUFFIX + _NEGATIVE_SUFFIX

        try:
            response = self.client.models.generate_images(
                model=self.model,
                prompt=full_prompt,
                config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="1:1"),
            )
            if not response.generated_images:
                return None

            img_bytes = response.generated_images[0].image.image_bytes
            is_valid, _ = _validate_image(img_bytes)
            if not is_valid:
                return None

            vision_ok, vision_reason = _vision_quality_check(img_bytes)
            if not vision_ok:
                print(f"[vision] Retry also rejected: {vision_reason}")
                return None

            filename = f"ai_bg_{hook_type}_{uuid.uuid4().hex[:8]}.png"
            path = self.output_dir / filename
            path.write_bytes(img_bytes)
            print(f"[imagen] ✓ Retry succeeded: {len(img_bytes):,} bytes → {filename}")
            return str(path)
        except Exception as e:
            print(f"[imagen] Retry failed: {e}")
            return None

    def generate_batch(
        self,
        variants: list[dict],
        generation_context: "Optional[GenerationContext]" = None,
        max_images: int = 12,
    ) -> list[Optional[str]]:
        """
        Generate background images for a batch of variants.

        Each variant dict should have: headline, body/primary_text, taxonomy.
        Claude crafts a unique scene for each.
        """
        results: list[Optional[str]] = []

        for i, v in enumerate(variants):
            if i >= max_images:
                # Reuse from earlier in the batch
                if results:
                    results.append(results[i % len([r for r in results if r])] if any(results) else None)
                else:
                    results.append(None)
                continue

            tax = v.get("taxonomy", {})
            headline = v.get("headline", "")
            body = v.get("primary_text", v.get("body", ""))

            path = self.generate_background(
                headline=headline,
                body=body,
                hook_type=tax.get("hook_type", "direct_benefit"),
                tone=tax.get("tone", "warm"),
                message_type=tax.get("message_type", "value_prop"),
                variant_index=i,
                generation_context=generation_context,
            )
            results.append(path)

            status = "✓" if path else "✗ (will use template fallback)"
            print(f"[imagen] [{i+1}/{min(len(variants), max_images)}] {status}")

        return results
