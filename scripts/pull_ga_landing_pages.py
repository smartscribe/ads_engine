#!/usr/bin/env python3
"""
Pull GA4 landing-page performance for jotpsych.com and save as parquet.

Usage:
    python scripts/pull_ga_landing_pages.py --start 2026-03-01 --end 2026-04-12
    python scripts/pull_ga_landing_pages.py --days 30

Output: data/analytics/landing_pages_{end_date}.parquet
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


def parse_date(s: str) -> date:
    return date.fromisoformat(s)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=parse_date, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", type=parse_date, help="End date YYYY-MM-DD")
    parser.add_argument("--days", type=int, help="Alternative to --start: last N days through today")
    parser.add_argument("--output", type=Path, help="Override output path")
    parser.add_argument("--limit", type=int, default=500, help="Max rows from GA (default 500)")
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
    adc_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    if not creds_path.exists() and not adc_path.exists():
        print("ERROR: no GA credentials found.")
        print(f"  Service account JSON expected at: {creds_path}")
        print(f"  Or ADC credentials expected at:   {adc_path}")
        print("Run `gcloud auth application-default login` or drop a service-account key at the first path.")
        return 1

    if creds_path.exists():
        auth_desc = f"service account key at {creds_path}"
    else:
        auth_desc = f"ADC impersonating {settings.GA_IMPERSONATE_SA}"
    print(f"Pulling landing pages for property {settings.GA_PROPERTY_ID}")
    print(f"Range: {start} → {end}")
    print(f"Auth: {auth_desc}")

    client = GAClient(
        property_id=settings.GA_PROPERTY_ID,
        credentials_path=str(creds_path) if creds_path.exists() else None,
        impersonate_sa=settings.GA_IMPERSONATE_SA,
    )
    df = client.pull_landing_pages(start, end, limit=args.limit)

    if df.empty:
        print("No rows returned. Either the range is empty or the tag is still broken.")
        return 2

    out_path = args.output or (
        REPO_ROOT / settings.DATA_DIR / "analytics" / f"landing_pages_{end.isoformat()}.parquet"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)

    print(f"Wrote {len(df)} rows to {out_path}")
    print()
    print("Top 20 landing pages by sessions:")
    cols = ["landingPagePlusQueryString", "sessionSourceMedium", "sessions", "engagedSessions", "conversions"]
    available = [c for c in cols if c in df.columns]
    print(df[available].head(20).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
