#!/usr/bin/env python3
"""
Query NPPES for PMHNPs + Psychiatrists, upload as Meta Custom Audience.

Matching schema: FN + LN + ST + ZIP (SHA256-hashed per Meta spec).
NPPES has no emails, so this is the best we can do for deterministic matching.
"""

import hashlib
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

NPPES_BASE = "https://npiregistry.cms.hhs.gov/api/"
NPPES_LIMIT = 200
NPPES_SKIP_CAP = 1000  # NPPES hard limit on the skip parameter

# Narrow queries to keep per-state results under the 1000-skip cap.
# Each is a prefix match against taxonomy_description; we still filter
# by exact taxonomy code below (TARGET_TAXONOMY_CODES).
TAXONOMY_QUERIES = [
    "Psychiatry",     # substring match -> psychiatrists (2084P0800X)
    "Psych/Mental",   # substring match -> PMHNPs (363LP0808X)
]

# Only keep providers whose taxonomy list includes one of these codes
TARGET_TAXONOMY_CODES = {
    "363LP0808X",  # Psychiatric/Mental Health Nurse Practitioner
    "2084P0800X",  # Psychiatry & Neurology, Psychiatry
}

US_STATES = [
    "AL","AK","AZ","AR","CA","CO","CT","DE","DC","FL","GA","HI","ID","IL","IN",
    "IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH",
    "NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT",
    "VT","VA","WA","WV","WI","WY",
]

META_API_VERSION = "v21.0"
META_AD_ACCOUNT = "act_1582817295627677"
META_GRAPH = f"https://graph.facebook.com/{META_API_VERSION}"
AUDIENCE_NAME = "NPPES PMHNPs + Psychiatrists"
UPLOAD_BATCH_SIZE = 10_000

TODAY = date.today().isoformat()
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "audiences"

# ---------------------------------------------------------------------------
# Env
# ---------------------------------------------------------------------------

def load_env(path: str = os.path.expanduser("~/.claude/.env")):
    """Parse KEY=VALUE lines from a file into os.environ."""
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
        os.environ.setdefault(key, val)


load_env()
META_TOKEN = os.environ["META_ADS_ACCESS_TOKEN"]

# ---------------------------------------------------------------------------
# NPPES pull
# ---------------------------------------------------------------------------

def log(msg: str):
    print(msg, file=sys.stderr)


