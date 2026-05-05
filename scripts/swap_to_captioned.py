"""
Swap each of the 6 staged Aryan ads to use the captioned version of its video.

Pipeline per item in aryan-stage-2026-04-20.json:
  1. Upload data/captioned-videos/{stem}.captioned.mp4 → new video_id
  2. Wait for processing
  3. Fetch preferred thumbnail
  4. POST new AdCreative (same object_story_spec shape as before, new video + thumb)
  5. PATCH ad to point at new creative_id (keeps old creative as rollback)
  6. Re-fetch preview iframes

Updates state JSON in place. Old creative_id preserved as rollback.creative_id.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

import requests

API = "https://graph.facebook.com/v21.0"

STATE_PATH = Path("data/ads-reports/aryan-stage-2026-04-20.json")
CSV_PATH = Path("/Users/nathanpeereboom/Downloads/ugc_wild_video_ads (1)/Video Ads Meta Copy.csv")
CAPTIONED_DIR = Path("data/captioned-videos")

PAGE_ID = "127683153772433"
INSTAGRAM_ACTOR_ID = "17841466259294846"

LANDING_BASE = "https://jotpsych.com"
URL_TAGS = (
    "utm_source={{site_source_name}}"
    "&utm_medium=paid_social"
    "&utm_campaign={{campaign.id}}"
    "&utm_content={{adset.id}}"
    "&utm_term={{ad.id}}"
)
CTA_MAP = {"Sign Up": "SIGN_UP", "Learn More": "LEARN_MORE"}

PREVIEW_FORMATS = [
    "INSTAGRAM_REELS",
    "INSTAGRAM_STORY",
    "FACEBOOK_REELS_MOBILE",
    "INSTAGRAM_STANDARD",
    "MOBILE_FEED_STANDARD",
]


def load_csv_by_ad_name() -> dict[str, dict]:
    with CSV_PATH.open() as f:
        return {row["ad_name"]: row for row in csv.DictReader(f)}


def captioned_path_for(item: dict) -> Path:
    """Derive captioned mp4 path from the item's local_path (real filename w/ spaces)."""
    local = Path(item["local_path"])
    stem = local.stem.replace(" ", "_")
    return CAPTIONED_DIR / f"{stem}.captioned.mp4"


def upload_video(tok: str, acct: str, file_path: Path, name: str) -> str:
    with file_path.open("rb") as f:
        r = requests.post(
            f"{API}/{acct}/advideos",
            data={"access_token": tok, "name": name},
            files={"source": (file_path.name, f, "video/mp4")},
            timeout=300,
        )
    r.raise_for_status()
    return r.json()["id"]


def wait_for_ready(tok: str, video_id: str, timeout_s: int = 600) -> None:
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        r = requests.get(
            f"{API}/{video_id}",
            params={"access_token": tok, "fields": "status"},
            timeout=30,
        )
        r.raise_for_status()
        vs = r.json().get("status", {}).get("video_status")
        if vs != last:
            print(f"    video {video_id}: {vs}", file=sys.stderr)
            last = vs
        if vs == "ready":
            return
        if vs == "error":
            raise RuntimeError(f"video {video_id} failed")
        time.sleep(10)
    raise TimeoutError(f"video {video_id} not ready after {timeout_s}s")


def preferred_thumbnail(tok: str, video_id: str) -> str:
    r = requests.get(f"{API}/{video_id}/thumbnails", params={"access_token": tok}, timeout=30)
    r.raise_for_status()
    thumbs = r.json().get("data", [])
    if not thumbs:
        raise RuntimeError(f"no thumbnails for {video_id}")
    preferred = next((t for t in thumbs if t.get("is_preferred")), thumbs[0])
    return preferred["uri"]


