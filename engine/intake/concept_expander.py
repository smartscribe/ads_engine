"""
Concept Expander — takes a high-level concept string and produces 20 diverse CreativeBriefs.

This is the core of the "concept → 20 variants" workflow agreed at the 3/25 kickoff.
A human originates the concept (e.g., "famous movie psychiatrists"), this engine handles
all tactical variant creation.

Expansion logic:
  concept → Claude enumerates:
    - 5 tactical angles
    - 3 format options
    - 4 emotional tones
    - 3 proof types
  → cross-product → select 20 diverse seeds
  → each seed → full CreativeBrief with distinct fields
"""

from __future__ import annotations

import json
from typing import Optional

from anthropic import Anthropic

from config.settings import get_settings
from engine.models import CreativeBrief, AdFormat, Platform


EXPANSION_SYSTEM_PROMPT = """You are a creative strategist for JotPsych, a clinical documentation AI for behavioral health clinicians.

Your job: take a single concept seed and systematically explore the full creative space it could unlock.
Don't just list synonyms. Each angle should be genuinely different in framing, emotional register, or approach.

JotPsych's core value props:
- Saves 1-2 hours of documentation time per day
- AI notes from session recordings, HIPAA-compliant
- Audit-ready with CPT/ICD codes
- Reduces burnout, clinicians fully present with patients

For the given concept, enumerate:
- 5 tactical_angles: different narrative framings or creative angles to explore the concept
- 3 format_options: ["feed_static", "feed_video", "story"]
- 4 emotional_tones: emotional registers that fit this concept (e.g. "relief", "empowerment", "peer_camaraderie", "anxiety_relief")
- 3 proof_types: ["specific_stat", "peer_testimonial", "before_after"]

Return JSON:
{
  "concept": "<the input concept>",
  "tactical_angles": ["angle 1", "angle 2", "angle 3", "angle 4", "angle 5"],
  "format_options": ["feed_static", "feed_video", "story"],
  "emotional_tones": ["tone1", "tone2", "tone3", "tone4"],
  "proof_types": ["specific_stat", "peer_testimonial", "before_after"]
}
"""

BRIEF_GENERATION_PROMPT = """You are a creative strategist for JotPsych, a clinical documentation AI for behavioral health clinicians.

Given a concept seed with specific parameters, write a RICH, SPECIFIC creative brief.

Rules (non-negotiable):
- tone_direction: describe a voice/relationship, not just a word
- emotional_register: arc from viewer's current state to desired state
- proof_element: specific stat or concrete evidence
- hook_strategy: specific opening scene or verbatim question
- target_persona_details: specific archetype with daily routine and pain moment
- brief_richness_score: honestly score 1-10

Concept: {concept}
Tactical angle: {angle}
Format: {format_option}
Emotional tone: {tone}
Proof type: {proof_type}

Return a JSON object:
{{
    "target_audience": "bh_clinicians" or "smb_clinic_owners",
    "value_proposition": "...",
    "pain_point": "...",
    "desired_action": "...",
    "tone_direction": "...",
    "visual_direction": "...",
    "key_phrases": ["..."],
    "emotional_register": "...",
    "proof_element": "...",
    "hook_strategy": "...",
    "target_persona_details": "...",
    "brief_richness_score": 0.0,
    "formats_requested": ["single_image"],
    "platforms": ["meta"]
}}
"""


def _parse_json(text: str):
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return json.loads(text.strip())