def pull_nppes_state(taxonomy_desc: str, state: str) -> list[dict]:
    """Pull all individual providers matching taxonomy_desc in a given state.

    Raises RuntimeError if the API fails repeatedly — caller decides whether
    to skip the state or abort. Caps `skip` at NPPES_SKIP_CAP since NPPES
    silently misbehaves beyond that.
    """
    results = []
    skip = 0
    while True:
        params = {
            "version": "2.1",
            "taxonomy_description": taxonomy_desc,
            "enumeration_type": "NPI-1",
            "state": state,
            "limit": NPPES_LIMIT,
            "skip": skip,
        }
        data = None
        for attempt in range(6):
            try:
                resp = requests.get(NPPES_BASE, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                break
            except requests.RequestException as e:
                if attempt == 5:
                    raise RuntimeError(
                        f"NPPES failed for {state} skip={skip}: {e}"
                    )
                time.sleep(2 ** attempt)
        batch = data.get("results", [])
        if not batch:
            break
        results.extend(batch)
        if len(batch) < NPPES_LIMIT:
            break
        skip += NPPES_LIMIT
        if skip >= NPPES_SKIP_CAP:
            log(f"    WARN: {state} hit NPPES skip cap ({NPPES_SKIP_CAP}); some providers omitted")
            break
        time.sleep(0.2)
    return results


def has_target_taxonomy(provider: dict) -> bool:
    """Check if provider has at least one taxonomy code in our target set."""
    for t in provider.get("taxonomies", []):
        if t.get("code") in TARGET_TAXONOMY_CODES:
            return True
    return False


def pull_all_nppes() -> list[dict]:
    """Pull PMHNPs + psychiatrists state-by-state, filter by taxonomy code.

    Resumable: writes per-state results to a checkpoint file after each
    state so a crash doesn't lose work.
    """
    checkpoint_path = DATA_DIR / "nppes-checkpoint.json"
    state_data: dict[str, list[dict]] = {}
    if checkpoint_path.exists():
        state_data = json.loads(checkpoint_path.read_text())
        log(f"Resumed from checkpoint: {len(state_data)} (query, state) pairs already pulled")

    failures: list[str] = []
    for query in TAXONOMY_QUERIES:
        log(f"Pulling NPPES: {query!r} across {len(US_STATES)} states")
        for state in US_STATES:
            key = f"{query}::{state}"
            if key in state_data:
                continue
            try:
                raw = pull_nppes_state(query, state)
            except RuntimeError as e:
                log(f"  ERROR {state}: {e} — will retry on next run")
                failures.append(key)
                continue
            filtered = [r for r in raw if has_target_taxonomy(r)]
            state_data[key] = filtered
            log(f"  {state}: {len(raw)} raw -> {len(filtered)} target providers")
            checkpoint_path.write_text(json.dumps(state_data))
            time.sleep(0.15)
        log(f"  Subtotal after {query!r}: {sum(len(v) for k, v in state_data.items() if k.startswith(query)):,} target providers")

    if failures:
        raise RuntimeError(f"{len(failures)} state pulls failed: {failures}. Re-run to resume.")

    all_results = []
    for v in state_data.values():
        all_results.extend(v)
    return all_results


def extract_records(nppes_results: list[dict]) -> list[dict]:
    """Pull FN, LN, state, zip from NPPES result objects. Dedup by NPI."""
    seen = set()
    records = []
    for r in nppes_results:
        npi = r.get("number")
        if npi in seen:
            continue
        seen.add(npi)

        basic = r.get("basic", {})
        fn = (basic.get("first_name") or "").strip()
        ln = (basic.get("last_name") or "").strip()

        # Use primary practice address; fall back to mailing
        addrs = r.get("addresses", [])
        practice = next(
            (a for a in addrs if a.get("address_purpose") == "LOCATION"),
            addrs[0] if addrs else {},
        )
        state = (practice.get("state") or "").strip()
        zipcode = (practice.get("postal_code") or "").strip()[:5]  # 5-digit

        if not (fn and ln and state and zipcode):
            continue

        records.append({
            "npi": npi,
            "fn": fn,
            "ln": ln,
            "state": state,
            "zip": zipcode,
        })
    return records


# ---------------------------------------------------------------------------
# Meta audience upload
# ---------------------------------------------------------------------------

def sha256(val: str) -> str:
    """Lowercase, strip, SHA256 — per Meta's normalization spec."""
    return hashlib.sha256(val.lower().strip().encode("utf-8")).hexdigest()


def create_audience(session: requests.Session) -> str:
    """Create a Custom Audience, return its ID."""
    url = f"{META_GRAPH}/{META_AD_ACCOUNT}/customaudiences"
    resp = session.post(url, data={
        "name": AUDIENCE_NAME,
        "subtype": "CUSTOM",
        "description": f"NPPES PMHNPs + Psychiatrists pulled {TODAY}",
        "customer_file_source": "USER_PROVIDED_ONLY",
        "access_token": META_TOKEN,
    })
    resp.raise_for_status()
    audience_id = resp.json()["id"]
    log(f"Created audience {audience_id}")
    return audience_id


def upload_batch(session: requests.Session, audience_id: str,
                 batch: list[list[str]], batch_num: int) -> dict:
    """Upload one batch of hashed records."""
    payload = {
        "schema": ["FN", "LN", "ST", "ZIP"],
        "data": batch,
    }
    url = f"{META_GRAPH}/{audience_id}/users"
    resp = session.post(url, data={
        "payload": json.dumps(payload),
        "access_token": META_TOKEN,
    })
    resp.raise_for_status()
    result = resp.json()
    log(f"  Batch {batch_num}: uploaded {len(batch)} records — "
        f"matched ~{result.get('audience_id', '?')}")
    return result


def upload_to_meta(records: list[dict]) -> dict:
    """Create audience + upload all records in batches."""
    session = requests.Session()
    audience_id = create_audience(session)

    hashed = [
        [sha256(r["fn"]), sha256(r["ln"]), sha256(r["state"]), sha256(r["zip"])]
        for r in records
    ]

    upload_results = []
    for i in range(0, len(hashed), UPLOAD_BATCH_SIZE):
        batch = hashed[i : i + UPLOAD_BATCH_SIZE]
        batch_num = i // UPLOAD_BATCH_SIZE + 1
        result = upload_batch(session, audience_id, batch, batch_num)
        upload_results.append(result)

    return {
        "audience_id": audience_id,
        "audience_name": AUDIENCE_NAME,
        "total_records": len(records),
        "batches": len(upload_results),
        "batch_results": upload_results,
        "date": TODAY,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Pull from NPPES (state-by-state, filtered by taxonomy code)
    all_raw = pull_all_nppes()

    raw_path = DATA_DIR / f"nppes-raw-{TODAY}.json"
    raw_path.write_text(json.dumps(all_raw, indent=2))
    log(f"Saved {len(all_raw)} raw NPPES records → {raw_path}")

    # Extract and dedup
    records = extract_records(all_raw)
    log(f"Extracted {len(records)} unique records with complete FN/LN/ST/ZIP")

    if not records:
        log("No records to upload. Exiting.")
        sys.exit(1)

    # Upload to Meta
    log("Uploading to Meta Custom Audience...")
    summary = upload_to_meta(records)

    summary_path = DATA_DIR / f"nppes-upload-{TODAY}.json"
    summary_path.write_text(json.dumps(summary, indent=2))
    log(f"Upload summary → {summary_path}")
    log("Done.")


if __name__ == "__main__":
    main()
