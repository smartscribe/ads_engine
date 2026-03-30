from __future__ import annotations

import itertools
import math
import random
from collections import Counter
from typing import Optional

from engine.models import CreativeBrief, CreativeTaxonomy, RegressionResult
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

EXPLOIT_RATIO = 0.8
FATIGUE_PENALTY_PER_CYCLE = 0.15
MIN_DEPLOYMENTS_FOR_TESTED = 3

DEFAULT_MIN_UNIQUE = {
    "hook_type": 3,
    "message_type": 3,
    "tone": 2,
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
        min_unique_hooks: int = DEFAULT_MIN_UNIQUE["hook_type"],
        min_unique_messages: int = DEFAULT_MIN_UNIQUE["message_type"],
        min_unique_tones: int = DEFAULT_MIN_UNIQUE["tone"],
    ) -> list[dict]:
        """
        Generate combinations of headlines x bodies x CTAs.
        Score each using regression coefficients if available.
        
        Uses explore/exploit framework:
        - 80% exploit: best predicted scores with fatigue penalty
        - 20% explore: novel, under-tested combinations

        After selection, enforces minimum diversity across hook_type,
        message_type, and tone dimensions.

        Returns list of dicts with strategy and fatigue_penalty fields.
        """
        regression = self.store.get_latest_regression()
        all_combos = list(itertools.product(headlines, bodies, ctas))
        
        n_total = brief.num_variants
        n_exploit = math.floor(n_total * EXPLOIT_RATIO)
        n_explore = n_total - n_exploit

        min_unique = {
            "hook_type": min_unique_hooks,
            "message_type": min_unique_messages,
            "tone": min_unique_tones,
        }

        if regression and regression.coefficients:
            recent_taxonomies = self.store.get_recent_deployed_taxonomies(n_cycles=3)
            feature_usage = self._compute_feature_usage(recent_taxonomies)
            all_feature_counts = self._compute_all_time_feature_counts()
            
            scored_with_penalty = []
            for combo in all_combos:
                base_score = self._predict_score(combo, regression)
                fatigue_penalty = self._compute_fatigue_penalty(combo, feature_usage)
                adjusted_score = base_score + fatigue_penalty
                exploration_score = self._compute_exploration_score(combo, all_feature_counts)
                scored_with_penalty.append({
                    "combo": combo,
                    "base_score": base_score,
                    "fatigue_penalty": fatigue_penalty,
                    "adjusted_score": adjusted_score,
                    "exploration_score": exploration_score,
                })
            
            exploit_selected = self._select_exploit(
                scored_with_penalty, n=n_exploit
            )
            
            exploit_ids = {id(s["combo"]) for s in exploit_selected}
            remaining = [s for s in scored_with_penalty if id(s["combo"]) not in exploit_ids]
            
            explore_selected = self._select_explore(remaining, n=n_explore)
            
            combined = exploit_selected + explore_selected
            combined = self._enforce_minimums(combined, scored_with_penalty, min_unique)

            results = []
            exploit_set = {id(s["combo"]) for s in exploit_selected}
            for item in combined:
                results.append({
                    "headline": item["combo"][0],
                    "body": item["combo"][1],
                    "cta": item["combo"][2],
                    "predicted_score": item["base_score"],
                    "fatigue_penalty": item["fatigue_penalty"],
                    "strategy": "exploit" if id(item["combo"]) in exploit_set else "explore",
                })
            
            return results
        else:
            selected = self._select_diverse_random(all_combos, n=n_total)
            return [
                {
                    "headline": s[0],
                    "body": s[1],
                    "cta": s[2],
                    "predicted_score": None,
                    "fatigue_penalty": 0.0,
                    "strategy": "random",
                }
                for (s, _) in selected
            ]

    def _compute_feature_usage(
        self, taxonomies: list[CreativeTaxonomy]
    ) -> Counter:
        """Count how many times each feature appears in recent deployments."""
        usage = Counter()
        for tax in taxonomies:
            usage[f"hook_type_{tax.hook_type}"] += 1
            usage[f"message_type_{tax.message_type}"] += 1
            usage[f"tone_{tax.tone}"] += 1
            usage[f"cta_type_{tax.cta_type}"] += 1
            if tax.uses_number:
                usage["uses_number"] += 1
            if tax.uses_question:
                usage["uses_question"] += 1
        return usage

    def _compute_all_time_feature_counts(self) -> Counter:
        """Count total deployments per feature across all time."""
        counts = Counter()
        from engine.models import AdStatus
        
        variants = self.store.get_all_variants()
        deployed = [v for v in variants if v.status in {AdStatus.LIVE, AdStatus.GRADUATED}]
        
        for v in deployed:
            if v.taxonomy is None:
                continue
            tax = v.taxonomy
            counts[f"hook_type_{tax.hook_type}"] += 1
            counts[f"message_type_{tax.message_type}"] += 1
            counts[f"tone_{tax.tone}"] += 1
            counts[f"cta_type_{tax.cta_type}"] += 1
            if tax.uses_number:
                counts["uses_number"] += 1
            if tax.uses_question:
                counts["uses_question"] += 1
        
        return counts

    def _compute_fatigue_penalty(
        self, combo: tuple, feature_usage: Counter
    ) -> float:
        """
        Compute penalty for features that have been heavily used recently.
        Higher usage = higher penalty (makes predicted CpFN worse).
        """
        headline, body, cta = combo
        
        features = [
            f"hook_type_{headline.get('hook_type', '')}",
            f"message_type_{body.get('message_type', '')}",
            f"tone_{body.get('tone', '')}",
        ]
        
        cta_normalized = cta.lower().replace(" ", "_").replace("'", "")
        cta_type = CTA_TYPE_MAP.get(cta_normalized, "learn_more")
        features.append(f"cta_type_{cta_type}")
        
        combined_text = headline.get("text", "") + body.get("text", "")
        if any(c.isdigit() for c in combined_text):
            features.append("uses_number")
        if "?" in headline.get("text", ""):
            features.append("uses_question")
        
        max_cycles = max((feature_usage.get(f, 0) for f in features), default=0)
        
        penalty = FATIGUE_PENALTY_PER_CYCLE * max_cycles
        return penalty

    def _compute_exploration_score(
        self, combo: tuple, all_feature_counts: Counter
    ) -> float:
        """
        Score for exploration: count of features with < 3 deployments.
        Higher = more novel/under-tested.
        """
        headline, body, cta = combo
        
        features = [
            f"hook_type_{headline.get('hook_type', '')}",
            f"message_type_{body.get('message_type', '')}",
            f"tone_{body.get('tone', '')}",
        ]
        
        cta_normalized = cta.lower().replace(" ", "_").replace("'", "")
        cta_type = CTA_TYPE_MAP.get(cta_normalized, "learn_more")
        features.append(f"cta_type_{cta_type}")
        
        under_tested = sum(
            1 for f in features
            if all_feature_counts.get(f, 0) < MIN_DEPLOYMENTS_FOR_TESTED
        )
        
        return float(under_tested)

    @staticmethod
    def _attribute_caps(n: int) -> dict[str, int]:
        """Max allowed count for any single value in a taxonomy dimension."""
        return {
            "hook_type": max(1, math.ceil(n / 6)),
            "message_type": max(1, math.ceil(n / 6)),
            "tone": max(1, math.ceil(n / 6)),
        }

    @staticmethod
    def _get_combo_attrs(combo: tuple) -> dict[str, str]:
        headline, body, cta = combo
        return {
            "hook_type": headline.get("hook_type", ""),
            "message_type": body.get("message_type", ""),
            "tone": body.get("tone", ""),
        }

    @staticmethod
    def _would_breach_cap(
        attrs: dict[str, str],
        counts: dict[str, Counter],
        caps: dict[str, int],
    ) -> bool:
        for dim, cap in caps.items():
            val = attrs.get(dim, "")
            if val and counts.get(dim, Counter()).get(val, 0) >= cap:
                return True
        return False

    @staticmethod
    def _update_counts(
        attrs: dict[str, str], counts: dict[str, Counter]
    ) -> None:
        for dim, val in attrs.items():
            if val:
                counts.setdefault(dim, Counter())[val] += 1

    def _select_exploit(
        self, scored: list[dict], n: int
    ) -> list[dict]:
        """
        Select top N by adjusted_score while enforcing diversity via:
        1. Pairwise similarity: reject candidates sharing 2+ of 4 attributes
           (hook_type, message_type, tone, CTA) with any already-selected variant.
        2. Per-attribute caps: no single hook_type/message_type/tone value may
           appear more than ceil(n/6) times in the batch.
        """
        scored_sorted = sorted(scored, key=lambda x: x["adjusted_score"])

        if len(scored_sorted) <= n:
            return scored_sorted

        caps = self._attribute_caps(n)
        dim_counts: dict[str, Counter] = {}

        selected = [scored_sorted[0]]
        first_attrs = self._get_combo_attrs(scored_sorted[0]["combo"])
        self._update_counts(first_attrs, dim_counts)

        for item in scored_sorted[1:]:
            if len(selected) >= n:
                break

            combo = item["combo"]
            headline, body, cta = combo
            attrs = self._get_combo_attrs(combo)

            if self._would_breach_cap(attrs, dim_counts, caps):
                continue

            too_similar = False
            for s_item in selected:
                s_h, s_b, s_c = s_item["combo"]
                shared = 0
                if headline.get("hook_type") == s_h.get("hook_type"):
                    shared += 1
                if body.get("message_type") == s_b.get("message_type"):
                    shared += 1
                if body.get("tone") == s_b.get("tone"):
                    shared += 1
                if cta == s_c:
                    shared += 1
                if shared >= 2:
                    too_similar = True
                    break

            if not too_similar:
                selected.append(item)
                self._update_counts(attrs, dim_counts)

        if len(selected) < n:
            for item in scored_sorted:
                if len(selected) >= n:
                    break
                if item not in selected:
                    selected.append(item)

        return selected

    def _select_explore(
        self, remaining: list[dict], n: int
    ) -> list[dict]:
        """
        Select N combinations to maximize exploration (under-tested features).
        Break ties randomly.
        """
        if n <= 0:
            return []
        
        for item in remaining:
            item["_random_tiebreaker"] = random.random()
        
        sorted_by_exploration = sorted(
            remaining,
            key=lambda x: (-x["exploration_score"], x["_random_tiebreaker"])
        )
        
        return sorted_by_exploration[:n]

    def _enforce_minimums(
        self,
        selected: list[dict],
        full_pool: list[dict],
        min_unique: dict[str, int],
    ) -> list[dict]:
        """
        Ensure the selected set meets minimum diversity requirements.
        Swaps out the most redundant item for one that adds a missing
        taxonomy value. Repeats until minimums are met or no more swaps
        are possible.
        """
        def _get_dim_value(item: dict, dim: str) -> str:
            combo = item["combo"]
            if dim == "hook_type":
                return combo[0].get("hook_type", "")
            elif dim == "message_type":
                return combo[1].get("message_type", "")
            elif dim == "tone":
                return combo[1].get("tone", "")
            return ""

        selected_ids = {id(s["combo"]) for s in selected}
        available = [s for s in full_pool if id(s["combo"]) not in selected_ids]

        for dim, required in min_unique.items():
            max_swaps = len(selected)
            swaps_done = 0

            while swaps_done < max_swaps:
                current_values = Counter(_get_dim_value(s, dim) for s in selected)
                unique_count = len([v for v in current_values if v])
                if unique_count >= required:
                    break

                needed_values = [
                    _get_dim_value(item, dim)
                    for item in available
                    if _get_dim_value(item, dim)
                    and _get_dim_value(item, dim) not in current_values
                ]
                if not needed_values:
                    break
                target_val = needed_values[0]

                candidate = next(
                    (s for s in available if _get_dim_value(s, dim) == target_val),
                    None,
                )
                if not candidate:
                    break

                most_common_val = current_values.most_common(1)[0][0] if current_values else None
                if not most_common_val or current_values[most_common_val] <= 1:
                    break

                swap_candidates = [
                    s for s in selected
                    if _get_dim_value(s, dim) == most_common_val
                ]
                swap_out = max(swap_candidates, key=lambda x: x.get("adjusted_score", 0))
                selected = [s for s in selected if id(s) != id(swap_out)]
                selected.append(candidate)
                available = [s for s in available if id(s["combo"]) != id(candidate["combo"])]
                swaps_done += 1

        return selected

    def _predict_score(
        self, combo: tuple, regression: RegressionResult
    ) -> float:
        """
        Estimate CpFN from regression coefficients.

        Coefficient names are one-hot encoded like "hook_type_question",
        "message_type_pain_point", etc.  Sum matching coefficients;
        lower total = better predicted CpFN.  Missing keys contribute 0.
        
        Also handles interaction terms like "uses_number_x_hook_type_statistic".
        """
        headline, body, cta = combo
        coefficients = regression.coefficients
        score = 0.0

        hook = headline.get("hook_type", "")
        hook_feature = f"hook_type_{hook}"
        score += coefficients.get(hook_feature, 0)

        message_type = body.get("message_type", "")
        message_feature = f"message_type_{message_type}"
        score += coefficients.get(message_feature, 0)
        
        tone = body.get("tone", "")
        tone_feature = f"tone_{tone}"
        score += coefficients.get(tone_feature, 0)

        cta_normalized = cta.lower().replace(" ", "_").replace("'", "")
        cta_type = CTA_TYPE_MAP.get(cta_normalized, "learn_more")
        cta_feature = f"cta_type_{cta_type}"
        score += coefficients.get(cta_feature, 0)

        combined_text = headline.get("text", "") + body.get("text", "")
        
        uses_number = any(c.isdigit() for c in combined_text)
        uses_question = "?" in headline.get("text", "")
        
        if uses_number:
            score += coefficients.get("uses_number", 0)
        if uses_question:
            score += coefficients.get("uses_question", 0)

        active_features = []
        if hook_feature:
            active_features.append(hook_feature)
        if message_feature:
            active_features.append(message_feature)
        if tone_feature:
            active_features.append(tone_feature)
        if cta_feature:
            active_features.append(cta_feature)
        
        boolean_values = {
            "uses_number": 1 if uses_number else 0,
            "uses_question": 1 if uses_question else 0,
        }
        
        for coef_name, coef_value in coefficients.items():
            if "_x_" not in coef_name:
                continue
            
            parts = coef_name.split("_x_")
            if len(parts) != 2:
                continue
            
            feat_a, feat_b = parts
            
            val_a = 0
            val_b = 0
            
            if feat_a in boolean_values:
                val_a = boolean_values[feat_a]
            elif feat_a in active_features:
                val_a = 1
            
            if feat_b in boolean_values:
                val_b = boolean_values[feat_b]
            elif feat_b in active_features:
                val_b = 1
            
            interaction_value = val_a * val_b
            if interaction_value > 0:
                score += coef_value

        return score

    def _select_diverse(
        self, scored: list[tuple], n: int
    ) -> list[tuple]:
        """
        Pick best-scoring combos while enforcing diversity: skip candidates
        sharing 2+ taxonomy attributes with any already-selected variant.
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
                if shared >= 2:
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
        No regression data — pick diverse random combos with:
        1. Pairwise similarity: reject candidates sharing 2+ of 4 attributes
           (hook_type, message_type, tone, CTA) with any already-selected.
        2. Per-attribute caps: same ceiling as _select_exploit.
        """
        if len(combos) <= n:
            return [(c, 0.0) for c in combos]

        random.shuffle(combos)
        caps = self._attribute_caps(n)
        dim_counts: dict[str, Counter] = {}
        selected: list[tuple] = []

        for combo in combos:
            if len(selected) >= n:
                break

            headline, body, cta = combo
            attrs = self._get_combo_attrs(combo)

            if self._would_breach_cap(attrs, dim_counts, caps):
                continue

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
                if shared >= 2:
                    too_similar = True
                    break

            if not too_similar:
                selected.append((combo, 0.0))
                self._update_counts(attrs, dim_counts)

        for combo in combos:
            if len(selected) >= n:
                break
            if not any(c == combo for c, _ in selected):
                selected.append((combo, 0.0))

        return selected

    def diversity_report(self, variants: list) -> dict:
        """
        Analyze the diversity of a generated batch of AdVariant objects.

        Checks minimum thresholds:
        - hook_types: at least 4 distinct in any batch of 20
        - tones: at least 3 distinct
        - visual_styles: at least 3 distinct

        Returns a dict with counts, coverage, and threshold_met flag.
        """
        hook_types = set()
        tones = set()
        visual_styles = set()
        message_types = set()
        cta_types = set()

        for v in variants:
            if not hasattr(v, "taxonomy") or v.taxonomy is None:
                continue
            t = v.taxonomy
            if hasattr(t, "hook_type"):
                hook_types.add(t.hook_type)
            if hasattr(t, "tone"):
                tones.add(t.tone)
            if hasattr(t, "visual_style"):
                visual_styles.add(t.visual_style)
            if hasattr(t, "message_type"):
                message_types.add(t.message_type)
            if hasattr(t, "cta_type"):
                cta_types.add(t.cta_type)

        n = len(variants)
        req_hooks = max(2, n // 5)
        req_tones = max(2, n // 7)
        req_styles = max(2, n // 7)

        meets_threshold = (
            len(hook_types) >= req_hooks
            and len(tones) >= req_tones
            and len(visual_styles) >= req_styles
        )

        return {
            "total_variants": n,
            "hook_types": sorted(hook_types),
            "tones": sorted(tones),
            "visual_styles": sorted(visual_styles),
            "message_types": sorted(message_types),
            "cta_types": sorted(cta_types),
            "counts": {
                "hook_types": len(hook_types),
                "tones": len(tones),
                "visual_styles": len(visual_styles),
                "message_types": len(message_types),
                "cta_types": len(cta_types),
            },
            "thresholds": {
                "hook_types": {"required": req_hooks, "actual": len(hook_types), "met": len(hook_types) >= req_hooks},
                "tones": {"required": req_tones, "actual": len(tones), "met": len(tones) >= req_tones},
                "visual_styles": {"required": req_styles, "actual": len(visual_styles), "met": len(visual_styles) >= req_styles},
            },
            "threshold_met": meets_threshold,
            "missing_hook_types": [
                h for h in ["question", "statistic", "testimonial", "provocative_claim", "scenario", "direct_benefit"]
                if h not in hook_types
            ],
        }
