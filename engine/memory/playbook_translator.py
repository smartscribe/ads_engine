"""
Playbook Translator — converts raw regression coefficients into actionable rules.

This runs once per regression cycle (not per generation). It takes feature names
like "hook_type_statistic" and produces rules like "Lead with a specific number
in the headline" along with real examples from approved/rejected variants.
"""

from __future__ import annotations

import json
import re
from typing import Optional, TYPE_CHECKING

from anthropic import Anthropic

from config.settings import get_settings
from engine.models import PlaybookRule, RegressionResult, AdStatus

if TYPE_CHECKING:
    from engine.store import Store


FEATURE_DESCRIPTIONS = {
    "hook_type_question": "Headlines that open with a question",
    "hook_type_statistic": "Headlines that lead with a specific number or statistic",
    "hook_type_testimonial": "Headlines featuring a testimonial or quote",
    "hook_type_provocative_claim": "Headlines with bold, provocative claims",
    "hook_type_scenario": "Headlines that paint a scenario",
    "hook_type_direct_benefit": "Headlines stating the benefit directly",
    "message_type_value_prop": "Copy focused on the core value proposition",
    "message_type_pain_point": "Copy that leads with a pain point",
    "message_type_social_proof": "Copy featuring social proof or testimonials",
    "message_type_urgency": "Copy with urgency or time pressure",
    "message_type_education": "Educational/informational copy",
    "message_type_comparison": "Copy comparing to alternatives",
    "tone_clinical": "Clinical, professional tone",
    "tone_warm": "Warm, friendly tone",
    "tone_urgent": "Urgent, action-oriented tone",
    "tone_playful": "Playful, light tone",
    "tone_authoritative": "Authoritative, expert tone",
    "tone_empathetic": "Empathetic, understanding tone",
    "cta_type_try_free": "'Try Free' or similar free trial CTAs",
    "cta_type_book_demo": "'Book Demo' or demo-focused CTAs",
    "cta_type_learn_more": "'Learn More' or information-seeking CTAs",
    "cta_type_see_how": "'See How' or demonstration CTAs",
    "cta_type_start_saving_time": "Time-saving focused CTAs",
    "cta_type_watch_video": "Video-viewing CTAs",
    "uses_number": "Copy that includes specific numbers (e.g., '2 hours')",
    "uses_question": "Copy that uses question format",
    "uses_first_person": "Copy using first person ('I', 'my')",
    "uses_social_proof": "Copy with social proof elements",
    "visual_style_photography": "Real photography visuals",
    "visual_style_illustration": "Illustrated visuals",
    "visual_style_screen_capture": "Product UI screenshots",
    "visual_style_text_heavy": "Text-heavy layouts",
    "color_mood_brand_primary": "Brand primary colors (midnight blue)",
    "color_mood_warm_earth": "Warm earth tones",
    "color_mood_cool_clinical": "Cool, clinical colors",
    "color_mood_high_contrast": "High contrast color schemes",
}

TRANSLATION_PROMPT = """You are a creative director translating regression analysis into actionable copywriting rules.

Given a list of features with their coefficients (negative = better for lowering cost per conversion), create clear, specific rules that a copywriter can follow.

For each feature, provide:
1. A concise rule (one sentence, actionable)
2. Why it works (brief explanation based on the feature)

Format your response as a JSON array:
[
  {
    "feature": "hook_type_statistic",
    "rule": "Lead headlines with a specific number — '2 hours of charting saved' beats 'Save time on charting'",
    "explanation": "Specific numbers create credibility and make benefits tangible"
  },
  ...
]

Features to translate (sorted by impact):
{features_json}

Keep rules specific to JotPsych (clinical documentation AI for behavioral health). 
Target audience: burned-out therapists and clinic owners drowning in paperwork.
"""


