"""
Render the staged Aryan ads into a single local HTML page.

Reads data/ads-reports/aryan-stage-2026-04-20.json, extracts the Meta preview
iframe HTML per ad per format, emits a self-contained HTML file showing
every ad in every format side-by-side.

Usage: python3 scripts/render_aryan_previews.py
Opens at: open data/ads-reports/aryan-stage-2026-04-20.html
"""
from __future__ import annotations

import html as htmllib
import json
from pathlib import Path

STATE_PATH = Path("data/ads-reports/aryan-stage-2026-04-20.json")
OUT_PATH = Path("data/ads-reports/aryan-stage-2026-04-20.html")

FORMAT_LABELS = {
    "INSTAGRAM_REELS": "IG Reels",
    "INSTAGRAM_STORY": "IG Story",
    "FACEBOOK_REELS_MOBILE": "FB Reels",
    "INSTAGRAM_STANDARD": "IG Feed",
    "MOBILE_FEED_STANDARD": "FB Feed",
}


def main() -> None:
    state = json.loads(STATE_PATH.read_text())
    items = [i for i in state["items"] if "ad_id" in i and i.get("previews")]

    parts = [
        "<!doctype html>",
        "<meta charset='utf-8'>",
        "<title>Aryan Batch — Meta Preview 2026-04-20</title>",
        "<style>",
        "body { font: 14px/1.4 -apple-system, system-ui, sans-serif; margin: 24px; background: #fafafa; }",
        "h1 { margin: 0 0 4px; font-weight: 600; }",
        "h2 { margin: 32px 0 8px; padding-top: 24px; border-top: 1px solid #ddd; }",
        ".meta { color: #666; font-size: 13px; margin-bottom: 12px; }",
        ".meta code { background: #eee; padding: 1px 5px; border-radius: 3px; }",
        ".copy { background: #fff; border: 1px solid #e0e0e0; padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; max-width: 900px; }",
        ".copy-row { margin: 4px 0; }",
        ".copy-row .k { color: #888; display: inline-block; width: 120px; font-size: 12px; text-transform: uppercase; }",
        ".previews { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 16px; }",
        ".preview { background: #fff; border: 1px solid #e0e0e0; border-radius: 6px; padding: 8px; }",
        ".preview-label { font-weight: 600; font-size: 12px; color: #444; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px; }",
        ".preview iframe { width: 100%; height: 720px; border: 0; }",
        "</style>",
        f"<h1>Aryan Batch — Meta Preview</h1>",
        f"<div class='meta'>Staged {len(items)} ads · adset <code>{state['target_adset_id']}</code> · all PAUSED · rendered 2026-04-20</div>",
    ]

    for item in items:
        ad_name = item["ad_name"]
        previews = item.get("previews", {})

        parts.append(f"<h2>{htmllib.escape(ad_name)}</h2>")
        parts.append("<div class='meta'>")
        parts.append(f"ad <code>{item['ad_id']}</code> · creative <code>{item['creative_id']}</code> · video <code>{item['video_id']}</code>")
        parts.append("</div>")

        parts.append("<div class='previews'>")
        for fmt in ["INSTAGRAM_REELS", "INSTAGRAM_STORY", "FACEBOOK_REELS_MOBILE", "INSTAGRAM_STANDARD", "MOBILE_FEED_STANDARD"]:
            body = previews.get(fmt, "")
            label = FORMAT_LABELS.get(fmt, fmt)
            parts.append(f"<div class='preview'><div class='preview-label'>{label}</div>{body}</div>")
        parts.append("</div>")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(parts))
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
