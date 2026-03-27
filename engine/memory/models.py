"""
Creative Memory Models — structured knowledge that compounds across generation cycles.

Three-layer architecture:
1. StatisticalMemory — from regression (quantitative backbone)
2. EditorialMemory — from human review (qualitative signal)
3. MarketMemory — from deployment/competitive signals (context awareness)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
import uuid


@dataclass
class TimestampedCoefficient:
    """A coefficient value at a point in time."""
    coefficient: float
    p_value: float
    run_date: date
    n_observations: int


@dataclass
class PatternInsight:
    """
    A fully-rendered creative pattern with evidence and examples.
    This is what gets injected into agent prompts.
    """
    feature: str                           # "hook_type_statistic"
    coefficient: float                     # -42.3
    p_value: float                         # 0.008
    confidence_tier: str                   # "high" | "moderate" | "directional"
    n_observations: int

    rule: str                              # "Lead with a specific statistic in the headline"
    evidence: str                          # "Coefficient: -42.3, p=0.008, n=47"

    positive_examples: list[str] = field(default_factory=list)
    negative_examples: list[str] = field(default_factory=list)

    trend: str = "stable"                  # "stable" | "strengthening" | "fatiguing"
    first_significant_date: Optional[date] = None
    cycles_significant: int = 1
    # When was this insight last updated/validated? (M3)
    memory_snapshot_date: Optional[date] = None


@dataclass
class InteractionInsight:
    """An interaction effect between two features."""
    feature_a: str
    feature_b: str
    interaction_name: str                  # "uses_number_x_hook_type_statistic"
    coefficient: float
    p_value: float
    interpretation: str                    # "Numbers work best with statistic hooks"


@dataclass
class FatigueAlert:
    """Warning when a pattern is showing signs of audience fatigue."""
    feature: str
    current_coefficient: float
    historical_avg: float
    delta_pct: float
    deployments: int
    first_deployed: date
    recommendation: str                    # "Reduce usage" | "Retire" | "Refresh angle"
    # When was this alert last evaluated? (M3)
    memory_snapshot_date: Optional[date] = None


@dataclass
class StatisticalMemory:
    """Quantitative insights from regression analysis."""
    
    winning_patterns: list[PatternInsight] = field(default_factory=list)
    losing_patterns: list[PatternInsight] = field(default_factory=list)
    
    coefficient_history: dict[str, list[TimestampedCoefficient]] = field(default_factory=dict)
    
    fatiguing_patterns: list[FatigueAlert] = field(default_factory=list)
    interaction_insights: list[InteractionInsight] = field(default_factory=list)
    
    r_squared: float = 0.0
    n_observations: int = 0
    last_run_date: Optional[date] = None
    
    @classmethod
    def empty(cls) -> "StatisticalMemory":
        return cls()


@dataclass
class ApprovalCluster:
    """
    A cluster of approved ads grouped by taxonomy signature.
    Prevents redundancy when many approvals are from the same brief.
    """
    signature: dict                        # {"hook_type": "statistic", "tone": "warm"}
    count: int                             # How many approvals match this signature
    representative_headline: str
    representative_body: str
    representative_cta: str
    reviewer_notes_summary: Optional[str] = None
    avg_performance: Optional[float] = None  # Avg CpFN if available


@dataclass
class RejectionRule:
    """
    A generalized rule extracted from multiple rejections.
    More useful than raw rejection examples.
    """
    rule: str                              # "Don't combine playful tone with urgency messaging"
    pattern: dict                          # {"tone": "playful", "message_type": "urgency"}
    rejection_count: int
    example_notes: list[str]               # Sample notes that led to this rule
    confidence: str                        # "high" (5+ rejections) | "moderate" (3-4) | "tentative" (2)


@dataclass
class ReviewerProfile:
    """Captured preferences for a specific reviewer."""
    reviewer: str
    approval_rate: float
    preferred_patterns: list[dict]         # Patterns they approve at high rate
    disliked_patterns: list[dict]          # Patterns they reject at high rate
    sample_size: int
    last_review_date: Optional[date] = None


@dataclass
class GoldStandardAd:
    """Manually curated exemplar ad — 'this is exactly what we want'."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    headline: str = ""
    body: str = ""
    cta: str = ""
    why_exemplary: str = ""                # What makes this a gold standard
    added_by: Optional[str] = None
    added_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class EditorialMemory:
    """Qualitative insights from human review."""
    
    approval_clusters: list[ApprovalCluster] = field(default_factory=list)
    rejection_rules: list[RejectionRule] = field(default_factory=list)
    reviewer_profiles: dict[str, ReviewerProfile] = field(default_factory=dict)
    gold_standard_ads: list[GoldStandardAd] = field(default_factory=list)
    
    total_approvals: int = 0
    total_rejections: int = 0
    
    @classmethod
    def empty(cls) -> "EditorialMemory":
        return cls()


