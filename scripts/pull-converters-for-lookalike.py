#!/usr/bin/env python3
"""Pull first-note converters from Metabase, upload as Meta Custom Audience seed,
create a 1% Lookalike.

Usage:  python scripts/pull-converters-for-lookalike.py
Env:    METABASE_URL, METABASE_API_KEY, META_ADS_ACCESS_TOKEN in ~/.claude/.env
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
METABASE_DB_ID = 2
METABASE_TIMEOUT = 300
META_API_VERSION = "v21.0"
META_AD_ACCOUNT = "act_1582817295627677"
AUDIENCE_NAME = "Converters - First Note Completers"
LOOKALIKE_NAME = "Lookalike - First Note Converters 1%"
LOOKALIKE_COUNTRY = "US"
LOOKALIKE_RATIO = 0.01

TODAY = date.today().isoformat()
REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIENCE_DIR = REPO_ROOT / "data" / "audiences"

# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------

def _load_env() -> None:
    """Parse ~/.claude/.env into os.environ (skip comments, strip quotes)."""
    env_file = Path.home() / ".claude" / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)

# ---------------------------------------------------------------------------
# Metabase
# ---------------------------------------------------------------------------

def mb_query(sql: str) -> list[dict[str, Any]]:
    """Run a native SQL query against Metabase and return rows as dicts."""
    base = os.environ["METABASE_URL"].rstrip("/")
    key = os.environ["METABASE_API_KEY"]
    resp = requests.post(
        f"{base}/api/dataset",
        json={"type": "native", "native": {"query": sql}, "database": METABASE_DB_ID},
        headers={"Content-Type": "application/json", "x-api-key": key},
        timeout=METABASE_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Metabase HTTP {resp.status_code}: {resp.text[:500]}")
    payload = resp.json()
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    cols = [c.get("name", f"col_{i}") for i, c in enumerate(data.get("cols", []))]
    rows = data.get("rows", [])
    return [dict(zip(cols, r)) for r in rows]


def pull_converters() -> list[dict[str, Any]]:
    """Try multiple SQL variants to pull users with >= 1 completed note."""
    queries = [
        (
            "provider_segments.notes_created_count",
            "SELECT email, notes_created_count FROM provider_segments "
            "WHERE notes_created_count >= 1 AND email IS NOT NULL AND email != '' "
            "ORDER BY notes_created_count DESC",
            "notes_created_count",
        ),
        (
            "users.user_notes_created_count",
            "SELECT u.user_notes_created_count, ps.email "
            "FROM users u JOIN provider_segments ps ON u.user_notes_created_count >= 1 "
            "WHERE ps.email IS NOT NULL AND ps.email != '' "
            "ORDER BY u.user_notes_created_count DESC",
            "user_notes_created_count",
        ),
    ]

    for label, sql, count_col in queries:
        log(f"Trying query: {label} ...")
        try:
            rows = mb_query(sql)
            if rows:
                # Normalise column name to 'note_count'
                for r in rows:
                    if count_col != "note_count" and count_col in r:
                        r["note_count"] = r.pop(count_col)
                log(f"  -> {len(rows)} converters found via {label}")
                return rows
            log(f"  -> 0 rows returned")
        except RuntimeError as e:
            log(f"  -> failed: {e}")

    # All queries failed — run schema discovery
    log("All converter queries failed. Running schema discovery ...")
    discovery_sql = (
        "SELECT table_name, column_name "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' "
        "  AND (column_name LIKE '%email%' OR column_name LIKE '%note%') "
        "ORDER BY table_name, column_name"
    )
    try:
        schema = mb_query(discovery_sql)
        log("Schema columns matching 'email' or 'note':")
        for r in schema:
            log(f"  {r.get('table_name')}.{r.get('column_name')}")
    except RuntimeError as e:
        log(f"Schema discovery also failed: {e}")

    log("Cannot pull converters. Fix the query and re-run.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Meta Custom Audience
# ---------------------------------------------------------------------------

def sha256_email(email: str) -> str:
    return hashlib.sha256(email.lower().strip().encode()).hexdigest()


def create_custom_audience(token: str) -> str:
    """Create (or find existing) Custom Audience. Returns audience ID."""
    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_AD_ACCOUNT}/customaudiences"

    # Check if audience already exists
    log("Checking for existing audience ...")
    list_resp = requests.get(
        url,
        params={"access_token": token, "fields": "id,name"},
        timeout=60,
    )
    if list_resp.ok:
        for aud in list_resp.json().get("data", []):
            if aud.get("name") == AUDIENCE_NAME:
                log(f"  -> Found existing audience {aud['id']}")
                return aud["id"]

    # Create new
    log(f"Creating Custom Audience: {AUDIENCE_NAME}")
    resp = requests.post(
        url,
        json={
            "name": AUDIENCE_NAME,
            "subtype": "CUSTOM",
            "description": f"Users who completed >= 1 note. Pulled {TODAY}.",
            "customer_file_source": "USER_PROVIDED_ONLY",
            "access_token": token,
        },
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Create audience failed HTTP {resp.status_code}: {resp.text[:500]}")
    aud_id = resp.json()["id"]
    log(f"  -> Created audience {aud_id}")
    return aud_id


def upload_audience(token: str, audience_id: str, hashed_emails: list[str]) -> dict:
    """Upload hashed emails to a Custom Audience in batches of 10k."""
    url = f"https://graph.facebook.com/{META_API_VERSION}/{audience_id}/users"
    batch_size = 10_000
    total_uploaded = 0
    results = []

    for i in range(0, len(hashed_emails), batch_size):
        batch = hashed_emails[i : i + batch_size]
        log(f"Uploading batch {i // batch_size + 1} ({len(batch)} hashes) ...")
        payload = {
            "payload": json.dumps({
                "schema": ["EMAIL"],
                "data": [[h] for h in batch],
            }),
            "access_token": token,
        }
        resp = requests.post(url, data=payload, timeout=120)
        if resp.status_code >= 400:
            raise RuntimeError(f"Upload failed HTTP {resp.status_code}: {resp.text[:500]}")
        body = resp.json()
        results.append(body)
        total_uploaded += body.get("audience_id") and len(batch) or 0
        log(f"  -> {body}")

    return {"batches": len(results), "total_hashes": len(hashed_emails), "responses": results}


def create_lookalike(token: str, source_audience_id: str) -> dict:
    """Create a 1% Lookalike from the source audience."""
    url = f"https://graph.facebook.com/{META_API_VERSION}/{META_AD_ACCOUNT}/customaudiences"

    # Check if it already exists
    list_resp = requests.get(
        url,
        params={"access_token": token, "fields": "id,name"},
        timeout=60,
    )
    if list_resp.ok:
        for aud in list_resp.json().get("data", []):
            if aud.get("name") == LOOKALIKE_NAME:
                log(f"Lookalike already exists: {aud['id']}")
                return {"id": aud["id"], "name": LOOKALIKE_NAME, "status": "already_exists"}

    log(f"Creating Lookalike: {LOOKALIKE_NAME}")
    resp = requests.post(
        url,
        json={
            "name": LOOKALIKE_NAME,
            "subtype": "LOOKALIKE",
            "origin_audience_id": source_audience_id,
            "lookalike_spec": json.dumps({
                "type": "similarity",
                "country": LOOKALIKE_COUNTRY,
                "ratio": LOOKALIKE_RATIO,
            }),
            "access_token": token,
        },
        timeout=60,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Lookalike creation failed HTTP {resp.status_code}: {resp.text[:500]}")
    body = resp.json()
    log(f"  -> Lookalike created: {body.get('id')}")
    return {"id": body["id"], "name": LOOKALIKE_NAME, "status": "created"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    _load_env()

    # Validate required env vars (fail loud)
    _ = os.environ["METABASE_URL"]
    _ = os.environ["METABASE_API_KEY"]
    meta_token = os.environ["META_ADS_ACCESS_TOKEN"]

    # 1. Pull converters from Metabase
    log("=== Pulling converters from Metabase ===")
    converters = pull_converters()
    emails = [r["email"] for r in converters if r.get("email")]
    log(f"Total converters with email: {len(emails)}")

    # 2. Save raw converter list (unhashed, internal reference)
    AUDIENCE_DIR.mkdir(parents=True, exist_ok=True)
    converter_path = AUDIENCE_DIR / f"converters-{TODAY}.json"
    converter_path.write_text(json.dumps(converters, indent=2, default=str))
    log(f"Saved converter list -> {converter_path}")

    # 3. Hash emails
    hashed = [sha256_email(e) for e in emails]
    log(f"Hashed {len(hashed)} emails")

    # 4. Create/find Custom Audience and upload
    log("\n=== Meta Custom Audience ===")
    audience_id = create_custom_audience(meta_token)
    upload_result = upload_audience(meta_token, audience_id, hashed)

    # 5. Create Lookalike
    log("\n=== Meta Lookalike Audience ===")
    lookalike_result = create_lookalike(meta_token, audience_id)

    # 6. Save upload summary
    summary = {
        "date": TODAY,
        "converter_count": len(emails),
        "audience_id": audience_id,
        "audience_name": AUDIENCE_NAME,
        "upload": upload_result,
        "lookalike": lookalike_result,
    }
    summary_path = AUDIENCE_DIR / f"converters-upload-{TODAY}.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    log(f"\nSaved upload summary -> {summary_path}")
    log("Done.")


if __name__ == "__main__":
    main()
