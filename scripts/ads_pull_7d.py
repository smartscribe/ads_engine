"""
Pull ad-level Meta insights for the last 7 days.
KPI: Canonical bundled Purchase CC (1604667127308749) — FirstNote $150 + SignUpConfirm $25 + CalendarScheduled $5.
Decomposition via archived CalendarScheduled probe (26939511482340303).
Saves raw JSON to data/ads-reports/raw-7d-<today>.json.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount

TODAY = date.today()
SINCE = (TODAY - timedelta(days=7)).isoformat()
UNTIL = (TODAY - timedelta(days=1)).isoformat()

# Canonical IDs from ATTRIBUTION.md
CANONICAL_PURCHASE_CC = "1604667127308749"
CAL_PROBE_CC = "26939511482340303"

OUT = Path("data/ads-reports") / f"raw-7d-{TODAY.isoformat()}.json"


def parse_action(lst: list, action_type: str) -> float:
    """Return the value for a specific action_type from a Meta actions/conversions list."""
    if not lst:
        return 0.0
    matches = [float(a.get("value", 0) or 0) for a in lst if a.get("action_type") == action_type]
    return max(matches) if matches else 0.0


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
        "actions", "action_values", "cost_per_action_type",
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

    # Summary
    total_spend = sum(float(r.get("spend", 0) or 0) for r in rows)
    total_purchases = 0
    total_cal = 0
    total_purchase_value = 0.0

    for r in rows:
        actions = r.get("actions") or []
        action_values = r.get("action_values") or []

        # Total purchase count (all sub-events collapsed)
        p = parse_action(actions, "offsite_conversion.fb_pixel_purchase")
        if not p:
            # Also check under custom CC ID in case it's returned differently
            p = parse_action(actions, f"offsite_conversion.custom.{CANONICAL_PURCHASE_CC}")
        total_purchases += int(p)

        # CalendarScheduled probe count (for decomposition)
        z = parse_action(actions, f"offsite_conversion.custom.{CAL_PROBE_CC}")
        total_cal += int(z)

        # Total canonical value
        v = parse_action(action_values, f"offsite_conversion.custom.{CANONICAL_PURCHASE_CC}")
        if not v:
            v = parse_action(action_values, "offsite_conversion.fb_pixel_purchase")
        total_purchase_value += v

    print(
        f"Total spend: ${total_spend:,.2f}  |  "
        f"Purchases (bundled): {total_purchases}  |  "
        f"CalendarScheduled: {total_cal}  |  "
        f"Purchase value: ${total_purchase_value:,.0f}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
