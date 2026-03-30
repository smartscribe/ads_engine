"""
scripts/retag_existing.py — Re-tag all existing ads with the updated TAXONOMY_PROMPT.

Run this once after R2 changes to populate the 5 new extended dimensions:
  contains_specific_number, shows_product_ui, human_face_visible,
  social_proof_type, copy_length_bin

Also populates tagging_confidence per dimension (A1).

Usage:
    cd /path/to/ads_engine
    python scripts/retag_existing.py [--force] [--batch-size 15]

Options:
    --force     Re-tag even ads that already have taxonomy (refreshes all tags
                with new dimensions). Without --force, only tags ads missing
                the new extended fields.
    --batch-size N  Claude batch size (default 15)
"""

import argparse
import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.store import Store
from engine.analysis.analyzer import CreativeAnalyzer
from engine.models import CreativeTaxonomy, Platform, AdFormat


def needs_retag(ad) -> bool:
    """Return True if this ad needs re-tagging for new extended fields."""
    if ad.taxonomy is None:
        return True
    t = ad.taxonomy
    # Check if extended fields are still at their defaults (suggests old tagging)
    has_extended = (
        t.contains_specific_number is not False
        or t.shows_product_ui is not False
        or t.human_face_visible is not False
        or t.social_proof_type != "none"
        or t.copy_length_bin != "medium"
        or bool(t.tagging_confidence)
    )
    return not has_extended


def main():
    parser = argparse.ArgumentParser(description="Re-tag existing ads with updated taxonomy")
    parser.add_argument("--force", action="store_true",
                        help="Re-tag all ads, even those already tagged")
    parser.add_argument("--batch-size", type=int, default=15,
                        help="Claude batch size (default 15)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be re-tagged without actually calling Claude")
    args = parser.parse_args()

    store = Store()
    analyzer = CreativeAnalyzer()

    all_ads = store.get_all_existing_ads()
    print(f"[retag] Found {len(all_ads)} existing ads total")

    if args.force:
        to_retag = all_ads
        print(f"[retag] --force: re-tagging all {len(to_retag)} ads")
    else:
        to_retag = [a for a in all_ads if needs_retag(a)]
        print(f"[retag] {len(to_retag)} ads need re-tagging (missing extended fields)")

    if args.dry_run:
        print(f"[retag] DRY RUN — would re-tag {len(to_retag)} ads")
        for ad in to_retag[:5]:
            print(f"  - {ad.meta_ad_id}: {ad.ad_name[:60]}")
        if len(to_retag) > 5:
            print(f"  ... and {len(to_retag) - 5} more")
        return

    if not to_retag:
        print("[retag] Nothing to do — all ads already have extended fields.")
        return

    # Force re-tag by clearing taxonomy on selected ads (tag_ads skips already-tagged)
    if args.force:
        for ad in to_retag:
            ad.taxonomy = None

    print(f"[retag] Starting re-tagging with batch size {args.batch_size}...")
    tagged = analyzer.tag_ads(to_retag, store, batch_size=args.batch_size)

    # Report results
    success = sum(1 for a in tagged if a.taxonomy is not None)
    has_confidence = sum(
        1 for a in tagged
        if a.taxonomy is not None and bool(a.taxonomy.tagging_confidence)
    )
    has_extended = sum(
        1 for a in tagged
        if a.taxonomy is not None and (
            a.taxonomy.human_face_visible
            or a.taxonomy.shows_product_ui
            or a.taxonomy.contains_specific_number
            or a.taxonomy.social_proof_type != "none"
        )
    )

    print(f"\n[retag] Done!")
    print(f"  Tagged:           {success}/{len(to_retag)}")
    print(f"  Has confidence:   {has_confidence}/{success}")
    print(f"  Has extended data:{has_extended}/{success} (at least one non-default extended field)")

    # Show sample confidence scores
    if has_confidence > 0:
        sample = next(
            a for a in tagged
            if a.taxonomy is not None and bool(a.taxonomy.tagging_confidence)
        )
        print(f"\n  Sample confidence scores for '{sample.ad_name[:40]}':")
        for dim, conf in sorted(sample.taxonomy.tagging_confidence.items()):
            bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))
            print(f"    {dim:25s} {bar} {conf:.2f}")

    # Show low-confidence summary
    low_conf_counts: dict[str, int] = {}
    for ad in tagged:
        if ad.taxonomy and ad.taxonomy.tagging_confidence:
            for dim in ad.taxonomy.low_confidence_fields(threshold=0.6):
                low_conf_counts[dim] = low_conf_counts.get(dim, 0) + 1

    if low_conf_counts:
        print(f"\n  Low-confidence dimensions (confidence < 0.6):")
        for dim, count in sorted(low_conf_counts.items(), key=lambda x: -x[1]):
            print(f"    {dim:25s} {count} ads")
    else:
        print(f"\n  No low-confidence tags found.")


if __name__ == "__main__":
    main()
