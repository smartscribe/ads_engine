"""
Pull ad-level Meta insights for the last 10 days (2026-04-04 .. 2026-04-13).
Saves raw JSON to data/ads-reports/raw-10d-<today>.json for downstream analysis.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount

SINCE = "2026-04-04"
UNTIL = "2026-04-13"
TODAY = date.today().isoformat()

OUT = Path("data/ads-reports") / f"raw-10d-{TODAY}.json"


def main() -> None:
    tok = os.environ["META_ADS_ACCESS_TOKEN"]
    acct = os.environ["META_ADS_ACCOUNT_ID"]
    if not acct.startswith("act_"):
        acct = f"act_{acct}"

    FacebookAdsApi.init(access_token=tok)
    account = AdAccount(acct)

    fields = [
        "ad_id", "ad_name", "adset_id", "adset_name",
        "campaign_id", "campaign_name",
        "spend", "impressions", "reach", "clicks",
        "ctr", "cpc", "cpm", "frequency",
        "actions", "cost_per_action_type",
        "conversions", "cost_per_conversion",
    ]
    params = {
        "level": "ad",
        "time_range": {"since": SINCE, "until": UNTIL},
        "time_increment": "all_days",
        "limit": 500,
        "filtering": [{"field": "spend", "operator": "GREATER_THAN", "value": 0}],
    }

    print(f"Pulling ad-level insights {SINCE}..{UNTIL} from {acct}...", file=sys.stderr)
    cursor = account.get_insights(fields=fields, params=params)
    rows: list[dict] = []
    for row in cursor:
        rows.append(dict(row))
    print(f"Fetched {len(rows)} ad rows with spend > 0", file=sys.stderr)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, default=str, indent=2))
    print(f"Wrote {OUT}", file=sys.stderr)

    total_spend = sum(float(r.get("spend", 0) or 0) for r in rows)
    total_fn = 0
    for r in rows:
        for a in r.get("actions", []) or []:
            if "first_note" in (a.get("action_type") or ""):
                total_fn += int(float(a.get("value", 0) or 0))
    print(f"Total spend: ${total_spend:,.2f}  |  first_note actions: {total_fn}", file=sys.stderr)


if __name__ == "__main__":
    main()