class ConceptExpander:
    """
    Expands a concept string into a diverse set of CreativeBriefs.

    The expansion process:
    1. Ask Claude to enumerate the dimension space (angles × formats × tones × proof types)
    2. Select a diverse 20-seed cross-product
    3. For each seed, generate a full CreativeBrief with distinct, rich fields
    """

    def __init__(self, client: Optional[Anthropic] = None):
        if client is None:
            settings = get_settings()
            self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        else:
            self.client = client

    def expand(self, concept: str, num_variants: int = 20) -> list[CreativeBrief]:
        """
        Expand a concept into up to num_variants CreativeBriefs.

        Each brief has distinct: angle, format, tone, proof type → minimizes
        creative overlap across the batch.
        """
        print(f"[concept_expander] Expanding concept: '{concept}' → {num_variants} briefs")

        # Step 1: Enumerate the dimension space
        seeds = self._enumerate_seeds(concept, num_variants)
        print(f"[concept_expander] Generated {len(seeds)} seeds")

        # Step 2: Generate a brief for each seed (batched to Claude)
        briefs = self._generate_briefs(seeds)
        print(f"[concept_expander] Generated {len(briefs)} briefs")

        return briefs

    def _enumerate_seeds(self, concept: str, num_variants: int) -> list[dict]:
        """Ask Claude to enumerate the creative dimension space for this concept."""
        try:
            resp = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                system=EXPANSION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": f"Concept: {concept}"}],
            )
            data = _parse_json(resp.content[0].text)
        except Exception as e:
            print(f"[concept_expander] Enumeration failed: {e}, using defaults")
            data = {
                "concept": concept,
                "tactical_angles": [
                    "direct pain point relief",
                    "peer success story",
                    "time reclaimed narrative",
                    "audit anxiety resolved",
                    "work-life balance restored",
                ],
                "format_options": ["feed_static", "feed_video", "story"],
                "emotional_tones": ["relief", "empowerment", "peer_camaraderie", "anxiety_relief"],
                "proof_types": ["specific_stat", "peer_testimonial", "before_after"],
            }

        angles = data.get("tactical_angles", [])[:5]
        formats = data.get("format_options", ["feed_static", "feed_video", "story"])[:3]
        tones = data.get("emotional_tones", ["relief", "empowerment", "urgency", "warmth"])[:4]
        proof_types = data.get("proof_types", ["specific_stat", "peer_testimonial", "before_after"])[:3]

        # Build cross-product seeds — systematically cycle through dimensions
        seeds = []
        import itertools
        all_combos = list(itertools.product(angles, formats, tones, proof_types))

        # Select diverse subset up to num_variants
        # Ensure coverage: at least one of each angle, tone, and proof type
        selected = []
        covered_angles = set()
        covered_tones = set()
        covered_proofs = set()

        # First pass: cover each dimension at least once
        for angle, fmt, tone, proof in all_combos:
            if len(selected) >= num_variants:
                break
            if angle not in covered_angles or tone not in covered_tones or proof not in covered_proofs:
                selected.append((angle, fmt, tone, proof))
                covered_angles.add(angle)
                covered_tones.add(tone)
                covered_proofs.add(proof)

        # Second pass: fill remaining slots with varied combos
        for combo in all_combos:
            if len(selected) >= num_variants:
                break
            if combo not in selected:
                selected.append(combo)

        for angle, fmt, tone, proof in selected[:num_variants]:
            seeds.append({
                "concept": concept,
                "angle": angle,
                "format_option": fmt,
                "tone": tone,
                "proof_type": proof,
            })

        return seeds

    def _generate_briefs(self, seeds: list[dict]) -> list[CreativeBrief]:
        """Generate a full CreativeBrief for each seed."""
        briefs = []
        for i, seed in enumerate(seeds):
            try:
                brief = self._generate_single_brief(seed)
                if brief:
                    briefs.append(brief)
                    print(f"[concept_expander] Brief {i+1}/{len(seeds)}: {brief.value_proposition[:50]} (score: {brief.brief_richness_score:.1f})")
            except Exception as e:
                print(f"[concept_expander] Brief {i+1} failed: {e}")
        return briefs

    def _generate_single_brief(self, seed: dict) -> Optional[CreativeBrief]:
        """Generate one CreativeBrief from a seed dict."""
        prompt = BRIEF_GENERATION_PROMPT.format(
            concept=seed["concept"],
            angle=seed["angle"],
            format_option=seed["format_option"],
            tone=seed["tone"],
            proof_type=seed["proof_type"],
        )

        resp = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        data = _parse_json(resp.content[0].text)

        # Map format option to AdFormat
        fmt_map = {
            "feed_static": [AdFormat.SINGLE_IMAGE],
            "feed_video": [AdFormat.VIDEO],
            "story": [AdFormat.STORY],
        }
        formats_requested = fmt_map.get(seed["format_option"], [AdFormat.SINGLE_IMAGE, AdFormat.VIDEO])

        return CreativeBrief(
            raw_input=f"[concept: {seed['concept']} | angle: {seed['angle']}]",
            source="concept",
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
            source_pattern_id=f"concept:{seed['concept']}:{seed['angle']}",
            formats_requested=formats_requested,
            platforms=[Platform.META],
        )
