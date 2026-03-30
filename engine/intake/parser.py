"""
Intake Parser — converts free-form idea dumps into structured creative briefs.

Input: raw text (slack message, voice transcript, notes, competitor URL)
Output: CreativeBrief with all fields populated

Uses LLM to extract structure. The prompt is the secret sauce here —
it needs to preserve the original creative intent while enforcing
the taxonomy vocabulary so downstream tagging stays clean.
"""

from __future__ import annotations

import json
import re
from typing import Optional, TYPE_CHECKING

from anthropic import Anthropic

from config.settings import get_settings
from engine.models import CreativeBrief, AdFormat, Platform

if TYPE_CHECKING:
    from engine.models import PlaybookRule


SYSTEM_PROMPT = """You are a creative strategist for JotPsych, a clinical documentation AI tool for behavioral health clinicians and small/medium clinic owners.

Your job: take a raw, messy creative idea and structure it into a RICH, SPECIFIC creative brief. Vague briefs produce generic ads. Fight every instinct to be generic.

JotPsych's core value props:
- Saves 1-2 hours of documentation time per day
- AI-powered note generation from session recordings
- HIPAA-compliant, built for behavioral health specifically
- Reduces burnout, lets clinicians focus on patients
- Works with existing EHR workflows

Target audiences:
1. Individual BH clinicians (therapists, psychologists, counselors, social workers)
2. SMB clinic owners / administrators (practice managers, clinical directors)

RICHNESS RULES (these are not optional):
- tone_direction: MUST describe an emotional journey or vivid quality, not a single word.
  BAD: "professional" or "warm" — too generic, rejected.
  GOOD: "Like a colleague who gets it — not selling, just sharing what worked for them"
- emotional_register: MUST be an arc (from → to), not a single adjective.
  BAD: "empathetic"
  GOOD: "overwhelmed by end-of-day charting → quiet relief that the notes are already done"
- proof_element: MUST cite a specific stat or concrete evidence.
  BAD: "backed by research" or "proven results"
  GOOD: "saves 2 hrs/day on average" or "used by 500+ BH clinicians"
- hook_strategy: MUST describe a specific opening approach.
  BAD: "engaging" or "attention-grabbing"
  GOOD: "open with the moment a therapist looks at the clock at 7pm — notes still unwritten"
- target_persona_details: MUST name a specific archetype with daily routine and pain moment.
  BAD: "behavioral health clinician"
  GOOD: "solo therapist, 8-10 sessions/day, bills at night, dreads the 90-minute note backlog after a hard session"

Output a JSON object with ALL of these fields:
{
    "target_audience": "bh_clinicians" or "smb_clinic_owners",
    "value_proposition": "the core promise in one sentence",
    "pain_point": "the specific problem being addressed",
    "desired_action": "what the viewer should do after seeing this",
    "tone_direction": "SPECIFIC: describe the voice/energy, not just a word",
    "visual_direction": "what the ad should look like — setting, lighting, props, subject",
    "key_phrases": ["specific language to use"],
    "emotional_register": "REQUIRED: emotional arc — from current state to desired state",
    "proof_element": "REQUIRED: specific stat or evidence backing the claim",
    "hook_strategy": "REQUIRED: how to open the ad — specific scene or question",
    "target_persona_details": "REQUIRED: specific archetype with daily routine and pain moment",
    "brief_richness_score": <float 1-10, honestly self-score this brief's specificity>,
    "num_variants": 6,
    "formats_requested": ["single_image", "video"],
    "platforms": ["meta", "google"]
}

SELF-SCORING GUIDE for brief_richness_score:
- 9-10: Every field is vivid, specific, actionable. A copywriter could write the ad without asking questions.
- 7-8: Most fields are specific. One or two could be sharper.
- 5-6: Several fields are generic. Would need clarification before writing.
- Below 5: Too vague. Reject and ask for more detail.

{playbook_context}
"""

RICHNESS_CRITERIA = {
    "emotional_register": {
        "generic_patterns": [r"^empathetic$", r"^warm$", r"^professional$", r"^relatable$"],
        "hint": "Must be an arc: 'frustrated by X → relieved by Y'"
    },
    "proof_element": {
        "generic_patterns": [r"proven", r"research", r"studies show", r"clinical evidence"],
        "hint": "Must cite a specific stat: 'saves 2hrs/day' or '500+ clinicians'"
    },
    "hook_strategy": {
        "generic_patterns": [r"^engaging$", r"attention.grabbing", r"^compelling$", r"question"],
        "hint": "Must describe a specific scene or verbatim question"
    },
    "tone_direction": {
        "generic_patterns": [r"^professional$", r"^warm$", r"^empathetic$", r"^friendly$", r"^clinical$"],
        "hint": "Must describe a voice/relationship: 'like a colleague who figured it out first'"
    },
}


def _strip_json(text: str) -> str:
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return text.strip()


def _score_field(field_name: str, value: str) -> int:
    """Score a single brief field: 0=empty, 1=generic, 2=specific."""
    if not value or not value.strip():
        return 0
    criteria = RICHNESS_CRITERIA.get(field_name)
    if criteria:
        for pattern in criteria["generic_patterns"]:
            if re.search(pattern, value.strip(), re.IGNORECASE):
                return 1
    if len(value.strip()) < 15:
        return 1
    return 2


