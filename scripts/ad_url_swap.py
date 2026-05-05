"""
Batch URL/UTM swap for 7 Meta ads (audit + podcast), preserving the one
performing ad (AJ Audit Letter Farm) untouched.

Reads the backup at data/ads-reports/creative-swap-backup-2026-04-14.json,
builds new creatives by cloning each source's object_story_spec + asset_feed_spec
+ degrees_of_freedom_spec with an updated link, POSTs them, then swaps each ad
to point at its new creative. Verifies the new links go live. Writes an
execution log to the same backup file.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import requests

BACKUP_PATH = Path("data/ads-reports/creative-swap-backup-2026-04-14.json")
API = "https://graph.facebook.com/v21.0"

NEW_URL_TAGS = (
    "utm_source={{site_source_name}}"
    "&utm_medium=paid_social"
    "&utm_campaign={{campaign.id}}"
    "&utm_content={{adset.id}}"
    "&utm_term={{ad.id}}"
)

NEW_BASE = "https://jotpsych.com"


def build_new_spec(src_full: dict, new_link: str) -> dict:
    """Transform source creative spec → new creative spec with updated link."""
    oss = copy.deepcopy(src_full.get("object_story_spec") or {})

    if "link_data" in oss:
        oss["link_data"]["link"] = new_link
    elif "video_data" in oss:
        cta = oss["video_data"].setdefault("call_to_action", {})
        cta.setdefault("value", {})["link"] = new_link
        # Meta now requires only one of image_url or image_hash — keep hash, drop URL
        oss["video_data"].pop("image_url", None)
    else:
        raise ValueError("source has neither link_data nor video_data")

    new_creative = {
        "object_story_spec": oss,
        "url_tags": NEW_URL_TAGS,
    }

    if src_full.get("asset_feed_spec"):
        new_creative["asset_feed_spec"] = copy.deepcopy(src_full["asset_feed_spec"])
    if src_full.get("degrees_of_freedom_spec"):
        dof = copy.deepcopy(src_full["degrees_of_freedom_spec"])
        # standard_enhancements is deprecated on new creatives — strip it
        cfs = dof.get("creative_features_spec") or {}
        cfs.pop("standard_enhancements", None)
        new_creative["degrees_of_freedom_spec"] = dof

    return new_creative


def main() -> None:
    tok = os.environ["META_ADS_ACCESS_TOKEN"]
    acct = os.environ["META_ADS_ACCOUNT_ID"]
    if not acct.startswith("act_"):
        acct = f"act_{acct}"

    backup = json.loads(BACKUP_PATH.read_text())
    swaps = backup["swaps"]

    # Phase A: build new creative specs
    for s in swaps:
        new_link = f"{NEW_BASE}{s['new_path']}"
        s["new_link"] = new_link
        s["new_spec"] = build_new_spec(s["full_spec"], new_link)
        s["new_spec"]["name"] = f"{s['label']} — URL swap 2026-04-14"

    # Phase B: POST new creatives
    print("=== Creating new creatives ===", file=sys.stderr)
    for s in swaps:
        payload = dict(s["new_spec"])
        for k in ("object_story_spec", "asset_feed_spec", "degrees_of_freedom_spec"):
            if k in payload:
                payload[k] = json.dumps(payload[k])
        payload["access_token"] = tok
        r = requests.post(f"{API}/{acct}/adcreatives", data=payload, timeout=60)
        if not r.ok:
            s["create_error"] = r.text
            print(f"  FAIL {s['label']}: {r.status_code} {r.text[:400]}", file=sys.stderr)
            continue
        new_id = r.json().get("id")
        s["new_creative_id"] = new_id
        print(f"  OK   {s['label']:45s} new_creative={new_id}", file=sys.stderr)

    failed = [s for s in swaps if "new_creative_id" not in s]
    if failed:
        BACKUP_PATH.write_text(json.dumps(backup, indent=2))
        print(f"\nABORT: {len(failed)} creative creates failed. No ads updated. Backup has partial state for manual review.", file=sys.stderr)
        sys.exit(1)

    # Phase C: swap creatives on ads
    print("\n=== Swapping ad creatives ===", file=sys.stderr)
    for s in swaps:
        r = requests.post(
            f"{API}/{s['ad_id']}",
            data={
                "creative": json.dumps({"creative_id": s["new_creative_id"]}),
                "access_token": tok,
            },
            timeout=60,
        )
        if not r.ok:
            s["swap_error"] = r.text
            print(f"  FAIL {s['ad_name']}: {r.status_code} {r.text[:400]}", file=sys.stderr)
            continue
        s["swap_ok"] = True
        print(f"  OK   {s['ad_name'][:55]:55s} → creative {s['new_creative_id']}", file=sys.stderr)

    # Phase D: verify
    print("\n=== Verifying new links live ===", file=sys.stderr)
    for s in swaps:
        if not s.get("swap_ok"):
            continue
        r = requests.get(
            f"{API}/{s['ad_id']}",
            params={
                "access_token": tok,
                "fields": "creative{id,object_story_spec{link_data{link},video_data{call_to_action{value{link}}}},url_tags}",
            },
            timeout=30,
        )
        if not r.ok:
            s["verify_error"] = r.text
            continue
        c = (r.json().get("creative") or {})
        oss = c.get("object_story_spec") or {}
        live_link = (
            (oss.get("link_data") or {}).get("link")
            or ((oss.get("video_data") or {}).get("call_to_action") or {}).get("value", {}).get("link")
        )
        live_tags = c.get("url_tags")
        s["live_link"] = live_link
        s["live_url_tags"] = live_tags
        match = live_link == s["new_link"]
        print(f"  {'OK' if match else 'MISMATCH'}  {s['ad_name'][:50]:50s} link={live_link}", file=sys.stderr)

    BACKUP_PATH.write_text(json.dumps(backup, indent=2))
    print(f"\nBackup + execution log saved to {BACKUP_PATH}", file=sys.stderr)

    n_ok = sum(1 for s in swaps if s.get("swap_ok") and s.get("live_link") == s["new_link"])
    print(f"\nResult: {n_ok}/{len(swaps)} ads swapped and verified", file=sys.stderr)


if __name__ == "__main__":
    main()
