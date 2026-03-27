"""
scripts/audit_images.py — Generate 20 images for visual quality audit.

Generates a set of images using the current _build_image_prompt_v2() pipeline
across different visual styles (UGC, editorial, product-focused) for manual
review and scoring.

Usage:
    cd /path/to/ads_engine
    python scripts/audit_images.py [--count 20] [--output data/audits/images/]

After running, manually rate each image 1-5 on:
  - Realism (does it look like a real photo? not AI-generated?)
  - Brand fit (JotPsych aesthetic? warm blues, clinician-authentic?)
  - Concept accuracy (does it match the brief it was generated from?)
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.models import CreativeBrief, AdFormat, Platform, CreativeTaxonomy


# Test briefs for image generation — one per visual style
IMAGE_TEST_CASES = [
    {
        "style": "ugc_style",
        "description": "Handheld, candid, slightly messy real environment",
        "brief_args": {
            "raw_input": "UGC style: therapist at desk at end of day",
            "source": "benchmark",
            "target_audience": "bh_clinicians",
            "value_proposition": "Notes done before you leave",
            "pain_point": "After-hours charting",
            "desired_action": "Learn more",
            "tone_direction": "candid and real",
            "visual_direction": "handheld style, natural light, real clinician office, slightly messy",
            "hook_strategy": "catch the moment of relief",
        },
        "taxonomy_args": {
            "visual_style": "photography",
            "subject_matter": "clinician_at_work",
            "tone": "warm",
            "human_face_visible": True,
        },
    },
    {
        "style": "editorial",
        "description": "Studio-lit, clean, polished composition",
        "brief_args": {
            "raw_input": "Editorial style: professional clinician",
            "source": "benchmark",
            "target_audience": "bh_clinicians",
            "value_proposition": "Complete documentation, done right",
            "pain_point": "Audit risk from incomplete notes",
            "desired_action": "Book demo",
            "tone_direction": "authoritative and trustworthy",
            "visual_direction": "editorial, clean desk, professional setting, confident clinician",
        },
        "taxonomy_args": {
            "visual_style": "photography",
            "subject_matter": "clinician_at_work",
            "tone": "authoritative",
            "shows_product_ui": False,
        },
    },
    {
        "style": "product_focused",
        "description": "JotPsych UI visible in the creative",
        "brief_args": {
            "raw_input": "Product shot: JotPsych on phone/laptop",
            "source": "benchmark",
            "target_audience": "bh_clinicians",
            "value_proposition": "AI notes ready in minutes",
            "pain_point": "Manual documentation takes too long",
            "desired_action": "See how it works",
            "tone_direction": "clear and product-forward",
            "visual_direction": "close up of JotPsych interface on phone screen or laptop, clean background",
        },
        "taxonomy_args": {
            "visual_style": "screen_capture",
            "subject_matter": "product_ui",
            "tone": "clinical",
            "shows_product_ui": True,
        },
    },
    {
        "style": "before_after",
        "description": "Split scene showing workflow comparison",
        "brief_args": {
            "raw_input": "Before/after: chaotic desk vs clean desk",
            "source": "benchmark",
            "target_audience": "bh_clinicians",
            "value_proposition": "From overwhelmed to organized",
            "pain_point": "Documentation backlog",
            "desired_action": "Start free trial",
            "tone_direction": "transformation, before vs after",
            "visual_direction": "split screen: left side cluttered desk with paper charts, right side clean desk with single device",
        },
        "taxonomy_args": {
            "visual_style": "photography",
            "subject_matter": "workflow_comparison",
            "tone": "empathetic",
            "contains_specific_number": True,
        },
    },
    {
        "style": "social_proof",
        "description": "Peer recommendation, clinician to clinician",
        "brief_args": {
            "raw_input": "Social proof: clinician talking to colleague",
            "source": "benchmark",
            "target_audience": "bh_clinicians",
            "value_proposition": "Clinicians recommending JotPsych to colleagues",
            "pain_point": "Skepticism about new tools",
            "desired_action": "Learn more",
            "tone_direction": "peer-to-peer warmth",
            "visual_direction": "two clinicians in conversation, one showing something on phone to the other",
        },
        "taxonomy_args": {
            "visual_style": "photography",
            "subject_matter": "clinician_at_work",
            "tone": "warm",
            "human_face_visible": True,
            "social_proof_type": "peer",
        },
    },
]


def build_test_brief(case: dict) -> CreativeBrief:
    from engine.models import AdFormat as AF
    args = case["brief_args"]
    return CreativeBrief(
        raw_input=args.get("raw_input", ""),
        source=args.get("source", "benchmark"),
        target_audience=args.get("target_audience", "bh_clinicians"),
        value_proposition=args.get("value_proposition", ""),
        pain_point=args.get("pain_point", ""),
        desired_action=args.get("desired_action", "Learn more"),
        tone_direction=args.get("tone_direction", ""),
        visual_direction=args.get("visual_direction", ""),
        key_phrases=args.get("key_phrases", []),
        formats_requested=[AF.SINGLE_IMAGE],
        platforms=[Platform.META],
    )


def build_test_taxonomy(case: dict) -> CreativeTaxonomy:
    tax_args = case.get("taxonomy_args", {})
    return CreativeTaxonomy(
        message_type=tax_args.get("message_type", "value_prop"),
        hook_type=tax_args.get("hook_type", "direct_benefit"),
        cta_type=tax_args.get("cta_type", "learn_more"),
        tone=tax_args.get("tone", "warm"),
        visual_style=tax_args.get("visual_style", "photography"),
        subject_matter=tax_args.get("subject_matter", "clinician_at_work"),
        color_mood=tax_args.get("color_mood", "warm_earth"),
        text_density=tax_args.get("text_density", "headline_subhead"),
        format=AdFormat.SINGLE_IMAGE,
        platform=Platform.META,
        placement="feed",
        headline_word_count=5,
        uses_number=tax_args.get("uses_number", False),
        uses_question=tax_args.get("uses_question", False),
        uses_first_person=False,
        uses_social_proof=tax_args.get("uses_social_proof", False),
        copy_reading_level=8.0,
        contains_specific_number=tax_args.get("contains_specific_number", False),
        shows_product_ui=tax_args.get("shows_product_ui", False),
        human_face_visible=tax_args.get("human_face_visible", False),
        social_proof_type=tax_args.get("social_proof_type", "none"),
    )


def main():
    parser = argparse.ArgumentParser(description="Generate images for quality audit")
    parser.add_argument("--count", type=int, default=20, help="Total images to generate (default 20)")
    parser.add_argument("--output", default=f"data/audits/images/{date.today()}", help="Output directory")
    parser.add_argument("--dry-run", action="store_true", help="Print prompts without generating")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    from engine.generation.generator import CreativeGenerator
    generator = CreativeGenerator()

    # Cycle through test cases to reach --count images
    import itertools
    test_cycle = itertools.cycle(IMAGE_TEST_CASES)
    results = []

    print(f"[audit_images] Generating {args.count} images to {output_dir}")

    for i in range(args.count):
        case = next(test_cycle)
        brief = build_test_brief(case)
        taxonomy = build_test_taxonomy(case)

        prompt = generator._build_image_prompt(brief, taxonomy)
        print(f"\n[{i+1}/{args.count}] Style: {case['style']}")
        print(f"  Description: {case['description']}")

        if args.dry_run:
            print(f"  PROMPT: {prompt[:300]}...")
            results.append({
                "index": i + 1,
                "style": case["style"],
                "prompt": prompt,
                "image_path": None,
            })
            continue

        print(f"  Generating image...")
        try:
            from engine.models import AdVariant
            import uuid
            variant = AdVariant(
                brief_id=brief.id,
                headline="Test headline",
                primary_text="Test body copy",
                cta_button="Learn More",
                asset_path=str(output_dir / f"audit_{i+1:02d}_{case['style']}.png"),
                asset_type="image",
                taxonomy=taxonomy,
            )
            image_path = generator._generate_image(variant, brief)
            results.append({
                "index": i + 1,
                "style": case["style"],
                "description": case["description"],
                "prompt": prompt[:500],
                "image_path": image_path,
                "SCORE_realism_1_5": "",
                "SCORE_brand_fit_1_5": "",
                "SCORE_concept_accuracy_1_5": "",
                "NOTES": "",
            })
            print(f"  Saved: {image_path}")
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({
                "index": i + 1,
                "style": case["style"],
                "error": str(e),
            })

    # Save audit log
    log_path = output_dir / "audit_log.json"
    with open(log_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Save review CSV
    import csv
    csv_path = output_dir / "review_sheet.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "index", "style", "description", "image_path",
            "SCORE_realism_1_5", "SCORE_brand_fit_1_5", "SCORE_concept_accuracy_1_5", "NOTES"
        ], extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    print(f"\n[audit_images] Done! {len(results)} images generated")
    print(f"  Audit log: {log_path}")
    print(f"  Review sheet: {csv_path}")
    print(f"\nNext steps:")
    print(f"  1. Open {output_dir}/ and review each image")
    print(f"  2. Fill in SCORE_* columns in {csv_path} (1=terrible, 5=photo-realistic)")
    print(f"  3. Use findings to update negative prompts in engine/generation/generator.py")


if __name__ == "__main__":
    main()
