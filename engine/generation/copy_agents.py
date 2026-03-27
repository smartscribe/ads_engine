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
    "- Warm but professional, like a trusted colleague, not a salesperson\n"
    "- Empathetic to clinician burnout, we understand the paperwork burden\n"
    "- Specific and concrete: '2 hours of charting' not 'save time'\n"
    "- Confident without being pushy\n\n"
    "NEVER USE:\n"
    "- Em dashes. No em dashes anywhere in ad copy. Use periods, commas, or colons instead.\n"
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

# Gold standard examples from best real JotPsych ads (G1)
# These are used as few-shot examples in copy agent prompts.
# Update these when new winning ads emerge from the regression.
GOLD_STANDARD_HEADLINES = [
    "Still Charting at 9pm?",
    "Your Notes Are Done Before You Leave",
    "2 Hours Back Every Day",
    "Finally, Notes That Write Themselves",
    "See Your Last Patient. Not Your Last Chart.",
]

GOLD_STANDARD_BODIES = [
    (
        "You became a therapist to help people, not spend your evenings buried in notes. "
        "JotPsych listens to your sessions and writes your clinical notes for you. "
        "HIPAA-compliant. Audit-ready. Done before you go home."
    ),
    (
        "Most therapists spend 2+ hours a day on documentation. "
        "JotPsych cuts that to minutes. AI-generated notes from your session recordings, "
        "formatted for your EHR, with CPT codes ready to submit."
    ),
    (
        "What would you do with 2 extra hours a day? "
        "JotPsych therapists get their evenings back. "
        "AI notes. Audit-ready docs. No more 9pm charting."
    ),
]


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
        memory=None,
        generation_context=None,
    ) -> list[dict]:
        print(f"[headline_agent] Generating {n} headlines...")

        char_limit = self.META_CHAR_LIMIT
        if Platform.GOOGLE in brief.platforms and Platform.META not in brief.platforms:
            char_limit = self.GOOGLE_HEADLINE_LIMIT

        # Build brief context including new richness fields
        brief_context_parts = [
            f"Target: {brief.target_audience}",
            f"Value Prop: {brief.value_proposition}",
            f"Pain Point: {brief.pain_point}",
            f"Tone: {brief.tone_direction}",
        ]
        if brief.emotional_register:
            brief_context_parts.append(f"Emotional Arc: {brief.emotional_register}")
        if brief.hook_strategy:
            brief_context_parts.append(f"Hook Strategy: {brief.hook_strategy}")
        if brief.target_persona_details:
            brief_context_parts.append(f"Target Persona: {brief.target_persona_details}")
        if brief.proof_element:
            brief_context_parts.append(f"Proof Element: {brief.proof_element}")
        if brief.key_phrases:
            brief_context_parts.append(f"Key Phrases: {', '.join(brief.key_phrases)}")

        system_parts = [
            "You are a direct-response headline writer for JotPsych, a clinical documentation AI for behavioral health.",
            f"\n{JOTPSYCH_VOICE}",
            f"\nJotPsych value props:\n{JOTPSYCH_VALUE_PROPS}",
            f"\nHARD CONSTRAINT: Every headline must be {char_limit} characters or fewer. No exceptions.",
            f"\nGenerate {n} headlines with diverse hooks: questions, statistics, scenarios, direct benefits, provocative claims.",
            "\nGOLD STANDARD HEADLINES (from our best ads, study the style, don't copy verbatim):\n"
            + "\n".join(f'  "{h}"' for h in GOLD_STANDARD_HEADLINES),
            '\nReturn a JSON array where each element is: {"text": "...", "char_count": <int>, "hook_type": "<question|statistic|scenario|direct_benefit|provocative_claim>"}',
        ]

        if generation_context is not None:
            context_block = generation_context.to_prompt_block()
            if context_block.strip():
                system_parts.append(f"\nCREATIVE MEMORY, WHAT WE'VE LEARNED:\n{context_block}")
        elif memory is not None:
            from engine.memory.creative_memory import CreativeMemoryManager
            memory_context = CreativeMemoryManager._to_agent_context_static(memory)
            if memory_context.strip():
                system_parts.append(f"\n{memory_context}")
        elif top_patterns:
            system_parts.append(
                f"\nThese patterns perform best in our ads: {json.dumps(top_patterns)}. "
                "Generate headlines that leverage these insights."
            )

        if approval_feedback:
            approved_headlines = [f"'{a['headline']}'" + (f" (reviewer said: {a['notes']})" if a.get('notes') else "")
                                  for a in approval_feedback if a.get('headline')][:5]
            if approved_headlines:
                system_parts.append(
                    f"\nThese headlines were APPROVED by our reviewers. Generate more in this style:\n"
                    + "\n".join(f"  - {h}" for h in approved_headlines)
                )

        if rejection_feedback:
            rejected_headlines = [f"'{r['headline']}' (rejected because: {r['notes']})"
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
                    "content": "\n".join(brief_context_parts),
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
        memory=None,
        generation_context=None,
    ) -> list[dict]:
        print(f"[body_agent] Generating {n} body copy variants...")

        # Build brief context including new richness fields
        brief_context_parts = [
            f"Target: {brief.target_audience}",
            f"Value Prop: {brief.value_proposition}",
            f"Pain Point: {brief.pain_point}",
            f"Desired Action: {brief.desired_action}",
            f"Tone: {brief.tone_direction}",
        ]
        if brief.emotional_register:
            brief_context_parts.append(f"Emotional Arc: {brief.emotional_register}")
        if brief.target_persona_details:
            brief_context_parts.append(f"Target Persona: {brief.target_persona_details}")
        if brief.proof_element:
            brief_context_parts.append(f"Proof Element to include: {brief.proof_element}")
        if brief.key_phrases:
            brief_context_parts.append(f"Key Phrases: {', '.join(brief.key_phrases)}")

        system_parts = [
            "You are a direct-response body copywriter for JotPsych, a clinical documentation AI for behavioral health.",
            f"\n{JOTPSYCH_VOICE}",
            f"\nJotPsych value props:\n{JOTPSYCH_VALUE_PROPS}",
            f"\nThe first {self.META_PRIMARY_TEXT_LIMIT} characters matter most, that's above the fold on Meta. Front-load impact.",
            "\nRules:"
            "\n- Specific pain points over vague benefits"
            '\n- Include a specific number where possible ("2 hours" not "save time")'
            "\n- Reference real clinician experiences"
            "\n- Vary message angles across: pain_point, value_prop, social_proof, urgency, education, comparison",
            "\nGOLD STANDARD BODY COPY (study the style: real, specific, human):\n"
            + "\n\n".join(f'  "{b}"' for b in GOLD_STANDARD_BODIES),
            f"\nGenerate {n} body copy variants.",
            '\nReturn a JSON array where each element is: {"text": "...", "char_count": <int>, "message_type": "<pain_point|value_prop|social_proof|urgency|education|comparison>", "tone": "<clinical|warm|urgent|playful|authoritative|empathetic>"}',
        ]

        if generation_context is not None:
            context_block = generation_context.to_prompt_block()
            if context_block.strip():
                system_parts.append(f"\nCREATIVE MEMORY, WHAT WE'VE LEARNED:\n{context_block}")
        elif memory is not None:
            from engine.memory.creative_memory import CreativeMemoryManager
            memory_context = CreativeMemoryManager._to_agent_context_static(memory)
            if memory_context.strip():
                system_parts.append(f"\n{memory_context}")
        elif top_patterns:
            system_parts.append(
                f"\nThese patterns perform best in our ads: {json.dumps(top_patterns)}. "
                "Generate body copy that leverages these insights."
            )

        if approval_feedback:
            approved_bodies = [f"'{a['body'][:100]}...'" + (f" (reviewer said: {a['notes']})" if a.get('notes') else "")
                               for a in approval_feedback if a.get('body')][:5]
            if approved_bodies:
                system_parts.append(
                    f"\nThese body copy styles were APPROVED by our reviewers. Generate more in this style:\n"
                    + "\n".join(f"  - {b}" for b in approved_bodies)
                )

        if rejection_feedback:
            rejected_bodies = [f"'{r['body'][:100]}...' (rejected because: {r['notes']})"
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
                    "content": "\n".join(brief_context_parts),
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

    def generate(
        self,
        brief: CreativeBrief,
        n: int = 5,
        generation_context=None,
        memory=None,
    ) -> list[str]:
        print(f"[cta_agent] Generating {n} CTA variations...")

        system_parts = [
            "You are a CTA button text specialist for JotPsych, a clinical documentation AI for behavioral health.\n",
            f"\n{JOTPSYCH_VOICE}\n",
            f"\nHARD CONSTRAINT: Every CTA must be {self.CTA_CHAR_LIMIT} characters or fewer.\n",
            "\nGenerate diverse CTAs varying between: try_free, book_demo, learn_more, see_how, start_saving_time, watch_video.\n",
            f"\nGenerate {n} CTA button texts.\n",
            '\nReturn a JSON array of strings, e.g. ["Try Free", "See How It Works", "Start Saving Time"]',
        ]

        # Inject generation context if available (parity with headline/body agents)
        if generation_context is not None:
            context_block = generation_context.to_prompt_block()
            # For CTAs, only inject the approved_patterns and rejection_rules sections
            # to avoid over-constraining the short-form text
            if "REVIEWER PREFERENCES" in context_block or "REJECTION RULES" in context_block:
                lines = [
                    l for l in context_block.split("\n")
                    if any(kw in l for kw in ["REVIEWER", "REJECTION", "APPROVED", "avoid CTA", "cta_type"])
                ]
                if lines:
                    system_parts.append("\nRELEVANT CONTEXT:\n" + "\n".join(lines))

        system_prompt = "\n".join(system_parts)

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
