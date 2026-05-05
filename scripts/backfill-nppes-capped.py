#!/usr/bin/env python3
"""Backfill NPPES providers in states that hit the 1000-skip cap.

For each (query, state) pair the original pull exceeded, slice by 2-letter
last-name prefix ("Aa*", "Ab*", ..., "Zz*") to get below the cap. NPPES
requires minimum 2 chars + trailing "*" for prefix matching.

Appends new records (NPI not in existing checkpoint) to the Meta Custom
Audience built on 2026-04-21 (id from nppes-upload-YYYY-MM-DD.json).
"""
from __future__ import annotations

import hashlib
import json
import os
import string
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
NPPES_BASE = "https://npiregistry.cms.hhs.gov/api/"
NPPES_LIMIT = 200
NPPES_SKIP_CAP = 1000

TARGET_TAXONOMY_CODES = {"363LP0808X", "2084P0800X"}

META_API_VERSION = "v21.0"
META_AD_ACCOUNT = "act_1582817295627677"
META_GRAPH = f"https://graph.facebook.com/{META_API_VERSION}"
UPLOAD_BATCH_SIZE = 10_000

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "audiences"
TODAY = date.today().isoformat()


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Env
# ---------------------------------------------------------------------------
def load_env() -> None:
    env_path = Path.home() / ".claude" / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()
META_TOKEN = os.environ["META_ADS_ACCESS_TOKEN"]


# ---------------------------------------------------------------------------
# NPPES sliced pull
# ---------------------------------------------------------------------------
def fetch_slice(query: str, state: str, prefix: str) -> list[dict]:
    """Pull all pages for a (query, state, last_name prefix) tuple."""
    results = []
    skip = 0
    for attempt in range(4):
        try:
            while True:
                r = requests.get(NPPES_BASE, params={
                    "version": "2.1",
                    "taxonomy_description": query,
                    "enumeration_type": "NPI-1",
                    "state": state,
                    "last_name": f"{prefix}*",
                    "limit": NPPES_LIMIT,
                    "skip": skip,
                }, timeout=20)
                r.raise_for_status()
                batch = r.json().get("results", [])
                if not batch:
                    return results
                results.extend(batch)
                if len(batch) < NPPES_LIMIT:
                    return results
                skip += NPPES_LIMIT
                if skip >= NPPES_SKIP_CAP:
                    log(f"    sub-cap hit: {query}/{state}/{prefix}*")
                    return results
        except requests.RequestException as e:
            if attempt == 3:
                log(f"    ERROR {query}/{state}/{prefix}: {e}")
                return results
            time.sleep(2 ** attempt)
    return results


def has_target_taxonomy(provider: dict) -> bool:
    return any(t.get("code") in TARGET_TAXONOMY_CODES
               for t in provider.get("taxonomies", []))


def extract_record(r: dict) -> dict | None:
    basic = r.get("basic", {})
    fn = (basic.get("first_name") or "").strip()
    ln = (basic.get("last_name") or "").strip()
    addrs = r.get("addresses", [])
    practice = next(
        (a for a in addrs if a.get("address_purpose") == "LOCATION"),
        addrs[0] if addrs else {},
    )
    state = (practice.get("state") or "").strip()
    zipcode = (practice.get("postal_code") or "").strip()[:5]
    if not (fn and ln and state and zipcode):
        return None
    return {"npi": r.get("number"), "fn": fn, "ln": ln, "state": state, "zip": zipcode}


# ---------------------------------------------------------------------------
# Existing NPI set (dedup)
# ---------------------------------------------------------------------------
def load_existing_npis() -> set[str]:
    cp = DATA_DIR / "nppes-checkpoint.json"
    if not cp.exists():
        log("ERROR: no checkpoint found at data/audiences/nppes-checkpoint.json")
        sys.exit(1)
    data = json.loads(cp.read_text())
    npis = set()
    for records in data.values():
        for r in records:
            if r.get("number"):
                npis.add(r["number"])
    log(f"Loaded {len(npis):,} existing NPIs from checkpoint")
    return npis


