#!/usr/bin/env python3
"""
Parse Chris's BH clinic CSVs, deduplicate, hash PII per Meta spec,
upload as a Custom Audience, then create a 1% Lookalike.
"""

import csv
import hashlib
import json
import os
import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional, Set

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_DIR = SCRIPT_DIR.parent
DATA_DIR = ENGINE_DIR / "data"

FILE_A = DATA_DIR / "Combined_Admin_Provider_List (2).csv"
FILE_B = DATA_DIR / "NPPES Top 4 Clinics Email (1).csv"
OUTPUT_DIR = DATA_DIR / "audiences"

AD_ACCOUNT = "act_1582817295627677"
API_VERSION = "v21.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

BATCH_SIZE = 10_000


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


# ---------------------------------------------------------------------------
# Env loading
# ---------------------------------------------------------------------------
def load_env(path: Path) -> None:
    """Parse KEY=VALUE lines from a .env file into os.environ."""
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            os.environ.setdefault(key, value)


load_env(Path.home() / ".claude" / ".env")
ACCESS_TOKEN = os.environ["META_ADS_ACCESS_TOKEN"]


# ---------------------------------------------------------------------------
# Hashing helpers (Meta spec: lowercase, strip, SHA256 hex)
# ---------------------------------------------------------------------------
def hash_value(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()


def norm_email(raw: str) -> Optional[str]:
    v = raw.strip().lower()
    return hash_value(v) if v else None


def norm_name(raw: str) -> Optional[str]:
    v = raw.strip().lower()
    # Remove non-alpha suffixes like periods, commas
    v = re.sub(r"[^a-z\s-]", "", v).strip()
    return hash_value(v) if v else None


def norm_phone(raw: str) -> Optional[str]:
    digits = re.sub(r"\D", "", raw.strip())
    if not digits:
        return None
    # If 10 digits and no country code, assume US
    if len(digits) == 10:
        digits = "1" + digits
    return hash_value(digits)


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------
def parse_file_a(path: Path) -> list[dict]:
    """Combined_Admin_Provider_List — has Company Name and Role columns."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "email": r.get("Work Email", "").strip(),
                "phone": r.get("Mobile Phone", "").strip(),
                "fn": r.get("First Name", "").strip(),
                "ln": r.get("Last Name", "").strip(),
                "source": "combined_admin_provider",
            })
    return rows


def parse_file_b(path: Path) -> list[dict]:
    """NPPES Top 4 Clinics — has ICP column instead of Role."""
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "email": r.get("Work Email", "").strip(),
                "phone": r.get("Mobile Phone", "").strip(),
                "fn": r.get("First Name", "").strip(),
                "ln": r.get("Last Name", "").strip(),
                "source": "nppes_top4",
            })
    return rows


def deduplicate(rows: list[dict]) -> list[dict]:
    """
    Deduplicate by lowercase email. Rows without email are kept
    if they have a phone number (phone-only match uses phone as dedup key).
    """
    seen_emails: Set[str] = set()
    seen_phones: Set[str] = set()
    unique: list[dict] = []

    for r in rows:
        email_lower = r["email"].lower()
        phone_digits = re.sub(r"\D", "", r["phone"])

        if email_lower:
            if email_lower in seen_emails:
                continue
            seen_emails.add(email_lower)
            unique.append(r)
        elif phone_digits:
            if phone_digits in seen_phones:
                continue
            seen_phones.add(phone_digits)
            unique.append(r)
        # No email and no phone → skip entirely

    return unique


def build_schema_and_data(rows: list[dict]) -> tuple[list[str], list[list[str]]]:
    """
    Build the schema list and hashed data rows for Meta multi-key upload.
    Schema: EMAIL, PHONE, FN, LN
    Each data row is a list of hashed values (empty string if missing).
    """
    schema = ["EMAIL", "PHONE", "FN", "LN"]
    data = []
    for r in rows:
        data.append([
            norm_email(r["email"]) or "",
            norm_phone(r["phone"]) or "",
            norm_name(r["fn"]) or "",
            norm_name(r["ln"]) or "",
        ])
    return schema, data


# ---------------------------------------------------------------------------
# Meta API calls
# ---------------------------------------------------------------------------
def create_custom_audience(name: str) -> str:
    """Create an empty Custom Audience, return its ID."""
    url = f"{BASE_URL}/{AD_ACCOUNT}/customaudiences"
    resp = requests.post(url, params={
        "access_token": ACCESS_TOKEN,
        "name": name,
        "subtype": "CUSTOM",
        "description": "BH clinic contacts from Chris's sales prospect lists",
        "customer_file_source": "USER_PROVIDED_ONLY",
    })
    resp.raise_for_status()
    audience_id = resp.json()["id"]
    log(f"Created Custom Audience: {audience_id}")
    return audience_id


def upload_users(audience_id: str, schema: list[str], data: list[list[str]]) -> dict:
    """Upload hashed user data in batches."""
    url = f"{BASE_URL}/{audience_id}/users"
    total = len(data)
    num_received = 0
    session_id = None

    for i in range(0, total, BATCH_SIZE):
        batch = data[i : i + BATCH_SIZE]
        batch_num = (i // BATCH_SIZE) + 1
        log(f"Uploading batch {batch_num} ({len(batch)} rows)...")

        payload = {
            "schema": schema,
            "data": batch,
        }

        resp = requests.post(url, data={
            "payload": json.dumps(payload),
            "access_token": ACCESS_TOKEN,
        })
        resp.raise_for_status()
        result = resp.json()
        num_received += result.get("num_received", len(batch))
        log(f"  Batch {batch_num}: received={result.get('num_received')}, invalid={result.get('num_invalid_entries', 0)}")

    return {"num_received": num_received, "session_id": session_id}


def create_lookalike(source_audience_id: str, name: str) -> str:
    """Create a 1% Lookalike Audience from the source."""
    url = f"{BASE_URL}/{AD_ACCOUNT}/customaudiences"
    resp = requests.post(url, params={
        "access_token": ACCESS_TOKEN,
        "name": name,
        "subtype": "LOOKALIKE",
        "origin_audience_id": source_audience_id,
        "lookalike_spec": json.dumps({
            "type": "similarity",
            "country": "US",
            "ratio": 0.01,
        }),
    })
    resp.raise_for_status()
    lookalike_id = resp.json()["id"]
    log(f"Created Lookalike Audience: {lookalike_id}")
    return lookalike_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    log("Parsing CSVs...")
    rows_a = parse_file_a(FILE_A)
    rows_b = parse_file_b(FILE_B)
    log(f"  File A: {len(rows_a)} rows")
    log(f"  File B: {len(rows_b)} rows")

    combined = rows_a + rows_b
    unique = deduplicate(combined)
    log(f"  After dedup: {len(unique)} unique contacts")

    has_email = sum(1 for r in unique if r["email"])
    has_phone = sum(1 for r in unique if r["phone"])
    phone_only = sum(1 for r in unique if not r["email"] and r["phone"])
    log(f"  With email: {has_email}, with phone: {has_phone}, phone-only: {phone_only}")

    schema, data = build_schema_and_data(unique)

    # Create audience and upload
    audience_name = "Sales Prospect List - BH Clinics"
    log(f"\nCreating Custom Audience: {audience_name}")
    audience_id = create_custom_audience(audience_name)

    log("Uploading hashed user data...")
    upload_result = upload_users(audience_id, schema, data)

    # Create lookalike
    lookalike_name = "Lookalike - BH Clinic Prospects 1%"
    log(f"\nCreating Lookalike: {lookalike_name}")
    lookalike_id = create_lookalike(audience_id, lookalike_name)

    # Save summary
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    summary = {
        "date": today,
        "sources": [str(FILE_A), str(FILE_B)],
        "rows_file_a": len(rows_a),
        "rows_file_b": len(rows_b),
        "total_before_dedup": len(combined),
        "total_after_dedup": len(unique),
        "with_email": has_email,
        "with_phone": has_phone,
        "phone_only": phone_only,
        "schema": schema,
        "custom_audience_id": audience_id,
        "custom_audience_name": audience_name,
        "upload_num_received": upload_result["num_received"],
        "lookalike_audience_id": lookalike_id,
        "lookalike_audience_name": lookalike_name,
    }

    out_path = OUTPUT_DIR / f"chris-lists-upload-{today}.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    log(f"\nSummary saved to {out_path}")
    log("Done.")


if __name__ == "__main__":
    main()
