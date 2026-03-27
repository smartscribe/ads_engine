"""
Dashboard API — FastAPI backend for the review gallery and performance views.

Endpoints:
- GET  /api/review          — variants pending review (gallery data)
- POST /api/review/approve  — approve variant(s)
- POST /api/review/reject   — reject variant(s) with feedback
- POST /api/review/submit   — structured review submission (chips + duration)
- GET  /api/review/history  — reviewed variants with feedback
- GET  /api/feedback-chips  — chip taxonomy for the review UI
- GET  /api/template-preview/{variant_id} — rendered HTML for iframe preview
- GET  /api/scoreboard      — live ads ranked by CpFN
- GET  /api/learnings       — regression insights + reviewer impact
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

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine.store import Store
from engine.intake.parser import IntakeParser
from engine.generation.generator import CreativeGenerator
from engine.generation.template_renderer import TemplateRenderer
from engine.review.reviewer import ReviewPipeline
from engine.review.chips import chips_for_api
from engine.decisions.engine import DecisionEngine
from engine.regression.model import CreativeRegressionModel
from engine.notifications import SlackNotifier
from engine.models import ReviewFeedback, AdStatus

app = FastAPI(title="JotPsych Ads Engine", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # INTERN: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redirect convenience URLs → actual HTML files (must be before static mount)
@app.get("/dashboard/review")
async def redirect_review():
    return RedirectResponse(url="/dashboard/pages/review.html")

@app.get("/")
async def redirect_root():
    return RedirectResponse(url="/dashboard/pages/review.html")

# Serve the frontend at /dashboard
_frontend_dir = Path(__file__).parent.parent / "frontend"
app.mount("/dashboard", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")

# Serve generated creative assets at /data
_data_dir = Path(__file__).parent.parent.parent / "data"
_data_dir.mkdir(parents=True, exist_ok=True)
app.mount("/data", StaticFiles(directory=str(_data_dir)), name="data")

# Serve brand assets (fonts, logos) so iframe template previews can load them via HTTP
_brand_dir = Path(__file__).parent.parent.parent / "brand"
_brand_dir.mkdir(parents=True, exist_ok=True)
app.mount("/brand", StaticFiles(directory=str(_brand_dir)), name="brand")

# Initialize services
store = Store()
review_pipeline = ReviewPipeline(store)
decision_engine = DecisionEngine(store)
regression_model = CreativeRegressionModel(store)
notifier = SlackNotifier()
_template_renderer = TemplateRenderer()


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
    from engine.orchestrator import AdCampaignOrchestrator
    orchestrator = AdCampaignOrchestrator()
    result = orchestrator.submit_idea(idea.raw_text, source=idea.source)
    return result


class ConceptInput(BaseModel):
    concept: str
    num_variants: int = 20


@app.post("/api/intake/concept")
async def submit_concept(concept: ConceptInput):
    """
    Expand a high-level concept into 20 diverse creative briefs, then generate variants.
    Returns an SSE stream of progress events.
    """
    import json as _json
    import asyncio

    async def event_generator():
        try:
            from engine.intake.concept_expander import ConceptExpander
            from engine.orchestrator import AdCampaignOrchestrator
            from engine.generation.generator import CreativeGenerator
            from engine.memory.builder import MemoryBuilder

            expander = ConceptExpander()
            orchestrator = AdCampaignOrchestrator()
            generator = CreativeGenerator()
            memory_builder = MemoryBuilder(store)

            yield f"data: {_json.dumps({'event': 'start', 'concept': concept.concept})}\n\n"
            await asyncio.sleep(0)

            # Step 1: Expand concept to briefs
            yield f"data: {_json.dumps({'event': 'expanding', 'message': 'Expanding concept into briefs...'})}\n\n"
            await asyncio.sleep(0)
            briefs = expander.expand(concept.concept, num_variants=concept.num_variants)
            yield f"data: {_json.dumps({'event': 'briefs_ready', 'count': len(briefs)})}\n\n"
            await asyncio.sleep(0)

            # Step 2: Build generation context
            memory = memory_builder.build()
            context = memory_builder.build_generation_context(memory)

            # Step 3: Generate variants for each brief
            all_variant_ids = []
            for i, brief in enumerate(briefs):
                store.save_brief(brief)
                try:
                    variants = generator.generate_with_templates(
                        brief, use_v2=True, store=store, generation_context=context
                    )
                    for v in variants:
                        store.save_variant(v)
                        all_variant_ids.append(v.id)
                    yield f"data: {_json.dumps({'event': 'progress', 'completed': i+1, 'total': len(briefs), 'variants_so_far': len(all_variant_ids)})}\n\n"
                except Exception as e:
                    yield f"data: {_json.dumps({'event': 'brief_error', 'brief_index': i, 'error': str(e)})}\n\n"
                await asyncio.sleep(0)

            yield f"data: {_json.dumps({'event': 'done', 'total_variants': len(all_variant_ids), 'variant_ids': all_variant_ids})}\n\n"

        except Exception as e:
            yield f"data: {_json.dumps({'event': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class SwipeInput(BaseModel):
    url: Optional[str] = None
    notes: Optional[str] = None  # Optional manual description of the ad


@app.post("/api/intake/swipe")
async def ingest_swipe_file(
    swipe: Optional[SwipeInput] = None,
    image: Optional[UploadFile] = File(None),
):
    """
    Ingest a competitor or best-in-class ad as a stylistic reference.
    Accepts:
    - JSON body with url (Facebook Ad Library) or notes
    - multipart/form-data with an image file

    The ad is tagged with taxonomy and saved as ExistingAd with
    source='swipe_file' and exclude_from_regression=True.
    """
    from engine.analysis.analyzer import CreativeAnalyzer
    from engine.models import ExistingAd, Platform
    import uuid as _uuid

    analyzer = CreativeAnalyzer()

    # Build ad object from input
    headline = ""
    body = ""
    creative_type = "image"

    if image:
        # Image upload — use Claude vision to describe the creative
        image_bytes = await image.read()
        import base64
        from anthropic import Anthropic
        from config.settings import get_settings
        client = Anthropic(api_key=get_settings().ANTHROPIC_API_KEY)
        resp = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": image.content_type or "image/jpeg",
                            "data": base64.b64encode(image_bytes).decode(),
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Describe this ad creative. Extract: headline text, body copy, "
                            "visual style, and overall message. Return JSON: "
                            '{"headline": "...", "body": "...", "visual_description": "..."}'
                        ),
                    },
                ],
            }],
        )
        import json
        try:
            desc = json.loads(resp.content[0].text)
            headline = desc.get("headline", "")
            body = desc.get("body", desc.get("visual_description", ""))
        except Exception:
            body = resp.content[0].text[:500]

    elif swipe and swipe.url:
        # URL — attempt to scrape ad copy
        try:
            import requests as _requests
            from bs4 import BeautifulSoup
            r = _requests.get(swipe.url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            soup = BeautifulSoup(r.text, "html.parser")
            headline = (soup.find("h1") or soup.find("h2") or soup.new_tag("span")).get_text(strip=True)[:200]
            body = " ".join(p.get_text(strip=True) for p in soup.find_all("p")[:3])[:500]
        except Exception as e:
            headline = swipe.url
            body = swipe.notes or ""
    elif swipe and swipe.notes:
        body = swipe.notes

    if not headline and not body:
        raise HTTPException(status_code=400, detail="Provide url, image file, or notes")

    # Create the ExistingAd
    ad = ExistingAd(
        meta_ad_id=f"swipe_{str(_uuid.uuid4())[:8]}",
        ad_name=f"Swipe: {headline[:50] or body[:50]}",
        headline=headline,
        body=body,
        platform=Platform.META,
        source="swipe_file",
        exclude_from_regression=True,
    )

    # Tag with taxonomy
    tagged = analyzer.tag_ads([ad], store, batch_size=1)
    tagged_ad = tagged[0] if tagged else ad

    return {
        "ad_id": tagged_ad.id,
        "headline": tagged_ad.headline,
        "body": tagged_ad.body,
        "taxonomy": tagged_ad.taxonomy.model_dump() if tagged_ad.taxonomy else None,
        "source": tagged_ad.source,
        "exclude_from_regression": tagged_ad.exclude_from_regression,
    }


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

@app.get("/api/review")
async def get_review_queue():
    """Get all variants pending review, with asset_status for three-tier rendering."""
    pending = review_pipeline.get_pending_review()
    variants_out = []
    for v in pending:
        asset_p = Path(v.asset_path) if v.asset_path else None

        # Only show variants with a real image file on disk
        has_image = (
            asset_p is not None
            and asset_p.suffix in (".png", ".jpg", ".jpeg", ".webp")
            and asset_p.exists()
            and asset_p.stat().st_size > 1024
        )

        if has_image:
            d = v.model_dump()
            d["asset_status"] = "rendered"
            variants_out.append(d)
        elif v.template_id:
            d = v.model_dump()
            d["asset_status"] = "template_available"
            variants_out.append(d)

    return {
        "count": len(variants_out),
        "variants": variants_out,
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


@app.post("/api/review/submit")
async def submit_review(feedback: ReviewFeedback):
    """
    Submit a structured review from the dashboard.
    Verdict is recorded immediately. Chips and freeform note are optional enrichment.
    """
    try:
        variant = review_pipeline.submit_review(feedback)
        return {
            "variant_id": variant.id,
            "status": variant.status.value,
            "chips_recorded": len(variant.review_chips),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Variant {feedback.variant_id} not found")


@app.get("/api/feedback-chips")
async def get_feedback_chips():
    """Return the chip taxonomy for the review UI."""
    return chips_for_api()


@app.get("/api/template-preview/{variant_id}", response_class=HTMLResponse)
async def get_template_preview(variant_id: str):
    """
    Return fully-substituted HTML for a variant's template.
    Embedded in an iframe in the review dashboard so ads display even without
    a rendered screenshot. Fonts and logos are served via /brand/ HTTP paths.
    """
    try:
        variant = store.get_variant(variant_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Variant not found")

    template_id = variant.template_id
    color_scheme = variant.template_color_scheme or "light"

    if not template_id:
        # Fall back to a generic feed template if none is stored on the variant
        template_id = "feed_1080x1080/headline_hero"

    try:
        html = _template_renderer.render_to_html(
            headline=variant.headline,
            body=variant.primary_text,
            cta=variant.cta_button,
            template=template_id,
            color_scheme=color_scheme,
            brand_base_url="/brand",
        )
        return HTMLResponse(content=html)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Template render failed: {exc}")


@app.get("/api/scoreboard")
async def get_scoreboard():
    """
    Live ads leaderboard ranked by cost-per-first-note (ascending = better).
    Returns LIVE and GRADUATED variants with their latest performance snapshot.
    """
    live_variants = store.get_variants_by_status(AdStatus.LIVE)
    graduated_variants = store.get_variants_by_status(AdStatus.GRADUATED)
    all_active = live_variants + graduated_variants

    if not all_active:
        return {"entries": [], "portfolio_avg_cpfn": None}

    entries = []
    total_spend = 0.0
    total_notes = 0

    for v in all_active:
        snapshots = store.get_snapshots_for_variant(v.id)
        if not snapshots:
            continue

        v_spend = sum(s.spend for s in snapshots)
        v_notes = sum(s.first_note_completions for s in snapshots)
        v_cpfn = v_spend / v_notes if v_notes > 0 else None
        total_spend += v_spend
        total_notes += v_notes

        # Simple trend: compare last 3 days CpFN vs overall
        sorted_snaps = sorted(snapshots, key=lambda s: s.date)
        recent = sorted_snaps[-3:] if len(sorted_snaps) >= 3 else sorted_snaps
        recent_spend = sum(s.spend for s in recent)
        recent_notes = sum(s.first_note_completions for s in recent)
        recent_cpfn = recent_spend / recent_notes if recent_notes > 0 else None

        if v_cpfn and recent_cpfn:
            if recent_cpfn < v_cpfn * 0.9:
                trend = "improving"
            elif recent_cpfn > v_cpfn * 1.1:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "unknown"

        decisions = store.get_decisions_for_variant(v.id)
        latest_decision = decisions[-1].verdict.value if decisions else None

        entries.append({
            "variant_id": v.id,
            "headline": v.headline,
            "status": v.status.value,
            "platform": v.taxonomy.platform.value if v.taxonomy else None,
            "format": v.taxonomy.format.value if v.taxonomy else None,
            "total_spend": round(v_spend, 2),
            "total_notes": v_notes,
            "cpfn": round(v_cpfn, 2) if v_cpfn else None,
            "trend": trend,
            "days_live": len(set(s.date for s in snapshots)),
            "latest_decision": latest_decision,
        })

    # Sort by CpFN ascending (lower = better), None last
    entries.sort(key=lambda e: (e["cpfn"] is None, e["cpfn"] or 0))

    portfolio_avg_cpfn = round(total_spend / total_notes, 2) if total_notes > 0 else None

    return {
        "entries": entries,
        "portfolio_avg_cpfn": portfolio_avg_cpfn,
        "total_active": len(entries),
    }


@app.get("/api/learnings")
async def get_learnings(reviewer: Optional[str] = None):
    """
    Creative insights for the Learnings dashboard view:
    - Regression-derived playbook rules (plain English)
    - Structured feedback aggregates from chip selections
    - Reviewer impact stats (if reviewer param supplied)
    """
    # Playbook rules from regression
    try:
        playbook = regression_model.get_creative_playbook()
        playbook_rules = playbook.get("rules", []) if isinstance(playbook, dict) else []
    except Exception:
        playbook_rules = []

    # Creative memory summary
    memory = store.load_memory()
    memory_summary = {}
    if memory:
        memory_summary = {
            "winning_patterns": len(memory.winning_patterns),
            "fatigue_alerts": [
                {"feature": a.feature, "delta_pct": a.delta_pct}
                for a in memory.fatigue_alerts[:3]
            ],
            "total_analyzed": memory.total_variants_analyzed,
            "last_regression": memory.last_regression_date.isoformat() if memory.last_regression_date else None,
        }

    # Structured chip feedback aggregates
    chip_aggregates = review_pipeline.get_structured_feedback()

    # Reviewer impact (optional)
    reviewer_impact = None
    if reviewer:
        reviewer_impact = review_pipeline.get_reviewer_impact(reviewer)

    return {
        "playbook_rules": playbook_rules,
        "memory_summary": memory_summary,
        "chip_aggregates": chip_aggregates,
        "reviewer_impact": reviewer_impact,
    }


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
    """
    Get the latest regression playbook with model health diagnostics.
    Includes bootstrap CIs, confidence tiers, and overfit risk assessment.
    """
    playbook = regression_model.get_creative_playbook()

    # Enrich with validation diagnostics when available
    latest = store.get_latest_regression()
    if latest:
        n_features = len(latest.coefficients)
        n_obs = latest.n_observations
        model_health = {
            "overfit_risk": n_obs < n_features * 5,
            "sample_ratio": round(n_obs / max(n_features, 1), 2),
            "test_r_squared": latest.test_r_squared,
            "train_r_squared": latest.r_squared,
            "validation_run": bool(latest.confidence_tiers),
            "trust_guidance": (
                "coefficients_reliable"
                if latest.test_r_squared is not None and latest.test_r_squared >= 0.15
                else (
                    "fallback_to_editorial"
                    if latest.test_r_squared is not None
                    else "no_validation_run"
                )
            ),
        }
        playbook["model_health"] = model_health

        # Include bootstrap CIs and confidence tiers for top features
        top_features = (
            latest.top_positive_features[:5] + latest.top_negative_features[:5]
        )
        validation_detail = {}
        for feat in top_features:
            detail: dict = {}
            if feat in latest.confidence_tiers:
                detail["confidence_tier"] = latest.confidence_tiers[feat]
            if feat in latest.bootstrap_ci:
                ci = latest.bootstrap_ci[feat]
                detail["bootstrap_ci"] = {
                    "point": ci[0], "lower": ci[1], "upper": ci[2]
                }
            if feat in latest.coefficient_stability:
                detail["stability_std"] = latest.coefficient_stability[feat]
            if detail:
                validation_detail[feat] = detail
        if validation_detail:
            playbook["validation_detail"] = validation_detail

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
# Memory endpoints (M2, M3)
# ---------------------------------------------------------------------------

class VoiceNoteSynthesizeRequest(BaseModel):
    reviewer: Optional[str] = None


@app.post("/api/review/voice-note")
async def upload_voice_note(
    reviewer: str = "unknown",
    audio: UploadFile = File(...),
):
    """
    Upload a review session voice note. Transcribes via OpenAI Whisper and
    stores alongside a transcript JSON file.
    (M2) — used for weekly review sessions with Nate + Jackson.
    """
    import json as _json
    from pathlib import Path

    try:
        from openai import OpenAI
        from config.settings import get_settings
        settings = get_settings()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI not configured: {e}")

    voice_dir = Path("data/memory/voice_notes")
    voice_dir.mkdir(parents=True, exist_ok=True)

    audio_bytes = await audio.read()
    audio_filename = f"{reviewer}_{audio.filename}"
    audio_path = voice_dir / audio_filename
    audio_path.write_bytes(audio_bytes)

    # Transcribe via Whisper
    try:
        client_oa = OpenAI(api_key=getattr(settings, "OPENAI_API_KEY", None))
        with open(audio_path, "rb") as f:
            transcript_resp = client_oa.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="text",
            )
        transcript = str(transcript_resp)
    except Exception as e:
        transcript = f"[transcription failed: {e}]"

    # Save transcript JSON
    transcript_path = voice_dir / f"{audio_filename}.transcript.json"
    transcript_path.write_text(_json.dumps({
        "reviewer": reviewer,
        "audio_file": audio_filename,
        "transcript": transcript,
        "uploaded_at": str(date.today()),
    }, indent=2))

    return {
        "audio_file": audio_filename,
        "transcript_length": len(transcript),
        "transcript_preview": transcript[:200] + "..." if len(transcript) > 200 else transcript,
    }


@app.post("/api/review/synthesize-preferences")
async def synthesize_reviewer_preferences(req: VoiceNoteSynthesizeRequest = None):
    """
    Synthesize reviewer preferences from all voice note transcripts and written
    review notes. Runs a Claude call to extract ReviewerPreference objects.
    (M2) — run after each weekly review session, not per note.
    """
    import json as _json
    from pathlib import Path
    from anthropic import Anthropic
    from config.settings import get_settings

    voice_dir = Path("data/memory/voice_notes")
    voice_dir.mkdir(parents=True, exist_ok=True)

    # Load all transcripts
    transcripts = []
    for tf in voice_dir.glob("*.transcript.json"):
        try:
            data = _json.loads(tf.read_text())
            transcripts.append(data)
        except Exception:
            pass

    # Load structured review feedback
    feedback_summary = review_pipeline.get_structured_feedback()

    if not transcripts and not feedback_summary.get("total_reviews", 0):
        return {"error": "No voice notes or review feedback found to synthesize from"}

    prompt_parts = [
        "You are synthesizing reviewer preferences for a JotPsych ad creative team.\n\n",
        f"REVIEW FEEDBACK SUMMARY:\n{_json.dumps(feedback_summary, indent=2)}\n\n",
    ]

    if transcripts:
        prompt_parts.append("VOICE NOTE TRANSCRIPTS:\n")
        for t in transcripts:
            prompt_parts.append(
                f"--- {t.get('reviewer', 'unknown')} ---\n"
                f"{t.get('transcript', '')}\n\n"
            )

    prompt_parts.append(
        "Extract structured reviewer preferences as a JSON array:\n"
        "[\n"
        "  {\n"
        '    "reviewer": "name",\n'
        '    "dimension": "hook_type|tone|visual_style|message_type|etc",\n'
        '    "rule": "clear one-sentence rule",\n'
        '    "example": "specific example if mentioned",\n'
        '    "confidence": "high|moderate|tentative",\n'
        '    "direction": "prefer|avoid"\n'
        "  },\n"
        "  ...\n"
        "]\n\n"
        "Focus on actionable patterns, not one-off opinions."
    )

    settings = get_settings()
    client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    try:
        resp = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            messages=[{"role": "user", "content": "".join(prompt_parts)}],
        )
        raw = resp.content[0].text
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        preferences = _json.loads(raw.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {e}")

    # Save synthesized preferences
    synth_path = voice_dir / "synthesized.json"
    synth_path.write_text(_json.dumps({
        "synthesized_at": str(date.today()),
        "source_transcripts": len(transcripts),
        "preferences": preferences,
    }, indent=2))

    return {
        "preferences_extracted": len(preferences),
        "source_transcripts": len(transcripts),
        "preferences": preferences,
    }


@app.get("/api/memory/status")
async def get_memory_status():
    """
    Memory health report: age, pattern count, confidence distribution, archived count.
    (M3)
    """
    return store.get_memory_status()


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
