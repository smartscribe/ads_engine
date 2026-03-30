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

# Format → template mapping for new Google display formats (G4)
_FORMAT_TEMPLATES = {
    "google_728x90":     "google_728x90/leaderboard",
    "google_160x600":    "google_160x600/skyscraper",
    "carousel":          "meta_carousel_frame/card",
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
        is_display = ad_format == AdFormat.DISPLAY
        is_google = platform == Platform.GOOGLE

        # Pick template based on format first, then taxonomy
        if ad_format == AdFormat.CAROUSEL:
            template = _FORMAT_TEMPLATES.get("carousel", "meta_carousel_frame/card")
            width, height = 1080, 1080
        elif is_display or is_google:
            template = "display_1200x628/responsive"
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

        If diversify=True, uses round-robin rotation through all available
        templates in each format family AND rotates color schemes, so no
        two variants in the batch look identical.
        """
        from collections import Counter

        plans = []
        template_counts: Counter = Counter()  # track usage for round-robin
        scheme_counts: Counter = Counter()

        # All available color schemes for rotation
        all_schemes = list(_COLOR_MOOD_SCHEMES.values())  # ["light", "warm", "light", "dark", ...]
        # Deduplicate while preserving order
        unique_schemes = list(dict.fromkeys(all_schemes))  # ["light", "warm", "dark", "accent"]

        for i, variant in enumerate(copy_variants):
            plan = self.select_for_variant(variant, regression, ad_format, platform)

            if diversify:
                # Rotate template: pick the least-used template in same family
                alt = self._get_least_used_template(
                    plan.template, template_counts
                )
                if alt:
                    plan.template = alt

                # Rotate color scheme across the batch
                plan.color_scheme = unique_schemes[i % len(unique_schemes)]

            template_counts[plan.template] += 1
            scheme_counts[plan.color_scheme] += 1
            plans.append(plan)

        return plans

    def _get_least_used_template(
        self, current: str, used_counts: "Counter"
    ) -> Optional[str]:
        """
        Pick the least-used template in the same format family.
        Returns None if no alternatives exist.
        """
        family = self._get_template_family(current)
        if not family:
            return None

        # Sort by usage count (ascending), break ties by list order
        ranked = sorted(family, key=lambda t: used_counts.get(t, 0))
        return ranked[0]  # pick the least-used

    @staticmethod
    def _get_template_family(template: str) -> Optional[list[str]]:
        """Return all templates in the same format family."""
        if template.startswith("feed_1080x1080/"):
            return [
                "feed_1080x1080/headline_hero",
                "feed_1080x1080/split_screen",
                "feed_1080x1080/stat_callout",
                "feed_1080x1080/testimonial",
                "feed_1080x1080/image_overlay",
            ]
        elif template.startswith("story_1080x1920/"):
            return [
                "story_1080x1920/full_bleed",
                "story_1080x1920/swipe_up",
            ]
        elif template.startswith("display_1200x628/"):
            return ["display_1200x628/responsive"]
        elif template.startswith("meta_carousel_frame/"):
            return ["meta_carousel_frame/card"]
        elif template.startswith("google_728x90/"):
            return ["google_728x90/leaderboard"]
        elif template.startswith("google_160x600/"):
            return ["google_160x600/skyscraper"]
        return None
