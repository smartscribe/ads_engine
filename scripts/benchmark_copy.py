"""
scripts/benchmark_copy.py — Benchmark copy agent output quality.

Generates headline + body sets across 3 representative briefs, with and without
memory context (A/B test). Saves results to data/benchmarks/copy_quality/ for
blind review.

Usage:
    cd /path/to/ads_engine
    python scripts/benchmark_copy.py [--briefs 3] [--per-brief 20]

Output:
    data/benchmarks/copy_quality/benchmark_{date}.json — all generated copy
    data/benchmarks/copy_quality/review_sheet_{date}.csv — formatted for blind review
"""

import argparse
import csv
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.generation.copy_agents import HeadlineAgent, BodyCopyAgent, CTAAgent
from engine.models import CreativeBrief, AdFormat, Platform

# 3 diverse test briefs covering different angles and audiences
TEST_BRIEFS = [
    CreativeBrief(
        raw_input="Test brief: after-hours charting pain, solo therapist",
        source="benchmark",
        target_audience="bh_clinicians",
        value_proposition="Eliminate after-hours charting — notes are done before you leave",
        pain_point="Solo therapist stays at office until 8pm every night writing notes",
        desired_action="Start free trial",
        tone_direction="Like a colleague who figured this out and is quietly excited to share",
        visual_direction="Therapist in dark office at night, then same therapist leaving at sunset",
        emotional_register="dreading the note backlog at day's end → quiet relief that it's already handled",
        proof_element="saves 2 hours per day on average",
        hook_strategy="open with the specific moment — 6pm, last patient left, stack of charts waiting",
        target_persona_details="solo therapist, 8-10 sessions/day, bills at night, resentful of the paperwork that cuts into personal time",
        key_phrases=["charting", "2 hours", "notes done", "evening back"],
    ),
    CreativeBrief(
        raw_input="Test brief: audit risk angle, clinic owner",
        source="benchmark",
        target_audience="smb_clinic_owners",
        value_proposition="Audit-ready documentation without extra staff time",
        pain_point="Clinic owner worried about billing audits and incomplete documentation",
        desired_action="Book a demo",
        tone_direction="Calm authority — like a colleague who's been through an audit and knows exactly what they wish they had done",
        visual_direction="Professional office setting, clinician reviewing clean organized records",
        emotional_register="low-grade anxiety about audit exposure → confidence that every note is complete and defensible",
        proof_element="CPT and ICD codes applied automatically to every note",
        hook_strategy="open with the moment an audit letter arrives — what do you wish your documentation looked like right now?",
        target_persona_details="clinic owner with 5-10 clinicians, had one billing audit already, knows their documentation quality varies by provider",
        key_phrases=["audit-ready", "CPT codes", "complete documentation", "defensible records"],
    ),
    CreativeBrief(
        raw_input="Test brief: UGC-style, peer recommendation",
        source="benchmark",
        target_audience="bh_clinicians",
        value_proposition="Other therapists are using JotPsych to get their evenings back",
        pain_point="Clinician skeptical of AI tools, trusts peer recommendations over marketing",
        desired_action="Learn more",
        tone_direction="Peer-to-peer: like a friend texting you 'you have to try this thing'",
        visual_direction="Candid, handheld-camera style photo of therapist at their desk smiling at phone",
        emotional_register="skeptical of another AI tool → curious because someone they respect is already using it",
        proof_element="used by 500+ behavioral health clinicians",
        hook_strategy="open with a social proof hook — 'My colleague Sarah told me about JotPsych...' or stats on adoption",
        target_persona_details="therapist mid-career, tired of productivity apps that add work, has seen colleagues burn out on admin, trusts word of mouth",
        key_phrases=["500+ clinicians", "colleagues", "word of mouth", "evenings back"],
    ),
]


