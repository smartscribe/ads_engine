"""
Ad Deployer — pushes approved variants to Meta and Google.

Full API integration target. Currently stubbed with interface contracts.

Meta: Marketing API (v21.0+)
Google: Google Ads API (v17+)

The intern needs to:
1. Set up Meta Business Manager + App with ads_management permission
2. Set up Google Ads API developer token + OAuth
3. Implement the actual API calls
4. Handle asset upload (images/videos to platform CDNs)
5. Map our AdVariant model to platform-specific ad structures
6. Handle campaign/adset/ad hierarchy (Meta) and campaign/adgroup/ad (Google)
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from engine.models import AdVariant, AdStatus, Platform
from engine.store import Store


class MetaDeployer:
    """
    Deploys ads to Meta (Facebook/Instagram) via Marketing API.

    Requires:
    - META_APP_ID
    - META_APP_SECRET
    - META_ACCESS_TOKEN (long-lived)
    - META_AD_ACCOUNT_ID
    """

    def __init__(self, access_token: str, ad_account_id: str):
        self.access_token = access_token
        self.ad_account_id = ad_account_id
        # INTERN: Initialize facebook_business SDK here
        # from facebook_business.api import FacebookAdsApi
        # from facebook_business.adobjects.adaccount import AdAccount

    def upload_asset(self, variant: AdVariant) -> str:
        """
        Upload image/video to Meta's CDN.
        Returns the platform asset ID (image_hash or video_id).

        STUB — intern implements with facebook_business SDK.
        """
        raise NotImplementedError("Intern: implement Meta asset upload")

    def create_ad(self, variant: AdVariant, campaign_id: str, adset_id: str) -> str:
        """
        Create an ad under an existing campaign/adset.
        Returns the Meta ad ID.

        STUB — intern implements.
        Steps:
        1. Upload creative asset
        2. Create AdCreative object
        3. Create Ad object linked to creative + adset
        """
        raise NotImplementedError("Intern: implement Meta ad creation")

    def pause_ad(self, meta_ad_id: str) -> bool:
        """Pause a running ad."""
        raise NotImplementedError("Intern: implement Meta ad pause")

    def resume_ad(self, meta_ad_id: str) -> bool:
        """Resume a paused ad."""
        raise NotImplementedError("Intern: implement Meta ad resume")

    def delete_ad(self, meta_ad_id: str) -> bool:
        """Delete an ad (for killed variants)."""
        raise NotImplementedError("Intern: implement Meta ad deletion")


class GoogleDeployer:
    """
    Deploys ads to Google Ads via Google Ads API.

    Requires:
    - GOOGLE_ADS_DEVELOPER_TOKEN
    - GOOGLE_ADS_CLIENT_ID
    - GOOGLE_ADS_CLIENT_SECRET
    - GOOGLE_ADS_REFRESH_TOKEN
    - GOOGLE_ADS_CUSTOMER_ID
    """

    def __init__(self, customer_id: str, credentials_path: str):
        self.customer_id = customer_id
        self.credentials_path = credentials_path
        # INTERN: Initialize google-ads SDK here
        # from google.ads.googleads.client import GoogleAdsClient

    def upload_asset(self, variant: AdVariant) -> str:
        """Upload asset to Google Ads. Returns asset resource name."""
        raise NotImplementedError("Intern: implement Google asset upload")

    def create_ad(self, variant: AdVariant, campaign_id: str, ad_group_id: str) -> str:
        """Create a responsive display/search ad. Returns Google ad ID."""
        raise NotImplementedError("Intern: implement Google ad creation")

    def pause_ad(self, google_ad_id: str) -> bool:
        """Pause a running ad."""
        raise NotImplementedError("Intern: implement Google ad pause")

    def resume_ad(self, google_ad_id: str) -> bool:
        """Resume a paused ad."""
        raise NotImplementedError("Intern: implement Google ad resume")


class AdDeployer:
    """
    Unified deployer — routes to Meta or Google based on variant platform.
    """

    def __init__(self, store: Store, meta: Optional[MetaDeployer] = None, google: Optional[GoogleDeployer] = None):
        self.store = store
        self.meta = meta
        self.google = google

    def deploy_variant(self, variant: AdVariant, campaign_id: str, adset_or_adgroup_id: str) -> AdVariant:
        """Deploy a single approved variant to its target platform."""
        if variant.status != AdStatus.APPROVED:
            raise ValueError(f"Variant {variant.id} is {variant.status}, not APPROVED")

        platform = variant.taxonomy.platform

        if platform == Platform.META:
            if not self.meta:
                raise RuntimeError("Meta deployer not configured")
            ad_id = self.meta.create_ad(variant, campaign_id, adset_or_adgroup_id)
            variant.meta_ad_id = ad_id

        elif platform == Platform.GOOGLE:
            if not self.google:
                raise RuntimeError("Google deployer not configured")
            ad_id = self.google.create_ad(variant, campaign_id, adset_or_adgroup_id)
            variant.google_ad_id = ad_id

        variant.status = AdStatus.LIVE
        self.store.save_variant(variant)
        return variant

    def deploy_batch(self, variant_ids: list[str], campaign_id: str, adset_or_adgroup_id: str) -> list[AdVariant]:
        """Deploy all approved variants in a batch."""
        results = []
        for vid in variant_ids:
            variant = self.store.get_variant(vid)
            deployed = self.deploy_variant(variant, campaign_id, adset_or_adgroup_id)
            results.append(deployed)
        return results

    def kill_variant(self, variant: AdVariant) -> AdVariant:
        """Kill a live ad — remove from platform and mark as killed."""
        if variant.taxonomy.platform == Platform.META and variant.meta_ad_id:
            if self.meta:
                self.meta.delete_ad(variant.meta_ad_id)
        elif variant.taxonomy.platform == Platform.GOOGLE and variant.google_ad_id:
            if self.google:
                self.google.pause_ad(variant.google_ad_id)

        variant.status = AdStatus.KILLED
        self.store.save_variant(variant)
        return variant

    def pause_variant(self, variant: AdVariant) -> AdVariant:
        """Pause a live ad temporarily."""
        if variant.taxonomy.platform == Platform.META and variant.meta_ad_id:
            if self.meta:
                self.meta.pause_ad(variant.meta_ad_id)
        elif variant.taxonomy.platform == Platform.GOOGLE and variant.google_ad_id:
            if self.google:
                self.google.pause_ad(variant.google_ad_id)

        variant.status = AdStatus.PAUSED
        self.store.save_variant(variant)
        return variant
