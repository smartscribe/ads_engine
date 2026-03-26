"""
Specialized copy generation agents — each focuses on one ad component.

HeadlineAgent  → headlines within platform char limits
BodyCopyAgent  → primary text / body copy
CTAAgent       → CTA button text variations
"""

from __future__ import annotations

import json
from typing import Optional

from anthropic import Anthropic

from config.settings import get_settings
from engine.models import CreativeBrief, AdFormat, Platform
from engine.brand import BRAND_VOICE, PRODUCT_DESCRIPTION


JOTPSYCH_VOICE = (
    "No AI slop. Write like a human copywriter who has talked to 100 burned-out "
    "therapists. Be specific. Be real.\n\n"
    "BRAND TONE GUIDELINES:\n"
    "- Warm but professional — like a trusted colleague, not a salesperson\n"
    "- Empathetic to clinician burnout — we understand the paperwork burden\n"
    "- Specific and concrete — '2 hours of charting' not 'save time'\n"
    "- Confident without being pushy\n\n"
    "NEVER USE:\n"
    "- 'revolutionize', 'leverage', 'streamline', 'cutting-edge', 'innovative'\n"
    "- 'powered by AI', 'next-generation', 'transform your workflow'\n"
    "- 'in today's fast-paced healthcare environment'\n"
    "- 'limited time', 'don't miss out', 'act now'"
)

JOTPSYCH_VALUE_PROPS = (
    "- Saves 1-2 hours of documentation time per day\n"
    "- AI listens to sessions, generates complete clinical notes automatically\n"
    "- Audit-ready documentation with CPT and ICD codes applied\n"
    "- HIPAA-compliant end-to-end for behavioral health\n"
    "- Notes are done before the clinician leaves the office\n"
    "- Clinicians can be fully present with patients (no laptop in session)\n"
    "- Reduces clinician burnout from administrative burden"
)


def _parse_json_response(text: str) -> list:
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return json.loads(text.strip())


class HeadlineAgent:
    META_CHAR_LIMIT = 40
    GOOGLE_HEADLINE_LIMIT = 30

    def __init__(self, client: Optional[Anthropic] = None):
        if client is None:
            settings = get_settings()
            self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        else:
            self.client = client

    def generate(
        self,
        brief: CreativeBrief,
        n: int = 10,
        top_patterns: list = None,
        rejection_feedback: list = None,
        approval_feedback: list = None,
    ) -> list[dict]:
        print(f"[headline_agent] Generating {n} headlines...")

        char_limit = self.META_CHAR_LIMIT
        if Platform.GOOGLE in brief.platforms and Platform.META not in brief.platforms:
            char_limit = self.GOOGLE_HEADLINE_LIMIT

        system_parts = [
            f"You are a direct-response headline writer for JotPsych, a clinical documentation AI for behavioral health.",
            f"\n{JOTPSYCH_VOICE}",
            f"\nJotPsych value props:\n{JOTPSYCH_VALUE_PROPS}",
            f"\nHARD CONSTRAINT: Every headline must be {char_limit} characters or fewer. No exceptions.",
            f"\nGenerate {n} headlines with diverse hooks: questions, statistics, scenarios, direct benefits, provocative claims.",
            '\nReturn a JSON array where each element is: {"text": "...", "char_count": <int>, "hook_type": "<question|statistic|scenario|direct_benefit|provocative_claim>"}',
        ]

        if top_patterns:
            system_parts.append(
                f"\nThese patterns perform best in our ads: {json.dumps(top_patterns)}. "
                "Generate headlines that leverage these insights."
            )

        if approval_feedback:
            approved_headlines = [f"'{a['headline']}'" + (f" (reviewer said: {a['notes']})" if a.get('notes') else "")
                                  for a in approval_feedback if a.get('headline')][:5]
            if approved_headlines:
                system_parts.append(
                    f"\nThese headlines were APPROVED by our reviewers — generate more in this style:\n"
                    + "\n".join(f"  - {h}" for h in approved_headlines)
                )

        if rejection_feedback:
            rejected_headlines = [f"'{r['headline']}' — rejected because: {r['notes']}"
                                  for r in rejection_feedback if r.get('headline')][:5]
            if rejected_headlines:
                system_parts.append(
                    f"\nDO NOT write headlines like these (they were rejected):\n"
                    + "\n".join(f"  - {h}" for h in rejected_headlines)
                )

        system_prompt = "\n".join(system_parts)

        response = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Creative Brief:\n"
                        f"Target: {brief.target_audience}\n"
                        f"Value Prop: {brief.value_proposition}\n"
                        f"Pain Point: {brief.pain_point}\n"
                        f"Tone: {brief.tone_direction}\n"
                        f"Key Phrases: {', '.join(brief.key_phrases)}\n"
                    ),
                }
            ],
        )

        return _parse_json_response(response.content[0].text)


