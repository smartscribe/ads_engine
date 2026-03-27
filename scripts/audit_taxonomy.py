"""
scripts/audit_taxonomy.py — Sample 50 tagged ads and export taxonomy for manual review.

Used for A1 (Taxonomy Quality Audit). Generates a CSV that you can open in
a spreadsheet and manually review: are the tags MECE? Are they assigned correctly?

Usage:
    cd /path/to/ads_engine
    python scripts/audit_taxonomy.py [--sample 50] [--output data/audits/taxonomy_audit.csv]

Also prints a MECE overlap report highlighting potentially confusing dimension boundaries.
"""

import argparse
import csv
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.store import Store
from engine.models import CreativeTaxonomy


MECE_NOTES = """
MECE Boundary Decisions (enforce in TAXONOMY_PROMPT and tag reviews):

hook_type:
  - "statistic" wins over "direct_benefit" if a specific number is present,
    regardless of whether it also states a benefit
  - Example: "Save 2 hours/day on charting" → statistic, not direct_benefit

tone:
  - "warm" = warm-colleague energy (peer-to-peer, buddy talking to you)
  - "empathetic" = I-feel-your-pain energy (understanding the struggle)
  - "authoritative" = expert voice (citing credentials, research, outcomes)
  - Watch: "empathetic" and "warm" are frequently confused — ask: "Is this
    commiserating (empathetic) or encouraging (warm)?"

subject_matter:
  - "patient_interaction" ONLY if a patient is visibly present in the scene
  - A clinician typing notes after a session = clinician_at_work, not patient_interaction
  - Split screen with paper charts on one side = workflow_comparison

text_density:
  - "headline_only": 1-4 words total copy visible
  - "headline_subhead": 5-15 words (headline + brief subhead)
  - "detailed_copy": 15+ words (full body copy visible)
  - "minimal_overlay": any text overlaid on a full-bleed image

social_proof_type vs uses_social_proof:
  - uses_social_proof (bool): any mention of other clinicians, stats, testimonials
  - social_proof_type (categorical): what TYPE — "peer" (other clinician mentioned),
    "testimonial" (direct quote), "stat" ("used by 500+ clinicians"), "none"
"""


def build_mece_overlap_report(ads) -> dict:
    """Flag dimensions that likely overlap and show co-occurrence counts."""
    overlap_pairs = [
        ("hook_type", "statistic", "hook_type", "direct_benefit"),
        ("tone", "warm", "tone", "empathetic"),
        ("subject_matter", "clinician_at_work", "subject_matter", "patient_interaction"),
    ]

    field_value_counts = defaultdict(Counter)
    for ad in ads:
        if ad.taxonomy is None:
            continue
        t = ad.taxonomy
        for field in ["message_type", "hook_type", "cta_type", "tone",
                      "visual_style", "subject_matter", "color_mood", "text_density",
                      "social_proof_type", "copy_length_bin"]:
            val = getattr(t, field, None)
            if val is not None:
                field_value_counts[field][str(val)] += 1

    report = {"dimension_distributions": {}, "overlap_flags": []}
    for field, counter in field_value_counts.items():
        total = sum(counter.values())
        report["dimension_distributions"][field] = {
            val: {"count": cnt, "pct": round(cnt / total * 100, 1)}
            for val, cnt in counter.most_common()
        }

    # Flag single-value concentration (>80% in one bucket = possible MECE issue)
    for field, counter in field_value_counts.items():
        total = sum(counter.values())
        if total == 0:
            continue
        top_val, top_cnt = counter.most_common(1)[0]
        if top_cnt / total > 0.8:
            report["overlap_flags"].append(
                f"WARNING: {field}='{top_val}' is {top_cnt/total*100:.0f}% of ads — "
                f"possible MECE gap or over-assignment"
            )

    # Low-confidence summary
    low_conf_dims: Counter = Counter()
    for ad in ads:
        if ad.taxonomy and ad.taxonomy.tagging_confidence:
            for dim in ad.taxonomy.low_confidence_fields(threshold=0.6):
                low_conf_dims[dim] += 1

    if low_conf_dims:
        report["low_confidence_dims"] = dict(low_conf_dims.most_common())

    return report


