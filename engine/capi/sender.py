"""
Meta Conversions API (CAPI) sender — server-side event delivery with dollar values.

Sends conversion events to Meta's server-side endpoint so campaign optimization
can weight on value (dollar-weighted CpFN) rather than binary event counts.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PIXEL_ID = "1625233994894344"  # WebApp Actions (canonical)
GRAPH_API_VERSION = "v21.0"
ENDPOINT = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{PIXEL_ID}/events"

EVENT_VALUES = {
    "FirstNote": 100.0,
    "CalendarScheduled": 15.0,
    "SignUpConfirm": 5.0,
}

# PII fields that must be SHA256-hashed before transmission.
_HASH_FIELDS = {"em", "ph", "fn", "ln"}

# Map from friendly user_data keys to Meta's abbreviated parameter names.
_USER_DATA_KEY_MAP = {
    "email": "em",
    "phone": "ph",
    "fn": "fn",
    "ln": "ln",
    "fbp": "fbp",
    "fbc": "fbc",
    "client_ip_address": "client_ip_address",
    "client_user_agent": "client_user_agent",
}

# ---------------------------------------------------------------------------
# Env bootstrap
# ---------------------------------------------------------------------------


def _load_global_env():
    """Parse ~/.claude/.env (KEY=VALUE lines, skip comments/blanks) into os.environ."""
    env_path = Path.home() / ".claude" / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


_load_global_env()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(value: str) -> str:
    """Lowercase, strip, then SHA256-hex a PII string per Meta's spec."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()


def _normalize_user_data(raw: dict) -> dict:
    """
    Convert friendly user_data dict into Meta's wire format.

    - Renames keys (email -> em, phone -> ph, etc.)
    - SHA256-hashes PII fields (em, ph, fn, ln)
    - Wraps hashed values in a list (Meta expects arrays)
    - Passes fbp, fbc, client_ip_address, client_user_agent as-is
    """
    out = {}
    for src_key, value in raw.items():
        meta_key = _USER_DATA_KEY_MAP.get(src_key)
        if meta_key is None:
            continue
        if value is None:
            continue
        if meta_key in _HASH_FIELDS:
            out[meta_key] = [_sha256(str(value))]
        else:
            out[meta_key] = value
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def send_event(
    event_name: str,
    value: float,
    currency: str = "USD",
    user_data: Optional[Dict] = None,
    event_time: Optional[int] = None,
    event_source_url: Optional[str] = None,
    test_event_code: Optional[str] = None,
) -> dict:
    """
    Send a single server-side conversion event to Meta CAPI.

    Returns the parsed JSON response from Meta's API.
    Raises on missing token or HTTP error.
    """
    access_token = os.environ["META_ADS_ACCESS_TOKEN"]

    event_time = event_time or int(time.time())

    event_payload = {
        "event_name": event_name,
        "event_time": event_time,
        "action_source": "website",
        "custom_data": {
            "value": value,
            "currency": currency,
        },
    }

    if event_source_url:
        event_payload["event_source_url"] = event_source_url

    if user_data:
        event_payload["user_data"] = _normalize_user_data(user_data)

    body = {"data": [event_payload]}

    if test_event_code:
        body["test_event_code"] = test_event_code

    resp = requests.post(
        ENDPOINT,
        params={"access_token": access_token},
        json=body,
        timeout=30,
    )

    result = resp.json()

    print(
        f"[CAPI] {event_name} val={value} {currency} "
        f"-> {resp.status_code} events_received={result.get('events_received', '?')}",
        file=sys.stderr,
    )

    resp.raise_for_status()
    return result


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Sending test event to Meta CAPI...", file=sys.stderr)
    response = send_event(
        event_name="FirstNote",
        value=EVENT_VALUES["FirstNote"],
        user_data={
            "email": "test@example.com",
            "fn": "Test",
            "ln": "User",
        },
        event_source_url="https://www.jotpsych.com/",
        test_event_code="TEST_CAPI_SENDER",
    )
    print(json.dumps(response, indent=2))
