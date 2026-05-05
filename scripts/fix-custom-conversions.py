"""
Fix the Custom Conversions — v3. Third bug discovered 2026-04-23: the rule field
name itself was wrong. We were building `{"event_type":{"eq":"FirstNote"}}`; the
correct Meta field is `event`. The v1 Apr 20 and v2 Apr 22 batches both used the
wrong key and never matched a single pixel event. Verified by inspecting all UI-
created CCs on the account (Page View, Demo Scheduled, etc.) — all use `event`.

Bugs across the three attempts:
1. v1 (Apr 20): whitespace in the rule value + cents mis-unit + event_type key.
2. v2 (Apr 22): whitespace fixed, cents fixed, but event_type key persisted.
3. v3 (this file): switches to `event`, rule field Meta actually matches against.

Behavior:
- Creates new CCs one at a time, starting with FirstNote.
- After each create, reads back via API and prints a verify block.
- Saves a manifest of the new CCs to data/custom-conversions/ with today's date.
- Does NOT delete or rename the old CCs. They stay in the account; per the
  never-delete rule, cleanup via archive/rename happens via a separate PATCH step.
- Does NOT touch the ad set's promoted_object. That PATCH is a separate step so
  the ad set's pixel_rule rebinds to the new v3 FirstNote CC.

Rollback:
- If a new CC is mis-created, rename it to _archived_<name> via PATCH on name,
  and re-run this script with a corrected value or rule.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests

API_VERSION = "v21.0"
GRAPH = f"https://graph.facebook.com/{API_VERSION}"

PIXEL_ID = "1625233994894344"  # WebApp Actions

# Broken predecessors. Not deleted. v1 archived Apr 22, v2 archived Apr 23.
OLD_CCS = {
    "FirstNote (Valued) v2": "4363987073922754",
    "SignUpConfirm (Valued) v2": "1673233627279622",
    "CalendarScheduled (Valued) v2": "829867779586914",
    "FirstNote (Valued) v1 (archived)": "3914250848710226",
    "SignUpConfirm (Valued) v1 (archived)": "1960979881475090",
    "CalendarScheduled (Valued) v1 (archived)": "1270312578633364",
}

NEW_CCS = [
    {
        "name": "FirstNote (Valued) v3",
        "event_name": "FirstNote",
        "value_dollars": 100,
        "description": "FirstNote event, auto-weighted $100 for VALUE optimization. v3 after event/event_type field bug 2026-04-23.",
    },
    {
        "name": "SignUpConfirm (Valued) v3",
        "event_name": "SignUpConfirm",
        "value_dollars": 5,
        "description": "SignUpConfirm event, auto-weighted $5 for VALUE optimization. v3 after event/event_type field bug 2026-04-23.",
    },
    {
        "name": "CalendarScheduled (Valued) v3",
        "event_name": "CalendarScheduled",
        "value_dollars": 15,
        "description": "CalendarScheduled event, auto-weighted $15 for VALUE optimization. v3 after event/event_type field bug 2026-04-23.",
    },
]


def build_rule(event_name: str) -> str:
    clean_name = event_name.strip()
    if clean_name != event_name or " " in clean_name:
        raise ValueError(f"event_name contains whitespace: {event_name!r}")
    # Meta rejects `{"and":[{"event":{"eq":"..."}}]}` alone (subcode 1760020,
    # "A conversion rule is required at creation time"). Requires a URL condition
    # paired with `event`. Matching the pattern of the account's UI-created CCs
    # (Page View, Demo Scheduled, etc. — `event`+URL, first_fired 2024-04-12).
    return json.dumps(
        {
            "and": [
                {"event": {"eq": clean_name}},
                {"or": [{"URL": {"i_contains": "jotpsych"}}]},
            ]
        },
        separators=(",", ":"),
    )


def account_id() -> str:
    acct = os.environ["META_ADS_ACCOUNT_ID"]
    return acct if acct.startswith("act_") else f"act_{acct}"


def create_custom_conversion(tok: str, spec: dict[str, Any]) -> dict[str, Any]:
    rule = build_rule(spec["event_name"])
    payload = {
        "access_token": tok,
        "name": spec["name"],
        "event_source_id": PIXEL_ID,
        "custom_event_type": "OTHER",
        "rule": rule,
        "default_conversion_value": spec["value_dollars"] * 100,
        "description": spec["description"],
    }
    url = f"{GRAPH}/{account_id()}/customconversions"
    r = requests.post(url, data=payload)
    j = r.json()
    if r.status_code >= 400 or "error" in j:
        raise RuntimeError(f"Create failed for {spec['name']}: {j}")
    return j


def read_custom_conversion(tok: str, cc_id: str) -> dict[str, Any]:
    r = requests.get(
        f"{GRAPH}/{cc_id}",
        params={
            "access_token": tok,
            "fields": "id,name,custom_event_type,rule,default_conversion_value,is_archived,creation_time,description,pixel{id,name}",
        },
    )
    return r.json()


def verify_block(cc: dict[str, Any], expected_cents: int, expected_event: str) -> list[str]:
    warnings: list[str] = []
    rule_str = cc.get("rule", "")
    try:
        rule_json = json.loads(rule_str)
        got_event = rule_json["and"][0]["event"]["eq"]
        if got_event != expected_event:
            warnings.append(f"rule event mismatch: got {got_event!r}, want {expected_event!r}")
        if got_event != got_event.strip():
            warnings.append(f"rule event has whitespace: {got_event!r}")
        if "event_type" in rule_str:
            warnings.append(f"rule still references event_type (wrong field): {rule_str}")
        if "URL" not in rule_str:
            warnings.append(f"rule lacks URL condition — Meta rejects bare `event` rules")
    except Exception as e:
        warnings.append(f"rule could not be parsed: {e}")
    got_value = cc.get("default_conversion_value")
    if got_value is None:
        warnings.append("default_conversion_value missing from API response")
    elif float(got_value) != float(expected_cents):
        warnings.append(
            f"default_conversion_value API mismatch: got {got_value!r}, sent {expected_cents!r}. "
            f"Note: UI displays this divided by 100; {expected_cents} should render as ${expected_cents/100:.2f}."
        )
    return warnings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=["FirstNote", "SignUpConfirm", "CalendarScheduled"], help="create only one CC by event name; useful for a halt-and-verify first pass")
    parser.add_argument("--skip", nargs="*", default=[], help="skip these event names (e.g. --skip FirstNote after a first-pass create)")
    parser.add_argument("--dry-run", action="store_true", help="print the payloads but do not hit the API")
    args = parser.parse_args()

    tok = os.environ["META_ADS_ACCESS_TOKEN"]

    out_dir = Path("data/custom-conversions")
    out_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    manifest_path = out_dir / f"valued-conversions-{today}.json"

    created: list[dict[str, Any]] = []
    to_run = [s for s in NEW_CCS if s["event_name"] not in args.skip]
    if args.only:
        to_run = [s for s in to_run if s["event_name"] == args.only]
    for i, spec in enumerate(to_run):
        rule = build_rule(spec["event_name"])
        print(f"\n--- [{i+1}/{len(to_run)}] {spec['name']} ---", file=sys.stderr)
        print(f"  rule: {rule}", file=sys.stderr)
        print(f"  value: ${spec['value_dollars']} (sent as {spec['value_dollars']*100} cents)", file=sys.stderr)
        print(f"  event_source_id: {PIXEL_ID}", file=sys.stderr)

        if args.dry_run:
            print("  [dry-run] not creating", file=sys.stderr)
            continue

        res = create_custom_conversion(tok, spec)
        cc_id = res["id"]
        print(f"  created id: {cc_id}", file=sys.stderr)

        read = read_custom_conversion(tok, cc_id)
        print(f"  API readback:", file=sys.stderr)
        print(json.dumps(read, indent=2), file=sys.stderr)

        warnings = verify_block(read, spec["value_dollars"] * 100, spec["event_name"])
        if warnings:
            print(f"  ⚠ VERIFY WARNINGS:", file=sys.stderr)
            for w in warnings:
                print(f"     {w}", file=sys.stderr)
        else:
            print(f"  ✓ API-level checks pass", file=sys.stderr)

        created.append({
            "name": spec["name"],
            "id": cc_id,
            "event_name": spec["event_name"],
            "value_dollars_intended": spec["value_dollars"],
            "value_sent_api": spec["value_dollars"] * 100,
            "value_returned": read.get("default_conversion_value"),
            "rule_returned": read.get("rule"),
            "warnings": warnings,
        })

        print(
            f"\n  ▶ ACTION: open Meta Events Manager > Custom Conversions > {spec['name']} "
            f"and confirm the UI shows 'Conversion value: ${spec['value_dollars']}.00' exactly. "
            f"If it shows a different dollar amount, STOP and archive this CC.",
            file=sys.stderr,
        )

    manifest = {
        "created_at": today,
        "pixel_id": PIXEL_ID,
        "deprecated_ccs": OLD_CCS,
        "new_ccs": created,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest written: {manifest_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
