"""
GTM Inventory — pulls the live GTM-KL9RPN9V container via the Tag Manager API
v2 and surfaces the tags + the GA4 measurement IDs each one fires to.

Auth pattern matches engine/tracking/ga_tracker.py: ADC + impersonation of
ads-engine-ga-reader@ads-engin.iam.gserviceaccount.com. The org policy blocks
SA key creation, so we mint short-lived tokens at runtime.

Granted GTM Read access to the SA on 2026-04-29.

Usage:
    python scripts/gtm_inventory.py
    python scripts/gtm_inventory.py --tag "GA4 - SignUp Confirm Event"
    python scripts/gtm_inventory.py --json
"""

from __future__ import annotations

import argparse
import json
import sys

import google.auth
from google.auth import impersonated_credentials
from googleapiclient.discovery import build


CONTAINER_PUBLIC_ID = "GTM-KL9RPN9V"
IMPERSONATE_SA = "ads-engine-ga-reader@ads-engin.iam.gserviceaccount.com"
SCOPES = ["https://www.googleapis.com/auth/tagmanager.readonly"]


def get_gtm_client():
    source_creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    target_creds = impersonated_credentials.Credentials(
        source_credentials=source_creds,
        target_principal=IMPERSONATE_SA,
        target_scopes=SCOPES,
        lifetime=3600,
    )
    return build("tagmanager", "v2", credentials=target_creds, cache_discovery=False)


def find_container(gtm):
    accounts = gtm.accounts().list().execute().get("account", [])
    for account in accounts:
        containers = (
            gtm.accounts()
            .containers()
            .list(parent=account["path"])
            .execute()
            .get("container", [])
        )
        for c in containers:
            if c.get("publicId") == CONTAINER_PUBLIC_ID:
                return account, c
    raise RuntimeError(f"Container {CONTAINER_PUBLIC_ID} not visible to {IMPERSONATE_SA}")


def get_default_workspace(gtm, container_path):
    workspaces = (
        gtm.accounts()
        .containers()
        .workspaces()
        .list(parent=container_path)
        .execute()
        .get("workspace", [])
    )
    if not workspaces:
        raise RuntimeError("No workspaces in container")
    for w in workspaces:
        if w.get("name", "").lower().startswith("default"):
            return w
    return workspaces[0]


def get_tags_and_triggers(gtm, workspace_path):
    tags = (
        gtm.accounts()
        .containers()
        .workspaces()
        .tags()
        .list(parent=workspace_path)
        .execute()
        .get("tag", [])
    )
    triggers = (
        gtm.accounts()
        .containers()
        .workspaces()
        .triggers()
        .list(parent=workspace_path)
        .execute()
        .get("trigger", [])
    )
    return tags, triggers


def param_value(tag, key):
    """Read a top-level parameter from a tag config."""
    for p in tag.get("parameter", []):
        if p.get("key") == key:
            return p.get("value")
    return None


def resolve_measurement_id(tag, all_tags_by_id):
    """For a GA4 Event tag, walk the tagConfigurationId reference to its
    Google Tag config and pull the measurementId."""
    config_id = param_value(tag, "measurementIdOverride")
    if config_id:
        return f"{config_id} (override)"

    config_ref_id = param_value(tag, "tagConfigurationId") or param_value(tag, "googleTagId")
    if config_ref_id:
        config_tag = all_tags_by_id.get(config_ref_id)
        if config_tag:
            mid = param_value(config_tag, "tagId") or param_value(config_tag, "measurementId")
            return f"{mid} (via {config_tag.get('name')})"
        return f"<unresolved config ref {config_ref_id}>"

    direct = param_value(tag, "tagId") or param_value(tag, "measurementId")
    if direct:
        return direct
    return None


def summarize_tag(tag, triggers_by_id, all_tags_by_id):
    trigger_names = [
        triggers_by_id.get(tid, {}).get("name", f"<{tid}>")
        for tid in tag.get("firingTriggerId", [])
    ]
    summary = {
        "name": tag.get("name"),
        "type": tag.get("type"),
        "paused": tag.get("paused", False),
        "triggers": trigger_names,
        "measurement_id": resolve_measurement_id(tag, all_tags_by_id),
    }
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", help="Filter to a single tag name")
    parser.add_argument("--json", action="store_true", help="Emit raw JSON")
    args = parser.parse_args()

    gtm = get_gtm_client()
    account, container = find_container(gtm)
    workspace = get_default_workspace(gtm, container["path"])

    tags, triggers = get_tags_and_triggers(gtm, workspace["path"])

    triggers_by_id = {t["triggerId"]: t for t in triggers}
    tags_by_id = {t["tagId"]: t for t in tags}

    print(f"Account: {account.get('name')} ({account.get('accountId')})")
    print(f"Container: {container.get('name')} ({container.get('publicId')})")
    print(f"Workspace: {workspace.get('name')}")
    print(f"Tags: {len(tags)}  Triggers: {len(triggers)}")
    print()

    summaries = [summarize_tag(t, triggers_by_id, tags_by_id) for t in tags]

    if args.tag:
        summaries = [s for s in summaries if s["name"] == args.tag]
        if not summaries:
            print(f"No tag named {args.tag!r}", file=sys.stderr)
            sys.exit(1)

    if args.json:
        print(json.dumps(summaries, indent=2))
        return

    print(f"{'TAG':<55} {'TYPE':<28} {'TRIGGERS':<35} MEASUREMENT_ID")
    print("-" * 160)
    for s in summaries:
        triggers_str = ", ".join(s["triggers"])[:33]
        mid = s["measurement_id"] or ""
        paused = " [PAUSED]" if s["paused"] else ""
        print(f"{s['name'][:53]+paused:<55} {s['type']:<28} {triggers_str:<35} {mid}")


if __name__ == "__main__":
    main()
