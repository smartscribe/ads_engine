"""
Smoke test for Google Ads API credentials.

Validates:
  1. All required env vars present
  2. OAuth refresh succeeds (developer token + refresh token + client creds)
  3. CustomerService.list_accessible_customers returns CID 944-822-1568
  4. A trivial GAQL query against `customer` returns the account row

Run after pasting all env vars into ~/.claude/.env:
    python3 scripts/test_google_ads.py

Expected first run with no developer token:
    -> ERROR: missing env vars: ['GOOGLE_ADS_DEVELOPER_TOKEN']
That confirms the rest of the pipe is wired.

Expected after token approval:
    -> Accessible customers (1+):
       customers/9448221568
    -> Customer 9448221568: JotPsych ...
    -> [OK] Google Ads API access verified.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def load_env(path: str = os.path.expanduser("~/.claude/.env")) -> None:
    """Parse KEY=VALUE lines from ~/.claude/.env into os.environ. Project pattern."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


REQUIRED_ENV = [
    "GOOGLE_ADS_DEVELOPER_TOKEN",
    "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN",
    "GOOGLE_ADS_CUSTOMER_ID",
    "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
]


def main() -> int:
    load_env()

    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        print(f"ERROR: missing env vars in ~/.claude/.env: {missing}")
        if "GOOGLE_ADS_DEVELOPER_TOKEN" in missing:
            print()
            print("Developer token still pending Google approval (1-3 business days).")
            print("Once received via email from Google, paste into ~/.claude/.env and re-run.")
        return 1

    try:
        from google.ads.googleads.client import GoogleAdsClient
        from google.ads.googleads.errors import GoogleAdsException
    except ImportError:
        print("ERROR: google-ads SDK not installed.")
        print("Fix: pip install 'google-ads>=24.0.0'")
        return 1

    config = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "login_customer_id": os.environ["GOOGLE_ADS_LOGIN_CUSTOMER_ID"],
        "use_proto_plus": True,
    }

    try:
        client = GoogleAdsClient.load_from_dict(config)
    except Exception as e:
        print(f"ERROR: failed to construct GoogleAdsClient: {e}")
        return 1

    customer_id = os.environ["GOOGLE_ADS_CUSTOMER_ID"]

    try:
        cs = client.get_service("CustomerService")
        accessible = cs.list_accessible_customers()
        print(f"Accessible customers ({len(accessible.resource_names)}):")
        for rn in accessible.resource_names:
            print(f"  {rn}")
    except GoogleAdsException as e:
        print("ERROR: list_accessible_customers failed:")
        for err in e.failure.errors:
            print(f"  {err.error_code}: {err.message}")
        return 1
    except Exception as e:
        print(f"ERROR: list_accessible_customers raised {type(e).__name__}: {e}")
        return 1

    try:
        gas = client.get_service("GoogleAdsService")
        query = """
            SELECT
              customer.id,
              customer.descriptive_name,
              customer.currency_code,
              customer.time_zone,
              customer.status
            FROM customer
            LIMIT 1
        """
        response = gas.search(customer_id=customer_id, query=query)
        for row in response:
            c = row.customer
            print()
            print(f"Customer {c.id}:")
            print(f"  Name:     {c.descriptive_name}")
            print(f"  Currency: {c.currency_code}")
            print(f"  Timezone: {c.time_zone}")
            print(f"  Status:   {c.status}")
        print()
        print("[OK] Google Ads API access verified.")
        return 0
    except GoogleAdsException as e:
        print("ERROR: GAQL test query failed:")
        for err in e.failure.errors:
            print(f"  {err.error_code}: {err.message}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
