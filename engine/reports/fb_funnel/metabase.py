"""Tiny Metabase native-query client. Self-contained — no jotbill_crm imports.

Auth: METABASE_URL + METABASE_API_KEY in ~/.claude/.env or process env.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

import requests

from .config import METABASE_DB_ID, METABASE_TIMEOUT

_GLOBAL_ENV = Path.home() / ".claude" / ".env"


def _load_env() -> None:
    """Load ~/.claude/.env into os.environ if not already present."""
    if "METABASE_URL" in os.environ and "METABASE_API_KEY" in os.environ:
        return
    if not _GLOBAL_ENV.exists():
        return
    for line in _GLOBAL_ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), v)


def run_sql(sql: str) -> List[Dict[str, Any]]:
    """Run a native Postgres query against the analytics Metabase and return rows as dicts."""
    _load_env()
    base = os.environ.get("METABASE_URL", "").rstrip("/")
    key = os.environ.get("METABASE_API_KEY", "")
    if not base or not key:
        raise RuntimeError("METABASE_URL and METABASE_API_KEY must be set (check ~/.claude/.env)")

    body = {
        "type": "native",
        "native": {"query": sql},
        "database": METABASE_DB_ID,
    }
    resp = requests.post(
        f"{base}/api/dataset",
        json=body,
        headers={"Content-Type": "application/json", "x-api-key": key},
        timeout=METABASE_TIMEOUT,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Metabase HTTP {resp.status_code}: {resp.text[:400]}")
    payload = resp.json()

    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    cols = [c.get("name", f"col_{i}") for i, c in enumerate(data.get("cols", []))]
    rows = data.get("rows", [])
    return [dict(zip(cols, r)) for r in rows]