def create_creative(tok: str, acct: str, row: dict, video_id: str, thumb_url: str) -> str:
    cta_type = CTA_MAP.get(row["cta_button"], "SIGN_UP")
    object_story_spec = {
        "page_id": PAGE_ID,
        "instagram_user_id": INSTAGRAM_ACTOR_ID,
        "video_data": {
            "video_id": video_id,
            "image_url": thumb_url,
            "title": row["headline"],
            "message": row["primary_text"],
            "link_description": row["description"],
            "call_to_action": {"type": cta_type, "value": {"link": LANDING_BASE}},
        },
    }
    payload = {
        "access_token": tok,
        "name": f"{row['ad_name']} (captioned)",
        "object_story_spec": json.dumps(object_story_spec),
        "url_tags": URL_TAGS,
    }
    r = requests.post(f"{API}/{acct}/adcreatives", data=payload, timeout=60)
    if not r.ok:
        raise RuntimeError(f"creative create failed: {r.status_code} {r.text}")
    return r.json()["id"]


def swap_ad_creative(tok: str, ad_id: str, new_creative_id: str) -> None:
    r = requests.post(
        f"{API}/{ad_id}",
        data={
            "access_token": tok,
            "creative": json.dumps({"creative_id": new_creative_id}),
        },
        timeout=60,
    )
    if not r.ok:
        raise RuntimeError(f"ad swap failed: {r.status_code} {r.text}")


def preview_urls(tok: str, creative_id: str) -> dict:
    out = {}
    for fmt in PREVIEW_FORMATS:
        r = requests.get(
            f"{API}/{creative_id}/previews",
            params={"access_token": tok, "ad_format": fmt},
            timeout=30,
        )
        if r.ok:
            body = (r.json().get("data") or [{}])[0].get("body", "")
            out[fmt] = body
        else:
            out[fmt] = f"ERROR {r.status_code}: {r.text[:200]}"
    return out


def main() -> None:
    tok = os.environ["META_ADS_ACCESS_TOKEN"]
    acct = os.environ["META_ADS_ACCOUNT_ID"]
    if not acct.startswith("act_"):
        acct = f"act_{acct}"

    state = json.loads(STATE_PATH.read_text())
    rows_by_name = load_csv_by_ad_name()

    for item in state["items"]:
        if "ad_id" not in item:
            continue
        if item.get("captioned", {}).get("ad_swapped"):
            print(f"[{item['ad_name']}] already swapped, skipping", file=sys.stderr)
            continue

        cap_mp4 = captioned_path_for(item)
        if not cap_mp4.exists():
            print(f"[{item['ad_name']}] no captioned mp4 at {cap_mp4}, skipping", file=sys.stderr)
            continue

        row = rows_by_name[item["ad_name"]]
        captioned: dict = item.setdefault("captioned", {})

        try:
            if "video_id" not in captioned:
                print(f"[{item['ad_name']}] uploading {cap_mp4.name}...", file=sys.stderr)
                captioned["video_id"] = upload_video(tok, acct, cap_mp4, f"{item['ad_name']} captioned")
                STATE_PATH.write_text(json.dumps(state, indent=2))

            wait_for_ready(tok, captioned["video_id"])

            if "thumbnail_url" not in captioned:
                captioned["thumbnail_url"] = preferred_thumbnail(tok, captioned["video_id"])

            if "creative_id" not in captioned:
                cid = create_creative(tok, acct, row, captioned["video_id"], captioned["thumbnail_url"])
                captioned["creative_id"] = cid
                print(f"  creative: {cid}", file=sys.stderr)
                STATE_PATH.write_text(json.dumps(state, indent=2))

            if not captioned.get("ad_swapped"):
                item.setdefault("rollback", {})["creative_id"] = item["creative_id"]
                swap_ad_creative(tok, item["ad_id"], captioned["creative_id"])
                captioned["ad_swapped"] = True
                item["creative_id"] = captioned["creative_id"]
                print(f"  ad {item['ad_id']} → creative {captioned['creative_id']}", file=sys.stderr)
                STATE_PATH.write_text(json.dumps(state, indent=2))

            item["previews"] = preview_urls(tok, captioned["creative_id"])
            STATE_PATH.write_text(json.dumps(state, indent=2))

        except Exception as e:
            captioned["error"] = str(e)
            print(f"  FAIL {item['ad_name']}: {e}", file=sys.stderr)
            STATE_PATH.write_text(json.dumps(state, indent=2))

    ok = sum(1 for i in state["items"] if i.get("captioned", {}).get("ad_swapped"))
    print(f"\nResult: {ok}/{len(state['items'])} ads swapped to captioned", file=sys.stderr)


if __name__ == "__main__":
    main()
