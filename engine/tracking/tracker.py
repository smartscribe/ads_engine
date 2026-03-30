"""
Performance Tracker — pulls daily metrics from Meta and Google APIs.

Runs on a daily schedule. Pulls spend, impressions, clicks, conversions
for every LIVE ad variant and stores PerformanceSnapshot records.
"""

from __future__ import annotations

import time
from datetime import date, datetime
from typing import Optional

from engine.models import AdVariant, AdStatus, Platform, PerformanceSnapshot
from engine.store import Store


def _retry(fn, retries=3, backoff=1.0):
    """Call fn() with exponential backoff on failure."""
    for attempt in range(retries):
        try:
            return fn()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(backoff * (2 ** attempt))


def _parse_actions(actions: list[dict]) -> dict:
    """Extract conversion counts from Meta actions array."""
    result = {
        "first_note_completions": 0,
        "signups": 0,
        "landing_page_views": 0,
    }
    if not actions:
        return result
    for action in actions:
        atype = action.get("action_type", "")
        value = int(action.get("value", 0))
        if "first_note" in atype or "first_note_completion" in atype:
            result["first_note_completions"] += value
        elif atype in ("lead", "onsite_conversion.lead_grouped") or "signup" in atype:
            result["signups"] += value
        elif atype == "landing_page_view":
            result["landing_page_views"] += value
    return result


class MetaTracker:
    """Pull performance data from Meta Marketing API via facebook_business SDK."""

    def __init__(self, access_token: str, ad_account_id: str):
        from facebook_business.api import FacebookAdsApi

        FacebookAdsApi.init(app_id=None, app_secret=None, access_token=access_token)
        self.access_token = access_token
        self.ad_account_id = ad_account_id

    def pull_ad_metrics(self, meta_ad_id: str, report_date: date) -> Optional[dict]:
        """
        Pull metrics for a single ad on a given date.
        Returns normalized dict or None if no data for that day.
        """
        from facebook_business.adobjects.ad import Ad

        ad = Ad(meta_ad_id)
        params = {
            "time_range": {
                "since": report_date.isoformat(),
                "until": report_date.isoformat(),
            },
            "level": "ad",
        }
        fields = [
            "spend", "impressions", "reach", "clicks",
            "actions", "cost_per_action_type",
        ]

        insights = _retry(lambda: ad.get_insights(params=params, fields=fields))

        if not insights:
            return None

        row = insights[0]
        actions = row.get("actions", [])
        parsed = _parse_actions(actions)

        return {
            "spend": float(row.get("spend", 0)),
            "impressions": int(row.get("impressions", 0)),
            "reach": int(row.get("reach", 0)),
            "clicks": int(row.get("clicks", 0)),
            "first_note_completions": parsed["first_note_completions"],
            "signups": parsed["signups"],
            "landing_page_views": parsed["landing_page_views"],
            "relevance_score": None,
            "quality_score": None,
        }

    def pull_all_active(self, report_date: date) -> list[dict]:
        """Pull metrics for all active ads in the account."""
        from facebook_business.adobjects.adaccount import AdAccount

        account = AdAccount(self.ad_account_id)
        ads = _retry(
            lambda: account.get_ads(
                params={"effective_status": ["ACTIVE"]},
                fields=["id", "name"],
            )
        )

        results = []
        for ad in ads:
            try:
                metrics = self.pull_ad_metrics(ad["id"], report_date)
                if metrics:
                    metrics["ad_id"] = ad["id"]
                    metrics["ad_name"] = ad.get("name", "")
                    results.append(metrics)
            except Exception as e:
                print(f"Error pulling metrics for {ad['id']}: {e}")
        return results


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
