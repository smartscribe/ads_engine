"""
Stage Aryan's 6 UGC + Wildcard videos as PAUSED ads in Farm: All Value Props Q226.

Pipeline per video:
  1. Upload mp4 to /act_{account}/advideos
  2. Poll /{video_id}?fields=status until status.video_status == 'ready'
  3. Fetch preferred thumbnail URL
  4. Create AdCreative with object_story_spec.video_data (page + IG + CTA + UTMs)
  5. Create Ad in target adset with status=PAUSED
  6. Fetch Feed/Reels/Stories preview iframe URLs

All state saved to data/ads-reports/aryan-stage-2026-04-20.json for rollback.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

API = "https://graph.facebook.com/v21.0"

SOURCE_DIR = Path("/Users/nathanpeereboom/Downloads/ugc_wild_video_ads (1)")
CSV_PATH = SOURCE_DIR / "Video Ads Meta Copy.csv"
OUT_PATH = Path("data/ads-reports/aryan-stage-2026-04-20.json")

PAGE_ID = "127683153772433"
INSTAGRAM_ACTOR_ID = "17841466259294846"
TARGET_ADSET_ID = "120245455503860548"  # Farm: All Value Props Q226

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


def parse_csv(path: Path) -> list[dict]:
    import csv
    rows = []
    with path.open() as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


def upload_video(tok: str, acct: str, file_path: Path, name: str) -> str:
    """POST the mp4 as multipart. Returns video_id."""
    with file_path.open("rb") as f:
        r = requests.post(
            f"{API}/{acct}/advideos",
            data={"access_token": tok, "name": name},
            files={"source": (file_path.name, f, "video/mp4")},
            timeout=300,
        )
    r.raise_for_status()
    return r.json()["id"]


def wait_for_ready(tok: str, video_id: str, timeout_s: int = 600) -> str:
    """Poll video status until ready. Returns final video_status."""
    deadline = time.time() + timeout_s
    last = None
    while time.time() < deadline:
        r = requests.get(
            f"{API}/{video_id}",
            params={"access_token": tok, "fields": "status"},
            timeout=30,
        )
        r.raise_for_status()
        status = r.json().get("status", {})
        vs = status.get("video_status")
        if vs != last:
            print(f"    video {video_id}: {vs}", file=sys.stderr)
            last = vs
        if vs == "ready":
            return vs
        if vs == "error":
            raise RuntimeError(f"video {video_id} failed: {status}")
        time.sleep(10)
    raise TimeoutError(f"video {video_id} not ready after {timeout_s}s (last={last})")


def preferred_thumbnail(tok: str, video_id: str) -> str:
    """Return URL of preferred auto-generated thumbnail."""
    r = requests.get(
        f"{API}/{video_id}/thumbnails",
        params={"access_token": tok},
        timeout=30,
    )
    r.raise_for_status()
    thumbs = r.json().get("data", [])
    if not thumbs:
        raise RuntimeError(f"no thumbnails for video {video_id}")
    preferred = next((t for t in thumbs if t.get("is_preferred")), thumbs[0])
    return preferred["uri"]


def create_creative(tok: str, acct: str, row: dict, video_id: str, thumb_url: str) -> str:
    """Create AdCreative from row metadata + video. Returns creative_id."""
    cta_type = CTA_MAP.get(row["cta_button"], "SIGN_UP")
    link = LANDING_BASE  # CSV specified app.jotpsych.com; we're using jotpsych.com per user direction

    object_story_spec = {
        "page_id": PAGE_ID,
        "instagram_user_id": INSTAGRAM_ACTOR_ID,
        "video_data": {
            "video_id": video_id,
            "image_url": thumb_url,
            "title": row["headline"],
            "message": row["primary_text"],
            "link_description": row["description"],
            "call_to_action": {
                "type": cta_type,
                "value": {"link": link},
            },
        },
    }

    payload = {
        "access_token": tok,
        "name": row["ad_name"],
        "object_story_spec": json.dumps(object_story_spec),
        "url_tags": URL_TAGS,
    }
    r = requests.post(f"{API}/{acct}/adcreatives", data=payload, timeout=60)
    if not r.ok:
        raise RuntimeError(f"creative create failed for {row['ad_name']}: {r.status_code} {r.text}")
    return r.json()["id"]


def create_ad(tok: str, acct: str, row: dict, creative_id: str, adset_id: str) -> str:
    """Create Ad in target adset with PAUSED status. Returns ad_id."""
    payload = {
        "access_token": tok,
        "name": row["ad_name"],
        "adset_id": adset_id,
        "creative": json.dumps({"creative_id": creative_id}),
        "status": "PAUSED",
    }
    r = requests.post(f"{API}/{acct}/ads", data=payload, timeout=60)
    if not r.ok:
        raise RuntimeError(f"ad create failed for {row['ad_name']}: {r.status_code} {r.text}")
    return r.json()["id"]


def preview_urls(tok: str, creative_id: str) -> dict:
    """Fetch preview iframe HTML per format."""
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

    rows = parse_csv(CSV_PATH)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUT_PATH.exists():
        state = json.loads(OUT_PATH.read_text())
        done_names = {i["ad_name"] for i in state.get("items", []) if "ad_id" in i}
        print(f"Resuming: {len(done_names)} already staged, will skip those\n", file=sys.stderr)
    else:
        state = {
            "generated_at": "2026-04-20",
            "source_dir": str(SOURCE_DIR),
            "target_adset_id": TARGET_ADSET_ID,
            "page_id": PAGE_ID,
            "landing_base": LANDING_BASE,
            "url_tags": URL_TAGS,
            "items": [],
        }
        done_names = set()

    print(f"Staging {len(rows)} ads into adset {TARGET_ADSET_ID} as PAUSED\n", file=sys.stderr)

    for row in rows:
        if row["ad_name"] in done_names:
            print(f"[{row['ad_name']}] already staged, skipping", file=sys.stderr)
            continue
        existing = next((i for i in state["items"] if i["ad_name"] == row["ad_name"]), None)
        if existing:
            existing.clear()
            item = existing
            item.update({"ad_name": row["ad_name"], "filename": row["filename"]})
        else:
            item = {"ad_name": row["ad_name"], "filename": row["filename"]}
            state["items"].append(item)

        # CSV filenames underscore-encode both spaces AND dots; real files keep dots.
        # Normalize both sides to a-z0-9 tokens joined by _ and compare.
        import re
        def norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
        actual = None
        csv_key = norm(row["filename"].rsplit(".", 1)[0])
        for f in SOURCE_DIR.glob("*.mp4"):
            if norm(f.stem) == csv_key:
                actual = f
                break
        if actual is None:
            item["error"] = f"file not found for {row['filename']}"
            print(f"  SKIP {row['ad_name']}: {item['error']}", file=sys.stderr)
            continue
        item["local_path"] = str(actual)

        try:
            print(f"[{row['ad_name']}] uploading {actual.name} ({actual.stat().st_size // 1024}KB)...", file=sys.stderr)
            video_id = upload_video(tok, acct, actual, row["ad_name"])
            item["video_id"] = video_id

            wait_for_ready(tok, video_id)

            thumb_url = preferred_thumbnail(tok, video_id)
            item["thumbnail_url"] = thumb_url

            creative_id = create_creative(tok, acct, row, video_id, thumb_url)
            item["creative_id"] = creative_id
            print(f"  creative: {creative_id}", file=sys.stderr)

            ad_id = create_ad(tok, acct, row, creative_id, TARGET_ADSET_ID)
            item["ad_id"] = ad_id
            print(f"  ad: {ad_id} (PAUSED)", file=sys.stderr)

            item["previews"] = preview_urls(tok, creative_id)
        except Exception as e:
            item["error"] = str(e)
            print(f"  FAIL {row['ad_name']}: {e}", file=sys.stderr)

        OUT_PATH.write_text(json.dumps(state, indent=2))

    ok = sum(1 for i in state["items"] if "ad_id" in i)
    print(f"\nResult: {ok}/{len(state['items'])} ads staged. State: {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