def main():
    parser = argparse.ArgumentParser(description="Taxonomy quality audit — sample and export for manual review")
    parser.add_argument("--sample", type=int, default=50, help="Number of ads to sample (default 50)")
    parser.add_argument("--output", default=f"data/audits/taxonomy_audit_{date.today()}.csv",
                        help="Output CSV path")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for sampling")
    parser.add_argument("--all", action="store_true", help="Export all tagged ads, not just a sample")
    args = parser.parse_args()

    store = Store()
    all_ads = store.get_all_existing_ads()
    tagged = [a for a in all_ads if a.taxonomy is not None]

    print(f"[audit] {len(all_ads)} total ads, {len(tagged)} tagged")

    if not tagged:
        print("[audit] No tagged ads found. Run 'python scripts/retag_existing.py' first.")
        return

    if args.all:
        sample = tagged
    else:
        n = min(args.sample, len(tagged))
        random.seed(args.seed)
        sample = random.sample(tagged, n)
        print(f"[audit] Sampling {n} ads for manual review")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)

    # Write CSV
    fieldnames = [
        "meta_ad_id", "ad_name", "spend", "conversions", "cost_per_conversion",
        "headline", "body",
        # Taxonomy
        "message_type", "hook_type", "cta_type", "tone",
        "visual_style", "subject_matter", "color_mood", "text_density",
        "headline_word_count", "uses_number", "uses_question",
        "uses_first_person", "uses_social_proof",
        # Extended (R2)
        "contains_specific_number", "shows_product_ui", "human_face_visible",
        "social_proof_type", "copy_length_bin",
        # Quality
        "low_confidence_fields", "min_confidence",
        # Review columns (fill these in during audit)
        "REVIEW_correct_y_n", "REVIEW_corrections", "REVIEW_notes",
    ]

    with open(args.output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for ad in sample:
            t = ad.taxonomy
            low_conf = t.low_confidence_fields(threshold=0.6) if t.tagging_confidence else []
            min_conf = (
                min(t.tagging_confidence.values()) if t.tagging_confidence else None
            )
            writer.writerow({
                "meta_ad_id": ad.meta_ad_id,
                "ad_name": ad.ad_name,
                "spend": round(ad.spend, 2),
                "conversions": ad.conversions,
                "cost_per_conversion": round(ad.cost_per_conversion or 0, 2),
                "headline": (ad.headline or "")[:200],
                "body": (ad.body or "")[:300],
                "message_type": t.message_type,
                "hook_type": t.hook_type,
                "cta_type": t.cta_type,
                "tone": t.tone,
                "visual_style": t.visual_style,
                "subject_matter": t.subject_matter,
                "color_mood": t.color_mood,
                "text_density": t.text_density,
                "headline_word_count": t.headline_word_count,
                "uses_number": t.uses_number,
                "uses_question": t.uses_question,
                "uses_first_person": t.uses_first_person,
                "uses_social_proof": t.uses_social_proof,
                "contains_specific_number": t.contains_specific_number,
                "shows_product_ui": t.shows_product_ui,
                "human_face_visible": t.human_face_visible,
                "social_proof_type": t.social_proof_type,
                "copy_length_bin": t.copy_length_bin,
                "low_confidence_fields": "; ".join(low_conf),
                "min_confidence": round(min_conf, 2) if min_conf is not None else "",
                "REVIEW_correct_y_n": "",
                "REVIEW_corrections": "",
                "REVIEW_notes": "",
            })

    print(f"[audit] CSV written to {args.output}")
    print(f"[audit] Open in Excel/Sheets and fill in REVIEW_correct_y_n, REVIEW_corrections columns")

    # Print MECE notes
    print(f"\n{MECE_NOTES}")

    # Print distribution report
    report = build_mece_overlap_report(tagged)
    print("=" * 60)
    print("DIMENSION DISTRIBUTIONS (across all tagged ads):")
    print("=" * 60)
    for field, dist in report["dimension_distributions"].items():
        print(f"\n  {field}:")
        for val, stats in sorted(dist.items(), key=lambda x: -x[1]["count"]):
            bar = "█" * int(stats["pct"] / 5)
            print(f"    {val:30s} {bar} {stats['count']:4d} ({stats['pct']:.0f}%)")

    if report.get("overlap_flags"):
        print(f"\n{'='*60}")
        print("MECE FLAGS:")
        for flag in report["overlap_flags"]:
            print(f"  ⚠  {flag}")

    if report.get("low_confidence_dims"):
        print(f"\n{'='*60}")
        print("LOW-CONFIDENCE DIMENSIONS (< 0.6 threshold):")
        for dim, count in sorted(report["low_confidence_dims"].items(), key=lambda x: -x[1]):
            print(f"  {dim:30s} {count} ads")


if __name__ == "__main__":
    main()
