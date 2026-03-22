"""
Performance Tracker — pulls daily metrics from Meta and Google APIs.

Runs on a daily schedule. Pulls spend, impressions, clicks, conversions
for every LIVE ad variant and stores PerformanceSnapshot records.

The intern needs to implement the actual API data pulls.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from engine.models import AdVariant, AdStatus, Platform, PerformanceSnapshot
from engine.store import Store


class MetaTracker:
    """Pull performance data from Meta Marketing API."""

    def __init__(self, access_token: str, ad_account_id: str):
        self.access_token = access_token
        self.ad_account_id = ad_account_id

    def pull_ad_metrics(self, meta_ad_id: str, report_date: date) -> dict:
        """
        Pull metrics for a single ad on a given date.

        STUB — intern implements using Meta Insights API.

        Should return dict with:
        - spend, impressions, reach, clicks
        - actions breakdown for: landing_page_view, sign_up, custom_conversion (first_note)
        - relevance_score (if available)

        Endpoint: GET /{ad_id}/insights?date_preset=yesterday&fields=...
        """
        raise NotImplementedError("Intern: implement Meta metrics pull")

    def pull_all_active(self, report_date: date) -> list[dict]:
        """Pull metrics for all active ads in the account."""
        raise NotImplementedError("Intern: implement Meta bulk metrics pull")


class GoogleTracker:
    """Pull performance data from Google Ads API."""

    def __init__(self, customer_id: str, credentials_path: str):
        self.customer_id = customer_id
        self.credentials_path = credentials_path

    def pull_ad_metrics(self, google_ad_id: str, report_date: date) -> dict:
        """
        Pull metrics for a single ad on a given date.

        STUB — intern implements using Google Ads reporting.

        Use GAQL:
        SELECT metrics.cost_micros, metrics.impressions, metrics.clicks,
               metrics.conversions, metrics.conversions_by_conversion_date
        FROM ad_group_ad
        WHERE ad_group_ad.ad.id = {ad_id}
        AND segments.date = '{date}'
        """
        raise NotImplementedError("Intern: implement Google metrics pull")


class PerformanceTracker:
    """
    Unified tracker. Pulls data from both platforms,
    normalizes into PerformanceSnapshot records.
    """

    def __init__(
        self,
        store: Store,
        meta_tracker: Optional[MetaTracker] = None,
        google_tracker: Optional[GoogleTracker] = None,
    ):
        self.store = store
        self.meta = meta_tracker
        self.google = google_tracker

    def pull_daily(self, report_date: Optional[date] = None) -> list[PerformanceSnapshot]:
        """
        Pull performance data for all live variants.
        Called daily by scheduler.
        """
        if report_date is None:
            report_date = date.today()

        live_variants = self.store.get_variants_by_status(AdStatus.LIVE)
        snapshots = []

        for variant in live_variants:
            try:
                snapshot = self._pull_variant(variant, report_date)
                if snapshot:
                    self.store.save_snapshot(snapshot)
                    snapshots.append(snapshot)
            except Exception as e:
                # Log error but don't stop the batch
                print(f"Error pulling metrics for {variant.id}: {e}")

        return snapshots

    def _pull_variant(self, variant: AdVariant, report_date: date) -> Optional[PerformanceSnapshot]:
        """Pull and normalize metrics for a single variant."""

        platform = variant.taxonomy.platform
        raw_metrics = None

        if platform == Platform.META and variant.meta_ad_id and self.meta:
            raw_metrics = self.meta.pull_ad_metrics(variant.meta_ad_id, report_date)
        elif platform == Platform.GOOGLE and variant.google_ad_id and self.google:
            raw_metrics = self.google.pull_ad_metrics(variant.google_ad_id, report_date)

        if not raw_metrics:
            return None

        # Normalize into PerformanceSnapshot
        spend = raw_metrics.get("spend", 0)
        impressions = raw_metrics.get("impressions", 0)
        clicks = raw_metrics.get("clicks", 0)
        signups = raw_metrics.get("signups", 0)
        first_notes = raw_metrics.get("first_note_completions", 0)

        return PerformanceSnapshot(
            ad_variant_id=variant.id,
            platform=platform,
            date=report_date,
            spend=spend,
            impressions=impressions,
            reach=raw_metrics.get("reach", 0),
            clicks=clicks,
            ctr=clicks / impressions if impressions > 0 else 0,
            cpc=spend / clicks if clicks > 0 else 0,
            landing_page_views=raw_metrics.get("landing_page_views", 0),
            signups=signups,
            first_note_completions=first_notes,
            cost_per_signup=spend / signups if signups > 0 else None,
            cost_per_first_note=spend / first_notes if first_notes > 0 else None,
            signup_to_note_rate=first_notes / signups if signups > 0 else None,
            meta_relevance_score=raw_metrics.get("relevance_score"),
            google_quality_score=raw_metrics.get("quality_score"),
        )
