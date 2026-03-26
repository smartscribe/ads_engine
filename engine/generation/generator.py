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


COPY_GENERATION_PROMPT = """You are a direct-response copywriter for JotPsych, a clinical AI documentation tool for behavioral health clinicians.

JotPsych listens to therapy sessions and generates complete, audit-ready clinical notes automatically — with CPT and ICD codes applied. It saves clinicians 1-2 hours of documentation per day so they can be fully present with patients and leave on time.

Given a creative brief, generate {num_variants} distinct ad copy variants.
Each variant must be meaningfully different — not just word swaps. Vary the:
- Hook (how it opens)
- Message angle (what benefit/pain it leads with)
- Tone (within the brief's direction)
- CTA phrasing

BRAND VOICE: Warm but professional — like a trusted colleague, not a salesperson. Empathetic to clinician burnout. Specific and concrete ("2 hours of charting" not "save time"). Confident without being pushy.

NEVER USE: "revolutionize", "leverage", "streamline", "cutting-edge", "innovative", "powered by AI", "next-generation", "transform your workflow", "in today's fast-paced world", "limited time", "don't miss out".

Write like a human copywriter who has talked to 100 burned-out therapists. Be specific. Be real.

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
        retry_count: int = 0,
    ) -> bool:
        """
        Generate a single image via Gemini. Returns True on success.
        
        Validates:
        - MIME type is image/png or image/jpeg
        - File size is > 10KB (real images are typically 50KB+)
        
        Retries once with simplified prompt on failure.
        """
        from engine.generation.scene_library import match_scene
        
        taxonomy = variant.get("taxonomy", {})
        
        # Match a scene based on taxonomy
        scene = match_scene(
            message_type=taxonomy.get("message_type"),
            hook_type=taxonomy.get("hook_type"),
            subject_matter=taxonomy.get("subject_matter"),
            tone=taxonomy.get("tone"),
            is_video=False,
        )
        
        # Build the prompt using scene library
        prompt = self._build_image_prompt(variant, brief, scene)
        
        try:
            response = gemini.models.generate_content(
                model="gemini-3.1-flash-image-preview",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )
            
            if not response.candidates or not response.candidates[0].content.parts:
                print(f"[generator] No candidates in response for image")
                return self._retry_image_if_needed(gemini, variant, brief, out_path, retry_count)
            
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    # Validate MIME type
                    mime_type = getattr(part.inline_data, 'mime_type', None)
                    if mime_type and mime_type not in ['image/png', 'image/jpeg', 'image/jpg']:
                        print(f"[generator] Invalid MIME type: {mime_type}")
                        return self._retry_image_if_needed(gemini, variant, brief, out_path, retry_count)
                    
                    # Decode the data - handle both base64 string and raw bytes
                    data = part.inline_data.data
                    if isinstance(data, str):
                        image_bytes = base64.b64decode(data)
                    else:
                        image_bytes = bytes(data)
                    
                    # Validate size (> 10KB for a real image)
                    if len(image_bytes) < 10240:
                        print(f"[generator] Image too small ({len(image_bytes)} bytes), likely corrupt")
                        return self._retry_image_if_needed(gemini, variant, brief, out_path, retry_count)
                    
                    # Validate PNG/JPEG magic bytes
                    is_png = image_bytes[:8] == b'\x89PNG\r\n\x1a\n'
                    is_jpeg = image_bytes[:2] == b'\xff\xd8'
                    if not (is_png or is_jpeg):
                        print(f"[generator] Invalid image magic bytes (not PNG or JPEG)")
                        return self._retry_image_if_needed(gemini, variant, brief, out_path, retry_count)
                    
                    # Write the validated image
                    out_path.write_bytes(image_bytes)
                    print(f"[generator] Image saved: {out_path} ({len(image_bytes)} bytes)")
                    return True
                    
            print(f"[generator] No inline_data in response parts")
            return self._retry_image_if_needed(gemini, variant, brief, out_path, retry_count)
            
        except Exception as e:
            print(f"[generator] Image generation error: {e}")
            return self._retry_image_if_needed(gemini, variant, brief, out_path, retry_count)
    
    def _retry_image_if_needed(
        self,
        gemini: genai.Client,
        variant: dict,
        brief: CreativeBrief,
        out_path: Path,
        retry_count: int,
    ) -> bool:
        """Retry image generation with simplified prompt if we haven't already."""
        if retry_count >= 1:
            print(f"[generator] Image generation failed after retry")
            return False
        
        print(f"[generator] Retrying image generation with simplified prompt...")
        # For retry, use a simpler, more reliable scene
        variant_copy = variant.copy()
        variant_copy["taxonomy"] = {
            "message_type": "value_prop",
            "subject_matter": "clinician_at_work",
            "tone": "warm",
        }
        return self._generate_image(gemini, variant_copy, brief, out_path, retry_count + 1)
    
    def _build_image_prompt(self, variant: dict, brief: CreativeBrief, scene) -> str:
        """Build a detailed image prompt using the scene library + brand config."""
        from engine.brand import get_brand_context_for_image_prompt
        brand_visual = get_brand_context_for_image_prompt()

        return f"""Generate a photorealistic advertising image for JotPsych, a clinical AI documentation tool for behavioral health clinicians.

SCENE DESCRIPTION (follow exactly):
{scene.description}

AD CONTEXT (for emotional accuracy, do NOT display as text):
- Headline message: {variant.get("headline", "")}
- Value proposition: {brief.value_proposition}
- Emotional tone: {scene.tone}

{brand_visual}

TECHNICAL REQUIREMENTS:
- Photorealistic, cinematic quality photography
- 1:1 square aspect ratio (1024x1024)
- No text, no logos, no watermarks, no UI elements overlaid on image
- Natural lighting consistent with {scene.time_of_day} time of day
- Color grading should lean warm — amber, cream, soft blues, touch of pink
- Environments should feel real and lived-in, not sterile or corporate

CRITICAL NEGATIVE PROMPTS - AVOID THESE:
{scene.negative_prompt}
- No AI-obvious artifacts, uncanny valley faces, distorted hands
- No generic stock photo poses or expressions
- No impossible anatomy or physics
- No floating objects or impossible shadows
- No text of any kind in the image
- No cold grey corporate offices or harsh fluorescent-only lighting"""

    def _generate_video(
        self,
        gemini: genai.Client,
        variant: dict,
        brief: CreativeBrief,
        out_path: Path,
        retry_count: int = 0,
    ) -> bool:
        """
        Generate a single video via Veo. Returns True on success.
        
        Validates:
        - File size is > 100KB (real videos are much larger)
        - Content starts with valid video container magic bytes
        
        Retries once with simplified prompt on failure.
        """
        from engine.generation.scene_library import match_scene
        
        settings = get_settings()
        taxonomy = variant.get("taxonomy", {})
        
        # Match a video-specific scene based on taxonomy
        scene = match_scene(
            message_type=taxonomy.get("message_type"),
            hook_type=taxonomy.get("hook_type"),
            subject_matter=taxonomy.get("subject_matter"),
            tone=taxonomy.get("tone"),
            is_video=True,
        )
        
        # Build the prompt using scene library
        prompt = self._build_video_prompt(variant, brief, scene)
        
        try:
            operation = gemini.models.generate_videos(
                model="veo-3.0-fast-generate-001",
                prompt=prompt,
                config=genai_types.GenerateVideosConfig(
                    aspectRatio="9:16",
                    numberOfVideos=1,
                ),
            )
            
            # Poll until done (Veo jobs take ~60–120s)
            poll_count = 0
            max_polls = 30  # 5 minutes max
            while not operation.done and poll_count < max_polls:
                time.sleep(10)
                operation = gemini.operations.get(operation)
                poll_count += 1
                print(f"[generator] Video generation polling... ({poll_count * 10}s)")
            
            if not operation.done:
                print(f"[generator] Video generation timed out after {poll_count * 10}s")
                return self._retry_video_if_needed(gemini, variant, brief, out_path, retry_count)

            videos = operation.response or operation.result
            generated = getattr(videos, "generated_videos", None) or []
            if not generated:
                print(f"[generator] No generated videos in response")
                return self._retry_video_if_needed(gemini, variant, brief, out_path, retry_count)

            video = generated[0].video
            video_bytes = None
            
            if video.video_bytes:
                video_bytes = video.video_bytes
            elif video.uri:
                # Veo returns a download URI — fetch it with the API key
                resp = requests.get(video.uri, params={"key": settings.gemini_api}, timeout=120)
                resp.raise_for_status()
                video_bytes = resp.content
            
            if not video_bytes:
                print(f"[generator] No video bytes obtained")
                return self._retry_video_if_needed(gemini, variant, brief, out_path, retry_count)
            
            # Validate size (> 100KB for a real video)
            if len(video_bytes) < 102400:
                print(f"[generator] Video too small ({len(video_bytes)} bytes), likely corrupt")
                return self._retry_video_if_needed(gemini, variant, brief, out_path, retry_count)
            
            # Write the validated video
            out_path.write_bytes(video_bytes)
            print(f"[generator] Video saved: {out_path} ({len(video_bytes)} bytes)")
            return True
            
        except Exception as e:
            print(f"[generator] Video generation error: {e}")
            return self._retry_video_if_needed(gemini, variant, brief, out_path, retry_count)
    
    def _retry_video_if_needed(
        self,
        gemini: genai.Client,
        variant: dict,
        brief: CreativeBrief,
        out_path: Path,
        retry_count: int,
    ) -> bool:
        """Retry video generation with simplified prompt if we haven't already."""
        if retry_count >= 1:
            print(f"[generator] Video generation failed after retry")
            return False
        
        print(f"[generator] Retrying video generation with simplified prompt...")
        # For retry, use a simpler, more reliable scene
        variant_copy = variant.copy()
        variant_copy["taxonomy"] = {
            "message_type": "value_prop",
            "subject_matter": "clinician_at_work",
            "tone": "warm",
        }
        return self._generate_video(gemini, variant_copy, brief, out_path, retry_count + 1)
    
    def _build_video_prompt(self, variant: dict, brief: CreativeBrief, scene) -> str:
        """Build a detailed video prompt using the scene library + brand config."""
        from engine.brand import get_brand_context_for_image_prompt
        brand_visual = get_brand_context_for_image_prompt()

        return f"""Generate a 5-second photorealistic advertising video for JotPsych, a clinical AI documentation tool for behavioral health clinicians.

SCENE DESCRIPTION (follow exactly):
{scene.description}

AD CONTEXT (for emotional accuracy, do NOT display as text):
- Headline message: {variant.get("headline", "")}
- Value proposition: {brief.value_proposition}
- Emotional tone: {scene.tone}

{brand_visual}

TECHNICAL REQUIREMENTS:
- Photorealistic, cinematic quality video
- 9:16 vertical aspect ratio (1080x1920) for mobile feed
- 5 seconds duration
- Natural, documentary-style motion - not slow motion unless specified
- No text, no logos, no watermarks, no UI overlays
- Natural lighting consistent with {scene.time_of_day} time of day
- Natural camera movement if any (gentle pan, slight handheld feel)
- Natural sound design appropriate to the scene
- Color grading should lean warm — amber, cream, soft blues, touch of pink

CRITICAL NEGATIVE PROMPTS - AVOID THESE:
{scene.negative_prompt}
- No AI-obvious artifacts, uncanny valley faces, distorted hands
- No glitchy transitions or impossible physics
- No floating objects or impossible camera movements
- No text of any kind in the video
- No cold grey corporate offices or harsh fluorescent-only lighting"""

    def generate_assets(
        self,
        brief: CreativeBrief,
        copy_variants: list[dict],
        force_regenerate: bool = False,
    ) -> list[str]:
        """
        Generate visual assets using Gemini (images) and Veo (video).

        Images  → gemini-2.0-flash-exp → .png
        Videos  → veo-3.0-fast-generate-001 → .mp4

        Saves to data/creatives/{brief_id}/ and returns file paths.
        
        Args:
            brief: The creative brief
            copy_variants: List of copy variant dicts with taxonomy
            force_regenerate: If True, deletes existing corrupt files and regenerates
        
        Returns:
            List of asset file paths
        """
        settings = get_settings()
        out_dir = Path("data/creatives") / brief.id
        out_dir.mkdir(parents=True, exist_ok=True)

        if not settings.gemini_api:
            return [str(out_dir / f"variant_{i}.placeholder") for i in range(len(copy_variants))]

        gemini = genai.Client(api_key=settings.gemini_api)
        asset_paths = []

        for i, variant in enumerate(copy_variants):
            # Alternate: even-indexed variants → image, odd → video
            is_video = (i % 2 == 1)

            ext = "mp4" if is_video else "png"
            out_path = out_dir / f"variant_{i}.{ext}"

            # Check if existing file is corrupt (< 10KB for images, < 100KB for videos)
            needs_generation = False
            if out_path.exists():
                file_size = out_path.stat().st_size
                min_size = 102400 if is_video else 10240  # 100KB for video, 10KB for image
                
                if file_size < min_size:
                    if force_regenerate:
                        print(f"[generator] Deleting corrupt file: {out_path} ({file_size} bytes)")
                        out_path.unlink()
                        needs_generation = True
                    else:
                        print(f"[generator] Skipping corrupt file (use force_regenerate=True): {out_path}")
                        asset_paths.append(str(out_path))
                        continue
                else:
                    # File exists and is valid
                    asset_paths.append(str(out_path))
                    continue
            else:
                needs_generation = True

            if needs_generation:
                try:
                    if is_video:
                        success = self._generate_video(gemini, variant, brief, out_path)
                    else:
                        success = self._generate_image(gemini, variant, brief, out_path)

                    if not success:
                        print(f"[generator] No output from API for variant {i}")
                        # Create placeholder file
                        placeholder_path = out_dir / f"variant_{i}.placeholder"
                        placeholder_path.touch()
                        out_path = placeholder_path
                except Exception as e:
                    print(f"[generator] Asset generation failed for variant {i}: {e}")
                    # Create placeholder file
                    placeholder_path = out_dir / f"variant_{i}.placeholder"
                    placeholder_path.touch()
                    out_path = placeholder_path

            asset_paths.append(str(out_path))

        return asset_paths

    def generate_copy_v2(
        self,
        brief: CreativeBrief,
        store=None,
        top_patterns: list = None,
        rejection_feedback: list = None,
        approval_feedback: list = None,
    ) -> list[dict]:
        """
        Enhanced copy generation using specialized sub-agents + quality filter + variant matrix.
        Falls back to generate_copy() if sub-agents produce insufficient output.
        """
        from engine.generation.copy_agents import HeadlineAgent, BodyCopyAgent, CTAAgent
        from engine.generation.quality_filter import CopyQualityFilter
        from engine.generation.variant_matrix import VariantMatrix

        headline_agent = HeadlineAgent(self.client)
        body_agent = BodyCopyAgent(self.client)
        cta_agent = CTAAgent(self.client)
        quality_filter = CopyQualityFilter()

        headlines = headline_agent.generate(
            brief, n=10, top_patterns=top_patterns,
            rejection_feedback=rejection_feedback, approval_feedback=approval_feedback,
        )
        bodies = body_agent.generate(
            brief, n=5, top_patterns=top_patterns,
            rejection_feedback=rejection_feedback, approval_feedback=approval_feedback,
        )
        ctas = cta_agent.generate(brief, n=5)

        headlines = quality_filter.filter_headlines(headlines)
        bodies = quality_filter.filter_bodies(bodies)
        ctas = quality_filter.filter_ctas(ctas)

        if not headlines or not bodies or not ctas:
            print("[generator] Sub-agents produced insufficient output after filtering, falling back to v1")
            return self.generate_copy(brief)

        if store:
            matrix = VariantMatrix(store)
            selected = matrix.generate_scored_matrix(headlines, bodies, ctas, brief)
        else:
            import itertools, random
            all_combos = list(itertools.product(headlines, bodies, ctas))
            random.shuffle(all_combos)
            selected = [
                {"headline": c[0], "body": c[1], "cta": c[2], "predicted_score": None}
                for c in all_combos[: brief.num_variants]
            ]

        result = []
        for s in selected:
            h = s["headline"]
            b = s["body"]
            result.append({
                "headline": h["text"],
                "primary_text": b["text"],
                "description": "",
                "cta_button": s["cta"],
                "taxonomy": {
                    "message_type": b.get("message_type", "value_prop"),
                    "hook_type": h.get("hook_type", "direct_benefit"),
                    "cta_type": s["cta"].lower().replace(" ", "_"),
                    "tone": b.get("tone", "warm"),
                    "visual_style": "photography",
                    "subject_matter": "clinician_at_work",
                    "color_mood": "brand_primary",
                    "text_density": "headline_subhead",
                    "headline_word_count": len(h["text"].split()),
                    "uses_number": any(c.isdigit() for c in h["text"] + b["text"]),
                    "uses_question": "?" in h["text"],
                    "uses_first_person": any(
                        w in (h["text"] + " " + b["text"]).lower().split()
                        for w in ["i", "my", "me"]
                    ),
                    "uses_social_proof": b.get("message_type") == "social_proof",
                    "copy_reading_level": 8.0,
                },
                "predicted_score": s.get("predicted_score"),
            })

        return result

    def generate(
        self,
        brief: CreativeBrief,
        use_v2: bool = False,
        store=None,
        top_patterns: list = None,
        rejection_feedback: list = None,
        approval_feedback: list = None,
    ) -> list[AdVariant]:
        """Full generation pipeline: copy → assets → tagged variants."""

        if use_v2:
            copy_variants = self.generate_copy_v2(
                brief, store=store,
                top_patterns=top_patterns,
                rejection_feedback=rejection_feedback,
                approval_feedback=approval_feedback,
            )
        else:
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
