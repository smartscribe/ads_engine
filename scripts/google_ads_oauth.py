"""
One-shot OAuth refresh-token generator for Google Ads API.

Run after the Desktop OAuth client has been created in GCP Console and the
credentials JSON has been saved to ~/.claude/integrations/google_ads_oauth.json.

Usage:
    python3 scripts/google_ads_oauth.py

What happens:
    1. Browser opens to Google's OAuth consent screen
    2. Sign in as nate@jotpsych.com (account owner of CID 944-822-1568)
    3. Click "Allow" on the adwords scope prompt
    4. Refresh token + client_id + client_secret printed to stdout
    5. Paste the printed lines into ~/.claude/.env

Refresh tokens do not expire unless revoked or unused for 6 months.
Single-use generation; this script only needs to run once per OAuth client.
"""

from __future__ import annotations

import sys
from pathlib import Path

CREDENTIALS_PATH = Path.home() / ".claude" / "integrations" / "google_ads_oauth.json"
SCOPES = ["https://www.googleapis.com/auth/adwords"]


def main() -> int:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("ERROR: google-auth-oauthlib not installed.")
        print("Fix: pip install google-auth-oauthlib")
        return 1

    if not CREDENTIALS_PATH.exists():
        print(f"ERROR: OAuth credentials file not found at {CREDENTIALS_PATH}")
        print()
        print("To create:")
        print("  1. Visit https://console.cloud.google.com/apis/credentials")
        print("  2. Confirm the correct project is selected (top bar)")
        print("  3. Click '+ CREATE CREDENTIALS' -> 'OAuth client ID'")
        print("  4. Application type: 'Desktop app'")
        print("  5. Name: 'JotPsych Ads Engine'")
        print("  6. After creation, click the download icon (JSON)")
        print(f"  7. Save the file to: {CREDENTIALS_PATH}")
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), scopes=SCOPES)
    creds = flow.run_local_server(
        port=0,
        prompt="consent",
        access_type="offline",
        open_browser=True,
    )

    if not creds.refresh_token:
        print("ERROR: no refresh token returned. Re-run and ensure consent prompt appears.")
        print("(prompt='consent' + access_type='offline' should force a refresh token.)")
        return 1

    print()
    print("=" * 70)
    print("OAuth flow complete. Paste these into ~/.claude/.env:")
    print("=" * 70)
    print(f"GOOGLE_ADS_CLIENT_ID={creds.client_id}")
    print(f"GOOGLE_ADS_CLIENT_SECRET={creds.client_secret}")
    print(f"GOOGLE_ADS_REFRESH_TOKEN={creds.refresh_token}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
