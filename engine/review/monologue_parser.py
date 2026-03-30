"""
Monologue Parser — converts freeform review monologues into structured
per-variant feedback and global creative direction.

Nathan's use case: "I'm looking at the gallery. I'm now going to monologue
for 10 minutes about what's working, what's not working."

The parser maps freeform commentary to specific variants when possible,
and extracts global creative direction statements separately.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from anthropic import Anthropic

from config.settings import get_settings


@dataclass
class VariantVerdict:
    variant_id: str
    verdict: str  # "approve" | "reject" | "skip"
    reason: str


@dataclass
class MonologueResult:
    monologue_id: str
    reviewer: str
    raw_text: str
    verdicts: list[VariantVerdict]
    global_directions: list[str]
    parsed_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "monologue_id": self.monologue_id,
            "reviewer": self.reviewer,
            "raw_text": self.raw_text,
            "verdicts": [
                {"variant_id": v.variant_id, "verdict": v.verdict, "reason": v.reason}
                for v in self.verdicts
            ],
            "global_directions": self.global_directions,
            "parsed_at": self.parsed_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "MonologueResult":
        return cls(
            monologue_id=d["monologue_id"],
            reviewer=d["reviewer"],
            raw_text=d["raw_text"],
            verdicts=[
                VariantVerdict(
                    variant_id=v["variant_id"],
                    verdict=v["verdict"],
                    reason=v["reason"],
                )
                for v in d["verdicts"]
            ],
            global_directions=d["global_directions"],
            parsed_at=datetime.fromisoformat(d["parsed_at"]) if "parsed_at" in d else datetime.utcnow(),
        )


SYSTEM_PROMPT = """You are a creative review analyst for JotPsych's ad engine.

You will receive:
1. A freeform monologue from a reviewer who has been looking at a gallery of ad variants
2. A list of ad variants with their IDs, headlines, body copy, CTAs, and taxonomy tags

Your job:
- Map the reviewer's specific comments to individual variants when possible
- For each variant mentioned (positively or negatively), produce a verdict: approve, reject, or skip
- Extract global creative direction statements that apply across all future ad generation
- If the reviewer doesn't mention a specific variant, mark it as "skip"

Output a JSON object with exactly this structure:
{
    "verdicts": [
        {
            "variant_id": "<id>",
            "verdict": "approve" | "reject" | "skip",
            "reason": "brief explanation of why, based on what the reviewer said"
        }
    ],
    "global_directions": [
        "extracted creative rule or preference, e.g. 'more urgency in headlines'",
        "another direction, e.g. 'stop using question hooks, they feel generic'"
    ]
}

Rules:
- Include a verdict entry for EVERY variant in the list, even if verdict is "skip"
- Be generous with mapping — if the reviewer says "the one about charting" and only one headline mentions charting, map it
- Global directions should be actionable, specific creative guidance
- If the monologue is entirely positive with no rejections, still extract any creative preferences mentioned
- Preserve the reviewer's intent faithfully — don't add your own creative opinions"""


class MonologueParser:
    def __init__(self):
        settings = get_settings()
        self.client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def parse(
        self,
        text: str,
        variants: list[dict],
        reviewer: str = "unknown",
    ) -> MonologueResult:
        """
        Parse a freeform monologue into structured per-variant feedback
        and global creative directions.

        Args:
            text: raw monologue text
            variants: list of dicts with keys: id, headline, body, cta, taxonomy
            reviewer: who submitted the monologue
        """
        variants_block = self._format_variants(variants)

        user_message = (
            f"## REVIEWER MONOLOGUE\n\n{text}\n\n"
            f"## AD VARIANTS IN GALLERY\n\n{variants_block}"
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        parsed = self._extract_json(response.content[0].text)

        verdicts = []
        variant_ids_in_list = {v["id"] for v in variants}

        for v in parsed.get("verdicts", []):
            vid = v.get("variant_id", "")
            if vid in variant_ids_in_list:
                verdicts.append(VariantVerdict(
                    variant_id=vid,
                    verdict=v.get("verdict", "skip"),
                    reason=v.get("reason", ""),
                ))

        covered_ids = {v.variant_id for v in verdicts}
        for vid in variant_ids_in_list - covered_ids:
            verdicts.append(VariantVerdict(variant_id=vid, verdict="skip", reason="Not mentioned in monologue"))

        return MonologueResult(
            monologue_id=str(uuid.uuid4()),
            reviewer=reviewer,
            raw_text=text,
            verdicts=verdicts,
            global_directions=parsed.get("global_directions", []),
        )

    def _format_variants(self, variants: list[dict]) -> str:
        lines = []
        for i, v in enumerate(variants, 1):
            tax = v.get("taxonomy") or {}
            tax_str = ", ".join(f"{k}={val}" for k, val in tax.items() if val) if tax else "n/a"
            lines.append(
                f"### Variant {i} (ID: {v['id']})\n"
                f"- Headline: {v.get('headline', 'n/a')}\n"
                f"- Body: {v.get('body', 'n/a')}\n"
                f"- CTA: {v.get('cta', 'n/a')}\n"
                f"- Tags: {tax_str}\n"
            )
        return "\n".join(lines)

    def _extract_json(self, text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # drop ```json
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(text[start:end])
            return {"verdicts": [], "global_directions": []}
