"""
Configuration — all secrets and settings in one place.

Uses environment variables with .env file fallback.
NEVER commit .env to version control.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    All configuration for the ads engine.
    Set via environment variables or .env file.
    """

    # -- Anthropic (for intake parsing + copy generation) --
    ANTHROPIC_API_KEY: str = ""

    # -- Meta Marketing API --
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    META_ACCESS_TOKEN: str = ""
    META_AD_ACCOUNT_ID: str = ""           # Format: act_XXXXXXXXXX
    META_PAGE_ID: str = ""                  # Facebook Page ID for ad creative

    # -- Meta Campaign Structure --
    # Get these IDs from Adam/Matt — they know the existing campaign structure
    META_FARM_CAMPAIGN_ID: str = ""         # Test budget campaign for new creatives
    META_FARM_ADSET_ID: str = ""            # Adset within farm campaign
    META_SCALE_CAMPAIGN_ID: str = ""        # Proven winners campaign
    META_SCALE_ADSET_ID: str = ""           # Adset within scale campaign

    # -- Google Ads API --
    GOOGLE_ADS_DEVELOPER_TOKEN: str = ""
    GOOGLE_ADS_CLIENT_ID: str = ""
    GOOGLE_ADS_CLIENT_SECRET: str = ""
    GOOGLE_ADS_REFRESH_TOKEN: str = ""
    GOOGLE_ADS_CUSTOMER_ID: str = ""       # Format: XXX-XXX-XXXX (no dashes in API)

    # -- Google Analytics 4 (Data API) --
    # Property 419769857 is the canonical www.jotpsych.com marketing property
    # (G-B7Q5FRBQRH). See docs/ga4-csp-fix-2026-04-13.md for property mapping.
    GA_PROPERTY_ID: str = "419769857"
    GA_CREDENTIALS_PATH: str = str(Path.home() / ".claude" / "ga-service-account.json")

    # -- Slack --
    SLACK_WEBHOOK_URL: str = ""
    SLACK_CHANNEL: str = "#ads-engine"

    # -- Gemini (image generation) --
    gemini_api: str = ""

    # -- Image Generation (intern fills in based on chosen tool) --
    IMAGE_GEN_API_KEY: str = ""
    IMAGE_GEN_PROVIDER: str = ""           # "midjourney", "flux", "dalle", "ideogram"

    # -- Video Generation (intern fills in if applicable) --
    VIDEO_GEN_API_KEY: str = ""
    VIDEO_GEN_PROVIDER: str = ""           # "runway", "pika", "kling"

    # -- Decision Engine Thresholds --
    MIN_SPEND_FOR_DECISION: float = 50.0
    MIN_DAYS_LIVE: int = 3
    KILL_CPA_MULTIPLIER: float = 2.0
    SCALE_CPA_MULTIPLIER: float = 0.7
    DAILY_BUDGET_LIMIT: float = 700.0      # ~$20k/mo ÷ 30

    # -- Budget Pacing --
    MONTHLY_BUDGET: float = 17500.0         # $15-20K/mo, midpoint
    BUDGET_ALERT_HIGH: float = 1.10         # Alert if run rate >110% of budget
    BUDGET_ALERT_LOW: float = 0.70          # Alert if run rate <70% of budget

    # -- Data --
    DATA_DIR: str = "data"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


def get_settings() -> Settings:
    return Settings()