@dataclass
class CombinationStats:
    """Tracking for a specific taxonomy combination."""
    signature: str                         # "statistic_hook+warm_tone+try_free_cta"
    deployment_count: int
    total_spend: float
    total_conversions: int
    avg_cpfn: Optional[float]
    last_deployed: Optional[date]


@dataclass
class PlatformModifier:
    """Platform-specific performance adjustments."""
    platform: str                          # "meta" | "google"
    modifier: str                          # "video outperforms static by 30%"
    coefficient_adjustment: float          # 0.7 (multiply prediction by this)
    confidence: str
    n_observations: int


@dataclass
class CompetitiveObservation:
    """Manually entered competitive intelligence."""
    observation: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: Optional[str] = None
    implications: Optional[str] = None     # What to do about it
    added_by: Optional[str] = None
    added_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[date] = None      # Some observations are time-sensitive


@dataclass
class MarketMemory:
    """External context that shapes creative direction."""
    
    combination_stats: dict[str, CombinationStats] = field(default_factory=dict)
    least_tested_combinations: list[tuple[str, int]] = field(default_factory=list)
    
    platform_modifiers: list[PlatformModifier] = field(default_factory=list)
    
    competitive_observations: list[CompetitiveObservation] = field(default_factory=list)
    
    day_of_week_performance: dict[str, float] = field(default_factory=dict)
    
    @classmethod
    def empty(cls) -> "MarketMemory":
        return cls()


@dataclass
class CreativeMemory:
    """
    The complete creative memory — assembled from all three layers.
    This is what gets persisted and loaded for generation.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    statistical: StatisticalMemory = field(default_factory=StatisticalMemory.empty)
    editorial: EditorialMemory = field(default_factory=EditorialMemory.empty)
    market: MarketMemory = field(default_factory=MarketMemory.empty)
    
    built_at: datetime = field(default_factory=datetime.utcnow)
    data_quality_score: float = 0.0        # 0-1, based on n, R², review coverage
    
    version: int = 2                       # Schema version for migrations


@dataclass
class GenerationContext:
    """
    The prompt-ready injection format for copy agents.
    Structured data that gets serialized into the system prompt.
    """
    winning_rules: list[str] = field(default_factory=list)
    losing_rules: list[str] = field(default_factory=list)

    exemplar_headlines: list[str] = field(default_factory=list)
    exemplar_bodies: list[str] = field(default_factory=list)

    approved_patterns: list[str] = field(default_factory=list)
    rejection_rules: list[str] = field(default_factory=list)

    fatigue_warnings: list[str] = field(default_factory=list)
    exploration_targets: list[str] = field(default_factory=list)

    # Stylistic references from swipe file ads (A4) — aesthetic/copy inspiration
    # These are NOT JotPsych performance data — don't treat as rules, just inspiration
    stylistic_references: list[str] = field(default_factory=list)

    confidence_note: str = ""

    def to_prompt_block(self) -> str:
        """Serialize to a markdown block for agent injection."""
        sections = []

        if self.winning_rules:
            sections.append("## WINNING PATTERNS (inspired by — adapt, don't copy verbatim):\n")
            for rule in self.winning_rules[:5]:
                sections.append(f"- {rule}")
            sections.append("")

        if self.exemplar_headlines:
            sections.append("## EXEMPLAR HEADLINES:\n")
            for headline in self.exemplar_headlines[:5]:
                sections.append(f"- \"{headline}\"")
            sections.append("")

        if self.losing_rules:
            sections.append("## AVOID (these hurt performance):\n")
            for rule in self.losing_rules[:3]:
                sections.append(f"- {rule}")
            sections.append("")

        if self.approved_patterns:
            sections.append("## REVIEWER PREFERENCES:\n")
            for pattern in self.approved_patterns[:5]:
                sections.append(f"- {pattern}")
            sections.append("")

        if self.rejection_rules:
            sections.append("## REJECTION RULES:\n")
            for rule in self.rejection_rules[:5]:
                sections.append(f"- {rule}")
            sections.append("")

        if self.fatigue_warnings:
            sections.append("## FATIGUE ALERTS:\n")
            for warning in self.fatigue_warnings[:3]:
                sections.append(f"- {warning}")
            sections.append("")

        if self.exploration_targets:
            sections.append("## EXPLORATION TARGETS (try these):\n")
            for target in self.exploration_targets[:3]:
                sections.append(f"- {target}")
            sections.append("")

        if self.stylistic_references:
            sections.append("## STYLISTIC REFERENCES (inspiration only — adapt style, not content):\n")
            for ref in self.stylistic_references[:3]:
                sections.append(f"- {ref}")
            sections.append("")

        if self.confidence_note:
            sections.append(f"*{self.confidence_note}*\n")

        return "\n".join(sections)
