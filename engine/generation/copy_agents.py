"""
Specialized copy generation agents — each focuses on one ad component.

HeadlineAgent  → headlines within platform char limits
BodyCopyAgent  → primary text / body copy
CTAAgent       → CTA button text variations
"""

from __future__ import annotations

import json
import math
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

# Per-hook-type exemplars for slot-based generation.
# Each type gets its own few-shot examples so the LLM anchors on the right style.
HOOK_TYPE_EXEMPLARS = {
    "question": {
        "description": "Open with a question that makes the reader pause and reflect on their own situation",
        "examples": [
            "Still Charting at 9pm?",
            "What If Notes Wrote Themselves?",
            "Burned Out on Paperwork Yet?",
        ],
    },
    "scenario": {
        "description": "Paint a specific, recognizable scene from the clinician's daily life",
        "examples": [
            "See Your Last Patient. Not Your Last Chart.",
            "Your Session Ends. Your Notes Are Done.",
            "Walk Out at 5. Notes Already Filed.",
        ],
    },
    "direct_benefit": {
        "description": "Lead with the concrete outcome or benefit the reader gets",
        "examples": [
            "Your Notes Are Done Before You Leave",
            "Finally, Notes That Write Themselves",
            "Be Present. We Handle the Notes.",
        ],
    },
    "provocative_claim": {
        "description": "Make a bold statement that challenges assumptions or the status quo",
        "examples": [
            "Therapists Shouldn't Be Typists",
            "Your EHR Is Stealing Your Evenings",
            "Documentation Is Not Clinical Care",
        ],
    },
    "testimonial": {
        "description": "Frame as a first-person voice from a real clinician's experience",
        "examples": [
            "I Got My Evenings Back",
            "I Haven't Charted Past 5 in Months",
            "My Notes Used to Take Hours. Now? Minutes.",
        ],
    },
    "statistic": {
        "description": "Lead with a specific, concrete number that quantifies the problem or benefit",
        "examples": [
            "2 Hours Back Every Day",
            "93% of Notes Done Before You Leave",
            "10 Sessions. Zero Hours of Charting.",
        ],
    },
}

