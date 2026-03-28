"""
Ad Deployer — pushes approved variants to Meta and Google.

Meta: Marketing API (v21.0+) via facebook_business SDK.
Google: Google Ads API (v17+) — still stubbed.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from engine.models import AdVariant, AdStatus, Platform
from engine.store import Store

JOTPSYCH_SIGNUP_URL = "https://app.jotpsych.com/signup"

CTA_MAP = {
    "Learn More": "LEARN_MORE",
    "Sign Up": "SIGN_UP",
    "Get Started": "SIGN_UP",
    "Try Free": "SIGN_UP",
    "Start Free Trial": "SIGN_UP",
    "Download": "DOWNLOAD",
    "Book Now": "BOOK_TRAVEL",
    "Contact Us": "CONTACT_US",
    "Apply Now": "APPLY_NOW",
}


def _retry(fn, retries=3, backoff=1.0):
    """Call fn() with exponential backoff on failure."""
    for attempt in range(retries):
        try:
            return fn()
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(backoff * (2 ** attempt))


class MetaDeployer:
    """
    Deploys ads to Meta (Facebook/Instagram) via Marketing API.

    Requires META_ACCESS_TOKEN and META_AD_ACCOUNT_ID.
    Ads are created in PAUSED status for safety — activate manually in Ads Manager.
    """

    def __init__(self, access_token: str, ad_account_id: str, page_id: str = ""):
        from facebook_business.api import FacebookAdsApi
        from facebook_business.adobjects.adaccount import AdAccount

        FacebookAdsApi.init(app_id=None, app_secret=None, access_token=access_token)
        self.access_token = access_token
        self.ad_account_id = ad_account_id
        self.page_id = page_id
        self.account = AdAccount(ad_account_id)

    def upload_asset(self, variant: AdVariant) -> str:
        """Upload image to Meta CDN. Returns the image_hash."""
        from facebook_business.adobjects.adimage import AdImage

        image = AdImage(parent_id=self.ad_account_id)
        image[AdImage.Field.filename] = str(Path(variant.asset_path).resolve())
        _retry(image.remote_create)
        return image[AdImage.Field.hash]

    def create_ad(self, variant: AdVariant, campaign_id: str, adset_id: str) -> str:
        """
        Create a full ad: upload asset -> create AdCreative -> create Ad.
        Returns the Meta ad ID. Ad is created in PAUSED status.
        """
        from facebook_business.adobjects.adcreative import AdCreative
        from facebook_business.adobjects.ad import Ad

        image_hash = self.upload_asset(variant)

        cta_type = CTA_MAP.get(variant.cta_button, "LEARN_MORE")

        object_story_spec = {
            "page_id": self.page_id,
            "link_data": {
                "image_hash": image_hash,
                "link": JOTPSYCH_SIGNUP_URL,
                "message": variant.primary_text or "",
                "name": variant.headline or "",
                "description": variant.description or "",
                "call_to_action": {
                    "type": cta_type,
                    "value": {"link": JOTPSYCH_SIGNUP_URL},
                },
            },
        }

        creative = AdCreative(parent_id=self.ad_account_id)
        creative[AdCreative.Field.name] = (variant.headline or "Ad")[:255]
        creative[AdCreative.Field.object_story_spec] = object_story_spec
        _retry(creative.remote_create)
        creative_id = creative["id"]

        ad = Ad(parent_id=self.ad_account_id)
        ad[Ad.Field.name] = (variant.headline or "Ad")[:255]
        ad[Ad.Field.adset_id] = adset_id
        ad[Ad.Field.creative] = {"creative_id": creative_id}
        ad[Ad.Field.status] = "PAUSED"
        _retry(ad.remote_create)
        return ad["id"]

    def pause_ad(self, meta_ad_id: str) -> bool:
        """Pause a running ad."""
        from facebook_business.adobjects.ad import Ad
        ad = Ad(meta_ad_id)
        ad[Ad.Field.status] = "PAUSED"
        _retry(lambda: ad.remote_update(params={Ad.Field.status: "PAUSED"}))
        return True

    def resume_ad(self, meta_ad_id: str) -> bool:
        """Resume a paused ad."""
        from facebook_business.adobjects.ad import Ad
        ad = Ad(meta_ad_id)
        _retry(lambda: ad.remote_update(params={Ad.Field.status: "ACTIVE"}))
        return True

    def delete_ad(self, meta_ad_id: str) -> bool:
        """Delete (archive) an ad."""
        from facebook_business.adobjects.ad import Ad
        ad = Ad(meta_ad_id)
        _retry(lambda: ad.remote_update(params={Ad.Field.status: "DELETED"}))
        return True


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
