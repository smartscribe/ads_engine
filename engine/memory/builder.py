"""
Memory Builder — assembles the creative memory from all data sources.

Runs after every regression cycle and review batch. Builds the three-layer
memory structure from regression results, review history, and deployment data.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Optional
import hashlib
import json

from engine.memory.models import (
    CreativeMemory,
    StatisticalMemory,
    EditorialMemory,
    MarketMemory,
    GenerationContext,
    PatternInsight,
    InteractionInsight,
    FatigueAlert,
    TimestampedCoefficient,
    ApprovalCluster,
    RejectionRule,
    ReviewerProfile,
    CombinationStats,
)
from engine.models import AdStatus, RegressionResult

if TYPE_CHECKING:
    from engine.store import Store


CONFIDENCE_TIERS = {
    "high": 0.01,      # p < 0.01
    "moderate": 0.05,  # p < 0.05
    "directional": 0.1 # p < 0.10
}

FEATURE_RULE_TEMPLATES = {
    "hook_type_statistic": "Lead with a specific statistic or number in the headline",
    "hook_type_question": "Open with a direct question to the clinician",
    "hook_type_testimonial": "Feature a testimonial or quote",
    "hook_type_provocative_claim": "Make a bold, provocative claim",
    "hook_type_scenario": "Paint a relatable scenario",
    "hook_type_direct_benefit": "State the benefit directly",
    "message_type_pain_point": "Lead with the documentation pain point",
    "message_type_value_prop": "Lead with the core value proposition",
    "message_type_social_proof": "Include social proof (other clinicians, usage stats)",
    "message_type_urgency": "Create urgency around the documentation burden",
    "message_type_education": "Take an educational approach",
    "message_type_comparison": "Compare to the status quo or alternatives",
    "tone_clinical": "Use clinical, professional tone",
    "tone_warm": "Use warm, empathetic tone",
    "tone_urgent": "Use urgent, action-oriented tone",
    "tone_playful": "Use playful, light tone",
    "tone_authoritative": "Use authoritative, expert tone",
    "tone_empathetic": "Use empathetic, understanding tone",
    "uses_number": "Include a specific number (hours saved, percentage, count)",
    "uses_question": "Use a question format",
    "uses_first_person": "Use first person ('I', 'my')",
    "uses_social_proof": "Include social proof elements",
    "cta_type_try_free": "Use a 'try free' call to action",
    "cta_type_book_demo": "Use a 'book demo' call to action",
    "cta_type_learn_more": "Use a 'learn more' call to action",
    "cta_type_see_how": "Use a 'see how it works' call to action",
    "visual_style_photography": "Use real photography",
    "visual_style_illustration": "Use illustrations",
    "visual_style_screen_capture": "Use product UI screenshots",
    "color_mood_brand_primary": "Use brand primary colors",
    "color_mood_warm_earth": "Use warm earth tones",
}


class MemoryBuilder:
    """Assembles CreativeMemory from all data sources."""

    def __init__(self, store: "Store"):
        self.store = store

    def build(self) -> CreativeMemory:
        """Assemble the full creative memory from all data sources."""
        print("[memory_builder] Building creative memory...")

        statistical = self._build_statistical_memory()
        editorial = self._build_editorial_memory()
        market = self._build_market_memory()

        # Apply memory decay and archiving (M3)
        statistical = self._apply_memory_decay(statistical)

        data_quality = self._assess_data_quality(statistical, editorial)

        memory = CreativeMemory(
            statistical=statistical,
            editorial=editorial,
            market=market,
            data_quality_score=data_quality,
        )

        print(f"[memory_builder] Built memory: {len(statistical.winning_patterns)} winning patterns, "
              f"{len(editorial.approval_clusters)} approval clusters, "
              f"{len(market.combination_stats)} combinations tracked")

        return memory

    def _apply_memory_decay(self, statistical: StatisticalMemory) -> StatisticalMemory:
        """
        Apply temporal decay to statistical memory patterns (M3).

        - Patterns older than 60 days: downgrade confidence_tier by one level
        - Patterns with LOW confidence + >90 days old: move to archive

        Confidence tier downgrade sequence:
          high → moderate → directional → unreliable
        """
        today = date.today()
        tier_downgrade = {
            "high": "moderate",
            "moderate": "directional",
            "directional": "unreliable",
            "insignificant": "unreliable",
        }

        active_winning = []
        archived_winning = []
        active_losing = []
        archived_losing = []

        for patterns, active_list, archived_list in [
            (statistical.winning_patterns, active_winning, archived_winning),
            (statistical.losing_patterns, active_losing, archived_losing),
        ]:
            for p in patterns:
                snapshot_date = p.memory_snapshot_date or p.first_significant_date or today
                days_old = (today - snapshot_date).days

                if days_old > 60:
                    current_tier = p.confidence_tier
                    p.confidence_tier = tier_downgrade.get(current_tier, "unreliable")

                if p.confidence_tier in ("unreliable", "insignificant") and days_old > 90:
                    archived_list.append(p)
                    print(f"[memory_builder] Archiving stale pattern: {p.feature} ({days_old}d old, {p.confidence_tier})")
                else:
                    active_list.append(p)

        # Archive stale patterns if any
        if archived_winning or archived_losing:
            self._archive_patterns(archived_winning + archived_losing, reason="stale_low_confidence")

        statistical.winning_patterns = active_winning
        statistical.losing_patterns = active_losing
        return statistical

    def _archive_patterns(self, patterns: list, reason: str) -> None:
        """Move patterns to archive storage (M3)."""
        import json
        from pathlib import Path

        archive_dir = Path(self.store.base) / "memory" / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        archive_file = archive_dir / f"{date.today()}.json"
        archive_data = {
            "archived_at": date.today().isoformat(),
            "reason": reason,
            "count": len(patterns),
            "patterns": [
                {
                    "feature": p.feature,
                    "confidence_tier": p.confidence_tier,
                    "rule": p.rule,
                    "snapshot_date": p.memory_snapshot_date.isoformat() if p.memory_snapshot_date else None,
                }
                for p in patterns
            ],
        }

        try:
            existing = []
            if archive_file.exists():
                existing = json.loads(archive_file.read_text())
                if not isinstance(existing, list):
                    existing = [existing]
            existing.append(archive_data)
            archive_file.write_text(json.dumps(existing, indent=2))
        except Exception as e:
            print(f"[memory_builder] Archive write failed: {e}")

    def _build_statistical_memory(self) -> StatisticalMemory:
        """Convert regression results into prompt-ready insights."""
        current = self.store.get_latest_regression()
        if not current:
            return StatisticalMemory.empty()
        
        historical = self._get_regression_history()
        coefficient_history = self._build_coefficient_history(historical)
        
        winning = []
        for feature in current.top_positive_features[:10]:
            insight = self._build_pattern_insight(
                feature, current, historical, coefficient_history, is_positive=True
            )
            if insight:
                winning.append(insight)
        
        losing = []
        for feature in current.top_negative_features[:10]:
            insight = self._build_pattern_insight(
                feature, current, historical, coefficient_history, is_positive=False
            )
            if insight:
                losing.append(insight)
        
        fatiguing = self._detect_fatigue_patterns(current, historical, coefficient_history)
        interactions = self._extract_interaction_insights(current)
        
        return StatisticalMemory(
            winning_patterns=winning,
            losing_patterns=losing,
            coefficient_history=coefficient_history,
            fatiguing_patterns=fatiguing,
            interaction_insights=interactions,
            r_squared=current.r_squared,
            n_observations=current.n_observations,
            last_run_date=current.run_date,
        )

    def _build_pattern_insight(
        self,
        feature: str,
        current: RegressionResult,
        historical: list[RegressionResult],
        coefficient_history: dict,
        is_positive: bool,
    ) -> Optional[PatternInsight]:
        """Build a fully-rendered PatternInsight from a feature."""
        coeff = current.coefficients.get(feature, 0)
        p_value = current.p_values.get(feature, 1)

        # Use bootstrap-validated confidence tiers when available (R1),
        # otherwise fall back to p-value-based tiering
        if current.confidence_tiers and feature in current.confidence_tiers:
            confidence_tier = current.confidence_tiers[feature]
        else:
            confidence_tier = self._get_confidence_tier(p_value)
        
        positive_examples, negative_examples = self._find_example_ads(feature)
        
        trend = self._detect_trend(feature, coefficient_history)
        first_sig_date = self._first_significant_date(feature, historical)
        cycles_sig = self._count_significant_cycles(feature, historical)
        
        rule = self._feature_to_rule(feature, coeff)
        evidence = f"Coefficient: {coeff:.1f}, p={p_value:.3f}, n={current.n_observations}"
        
        return PatternInsight(
            feature=feature,
            coefficient=coeff,
            p_value=p_value,
            confidence_tier=confidence_tier,
            n_observations=current.n_observations,
            rule=rule,
            evidence=evidence,
            positive_examples=positive_examples,
            negative_examples=negative_examples,
            trend=trend,
            first_significant_date=first_sig_date,
            cycles_significant=cycles_sig,
            memory_snapshot_date=date.today(),
        )

    def _find_example_ads(self, feature: str, n: int = 3) -> tuple[list[str], list[str]]:
        """Find actual ad examples that match a feature."""
        dimension, value = self._parse_feature(feature)
        if dimension is None:
            return [], []
        
        variants = self.store.get_all_variants()
        matching = []
        
        for v in variants:
            if v.taxonomy is None:
                continue
            
            tax_dict = v.taxonomy.model_dump()
            
            if dimension in tax_dict:
                tax_value = tax_dict[dimension]
                if isinstance(tax_value, bool):
                    matches = tax_value == (value == "True")
                elif hasattr(tax_value, "value"):
                    matches = tax_value.value == value
                else:
                    matches = str(tax_value) == value
                
                if matches:
                    snapshots = self.store.get_snapshots_for_variant(v.id)
                    cpfn = None
                    if snapshots:
                        total_spend = sum(s.spend for s in snapshots)
                        total_fn = sum(s.first_note_completions for s in snapshots)
                        if total_fn > 0:
                            cpfn = total_spend / total_fn
                    
                    matching.append({
                        "headline": v.headline,
                        "body": v.primary_text,
                        "cpfn": cpfn,
                        "status": v.status.value,
                    })
        
        matching_with_cpfn = [m for m in matching if m["cpfn"] is not None]
        matching_with_cpfn.sort(key=lambda x: x["cpfn"])
        
        positive = [m["headline"] for m in matching_with_cpfn[:n]]
        negative = [m["headline"] for m in matching_with_cpfn[-n:]] if len(matching_with_cpfn) > n else []
        
        if not positive:
            approved = [m for m in matching if m["status"] in ("approved", "graduated")]
            positive = [m["headline"] for m in approved[:n]]
        
        if not negative:
            rejected = [m for m in matching if m["status"] == "rejected"]
            negative = [m["headline"] for m in rejected[:n]]
        
        return positive, negative

    def _parse_feature(self, feature: str) -> tuple[Optional[str], Optional[str]]:
        """Parse feature name into dimension and value."""
        boolean_features = ["uses_number", "uses_question", "uses_first_person", "uses_social_proof"]
        if feature in boolean_features:
            return (feature, "True")
        
        if "_x_" in feature:
            return (None, None)
        
        prefixes = [
            "message_type_", "hook_type_", "cta_type_", "tone_",
            "visual_style_", "subject_matter_", "color_mood_", "text_density_",
            "format_", "platform_", "placement_",
        ]
        
        for prefix in prefixes:
            if feature.startswith(prefix):
                dimension = prefix.rstrip("_")
                value = feature[len(prefix):]
                return (dimension, value)
        
        return (None, None)

    def _feature_to_rule(self, feature: str, coefficient: float) -> str:
        """Translate a feature name into a human-readable rule."""
        base_rule = FEATURE_RULE_TEMPLATES.get(feature, f"Use {feature}")
        direction = "lowers CpFN" if coefficient < 0 else "increases CpFN"
        return f"{base_rule} — this {direction} by ~${abs(coefficient):.0f}"

    def _get_confidence_tier(self, p_value: float) -> str:
        """Determine confidence tier from p-value."""
        if p_value < CONFIDENCE_TIERS["high"]:
            return "high"
        elif p_value < CONFIDENCE_TIERS["moderate"]:
            return "moderate"
        elif p_value < CONFIDENCE_TIERS["directional"]:
            return "directional"
        return "insignificant"

    def _get_regression_history(self) -> list[RegressionResult]:
        """Load all historical regression results."""
        from pathlib import Path
        
        regression_dir = self.store.regression_dir
        files = sorted(regression_dir.glob("regression_*.json"), reverse=True)
        
        results = []
        for f in files[:30]:
            try:
                result = RegressionResult.model_validate_json(f.read_text())
                results.append(result)
            except Exception:
                continue
        
        return results

    def _build_coefficient_history(
        self, historical: list[RegressionResult]
    ) -> dict[str, list[TimestampedCoefficient]]:
        """Build coefficient history from all regression runs."""
        history: dict[str, list[TimestampedCoefficient]] = defaultdict(list)
        
        for result in historical:
            for feature, coeff in result.coefficients.items():
                p_value = result.p_values.get(feature, 1)
                history[feature].append(TimestampedCoefficient(
                    coefficient=coeff,
                    p_value=p_value,
                    run_date=result.run_date,
                    n_observations=result.n_observations,
                ))
        
        for feature in history:
            history[feature].sort(key=lambda x: x.run_date, reverse=True)
        
        return dict(history)

    def _detect_trend(self, feature: str, coefficient_history: dict) -> str:
        """Detect trend from coefficient history."""
        if feature not in coefficient_history:
            return "stable"
        
        history = coefficient_history[feature]
        if len(history) < 3:
            return "stable"
        
        recent = [h.coefficient for h in history[:3]]
        older = [h.coefficient for h in history[3:6]] if len(history) >= 6 else recent
        
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        
        if abs(older_avg) < 0.01:
            return "stable"
        
        change_pct = (recent_avg - older_avg) / abs(older_avg)
        
        if recent_avg < 0:
            if change_pct < -0.2:
                return "strengthening"
            elif change_pct > 0.2:
                return "fatiguing"
        else:
            if change_pct > 0.2:
                return "strengthening"
            elif change_pct < -0.2:
                return "fatiguing"
        
        return "stable"

    def _first_significant_date(
        self, feature: str, historical: list[RegressionResult]
    ) -> Optional[date]:
        """Find the first date a feature was significant."""
        for result in reversed(historical):
            if feature in result.p_values:
                if result.p_values[feature] < 0.05:
                    return result.run_date
        return None

    def _count_significant_cycles(
        self, feature: str, historical: list[RegressionResult]
    ) -> int:
        """Count consecutive significant cycles."""
        count = 0
        for result in historical:
            if feature in result.p_values and result.p_values[feature] < 0.05:
                count += 1
            else:
                break
        return count

    def _detect_fatigue_patterns(
        self,
        current: RegressionResult,
        historical: list[RegressionResult],
        coefficient_history: dict,
    ) -> list[FatigueAlert]:
        """Detect patterns showing signs of fatigue."""
        alerts = []
        
        for feature in current.top_positive_features:
            trend = self._detect_trend(feature, coefficient_history)
            if trend != "fatiguing":
                continue
            
            history = coefficient_history.get(feature, [])
            if len(history) < 2:
                continue
            
            current_coeff = history[0].coefficient
            historical_avg = sum(h.coefficient for h in history[1:]) / len(history[1:])
            delta_pct = ((current_coeff - historical_avg) / abs(historical_avg)) * 100 if historical_avg != 0 else 0
            
            deployments = self._count_deployments(feature)
            first_deployed = self._first_deployment_date(feature)
            
            if deployments >= 3:
                recommendation = "Refresh the angle — same insight, new creative execution"
            elif delta_pct > 50:
                recommendation = "Retire this pattern — significant degradation"
            else:
                recommendation = "Reduce usage — early fatigue signals"
            
            alerts.append(FatigueAlert(
                feature=feature,
                current_coefficient=current_coeff,
                historical_avg=historical_avg,
                delta_pct=delta_pct,
                deployments=deployments,
                first_deployed=first_deployed,
                recommendation=recommendation,
            ))
        
        return alerts

    def _count_deployments(self, feature: str) -> int:
        """Count how many times a feature has been deployed."""
        dimension, value = self._parse_feature(feature)
        if dimension is None:
            return 0
        
        count = 0
        for v in self.store.get_all_variants():
            if v.status not in (AdStatus.LIVE, AdStatus.GRADUATED):
                continue
            if v.taxonomy is None:
                continue
            
            tax_dict = v.taxonomy.model_dump()
            if dimension in tax_dict:
                tax_value = tax_dict[dimension]
                if isinstance(tax_value, bool):
                    if tax_value == (value == "True"):
                        count += 1
                elif hasattr(tax_value, "value"):
                    if tax_value.value == value:
                        count += 1
                elif str(tax_value) == value:
                    count += 1
        
        return count

    def _first_deployment_date(self, feature: str) -> Optional[date]:
        """Find the first deployment date for a feature."""
        dimension, value = self._parse_feature(feature)
        if dimension is None:
            return None
        
        earliest = None
        for v in self.store.get_all_variants():
            if v.status not in (AdStatus.LIVE, AdStatus.GRADUATED):
                continue
            if v.taxonomy is None:
                continue
            
            tax_dict = v.taxonomy.model_dump()
            if dimension in tax_dict:
                tax_value = tax_dict[dimension]
                matches = False
                if isinstance(tax_value, bool):
                    matches = tax_value == (value == "True")
                elif hasattr(tax_value, "value"):
                    matches = tax_value.value == value
                else:
                    matches = str(tax_value) == value
                
                if matches:
                    created = v.created_at.date()
                    if earliest is None or created < earliest:
                        earliest = created
        
        return earliest

    def _extract_interaction_insights(self, current: RegressionResult) -> list[InteractionInsight]:
        """Extract interaction term insights from regression."""
        insights = []
        
        for feature, coeff in current.coefficients.items():
            if "_x_" not in feature:
                continue
            
            p_value = current.p_values.get(feature, 1)
            if p_value >= 0.1:
                continue
            
            parts = feature.split("_x_")
            if len(parts) != 2:
                continue
            
            feat_a, feat_b = parts
            
            if coeff < 0:
                interpretation = f"{feat_a} and {feat_b} work well together — combined effect lowers CpFN"
            else:
                interpretation = f"{feat_a} and {feat_b} conflict — combined effect raises CpFN"
            
            insights.append(InteractionInsight(
                feature_a=feat_a,
                feature_b=feat_b,
                interaction_name=feature,
                coefficient=coeff,
                p_value=p_value,
                interpretation=interpretation,
            ))
        
        insights.sort(key=lambda x: abs(x.coefficient), reverse=True)
        return insights[:10]

    def _build_editorial_memory(self) -> EditorialMemory:
        """Build editorial memory from review history."""
        variants = self.store.get_all_variants()

        approved = [v for v in variants if v.status in (AdStatus.APPROVED, AdStatus.GRADUATED)]
        rejected = [v for v in variants if v.status == AdStatus.REJECTED]

        approval_clusters = self._cluster_approvals(approved)
        rejection_rules = self._extract_rejection_rules(rejected)
        reviewer_profiles = self._build_reviewer_profiles(variants)

        # Load synthesized reviewer preferences from voice notes (M2)
        synthesized = self._load_synthesized_preferences()
        if synthesized:
            reviewer_profiles = self._merge_synthesized_preferences(reviewer_profiles, synthesized)

        return EditorialMemory(
            approval_clusters=approval_clusters,
            rejection_rules=rejection_rules,
            reviewer_profiles=reviewer_profiles,
            total_approvals=len(approved),
            total_rejections=len(rejected),
        )

    def _load_synthesized_preferences(self) -> list[dict]:
        """Load synthesized reviewer preferences from voice notes (M2)."""
        import json
        from pathlib import Path

        synth_path = Path(self.store.base) / "memory" / "voice_notes" / "synthesized.json"
        if not synth_path.exists():
            return []
        try:
            data = json.loads(synth_path.read_text())
            return data.get("preferences", [])
        except Exception:
            return []

    def _merge_synthesized_preferences(
        self, existing_profiles: list, synthesized: list[dict]
    ) -> list:
        """Merge synthesized voice note preferences into reviewer profiles."""
        from engine.memory.models import ReviewerProfile

        reviewer_prefs: dict[str, list] = {}
        for pref in synthesized:
            reviewer = pref.get("reviewer", "unknown")
            if reviewer not in reviewer_prefs:
                reviewer_prefs[reviewer] = []
            reviewer_prefs[reviewer].append(pref)

        for reviewer, prefs in reviewer_prefs.items():
            preferred = [p for p in prefs if p.get("direction") == "prefer"]
            disliked = [p for p in prefs if p.get("direction") == "avoid"]

            existing = next((p for p in existing_profiles if p.reviewer == reviewer), None)
            if existing is None:
                existing = ReviewerProfile(
                    reviewer=reviewer,
                    approval_rate=0.5,
                    preferred_patterns=[{"rule": p["rule"], "confidence": p["confidence"]} for p in preferred],
                    disliked_patterns=[{"rule": p["rule"], "confidence": p["confidence"]} for p in disliked],
                    sample_size=len(prefs),
                )
                existing_profiles.append(existing)
            else:
                if preferred:
                    existing.preferred_patterns.extend(
                        {"rule": p["rule"], "confidence": p["confidence"]} for p in preferred
                    )
                if disliked:
                    existing.disliked_patterns.extend(
                        {"rule": p["rule"], "confidence": p["confidence"]} for p in disliked
                    )

        return existing_profiles

    def _cluster_approvals(self, approved: list) -> list[ApprovalCluster]:
        """Cluster approved ads by taxonomy signature."""
        clusters: dict[str, list] = defaultdict(list)
        
        for v in approved:
            if v.taxonomy is None:
                continue
            
            signature = {
                "hook_type": v.taxonomy.hook_type,
                "message_type": v.taxonomy.message_type,
                "tone": v.taxonomy.tone,
                "uses_number": v.taxonomy.uses_number,
            }
            
            sig_hash = hashlib.md5(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:8]
            clusters[sig_hash].append({
                "variant": v,
                "signature": signature,
            })
        
        result = []
        for sig_hash, items in clusters.items():
            if not items:
                continue
            
            items_with_perf = []
            for item in items:
                v = item["variant"]
                snapshots = self.store.get_snapshots_for_variant(v.id)
                cpfn = None
                if snapshots:
                    total_spend = sum(s.spend for s in snapshots)
                    total_fn = sum(s.first_note_completions for s in snapshots)
                    if total_fn > 0:
                        cpfn = total_spend / total_fn
                items_with_perf.append({**item, "cpfn": cpfn})
            
            items_with_perf.sort(key=lambda x: x["cpfn"] if x["cpfn"] else float("inf"))
            best = items_with_perf[0]["variant"]
            
            notes = [item["variant"].review_notes for item in items_with_perf if item["variant"].review_notes]
            notes_summary = notes[0] if notes else None
            
            avg_perf = None
            cpfns = [x["cpfn"] for x in items_with_perf if x["cpfn"]]
            if cpfns:
                avg_perf = sum(cpfns) / len(cpfns)
            
            result.append(ApprovalCluster(
                signature=items[0]["signature"],
                count=len(items),
                representative_headline=best.headline,
                representative_body=best.primary_text,
                representative_cta=best.cta_button,
                reviewer_notes_summary=notes_summary,
                avg_performance=avg_perf,
            ))
        
        result.sort(key=lambda x: -x.count)
        return result[:20]

    def _extract_rejection_rules(self, rejected: list) -> list[RejectionRule]:
        """Extract generalized rules from rejections."""
        pattern_rejections: dict[str, list] = defaultdict(list)
        
        for v in rejected:
            if v.taxonomy is None or not v.review_notes:
                continue
            
            pattern = {
                "tone": v.taxonomy.tone,
                "message_type": v.taxonomy.message_type,
            }
            
            pattern_hash = hashlib.md5(json.dumps(pattern, sort_keys=True).encode()).hexdigest()[:8]
            pattern_rejections[pattern_hash].append({
                "pattern": pattern,
                "notes": v.review_notes,
            })
        
        rules = []
        for pattern_hash, items in pattern_rejections.items():
            if len(items) < 2:
                continue
            
            pattern = items[0]["pattern"]
            notes = [item["notes"] for item in items]
            
            rule = f"Don't combine {pattern['tone']} tone with {pattern['message_type']} messaging"
            
            confidence = "high" if len(items) >= 5 else ("moderate" if len(items) >= 3 else "tentative")
            
            rules.append(RejectionRule(
                rule=rule,
                pattern=pattern,
                rejection_count=len(items),
                example_notes=notes[:3],
                confidence=confidence,
            ))
        
        rules.sort(key=lambda x: -x.rejection_count)
        return rules[:10]

    def _build_reviewer_profiles(self, variants: list) -> dict[str, ReviewerProfile]:
        """Build profiles for each reviewer."""
        reviewer_data: dict[str, dict] = defaultdict(lambda: {
            "approvals": [],
            "rejections": [],
            "last_date": None,
        })
        
        for v in variants:
            if v.reviewer is None:
                continue
            
            data = reviewer_data[v.reviewer]
            if v.status in (AdStatus.APPROVED, AdStatus.GRADUATED):
                data["approvals"].append(v)
            elif v.status == AdStatus.REJECTED:
                data["rejections"].append(v)
            
            if v.reviewed_at:
                review_date = v.reviewed_at.date()
                if data["last_date"] is None or review_date > data["last_date"]:
                    data["last_date"] = review_date
        
        profiles = {}
        for reviewer, data in reviewer_data.items():
            total = len(data["approvals"]) + len(data["rejections"])
            if total < 3:
                continue
            
            approval_rate = len(data["approvals"]) / total if total > 0 else 0
            
            profiles[reviewer] = ReviewerProfile(
                reviewer=reviewer,
                approval_rate=approval_rate,
                preferred_patterns=[],
                disliked_patterns=[],
                sample_size=total,
                last_review_date=data["last_date"],
            )
        
        return profiles

    def _build_market_memory(self) -> MarketMemory:
        """Build market memory from deployment and performance data."""
        combination_stats = self._build_combination_stats()
        
        least_tested = sorted(
            [(sig, stats.deployment_count) for sig, stats in combination_stats.items()],
            key=lambda x: x[1]
        )[:10]
        
        return MarketMemory(
            combination_stats=combination_stats,
            least_tested_combinations=least_tested,
        )

    def _build_combination_stats(self) -> dict[str, CombinationStats]:
        """Build stats for each taxonomy combination."""
        stats: dict[str, dict] = defaultdict(lambda: {
            "count": 0,
            "spend": 0,
            "conversions": 0,
            "last_deployed": None,
        })
        
        for v in self.store.get_all_variants():
            if v.status not in (AdStatus.LIVE, AdStatus.GRADUATED):
                continue
            if v.taxonomy is None:
                continue
            
            sig = f"{v.taxonomy.hook_type}+{v.taxonomy.tone}+{v.taxonomy.cta_type}"
            
            stats[sig]["count"] += 1
            
            snapshots = self.store.get_snapshots_for_variant(v.id)
            for s in snapshots:
                stats[sig]["spend"] += s.spend
                stats[sig]["conversions"] += s.first_note_completions
            
            created = v.created_at.date()
            if stats[sig]["last_deployed"] is None or created > stats[sig]["last_deployed"]:
                stats[sig]["last_deployed"] = created
        
        result = {}
        for sig, data in stats.items():
            avg_cpfn = None
            if data["conversions"] > 0:
                avg_cpfn = data["spend"] / data["conversions"]
            
            result[sig] = CombinationStats(
                signature=sig,
                deployment_count=data["count"],
                total_spend=data["spend"],
                total_conversions=data["conversions"],
                avg_cpfn=avg_cpfn,
                last_deployed=data["last_deployed"],
            )
        
        return result

    def _assess_data_quality(
        self, statistical: StatisticalMemory, editorial: EditorialMemory
    ) -> float:
        """Assess overall data quality (0-1)."""
        score = 0.0
        
        if statistical.n_observations >= 100:
            score += 0.3
        elif statistical.n_observations >= 50:
            score += 0.2
        elif statistical.n_observations >= 20:
            score += 0.1
        
        if statistical.r_squared >= 0.4:
            score += 0.3
        elif statistical.r_squared >= 0.25:
            score += 0.2
        elif statistical.r_squared >= 0.15:
            score += 0.1
        
        total_reviews = editorial.total_approvals + editorial.total_rejections
        if total_reviews >= 50:
            score += 0.2
        elif total_reviews >= 20:
            score += 0.1
        
        if len(editorial.approval_clusters) >= 5:
            score += 0.1
        
        if len(statistical.coefficient_history) >= 3:
            score += 0.1
        
        return min(score, 1.0)

    def build_generation_context(self, memory: CreativeMemory) -> GenerationContext:
        """Build the prompt-ready GenerationContext from memory."""

        winning_rules = [p.rule for p in memory.statistical.winning_patterns[:5]]
        losing_rules = [p.rule for p in memory.statistical.losing_patterns[:3]]

        exemplar_headlines = []
        for p in memory.statistical.winning_patterns[:3]:
            exemplar_headlines.extend(p.positive_examples[:2])

        exemplar_bodies = [
            c.representative_body[:100] for c in memory.editorial.approval_clusters[:3]
        ]

        approved_patterns = [
            f"Pattern: {c.signature} (approved {c.count}x). Example: '{c.representative_headline}'"
            for c in memory.editorial.approval_clusters[:5]
        ]

        rejection_rules = [r.rule for r in memory.editorial.rejection_rules[:5]]

        fatigue_warnings = [
            f"AVOID: {a.feature} — {a.recommendation} (deployed {a.deployments}x)"
            for a in memory.statistical.fatiguing_patterns[:3]
        ]

        exploration_targets = [
            f"EXPERIMENT: {combo} — only tested {count}x"
            for combo, count in memory.market.least_tested_combinations[:3]
        ]

        confidence_note = (
            f"Model R²={memory.statistical.r_squared:.2f}, "
            f"n={memory.statistical.n_observations}. "
            f"{'High confidence' if memory.data_quality_score > 0.7 else 'Treat as directional'}."
        )

        # Load stylistic references from swipe file ads (A4)
        stylistic_references = self._build_stylistic_references()

        return GenerationContext(
            winning_rules=winning_rules,
            losing_rules=losing_rules,
            exemplar_headlines=exemplar_headlines,
            exemplar_bodies=exemplar_bodies,
            approved_patterns=approved_patterns,
            rejection_rules=rejection_rules,
            fatigue_warnings=fatigue_warnings,
            exploration_targets=exploration_targets,
            confidence_note=confidence_note,
            stylistic_references=stylistic_references,
        )

    def _build_stylistic_references(self, max_refs: int = 5) -> list[str]:
        """
        Load swipe file ads and extract copy/style descriptions as stylistic references.
        These are ads with source='swipe_file' — competitor or best-in-class examples.
        """
        try:
            all_ads = self.store.get_all_existing_ads()
            swipe_ads = [a for a in all_ads if getattr(a, "source", "meta_api") == "swipe_file"]
            if not swipe_ads:
                return []

            references = []
            for ad in swipe_ads[:max_refs]:
                parts = []
                if ad.headline:
                    parts.append(f"Headline: \"{ad.headline}\"")
                if ad.body:
                    parts.append(f"Copy: \"{ad.body[:100]}\"")
                if ad.taxonomy:
                    parts.append(
                        f"Style: {ad.taxonomy.visual_style}, "
                        f"tone={ad.taxonomy.tone}, "
                        f"hook={ad.taxonomy.hook_type}"
                    )
                if parts:
                    references.append(" | ".join(parts))

            return references
        except Exception:
            return []
