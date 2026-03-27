"""
Template Selector — maps taxonomy tags + regression coefficients to template + color scheme.

Given a variant's taxonomy dimensions and (optionally) the latest regression result,
picks the best template layout and color scheme. This is the bridge between the
copy generation pipeline (which tags every variant with a CreativeTaxonomy) and the
Playwright rendering pipeline (which needs a concrete template + colors).

When regression data exists, the selector biases toward visual treatments that
correlate with lower CpFN. Without regression data, it uses sensible heuristics
based on the taxonomy dimensions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from engine.models import RegressionResult, AdFormat, Platform


@dataclass
class TemplatePlan:
    """Concrete rendering instructions for a single ad variant."""
    template: str               # e.g. "feed_1080x1080/stat_callout"
    color_scheme: str           # e.g. "dark"
    format: str                 # e.g. "single_image"
    width: int = 1080
    height: int = 1080
    is_video: bool = False
    video_duration_ms: int = 5000
    context: dict = field(default_factory=dict)


# Taxonomy dimension → template family mapping.
# Priority order matters: first match wins, more specific keys first.
_HOOK_TYPE_TEMPLATES = {
    "testimonial":       "feed_1080x1080/testimonial",
    "statistic":         "feed_1080x1080/stat_callout",
}

_SUBJECT_MATTER_TEMPLATES = {
    "data_viz":          "feed_1080x1080/stat_callout",
    "product_ui":        "feed_1080x1080/split_screen",
    "workflow_comparison": "feed_1080x1080/split_screen",
}

_TEXT_DENSITY_TEMPLATES = {
    "headline_only":     "feed_1080x1080/headline_hero",
    "minimal_overlay":   "feed_1080x1080/headline_hero",
    "detailed_copy":     "feed_1080x1080/split_screen",
}

_VISUAL_STYLE_TEMPLATES = {
    "text_heavy":        "feed_1080x1080/headline_hero",
}

# Color mood → color scheme mapping
_COLOR_MOOD_SCHEMES = {
    "brand_primary":     "light",
    "warm_earth":        "warm",
    "cool_clinical":     "light",
    "high_contrast":     "dark",
    "muted_soft":        "warm",
    "bold_saturated":    "accent",
}

# Story-format template mapping
_STORY_TEMPLATES = {
    "statistic":         "story_1080x1920/swipe_up",
    "testimonial":       "story_1080x1920/full_bleed",
    "_default":          "story_1080x1920/full_bleed",
}

# Format → viewport sizes
_FORMAT_SIZES = {
    "feed_1080x1080":    (1080, 1080),
    "story_1080x1920":   (1080, 1920),
    "display_1200x628":  (1200, 628),
}


class TemplateSelector:
    """
    Select the best template + color scheme for a variant based on its
    taxonomy tags and regression insights.
    """

    def select(
        self,
        taxonomy: dict,
        regression: Optional[RegressionResult] = None,
        ad_format: Optional[AdFormat] = None,
        platform: Optional[Platform] = None,
    ) -> TemplatePlan:
        """
        Pick the best template and color scheme.

        Args:
            taxonomy:   Dict of taxonomy dimensions (hook_type, message_type, etc.)
            regression: Latest regression result (for coefficient-driven overrides)
            ad_format:  Target ad format (SINGLE_IMAGE, STORY, VIDEO, DISPLAY, etc.)
            platform:   Target platform (META, GOOGLE)

        Returns:
            TemplatePlan with template path, color scheme, and rendering config.
        """
        is_story = ad_format in (AdFormat.STORY, AdFormat.REELS)
        is_video = ad_format == AdFormat.VIDEO or is_story
        is_display = ad_format == AdFormat.DISPLAY
        is_google = platform == Platform.GOOGLE

        # Pick template based on format first, then taxonomy
        if is_display or is_google:
            template = "display_1200x628/responsive"
        elif is_story:
            template = self._select_story_template(taxonomy)
        else:
            template = self._select_feed_template(taxonomy)

        # Pick color scheme from taxonomy color_mood
        color_mood = taxonomy.get("color_mood", "brand_primary")
        color_scheme = _COLOR_MOOD_SCHEMES.get(color_mood, "light")

        # Apply regression overrides if available
        if regression and regression.coefficients:
            color_scheme = self._apply_regression_overrides(
                color_scheme, taxonomy, regression
            )

        # Determine viewport
        format_prefix = template.rsplit("/", 1)[0] if "/" in template else "feed_1080x1080"
        width, height = _FORMAT_SIZES.get(format_prefix, (1080, 1080))

        # Build extra context for certain templates
        context = self._build_context(template, taxonomy)

        return TemplatePlan(
            template=template,
            color_scheme=color_scheme,
            format=ad_format.value if ad_format else "single_image",
            width=width,
            height=height,
            is_video=is_video,
            video_duration_ms=5000 if is_video else 0,
            context=context,
        )

    def select_for_variant(
        self,
        copy_variant: dict,
        regression: Optional[RegressionResult] = None,
        ad_format: Optional[AdFormat] = None,
        platform: Optional[Platform] = None,
    ) -> TemplatePlan:
        """Convenience: extract taxonomy from a copy variant dict and select."""
        taxonomy = copy_variant.get("taxonomy", {})
        return self.select(taxonomy, regression, ad_format, platform)

    def _select_feed_template(self, taxonomy: dict) -> str:
        hook_type = taxonomy.get("hook_type", "")
        if hook_type in _HOOK_TYPE_TEMPLATES:
            return _HOOK_TYPE_TEMPLATES[hook_type]

        subject = taxonomy.get("subject_matter", "")
        if subject in _SUBJECT_MATTER_TEMPLATES:
            return _SUBJECT_MATTER_TEMPLATES[subject]

        text_density = taxonomy.get("text_density", "")
        if text_density in _TEXT_DENSITY_TEMPLATES:
            return _TEXT_DENSITY_TEMPLATES[text_density]

        visual = taxonomy.get("visual_style", "")
        if visual in _VISUAL_STYLE_TEMPLATES:
            return _VISUAL_STYLE_TEMPLATES[visual]

        # Default for feed
        return "feed_1080x1080/headline_hero"

    def _select_story_template(self, taxonomy: dict) -> str:
        hook_type = taxonomy.get("hook_type", "")
        return _STORY_TEMPLATES.get(hook_type, _STORY_TEMPLATES["_default"])

    def _apply_regression_overrides(
        self,
        base_scheme: str,
        taxonomy: dict,
        regression: RegressionResult,
    ) -> str:
        """
        If regression shows a specific color_mood or visual_style drives
        better performance, override the default scheme.
        """
        coefficients = regression.coefficients
        p_values = regression.p_values

        best_scheme = base_scheme
        best_delta = 0.0

        for mood, scheme in _COLOR_MOOD_SCHEMES.items():
            feature = f"color_mood_{mood}"
            coeff = coefficients.get(feature, 0)
            p_val = p_values.get(feature, 1.0)

            # Negative coefficient = lower CpFN = better.
            # Only override if statistically significant.
            if coeff < best_delta and p_val < 0.05:
                best_delta = coeff
                best_scheme = scheme

        return best_scheme

    def _build_context(self, template: str, taxonomy: dict) -> dict:
        """
        Build extra context variables needed by specific templates.

        Templates like stat_callout need stat_number/stat_unit;
        testimonial needs attribution; swipe_up needs badge_text.
        """
        context = {}

        if "stat_callout" in template:
            context.setdefault("stat_number", "2")
            context.setdefault("stat_unit", "hours saved per day")

        if "testimonial" in template:
            context.setdefault("attribution", "Behavioral Health Clinician")

        if "swipe_up" in template:
            context.setdefault("badge_text", "For Clinicians")

        return context

    def select_batch(
        self,
        copy_variants: list[dict],
        regression: Optional[RegressionResult] = None,
        ad_format: Optional[AdFormat] = None,
        platform: Optional[Platform] = None,
        diversify: bool = True,
    ) -> list[TemplatePlan]:
        """
        Select templates for a batch of variants.

        If diversify=True, ensures we don't repeat the same template
        for every variant — rotates through available layouts.
        """
        plans = []
        used_templates = set()

        for variant in copy_variants:
            plan = self.select_for_variant(variant, regression, ad_format, platform)

            if diversify and plan.template in used_templates:
                alt = self._get_alternative_template(plan.template, variant.get("taxonomy", {}))
                if alt:
                    plan.template = alt

            used_templates.add(plan.template)
            plans.append(plan)

        return plans

    def _get_alternative_template(self, current: str, taxonomy: dict) -> Optional[str]:
        """Pick a different template in the same format family."""
        if current.startswith("feed_1080x1080/"):
            alternatives = [
                "feed_1080x1080/headline_hero",
                "feed_1080x1080/split_screen",
                "feed_1080x1080/stat_callout",
                "feed_1080x1080/testimonial",
            ]
        elif current.startswith("story_1080x1920/"):
            alternatives = [
                "story_1080x1920/full_bleed",
                "story_1080x1920/swipe_up",
            ]
        else:
            return None

        for alt in alternatives:
            if alt != current:
                return alt
        return None
