from __future__ import annotations

import itertools
import random
from typing import Optional

from engine.models import CreativeBrief, RegressionResult
from engine.store import Store

CTA_TYPE_MAP = {
    "try_free": "try_free",
    "try_it_free": "try_free",
    "learn_more": "learn_more",
    "see_how": "see_how",
    "see_how_it_works": "see_how",
    "start_saving_time": "start_saving_time",
    "watch_demo": "watch_video",
    "watch_video": "watch_video",
    "book_a_demo": "book_demo",
    "book_demo": "book_demo",
    "get_started": "try_free",
}


class VariantMatrix:
    def __init__(self, store: Store):
        self.store = store

    def generate_scored_matrix(
        self,
        headlines: list[dict],
        bodies: list[dict],
        ctas: list[str],
        brief: CreativeBrief,
    ) -> list[dict]:
        """
        Generate combinations of headlines x bodies x CTAs.
        Score each using regression coefficients if available.
        Select top N (brief.num_variants) with diversity constraint.

        Returns list of dicts: [{"headline": dict, "body": dict, "cta": str, "predicted_score": float}, ...]
        """
        regression = self.store.get_latest_regression()
        all_combos = list(itertools.product(headlines, bodies, ctas))

        if regression and regression.coefficients:
            scored = [
                (combo, self._predict_score(combo, regression))
                for combo in all_combos
            ]
            scored.sort(key=lambda x: x[1])  # lower predicted CpFN = better
            selected = self._select_diverse(scored, n=brief.num_variants)
        else:
            selected = self._select_diverse_random(all_combos, n=brief.num_variants)

        return [
            {
                "headline": s[0],
                "body": s[1],
                "cta": s[2],
                "predicted_score": score if regression else None,
            }
            for (s, score) in selected
        ]

    def _predict_score(
        self, combo: tuple, regression: RegressionResult
    ) -> float:
        """
        Estimate CpFN from regression coefficients.

        Coefficient names are one-hot encoded like "hook_type_question",
        "message_type_pain_point", etc.  Sum matching coefficients;
        lower total = better predicted CpFN.  Missing keys contribute 0.
        """
        headline, body, cta = combo
        coefficients = regression.coefficients
        score = 0.0

        hook = headline.get("hook_type", "")
        score += coefficients.get(f"hook_type_{hook}", 0)

        score += coefficients.get(f"message_type_{body.get('message_type', '')}", 0)
        score += coefficients.get(f"tone_{body.get('tone', '')}", 0)

        cta_normalized = cta.lower().replace(" ", "_").replace("'", "")
        cta_type = CTA_TYPE_MAP.get(cta_normalized, "learn_more")
        score += coefficients.get(f"cta_type_{cta_type}", 0)

        combined_text = headline.get("text", "") + body.get("text", "")
        if any(c.isdigit() for c in combined_text):
            score += coefficients.get("uses_number", 0)
        if "?" in headline.get("text", ""):
            score += coefficients.get("uses_question", 0)

        return score

    def _select_diverse(
        self, scored: list[tuple], n: int
    ) -> list[tuple]:
        """
        Pick best-scoring combos while enforcing diversity: skip candidates
        sharing 3+ taxonomy attributes with any already-selected variant.
        Falls back to top scorers if the constraint is too strict.
        """
        if len(scored) <= n:
            return scored

        selected = [scored[0]]

        for combo, score in scored[1:]:
            if len(selected) >= n:
                break

            headline, body, cta = combo
            too_similar = False

            for s_combo, _ in selected:
                s_h, s_b, s_c = s_combo
                shared = 0
                if headline.get("hook_type") == s_h.get("hook_type"):
                    shared += 1
                if body.get("message_type") == s_b.get("message_type"):
                    shared += 1
                if body.get("tone") == s_b.get("tone"):
                    shared += 1
                if cta == s_c:
                    shared += 1
                if shared >= 3:
                    too_similar = True
                    break

            if not too_similar:
                selected.append((combo, score))

        # Backfill from top scorers if diversity was too restrictive
        if len(selected) < n:
            for combo, score in scored:
                if len(selected) >= n:
                    break
                if (combo, score) not in selected:
                    selected.append((combo, score))

        return selected

    def _select_diverse_random(
        self, combos: list[tuple], n: int
    ) -> list[tuple]:
        """
        No regression data — pick diverse random combos.
        Stricter similarity threshold (2+ shared attrs) since there's no
        scoring signal to differentiate otherwise.
        """
        if len(combos) <= n:
            return [(c, 0.0) for c in combos]

        random.shuffle(combos)
        selected: list[tuple] = []

        for combo in combos:
            if len(selected) >= n:
                break

            headline, body, cta = combo
            too_similar = False

            for s_combo, _ in selected:
                s_h, s_b, s_c = s_combo
                shared = 0
                if headline.get("hook_type") == s_h.get("hook_type"):
                    shared += 1
                if body.get("message_type") == s_b.get("message_type"):
                    shared += 1
                if cta == s_c:
                    shared += 1
                if shared >= 2:
                    too_similar = True
                    break

            if not too_similar:
                selected.append((combo, 0.0))

        for combo in combos:
            if len(selected) >= n:
                break
            if not any(c == combo for c, _ in selected):
                selected.append((combo, 0.0))

        return selected
