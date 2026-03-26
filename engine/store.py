"""
Data Store — persistence layer for all engine objects.

Starts with JSON file storage for simplicity. The intern can migrate
to SQLite or Postgres when volume demands it. The interface stays the same.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from engine.models import (
    AdVariant,
    AdStatus,
    CreativeBrief,
    DecisionRecord,
    ExistingAd,
    PerformanceSnapshot,
    RegressionResult,
)


class Store:
    """
    File-based store. Each entity type gets its own directory.
    Objects are stored as individual JSON files keyed by ID.
    """

    def __init__(self, base_path: str = "data"):
        self.base = Path(base_path)
        self.briefs_dir = self.base / "briefs"
        self.variants_dir = self.base / "creatives" / "variants"
        self.snapshots_dir = self.base / "performance" / "snapshots"
        self.decisions_dir = self.base / "performance" / "decisions"
        self.regression_dir = self.base / "models"
        self.existing_ads_dir = self.base / "existing_creative"

        # Ensure directories exist
        for d in [self.briefs_dir, self.variants_dir, self.snapshots_dir, self.decisions_dir, self.regression_dir, self.existing_ads_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # -- Briefs --

    def save_brief(self, brief: CreativeBrief) -> None:
        path = self.briefs_dir / f"{brief.id}.json"
        path.write_text(brief.model_dump_json(indent=2))

    def get_brief(self, brief_id: str) -> CreativeBrief:
        path = self.briefs_dir / f"{brief_id}.json"
        return CreativeBrief.model_validate_json(path.read_text())

    def get_all_briefs(self) -> list[CreativeBrief]:
        return [
            CreativeBrief.model_validate_json(f.read_text())
            for f in self.briefs_dir.glob("*.json")
        ]

    # -- Variants --

    def save_variant(self, variant: AdVariant) -> None:
        path = self.variants_dir / f"{variant.id}.json"
        path.write_text(variant.model_dump_json(indent=2))

    def get_variant(self, variant_id: str) -> AdVariant:
        path = self.variants_dir / f"{variant_id}.json"
        return AdVariant.model_validate_json(path.read_text())

    def get_all_variants(self) -> list[AdVariant]:
        return [
            AdVariant.model_validate_json(f.read_text())
            for f in self.variants_dir.glob("*.json")
        ]

    def get_variants_by_status(self, status: AdStatus) -> list[AdVariant]:
        return [v for v in self.get_all_variants() if v.status == status]

    def get_variants_for_brief(self, brief_id: str) -> list[AdVariant]:
        return [v for v in self.get_all_variants() if v.brief_id == brief_id]

    # -- Performance Snapshots --

    def save_snapshot(self, snapshot: PerformanceSnapshot) -> None:
        path = self.snapshots_dir / f"{snapshot.id}.json"
        path.write_text(snapshot.model_dump_json(indent=2))

    def get_snapshots_for_variant(self, variant_id: str) -> list[PerformanceSnapshot]:
        all_snapshots = [
            PerformanceSnapshot.model_validate_json(f.read_text())
            for f in self.snapshots_dir.glob("*.json")
        ]
        return sorted(
            [s for s in all_snapshots if s.ad_variant_id == variant_id],
            key=lambda s: s.date,
        )

    def get_all_snapshots(self) -> list[PerformanceSnapshot]:
        return [
            PerformanceSnapshot.model_validate_json(f.read_text())
            for f in self.snapshots_dir.glob("*.json")
        ]

    # -- Decision Records --

    def save_decision(self, decision: DecisionRecord) -> None:
        path = self.decisions_dir / f"{decision.id}.json"
        path.write_text(decision.model_dump_json(indent=2))

    def get_decisions_for_variant(self, variant_id: str) -> list[DecisionRecord]:
        all_decisions = [
            DecisionRecord.model_validate_json(f.read_text())
            for f in self.decisions_dir.glob("*.json")
        ]
        return sorted(
            [d for d in all_decisions if d.ad_variant_id == variant_id],
            key=lambda d: d.date,
        )

    # -- Regression Results --

    def save_regression(self, result: RegressionResult) -> None:
        path = self.regression_dir / f"regression_{result.run_date.isoformat()}.json"
        path.write_text(result.model_dump_json(indent=2))

    def get_latest_regression(self) -> Optional[RegressionResult]:
        files = sorted(self.regression_dir.glob("regression_*.json"), reverse=True)
        if not files:
            return None
        return RegressionResult.model_validate_json(files[0].read_text())

    # -- Existing Ads (imported from Meta/Google) --

    def save_existing_ad(self, ad: ExistingAd) -> None:
        path = self.existing_ads_dir / f"{ad.id}.json"
        path.write_text(ad.model_dump_json(indent=2))

    def get_existing_ad(self, ad_id: str) -> ExistingAd:
        path = self.existing_ads_dir / f"{ad_id}.json"
        return ExistingAd.model_validate_json(path.read_text())

    def get_all_existing_ads(self) -> list[ExistingAd]:
        return [
            ExistingAd.model_validate_json(f.read_text())
            for f in self.existing_ads_dir.glob("*.json")
        ]

    def get_existing_ads_with_taxonomy(self) -> list[ExistingAd]:
        return [ad for ad in self.get_all_existing_ads() if ad.taxonomy is not None]

    def find_existing_ad_by_meta_id(self, meta_ad_id: str) -> Optional[ExistingAd]:
        for ad in self.get_all_existing_ads():
            if ad.meta_ad_id == meta_ad_id:
                return ad
        return None
