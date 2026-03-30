"""
Data Store — persistence layer for all engine objects.

Starts with JSON file storage for simplicity. The intern can migrate
to SQLite or Postgres when volume demands it. The interface stays the same.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Optional


@contextmanager
def _atomic_write(path: Path):
    """Write to a file with advisory locking to prevent concurrent corruption."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            yield f
            f.flush()
            os.fsync(f.fileno())
        tmp.rename(path)  # atomic on POSIX
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

from engine.models import (
    AdVariant,
    AdStatus,
    CreativeBrief,
    CreativeMemory,
    CreativeTaxonomy,
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
        self.memory_dir = self.base / "memory"

        # Ensure directories exist
        for d in [self.briefs_dir, self.variants_dir, self.snapshots_dir, self.decisions_dir, self.regression_dir, self.existing_ads_dir, self.memory_dir]:
            d.mkdir(parents=True, exist_ok=True)

    # -- Briefs --

    def save_brief(self, brief: CreativeBrief) -> None:
        path = self.briefs_dir / f"{brief.id}.json"
        with _atomic_write(path) as f:
            f.write(brief.model_dump_json(indent=2))

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
        with _atomic_write(path) as f:
            f.write(variant.model_dump_json(indent=2))

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
        with _atomic_write(path) as f:
            f.write(snapshot.model_dump_json(indent=2))

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
        with _atomic_write(path) as f:
            f.write(decision.model_dump_json(indent=2))

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
        with _atomic_write(path) as f:
            f.write(result.model_dump_json(indent=2))

    def get_latest_regression(self) -> Optional[RegressionResult]:
        files = sorted(self.regression_dir.glob("regression_*.json"), reverse=True)
        if not files:
            return None
        return RegressionResult.model_validate_json(files[0].read_text())

    # -- Existing Ads (imported from Meta/Google) --

    def save_existing_ad(self, ad: ExistingAd) -> None:
        path = self.existing_ads_dir / f"{ad.id}.json"
        with _atomic_write(path) as f:
            f.write(ad.model_dump_json(indent=2))

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

    # -- Creative Memory --

    def save_memory(self, memory) -> None:
        """Save creative memory (supports both v1 and v2 formats)."""
        import dataclasses
        import json
        
        path = self.memory_dir / "creative_memory.json"
        
        if hasattr(memory, 'model_dump_json'):
            with _atomic_write(path) as f:
                f.write(memory.model_dump_json(indent=2))
        elif dataclasses.is_dataclass(memory):
            def convert(obj):
                if dataclasses.is_dataclass(obj):
                    return {k: convert(v) for k, v in dataclasses.asdict(obj).items()}
                elif isinstance(obj, (list, tuple)):
                    return [convert(v) for v in obj]
                elif isinstance(obj, dict):
                    return {k: convert(v) for k, v in obj.items()}
                elif hasattr(obj, 'isoformat'):
                    return obj.isoformat()
                elif hasattr(obj, 'value'):
                    return obj.value
                return obj

            with _atomic_write(path) as f:
                f.write(json.dumps(convert(memory), indent=2, default=str))
        else:
            raise ValueError(f"Unknown memory type: {type(memory)}")

    def load_memory(self) -> Optional[CreativeMemory]:
        """Load creative memory (returns None if not found)."""
        path = self.memory_dir / "creative_memory.json"
        if not path.exists():
            return None
        return CreativeMemory.model_validate_json(path.read_text())

    def load_memory_v2(self):
        """Load v2 creative memory (dataclass-based)."""
        import json
        from engine.memory.models import CreativeMemory as CreativeMemoryV2
        
        path = self.memory_dir / "creative_memory.json"
        if not path.exists():
            return None
        
        data = json.loads(path.read_text())
        
        if data.get("version", 1) >= 2:
            return self._deserialize_memory_v2(data)
        
        return None

    def _deserialize_memory_v2(self, data: dict):
        """Deserialize v2 memory from JSON dict."""
        from datetime import date, datetime
        from engine.memory.models import (
            CreativeMemory,
            StatisticalMemory,
            EditorialMemory,
            MarketMemory,
            PatternInsight,
            FatigueAlert,
            InteractionInsight,
            TimestampedCoefficient,
            ApprovalCluster,
            RejectionRule,
            ReviewerProfile,
            CombinationStats,
        )
        
        def parse_date(s):
            if s is None:
                return None
            if isinstance(s, date):
                return s
            return date.fromisoformat(s) if s else None
        
        def parse_datetime(s):
            if s is None:
                return None
            if isinstance(s, datetime):
                return s
            return datetime.fromisoformat(s) if s else None
        
        stat_data = data.get("statistical", {})
        stat = StatisticalMemory(
            winning_patterns=[
                PatternInsight(
                    first_significant_date=parse_date(p.get("first_significant_date")),
                    **{k: v for k, v in p.items() if k != "first_significant_date"}
                )
                for p in stat_data.get("winning_patterns", [])
            ],
            losing_patterns=[
                PatternInsight(
                    first_significant_date=parse_date(p.get("first_significant_date")),
                    **{k: v for k, v in p.items() if k != "first_significant_date"}
                )
                for p in stat_data.get("losing_patterns", [])
            ],
            coefficient_history={
                k: [TimestampedCoefficient(
                    run_date=parse_date(c.get("run_date")),
                    **{ck: cv for ck, cv in c.items() if ck != "run_date"}
                ) for c in v]
                for k, v in stat_data.get("coefficient_history", {}).items()
            },
            fatiguing_patterns=[
                FatigueAlert(
                    first_deployed=parse_date(f.get("first_deployed")),
                    **{k: v for k, v in f.items() if k != "first_deployed"}
                )
                for f in stat_data.get("fatiguing_patterns", [])
            ],
            r_squared=stat_data.get("r_squared", 0),
            n_observations=stat_data.get("n_observations", 0),
            last_run_date=parse_date(stat_data.get("last_run_date")),
        )
        
        edit_data = data.get("editorial", {})
        edit = EditorialMemory(
            approval_clusters=[
                ApprovalCluster(**c) for c in edit_data.get("approval_clusters", [])
            ],
            rejection_rules=[
                RejectionRule(**r) for r in edit_data.get("rejection_rules", [])
            ],
            reviewer_profiles={
                k: ReviewerProfile(
                    last_review_date=parse_date(v.get("last_review_date")),
                    **{rk: rv for rk, rv in v.items() if rk != "last_review_date"}
                )
                for k, v in edit_data.get("reviewer_profiles", {}).items()
            },
            total_approvals=edit_data.get("total_approvals", 0),
            total_rejections=edit_data.get("total_rejections", 0),
        )
        
        market_data = data.get("market", {})
        market = MarketMemory(
            combination_stats={
                k: CombinationStats(
                    last_deployed=parse_date(v.get("last_deployed")),
                    **{ck: cv for ck, cv in v.items() if ck != "last_deployed"}
                )
                for k, v in market_data.get("combination_stats", {}).items()
            },
            least_tested_combinations=[
                tuple(c) for c in market_data.get("least_tested_combinations", [])
            ],
        )
        
        # Parse creative directions
        from engine.memory.models import CreativeDirection
        creative_directions = []
        for d in data.get("creative_directions", []):
            creative_directions.append(CreativeDirection(
                id=d.get("id", ""),
                text=d.get("text", ""),
                added_by=d.get("added_by", ""),
                added_at=parse_datetime(d.get("added_at")) or datetime.utcnow(),
                active=d.get("active", True),
                source=d.get("source", "manual"),
                source_id=d.get("source_id"),
            ))

        return CreativeMemory(
            id=data.get("id", ""),
            statistical=stat,
            editorial=edit,
            market=market,
            creative_directions=creative_directions,
            built_at=parse_datetime(data.get("built_at")),
            data_quality_score=data.get("data_quality_score", 0),
            version=data.get("version", 2),
        )

    # -- Deployed Taxonomies (for explore/exploit) --

    def get_recent_deployed_taxonomies(self, n_cycles: int = 3) -> list[CreativeTaxonomy]:
        """
        Get taxonomy data from recently deployed variants.
        Uses n_cycles worth of regression runs to determine recency.
        """
        regression_files = sorted(self.regression_dir.glob("regression_*.json"), reverse=True)
        
        if len(regression_files) < n_cycles:
            cutoff_date = None
        else:
            oldest_file = regression_files[n_cycles - 1]
            oldest_result = RegressionResult.model_validate_json(oldest_file.read_text())
            cutoff_date = oldest_result.run_date
        
        deployed_statuses = {AdStatus.LIVE, AdStatus.GRADUATED}
        variants = self.get_all_variants()
        
        taxonomies = []
        for v in variants:
            if v.status not in deployed_statuses:
                continue
            if v.taxonomy is None:
                continue
            
            if cutoff_date is not None:
                if v.created_at.date() < cutoff_date:
                    continue
            
            taxonomies.append(v.taxonomy)

        return taxonomies

    def archive_memory_patterns(self, patterns: list, reason: str) -> None:
        """
        Move memory patterns to archive storage (M3).
        Archived patterns are preserved for historical analysis but excluded from
        active generation context.
        """
        import json
        from datetime import date

        archive_dir = self.memory_dir / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)

        archive_file = archive_dir / f"{date.today().isoformat()}.json"

        def _serialize(p):
            import dataclasses
            if dataclasses.is_dataclass(p):
                d = dataclasses.asdict(p)
                return {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in d.items()}
            elif hasattr(p, "model_dump"):
                return p.model_dump()
            return str(p)

        archive_data = {
            "archived_at": date.today().isoformat(),
            "reason": reason,
            "count": len(patterns),
            "patterns": [_serialize(p) for p in patterns],
        }

        existing = []
        if archive_file.exists():
            try:
                existing = json.loads(archive_file.read_text())
                if not isinstance(existing, list):
                    existing = [existing]
            except Exception:
                pass
        existing.append(archive_data)
        archive_file.write_text(json.dumps(existing, indent=2, default=str))

    def get_memory_status(self) -> dict:
        """
        Return memory health summary for GET /api/memory/status (M3).
        """
        import json
        from datetime import date

        status = {
            "memory_exists": False,
            "pattern_count": 0,
            "winning_count": 0,
            "losing_count": 0,
            "confidence_distribution": {},
            "oldest_pattern_date": None,
            "data_quality_score": 0.0,
            "archived_count": 0,
        }

        path = self.memory_dir / "creative_memory.json"
        if not path.exists():
            return status

        try:
            data = json.loads(path.read_text())
            status["memory_exists"] = True

            statistical = data.get("statistical", {})
            winning = statistical.get("winning_patterns", [])
            losing = statistical.get("losing_patterns", [])

            status["winning_count"] = len(winning)
            status["losing_count"] = len(losing)
            status["pattern_count"] = len(winning) + len(losing)
            status["data_quality_score"] = data.get("data_quality_score", 0.0)

            # Confidence distribution
            tiers: dict[str, int] = {}
            oldest = None
            for p in winning + losing:
                tier = p.get("confidence_tier", "unknown")
                tiers[tier] = tiers.get(tier, 0) + 1
                snap = p.get("memory_snapshot_date") or p.get("first_significant_date")
                if snap:
                    try:
                        snap_date = date.fromisoformat(snap) if isinstance(snap, str) else snap
                        if oldest is None or snap_date < oldest:
                            oldest = snap_date
                    except Exception:
                        pass
            status["confidence_distribution"] = tiers
            status["oldest_pattern_date"] = oldest.isoformat() if oldest else None

        except Exception as e:
            status["error"] = str(e)

        # Count archived patterns
        archive_dir = self.memory_dir / "archive"
        if archive_dir.exists():
            total_archived = 0
            for f in archive_dir.glob("*.json"):
                try:
                    batches = json.loads(f.read_text())
                    if isinstance(batches, list):
                        total_archived += sum(b.get("count", 0) for b in batches)
                    else:
                        total_archived += batches.get("count", 0)
                except Exception:
                    pass
            status["archived_count"] = total_archived

        return status

    # -- Hypotheses --

    def save_hypotheses(self, hypotheses: list) -> None:
        """Persist all hypotheses to data/hypotheses.json."""
        import json

        path = self.base / "hypotheses.json"
        data = []
        for h in hypotheses:
            if hasattr(h, "model_dump"):
                d = h.model_dump()
            else:
                d = h.__dict__.copy()
            # Serialize enums and dates
            for k, v in d.items():
                if hasattr(v, "value"):
                    d[k] = v.value
                elif hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
            data.append(d)
        with _atomic_write(path) as f:
            f.write(json.dumps(data, indent=2, default=str))

    def load_hypotheses(self) -> list:
        """Load all hypotheses from data/hypotheses.json."""
        import json
        from engine.models import CreativeHypothesis, HypothesisStatus

        path = self.base / "hypotheses.json"
        if not path.exists():
            return []

        try:
            data = json.loads(path.read_text())
            hypotheses = []
            for d in data:
                if "status" in d and isinstance(d["status"], str):
                    d["status"] = HypothesisStatus(d["status"])
                if "last_evaluated" in d and isinstance(d["last_evaluated"], str):
                    d["last_evaluated"] = date.fromisoformat(d["last_evaluated"]) if d["last_evaluated"] else None
                hypotheses.append(CreativeHypothesis(**d))
            return hypotheses
        except Exception:
            return []

    def get_hypothesis(self, hypothesis_id: str):
        """Load a single hypothesis by ID."""
        hypotheses = self.load_hypotheses()
        for h in hypotheses:
            if h.id == hypothesis_id:
                return h
        return None

    def get_variants_by_hypothesis(self, hypothesis_id: str) -> list[AdVariant]:
        """Get all variants generated to test a specific hypothesis."""
        return [
            v for v in self.get_all_variants()
            if getattr(v, "hypothesis_id", None) == hypothesis_id
        ]
