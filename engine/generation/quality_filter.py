"""
Copy quality filter — catches AI tells and enforces brand standards.
"""

from __future__ import annotations


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
        """Filter a list of headline dicts, keeping only those that pass."""
        passed = []
        for h in headlines:
            ok, violations = self.check_headline(h["text"])
            if ok:
                passed.append(h)
            else:
                print(f"[quality] Filtered headline: '{h['text'][:40]}...' — {violations}")
        return passed

    def filter_bodies(self, bodies: list[dict]) -> list[dict]:
        """Filter body copy dicts."""
        passed = []
        for b in bodies:
            ok, violations = self.check_body(b["text"])
            if ok:
                passed.append(b)
            else:
                print(f"[quality] Filtered body: '{b['text'][:40]}...' — {violations}")
        return passed

    def filter_ctas(self, ctas: list[str]) -> list[str]:
        """Filter CTA strings."""
        passed = []
        for c in ctas:
            ok, violations = self.check_cta(c)
            if ok:
                passed.append(c)
            else:
                print(f"[quality] Filtered CTA: '{c}' — {violations}")
        return passed
