"""
Dashboard API — FastAPI backend for the review gallery and performance views.

Endpoints:
- GET  /api/review          — variants pending review (gallery data)
- POST /api/review/approve  — approve variant(s)
- POST /api/review/reject   — reject variant(s) with feedback
- GET  /api/performance     — portfolio performance overview
- GET  /api/performance/{variant_id} — single variant performance
- GET  /api/decisions       — latest scale/kill/wait decisions
- GET  /api/regression      — latest regression insights / playbook
- POST /api/intake          — submit a new idea dump
- GET  /api/variants        — all variants with filters
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine.store import Store
from engine.intake.parser import IntakeParser
from engine.generation.generator import CreativeGenerator
from engine.review.reviewer import ReviewPipeline
from engine.decisions.engine import DecisionEngine
from engine.regression.model import CreativeRegressionModel
from engine.notifications import SlackNotifier

app = FastAPI(title="JotPsych Ads Engine", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # INTERN: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the frontend at /dashboard
_frontend_dir = Path(__file__).parent.parent / "frontend"
app.mount("/dashboard", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")

# Serve generated creative assets at /data
_data_dir = Path(__file__).parent.parent.parent / "data"
_data_dir.mkdir(parents=True, exist_ok=True)
app.mount("/data", StaticFiles(directory=str(_data_dir)), name="data")

# Initialize services
store = Store()
review_pipeline = ReviewPipeline(store)
decision_engine = DecisionEngine(store)
regression_model = CreativeRegressionModel(store)
notifier = SlackNotifier()


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class IdeaInput(BaseModel):
    raw_text: str
    source: str = "manual"


class ReviewAction(BaseModel):
    variant_ids: list[str]
    reviewer: str
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Intake
# ---------------------------------------------------------------------------

@app.post("/api/intake")
async def submit_idea(idea: IdeaInput):
    """Parse a free-form idea into a brief, generate variants."""
    parser = IntakeParser()
    brief = parser.parse(idea.raw_text, source=idea.source)
    store.save_brief(brief)

    generator = CreativeGenerator()
    variants = generator.generate(brief)
    for v in variants:
        store.save_variant(v)

    notifier.notify_variants_generated(brief.id, variants)

    return {
        "brief_id": brief.id,
        "brief": brief.model_dump(),
        "variants_generated": len(variants),
    }


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

@app.get("/api/review")
async def get_review_queue():
    """Get all variants pending review."""
    pending = review_pipeline.get_pending_review()
    return {
        "count": len(pending),
        "variants": [v.model_dump() for v in pending],
    }


@app.post("/api/review/approve")
async def approve_variants(action: ReviewAction):
    """Approve variants for deployment. Notes are optional but train the generator."""
    results = []
    for vid in action.variant_ids:
        results.append(review_pipeline.approve(vid, action.reviewer, action.notes))
    return {"approved": len(results)}


@app.post("/api/review/reject")
async def reject_variants(action: ReviewAction):
    """Reject variants with feedback."""
    if not action.notes:
        raise HTTPException(status_code=400, detail="Rejection notes are required")
    rejected = review_pipeline.batch_reject(action.variant_ids, action.reviewer, action.notes)
    return {"rejected": len(rejected)}


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

@app.get("/api/performance")
async def get_portfolio_performance():
    """Portfolio-level performance summary."""
    snapshots = store.get_all_snapshots()
    if not snapshots:
        return {"status": "no_data"}

    total_spend = sum(s.spend for s in snapshots)
    total_notes = sum(s.first_note_completions for s in snapshots)
    total_clicks = sum(s.clicks for s in snapshots)
    total_impressions = sum(s.impressions for s in snapshots)

    return {
        "total_spend": total_spend,
        "total_first_notes": total_notes,
        "blended_cpa": total_spend / total_notes if total_notes > 0 else None,
        "total_clicks": total_clicks,
        "total_impressions": total_impressions,
        "blended_ctr": total_clicks / total_impressions if total_impressions > 0 else 0,
        "active_variants": len(store.get_variants_by_status("live")),
    }


@app.get("/api/performance/{variant_id}")
async def get_variant_performance(variant_id: str):
    """Performance data for a specific variant."""
    try:
        variant = store.get_variant(variant_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Variant not found")

    snapshots = store.get_snapshots_for_variant(variant_id)
    decisions = store.get_decisions_for_variant(variant_id)

    return {
        "variant": variant.model_dump(),
        "snapshots": [s.model_dump() for s in snapshots],
        "decisions": [d.model_dump() for d in decisions],
    }


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------

@app.get("/api/decisions")
async def get_latest_decisions():
    """Get the most recent decision batch."""
    decisions = decision_engine.run_daily()
    return {
        "date": date.today().isoformat(),
        "decisions": [d.model_dump() for d in decisions],
        "summary": {
            "scale": len([d for d in decisions if d.verdict.value == "scale"]),
            "kill": len([d for d in decisions if d.verdict.value == "kill"]),
            "wait": len([d for d in decisions if d.verdict.value == "wait"]),
        },
    }


# ---------------------------------------------------------------------------
# Regression
# ---------------------------------------------------------------------------

@app.get("/api/regression")
async def get_regression_insights():
    """Get the latest regression playbook."""
    playbook = regression_model.get_creative_playbook()
    return playbook


# ---------------------------------------------------------------------------
# Variants
# ---------------------------------------------------------------------------

@app.get("/api/variants")
async def list_variants(status: Optional[str] = None):
    """List all variants, optionally filtered by status."""
    if status:
        variants = store.get_variants_by_status(status)
    else:
        variants = store.get_all_variants()

    return {
        "count": len(variants),
        "variants": [v.model_dump() for v in variants],
    }


# ---------------------------------------------------------------------------
# Analysis — export, tag, and analyze existing Meta ads
# ---------------------------------------------------------------------------

@app.post("/api/analyze/export")
async def export_meta_ads():
    """Export all Meta ads with creative + performance data."""
    from engine.analysis.analyzer import MetaAdsExporter
    exporter = MetaAdsExporter()
    ads = exporter.export_all(store)
    return {
        "exported": len(ads),
        "with_conversions": len([a for a in ads if a.conversions > 0]),
        "total_spend": sum(a.spend for a in ads),
    }


@app.get("/api/analyze/status")
async def get_analysis_status():
    """Check export and analysis progress."""
    all_ads = store.get_all_existing_ads()
    tagged = [a for a in all_ads if a.taxonomy is not None]
    with_spend = [a for a in all_ads if a.spend > 0]
    return {
        "total_exported": len(all_ads),
        "tagged": len(tagged),
        "untagged": len(all_ads) - len(tagged),
        "with_spend": len(with_spend),
        "total_spend": sum(a.spend for a in all_ads),
        "total_conversions": sum(a.conversions for a in all_ads),
    }


@app.post("/api/analyze/tag")
async def tag_exported_ads():
    """Run Claude taxonomy tagging on exported ads."""
    from engine.analysis.analyzer import CreativeAnalyzer
    analyzer = CreativeAnalyzer()
    ads = store.get_all_existing_ads()
    tagged = analyzer.tag_ads(ads, store)
    return {
        "total": len(tagged),
        "newly_tagged": len([a for a in tagged if a.taxonomy is not None]),
    }


@app.post("/api/analyze/playbook")
async def generate_playbook():
    """Run portfolio analysis and generate the creative playbook."""
    from engine.analysis.analyzer import CreativeAnalyzer
    analyzer = CreativeAnalyzer()
    ads = store.get_all_existing_ads()
    analysis = analyzer.analyze_portfolio(ads)
    playbook = analyzer.generate_playbook(ads, analysis)
    return {
        "analysis": analysis,
        "playbook_length": len(playbook),
        "playbook_path": "data/existing_creative/playbook.md",
    }


@app.get("/api/analyze/playbook")
async def get_playbook():
    """Get the latest playbook markdown."""
    playbook_path = Path("data/existing_creative/playbook.md")
    if not playbook_path.exists():
        raise HTTPException(status_code=404, detail="Playbook not yet generated")
    return {"playbook": playbook_path.read_text()}


@app.post("/api/analyze/generate")
async def generate_from_playbook():
    """Generate ads from playbook briefs using v2 pipeline + Gemini visuals."""
    from engine.analysis.analyzer import CreativeAnalyzer
    from engine.generation.generator import CreativeGenerator
    from engine.orchestrator import Orchestrator
    o = Orchestrator(store=store)
    result = o.generate_from_playbook()
    return result


@app.get("/api/existing-ads")
async def list_existing_ads(min_spend: float = 0):
    """List imported existing ads, optionally filtered by minimum spend."""
    ads = store.get_all_existing_ads()
    if min_spend > 0:
        ads = [a for a in ads if a.spend >= min_spend]
    return {
        "count": len(ads),
        "ads": [a.model_dump() for a in ads],
    }


@app.get("/api/review/history")
async def get_review_history():
    """Get all reviewed variants (approved + rejected) with feedback."""
    from engine.models import AdStatus
    approved = store.get_variants_by_status(AdStatus.APPROVED)
    rejected = store.get_variants_by_status(AdStatus.REJECTED)
    return {
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "approved": [
            {"id": v.id, "headline": v.headline, "reviewer": v.reviewer,
             "notes": v.review_notes, "reviewed_at": str(v.reviewed_at)}
            for v in approved
        ],
        "rejected": [
            {"id": v.id, "headline": v.headline, "reviewer": v.reviewer,
             "notes": v.review_notes, "reviewed_at": str(v.reviewed_at)}
            for v in rejected
        ],
    }


@app.get("/api/feedback")
async def get_rejection_feedback():
    """Get all rejection feedback for training generators."""
    return {"feedback": review_pipeline.get_rejection_feedback()}


# ---------------------------------------------------------------------------
# Asset health — fix stale paths on startup and on demand
# ---------------------------------------------------------------------------

def _heal_stale_asset_paths() -> dict:
    """
    Scan all variant JSONs. If asset_path points to a file that doesn't exist
    on disk, update the path to a .placeholder so the frontend handles it
    gracefully instead of showing a broken image icon.
    """
    all_variants = store.get_all_variants()
    fixed = 0
    for v in all_variants:
        p = Path(v.asset_path)
        if p.suffix == ".placeholder":
            continue
        if not p.exists():
            placeholder = p.with_suffix(".placeholder")
            placeholder.parent.mkdir(parents=True, exist_ok=True)
            placeholder.touch(exist_ok=True)
            v.asset_path = str(placeholder)
            store.save_variant(v)
            fixed += 1
    return {"scanned": len(all_variants), "fixed": fixed}


@app.on_event("startup")
async def startup_heal_assets():
    """Auto-heal stale asset paths when the server starts."""
    result = _heal_stale_asset_paths()
    if result["fixed"] > 0:
        print(f"[startup] Healed {result['fixed']} stale asset paths out of {result['scanned']} variants")


@app.post("/api/assets/heal")
async def heal_asset_paths():
    """Manually trigger stale asset path healing."""
    return _heal_stale_asset_paths()