def validate_brief(brief: CreativeBrief) -> tuple[float, list[str]]:
    """
    Score a CreativeBrief for richness and return (score, list_of_vague_fields).
    Score is 0-10. Fields below threshold are listed for re-prompt feedback.
    """
    scored_fields = [
        "emotional_register", "proof_element", "hook_strategy",
        "target_persona_details", "tone_direction", "value_proposition",
    ]
    total = 0
    vague = []
    for field in scored_fields:
        val = getattr(brief, field, "")
        score = _score_field(field, str(val))
        total += score
        if score < 2:
            hint = RICHNESS_CRITERIA.get(field, {}).get("hint", "needs more specificity")
            vague.append(f"{field}: {hint}")

    max_score = len(scored_fields) * 2
    normalized = round(total / max_score * 10, 1)
    return normalized, vague


class IntakeParser:
    def __init__(self, client: Optional[Anthropic] = None):
        if client is None:
            settings = get_settings()
            self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        else:
            self.client = client

    def parse(
        self,
        raw_input: str,
        source: str = "manual",
        playbook_rules: Optional[list] = None,
        creative_direction: Optional[str] = None,
    ) -> CreativeBrief:
        """
        Parse a free-form idea dump into a structured creative brief.

        If the first pass produces a brief_richness_score < 6, automatically
        re-prompts Claude once with feedback on which fields are too vague.

        playbook_rules: optional list of PlaybookRule objects to inject as
        winning pattern examples into the system prompt (A2).

        creative_direction: optional human-supplied creative direction to
        inject as a strong signal alongside playbook rules.
        """
        system = self._build_system_prompt(playbook_rules, creative_direction)
        brief = self._call_claude(raw_input, source, system)

        # Validate and re-prompt if needed (max 1 retry)
        computed_score, vague_fields = validate_brief(brief)
        brief.brief_richness_score = computed_score

        if computed_score < 6 and vague_fields:
            print(
                f"[intake] Brief richness score {computed_score}/10 — retrying with feedback "
                f"on: {', '.join(f.split(':')[0] for f in vague_fields)}"
            )
            feedback_prompt = (
                f"Turn this into a creative brief:\n\n{raw_input}\n\n"
                f"Your previous attempt scored {computed_score}/10 on specificity. "
                f"Please be MORE SPECIFIC on these fields:\n"
                + "\n".join(f"- {v}" for v in vague_fields)
            )
            brief = self._call_claude(feedback_prompt, source, system)
            recomputed_score, _ = validate_brief(brief)
            brief.brief_richness_score = recomputed_score
            print(f"[intake] After retry: {recomputed_score}/10")

        return brief

    def _build_system_prompt(
        self,
        playbook_rules: Optional[list] = None,
        creative_direction: Optional[str] = None,
    ) -> str:
        """Build the system prompt, optionally injecting playbook rules and creative direction.

        Uses str.replace() instead of .format() because the prompt body contains
        JSON examples with curly braces that would break str.format().
        """
        playbook_context = ""
        if playbook_rules:
            rules_text = "\n\nWINNING PATTERNS FROM REGRESSION (use these as creative seeds):\n"
            for rule in playbook_rules[:5]:
                if hasattr(rule, "rule") and hasattr(rule, "direction"):
                    direction = "DO" if rule.direction == "use_more" else "AVOID"
                    rules_text += f"- [{direction}] {rule.rule}\n"
                    if hasattr(rule, "good_examples") and rule.good_examples:
                        rules_text += f"  Example: \"{rule.good_examples[0]}\"\n"
            playbook_context = rules_text

        if creative_direction:
            playbook_context += (
                "\n\nHUMAN CREATIVE DIRECTION (treat as strong signal — "
                "this is the concept owner's intent):\n"
                f"{creative_direction}\n"
            )

        return SYSTEM_PROMPT.replace("{playbook_context}", playbook_context)

    def _call_claude(self, user_content: str, source: str, system: str) -> CreativeBrief:
        """Call Claude and parse the response into a CreativeBrief."""
        response = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": f"Turn this into a creative brief:\n\n{user_content}",
                }
            ],
        )

        text = _strip_json(response.content[0].text)
        data = json.loads(text)

        return CreativeBrief(
            raw_input=user_content,
            source=source,
            target_audience=data.get("target_audience", "bh_clinicians"),
            value_proposition=data.get("value_proposition", ""),
            pain_point=data.get("pain_point", ""),
            desired_action=data.get("desired_action", "Learn more about JotPsych"),
            tone_direction=data.get("tone_direction", ""),
            visual_direction=data.get("visual_direction", ""),
            key_phrases=data.get("key_phrases", []),
            emotional_register=data.get("emotional_register", ""),
            proof_element=data.get("proof_element", ""),
            hook_strategy=data.get("hook_strategy", ""),
            target_persona_details=data.get("target_persona_details", ""),
            brief_richness_score=float(data.get("brief_richness_score", 0.0)),
            num_variants=data.get("num_variants", 6),
            formats_requested=[
                AdFormat(f) for f in data.get("formats_requested", ["single_image", "video"])
            ],
            platforms=[
                Platform(p) for p in data.get("platforms", ["meta", "google"])
            ],
        )

    def parse_batch(
        self,
        ideas: list[str],
        source: str = "manual",
        playbook_rules: Optional[list] = None,
    ) -> list[CreativeBrief]:
        """Parse multiple idea dumps into briefs."""
        return [self.parse(idea, source, playbook_rules) for idea in ideas]
