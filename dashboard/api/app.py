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
    allow_origins=["*"],  # TODO: restrict to dashboard origin in production
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
    creative_direction: Optional[str] = None


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
    from engine.orchestrator import Orchestrator
    orchestrator = Orchestrator(store=store)
    result = orchestrator.submit_idea(
        idea.raw_text,
        source=idea.source,
        creative_direction=idea.creative_direction,
    )
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
            from engine.orchestrator import Orchestrator
            from engine.generation.generator import CreativeGenerator
            from engine.memory.builder import MemoryBuilder

            expander = ConceptExpander()
            orchestrator = Orchestrator()
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
                        brief, use_v2=True, store=store, generation_context=context,
                        use_selector=True,
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
    If a freeform note is provided, extracts testable hypothesis candidates.
    """
    try:
        variant = review_pipeline.submit_review(feedback)
        result = {
            "variant_id": variant.id,
            "status": variant.status.value,
            "chips_recorded": len(variant.review_chips),
        }

        if feedback.freeform_note and len(feedback.freeform_note.strip()) > 15:
            try:
                from engine.tracking.hypothesis_extractor import HypothesisExtractor, FEATURE_LABELS
                extractor = HypothesisExtractor()
                candidates = extractor.extract(
                    feedback.freeform_note,
                    context=f"Review feedback ({feedback.verdict}) on ad variant",
                )
                for c in candidates:
                    c["feature_labels"] = [
                        FEATURE_LABELS.get(f, f.replace("_", " "))
                        for f in c.get("related_features", [])
                    ]
                if candidates:
                    result["suggested_hypotheses"] = candidates
            except Exception:
                pass

        return result
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

    When a variant has no template_id stored, derives one from its taxonomy
    using the TemplateSelector so different ads look visually distinct.
    """
    try:
        variant = store.get_variant(variant_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Variant not found")

    template_id = variant.template_id
    color_scheme = variant.template_color_scheme or "light"

    if not template_id:
        # Use TemplateSelector to pick a template based on taxonomy, not a static fallback
        from engine.generation.template_selector import TemplateSelector
        selector = TemplateSelector()
        taxonomy = variant.taxonomy.model_dump() if variant.taxonomy else {}
        plan = selector.select(taxonomy)
        template_id = plan.template
        color_scheme = plan.color_scheme

    # Build extra context for special templates (stat_callout, testimonial, etc.)
    context = {}
    if "stat_callout" in template_id:
        # Try to extract a number from the headline for the stat display
        import re
        nums = re.findall(r'\d+', variant.headline or "")
        context["stat_number"] = nums[0] if nums else "2"
        context["stat_unit"] = "hours saved\nper day"
    if "testimonial" in template_id:
        context["attribution"] = "Behavioral Health Clinician"

    try:
        html = _template_renderer.render_to_html(
            headline=variant.headline,
            body=variant.primary_text,
            cta=variant.cta_button,
            template=template_id,
            color_scheme=color_scheme,
            brand_base_url="/brand",
            context=context,
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


# ---------------------------------------------------------------------------
# Performance Dashboard (P1.2)
# ---------------------------------------------------------------------------

@app.get("/api/performance/dashboard")
async def performance_dashboard():
    """
    Aggregated performance data for all deployed/active variants.
    Returns per-variant metrics with sparkline data and summary stats.
    """
    from collections import defaultdict

    # Load all variants that have been deployed (any status post-review)
    deployed_statuses = [AdStatus.LIVE, AdStatus.GRADUATED, AdStatus.PAUSED, AdStatus.KILLED]
    all_variants = []
    for status in deployed_statuses:
        all_variants.extend(store.get_variants_by_status(status))

    if not all_variants:
        return {
            "variants": [],
            "summary": {
                "total_active": 0,
                "total_daily_spend": 0,
                "avg_cpfn": None,
                "best_performer": None,
                "worst_performer": None,
            },
        }

    variant_data = []
    total_spend = 0.0
    total_notes = 0

    for v in all_variants:
        snapshots = store.get_snapshots_for_variant(v.id)
        if not snapshots:
            continue

        v_spend = sum(s.spend for s in snapshots)
        v_impressions = sum(s.impressions for s in snapshots)
        v_clicks = sum(s.clicks for s in snapshots)
        v_notes = sum(s.first_note_completions for s in snapshots)
        v_cpfn = round(v_spend / v_notes, 2) if v_notes > 0 else None
        v_ctr = round(v_clicks / v_impressions, 4) if v_impressions > 0 else 0
        days_running = len(set(s.date.isoformat() if hasattr(s.date, 'isoformat') else str(s.date) for s in snapshots))

        total_spend += v_spend
        total_notes += v_notes

        # Build sparkline data (last 7 days)
        sorted_snaps = sorted(snapshots, key=lambda s: str(s.date))
        daily = defaultdict(lambda: {"spend": 0.0, "notes": 0})
        for s in sorted_snaps:
            d = s.date.isoformat() if hasattr(s.date, 'isoformat') else str(s.date)
            daily[d]["spend"] += s.spend
            daily[d]["notes"] += s.first_note_completions

        dates_sorted = sorted(daily.keys())[-7:]
        sparkline_spend = [round(daily[d]["spend"], 2) for d in dates_sorted]
        sparkline_cpfn = []
        for d in dates_sorted:
            if daily[d]["notes"] > 0:
                sparkline_cpfn.append(round(daily[d]["spend"] / daily[d]["notes"], 2))
            else:
                sparkline_cpfn.append(None)

        # Trend: compare recent 3 days vs overall
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

        # Latest decision
        decisions = store.get_decisions_for_variant(v.id)
        latest_verdict = decisions[-1].verdict.value if decisions else None

        # Asset thumbnail
        asset_p = Path(v.asset_path) if v.asset_path else None
        has_thumb = (
            asset_p is not None
            and asset_p.suffix in (".png", ".jpg", ".jpeg", ".webp")
            and asset_p.exists()
            and asset_p.stat().st_size > 1024
        )

        variant_data.append({
            "variant_id": v.id,
            "headline": v.headline,
            "status": v.status.value if hasattr(v.status, 'value') else str(v.status),
            "thumbnail_url": f"/data/creatives/rendered/{asset_p.name}" if has_thumb else None,
            "spend": round(v_spend, 2),
            "impressions": v_impressions,
            "clicks": v_clicks,
            "conversions": v_notes,
            "cpfn": v_cpfn,
            "ctr": v_ctr,
            "days_running": days_running,
            "trend": trend,
            "sparkline_spend": sparkline_spend,
            "sparkline_cpfn": sparkline_cpfn,
            "latest_verdict": latest_verdict,
        })

    # Sort by CpFN ascending (lower = better), None last
    variant_data.sort(key=lambda e: (e["cpfn"] is None, e["cpfn"] or 0))

    # Summary stats
    avg_cpfn = round(total_spend / total_notes, 2) if total_notes > 0 else None
    with_cpfn = [v for v in variant_data if v["cpfn"] is not None]
    best = min(with_cpfn, key=lambda v: v["cpfn"]) if with_cpfn else None
    worst = max(with_cpfn, key=lambda v: v["cpfn"]) if with_cpfn else None

    active_count = len([v for v in variant_data if v["status"] in ("live", "graduated")])

    return {
        "variants": variant_data,
        "summary": {
            "total_active": active_count,
            "total_daily_spend": round(total_spend / max(1, len(set(
                s.date.isoformat() if hasattr(s.date, 'isoformat') else str(s.date)
                for v in all_variants
                for s in store.get_snapshots_for_variant(v.id)
            ))), 2) if total_spend > 0 else 0,
            "avg_cpfn": avg_cpfn,
            "best_performer": {"id": best["variant_id"], "headline": best["headline"], "cpfn": best["cpfn"]} if best else None,
            "worst_performer": {"id": worst["variant_id"], "headline": worst["headline"], "cpfn": worst["cpfn"]} if worst else None,
        },
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


class DecisionAction(BaseModel):
    variant_id: str
    action: str  # "kill" | "scale" | "pause" | "resume"


@app.post("/api/decisions/act")
async def act_on_decision(body: DecisionAction):
    """
    Execute a scale/kill/pause/resume action on a variant.
    Updates variant status and optionally calls the Meta deployer.
    """
    try:
        variant = store.get_variant(body.variant_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Variant {body.variant_id} not found")

    action = body.action.lower()
    if action not in ("kill", "scale", "pause", "resume"):
        raise HTTPException(status_code=400, detail=f"Invalid action: {action}. Must be kill, scale, pause, or resume.")

    # Update variant status
    if action == "kill":
        variant.status = AdStatus.KILLED
    elif action == "scale":
        variant.status = AdStatus.GRADUATED
    elif action == "pause":
        variant.status = AdStatus.PAUSED
    elif action == "resume":
        variant.status = AdStatus.LIVE

    store.save_variant(variant)

    # Try to update on Meta if we have credentials and a meta_ad_id
    platform_result = None
    if variant.meta_ad_id:
        try:
            from config.settings import get_settings
            settings = get_settings()
            if settings.META_ACCESS_TOKEN and settings.META_AD_ACCOUNT_ID:
                meta = MetaDeployer(
                    settings.META_ACCESS_TOKEN,
                    settings.META_AD_ACCOUNT_ID,
                    page_id=getattr(settings, "META_PAGE_ID", ""),
                )
                if action in ("kill", "pause"):
                    meta.pause_ad(variant.meta_ad_id)
                    platform_result = "paused_on_meta"
                elif action == "resume":
                    meta.resume_ad(variant.meta_ad_id)
                    platform_result = "resumed_on_meta"
        except Exception as e:
            platform_result = f"platform_error: {e}"

    # Notify via Slack
    notifier.notify_deployment(
        [variant],
        f"Action: {action.upper()}"
    )

    return {
        "variant_id": variant.id,
        "new_status": variant.status.value if hasattr(variant.status, 'value') else str(variant.status),
        "action": action,
        "platform_result": platform_result,
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


@app.get("/api/regression/coefficients")
async def regression_coefficients():
    """
    Return all regression coefficients with human-readable names,
    confidence tiers, bootstrap CIs, and directional indicators.
    Used by the insights dashboard for the coefficient bar chart.
    """
    from engine.memory.playbook_translator import FEATURE_DESCRIPTIONS

    latest = store.get_latest_regression()
    if not latest:
        return {"coefficients": [], "model_health": None}

    coefficients = []
    for feature, coeff in latest.coefficients.items():
        tier = latest.confidence_tiers.get(feature, "unreliable")
        p_val = latest.p_values.get(feature, 1.0)
        ci = latest.bootstrap_ci.get(feature)
        stability = latest.coefficient_stability.get(feature)

        coefficients.append({
            "feature": feature,
            "label": FEATURE_DESCRIPTIONS.get(feature, feature.replace("_", " ").title()),
            "coefficient": round(coeff, 4),
            "p_value": round(p_val, 6),
            "confidence_tier": tier,
            "bootstrap_ci": {
                "point": round(ci[0], 4),
                "lower": round(ci[1], 4),
                "upper": round(ci[2], 4),
            } if ci else None,
            "stability_std": round(stability, 4) if stability is not None else None,
            "direction": "good" if coeff < 0 else "bad",  # negative coeff = lower CpFN = good
        })

    # Sort by absolute magnitude descending
    coefficients.sort(key=lambda c: abs(c["coefficient"]), reverse=True)

    model_health = {
        "r_squared": round(latest.r_squared, 4),
        "adjusted_r_squared": round(latest.adjusted_r_squared, 4),
        "test_r_squared": round(latest.test_r_squared, 4) if latest.test_r_squared is not None else None,
        "n_observations": latest.n_observations,
        "n_features": len(latest.coefficients),
        "durbin_watson": round(latest.durbin_watson, 4),
        "condition_number": round(latest.condition_number, 2),
        "sample_ratio": round(latest.n_observations / max(len(latest.coefficients), 1), 2),
        "overfit_risk": latest.n_observations < len(latest.coefficients) * 5,
        "run_date": latest.run_date.isoformat(),
    }

    return {
        "coefficients": coefficients,
        "model_health": model_health,
        "tier_counts": {
            "high": len([c for c in coefficients if c["confidence_tier"] == "high"]),
            "moderate": len([c for c in coefficients if c["confidence_tier"] == "moderate"]),
            "directional": len([c for c in coefficients if c["confidence_tier"] == "directional"]),
            "unreliable": len([c for c in coefficients if c["confidence_tier"] == "unreliable"]),
        },
    }


@app.get("/api/regression/playbook-rules")
async def regression_playbook_rules():
    """
    Return translated playbook rules (natural language generation instructions).
    """
    from engine.memory.playbook_translator import PlaybookTranslator

    latest = store.get_latest_regression()
    if not latest:
        return {"rules": [], "status": "no_regression_data"}

    try:
        translator = PlaybookTranslator(store)
        rules = translator.translate(latest)
        return {
            "rules": [
                {
                    "feature": r.feature,
                    "direction": r.direction,
                    "confidence": r.confidence,
                    "rule": r.rule,
                    "good_examples": r.good_examples,
                    "bad_examples": getattr(r, "bad_examples", []),
                }
                for r in rules
            ],
            "count": len(rules),
        }
    except Exception as e:
        return {"rules": [], "status": f"translation_error: {e}"}


@app.get("/api/regression/fatigue")
async def regression_fatigue():
    """
    Return fatigue alerts from memory — features whose recent coefficients
    are degrading compared to historical performance.
    """
    memory = store.load_memory_v2()
    if not memory:
        return {"alerts": []}

    from engine.memory.playbook_translator import FEATURE_DESCRIPTIONS

    alerts = []
    if hasattr(memory, 'statistical') and hasattr(memory.statistical, 'fatiguing_patterns'):
        for alert in memory.statistical.fatiguing_patterns:
            alerts.append({
                "feature": alert.feature,
                "label": FEATURE_DESCRIPTIONS.get(alert.feature, alert.feature.replace("_", " ").title()),
                "current_coefficient": round(alert.current_coefficient, 4),
                "historical_avg": round(alert.historical_avg, 4),
                "delta_pct": round(alert.delta_pct, 2),
                "deployments": alert.deployments,
                "recommendation": alert.recommendation,
            })

    return {"alerts": alerts}


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
# Bulk Creative Export
# ---------------------------------------------------------------------------

@app.get("/api/variants/export")
async def export_variants(status: str = "approved"):
    """
    Download approved (or other status) variants as a ZIP file.
    ZIP contains PNGs organized by format folder + a copy.csv with metadata.
    Bridge for manual upload while programmatic deploy is being tested.
    """
    import csv
    import io
    import zipfile

    variants = store.get_variants_by_status(status)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Build CSV in memory
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow([
            "variant_id", "headline", "body", "cta", "hook_type",
            "message_type", "tone", "template_id", "format", "asset_file",
        ])

        for v in variants:
            # Determine format folder from template_id
            fmt_folder = "other"
            if v.template_id:
                parts = v.template_id.split("/")
                fmt_folder = parts[0] if parts else "other"

            # Check if the variant has a valid rendered PNG
            asset_p = Path(v.asset_path) if v.asset_path else None
            asset_filename = ""
            if (
                asset_p is not None
                and asset_p.suffix in (".png", ".jpg", ".jpeg", ".webp")
                and asset_p.exists()
                and asset_p.stat().st_size > 1024
            ):
                asset_filename = f"{fmt_folder}/{v.id}{asset_p.suffix}"
                zf.write(str(asset_p), asset_filename)

            # Extract taxonomy fields
            hook = v.taxonomy.hook_type if v.taxonomy else ""
            msg = v.taxonomy.message_type if v.taxonomy else ""
            tone = v.taxonomy.tone if v.taxonomy else ""

            writer.writerow([
                v.id,
                v.headline,
                v.primary_text,
                v.cta_button,
                hook,
                msg,
                tone,
                v.template_id or "",
                fmt_folder,
                asset_filename,
            ])

        zf.writestr("copy.csv", csv_buf.getvalue())

    buf.seek(0)
    today = date.today().isoformat()
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{status}_creatives_{today}.zip"'
        },
    )


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


class MonologueInput(BaseModel):
    text: str
    reviewer: str
    variant_ids: Optional[list[str]] = None


class MonologueRegenerateInput(BaseModel):
    monologue_id: str
    additional_direction: Optional[str] = None


@app.post("/api/review/monologue")
async def submit_monologue(body: MonologueInput):
    """
    Parse a freeform review monologue into per-variant verdicts
    and global creative directions. Applies verdicts immediately.
    """
    import json as _json

    from engine.review.monologue_parser import MonologueParser

    # Load variants to review
    if body.variant_ids:
        variants_raw = [store.get_variant(vid) for vid in body.variant_ids]
    else:
        variants_raw = review_pipeline.get_pending_review()

    if not variants_raw:
        raise HTTPException(status_code=400, detail="No variants to review")

    variants_for_parser = [
        {
            "id": v.id,
            "headline": v.headline,
            "body": v.primary_text,
            "cta": v.cta_button,
            "taxonomy": {
                "message_type": v.taxonomy.message_type,
                "hook_type": v.taxonomy.hook_type,
                "tone": v.taxonomy.tone,
            } if v.taxonomy else None,
        }
        for v in variants_raw
    ]

    parser = MonologueParser()
    result = parser.parse(body.text, variants_for_parser, reviewer=body.reviewer)

    # Apply verdicts via review pipeline
    applied = []
    for verdict in result.verdicts:
        if verdict.verdict == "skip":
            applied.append({"variant_id": verdict.variant_id, "action": "skipped"})
            continue
        feedback = ReviewFeedback(
            variant_id=verdict.variant_id,
            reviewer=body.reviewer,
            verdict="approved" if verdict.verdict == "approve" else "rejected",
            freeform_note=verdict.reason,
        )
        try:
            review_pipeline.submit_review(feedback)
            applied.append({"variant_id": verdict.variant_id, "action": verdict.verdict})
        except FileNotFoundError:
            applied.append({"variant_id": verdict.variant_id, "action": "not_found"})

    # Persist monologue
    monologue_dir = Path("data/memory/monologues")
    monologue_dir.mkdir(parents=True, exist_ok=True)
    monologue_path = monologue_dir / f"{result.monologue_id}.json"
    monologue_path.write_text(_json.dumps(result.to_dict(), indent=2))

    response = {
        "monologue_id": result.monologue_id,
        "verdicts": [
            {"variant_id": v.variant_id, "verdict": v.verdict, "reason": v.reason}
            for v in result.verdicts
        ],
        "global_directions": result.global_directions,
        "applied": applied,
    }

    if result.global_directions:
        try:
            from engine.tracking.hypothesis_extractor import HypothesisExtractor, FEATURE_LABELS
            extractor = HypothesisExtractor()
            directions_text = "\n".join(result.global_directions)
            candidates = extractor.extract(directions_text, context="Monologue review global directions")
            for c in candidates:
                c["feature_labels"] = [
                    FEATURE_LABELS.get(f, f.replace("_", " "))
                    for f in c.get("related_features", [])
                ]
            if candidates:
                response["suggested_hypotheses"] = candidates
        except Exception:
            pass

    return response


@app.post("/api/review/monologue-regenerate")
async def regenerate_from_monologue(body: MonologueRegenerateInput):
    """
    Regenerate ad variants using creative directions extracted from a monologue.
    """
    import json as _json

    monologue_path = Path("data/memory/monologues") / f"{body.monologue_id}.json"
    if not monologue_path.exists():
        raise HTTPException(status_code=404, detail="Monologue not found")

    data = _json.loads(monologue_path.read_text())
    directions = data.get("global_directions", [])

    # Collect rejection reasons as additional context
    rejection_reasons = [
        v["reason"]
        for v in data.get("verdicts", [])
        if v.get("verdict") == "reject" and v.get("reason")
    ]

    direction_text = "Creative direction from review monologue:\n"
    for d in directions:
        direction_text += f"- {d}\n"
    if rejection_reasons:
        direction_text += "\nRejected ad patterns to avoid:\n"
        for r in rejection_reasons[:5]:
            direction_text += f"- {r}\n"
    if body.additional_direction:
        direction_text += f"\nAdditional direction: {body.additional_direction}\n"

    from engine.orchestrator import Orchestrator
    orchestrator = Orchestrator(store=store)
    result = orchestrator.submit_idea(
        raw_text=direction_text,
        source="monologue_regenerate",
        creative_direction=direction_text,
    )
    return result


class CreativeDirectionInput(BaseModel):
    text: str
    added_by: str


class CreativeDirectionUpdate(BaseModel):
    active: Optional[bool] = None


@app.get("/api/memory/creative-directions")
async def list_creative_directions():
    """List all creative directions (active + inactive)."""
    from engine.memory.models import CreativeMemory as CreativeMemoryV2
    memory = store.load_memory()
    if not memory or not hasattr(memory, "creative_directions"):
        return {"directions": [], "active_count": 0}
    directions = []
    for d in memory.creative_directions:
        directions.append({
            "id": d.id,
            "text": d.text,
            "added_by": d.added_by,
            "added_at": d.added_at.isoformat() if d.added_at else None,
            "active": d.active,
            "source": d.source,
            "source_id": d.source_id,
        })
    return {
        "directions": directions,
        "active_count": len([d for d in directions if d["active"]]),
    }


@app.post("/api/memory/creative-directions")
async def add_creative_direction(body: CreativeDirectionInput):
    """Add a new creative direction that persists across generation cycles."""
    from engine.memory.models import CreativeDirection, CreativeMemory as CreativeMemoryV2
    from engine.memory.builder import MemoryBuilder

    direction = CreativeDirection(
        text=body.text,
        added_by=body.added_by,
    )

    memory = store.load_memory()
    if memory and hasattr(memory, "creative_directions"):
        memory.creative_directions.append(direction)
    else:
        builder = MemoryBuilder(store)
        memory = builder.build()
        memory.creative_directions.append(direction)

    store.save_memory(memory)
    return {
        "id": direction.id,
        "text": direction.text,
        "added_by": direction.added_by,
        "active": direction.active,
    }


@app.patch("/api/memory/creative-directions/{direction_id}")
async def update_creative_direction(direction_id: str, body: CreativeDirectionUpdate):
    """Activate or deactivate a creative direction."""
    memory = store.load_memory()
    if not memory or not hasattr(memory, "creative_directions"):
        raise HTTPException(status_code=404, detail="No creative directions found")

    for d in memory.creative_directions:
        if d.id == direction_id:
            if body.active is not None:
                d.active = body.active
            store.save_memory(memory)
            return {"id": d.id, "active": d.active}

    raise HTTPException(status_code=404, detail=f"Direction {direction_id} not found")


@app.get("/api/memory/status")
async def get_memory_status():
    """
    Memory health report: age, pattern count, confidence distribution, archived count.
    (M3)
    """
    return store.get_memory_status()


# ---------------------------------------------------------------------------
# Hypotheses
# ---------------------------------------------------------------------------

class HypothesisInput(BaseModel):
    hypothesis_text: str
    created_by: str
    related_features: list[str] = []


class HypothesisUpdate(BaseModel):
    status: Optional[str] = None
    evidence: Optional[str] = None


@app.get("/api/hypotheses")
async def list_hypotheses(status: Optional[str] = None):
    """List all hypotheses, optionally filtered by status."""
    from engine.models import HypothesisStatus
    hypotheses = store.load_hypotheses()
    if status:
        try:
            filter_status = HypothesisStatus(status)
            hypotheses = [h for h in hypotheses if h.status == filter_status]
        except ValueError:
            pass
    return {
        "count": len(hypotheses),
        "hypotheses": [h.model_dump() for h in hypotheses],
    }


@app.post("/api/hypotheses")
async def create_hypothesis(body: HypothesisInput):
    """Create a new creative hypothesis."""
    from engine.models import CreativeHypothesis
    hypothesis = CreativeHypothesis(
        hypothesis_text=body.hypothesis_text,
        created_by=body.created_by,
        related_features=body.related_features,
    )
    hypotheses = store.load_hypotheses()
    hypotheses.append(hypothesis)
    store.save_hypotheses(hypotheses)
    return hypothesis.model_dump()


@app.patch("/api/hypotheses/{hypothesis_id}")
async def update_hypothesis(hypothesis_id: str, body: HypothesisUpdate):
    """Update hypothesis status or add evidence manually."""
    from engine.models import HypothesisStatus
    hypotheses = store.load_hypotheses()
    for h in hypotheses:
        if h.id == hypothesis_id:
            if body.status:
                try:
                    h.status = HypothesisStatus(body.status)
                except ValueError:
                    raise HTTPException(status_code=400, detail=f"Invalid status: {body.status}")
            if body.evidence:
                h.evidence.append(body.evidence)
            store.save_hypotheses(hypotheses)
            return h.model_dump()
    raise HTTPException(status_code=404, detail=f"Hypothesis {hypothesis_id} not found")


@app.delete("/api/hypotheses/{hypothesis_id}")
async def delete_hypothesis(hypothesis_id: str):
    """Soft-delete a hypothesis by marking it inconclusive."""
    from engine.models import HypothesisStatus
    hypotheses = store.load_hypotheses()
    for h in hypotheses:
        if h.id == hypothesis_id:
            h.status = HypothesisStatus.INCONCLUSIVE
            store.save_hypotheses(hypotheses)
            return {"id": h.id, "status": h.status.value}
    raise HTTPException(status_code=404, detail=f"Hypothesis {hypothesis_id} not found")


@app.get("/api/hypotheses/{hypothesis_id}/history")
async def get_hypothesis_history(hypothesis_id: str):
    """Get the evaluation trail for a hypothesis."""
    hypothesis = store.get_hypothesis(hypothesis_id)
    if not hypothesis:
        raise HTTPException(status_code=404, detail=f"Hypothesis {hypothesis_id} not found")
    return {
        "id": hypothesis.id,
        "hypothesis_text": hypothesis.hypothesis_text,
        "status": hypothesis.status.value,
        "confidence": hypothesis.confidence,
        "evaluation_count": hypothesis.evaluation_count,
        "evidence": hypothesis.evidence,
    }


@app.get("/api/hypotheses/report")
async def get_hypothesis_report():
    """Get a summary report of all hypotheses with performance data."""
    from engine.tracking.hypothesis_tracker import HypothesisTracker
    tracker = HypothesisTracker(store)
    return tracker.generate_report()


class HypothesisExtractInput(BaseModel):
    text: str
    context: str = ""


class HypothesisConfirmInput(BaseModel):
    hypothesis_text: str
    related_features: list[str] = []
    created_by: str = "dashboard"
    source: str = "manual"
    source_context: str = ""
    generate: bool = False


@app.post("/api/hypotheses/extract")
async def extract_hypotheses(body: HypothesisExtractInput):
    """
    Extract testable hypothesis candidates from natural language.
    Returns suggestions — does NOT create hypotheses.
    """
    from engine.tracking.hypothesis_extractor import HypothesisExtractor
    extractor = HypothesisExtractor()
    candidates = extractor.extract(body.text, context=body.context)

    for c in candidates:
        from engine.tracking.hypothesis_extractor import FEATURE_LABELS
        c["feature_labels"] = [
            FEATURE_LABELS.get(f, f.replace("_", " ")) for f in c.get("related_features", [])
        ]

    return {"candidates": candidates}


@app.post("/api/hypotheses/confirm")
async def confirm_hypothesis(body: HypothesisConfirmInput):
    """
    Create a hypothesis from a confirmed candidate. Optionally trigger ad generation.
    """
    from engine.models import CreativeHypothesis

    hypothesis = CreativeHypothesis(
        hypothesis_text=body.hypothesis_text,
        created_by=body.created_by,
        related_features=body.related_features,
        source=body.source,
        source_context=body.source_context,
    )
    hypotheses = store.load_hypotheses()
    hypotheses.append(hypothesis)
    store.save_hypotheses(hypotheses)

    result = {"hypothesis": hypothesis.model_dump()}

    if body.generate:
        orchestrator = _get_orchestrator()
        gen_result = orchestrator.test_hypothesis(hypothesis.id)
        result["generation"] = gen_result

    return result


@app.post("/api/hypotheses/{hypothesis_id}/test")
async def test_hypothesis(hypothesis_id: str):
    """Generate ads to test a hypothesis."""
    hypothesis = store.get_hypothesis(hypothesis_id)
    if not hypothesis:
        raise HTTPException(status_code=404, detail=f"Hypothesis {hypothesis_id} not found")

    orchestrator = _get_orchestrator()
    result = orchestrator.test_hypothesis(hypothesis_id)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


@app.get("/api/hypotheses/{hypothesis_id}/performance")
async def get_hypothesis_performance(hypothesis_id: str):
    """Get direct A/B performance data for a hypothesis."""
    from engine.tracking.hypothesis_tracker import HypothesisTracker
    tracker = HypothesisTracker(store)
    perf = tracker.get_hypothesis_performance(hypothesis_id)
    if not perf:
        raise HTTPException(status_code=404, detail=f"Hypothesis {hypothesis_id} not found")
    return perf


def _get_orchestrator():
    """Lazy-init orchestrator for hypothesis testing endpoints."""
    from engine.orchestrator import Orchestrator
    return Orchestrator(store=store)


# ---------------------------------------------------------------------------
# Analysis: Portfolio scatter, format comparison, deploy
# ---------------------------------------------------------------------------

@app.get("/api/analysis/portfolio-scatter")
async def portfolio_scatter(min_spend: float = 50.0):
    """
    Every ad we've ever run, merged from engine variants + imported existing ads.
    Filters out statistically insignificant ads (below min_spend), detects outliers
    via IQR, ranks by CpFN, and returns top 5.
    """
    import statistics

    VIDEO_FORMATS = {"video", "reels", "story"}
    ads = []
    total_before_filter = 0

    # 1. Engine-generated variants with snapshot data
    for variant in store.get_all_variants():
        snapshots = store.get_snapshots_for_variant(variant.id)
        if not snapshots:
            continue
        total_before_filter += 1
        total_spend = sum(s.spend for s in snapshots)
        total_notes = sum(s.first_note_completions for s in snapshots)
        if total_spend < min_spend:
            continue
        fmt = variant.taxonomy.format.value if variant.taxonomy else "single_image"
        ads.append({
            "id": variant.id,
            "name": variant.headline or "",
            "spend": round(total_spend, 2),
            "cpfn": round(total_spend / total_notes, 2) if total_notes > 0 else None,
            "first_notes": total_notes,
            "format": fmt,
            "is_video": fmt in VIDEO_FORMATS,
            "source": "engine",
            "image_url": variant.asset_path,
            "full_image_url": variant.asset_path,
            "is_outlier": False,
            "rank": None,
        })

    # 2. Imported existing ads (pre-aggregated performance)
    for ad in store.get_all_existing_ads():
        total_before_filter += 1
        if ad.spend < min_spend:
            continue
        fmt = ad.creative_type or "image"
        cpfn = ad.cost_per_conversion
        if cpfn is None and ad.conversions > 0:
            cpfn = round(ad.spend / ad.conversions, 2)
        ads.append({
            "id": ad.id,
            "name": ad.ad_name or ad.headline or "",
            "spend": round(ad.spend, 2),
            "cpfn": round(cpfn, 2) if cpfn is not None else None,
            "first_notes": ad.conversions,
            "format": fmt,
            "is_video": fmt in VIDEO_FORMATS,
            "source": "existing",
            "image_url": ad.thumbnail_url or ad.image_url,
            "full_image_url": ad.image_url,
            "is_outlier": False,
            "rank": None,
        })

    # 3. Outlier detection via IQR on cpfn
    cpfn_values = [a["cpfn"] for a in ads if a["cpfn"] is not None]
    if len(cpfn_values) >= 4:
        sorted_vals = sorted(cpfn_values)
        n = len(sorted_vals)
        q1 = sorted_vals[n // 4]
        q3 = sorted_vals[3 * n // 4]
        iqr = q3 - q1
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr
        for a in ads:
            if a["cpfn"] is not None and (a["cpfn"] < lower_fence or a["cpfn"] > upper_fence):
                a["is_outlier"] = True

    # 4. Rank by cpfn ascending (lower is better), None sorts last
    ranked = sorted(ads, key=lambda a: (a["cpfn"] is None, a["cpfn"] or 0))
    for i, a in enumerate(ranked):
        if a["cpfn"] is not None:
            a["rank"] = i + 1

    top_5 = [a for a in ranked if a["cpfn"] is not None][:5]
    outliers = [a for a in ranked if a["is_outlier"]]

    median_cpfn = round(statistics.median(cpfn_values), 2) if cpfn_values else None
    avg_cpfn = round(statistics.mean(cpfn_values), 2) if cpfn_values else None

    return {
        "ads": ranked,
        "top_5": top_5,
        "outliers": outliers,
        "median_cpfn": median_cpfn,
        "avg_cpfn": avg_cpfn,
        "total_ads": len(ranked),
        "filtered_out": total_before_filter - len(ranked),
    }


@app.get("/api/analysis/format-comparison")
async def format_comparison(min_spend: float = 50.0):
    """Compare video vs static ad format performance with statistical testing."""
    from engine.regression.model import CreativeRegressionModel
    regression = CreativeRegressionModel(store)
    result = regression.format_comparison(min_spend=min_spend)
    if result is None:
        raise HTTPException(status_code=400, detail="Insufficient data for format comparison")
    return result


class DeployRequest(BaseModel):
    variant_ids: list[str]
    campaign_id: Optional[str] = None  # Defaults to farm campaign from settings
    adset_id: Optional[str] = None     # Defaults to farm adset from settings


@app.post("/api/deploy")
async def deploy_to_meta(body: DeployRequest):
    """Deploy approved variants to Meta as paused ads."""
    from engine.deployment.deployer import AdDeployer, MetaDeployer
    from config.settings import get_settings

    settings = get_settings()
    if not settings.META_ACCESS_TOKEN or not settings.META_AD_ACCOUNT_ID:
        raise HTTPException(status_code=500, detail="Meta API credentials not configured")

    # Default to farm campaign/adset from settings
    campaign_id = body.campaign_id or settings.META_FARM_CAMPAIGN_ID
    adset_id = body.adset_id or settings.META_FARM_ADSET_ID

    if not campaign_id or not adset_id:
        raise HTTPException(
            status_code=400,
            detail="campaign_id and adset_id are required (or set META_FARM_CAMPAIGN_ID/META_FARM_ADSET_ID in .env)",
        )

    for vid in body.variant_ids:
        try:
            v = store.get_variant(vid)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Variant {vid} not found")
        if v.status != AdStatus.APPROVED:
            raise HTTPException(
                status_code=400,
                detail=f"Variant {vid} is {v.status.value}, not approved",
            )

    meta = MetaDeployer(
        settings.META_ACCESS_TOKEN,
        settings.META_AD_ACCOUNT_ID,
        page_id=settings.META_PAGE_ID,
    )
    deployer = AdDeployer(store, meta=meta)

    deployed = deployer.deploy_batch(body.variant_ids, campaign_id, adset_id)
    notifier.notify_deployment(deployed, "meta")

    return {
        "deployed": len(deployed),
        "ads": [
            {
                "variant_id": v.id,
                "meta_ad_id": v.meta_ad_id,
                "status": v.status.value,
            }
            for v in deployed
        ],
    }


# ---------------------------------------------------------------------------
# Tracking — manual data pull (P2.3)
# ---------------------------------------------------------------------------

@app.post("/api/tracking/pull")
async def pull_tracking():
    """Manually trigger performance data pull from Meta/Google."""
    try:
        from engine.orchestrator import Orchestrator
        orch = Orchestrator(store=store)
        snapshots = orch.tracker.pull_daily()
        return {
            "snapshots_created": len(snapshots),
            "date": date.today().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Tracking pull failed: {e}")


# ---------------------------------------------------------------------------
# Budget Pacing (P2.5)
# ---------------------------------------------------------------------------

@app.get("/api/budget/pacing")
async def budget_pacing():
    """Current month budget pacing vs target."""
    from engine.tracking.budget import compute_budget_pacing
    from config.settings import get_settings

    settings = get_settings()
    snapshots = store.get_all_snapshots()
    pacing = compute_budget_pacing(
        snapshots,
        monthly_budget=settings.MONTHLY_BUDGET,
    )
    return pacing


# ---------------------------------------------------------------------------
# Scheduler & Admin (P2.4)
# ---------------------------------------------------------------------------

@app.post("/api/admin/run-cycle")
async def manual_daily_cycle():
    """Manually trigger the full daily cycle (track → decide → regress → notify)."""
    import asyncio
    import json as _json

    async def _run():
        try:
            from engine.orchestrator import Orchestrator
            orch = Orchestrator(store=store)
            results = orch.run_daily_cycle()

            # Log cycle run
            cycles_dir = Path("data/cycles")
            cycles_dir.mkdir(parents=True, exist_ok=True)
            cycle_path = cycles_dir / f"{date.today().isoformat()}.json"
            cycle_path.write_text(_json.dumps(results, indent=2, default=str))

            return results
        except Exception as e:
            print(f"[CYCLE ERROR] {e}")
            return {"error": str(e)}

    asyncio.create_task(_run())
    return {"status": "started", "message": "Daily cycle running in background"}


@app.get("/api/admin/cycles")
async def list_cycles():
    """View history of daily cycle runs."""
    import json as _json

    cycles_dir = Path("data/cycles")
    cycles_dir.mkdir(parents=True, exist_ok=True)

    cycles = []
    for f in sorted(cycles_dir.glob("*.json"), reverse=True):
        try:
            data = _json.loads(f.read_text())
            cycles.append({
                "date": f.stem,
                "results": data,
            })
        except Exception:
            cycles.append({"date": f.stem, "results": {"error": "corrupt file"}})

    return {"cycles": cycles[:30]}  # Last 30 cycles


@app.get("/api/admin/config")
async def get_config_status():
    """
    Non-secret config status — which integrations are configured.
    Does NOT expose actual keys/tokens.
    """
    from config.settings import get_settings
    settings = get_settings()

    return {
        "meta": {
            "access_token_set": bool(settings.META_ACCESS_TOKEN),
            "ad_account_id_set": bool(settings.META_AD_ACCOUNT_ID),
            "page_id_set": bool(settings.META_PAGE_ID),
            "farm_campaign_id": settings.META_FARM_CAMPAIGN_ID or "(not set)",
            "farm_adset_id": settings.META_FARM_ADSET_ID or "(not set)",
            "scale_campaign_id": settings.META_SCALE_CAMPAIGN_ID or "(not set)",
            "scale_adset_id": settings.META_SCALE_ADSET_ID or "(not set)",
        },
        "google": {
            "developer_token_set": bool(settings.GOOGLE_ADS_DEVELOPER_TOKEN),
            "customer_id_set": bool(settings.GOOGLE_ADS_CUSTOMER_ID),
        },
        "slack": {
            "webhook_url_set": bool(settings.SLACK_WEBHOOK_URL),
            "channel": settings.SLACK_CHANNEL,
        },
        "budget": {
            "monthly_budget": settings.MONTHLY_BUDGET,
            "daily_limit": settings.DAILY_BUDGET_LIMIT,
            "alert_high_pct": settings.BUDGET_ALERT_HIGH * 100,
            "alert_low_pct": settings.BUDGET_ALERT_LOW * 100,
        },
    }


# ---------------------------------------------------------------------------
# Scheduler setup (P2.4) — APScheduler for automated daily cycle
# ---------------------------------------------------------------------------

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = AsyncIOScheduler()

    async def daily_cycle_job():
        """Run the full daily cycle: track → decide → regress → memory → notify."""
        import json as _json
        try:
            from engine.orchestrator import Orchestrator
            orch = Orchestrator(store=store)
            results = orch.run_daily_cycle()

            # Log cycle run
            cycles_dir = Path("data/cycles")
            cycles_dir.mkdir(parents=True, exist_ok=True)
            cycle_path = cycles_dir / f"{date.today().isoformat()}.json"
            cycle_path.write_text(_json.dumps(results, indent=2, default=str))

            print(f"[SCHEDULER] Daily cycle complete: {results.get('date', 'unknown')}")
        except Exception as e:
            print(f"[SCHEDULER ERROR] Daily cycle failed: {e}")
            # Notify via Slack that the daily cycle failed
            try:
                notifier._send(f"⚠️ *Daily cycle failed*\nError: {e}")
            except Exception:
                pass

    @app.on_event("startup")
    async def start_scheduler():
        scheduler.add_job(
            daily_cycle_job,
            CronTrigger(hour=6, minute=0, timezone="America/Los_Angeles"),  # 6am PT
            id="daily_cycle",
            replace_existing=True,
        )
        scheduler.start()
        print("[SCHEDULER] Daily cycle scheduled for 6:00 AM PT")

    @app.on_event("shutdown")
    async def stop_scheduler():
        scheduler.shutdown(wait=False)

except ImportError:
    print("[SCHEDULER] APScheduler not installed — daily cycle will not run automatically")
    print("[SCHEDULER] Install with: pip install apscheduler>=3.10.0")


# ---------------------------------------------------------------------------
# Backfill variant visual diversity (assign template + color scheme)
# ---------------------------------------------------------------------------

def _backfill_variant_templates() -> dict:
    """
    Backfill template_id and template_color_scheme on existing variants
    that have None for these fields. Uses TemplateSelector with batch
    diversity to assign varied templates and color schemes.
    """
    from engine.generation.template_selector import TemplateSelector

    all_variants = store.get_all_variants()
    needs_backfill = [v for v in all_variants if not v.template_id]

    if not needs_backfill:
        return {"backfilled": 0, "total": len(all_variants)}

    selector = TemplateSelector()

    # Build copy_variant dicts for the selector
    copy_variants = []
    for v in needs_backfill:
        taxonomy = v.taxonomy.model_dump() if v.taxonomy else {}
        copy_variants.append({"taxonomy": taxonomy})

    # Use batch selection for diversity
    plans = selector.select_batch(copy_variants, diversify=True)

    for v, plan in zip(needs_backfill, plans):
        v.template_id = plan.template
        v.template_color_scheme = plan.color_scheme
        store.save_variant(v)

    return {
        "backfilled": len(needs_backfill),
        "total": len(all_variants),
        "templates_assigned": len(set(p.template for p in plans)),
        "schemes_assigned": len(set(p.color_scheme for p in plans)),
    }


@app.post("/api/assets/backfill-templates")
async def backfill_templates():
    """Backfill template_id and template_color_scheme on variants missing them."""
    return _backfill_variant_templates()


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
    """Auto-heal stale asset paths and backfill template diversity on startup."""
    result = _heal_stale_asset_paths()
    if result["fixed"] > 0:
        print(f"[startup] Healed {result['fixed']} stale asset paths out of {result['scanned']} variants")

    # Backfill template_id and template_color_scheme for variants missing them
    backfill = _backfill_variant_templates()
    if backfill["backfilled"] > 0:
        print(
            f"[startup] Backfilled {backfill['backfilled']} variants with diverse templates "
            f"({backfill['templates_assigned']} templates, {backfill['schemes_assigned']} schemes)"
        )


@app.post("/api/assets/heal")
async def heal_asset_paths():
    """Manually trigger stale asset path healing."""
    return _heal_stale_asset_paths()