# ---------------------------------------------------------------------------
# Meta upload (append to existing audience)
# ---------------------------------------------------------------------------
def sha256(val: str) -> str:
    return hashlib.sha256(val.lower().strip().encode("utf-8")).hexdigest()


def upload_to_meta(audience_id: str, records: list[dict]) -> list[dict]:
    if not records:
        log("No new records to upload.")
        return []
    session = requests.Session()
    url = f"{META_GRAPH}/{audience_id}/users"
    hashed = [
        [sha256(r["fn"]), sha256(r["ln"]), sha256(r["state"]), sha256(r["zip"])]
        for r in records
    ]
    results = []
    for i in range(0, len(hashed), UPLOAD_BATCH_SIZE):
        batch = hashed[i : i + UPLOAD_BATCH_SIZE]
        payload = {"schema": ["FN", "LN", "ST", "ZIP"], "data": batch}
        r = session.post(url, data={
            "payload": json.dumps(payload),
            "access_token": META_TOKEN,
        })
        r.raise_for_status()
        results.append(r.json())
        log(f"  uploaded batch {i // UPLOAD_BATCH_SIZE + 1}: {len(batch):,} records")
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
CAPPED_PAIRS = [
    ("Psychiatry", s) for s in
    "AZ CA CO CT FL GA IL IN KY LA MD MA MI MN MO NJ NY NC OH OR PA SC TN TX VA WA WI".split()
] + [
    ("Psych/Mental", s) for s in
    "AZ CA CO CT FL GA IL IN KY LA MD MA MI MN MO NJ NY NC OH OR PA TN TX VA WA".split()
]

PREFIXES = [a + b for a in string.ascii_lowercase for b in string.ascii_lowercase]


def main() -> None:
    existing_npis = load_existing_npis()

    # Load audience id from latest upload summary
    summaries = sorted(DATA_DIR.glob("nppes-upload-*.json"), reverse=True)
    if not summaries:
        log("ERROR: no nppes-upload-*.json found.")
        sys.exit(1)
    summary = json.loads(summaries[0].read_text())
    audience_id = summary["audience_id"]
    log(f"Target audience: {audience_id} ({summary['audience_name']})")

    total_tasks = len(CAPPED_PAIRS) * len(PREFIXES)
    log(f"Fanning out {total_tasks:,} NPPES queries ({len(CAPPED_PAIRS)} pairs × {len(PREFIXES)} prefixes)")

    new_records: dict[str, dict] = {}
    completed = 0

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {}
        for query, state in CAPPED_PAIRS:
            for prefix in PREFIXES:
                fut = ex.submit(fetch_slice, query, state, prefix)
                futures[fut] = (query, state, prefix)

        for fut in as_completed(futures):
            completed += 1
            query, state, prefix = futures[fut]
            try:
                batch = fut.result()
            except Exception as e:
                log(f"  task failed {query}/{state}/{prefix}: {e}")
                continue
            for raw in batch:
                if not has_target_taxonomy(raw):
                    continue
                npi = raw.get("number")
                if not npi or npi in existing_npis or npi in new_records:
                    continue
                rec = extract_record(raw)
                if rec:
                    new_records[npi] = rec
            if completed % 500 == 0:
                log(f"  {completed:,}/{total_tasks:,} tasks done; new unique providers so far: {len(new_records):,}")

    log(f"Backfill complete: {len(new_records):,} new unique providers found")

    backfill_path = DATA_DIR / f"nppes-backfill-{TODAY}.json"
    backfill_path.write_text(json.dumps(list(new_records.values()), indent=2))
    log(f"Saved backfill records -> {backfill_path}")

    if new_records:
        log(f"Appending {len(new_records):,} records to audience {audience_id}")
        upload_results = upload_to_meta(audience_id, list(new_records.values()))
        result_path = DATA_DIR / f"nppes-backfill-upload-{TODAY}.json"
        result_path.write_text(json.dumps({
            "date": TODAY,
            "audience_id": audience_id,
            "new_records": len(new_records),
            "batches": len(upload_results),
            "batch_results": upload_results,
        }, indent=2))
        log(f"Upload summary -> {result_path}")

    log("Done.")


if __name__ == "__main__":
    main()
