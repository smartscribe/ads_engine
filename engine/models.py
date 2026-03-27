"""
Core data models for the ads engine.
Every ad, brief, and performance record flows through these.
"""

from __future__ import annotations

import uuid
from datetime import datetime, date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Platform(str, Enum):
    META = "meta"
    GOOGLE = "google"


class AdFormat(str, Enum):
    SINGLE_IMAGE = "single_image"
    CAROUSEL = "carousel"
    VIDEO = "video"
    GIF = "gif"
    STORY = "story"
    REELS = "reels"
    SEARCH_TEXT = "search_text"
    DISPLAY = "display"


class AdStatus(str, Enum):
    DRAFT = "draft"           # Generated, not yet reviewed
    APPROVED = "approved"     # Passed review, ready to deploy
    REJECTED = "rejected"     # Failed review
    LIVE = "live"             # Currently running
    PAUSED = "paused"         # Temporarily pulled
    KILLED = "killed"         # Permanently stopped
    GRADUATED = "graduated"   # Scaled up — proven winner


class DecisionVerdict(str, Enum):
    SCALE = "scale"
    KILL = "kill"
    WAIT = "wait"


# ---------------------------------------------------------------------------
# Creative Brief — what comes out of intake
# ---------------------------------------------------------------------------

class CreativeBrief(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Raw input
    raw_input: str                    # The free-form dump (text, transcript, etc.)
    source: str = "manual"            # "manual", "slack", "voice", "swipe_file"

    # AI-structured fields
    target_audience: str              # "bh_clinicians" or "smb_clinic_owners"
    value_proposition: str            # Core promise
    pain_point: str                   # What problem are we poking?
    desired_action: str               # What should the viewer do?
    tone_direction: str               # e.g. "warm but urgent", "clinical authority"
    visual_direction: str             # e.g. "real clinician at desk, warm lighting"
    key_phrases: list[str] = []       # Specific language to try
    references: list[str] = []        # URLs, competitor examples, swipe file paths

    # Generation config
    num_variants: int = 6
    formats_requested: list[AdFormat] = [AdFormat.SINGLE_IMAGE, AdFormat.VIDEO]
    platforms: list[Platform] = [Platform.META, Platform.GOOGLE]


# ---------------------------------------------------------------------------
# Creative Taxonomy — MECE element decomposition for regression
# ---------------------------------------------------------------------------

class CreativeTaxonomy(BaseModel):
    """
    Every ad variant gets auto-tagged across these dimensions.
    Each dimension is MECE — mutually exclusive, collectively exhaustive.
    The regression model uses these as features.
    """

    # MESSAGE LAYER — what the ad says
    message_type: str          # value_prop | pain_point | social_proof | urgency | education | comparison
    hook_type: str             # question | statistic | testimonial | provocative_claim | scenario | direct_benefit
    cta_type: str              # try_free | book_demo | learn_more | see_how | start_saving_time | watch_video
    tone: str                  # clinical | warm | urgent | playful | authoritative | empathetic

    # VISUAL LAYER — what the ad looks like
    visual_style: str          # photography | illustration | screen_capture | text_heavy | mixed_media | abstract
    subject_matter: str        # clinician_at_work | patient_interaction | product_ui | workflow_comparison | conceptual | data_viz
    color_mood: str            # brand_primary | warm_earth | cool_clinical | high_contrast | muted_soft | bold_saturated
    text_density: str          # headline_only | headline_subhead | detailed_copy | minimal_overlay

    # STRUCTURAL LAYER — how the ad is built
    format: AdFormat
    platform: Platform
    placement: str             # feed | story | reels | search | display | discover

    # COPY SPECIFICS — granular text features
    headline_word_count: int
    uses_number: bool          # "Save 2 hours/day" vs "Save time"
    uses_question: bool
    uses_first_person: bool    # "I" / "my" vs "you" / "your"
    uses_social_proof: bool    # mentions other clinicians, stats, testimonials
    copy_reading_level: float  # Flesch-Kincaid grade level


# ---------------------------------------------------------------------------
# Ad Variant — a single generated creative
# ---------------------------------------------------------------------------

class AdVariant(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    brief_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Content
    headline: str
    primary_text: str
    description: Optional[str] = None
    cta_button: str = "Learn More"
    asset_path: str               # Path to image/video file
    asset_type: str               # "image" or "video"

    # Asset rendering metadata
    # "rendered" = screenshot PNG exists, "template_available" = HTML template can be previewed, "pending" = neither
    asset_status: str = "pending"
    template_id: Optional[str] = None    # e.g. "feed_1080x1080/headline_hero"
    template_color_scheme: Optional[str] = None

    # Taxonomy (auto-tagged)
    taxonomy: CreativeTaxonomy

    # Status
    status: AdStatus = AdStatus.DRAFT
    review_notes: Optional[str] = None
    reviewer: Optional[str] = None
    reviewed_at: Optional[datetime] = None

    # Structured review feedback (new fields alongside review_notes for backward compat)
    review_chips: list[str] = []         # e.g. ["headline_too_generic", "wrong_tone"]
    review_duration_ms: int = 0          # how long the reviewer looked at this card

    # Platform IDs (populated after deployment)
    meta_ad_id: Optional[str] = None
    google_ad_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Review Feedback — structured review signal from the dashboard
# ---------------------------------------------------------------------------

class ReviewFeedback(BaseModel):
    """
    Submitted from the review dashboard when a reviewer approves or rejects a variant.
    The verdict is recorded instantly; chips and notes are optional enrichment.
    """
    variant_id: str
    reviewer: str
    verdict: str                          # "approved" | "rejected"
    chips: list[str] = []                 # e.g. ["headline_too_generic", "wrong_tone"]
    freeform_note: Optional[str] = None   # Optional freeform text (stored as review_notes)
    review_duration_ms: int = 0           # ms from card shown to verdict tap


# ---------------------------------------------------------------------------
# Performance Snapshot — daily pull from platforms
# ---------------------------------------------------------------------------

class PerformanceSnapshot(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ad_variant_id: str
    platform: Platform
    date: date
    pulled_at: datetime = Field(default_factory=datetime.utcnow)

    # Spend & reach
    spend: float
    impressions: int
    reach: int

    # Engagement
    clicks: int
    ctr: float                     # clicks / impressions
    cpc: float                     # spend / clicks

    # Conversion funnel
    landing_page_views: int
    signups: int
    first_note_completions: int    # PRIMARY CONVERSION

    # Derived
    cost_per_signup: Optional[float] = None
    cost_per_first_note: Optional[float] = None
    signup_to_note_rate: Optional[float] = None

    # Platform-specific quality scores
    meta_relevance_score: Optional[float] = None
    google_quality_score: Optional[float] = None


# ---------------------------------------------------------------------------
# Decision Record — daily scale/kill/wait output
# ---------------------------------------------------------------------------

class DecisionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    ad_variant_id: str
    date: date
    created_at: datetime = Field(default_factory=datetime.utcnow)

    verdict: DecisionVerdict
    confidence: float              # 0-1, based on data volume + signal strength
    reasoning: str                 # Human-readable explanation

    # Key metrics at time of decision
    total_spend: float
    total_first_notes: int
    cost_per_first_note: float
    days_live: int
    trend: str                     # "improving" | "stable" | "declining"

    # Action taken
    executed: bool = False
    executed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Regression Result — what the model learned
# ---------------------------------------------------------------------------

class RegressionResult(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_date: date
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Model metadata
    n_observations: int
    r_squared: float
    adjusted_r_squared: float

    # Feature coefficients with significance
    coefficients: dict[str, float]        # feature_name → coefficient
    p_values: dict[str, float]            # feature_name → p-value
    confidence_intervals: dict[str, tuple[float, float]]  # feature_name → (low, high)

    # Top insights (auto-generated)
    top_positive_features: list[str]      # Features that drive performance
    top_negative_features: list[str]      # Features that hurt performance
    insignificant_features: list[str]     # Features with p > 0.05

    # Diagnostics
    vif_scores: dict[str, float]          # Variance inflation factors (covariance check)
    durbin_watson: float                  # Autocorrelation check
    condition_number: float               # Multicollinearity diagnostic

    # Rolling window / weighted regression metadata
    window_days: Optional[int] = None     # None = all-time, else rolling window size
    sample_weights_used: bool = False     # True if exponential decay weights applied


# ---------------------------------------------------------------------------
# Existing Ad — imported from Meta/Google for analysis
# ---------------------------------------------------------------------------

class ExistingAd(BaseModel):
    """
    An ad imported from Meta (or Google) for analysis and regression seeding.
    Unlike AdVariant, these were NOT generated by the engine — they're
    historical ads pulled from the platform APIs.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    platform: Platform = Platform.META
    meta_ad_id: str
    ad_name: str
    campaign_name: str = ""
    campaign_status: str = ""
    adset_name: str = ""

    # Creative content
    headline: Optional[str] = None
    body: Optional[str] = None
    cta_type: Optional[str] = None
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    creative_type: str = "image"           # "image", "video", "carousel"

    # Performance (aggregated over date range)
    spend: float = 0
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    ctr: float = 0
    cpc: float = 0
    conversions: int = 0
    cost_per_conversion: Optional[float] = None
    landing_page_views: int = 0
    video_views: int = 0

    # Taxonomy (populated by Claude analysis)
    taxonomy: Optional[CreativeTaxonomy] = None
    analyzed_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Creative Memory — persistent knowledge base across generation cycles
# ---------------------------------------------------------------------------

class WinningPattern(BaseModel):
    """A proven winning ad pattern with performance data."""
    variant_id: str
    headline: str
    body: str
    cta: str
    taxonomy: dict                         # Full taxonomy as dict for flexibility
    reviewer: Optional[str] = None
    review_notes: Optional[str] = None
    cost_per_first_note: Optional[float] = None
    status: str                            # graduated > approved > live
    added_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewerPreference(BaseModel):
    """Synthesized preference pattern for a specific reviewer."""
    reviewer: str
    dimension: str                         # e.g. "tone", "hook_type"
    pattern: str                           # e.g. "approves question hooks 4:1 vs direct"
    approval_rate: float                   # 0-1
    sample_size: int
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class FatigueAlert(BaseModel):
    """Warning when a feature's recent performance is worse than all-time."""
    feature: str
    all_time_coefficient: float
    rolling_coefficient: float
    delta_pct: float                       # (rolling - all_time) / abs(all_time) * 100
    detected_at: date
    window_days: int = 30


class CompetitiveIntel(BaseModel):
    """Manually added competitive insight or swipe file note."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str
    source: Optional[str] = None           # URL, competitor name, etc.
    tags: list[str] = []
    added_by: Optional[str] = None
    added_at: datetime = Field(default_factory=datetime.utcnow)


class PlaybookRule(BaseModel):
    """Actionable generation rule derived from regression coefficients."""
    feature: str                           # Raw feature name (e.g. hook_type_statistic)
    direction: str                         # "use_more" or "avoid"
    confidence: str                        # "high" (p<0.01) or "moderate" (p<0.05)
    rule: str                              # Natural language instruction
    good_examples: list[str] = []          # 2-3 concrete examples from approved variants
    bad_examples: list[str] = []           # 2-3 examples from rejected/poor variants
    coefficient: float
    p_value: float


class CreativeMemory(BaseModel):
    """
    Persistent knowledge base that accumulates across generation cycles.
    Loaded fresh on every generate call. Stores winning patterns, reviewer
    preferences, fatigue alerts, playbook rules, and competitive intel.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Winning patterns — capped at 50, ranked by CpFN
    winning_patterns: list[WinningPattern] = []

    # Reviewer preferences — synthesized from approval/rejection patterns
    reviewer_preferences: list[ReviewerPreference] = []

    # Fatigue alerts — features whose rolling perf is worse than all-time
    fatigue_alerts: list[FatigueAlert] = []

    # Playbook rules — actionable instructions with examples
    playbook_rules: list[PlaybookRule] = []

    # Competitive intel — manually added notes
    competitive_intel: list[CompetitiveIntel] = []

    # Metadata
    last_regression_date: Optional[date] = None
    total_variants_analyzed: int = 0