class BodyCopyAgent:
    META_PRIMARY_TEXT_LIMIT = 125  # above-fold optimal; 255 max

    def __init__(self, client: Optional[Anthropic] = None):
        if client is None:
            settings = get_settings()
            self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        else:
            self.client = client

    def generate(
        self,
        brief: CreativeBrief,
        n: int = 5,
        top_patterns: list = None,
        rejection_feedback: list = None,
        approval_feedback: list = None,
    ) -> list[dict]:
        print(f"[body_agent] Generating {n} body copy variants...")

        system_parts = [
            "You are a direct-response body copywriter for JotPsych, a clinical documentation AI for behavioral health.",
            f"\n{JOTPSYCH_VOICE}",
            f"\nJotPsych value props:\n{JOTPSYCH_VALUE_PROPS}",
            f"\nThe first {self.META_PRIMARY_TEXT_LIMIT} characters matter most — that's above the fold on Meta. Front-load impact.",
            "\nRules:"
            "\n- Specific pain points over vague benefits"
            '\n- Include a specific number where possible ("2 hours" not "save time")'
            "\n- Reference real clinician experiences"
            "\n- Vary message angles across: pain_point, value_prop, social_proof, urgency, education, comparison",
            f"\nGenerate {n} body copy variants.",
            '\nReturn a JSON array where each element is: {"text": "...", "char_count": <int>, "message_type": "<pain_point|value_prop|social_proof|urgency|education|comparison>", "tone": "<clinical|warm|urgent|playful|authoritative|empathetic>"}',
        ]

        if top_patterns:
            system_parts.append(
                f"\nThese patterns perform best in our ads: {json.dumps(top_patterns)}. "
                "Generate body copy that leverages these insights."
            )

        if approval_feedback:
            approved_bodies = [f"'{a['body'][:100]}...'" + (f" (reviewer said: {a['notes']})" if a.get('notes') else "")
                               for a in approval_feedback if a.get('body')][:5]
            if approved_bodies:
                system_parts.append(
                    f"\nThese body copy styles were APPROVED by our reviewers — generate more in this style:\n"
                    + "\n".join(f"  - {b}" for b in approved_bodies)
                )

        if rejection_feedback:
            rejected_bodies = [f"'{r['body'][:100]}...' — rejected because: {r['notes']}"
                               for r in rejection_feedback if r.get('body')][:5]
            if rejected_bodies:
                system_parts.append(
                    f"\nDO NOT write body copy like these (they were rejected):\n"
                    + "\n".join(f"  - {b}" for b in rejected_bodies)
                )

        system_prompt = "\n".join(system_parts)

        response = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Creative Brief:\n"
                        f"Target: {brief.target_audience}\n"
                        f"Value Prop: {brief.value_proposition}\n"
                        f"Pain Point: {brief.pain_point}\n"
                        f"Desired Action: {brief.desired_action}\n"
                        f"Tone: {brief.tone_direction}\n"
                        f"Key Phrases: {', '.join(brief.key_phrases)}\n"
                    ),
                }
            ],
        )

        return _parse_json_response(response.content[0].text)


class CTAAgent:
    CTA_CHAR_LIMIT = 20

    def __init__(self, client: Optional[Anthropic] = None):
        if client is None:
            settings = get_settings()
            self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        else:
            self.client = client

    def generate(self, brief: CreativeBrief, n: int = 5) -> list[str]:
        print(f"[cta_agent] Generating {n} CTA variations...")

        system_prompt = (
            "You are a CTA button text specialist for JotPsych, a clinical documentation AI for behavioral health.\n"
            f"\n{JOTPSYCH_VOICE}\n"
            f"\nHARD CONSTRAINT: Every CTA must be {self.CTA_CHAR_LIMIT} characters or fewer.\n"
            "\nGenerate diverse CTAs varying between: try_free, book_demo, learn_more, see_how, start_saving_time, watch_video.\n"
            f"\nGenerate {n} CTA button texts.\n"
            '\nReturn a JSON array of strings, e.g. ["Try Free", "See How It Works", "Start Saving Time"]'
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1000,
            system=system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Creative Brief:\n"
                        f"Target: {brief.target_audience}\n"
                        f"Value Prop: {brief.value_proposition}\n"
                        f"Desired Action: {brief.desired_action}\n"
                    ),
                }
            ],
        )

        return _parse_json_response(response.content[0].text)
