"""
Creative Memory Manager — accumulates knowledge across generation cycles.

This is the brain's long-term memory. It persists winning patterns, reviewer
preferences, fatigue alerts, and competitive intel. Every generation call
loads the latest memory and uses it to inform copy generation.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, date
from typing import Optional, TYPE_CHECKING

from engine.models import (
    CreativeMemory,
    WinningPattern,
    ReviewerPreference,
    FatigueAlert,
    CompetitiveIntel,
    PlaybookRule,
    AdStatus,
    RegressionResult,
)

if TYPE_CHECKING:
    from engine.store import Store


MAX_WINNING_PATTERNS = 50
STATUS_PRIORITY = {
    AdStatus.GRADUATED.value: 0,
    AdStatus.APPROVED.value: 1,
    AdStatus.LIVE.value: 2,
}


class CreativeMemoryManager:
    """
    Manages the creative memory lifecycle: loading, updating, and serializing
    for agent consumption.
    """

    def __init__(self, store: "Store"):
        self.store = store

    def load_or_create(self) -> CreativeMemory:
        """Load existing memory or create a new one."""
        memory = self.store.load_memory()
        if memory is None:
            memory = CreativeMemory()
        return memory

    def update_from_variants(self, memory: CreativeMemory) -> CreativeMemory:
        """
        Scan all reviewed variants and update winning patterns + reviewer preferences.
        Called after review cycles.
        """
        variants = self.store.get_all_variants()
        
        dominated_statuses = {
            AdStatus.GRADUATED.value,
            AdStatus.APPROVED.value,
            AdStatus.LIVE.value,
        }
        winners = [v for v in variants if v.status.value in dominated_statuses]
        
        existing_ids = {wp.variant_id for wp in memory.winning_patterns}
        
        for variant in winners:
            if variant.id in existing_ids:
                continue
            
            snapshots = self.store.get_snapshots_for_variant(variant.id)
            cpfn = None
            if snapshots:
                total_spend = sum(s.spend for s in snapshots)
                total_fn = sum(s.first_note_completions for s in snapshots)
                if total_fn > 0:
                    cpfn = total_spend / total_fn
            
            pattern = WinningPattern(
                variant_id=variant.id,
                headline=variant.headline,
                body=variant.primary_text,
                cta=variant.cta_button,
                taxonomy=variant.taxonomy.model_dump() if variant.taxonomy else {},
                reviewer=variant.reviewer,
                review_notes=variant.review_notes,
                cost_per_first_note=cpfn,
                status=variant.status.value,
            )
            memory.winning_patterns.append(pattern)
        
        memory.winning_patterns.sort(
            key=lambda wp: (
                STATUS_PRIORITY.get(wp.status, 99),
                wp.cost_per_first_note if wp.cost_per_first_note else float("inf"),
            )
        )
        memory.winning_patterns = memory.winning_patterns[:MAX_WINNING_PATTERNS]
        
        memory = self._update_reviewer_preferences(memory, variants)
        memory.total_variants_analyzed = len(variants)
        memory.updated_at = datetime.utcnow()
        
        return memory

    def _update_reviewer_preferences(
        self, memory: CreativeMemory, variants: list
    ) -> CreativeMemory:
        """
        Analyze approval/rejection patterns by reviewer and taxonomy dimension.
        """
        reviewer_dim_stats: dict[str, dict[str, dict[str, dict]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(lambda: {"approved": 0, "rejected": 0}))
        )
        
        taxonomy_dims = [
            "message_type", "hook_type", "cta_type", "tone",
            "visual_style", "subject_matter", "color_mood", "text_density",
        ]
        
        for v in variants:
            if v.reviewer is None or v.taxonomy is None:
                continue
            
            status = v.status.value
            if status not in ("approved", "rejected"):
                continue
            
            reviewer = v.reviewer
            tax_dict = v.taxonomy.model_dump()
            
            for dim in taxonomy_dims:
                val = tax_dict.get(dim)
                if val:
                    reviewer_dim_stats[reviewer][dim][val][status] += 1
        
        new_preferences = []
        for reviewer, dims in reviewer_dim_stats.items():
            for dim, values in dims.items():
                for val, counts in values.items():
                    total = counts["approved"] + counts["rejected"]
                    if total < 3:
                        continue
                    
                    approval_rate = counts["approved"] / total
                    
                    if approval_rate >= 0.75:
                        pattern = f"strongly prefers {val}"
                    elif approval_rate >= 0.6:
                        pattern = f"tends to approve {val}"
                    elif approval_rate <= 0.25:
                        pattern = f"strongly dislikes {val}"
                    elif approval_rate <= 0.4:
                        pattern = f"tends to reject {val}"
                    else:
                        continue
                    
                    pref = ReviewerPreference(
                        reviewer=reviewer,
                        dimension=dim,
                        pattern=pattern,
                        approval_rate=round(approval_rate, 2),
                        sample_size=total,
                    )
                    new_preferences.append(pref)
        
        memory.reviewer_preferences = new_preferences
        return memory

    def update_fatigue_alerts(
        self,
        memory: CreativeMemory,
        all_time: RegressionResult,
        rolling: RegressionResult,
    ) -> CreativeMemory:
        """
        Compare rolling vs all-time coefficients to detect fatigue.
        Flags features where recent performance is significantly worse.
        """
        memory.fatigue_alerts = []
        
        for feature, all_time_coef in all_time.coefficients.items():
            if feature not in rolling.coefficients:
                continue
            
            rolling_coef = rolling.coefficients[feature]
            
            if abs(all_time_coef) < 0.01:
                continue
            
            sign_flip = (all_time_coef > 0 and rolling_coef < 0) or \
                       (all_time_coef < 0 and rolling_coef > 0)
            
            delta_pct = ((rolling_coef - all_time_coef) / abs(all_time_coef)) * 100
            
            significant_degradation = (
                (all_time_coef < 0 and delta_pct > 50) or
                (all_time_coef > 0 and delta_pct < -50) or
                sign_flip
            )
            
            if significant_degradation:
                alert = FatigueAlert(
                    feature=feature,
                    all_time_coefficient=round(all_time_coef, 4),
                    rolling_coefficient=round(rolling_coef, 4),
                    delta_pct=round(delta_pct, 1),
                    detected_at=date.today(),
                    window_days=rolling.window_days or 30,
                )
                memory.fatigue_alerts.append(alert)
        
        memory.last_regression_date = all_time.run_date
        memory.updated_at = datetime.utcnow()
        return memory

    def add_competitive_intel(
        self,
        memory: CreativeMemory,
        content: str,
        source: Optional[str] = None,
        tags: Optional[list[str]] = None,
        added_by: Optional[str] = None,
    ) -> CreativeMemory:
        """Add a competitive intel note."""
        intel = CompetitiveIntel(
            content=content,
            source=source,
            tags=tags or [],
            added_by=added_by,
        )
        memory.competitive_intel.append(intel)
        memory.updated_at = datetime.utcnow()
        return memory

    def set_playbook_rules(
        self, memory: CreativeMemory, rules: list[PlaybookRule]
    ) -> CreativeMemory:
        """Replace playbook rules (called after regression + translation)."""
        memory.playbook_rules = rules
        memory.updated_at = datetime.utcnow()
        return memory

    @staticmethod
    def _to_agent_context_static(memory: CreativeMemory) -> str:
        """Static version of to_agent_context for use in copy agents."""
        return CreativeMemoryManager._build_agent_context(memory)

    @staticmethod
    def _build_agent_context(memory: CreativeMemory) -> str:
        """Build the agent context string from memory."""
        from collections import defaultdict
        
        sections = []
        
        if memory.playbook_rules:
            sections.append("## What Works (from regression analysis)\n")
            use_more = [r for r in memory.playbook_rules if r.direction == "use_more"]
            avoid = [r for r in memory.playbook_rules if r.direction == "avoid"]
            
            if use_more:
                sections.append("**USE MORE:**\n")
                for rule in use_more[:5]:
                    sections.append(f"- {rule.rule}")
                    if rule.good_examples:
                        sections.append(f"  - Good: \"{rule.good_examples[0]}\"")
                    if rule.bad_examples:
                        sections.append(f"  - Avoid: \"{rule.bad_examples[0]}\"")
                sections.append("")
            
            if avoid:
                sections.append("**AVOID:**\n")
                for rule in avoid[:5]:
                    sections.append(f"- {rule.rule}")
                    if rule.bad_examples:
                        sections.append(f"  - Bad: \"{rule.bad_examples[0]}\"")
                sections.append("")
        
        if memory.fatigue_alerts:
            sections.append("## Fatigue Warnings\n")
            sections.append("These elements have degraded recently — reduce usage:\n")
            for alert in memory.fatigue_alerts[:5]:
                sections.append(
                    f"- {alert.feature}: {alert.delta_pct:+.0f}% worse vs all-time"
                )
            sections.append("")
        
        if memory.winning_patterns:
            sections.append("## Winning Examples\n")
            sections.append("Headlines and copy that have been approved or performed well:\n")
            for wp in memory.winning_patterns[:5]:
                sections.append(f"- Headline: \"{wp.headline}\"")
                sections.append(f"  Body: \"{wp.body[:100]}...\"" if len(wp.body) > 100 else f"  Body: \"{wp.body}\"")
                if wp.review_notes:
                    sections.append(f"  (Reviewer: {wp.review_notes})")
            sections.append("")
        
        if memory.reviewer_preferences:
            prefs_by_reviewer: dict[str, list] = defaultdict(list)
            for pref in memory.reviewer_preferences:
                prefs_by_reviewer[pref.reviewer].append(pref)
            
            sections.append("## Reviewer Preferences\n")
            for reviewer, prefs in prefs_by_reviewer.items():
                sections.append(f"**{reviewer}:**")
                for pref in prefs[:3]:
                    sections.append(f"- {pref.pattern} ({pref.dimension}, {pref.sample_size} samples)")
            sections.append("")
        
        if memory.competitive_intel:
            sections.append("## Competitive Intel\n")
            for intel in memory.competitive_intel[-5:]:
                sections.append(f"- {intel.content}")
                if intel.source:
                    sections.append(f"  (Source: {intel.source})")
            sections.append("")
        
        return "\n".join(sections)

    def to_agent_context(self, memory: CreativeMemory) -> str:
        """
        Serialize memory into a structured prompt block for sub-agents.
        This is what HeadlineAgent and BodyCopyAgent consume.
        """
        return self._build_agent_context(memory)

    def get_rejection_feedback(self, memory: CreativeMemory, limit: int = 10) -> list[dict]:
        """
        Get recent rejection examples for negative training.
        Pulls from variants not in winning_patterns.
        """
        rejected = self.store.get_variants_by_status(AdStatus.REJECTED)
        feedback = []
        for v in rejected[-limit:]:
            if v.review_notes:
                feedback.append({
                    "variant_id": v.id,
                    "headline": v.headline,
                    "body": v.primary_text,
                    "cta": v.cta_button,
                    "notes": v.review_notes,
                    "taxonomy": v.taxonomy.model_dump() if v.taxonomy else None,
                })
        return feedback

    def get_approval_feedback(self, memory: CreativeMemory, limit: int = 10) -> list[dict]:
        """
        Get recent approval examples for positive training.
        Supplements winning_patterns with fresh approvals.
        """
        approved = self.store.get_variants_by_status(AdStatus.APPROVED)
        feedback = []
        for v in approved[-limit:]:
            feedback.append({
                "variant_id": v.id,
                "headline": v.headline,
                "body": v.primary_text,
                "cta": v.cta_button,
                "notes": v.review_notes,
                "taxonomy": v.taxonomy.model_dump() if v.taxonomy else None,
            })
        return feedback
