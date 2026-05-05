#!/usr/bin/env python3
"""Retry NPPES prefix queries that 403'd during the backfill.

NPPES rate-limited us on the tail of the 34K-query fan-out. This re-runs
the ~930 failed (query, state, prefix) tuples serially with generous
delays, dedupes, and appends anything new to the existing audience.
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date
from pathlib import Path

# Reuse utilities from the backfill module
sys.path.insert(0, str(Path(__file__).resolve().parent))
from importlib.util import spec_from_file_location, module_from_spec
spec = spec_from_file_location("bf", str(Path(__file__).resolve().parent / "backfill-nppes-capped.py"))
bf = module_from_spec(spec)
spec.loader.exec_module(bf)

LOG = Path("/tmp/nppes-backfill.log")
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "audiences"
TODAY = date.today().isoformat()


def parse_failures(log_path: Path) -> list[tuple[str, str, str]]:
    """Extract (query, state, prefix) from ERROR lines."""
    pattern = re.compile(r"ERROR (Psychiatry|Psych/Mental)/(\w+)/(\w+): 403")
    tuples = []
    for line in log_path.read_text().splitlines():
        m = pattern.search(line)
        if m:
            tuples.append((m.group(1), m.group(2), m.group(3)))
    return tuples


def main() -> None:
    failures = parse_failures(LOG)
    bf.log(f"Retrying {len(failures)} failed prefix queries (serial, 0.4s sleep)")

    existing = bf.load_existing_npis()
    # Add the prior backfill's NPIs to the "already seen" set
    prior = DATA_DIR / f"nppes-backfill-{TODAY}.json"
    if prior.exists():
        for r in json.loads(prior.read_text()):
            if r.get("npi"):
                existing.add(r["npi"])
        bf.log(f"Added prior backfill NPIs -> {len(existing):,} total seen")

    new: dict[str, dict] = {}
    for i, (query, state, prefix) in enumerate(failures, 1):
        try:
            batch = bf.fetch_slice(query, state, prefix)
        except Exception as e:
            bf.log(f"  still failed {query}/{state}/{prefix}: {e}")
            continue
        for raw in batch:
            if not bf.has_target_taxonomy(raw):
                continue
            npi = raw.get("number")
            if not npi or npi in existing or npi in new:
                continue
            rec = bf.extract_record(raw)
            if rec:
                new[npi] = rec
        if i % 100 == 0:
            bf.log(f"  {i}/{len(failures)} done; new so far: {len(new):,}")
        time.sleep(0.4)

    bf.log(f"Retry complete: {len(new):,} additional unique providers")
    out = DATA_DIR / f"nppes-retry-{TODAY}.json"
    out.write_text(json.dumps(list(new.values()), indent=2))

    if new:
        summaries = sorted(DATA_DIR.glob("nppes-upload-*.json"), reverse=True)
        audience_id = json.loads(summaries[0].read_text())["audience_id"]
        bf.log(f"Appending {len(new):,} records to {audience_id}")
        results = bf.upload_to_meta(audience_id, list(new.values()))
        (DATA_DIR / f"nppes-retry-upload-{TODAY}.json").write_text(json.dumps({
            "date": TODAY,
            "audience_id": audience_id,
            "new_records": len(new),
            "batches": len(results),
            "batch_results": results,
        }, indent=2))

    bf.log("Done.")


if __name__ == "__main__":
    main()
