"""
scripts/test_memory_impact.py — A/B test: does memory injection improve copy quality?

Generates 10 variants with memory OFF and 10 with memory ON for each of 5 representative
briefs. Saves all output to data/benchmarks/memory_test/ for blind review.

Also checks for convergence: if memory-ON variants are too similar to each other,
that's a sign to soften the to_prompt_block() framing from "do this" to "inspired by".

Usage:
    cd /path/to/ads_engine
    python scripts/test_memory_impact.py [--briefs 5] [--per-condition 10]

Output:
    data/benchmarks/memory_test/memory_test_{date}.json
    data/benchmarks/memory_test/blind_review_{date}.csv

SCORING GUIDE:
After running, open the CSV, shuffle rows (sort by random column), and rate each row
without looking at the condition column. Compare average scores for ON vs OFF.

If memory_ON variance is very LOW (all variants similar), reduce prompt framing.
If memory_ON scores are HIGHER, double down on context injection.
"""

import argparse
import csv
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.generation.copy_agents import HeadlineAgent, BodyCopyAgent
from engine.models import CreativeBrief, AdFormat, Platform
from engine.memory.models import GenerationContext

# 5 representative briefs (different angles, audiences, pain points)
TEST_BRIEFS = [
    CreativeBrief(
        raw_input="test: charting late at night",
        source="benchmark",
        target_audience="bh_clinicians",
        value_proposition="End after-hours charting tonight",
        pain_point="Therapist stays until 9pm writing notes every day",
        desired_action="Start free trial",
        tone_direction="Like a colleague who figured this out and can't believe how different life is",
        visual_direction="Empty office at dusk, one lamp on",
        emotional_register="resentful nightly routine → surprised relief that it's already done",
        proof_element="saves 2 hours per day on average",
        hook_strategy="open with the exact moment: 7pm, last patient left, notes still waiting",
        target_persona_details="solo therapist, 8-10 sessions/day, dreads the note backlog that follows every session",
        key_phrases=["2 hours", "notes done", "charting"],
    ),
    CreativeBrief(
        raw_input="test: audit anxiety",
        source="benchmark",
        target_audience="smb_clinic_owners",
        value_proposition="Every note is audit-ready, automatically",
        pain_point="Fear of billing audit with inconsistent documentation across the clinic",
        desired_action="Book demo",
        tone_direction="Calm authority — someone who's been through an audit and knows what they wish they had",
        visual_direction="Clinical director reviewing organized binder, confident expression",
        emotional_register="low-grade audit anxiety → quiet confidence that every note is defensible",
        proof_element="CPT and ICD codes applied automatically to every session note",
        hook_strategy="open with the audit letter scenario — what do your notes look like right now?",
        target_persona_details="clinic director, 6-8 clinicians, had one audit already, documentation quality varies by provider",
        key_phrases=["audit-ready", "CPT codes", "every note"],
    ),
    CreativeBrief(
        raw_input="test: social proof, peer recommendation",
        source="benchmark",
        target_audience="bh_clinicians",
        value_proposition="Your colleagues are already using this",
        pain_point="Skepticism about AI tools — another thing that adds work",
        desired_action="Learn more",
        tone_direction="Peer-to-peer: casual, low-pressure, genuine excitement not marketing speak",
        visual_direction="Candid clinician talking on phone, relaxed pose",
        emotional_register="skeptical of yet another productivity tool → curious because Sarah from your study group swears by it",
        proof_element="used by 500+ behavioral health clinicians",
        hook_strategy="open with a peer conversation: 'have you heard of JotPsych?' or stats on clinician adoption",
        target_persona_details="mid-career therapist, has tried and abandoned multiple apps, trusts recommendations from colleagues more than ads",
        key_phrases=["500+ clinicians", "colleagues", "Sarah"],
    ),
    CreativeBrief(
        raw_input="test: first session experience",
        source="benchmark",
        target_audience="bh_clinicians",
        value_proposition="Leave your first session with notes already written",
        pain_point="Nervous about documentation falling behind from day one",
        desired_action="Start free trial",
        tone_direction="Encouraging, like someone who wants you to experience the magic yourself",
        visual_direction="Therapist finishing first session of day, looking at phone with pleasant surprise",
        emotional_register="anticipating the note-writing burden → delighted to find the notes are already waiting",
        proof_element="notes generated in under 3 minutes after session ends",
        hook_strategy="paint the specific moment: session ends, clinician opens JotPsych, note is already there",
        target_persona_details="newer clinician in first year of practice, establishing documentation habits, open to new tools",
        key_phrases=["3 minutes", "already done", "first session"],
    ),
    CreativeBrief(
        raw_input="test: burnout prevention angle",
        source="benchmark",
        target_audience="bh_clinicians",
        value_proposition="Documentation burnout isn't inevitable",
        pain_point="Considering leaving clinical practice because of administrative burden",
        desired_action="See how it works",
        tone_direction="Direct, almost confrontational: 'You didn't train for years to spend your evenings typing'",
        visual_direction="Stark contrast: tired clinician at late-night desk vs same person leaving office at sunset",
        emotional_register="demoralized by the documentation treadmill → quiet anger that this is optional",
        proof_element="clinicians recover 10+ hours per week",
        hook_strategy="open with the statistic about documentation-driven burnout, then pivot: it doesn't have to be this way",
        target_persona_details="experienced clinician, 5+ years in practice, seriously considering reducing caseload or leaving due to paperwork",
        key_phrases=["10 hours back", "burnout", "you trained for this"],
    ),
]


