#!/usr/bin/env python3
"""
Attach Custom Audiences to all active Farm+Scale ad sets.

- Inclusion: NPPES PMHNPs + Psychiatrists, Sales Prospect List, Lookalikes
- Exclusion: Stripe Customers, Converters (don't target existing users)

Reads audience IDs from the latest upload summaries in data/audiences/.
Pulls all ad sets from Farm+Scale campaigns via Meta API and PATCHes their targeting.

Usage:  python scripts/attach-audiences-to-adsets.py [--dry-run]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
META_API_VERSION = "v21.0"
META_AD_ACCOUNT = "act_1582817295627677"
BASE_URL = f"https://graph.facebook.com/{META_API_VERSION}"

SCOPE_PREFIXES = ("Farm", "Scale")

AUDIENCES_DIR = Path(__file__).resolve().parents[1] / "data" / "audiences"


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


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
TOKEN = os.environ["META_ADS_ACCESS_TOKEN"]


# ---------------------------------------------------------------------------
# Load audience IDs from upload summaries
# ---------------------------------------------------------------------------
def load_latest_summary(prefix: str) -> dict:
    """Find the most recent summary JSON matching prefix in audiences dir."""
    candidates = sorted(AUDIENCES_DIR.glob(f"{prefix}*.json"), reverse=True)
    if not candidates:
        return {}
    return json.loads(candidates[0].read_text())


def collect_audience_ids() -> tuple[list[str], list[str]]:
    """Return (inclusion_ids, exclusion_ids) from all upload summaries."""
    inclusion = []
    exclusion = []

    # Chris's list (direct match) + lookalike
    chris = load_latest_summary("chris-lists-upload")
    if chris.get("custom_audience_id"):
        inclusion.append(chris["custom_audience_id"])
        log(f"  Include: Sales Prospect List = {chris['custom_audience_id']}")
    if chris.get("lookalike_audience_id"):
        inclusion.append(chris["lookalike_audience_id"])
        log(f"  Include: BH Clinic Lookalike = {chris['lookalike_audience_id']}")

    # NPPES audience + its lookalike
    nppes = load_latest_summary("nppes-upload")
    if nppes.get("audience_id"):
        inclusion.append(nppes["audience_id"])
        log(f"  Include: NPPES PMHNPs + Psychiatrists = {nppes['audience_id']}")
    if nppes.get("lookalike_audience_id"):
        inclusion.append(nppes["lookalike_audience_id"])
        log(f"  Include: NPPES Lookalike 1% = {nppes['lookalike_audience_id']}")

    # Converter lookalike (inclusion — find-more-like-these)
    conv = load_latest_summary("converters-upload")
    if conv.get("lookalike", {}).get("id"):
        inclusion.append(conv["lookalike"]["id"])
        log(f"  Include: Converter Lookalike = {conv['lookalike']['id']}")

    # Converter seed (exclusion — don't target existing converters)
    if conv.get("audience_id"):
        exclusion.append(conv["audience_id"])
        log(f"  Exclude: Converters = {conv['audience_id']}")

    # Stripe exclusion — hardcoded from latest sync (created fresh each run)
    # Check the exclusion log
    exc_dir = Path(__file__).resolve().parents[1] / "data" / "exclusion-logs"
    exc_logs = sorted(exc_dir.glob("sync-*.json"), reverse=True) if exc_dir.exists() else []
    if exc_logs:
        exc_data = json.loads(exc_logs[0].read_text())
        if exc_data.get("meta_audience_id"):
            exclusion.append(exc_data["meta_audience_id"])
            log(f"  Exclude: Stripe Customers = {exc_data['meta_audience_id']}")

    return inclusion, exclusion


# ---------------------------------------------------------------------------
# Meta API: Get ad sets, patch targeting
# ---------------------------------------------------------------------------
def get_active_adsets() -> list[dict]:
    """Fetch all ACTIVE ad sets from Farm+Scale campaigns."""
    url = f"{BASE_URL}/{META_AD_ACCOUNT}/adsets"
    params = {
        "access_token": TOKEN,
        "fields": "id,name,campaign_id,campaign{name},status,targeting",
        "limit": 200,
        "filtering": json.dumps([
            {"field": "effective_status", "operator": "IN", "value": ["ACTIVE", "PAUSED"]},
        ]),
    }
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json().get("data", [])

    # Filter to Farm+Scale campaigns
    in_scope = []
    for adset in data:
        campaign_name = adset.get("campaign", {}).get("name", "")
        if any(campaign_name.startswith(p) for p in SCOPE_PREFIXES):
            in_scope.append(adset)

    return in_scope


def patch_adset_targeting(adset_id: str, adset_name: str,
                          current_targeting: dict,
                          include_ids: list[str],
                          exclude_ids: list[str],
                          dry_run: bool = False) -> dict:
    """Add custom audiences to an ad set's targeting. Merges with existing."""
    targeting = dict(current_targeting)

    # Merge inclusion custom audiences
    existing_custom = targeting.get("custom_audiences", [])
    existing_ids = {a.get("id") for a in existing_custom}
    for aid in include_ids:
        if aid not in existing_ids:
            existing_custom.append({"id": aid})
    targeting["custom_audiences"] = existing_custom

    # Merge exclusion custom audiences
    existing_excl = targeting.get("excluded_custom_audiences", [])
    existing_excl_ids = {a.get("id") for a in existing_excl}
    for aid in exclude_ids:
        if aid not in existing_excl_ids:
            existing_excl.append({"id": aid})
    targeting["excluded_custom_audiences"] = existing_excl

    if dry_run:
        log(f"  [DRY RUN] Would patch {adset_name} ({adset_id})")
        log(f"    Include: {[a['id'] for a in targeting['custom_audiences']]}")
        log(f"    Exclude: {[a['id'] for a in targeting['excluded_custom_audiences']]}")
        return {"dry_run": True, "adset_id": adset_id}

    url = f"{BASE_URL}/{adset_id}"
    resp = requests.post(url, data={
        "access_token": TOKEN,
        "targeting": json.dumps(targeting),
    }, timeout=60)
    resp.raise_for_status()
    result = resp.json()
    log(f"  Patched {adset_name} ({adset_id}) -> {result}")
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        log("=== DRY RUN MODE ===\n")

    log("Loading audience IDs from upload summaries...")
    include_ids, exclude_ids = collect_audience_ids()

    if not include_ids and not exclude_ids:
        log("No audience IDs found. Run the upload scripts first.")
        sys.exit(1)

    log(f"\nTotal inclusion audiences: {len(include_ids)}")
    log(f"Total exclusion audiences: {len(exclude_ids)}")

    log("\nFetching active Farm+Scale ad sets...")
    adsets = get_active_adsets()
    log(f"Found {len(adsets)} in-scope ad sets\n")

    results = []
    for adset in adsets:
        current_targeting = adset.get("targeting", {})
        result = patch_adset_targeting(
            adset["id"], adset["name"],
            current_targeting,
            include_ids, exclude_ids,
            dry_run=dry_run,
        )
        results.append(result)

    log(f"\nDone. Patched {len(results)} ad sets.")

    if not dry_run:
        summary_path = AUDIENCES_DIR / "attach-summary-latest.json"
        summary_path.write_text(json.dumps({
            "include_ids": include_ids,
            "exclude_ids": exclude_ids,
            "adsets_patched": len(results),
            "results": results,
        }, indent=2))
        log(f"Summary -> {summary_path}")


if __name__ == "__main__":
    main()