class PlaybookTranslator:
    """
    Translates regression coefficients into actionable PlaybookRules with examples.
    """

    def __init__(self, store: "Store", client: Optional[Anthropic] = None):
        self.store = store
        if client is None:
            settings = get_settings()
            self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        else:
            self.client = client

    def translate(self, regression: RegressionResult) -> list[PlaybookRule]:
        """
        Convert regression results into playbook rules with examples.
        """
        significant = []
        for feature in regression.top_positive_features[:10]:
            significant.append({
                "feature": feature,
                "coefficient": regression.coefficients[feature],
                "p_value": regression.p_values.get(feature, 0),
                "direction": "use_more",
                "description": FEATURE_DESCRIPTIONS.get(feature, feature),
            })
        
        for feature in regression.top_negative_features[:10]:
            significant.append({
                "feature": feature,
                "coefficient": regression.coefficients[feature],
                "p_value": regression.p_values.get(feature, 0),
                "direction": "avoid",
                "description": FEATURE_DESCRIPTIONS.get(feature, feature),
            })
        
        if not significant:
            return []
        
        translated = self._call_claude_for_rules(significant)
        
        rules = []
        for item in significant:
            feature = item["feature"]
            rule_text = translated.get(feature, {}).get("rule", f"Use {item['description']}")
            
            good_examples = self._find_examples(feature, approved=True)
            bad_examples = self._find_examples(feature, approved=False)
            
            rule = PlaybookRule(
                feature=feature,
                direction=item["direction"],
                confidence="high" if item["p_value"] < 0.01 else "moderate",
                rule=rule_text,
                good_examples=good_examples,
                bad_examples=bad_examples,
                coefficient=item["coefficient"],
                p_value=item["p_value"],
            )
            rules.append(rule)
        
        return rules

    def _call_claude_for_rules(self, features: list[dict]) -> dict[str, dict]:
        """Call Claude to generate natural language rules."""
        features_json = json.dumps(features, indent=2)
        prompt = TRANSLATION_PROMPT.format(features_json=features_json)
        
        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            
            text = response.content[0].text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            
            rules_list = json.loads(text.strip())
            return {r["feature"]: r for r in rules_list}
        
        except Exception as e:
            print(f"[playbook_translator] Claude call failed: {e}")
            return {}

    def _find_examples(self, feature: str, approved: bool, limit: int = 3) -> list[str]:
        """
        Find real copy examples from variants matching the feature.
        """
        if approved:
            variants = self.store.get_variants_by_status(AdStatus.APPROVED)
            variants.extend(self.store.get_variants_by_status(AdStatus.GRADUATED))
        else:
            variants = self.store.get_variants_by_status(AdStatus.REJECTED)
        
        examples = []
        
        dimension, value = self._parse_feature(feature)
        if dimension is None:
            return examples
        
        for v in variants:
            if v.taxonomy is None:
                continue
            
            tax_dict = v.taxonomy.model_dump()
            
            matches = False
            if dimension in tax_dict:
                if isinstance(tax_dict[dimension], bool):
                    matches = tax_dict[dimension] == (value == "True" or value == "1")
                elif hasattr(tax_dict[dimension], "value"):
                    matches = tax_dict[dimension].value == value
                else:
                    matches = str(tax_dict[dimension]) == value
            
            if matches:
                if dimension.startswith("hook_type") or dimension == "uses_number" or dimension == "uses_question":
                    examples.append(v.headline)
                else:
                    examples.append(v.primary_text[:100])
                
                if len(examples) >= limit:
                    break
        
        return examples

    def _parse_feature(self, feature: str) -> tuple[Optional[str], Optional[str]]:
        """
        Parse feature name into dimension and value.
        e.g., 'hook_type_statistic' -> ('hook_type', 'statistic')
        """
        boolean_features = ["uses_number", "uses_question", "uses_first_person", "uses_social_proof"]
        if feature in boolean_features:
            return (feature, "True")
        
        categorical_prefixes = [
            "message_type_", "hook_type_", "cta_type_", "tone_",
            "visual_style_", "subject_matter_", "color_mood_", "text_density_",
            "format_", "platform_", "placement_",
        ]
        
        for prefix in categorical_prefixes:
            if feature.startswith(prefix):
                dimension = prefix.rstrip("_")
                value = feature[len(prefix):]
                return (dimension, value)
        
        if "_x_" in feature:
            return (None, None)
        
        return (None, None)