def generate_headlines(brief: CreativeBrief, with_memory: bool, n: int = 10) -> list:
    """Generate headlines with or without memory context."""
    agent = HeadlineAgent()
    context = None

    if with_memory:
        try:
            from engine.store import Store
            from engine.memory.builder import MemoryBuilder
            store = Store()
            mb = MemoryBuilder(store)
            memory = mb.build()
            context = mb.build_generation_context(memory)
        except Exception as e:
            print(f"  [warn] Could not load memory: {e}")

    try:
        return agent.generate(brief, n=n, generation_context=context)
    except Exception as e:
        print(f"  [error] Headline gen failed: {e}")
        return []


def check_convergence(variants: list) -> dict:
    """
    Check if variants converge (all too similar).
    Returns convergence metrics.
    """
    if not variants:
        return {"convergence_score": 0, "unique_hook_types": 0, "note": "no variants"}

    hook_types = set()
    for v in variants:
        if isinstance(v, dict) and "hook_type" in v:
            hook_types.add(v["hook_type"])

    texts = [v.get("text", "") if isinstance(v, dict) else str(v) for v in variants]

    # Simple word overlap check
    word_sets = [set(t.lower().split()) for t in texts if t]
    if len(word_sets) < 2:
        return {"convergence_score": 0, "unique_hook_types": len(hook_types)}

    overlaps = []
    for i in range(len(word_sets)):
        for j in range(i + 1, len(word_sets)):
            if word_sets[i] and word_sets[j]:
                overlap = len(word_sets[i] & word_sets[j]) / max(len(word_sets[i]), len(word_sets[j]))
                overlaps.append(overlap)

    avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0

    return {
        "convergence_score": round(avg_overlap, 3),
        "unique_hook_types": len(hook_types),
        "hook_type_coverage": sorted(hook_types),
        "note": (
            "HIGH CONVERGENCE — consider softening to_prompt_block() framing"
            if avg_overlap > 0.5 else
            "OK convergence"
        )
    }


