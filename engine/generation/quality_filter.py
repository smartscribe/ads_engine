"""
Copy quality filter — catches AI tells, brand violations, and enforces standards.

Quality gates:
- AI tells (23 phrases that signal LLM-generated text)
- Generic phrases (12 marketing clichés)
- Em dashes (brand voice prohibits them — use periods, commas, colons)
- Character limits (headline ≤ 40, CTA ≤ 20)
- Empty text
"""

from __future__ import annotations

import re


class CopyQualityFilter:
    AI_TELLS = [
        "revolutionize", "leverage", "streamline", "cutting-edge", "game-changer",
        "transform your", "empower", "innovative", "seamless", "state-of-the-art",
        "harness", "unlock your", "paradigm", "synergy", "holistic solution",
        "next-level", "supercharge", "reimagine", "disruptive", "optimize your",
        "elevate your", "robust", "scalable solution",
    ]

    GENERIC_PHRASES = [
        "in today's fast-paced world", "take your practice to the next level",
        "the future of", "don't miss out", "act now", "limited time",
        "what if i told you", "imagine a world", "tired of",
        "say goodbye to", "introducing the", "are you ready to",
    ]

    @staticmethod
    def fix_em_dashes(text: str) -> str:
        """Replace em dashes with periods — a hard brand voice rule."""
        if "—" not in text:
            return text
        fixed = text.replace("—", ". ")
        # Clean up double periods and excess whitespace
        fixed = re.sub(r"\.\s*\.", ".", fixed)
        fixed = re.sub(r"\s{2,}", " ", fixed)
        return fixed.strip()

    def check(self, text: str, char_limit: int = None) -> tuple[bool, list[str]]:
        """
        Check a piece of copy for quality issues.
        Returns (passes, violations). Passes if zero violations.
        """
        violations = []

        if char_limit and len(text) > char_limit:
            violations.append(f"Over {char_limit} char limit ({len(text)} chars)")

        text_lower = text.lower()
        for tell in self.AI_TELLS:
            if tell.lower() in text_lower:
                violations.append(f"AI tell: '{tell}'")

        for phrase in self.GENERIC_PHRASES:
            if phrase.lower() in text_lower:
                violations.append(f"Generic phrase: '{phrase}'")

        # Em dashes are a brand voice violation
        if "—" in text:
            violations.append("Em dash detected (use periods, commas, or colons instead)")

        if not text.strip():
            violations.append("Empty or whitespace-only text")

        return (len(violations) == 0, violations)

    def check_headline(self, text: str) -> tuple[bool, list[str]]:
        """Check headline with Meta's 40-char optimal limit."""
        return self.check(text, char_limit=40)

    def check_body(self, text: str) -> tuple[bool, list[str]]:
        """Check body for AI tells and generic phrases only (Meta allows ~2200 chars for primary text)."""
        return self.check(text, char_limit=None)

    def check_cta(self, text: str) -> tuple[bool, list[str]]:
        """Check CTA button text with 20-char limit."""
        return self.check(text, char_limit=20)

    def filter_headlines(self, headlines: list[dict]) -> list[dict]:
        """
        Filter headline dicts. Auto-fixes em dashes before checking.
        Deduplicates: only keeps the first occurrence of each headline text.
        """
        passed = []
        seen_texts = set()
        for h in headlines:
            # Auto-fix em dashes
            h["text"] = self.fix_em_dashes(h["text"])

            # Deduplicate
            if h["text"].lower().strip() in seen_texts:
                continue
            seen_texts.add(h["text"].lower().strip())

            ok, violations = self.check_headline(h["text"])
            if ok:
                passed.append(h)
            else:
                print(f"[quality] Filtered headline: '{h['text'][:40]}...' — {violations}")
        return passed

    def filter_bodies(self, bodies: list[dict]) -> list[dict]:
        """
        Filter body copy dicts. Auto-fixes em dashes before checking.
        Deduplicates by text content.
        """
        passed = []
        seen_texts = set()
        for b in bodies:
            # Auto-fix em dashes
            b["text"] = self.fix_em_dashes(b["text"])

            # Deduplicate
            text_key = b["text"].lower().strip()[:100]  # first 100 chars for dedup
            if text_key in seen_texts:
                continue
            seen_texts.add(text_key)

            ok, violations = self.check_body(b["text"])
            if ok:
                passed.append(b)
            else:
                print(f"[quality] Filtered body: '{b['text'][:40]}...' — {violations}")
        return passed

    def filter_ctas(self, ctas: list[str]) -> list[str]:
        """Filter CTA strings. Deduplicates."""
        passed = []
        seen = set()
        for c in ctas:
            c_lower = c.lower().strip()
            if c_lower in seen:
                continue
            seen.add(c_lower)

            ok, violations = self.check_cta(c)
            if ok:
                passed.append(c)
            else:
                print(f"[quality] Filtered CTA: '{c}' — {violations}")
        return passed
