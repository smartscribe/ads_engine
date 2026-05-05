#!/usr/bin/env python3
"""
Pull GA4 attribution matrix for jotpsych.com marketing site.

Four views: source × event, landing × event, campaign × event,
source × landing × event. Filtered to hostname = jotpsych.com
to exclude app.jotpsych.com traffic.

Usage:
    python scripts/pull_attribution_matrix.py --days 28
    python scripts/pull_attribution_matrix.py --start 2026-03-25 --end 2026-04-21

Output: data/analytics/attribution-{end_date}/{view}.parquet
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config.settings import get_settings
from engine.tracking.ga_tracker import GAClient


HOSTNAME = "jotpsych.com"
METRICS = ["eventCount", "keyEvents", "totalUsers", "newUsers"]

VIEWS = {
    "source-x-event": ["sessionSourceMedium", "eventName"],
    "landing-x-event": ["landingPagePlusQueryString", "eventName"],
    "campaign-x-event": ["sessionCampaignName", "eventName"],
    "source-x-landing-x-event": ["sessionSourceMedium", "landingPagePlusQueryString", "eventName"],
}


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=parse_date, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=parse_date, help="End date YYYY-MM-DD")
    parser.add_argument("--days", type=int, help="Last N days through today")
    parser.add_argument("--property", dest="property_id", type=str, help="Override GA property ID (default from settings)")
    parser.add_argument("--limit", type=int, default=10000, help="Max rows per view")
    parser.add_argument("--head", type=int, default=10, help="Top rows to print per view")
    args = parser.parse_args()

    if args.days:
        end = date.today()
        start = end - timedelta(days=args.days)
    elif args.start and args.end:
        start, end = args.start, args.end
    else:
        parser.error("Provide --days, or both --start and --end")

    settings = get_settings()
    creds_path = Path(settings.GA_CREDENTIALS_PATH)
    property_id = args.property_id or settings.GA_PROPERTY_ID

    client = GAClient(
        property_id=property_id,
        credentials_path=str(creds_path) if creds_path.exists() else None,
        impersonate_sa=settings.GA_IMPERSONATE_SA,
    )

    out_dir = REPO_ROOT / settings.DATA_DIR / "analytics" / f"attribution-{end.isoformat()}-p{property_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"GA property {property_id}   hostname={HOSTNAME}   range={start} → {end}")
    print(f"Output: {out_dir}")

    for name, dimensions in VIEWS.items():
        df = client.pull_report(
            dimensions=dimensions,
            metrics=METRICS,
            start_date=start,
            end_date=end,
            hostname=HOSTNAME,
            limit=args.limit,
        )
        path = out_dir / f"{name}.parquet"
        df.to_parquet(path, index=False)
        print(f"\n[{name}] {len(df)} rows → {path.name}")
        if not df.empty:
            print(df.head(args.head).to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
