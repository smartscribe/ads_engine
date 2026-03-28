"""
Creative Generator — takes briefs, produces ad variants with auto-taxonomy tagging.

All ad images are rendered deterministically via Playwright (HTML templates → PNG).
Copy generation uses Claude sub-agents. No AI image/video generation.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from anthropic import Anthropic

from config.settings import get_settings
from engine.models import (
    CreativeBrief,
    AdVariant,
    CreativeTaxonomy,
    AdFormat,
    AdStatus,
)


COPY_GENERATION_PROMPT = """You are a direct-response copywriter for JotPsych, a clinical AI documentation tool for behavioral health clinicians.

JotPsych listens to therapy sessions and generates complete, audit-ready clinical notes automatically, with CPT and ICD codes applied. It saves clinicians 1-2 hours of documentation per day so they can be fully present with patients and leave on time.

Given a creative brief, generate {num_variants} distinct ad copy variants.
Each variant must be meaningfully different, not just word swaps. Vary the:
- Hook (how it opens)
- Message angle (what benefit/pain it leads with)
- Tone (within the brief's direction)
- CTA phrasing

BRAND VOICE: Warm but professional, like a trusted colleague, not a salesperson. Empathetic to clinician burnout. Specific and concrete ("2 hours of charting" not "save time"). Confident without being pushy.

NEVER USE: em dashes (use periods, commas, or colons instead), "revolutionize", "leverage", "streamline", "cutting-edge", "innovative", "powered by AI", "next-generation", "transform your workflow", "in today's fast-paced world", "limited time", "don't miss out".

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


# ---------------------------------------------------------------------------
# Visual taxonomy assignment — maps copy attributes to visual dimensions
# so every variant gets a distinct look instead of identical styling.
# ---------------------------------------------------------------------------

# Hook type → preferred visual style + subject matter
_HOOK_VISUAL_MAP = {
    "statistic":         {"visual_style": "text_heavy",    "subject_matter": "data_viz"},
    "testimonial":       {"visual_style": "photography",   "subject_matter": "clinician_at_work"},
    "scenario":          {"visual_style": "photography",   "subject_matter": "patient_interaction"},
    "question":          {"visual_style": "mixed_media",   "subject_matter": "conceptual"},
    "provocative_claim": {"visual_style": "text_heavy",    "subject_matter": "workflow_comparison"},
    "direct_benefit":    {"visual_style": "screen_capture", "subject_matter": "product_ui"},
}

# All valid color moods — rotated round-robin across the batch
_COLOR_MOOD_ROTATION = [
    "brand_primary", "high_contrast", "warm_earth",
    "cool_clinical", "bold_saturated", "muted_soft",
]

# Secondary visual_style options for additional diversity when same hook
# type appears multiple times
_VISUAL_STYLE_ALTERNATES = {
    "text_heavy":    ["mixed_media", "screen_capture", "photography"],
    "photography":   ["mixed_media", "screen_capture", "text_heavy"],
    "mixed_media":   ["photography", "text_heavy", "screen_capture"],
    "screen_capture": ["photography", "mixed_media", "text_heavy"],
}

# Secondary subject_matter options for rotation
_SUBJECT_ALTERNATES = {
    "data_viz":             ["product_ui", "workflow_comparison", "conceptual"],
    "clinician_at_work":    ["patient_interaction", "product_ui", "conceptual"],
    "patient_interaction":  ["clinician_at_work", "conceptual", "product_ui"],
    "conceptual":           ["clinician_at_work", "data_viz", "workflow_comparison"],
    "workflow_comparison":  ["product_ui", "data_viz", "conceptual"],
    "product_ui":           ["workflow_comparison", "clinician_at_work", "data_viz"],
}


def _assign_visual_taxonomy(
    hook_type: str,
    message_type: str,
    tone: str,
    primary_text: str,
    index: int,
    batch_size: int,
    seen_styles: dict | None = None,
) -> dict:
    """
    Assign visual taxonomy fields based on copy attributes + batch position.

    Instead of hardcoding every variant to photography/brand_primary, this:
    1. Maps hook_type → base visual_style + subject_matter
    2. Rotates color_mood round-robin across the batch
    3. When the same hook_type appears multiple times, cycles through
       alternate visual styles so no two variants look identical
    4. Derives text_density from actual copy length
    """
    # Base mapping from hook type
    base = _HOOK_VISUAL_MAP.get(hook_type, {"visual_style": "photography", "subject_matter": "clinician_at_work"})
    visual_style = base["visual_style"]
    subject_matter = base["subject_matter"]

    # If we've seen this visual_style before in the batch, rotate to an alternate
    if seen_styles is not None:
        style_count = seen_styles.get(visual_style, 0)
        if style_count > 0:
            alts = _VISUAL_STYLE_ALTERNATES.get(visual_style, [])
            if alts:
                visual_style = alts[(style_count - 1) % len(alts)]
            sub_alts = _SUBJECT_ALTERNATES.get(subject_matter, [])
            if sub_alts:
                subject_matter = sub_alts[(style_count - 1) % len(sub_alts)]

    # Rotate color_mood across the batch
    color_mood = _COLOR_MOOD_ROTATION[index % len(_COLOR_MOOD_ROTATION)]

    # Derive text_density from actual copy length
    text_len = len(primary_text)
    if text_len < 80:
        text_density = "headline_only"
    elif text_len < 150:
        text_density = "headline_subhead"
    elif text_len < 250:
        text_density = "detailed_copy"
    else:
        text_density = "detailed_copy"

    return {
        "visual_style": visual_style,
        "subject_matter": subject_matter,
        "color_mood": color_mood,
        "text_density": text_density,
    }


class CreativeGenerator:
    """
    Generates ad variants from creative briefs.

    Copy generation uses Claude. Images rendered via Playwright (HTML templates → PNG).
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

    def generate_copy_v2(
        self,
        brief: CreativeBrief,
        store=None,
        top_patterns: list = None,
        rejection_feedback: list = None,
        approval_feedback: list = None,
        memory=None,
        generation_context=None,
    ) -> list[dict]:
        """
        Enhanced copy generation using specialized sub-agents + quality filter + variant matrix.
        Falls back to generate_copy() if sub-agents produce insufficient output.
        
        If generation_context is provided (v2), uses the structured three-layer memory.
        If memory is provided (v1), uses the legacy CreativeMemory format.
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
            memory=memory, generation_context=generation_context,
        )
        bodies = body_agent.generate(
            brief, n=5, top_patterns=top_patterns,
            rejection_feedback=rejection_feedback, approval_feedback=approval_feedback,
            memory=memory, generation_context=generation_context,
        )
        ctas = cta_agent.generate(brief, n=5, generation_context=generation_context)

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
        seen_styles: dict[str, int] = {}  # track visual_style usage for rotation
        batch_size = len(selected)

        for i, s in enumerate(selected):
            h = s["headline"]
            b = s["body"]

            hook_type = h.get("hook_type", "direct_benefit")
            message_type = b.get("message_type", "value_prop")
            tone = b.get("tone", "warm")

            # Assign diverse visual taxonomy instead of hardcoding
            visual_tax = _assign_visual_taxonomy(
                hook_type=hook_type,
                message_type=message_type,
                tone=tone,
                primary_text=b["text"],
                index=i,
                batch_size=batch_size,
                seen_styles=seen_styles,
            )
            # Track usage for next iteration's rotation
            seen_styles[visual_tax["visual_style"]] = seen_styles.get(visual_tax["visual_style"], 0) + 1

            result.append({
                "headline": h["text"],
                "primary_text": b["text"],
                "description": "",
                "cta_button": s["cta"],
                "taxonomy": {
                    "message_type": message_type,
                    "hook_type": hook_type,
                    "cta_type": s["cta"].lower().replace(" ", "_"),
                    "tone": tone,
                    "visual_style": visual_tax["visual_style"],
                    "subject_matter": visual_tax["subject_matter"],
                    "color_mood": visual_tax["color_mood"],
                    "text_density": visual_tax["text_density"],
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
        use_v2: bool = True,
        store=None,
        top_patterns: list = None,
        rejection_feedback: list = None,
        approval_feedback: list = None,
        memory=None,
        generation_context=None,
    ) -> list[AdVariant]:
        """Full generation pipeline: copy → template render → tagged variants."""
        return self.generate_with_templates(
            brief,
            use_v2=use_v2,
            store=store,
            top_patterns=top_patterns,
            rejection_feedback=rejection_feedback,
            approval_feedback=approval_feedback,
            memory=memory,
            generation_context=generation_context,
        )

    def _generate_ai_backgrounds(
        self,
        copy_variants: list[dict],
        plans: list,
        generation_context=None,
    ) -> dict[int, str]:
        """
        Generate AI background images for variants using the image_overlay template.

        Uses Claude SceneDirector to craft bespoke Imagen prompts per ad — each
        scene is tailored to the ad's headline, body, hook type, and tone.
        Regression insights from generation_context influence visual direction.

        Returns a dict mapping variant index → background image path.
        """
        overlay_indices = [
            i for i, plan in enumerate(plans)
            if plan.template == "feed_1080x1080/image_overlay"
        ]

        if not overlay_indices:
            return {}

        try:
            from engine.generation.image_generator import AIImageGenerator
            ai_gen = AIImageGenerator()
        except Exception as e:
            print(f"[generator] AI image generator unavailable: {e}")
            for i in overlay_indices:
                plans[i].template = "feed_1080x1080/headline_hero"
            return {}

        # Build variant dicts with full copy + taxonomy for Claude SceneDirector
        overlay_variants = [
            {
                "headline": copy_variants[i].get("headline", ""),
                "primary_text": copy_variants[i].get("primary_text", ""),
                "taxonomy": copy_variants[i].get("taxonomy", {}),
            }
            for i in overlay_indices
        ]

        print(f"[generator] Generating {len(overlay_variants)} AI backgrounds (Claude-directed)...")
        paths = ai_gen.generate_batch(
            overlay_variants,
            generation_context=generation_context,
            max_images=len(overlay_variants),
        )

        result = {}
        for overlay_idx, path in zip(overlay_indices, paths):
            if path:
                result[overlay_idx] = path
            else:
                plans[overlay_idx].template = "feed_1080x1080/headline_hero"

        return result

    def generate_assets_from_template(
        self,
        brief: CreativeBrief,
        copy_variants: list[dict],
        template: str = "meta_feed",
        color_scheme: str = "light",
    ) -> list[str]:
        """
        Generate ad images using HTML/CSS templates instead of AI.
        
        This produces pixel-perfect, brand-consistent images using the brand kit
        colors and fonts. No AI generation — full control over every pixel.
        
        Args:
            brief: The creative brief
            copy_variants: List of dicts with headline, primary_text, cta_button
            template: Template name (meta_feed, meta_story, google_300x250, etc.)
            color_scheme: Color scheme (light, dark, warm, accent)
            
        Returns:
            List of paths to rendered PNG files
        """
        from engine.generation.template_renderer import TemplateRenderer
        
        renderer = TemplateRenderer()
        
        render_variants = [
            {
                "headline": v.get("headline", ""),
                "body": v.get("primary_text", ""),
                "cta": v.get("cta_button", "Learn More"),
            }
            for v in copy_variants
        ]
        
        paths = renderer.render_batch(render_variants, template, color_scheme)
        
        return paths

    def generate_assets_from_selector(
        self,
        brief: CreativeBrief,
        copy_variants: list[dict],
        store=None,
        generation_context=None,
    ) -> list[tuple[str, "TemplatePlan"]]:
        """
        Generate ad images using the TemplateSelector to pick per-variant
        template + color scheme based on taxonomy tags and regression data.
        All assets rendered as PNG via Playwright.

        Returns:
            List of (asset_path, TemplatePlan) tuples so callers can store
            the template_id and color_scheme on the AdVariant.
        """
        from engine.generation.template_renderer import TemplateRenderer
        from engine.generation.template_selector import TemplateSelector, TemplatePlan

        selector = TemplateSelector()
        renderer = TemplateRenderer()

        regression = store.get_latest_regression() if store else None

        ad_format = brief.formats_requested[0] if brief.formats_requested else AdFormat.SINGLE_IMAGE
        platform = brief.platforms[0] if brief.platforms else None

        plans = selector.select_batch(
            copy_variants,
            regression=regression,
            ad_format=ad_format,
            platform=platform,
            diversify=True,
        )

        # Generate AI background images for variants using image_overlay template
        # Claude SceneDirector uses generation_context for regression-informed visual direction
        ai_backgrounds = self._generate_ai_backgrounds(copy_variants, plans, generation_context)

        results = []
        for i, (variant, plan) in enumerate(zip(copy_variants, plans)):
            headline = variant.get("headline", "")
            body = variant.get("primary_text", "")
            cta = variant.get("cta_button", "Learn More")

            # If this variant uses image_overlay, inject the AI background
            context = dict(plan.context) if plan.context else {}
            if plan.template == "feed_1080x1080/image_overlay" and ai_backgrounds.get(i):
                bg_path = Path(ai_backgrounds[i]).resolve()
                context["background_image"] = f"file://{bg_path}"

            try:
                path = renderer.render(
                    headline=headline,
                    body=body,
                    cta=cta,
                    template=plan.template,
                    color_scheme=plan.color_scheme,
                    context=context,
                )
                results.append((path, plan))
            except Exception as e:
                print(f"[generator] Template render failed ({plan.template}): {e}")
                fallback_plan = TemplatePlan(
                    template="feed_1080x1080/headline_hero",
                    color_scheme="light",
                    format=plan.format,
                )
                try:
                    path = renderer.render(
                        headline=headline, body=body, cta=cta,
                        template=fallback_plan.template,
                        color_scheme=fallback_plan.color_scheme,
                    )
                    results.append((path, fallback_plan))
                except Exception as e2:
                    print(f"[generator] Fallback render also failed: {e2}")
                    placeholder = Path("data/creatives/rendered") / f"failed_{variant.get('headline', 'unknown')[:20]}.placeholder"
                    placeholder.parent.mkdir(parents=True, exist_ok=True)
                    placeholder.touch()
                    results.append((str(placeholder), fallback_plan))

        return results

    def generate_with_templates(
        self,
        brief: CreativeBrief,
        use_v2: bool = True,
        store=None,
        top_patterns: list = None,
        rejection_feedback: list = None,
        approval_feedback: list = None,
        memory=None,
        generation_context=None,
        template: str = "meta_feed",
        color_scheme: str = "light",
        use_selector: bool = False,
    ) -> list[AdVariant]:
        """
        Full generation pipeline using HTML templates for images.
        
        When use_selector=True, the TemplateSelector picks per-variant template
        and color scheme based on taxonomy tags and regression coefficients.
        When False, uses the single template/color_scheme for all variants
        (backward compatible behavior).
        """
        if use_v2:
            copy_variants = self.generate_copy_v2(
                brief, store=store,
                top_patterns=top_patterns,
                rejection_feedback=rejection_feedback,
                approval_feedback=approval_feedback,
                memory=memory,
                generation_context=generation_context,
            )
        else:
            copy_variants = self.generate_copy(brief)

        # Generate assets — selector returns (path, plan) tuples; flat returns paths
        asset_results = []
        if use_selector:
            selector_results = self.generate_assets_from_selector(
                brief, copy_variants, store=store,
                generation_context=generation_context,
            )
            asset_results = selector_results  # list of (path, TemplatePlan)
        else:
            flat_paths = self.generate_assets_from_template(
                brief, copy_variants, template, color_scheme
            )
            asset_results = [(p, None) for p in flat_paths]  # no plan info

        deployment_targets = [
            {"format": fmt.value, "platform": p.value}
            for fmt in brief.formats_requested
            for p in brief.platforms
        ]

        primary_fmt = brief.formats_requested[0] if brief.formats_requested else AdFormat.SINGLE_IMAGE
        primary_platform = brief.platforms[0] if brief.platforms else Platform.META

        variants = []
        for copy_data, (asset_path, plan) in zip(copy_variants, asset_results):
            tax_data = copy_data["taxonomy"]

            # Determine asset_source for regression tracking
            is_ai = plan and plan.template == "feed_1080x1080/image_overlay"
            asset_source = "ai_generated" if is_ai else "template"

            taxonomy = CreativeTaxonomy(
                **tax_data,
                format=primary_fmt,
                platform=primary_platform,
                placement="feed",
                asset_source=asset_source,
            )

            variant = AdVariant(
                brief_id=brief.id,
                headline=copy_data["headline"],
                primary_text=copy_data["primary_text"],
                description=copy_data.get("description", ""),
                cta_button=copy_data.get("cta_button", "Learn More"),
                asset_path=asset_path,
                asset_type="image",
                taxonomy=taxonomy,
                status=AdStatus.DRAFT,
                deployment_targets=deployment_targets,
                template_id=plan.template if plan else template,
                template_color_scheme=plan.color_scheme if plan else color_scheme,
            )
            variants.append(variant)

        return variants
