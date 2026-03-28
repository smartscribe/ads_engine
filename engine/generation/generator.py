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
    ) -> list[str]:
        """
        Generate ad images using the TemplateSelector to pick per-variant
        template + color scheme based on taxonomy tags and regression data.
        All assets rendered as PNG via Playwright.

        Returns:
            List of asset file paths (.png only)
        """
        from engine.generation.template_renderer import TemplateRenderer
        from engine.generation.template_selector import TemplateSelector

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

        asset_paths = []
        for variant, plan in zip(copy_variants, plans):
            headline = variant.get("headline", "")
            body = variant.get("primary_text", "")
            cta = variant.get("cta_button", "Learn More")

            try:
                path = renderer.render(
                    headline=headline,
                    body=body,
                    cta=cta,
                    template=plan.template,
                    color_scheme=plan.color_scheme,
                    context=plan.context,
                )
                asset_paths.append(path)
            except Exception as e:
                print(f"[generator] Template render failed ({plan.template}): {e}")
                try:
                    path = renderer.render(
                        headline=headline, body=body, cta=cta,
                        template="feed_1080x1080/headline_hero",
                        color_scheme="light",
                    )
                    asset_paths.append(path)
                except Exception as e2:
                    print(f"[generator] Fallback render also failed: {e2}")
                    placeholder = Path("data/creatives/rendered") / f"failed_{variant.get('headline', 'unknown')[:20]}.placeholder"
                    placeholder.parent.mkdir(parents=True, exist_ok=True)
                    placeholder.touch()
                    asset_paths.append(str(placeholder))

        return asset_paths

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

        if use_selector:
            asset_paths = self.generate_assets_from_selector(
                brief, copy_variants, store=store
            )
        else:
            asset_paths = self.generate_assets_from_template(
                brief, copy_variants, template, color_scheme
            )

        deployment_targets = [
            {"format": fmt.value, "platform": p.value}
            for fmt in brief.formats_requested
            for p in brief.platforms
        ]

        primary_fmt = brief.formats_requested[0] if brief.formats_requested else AdFormat.SINGLE_IMAGE
        primary_platform = brief.platforms[0] if brief.platforms else Platform.META

        variants = []
        for copy_data, asset_path in zip(copy_variants, asset_paths):
            tax_data = copy_data["taxonomy"]

            taxonomy = CreativeTaxonomy(
                **tax_data,
                format=primary_fmt,
                platform=primary_platform,
                placement="feed",
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
            )
            variants.append(variant)

        return variants