def main():
    parser = argparse.ArgumentParser(description="A/B test memory injection impact on copy quality")
    parser.add_argument("--per-condition", type=int, default=10, help="Variants per condition per brief (default 10)")
    parser.add_argument("--no-off-condition", action="store_true", help="Skip memory OFF condition (only run ON)")
    args = parser.parse_args()

    output_dir = Path("data/benchmarks/memory_test")
    output_dir.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()

    all_results = []

    print(f"[memory_test] Testing {len(TEST_BRIEFS)} briefs × {args.per_condition} variants per condition")
    print(f"[memory_test] Output: {output_dir}/")

    for i, brief in enumerate(TEST_BRIEFS):
        print(f"\n[brief {i+1}/{len(TEST_BRIEFS)}] {brief.value_proposition[:50]}")

        print(f"  Generating {args.per_condition} headlines with memory ON...")
        on_variants = generate_headlines(brief, with_memory=True, n=args.per_condition)
        on_convergence = check_convergence(on_variants)
        print(f"  ON: {len(on_variants)} variants, convergence={on_convergence['convergence_score']:.2f} — {on_convergence['note']}")

        off_variants = []
        off_convergence = {}
        if not args.no_off_condition:
            print(f"  Generating {args.per_condition} headlines with memory OFF...")
            off_variants = generate_headlines(brief, with_memory=False, n=args.per_condition)
            off_convergence = check_convergence(off_variants)
            print(f"  OFF: {len(off_variants)} variants, convergence={off_convergence['convergence_score']:.2f}")

        all_results.append({
            "brief_index": i + 1,
            "brief_value_prop": brief.value_proposition,
            "brief_hook_strategy": brief.hook_strategy,
            "brief_emotional_register": brief.emotional_register,
            "memory_on": {
                "variants": on_variants,
                "convergence": on_convergence,
            },
            "memory_off": {
                "variants": off_variants,
                "convergence": off_convergence,
            },
        })

    # Save JSON
    json_path = output_dir / f"memory_test_{today}.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n[memory_test] Saved JSON to {json_path}")

    # Save CSV for blind review
    csv_path = output_dir / f"blind_review_{today}.csv"
    rows = []
    for r in all_results:
        brief_id = f"brief_{r['brief_index']}"
        for variant in r["memory_on"].get("variants", []):
            text = variant.get("text", str(variant)) if isinstance(variant, dict) else str(variant)
            hook = variant.get("hook_type", "") if isinstance(variant, dict) else ""
            rows.append({
                "brief_id": brief_id,
                "condition": "memory_ON",
                "text": text,
                "hook_type": hook,
                "SCORE_1_5": "",
                "NOTES": "",
            })
        for variant in r["memory_off"].get("variants", []):
            text = variant.get("text", str(variant)) if isinstance(variant, dict) else str(variant)
            hook = variant.get("hook_type", "") if isinstance(variant, dict) else ""
            rows.append({
                "brief_id": brief_id,
                "condition": "memory_OFF",
                "text": text,
                "hook_type": hook,
                "SCORE_1_5": "",
                "NOTES": "",
            })

    # Shuffle for blind review (sort by brief_id + random_order)
    import random
    random.shuffle(rows)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["brief_id", "condition", "text", "hook_type", "SCORE_1_5", "NOTES"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"[memory_test] Saved review sheet to {csv_path}")
    print(f"\n[memory_test] Next steps:")
    print(f"  1. Open {csv_path}")
    print(f"  2. DO NOT look at the 'condition' column yet — score all rows 1-5")
    print(f"  3. After scoring, reveal condition and compare avg scores ON vs OFF")
    print(f"  4. If convergence_score > 0.5 on memory_ON: soften to_prompt_block() framing to 'inspired by'")
    print(f"  5. If memory_ON avg score > memory_OFF + 0.5: the memory system is working well")

    # Print convergence summary
    print(f"\n[memory_test] CONVERGENCE SUMMARY:")
    for r in all_results:
        on_conv = r["memory_on"].get("convergence", {})
        off_conv = r["memory_off"].get("convergence", {})
        print(f"  Brief {r['brief_index']}: ON={on_conv.get('convergence_score', 'N/A'):.2f} hooks={on_conv.get('unique_hook_types', 0)} | OFF={off_conv.get('convergence_score', 'N/A') if off_conv else 'skipped'}")


if __name__ == "__main__":
    main()
