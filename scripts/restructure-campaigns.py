#!/usr/bin/env python3
"""
Campaign restructure: OUTCOME_LEADS → OUTCOME_SALES with value prop ad sets.

Creates new Farm + Scale campaigns, 5 ad sets by value prop in Farm,
copies ads from old campaigns into correct ad sets, fixes landing pages + UTMs.
Old campaigns are PAUSED (not deleted) for rollback.

Usage:
    python scripts/restructure-campaigns.py              # full run
    python scripts/restructure-campaigns.py --dry-run    # show plan only
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
META_API = "v21.0"
BASE = f"https://graph.facebook.com/{META_API}"
ACCOUNT = "act_1582817295627677"
PIXEL = "1625233994894344"

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "audiences"
MANIFEST_DIR = Path(__file__).resolve().parents[1] / "data" / "restructure"

OLD_CAMPAIGNS = {
    "Farm: Testing - Apr 2026": None,      # ID filled at runtime
    "Scale: Winners - Apr 2026": None,
    "Scale": None,
}

UTM_TAGS = (
    "utm_source={{site_source_name}}"
    "&utm_medium=paid_social"
    "&utm_campaign={{campaign.id}}"
    "&utm_content={{adset.id}}"
    "&utm_term={{ad.id}}"
)

# Ad set definitions: name → (daily_budget_cents, landing_page)
ADSET_DEFS = {
    "Billing & Audit": {
        "budget": 8000,
        "url": "https://www.jotpsych.com/audit",
    },
    "Time Savings": {
        "budget": 3000,
        "url": "https://www.jotpsych.com/",
    },
    "EHR Integration": {
        "budget": 3000,
        "url": "https://www.jotpsych.com/features",
    },
    "UGC / Social Proof": {
        "budget": 3000,
        "url": "https://www.jotpsych.com/",
    },
    "AI Progress Concepts": {
        "budget": 3000,
        "url": "https://www.jotpsych.com/",
    },
}

# Map each existing ad name → target ad set + optional URL override
AD_ROUTING = {
    # Billing & Audit
    "AJ: Audit Letter Arrives. You're Ready": "Billing & Audit",
    "AJ: Audit Ready. Home On Time": "Billing & Audit",
    "AJ: How Much Did You Underbill?": "Billing & Audit",
    "AJ: Cigna Has Rules. JotPsych Knows Them - Copy": "Billing & Audit",
    "AN: 4 Different Logins": "Billing & Audit",
    "AN: 47 Different Payer Rules": "Billing & Audit",
    "AN: 847 Ways payers reject claims": "Billing & Audit",
    "AN: Audit Anxiety vs. Confidence": "Billing & Audit",
    "AN: Cigna vs. Aetna Rules": "Billing & Audit",
    "AN: Doing 99214, Billing 99213": "Billing & Audit",
    "AN: E-prescribe from scribe": "Billing & Audit",
    "AN: Insurance Game Has Rules": "Billing & Audit",
    "AN: JotAudit Catches What Others Miss": "Billing & Audit",
    "AN: Missing $460?": "Billing & Audit",
    "AN: Most Stop at the Note": "Billing & Audit",
    "AN: Scribe that Thinks Like an Auditor": "Billing & Audit",
    "AN: Stop leaving your practice exposed to audit risk": "Billing & Audit",
    "AN: The Work. The Bill": "Billing & Audit",
    "AN: Your Notes Are Perfect - Insurance Doesnt Care - Copy": "Billing & Audit",
    # Time Savings
    "Scale: AI for Progress Notes": "Time Savings",
    "Farm: Test: Florence Static 1 - Notes Complete": "Time Savings",
    "Farm: Nate Podcast 4 - ad": ("Time Savings", "https://www.jotpsych.com/making-time-for-presence"),
    # EHR Integration
    "Farm: EHR V2": "EHR Integration",
    "Scale: PDF to Template": "EHR Integration",
    "Farm: Test: AI for Progress: Concept 2": "EHR Integration",
    # UGC / Social Proof
    "Farm: Test: KM UGC - Video Concept 2": "UGC / Social Proof",
    # AI Progress Concepts
    "Scale: Test: AI for Progress Notes Concept 3": "AI Progress Concepts",
    "Scale: Test: AI for Progress Notes: Concept 4": "AI Progress Concepts",
    # Old Scale campaign duplicates
    "Scale: Test: KM UGC - Video Concept 1": "UGC / Social Proof",
    "AJ: Audit Letter Arrives. You're Ready - Copy": "Billing & Audit",
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Env
# ---------------------------------------------------------------------------
def load_env() -> None:
    env_path = Path.home() / ".claude" / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
TOKEN = os.environ["META_ADS_ACCESS_TOKEN"]


# ---------------------------------------------------------------------------
# Audience IDs (reuse from attach script logic)
# ---------------------------------------------------------------------------
def collect_audience_ids() -> tuple[list[dict], list[dict]]:
    include = []
    exclude = []

    chris = _latest_summary("chris-lists-upload")
    if chris.get("custom_audience_id"):
        include.append({"id": chris["custom_audience_id"]})
    if chris.get("lookalike_audience_id"):
        include.append({"id": chris["lookalike_audience_id"]})

    nppes = _latest_summary("nppes-upload")
    if nppes.get("audience_id"):
        include.append({"id": nppes["audience_id"]})

    conv = _latest_summary("converters-upload")
    if conv.get("lookalike", {}).get("id"):
        include.append({"id": conv["lookalike"]["id"]})
    if conv.get("audience_id"):
        exclude.append({"id": conv["audience_id"]})

    exc_dir = Path(__file__).resolve().parents[1] / "data" / "exclusion-logs"
    exc_logs = sorted(exc_dir.glob("sync-*.json"), reverse=True) if exc_dir.exists() else []
    if exc_logs:
        exc_data = json.loads(exc_logs[0].read_text())
        if exc_data.get("meta_audience_id"):
            exclude.append({"id": exc_data["meta_audience_id"]})

    return include, exclude


def _latest_summary(prefix: str) -> dict:
    candidates = sorted(DATA_DIR.glob(f"{prefix}*.json"), reverse=True)
    return json.loads(candidates[0].read_text()) if candidates else {}


# ---------------------------------------------------------------------------
# Meta API helpers
# ---------------------------------------------------------------------------
def api_post(endpoint: str, data: dict) -> dict:
    data["access_token"] = TOKEN
    resp = requests.post(f"{BASE}/{endpoint}", data=data, timeout=60)
    result = resp.json()
    if "error" in result:
        log(f"  API ERROR: {result['error'].get('message', '')}")
        log(f"  Detail: {result['error'].get('error_user_msg', '')}")
    return result


def api_get(endpoint: str, fields: str) -> dict:
    resp = requests.get(f"{BASE}/{endpoint}", params={
        "access_token": TOKEN, "fields": fields,
    }, timeout=60)
    return resp.json()


# ---------------------------------------------------------------------------
# Step 1: Fetch old ads
# ---------------------------------------------------------------------------
def fetch_old_ads() -> list[dict]:
    resp = requests.get(f"{BASE}/{ACCOUNT}/ads", params={
        "access_token": TOKEN,
        "fields": "id,name,status,effective_status,creative{id},adset{name},campaign{name}",
        "limit": 200,
    }, timeout=60)
    resp.raise_for_status()
    all_ads = resp.json().get("data", [])
    old = [a for a in all_ads if a.get("campaign", {}).get("name", "") in OLD_CAMPAIGNS]
    return old


# ---------------------------------------------------------------------------
# Step 2: Create campaigns
# ---------------------------------------------------------------------------
def create_campaign(name: str) -> str:
    result = api_post(f"{ACCOUNT}/campaigns", {
        "name": name,
        "objective": "OUTCOME_SALES",
        "status": "PAUSED",
        "special_ad_categories": "[]",
        "is_adset_budget_sharing_enabled": "false",
    })
    cid = result.get("id")
    if cid:
        log(f"  Created campaign: {name} = {cid}")
    return cid


# ---------------------------------------------------------------------------
# Step 3: Create ad sets
# ---------------------------------------------------------------------------
def create_adset(name: str, campaign_id: str, budget: int, url: str,
                 include: list[dict], exclude: list[dict]) -> str:
    targeting = {
        "geo_locations": {"countries": ["US"]},
        "age_min": 25,
        "age_max": 65,
        "custom_audiences": include,
        "excluded_custom_audiences": exclude,
        "targeting_automation": {"advantage_audience": 0},
    }

    result = api_post(f"{ACCOUNT}/adsets", {
        "name": name,
        "campaign_id": campaign_id,
        "status": "PAUSED",
        "billing_event": "IMPRESSIONS",
        "optimization_goal": "VALUE",
        "daily_budget": str(budget),
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "promoted_object": json.dumps({
            "pixel_id": PIXEL,
            "custom_event_type": "OTHER",
            "custom_event_str": "FirstNote",
        }),
        "targeting": json.dumps(targeting),
        "url_tags": UTM_TAGS,
        "attribution_spec": json.dumps([
            {"event_type": "CLICK_THROUGH", "window_days": 7},
            {"event_type": "VIEW_THROUGH", "window_days": 1},
        ]),
    })
    asid = result.get("id")
    if asid:
        log(f"  Created ad set: {name} = {asid} (${budget/100}/day)")
    return asid


# ---------------------------------------------------------------------------
# Step 4: Copy ads into new ad sets, fix URLs
# ---------------------------------------------------------------------------
def copy_ad_to_adset(ad: dict, new_adset_id: str, landing_url: str) -> dict:
    ad_id = ad["id"]
    ad_name = ad["name"]

    # Use Meta's ad copy endpoint
    result = api_post(f"{ad_id}/copies", {
        "adset_id": new_adset_id,
        "status_option": "PAUSED",
    })

    new_ad_id = None
    copied = result.get("copied_ad_id") or (result.get("data", [{}])[0].get("copied_ad_id") if result.get("data") else None)
    if not copied:
        # Try alternate response format
        if isinstance(result.get("data"), list) and result["data"]:
            copied = result["data"][0].get("copied_ad_id")
    if not copied:
        log(f"    FAILED to copy {ad_name}: {json.dumps(result)}")
        return {"ad_name": ad_name, "old_id": ad_id, "new_id": None, "error": str(result)}

    new_ad_id = copied
    log(f"    Copied {ad_name} → {new_ad_id}")

    # Now update the creative's destination URL on the new ad
    # First get the new ad's creative
    new_ad_data = api_get(new_ad_id, "creative{id,object_story_spec,asset_feed_spec}")
    creative = new_ad_data.get("creative", {})
    creative_id = creative.get("id")

    if creative_id:
        # Try to update link in object_story_spec
        oss = creative.get("object_story_spec", {})
        link_data = oss.get("link_data", {})
        video_data = oss.get("video_data", {})

        updated = False
        if link_data and link_data.get("link"):
            link_data["link"] = landing_url
            oss["link_data"] = link_data
            update_resp = api_post(creative_id, {
                "object_story_spec": json.dumps(oss),
            })
            if update_resp.get("success"):
                updated = True
                log(f"      URL → {landing_url}")
        elif video_data:
            cta = video_data.get("call_to_action", {})
            if cta.get("value", {}).get("link"):
                cta["value"]["link"] = landing_url
                video_data["call_to_action"] = cta
                oss["video_data"] = video_data
                update_resp = api_post(creative_id, {
                    "object_story_spec": json.dumps(oss),
                })
                if update_resp.get("success"):
                    updated = True
                    log(f"      URL → {landing_url}")

        # Handle asset_feed_spec (dynamic creative)
        afs = creative.get("asset_feed_spec", {})
        if afs and afs.get("link_urls"):
            for lu in afs["link_urls"]:
                lu["website_url"] = landing_url
            update_resp = api_post(creative_id, {
                "asset_feed_spec": json.dumps(afs),
            })
            if update_resp.get("success"):
                updated = True
                log(f"      URL (asset_feed) → {landing_url}")

        if not updated:
            log(f"      WARNING: Could not update URL for {ad_name}")

    return {"ad_name": ad_name, "old_id": ad_id, "new_id": new_ad_id, "url": landing_url}


# ---------------------------------------------------------------------------
# Step 5: Pause old campaigns
# ---------------------------------------------------------------------------
def pause_campaign(campaign_name: str, campaign_id: str) -> bool:
    result = api_post(campaign_id, {"status": "PAUSED"})
    if result.get("success"):
        log(f"  Paused: {campaign_name} ({campaign_id})")
        return True
    log(f"  FAILED to pause {campaign_name}")
    return False


# ---------------------------------------------------------------------------
# Step 6: Activate new campaign
# ---------------------------------------------------------------------------
def activate_campaign(campaign_id: str, name: str) -> bool:
    result = api_post(campaign_id, {"status": "ACTIVE"})
    if result.get("success"):
        log(f"  Activated: {name} ({campaign_id})")
        return True
    log(f"  FAILED to activate {name}")
    return False


def activate_adsets(adset_ids: list[str]) -> int:
    activated = 0
    for asid in adset_ids:
        result = api_post(asid, {"status": "ACTIVE"})
        if result.get("success"):
            activated += 1
    return activated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    dry_run = "--dry-run" in sys.argv
    today = date.today().isoformat()

    if dry_run:
        log("=== DRY RUN ===\n")

    # Fetch old ads
    log("Fetching existing ads...")
    old_ads = fetch_old_ads()
    log(f"  Found {len(old_ads)} ads in old Farm+Scale campaigns")

    # Route ads to value prop ad sets
    routed = {}  # adset_name → list of ad dicts
    unrouted = []
    for ad in old_ads:
        name = ad["name"]
        route = AD_ROUTING.get(name)
        if route is None:
            unrouted.append(name)
            continue
        if isinstance(route, tuple):
            adset_name, url_override = route
        else:
            adset_name = route
            url_override = None
        ad["_target_adset"] = adset_name
        ad["_url_override"] = url_override
        routed.setdefault(adset_name, []).append(ad)

    log(f"\nRouted {sum(len(v) for v in routed.values())} ads to {len(routed)} ad sets")
    if unrouted:
        log(f"  WARNING: {len(unrouted)} unrouted ads: {unrouted}")

    for adset_name, ads in sorted(routed.items()):
        url = ADSET_DEFS[adset_name]["url"]
        budget = ADSET_DEFS[adset_name]["budget"]
        log(f"\n  {adset_name} (${budget/100}/day → {url})")
        for ad in ads:
            override = ad.get("_url_override", "")
            dest = override or url
            log(f"    {ad['name']} → {dest}")

    if dry_run:
        log("\n=== DRY RUN COMPLETE ===")
        return

    # Collect audiences
    log("\nCollecting audience IDs...")
    include, exclude = collect_audience_ids()
    log(f"  {len(include)} inclusion, {len(exclude)} exclusion")

    # Create campaigns
    log("\nCreating campaigns...")
    farm_id = create_campaign("Farm: Testing - Q226")
    scale_id = create_campaign("Scale: Winners - Q226")
    if not farm_id or not scale_id:
        log("FATAL: Failed to create campaigns.")
        sys.exit(1)

    # Create ad sets in Farm
    log("\nCreating ad sets...")
    adset_ids = {}
    for adset_name, config in ADSET_DEFS.items():
        asid = create_adset(
            adset_name, farm_id, config["budget"], config["url"],
            include, exclude,
        )
        if asid:
            adset_ids[adset_name] = asid
        else:
            log(f"FATAL: Failed to create ad set {adset_name}")
            sys.exit(1)
        time.sleep(0.5)

    # Copy ads
    log("\nCopying ads to new ad sets...")
    manifest = []
    for adset_name, ads in routed.items():
        new_adset_id = adset_ids[adset_name]
        default_url = ADSET_DEFS[adset_name]["url"]
        log(f"\n  → {adset_name} ({new_adset_id})")
        for ad in ads:
            url = ad.get("_url_override") or default_url
            result = copy_ad_to_adset(ad, new_adset_id, url)
            manifest.append(result)
            time.sleep(0.3)

    # Verify
    log("\nVerifying new ad sets...")
    for adset_name, asid in adset_ids.items():
        check = api_get(asid, "id,name,optimization_goal,promoted_object,targeting,url_tags,daily_budget")
        opt = check.get("optimization_goal")
        budget = check.get("daily_budget")
        tags = check.get("url_tags", "")
        n_include = len(check.get("targeting", {}).get("custom_audiences", []))
        n_exclude = len(check.get("targeting", {}).get("excluded_custom_audiences", []))
        log(f"  {adset_name}: opt={opt}, budget=${int(budget)/100 if budget else '?'}/day, audiences={n_include}in/{n_exclude}ex, utm={'OK' if 'utm_source' in tags else 'MISSING'}")

    # Pause old campaigns
    log("\nPausing old campaigns...")
    resp = requests.get(f"{BASE}/{ACCOUNT}/campaigns", params={
        "access_token": TOKEN,
        "fields": "id,name,status",
        "limit": 50,
    }, timeout=60)
    for c in resp.json().get("data", []):
        if c["name"] in OLD_CAMPAIGNS and c.get("status") == "ACTIVE":
            pause_campaign(c["name"], c["id"])
            OLD_CAMPAIGNS[c["name"]] = c["id"]

    # Activate new Farm
    log("\nActivating new Farm campaign + ad sets...")
    activate_campaign(farm_id, "Farm: Testing - Q226")
    activated = activate_adsets(list(adset_ids.values()))
    log(f"  {activated}/{len(adset_ids)} ad sets activated")

    # Save manifest
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    manifest_data = {
        "date": today,
        "new_farm_campaign_id": farm_id,
        "new_scale_campaign_id": scale_id,
        "old_campaigns": OLD_CAMPAIGNS,
        "adset_ids": adset_ids,
        "ad_copies": manifest,
        "audiences": {"include": include, "exclude": exclude},
    }
    manifest_path = MANIFEST_DIR / f"restructure-{today}.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2, default=str))
    log(f"\nManifest saved → {manifest_path}")

    # Summary
    copied_ok = sum(1 for m in manifest if m.get("new_id"))
    copied_fail = sum(1 for m in manifest if not m.get("new_id"))
    log(f"\n{'='*60}")
    log(f"DONE.")
    log(f"  New Farm campaign: {farm_id}")
    log(f"  New Scale campaign: {scale_id} (empty, for winners)")
    log(f"  Ad sets created: {len(adset_ids)}")
    log(f"  Ads copied: {copied_ok} OK, {copied_fail} failed")
    log(f"  Old campaigns: paused")
    log(f"  Rollback: reactivate old campaigns, pause new ones")


if __name__ == "__main__":
    main()