def generate_for_brief(brief: CreativeBrief, with_context: bool, n_headlines: int = 20, n_bodies: int = 20):
    """Generate copy with or without memory context."""
    h_agent = HeadlineAgent()
    b_agent = BodyCopyAgent()
    c_agent = CTAAgent()

    context = None
    if with_context:
        try:
            from engine.store import Store
            from engine.memory.builder import MemoryBuilder
            store = Store()
            mb = MemoryBuilder(store)
            memory = mb.build()
            context = mb.build_generation_context(memory)
        except Exception as e:
            print(f"  [warn] Could not load memory context: {e}")

    try:
        headlines = h_agent.generate(brief, n=n_headlines, generation_context=context)
    except Exception as e:
        print(f"  [error] Headline generation failed: {e}")
        headlines = []

    try:
        bodies = b_agent.generate(brief, n=n_bodies, generation_context=context)
    except Exception as e:
        print(f"  [error] Body generation failed: {e}")
        bodies = []

    try:
        ctas = c_agent.generate(brief, n=5, generation_context=context)
    except Exception as e:
        print(f"  [error] CTA generation failed: {e}")
        ctas = []

    return {
        "headlines": headlines,
        "bodies": bodies,
        "ctas": ctas,
        "memory_on": with_context,
    }


def main():
    parser = argparse.ArgumentParser(description="Benchmark copy agent quality (A/B test memory)")
    parser.add_argument("--per-brief", type=int, default=20, help="Headlines + bodies per brief (default 20)")
    parser.add_argument("--no-ab", action="store_true", help="Skip A/B test, only run with memory ON")
    args = parser.parse_args()

    output_dir = Path("data/benchmarks/copy_quality")
    output_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    all_results = []

    for i, brief in enumerate(TEST_BRIEFS):
        print(f"\n[benchmark] Brief {i+1}/{len(TEST_BRIEFS)}: {brief.value_proposition[:60]}")

        print(f"  Generating with memory ON...")
        result_on = generate_for_brief(brief, with_context=True, n_headlines=args.per_brief, n_bodies=args.per_brief)

        result_off = {"headlines": [], "bodies": [], "ctas": [], "memory_on": False}
        if not args.no_ab:
            print(f"  Generating with memory OFF...")
            result_off = generate_for_brief(brief, with_context=False, n_headlines=args.per_brief, n_bodies=args.per_brief)

        all_results.append({
            "brief_index": i,
            "brief_audience": brief.target_audience,
            "brief_value_prop": brief.value_proposition,
            "brief_emotional_register": brief.emotional_register,
            "brief_hook_strategy": brief.hook_strategy,
            "memory_on": result_on,
            "memory_off": result_off,
        })

        h_on = len(result_on["headlines"])
        h_off = len(result_off["headlines"])
        print(f"  Generated: {h_on} headlines (ON), {h_off} headlines (OFF)")

    # Save JSON
    json_path = output_dir / f"benchmark_{today}.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n[benchmark] Saved to {json_path}")

    # Save CSV for blind review
    csv_path = output_dir / f"review_sheet_{today}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "brief_id", "type", "condition", "text",
            "SCORE_specificity_1_5", "SCORE_emotional_resonance_1_5",
            "SCORE_brand_voice_1_5", "NOTES"
        ])

        for r in all_results:
            brief_id = f"brief_{r['brief_index']+1}"
            for cond, data in [("memory_ON", r["memory_on"]), ("memory_OFF", r["memory_off"])]:
                for h in data.get("headlines", []):
                    text = h.get("text", h) if isinstance(h, dict) else h
                    writer.writerow([brief_id, "headline", cond, text, "", "", "", ""])
                for b in data.get("bodies", []):
                    text = b.get("text", b) if isinstance(b, dict) else b
                    writer.writerow([brief_id, "body", cond, text[:200], "", "", "", ""])

    print(f"[benchmark] Review sheet saved to {csv_path}")
    print(f"\nNext steps:")
    print(f"  1. Open {csv_path} in a spreadsheet")
    print(f"  2. Score each row without looking at the 'condition' column (blind review)")
    print(f"  3. Compare average scores for memory_ON vs memory_OFF")
    print(f"  4. If memory_ON has convergence (all similar), change to_prompt_block() framing to 'inspired by'")


if __name__ == "__main__":
    main()