# Per-message-type exemplars for slot-based body copy generation.
MESSAGE_TYPE_EXEMPLARS = {
    "pain_point": {
        "description": "Lead with the frustration or struggle the clinician faces daily",
        "examples": [
            "You became a therapist to help people, not spend your evenings buried in notes. "
            "JotPsych listens to your sessions and writes your clinical notes for you. "
            "HIPAA-compliant. Audit-ready. Done before you go home.",
        ],
    },
    "value_prop": {
        "description": "Lead with what JotPsych does and why it matters concretely",
        "examples": [
            "JotPsych turns your session recordings into complete clinical notes. "
            "Formatted for your EHR, with CPT codes applied. "
            "No typing, no templates, no after-hours charting.",
        ],
    },
    "social_proof": {
        "description": "Reference other clinicians' experiences or real adoption evidence",
        "examples": [
            "Therapists across the country are getting their evenings back. "
            "JotPsych handles the notes so you can focus on what you trained for: "
            "helping people. Try it on your next session.",
        ],
    },
    "urgency": {
        "description": "Highlight the cost of waiting or the compounding burden of the status quo",
        "examples": [
            "Every week you chart by hand is another 10 hours you don't get back. "
            "JotPsych therapists finish documentation before they leave the office. "
            "Your next session could be the last one you chart manually.",
        ],
    },
    "education": {
        "description": "Teach the reader something about their own situation they may not have quantified",
        "examples": [
            "The average therapist spends 40% of their workweek on documentation. "
            "That's not a workflow problem. That's a career sustainability problem. "
            "JotPsych cuts documentation to minutes per session.",
        ],
    },
    "comparison": {
        "description": "Contrast before and after, or JotPsych vs. the manual status quo",
        "examples": [
            "What would you do with 2 extra hours a day? "
            "JotPsych therapists get their evenings back. "
            "AI notes. Audit-ready docs. No more 9pm charting.",
        ],
    },
}


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
        """
        Slot-based headline generation: makes separate LLM calls per hook_type
        with type-specific exemplars, guaranteeing diversity structurally.
        """
        print(f"[headline_agent] Generating {n} headlines via slot-based generation...")

        char_limit = self.META_CHAR_LIMIT
        if Platform.GOOGLE in brief.platforms and Platform.META not in brief.platforms:
            char_limit = self.GOOGLE_HEADLINE_LIMIT

        brief_context_parts = self._build_brief_context(brief)
        memory_block = self._build_memory_block(
            generation_context, memory, top_patterns
        )
        feedback_block = self._build_feedback_block(
            approval_feedback, rejection_feedback
        )

        hook_types = list(HOOK_TYPE_EXEMPLARS.keys())
        slots = self._distribute_slots(n, len(hook_types))

        results = []
        for hook_type, count in zip(hook_types, slots):
            if count == 0:
                continue
            exemplars = HOOK_TYPE_EXEMPLARS[hook_type]
            try:
                headlines = self._generate_for_hook_type(
                    hook_type, count, exemplars, char_limit,
                    brief_context_parts, memory_block, feedback_block,
                )
                results.extend(headlines)
                print(f"[headline_agent]   {hook_type}: {len(headlines)} headlines")
            except Exception as e:
                print(f"[headline_agent]   {hook_type}: failed ({e})")

        print(f"[headline_agent] Total: {len(results)} headlines across {len({r.get('hook_type') for r in results})} hook_types")
        return results

    def _build_brief_context(self, brief: CreativeBrief) -> list[str]:
        parts = [
            f"Target: {brief.target_audience}",
            f"Value Prop: {brief.value_proposition}",
            f"Pain Point: {brief.pain_point}",
            f"Tone: {brief.tone_direction}",
        ]
        if brief.emotional_register:
            parts.append(f"Emotional Arc: {brief.emotional_register}")
        if brief.hook_strategy:
            parts.append(f"Hook Strategy: {brief.hook_strategy}")
        if brief.target_persona_details:
            parts.append(f"Target Persona: {brief.target_persona_details}")
        if brief.proof_element:
            parts.append(f"Proof Element: {brief.proof_element}")
        if brief.key_phrases:
            parts.append(f"Key Phrases: {', '.join(brief.key_phrases)}")
        return parts

    def _build_memory_block(self, generation_context, memory, top_patterns) -> str:
        if generation_context is not None:
            block = generation_context.to_prompt_block()
            if block.strip():
                return f"\nCREATIVE MEMORY, WHAT WE'VE LEARNED:\n{block}"
        elif memory is not None:
            from engine.memory.creative_memory import CreativeMemoryManager
            ctx = CreativeMemoryManager._to_agent_context_static(memory)
            if ctx.strip():
                return f"\n{ctx}"
        elif top_patterns:
            return (
                f"\nThese patterns perform best in our ads: {json.dumps(top_patterns)}. "
                "Generate headlines that leverage these insights."
            )
        return ""

    def _build_feedback_block(self, approval_feedback, rejection_feedback) -> str:
        parts = []
        if approval_feedback:
            approved = [
                f"'{a['headline']}'" + (f" (reviewer said: {a['notes']})" if a.get('notes') else "")
                for a in approval_feedback if a.get('headline')
            ][:5]
            if approved:
                parts.append(
                    "\nThese headlines were APPROVED by our reviewers. Generate more in this style:\n"
                    + "\n".join(f"  - {h}" for h in approved)
                )
        if rejection_feedback:
            rejected = [
                f"'{r['headline']}' (rejected because: {r['notes']})"
                for r in rejection_feedback if r.get('headline')
            ][:5]
            if rejected:
                parts.append(
                    "\nDO NOT write headlines like these (they were rejected):\n"
                    + "\n".join(f"  - {h}" for h in rejected)
                )
        return "\n".join(parts)

    @staticmethod
    def _distribute_slots(n: int, num_types: int) -> list[int]:
        """Distribute n items across num_types as evenly as possible."""
        base = n // num_types
        remainder = n % num_types
        return [base + (1 if i < remainder else 0) for i in range(num_types)]

    def _generate_for_hook_type(
        self,
        hook_type: str,
        count: int,
        exemplars: dict,
        char_limit: int,
        brief_context_parts: list[str],
        memory_block: str,
        feedback_block: str,
    ) -> list[dict]:
        examples_str = "\n".join(f'  "{ex}"' for ex in exemplars["examples"])

        system_parts = [
            "You are a direct-response headline writer for JotPsych, a clinical documentation AI for behavioral health.",
            f"\n{JOTPSYCH_VOICE}",
            f"\nJotPsych value props:\n{JOTPSYCH_VALUE_PROPS}",
            f"\nHARD CONSTRAINT: Every headline must be {char_limit} characters or fewer. No exceptions.",
            f"\nYour task: write exactly {count} headline(s) using the '{hook_type}' hook style.",
            f"\nWhat '{hook_type}' means: {exemplars['description']}",
            f"\nExamples of great '{hook_type}' headlines (study the style, don't copy verbatim):\n{examples_str}",
            f"\nWrite {count} NEW headline(s) in this style. Each must feel distinct from the examples and from each other.",
            f'\nReturn a JSON array where each element is: {{"text": "...", "char_count": <int>, "hook_type": "{hook_type}"}}',
        ]
        if memory_block:
            system_parts.append(memory_block)
        if feedback_block:
            system_parts.append(feedback_block)

        response = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=500,
            system="\n".join(system_parts),
            messages=[{"role": "user", "content": "\n".join(brief_context_parts)}],
        )

        headlines = _parse_json_response(response.content[0].text)
        for h in headlines:
            h["hook_type"] = hook_type
        return headlines[:count]


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
        """
        Slot-based body copy generation: makes separate LLM calls per message_type
        with type-specific exemplars, guaranteeing diversity structurally.
        """
        print(f"[body_agent] Generating {n} body copy variants via slot-based generation...")

        brief_context_parts = self._build_brief_context(brief)
        memory_block = self._build_memory_block(
            generation_context, memory, top_patterns
        )
        feedback_block = self._build_feedback_block(
            approval_feedback, rejection_feedback
        )

        message_types = list(MESSAGE_TYPE_EXEMPLARS.keys())
        slots = HeadlineAgent._distribute_slots(n, len(message_types))

        results = []
        for msg_type, count in zip(message_types, slots):
            if count == 0:
                continue
            exemplars = MESSAGE_TYPE_EXEMPLARS[msg_type]
            try:
                bodies = self._generate_for_message_type(
                    msg_type, count, exemplars,
                    brief_context_parts, memory_block, feedback_block,
                )
                results.extend(bodies)
                print(f"[body_agent]   {msg_type}: {len(bodies)} bodies")
            except Exception as e:
                print(f"[body_agent]   {msg_type}: failed ({e})")

        print(f"[body_agent] Total: {len(results)} bodies across {len({r.get('message_type') for r in results})} message_types")
        return results

    def _build_brief_context(self, brief: CreativeBrief) -> list[str]:
        parts = [
            f"Target: {brief.target_audience}",
            f"Value Prop: {brief.value_proposition}",
            f"Pain Point: {brief.pain_point}",
            f"Desired Action: {brief.desired_action}",
            f"Tone: {brief.tone_direction}",
        ]
        if brief.emotional_register:
            parts.append(f"Emotional Arc: {brief.emotional_register}")
        if brief.target_persona_details:
            parts.append(f"Target Persona: {brief.target_persona_details}")
        if brief.proof_element:
            parts.append(f"Proof Element to include: {brief.proof_element}")
        if brief.key_phrases:
            parts.append(f"Key Phrases: {', '.join(brief.key_phrases)}")
        return parts

    def _build_memory_block(self, generation_context, memory, top_patterns) -> str:
        if generation_context is not None:
            block = generation_context.to_prompt_block()
            if block.strip():
                return f"\nCREATIVE MEMORY, WHAT WE'VE LEARNED:\n{block}"
        elif memory is not None:
            from engine.memory.creative_memory import CreativeMemoryManager
            ctx = CreativeMemoryManager._to_agent_context_static(memory)
            if ctx.strip():
                return f"\n{ctx}"
        elif top_patterns:
            return (
                f"\nThese patterns perform best in our ads: {json.dumps(top_patterns)}. "
                "Generate body copy that leverages these insights."
            )
        return ""

    def _build_feedback_block(self, approval_feedback, rejection_feedback) -> str:
        parts = []
        if approval_feedback:
            approved = [
                f"'{a['body'][:100]}...'" + (f" (reviewer said: {a['notes']})" if a.get('notes') else "")
                for a in approval_feedback if a.get('body')
            ][:5]
            if approved:
                parts.append(
                    "\nThese body copy styles were APPROVED by our reviewers. Generate more in this style:\n"
                    + "\n".join(f"  - {b}" for b in approved)
                )
        if rejection_feedback:
            rejected = [
                f"'{r['body'][:100]}...' (rejected because: {r['notes']})"
                for r in rejection_feedback if r.get('body')
            ][:5]
            if rejected:
                parts.append(
                    "\nDO NOT write body copy like these (they were rejected):\n"
                    + "\n".join(f"  - {b}" for b in rejected)
                )
        return "\n".join(parts)

    def _generate_for_message_type(
        self,
        msg_type: str,
        count: int,
        exemplars: dict,
        brief_context_parts: list[str],
        memory_block: str,
        feedback_block: str,
    ) -> list[dict]:
        examples_str = "\n\n".join(f'  "{ex}"' for ex in exemplars["examples"])

        system_parts = [
            "You are a direct-response body copywriter for JotPsych, a clinical documentation AI for behavioral health.",
            f"\n{JOTPSYCH_VOICE}",
            f"\nJotPsych value props:\n{JOTPSYCH_VALUE_PROPS}",
            f"\nThe first {self.META_PRIMARY_TEXT_LIMIT} characters matter most, that's above the fold on Meta. Front-load impact.",
            "\nRules:"
            "\n- Specific pain points over vague benefits"
            '\n- Include a specific number where possible ("2 hours" not "save time")'
            "\n- Reference real clinician experiences",
            f"\nYour task: write exactly {count} body copy variant(s) using the '{msg_type}' message angle.",
            f"\nWhat '{msg_type}' means: {exemplars['description']}",
            f"\nExample of great '{msg_type}' body copy (study the style, don't copy verbatim):\n{examples_str}",
            f"\nWrite {count} NEW body copy variant(s) in this style. Each must feel distinct from the examples and from each other.",
            f'\nReturn a JSON array where each element is: {{"text": "...", "char_count": <int>, "message_type": "{msg_type}", '
            '"tone": "<clinical|warm|urgent|playful|authoritative|empathetic>"}',
        ]
        if memory_block:
            system_parts.append(memory_block)
        if feedback_block:
            system_parts.append(feedback_block)

        response = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=800,
            system="\n".join(system_parts),
            messages=[{"role": "user", "content": "\n".join(brief_context_parts)}],
        )

        bodies = _parse_json_response(response.content[0].text)
        for b in bodies:
            b["message_type"] = msg_type
        return bodies[:count]


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
