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


class HypothesisStatus(str, Enum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    INCONCLUSIVE = "inconclusive"


# ---------------------------------------------------------------------------
# Creative Brief — what comes out of intake
# ---------------------------------------------------------------------------

class CreativeBrief(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Raw input
    raw_input: str                    # The free-form dump (text, transcript, etc.)
    source: str = "manual"            # "manual", "slack", "voice", "swipe_file", "playbook", "concept"

    # AI-structured fields
    target_audience: str              # "bh_clinicians" or "smb_clinic_owners"
    value_proposition: str            # Core promise
    pain_point: str                   # What problem are we poking?
    desired_action: str               # What should the viewer do?
    tone_direction: str               # e.g. "warm but urgent", "clinical authority"
    visual_direction: str             # e.g. "real clinician at desk, warm lighting"
    key_phrases: list[str] = []       # Specific language to try
    references: list[str] = []        # URLs, competitor examples, swipe file paths

    # Richer brief fields (A2) — more specific creative direction
    # emotional_register: arc from viewer's current state to desired state
    # e.g. "overwhelmed by charting → quiet relief" not just "empathetic"
    emotional_register: str = ""
    # proof_element: specific stat or evidence to back the claim
    # e.g. "saves 2hrs/day" not "backed by research"
    proof_element: str = ""
    # hook_strategy: how to open the ad
    # e.g. "question about after-hours charting" not "engaging"
    hook_strategy: str = ""
    # target_persona_details: specific archetype, daily routine, pain moment
    # e.g. "solo therapist, 8-10 patients/day, drowning in notes after 6pm"
    target_persona_details: str = ""
    # brief_richness_score: 1-10 AI self-scored — below 6 triggers re-prompt
    brief_richness_score: float = 0.0
    # source_pattern_id: which winning playbook pattern seeded this brief
    source_pattern_id: Optional[str] = None

    # Generation config
    num_variants: int = 6
    formats_requested: list[AdFormat] = [AdFormat.SINGLE_IMAGE]
    platforms: list[Platform] = [Platform.META, Platform.GOOGLE]


# ---------------------------------------------------------------------------
# Creative Taxonomy — MECE element decomposition for regression
# ---------------------------------------------------------------------------

class CreativeTaxonomy(BaseModel):
    """
    Every ad variant gets auto-tagged across these dimensions.
    Each dimension is MECE — mutually exclusive, collectively exhaustive.
    The regression model uses these as features.

    MECE boundary decisions (keep in sync with TAXONOMY_PROMPT in analyzer.py):
    - hook_type: "statistic" wins over "direct_benefit" if a specific number is present
    - tone: "warm" = warm-colleague energy; "empathetic" = I-feel-your-pain energy
    - subject_matter: "patient_interaction" requires a patient visibly present in the scene
    - text_density: "headline_only" <5 words; "headline_subhead" 5-15 words; "detailed_copy" 15+ words
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

    # EXTENDED TAXONOMY FEATURES (R2) — added for richer regression signal
    # contains_specific_number: visual stat callout in image (distinct from uses_number in copy)
    contains_specific_number: bool = False
    # shows_product_ui: JotPsych UI is visible in the creative
    shows_product_ui: bool = False
    # human_face_visible: a human face is visible in the creative
    human_face_visible: bool = False
    # social_proof_type: type of social proof if any (none | peer | testimonial | stat)
    social_proof_type: str = "none"
    # copy_length_bin: binned copy length (short <15 words | medium 15-40 | long 40+)
    copy_length_bin: str = "medium"

    # TAGGING CONFIDENCE (A1) — Claude's confidence per dimension (0.0-1.0)
    # Populated by _tag_batch() in analyzer.py when tagging_confidence is requested
    tagging_confidence: dict[str, float] = {}

    # Allowed values for each categorical field (used by validate_values())
    VALID_VALUES: dict = {
        "message_type": ["value_prop", "pain_point", "social_proof", "urgency", "education", "comparison"],
        "hook_type": ["question", "statistic", "testimonial", "provocative_claim", "scenario", "direct_benefit"],
        "cta_type": ["try_free", "book_demo", "learn_more", "see_how", "start_saving_time", "watch_video"],
        "tone": ["clinical", "warm", "urgent", "playful", "authoritative", "empathetic"],
        "visual_style": ["photography", "illustration", "screen_capture", "text_heavy", "mixed_media", "abstract"],
        "subject_matter": ["clinician_at_work", "patient_interaction", "product_ui", "workflow_comparison", "conceptual", "data_viz"],
        "color_mood": ["brand_primary", "warm_earth", "cool_clinical", "high_contrast", "muted_soft", "bold_saturated"],
        "text_density": ["headline_only", "headline_subhead", "detailed_copy", "minimal_overlay"],
        "placement": ["feed", "story", "reels", "search", "display", "discover"],
        "social_proof_type": ["none", "peer", "testimonial", "stat"],
        "copy_length_bin": ["short", "medium", "long"],
    }

    def validate_values(self) -> list[str]:
        """
        Check all categorical fields against VALID_VALUES.
        Returns a list of violation strings like 'tone="inspirational" not in allowed values'.
        """
        violations = []
        for field_name, allowed in self.VALID_VALUES.items():
            value = getattr(self, field_name, None)
            if value is not None and value not in allowed:
                violations.append(f'{field_name}="{value}" not in {allowed}')
        return violations

    def low_confidence_fields(self, threshold: float = 0.6) -> list[str]:
        """Return list of field names where tagging_confidence is below threshold."""
        return [
            field for field, conf in self.tagging_confidence.items()
            if conf < threshold
        ]


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

    # Validation diagnostics (R1) — populated by run_with_validation()
    test_r_squared: Optional[float] = None
    # bootstrap_ci[feature] = (point_estimate, lower_2.5, upper_97.5) from 1000 resamples
    bootstrap_ci: dict[str, tuple[float, float, float]] = {}
    # coefficient_stability[feature] = std dev of coefficient across 10 subsample runs
    coefficient_stability: dict[str, float] = {}
    # confidence_tiers[feature] = "high"|"moderate"|"directional"|"unreliable"
    # high: bootstrap CI doesn't cross 0 AND stability std < 0.3 * |coeff|
    # moderate: bootstrap CI doesn't cross 0
    # directional: p < 0.10
    # unreliable: everything else
    confidence_tiers: dict[str, str] = {}


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

    # Source tracking (A4) — distinguish imported platform ads from swipe files
    # "meta_api" | "google_api" | "swipe_file"
    source: str = "meta_api"
    # exclude_from_regression: swipe file ads add stylistic signal but shouldn't
    # pollute regression coefficients (they're not JotPsych performance data)
    exclude_from_regression: bool = False

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
    """
    A proven winning ad pattern with performance data.

    DEPRECATED: Use `engine.memory.models.PatternInsight` instead.
    This model is kept for backward compatibility with v1 CreativeMemory.
    New code should use the v2 memory architecture in engine/memory/.
    """
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
    """
    Synthesized preference pattern for a specific reviewer.

    DEPRECATED: Use `engine.memory.models.ReviewerProfile` instead.
    Kept for backward compatibility.
    """
    reviewer: str
    dimension: str                         # e.g. "tone", "hook_type"
    pattern: str                           # e.g. "approves question hooks 4:1 vs direct"
    approval_rate: float                   # 0-1
    sample_size: int
    last_updated: datetime = Field(default_factory=datetime.utcnow)


class FatigueAlert(BaseModel):
    """
    Warning when a feature's recent performance is worse than all-time.

    DEPRECATED: Use `engine.memory.models.FatigueAlert` instead.
    Kept for backward compatibility.
    """
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
    """
    Actionable generation rule derived from regression coefficients.
    Used by PlaybookTranslator and as injection context in copy agents.
    This is the canonical model — both v1 and v2 memory paths use this.
    """
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

    LEGACY v1 format: Stored as Pydantic model in creative_memory.json.
    Superseded by `engine.memory.models.CreativeMemory` (v2 dataclass-based).
    This is kept for backward compatibility in store.load_memory().
    New code should use MemoryBuilder to build v2 memory.
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


# ---------------------------------------------------------------------------
# Hypothesis Tracking
# ---------------------------------------------------------------------------

class CreativeHypothesis(BaseModel):
    """
    Tracked hypothesis about what creative works and why.
    Evaluated against regression coefficients after each run.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hypothesis_text: str
    created_by: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    related_features: list[str] = []       # e.g. ["hook_type_scenario", "message_type_urgency"]
    status: HypothesisStatus = HypothesisStatus.ACTIVE
    confidence: float = 0.0                # 0.0-1.0
    evidence: list[str] = []               # human-readable evidence trail
    last_evaluated: Optional[date] = None
    evaluation_count: int = 0
