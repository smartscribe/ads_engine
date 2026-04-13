"""Constants for the FB funnel report. Edit these when assumptions shift."""
from pathlib import Path

# ----- Cohort & trial window -----
COHORT_DAYS = 180              # L6M
TRIAL_NOMINAL_DAYS = 14        # fallback trial length for users without a status change
TRIAL_CAP_DAYS = 30            # sanity cap regardless
MATURED_MIN_DAYS = 14          # users younger than this are excluded from the per-note rate model

# ----- Economics -----
ARPU_MONTHLY = 150             # flat blended ARPU for MRR estimates. Override when you have a Stripe pull.

# ----- Channel taxonomy -----
PAID_CHANNELS = ["google_ad", "facebook_ad", "linkedin_ad"]
REST_LABEL = "rest"

CHANNEL_COLORS = {
    "google_ad":        "#6b5dd3",   # JotPsych purple
    "facebook_ad":      "#1877f2",   # FB blue
    "linkedin_ad":      "#0a66c2",   # LinkedIn blue
    "friend_colleague": "#2d8a4e",
    "part_of_group":    "#8da0cb",
    "conference_event": "#fc8d62",
    "blog":             "#a6761d",
    "newsletter":       "#e78ac3",
    "podcast":          "#66c2a5",
    "other":            "#b3b3b3",
    "null":             "#5a5750",
    "rest":             "#a89fdf",
}

CHANNEL_LABELS = {
    "google_ad":        "Google ad",
    "facebook_ad":      "Facebook ad",
    "linkedin_ad":      "LinkedIn ad",
    "friend_colleague": "Friend / colleague",
    "part_of_group":    "Part of a group",
    "conference_event": "Conference / event",
    "blog":             "Blog",
    "newsletter":       "Newsletter",
    "podcast":          "Podcast",
    "other":            "Other",
    "null":             "(Null)",
    "rest":             "Rest (organic + other)",
}

# ----- Smoothing -----
ROLLING_WINDOW = 5             # notes-per-user rolling rate window
NOTES_CAP = 30                 # users with > this are all binned as '30+'

# ----- Metabase -----
METABASE_DB_ID = 2             # Smartscribe Analytics Supabase
METABASE_TIMEOUT = 300         # seconds; large queries

# ----- Paths (all relative to ads_engine root) -----
REPO_ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT_DIR = REPO_ROOT / "data" / "performance" / "snapshots" / "fb_funnel"
RAW_DIR = SNAPSHOT_DIR / "raw"
MODEL_PATH = SNAPSHOT_DIR / "model.json"
RENDER_PATH = REPO_ROOT / "data" / "performance" / "snapshots" / "trial-conversion-by-notes.html"
