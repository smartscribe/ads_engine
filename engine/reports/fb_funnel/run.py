"""FB funnel report orchestrator.

Runs the full pipeline: pull → compute → qc → render.

Usage:
    python3 -m engine.reports.fb_funnel.run               # full pipeline
    python3 -m engine.reports.fb_funnel.run --no-pull     # use cached raw/
    python3 -m engine.reports.fb_funnel.run --stage qc    # only QC (assumes model.json exists)
"""
from __future__ import annotations

import argparse
import sys
import time

from . import compute, pull, qc, render


def _banner(title: str) -> None:
    print()
    print(f"━━━ {title} ━━━")


def run(do_pull: bool = True, stage: str = "all") -> int:
    t0 = time.time()

    if stage in ("all", "pull") and do_pull:
        _banner("PULL")
        pull.pull_all()

    if stage in ("all", "compute"):
        _banner("COMPUTE")
        model = compute.compute_model()
        compute.write_model(model)
        print(
            f"  weeks={len(model['weekly'])}  "
            f"biweeks={len(model['biweekly_discovery'])}  "
            f"cohort={model['cohort']['total']}  "
            f"base={model['overall_base_pct']}%"
        )

    if stage in ("all", "qc"):
        _banner("QC")
        checks = qc.run_checks()
        print(checks.report())
        if not checks.all_pass():
            print("\nQC FAILED — aborting before render.", file=sys.stderr)
            return 2

    if stage in ("all", "render"):
        _banner("RENDER")
        path = render.main()
        print(f"  → {path}")

    print(f"\nDone in {time.time() - t0:.1f}s")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="FB funnel report pipeline")
    ap.add_argument("--no-pull", action="store_true", help="skip Metabase pull; use cached raw/")
    ap.add_argument(
        "--stage",
        choices=("all", "pull", "compute", "qc", "render"),
        default="all",
        help="run a single stage",
    )
    args = ap.parse_args()
    return run(do_pull=not args.no_pull, stage=args.stage)


if __name__ == "__main__":
    sys.exit(main())
