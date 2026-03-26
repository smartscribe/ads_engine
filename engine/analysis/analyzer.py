"""
Meta Ads export + Claude-powered creative analysis pipeline.

MetaAdsExporter: pulls all ads and insights from Meta Graph API via requests.
CreativeAnalyzer: tags ads with CreativeTaxonomy using Claude, runs portfolio analysis.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from anthropic import Anthropic

from config.settings import get_settings
from engine.models import (
    AdFormat,
    CreativeTaxonomy,
    ExistingAd,
    Platform,
)
from engine.store import Store


# ---------------------------------------------------------------------------
# Meta Graph API exporter
# ---------------------------------------------------------------------------

class MetaAdsExporter:
    BASE_URL = "https://graph.facebook.com/v21.0"

    def __init__(self, access_token: str = None, ad_account_id: str = None):
        s = get_settings()
        self.access_token = access_token or s.META_ACCESS_TOKEN
        self.ad_account_id = ad_account_id or s.META_AD_ACCOUNT_ID

    def export_all(self, store: Store) -> list[ExistingAd]:
        """Pull every ad + its performance data from Meta and persist to *store*."""

        print("[exporter] Fetching ad stubs...")
        ads_data = self._paginate_raw(
            f"{self.BASE_URL}/{self.ad_account_id}/ads"
            f"?fields=name,status,campaign{{name,status}},adset{{name}}"
            f"&limit=200&access_token={self.access_token}"
        )
        print(f"[exporter] Got {len(ads_data)} ads")

        print("[exporter] Fetching creative content in batches...")
        self._enrich_creative_batched(ads_data)

        print("[exporter] Fetching ad-level insights...")
        insights_data = self._paginate_raw(
            f"{self.BASE_URL}/{self.ad_account_id}/insights"
            f"?fields=ad_id,ad_name,spend,impressions,reach,clicks,ctr,cpc,actions,cost_per_action_type"
            f"&level=ad&date_preset=maximum&limit=200&access_token={self.access_token}"
        )
        print(f"[exporter] Got {len(insights_data)} insight rows")

        insights_by_id: dict[str, dict] = {}
        insights_by_name: dict[str, dict] = {}
        for row in insights_data:
            if "ad_id" in row:
                insights_by_id[row["ad_id"]] = row
            if "ad_name" in row:
                insights_by_name[row["ad_name"]] = row

        results: list[ExistingAd] = []
        for ad in ads_data:
            ad_id = ad["id"]
            ad_name = ad.get("name", "")

            insight = insights_by_id.get(ad_id) or insights_by_name.get(ad_name) or {}

            creative = ad.get("creative") or {}
            creative_type = self._determine_creative_type(creative, ad_name)

            actions = insight.get("actions") or []
            cost_per_actions = insight.get("cost_per_action_type") or []
            conversions, cost_per_conversion = self._extract_conversions(
                actions, cost_per_actions
            )

            existing = store.find_existing_ad_by_meta_id(ad_id)
            existing_ad = ExistingAd(
                **({"id": existing.id} if existing else {}),
                platform=Platform.META,
                meta_ad_id=ad_id,
                ad_name=ad_name,
                campaign_name=(ad.get("campaign") or {}).get("name", ""),
                campaign_status=(ad.get("campaign") or {}).get("status", ""),
                adset_name=(ad.get("adset") or {}).get("name", ""),
                headline=creative.get("title"),
                body=creative.get("body"),
                cta_type=creative.get("call_to_action_type"),
                image_url=creative.get("image_url"),
                thumbnail_url=creative.get("thumbnail_url"),
                creative_type=creative_type,
                spend=float(insight.get("spend", 0)),
                impressions=int(insight.get("impressions", 0)),
                reach=int(insight.get("reach", 0)),
                clicks=int(insight.get("clicks", 0)),
                ctr=float(insight.get("ctr", 0)),
                cpc=float(insight.get("cpc", 0)),
                conversions=conversions,
                cost_per_conversion=cost_per_conversion if cost_per_conversion else None,
                taxonomy=existing.taxonomy if existing else None,
                analyzed_at=existing.analyzed_at if existing else None,
            )
            store.save_existing_ad(existing_ad)
            results.append(existing_ad)

        print(f"[exporter] Saved {len(results)} ads to store")
        return results

    # -- Internal helpers -----------------------------------------------------

    def _enrich_creative_batched(self, ads: list[dict], batch_size: int = 50) -> None:
        """Fetch creative fields for ads including asset_feed_spec for copy."""
        for i in range(0, len(ads), batch_size):
            batch = ads[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(ads) + batch_size - 1) // batch_size
            print(f"[exporter] Creative batch {batch_num}/{total_batches} ({len(batch)} ads)...")
            for ad in batch:
                try:
                    with urllib.request.urlopen(
                        f"{self.BASE_URL}/{ad['id']}"
                        f"?fields=creative.fields(title,body,call_to_action_type,image_url,thumbnail_url,object_type,asset_feed_spec)"
                        f"&access_token={self.access_token}",
                        timeout=30,
                    ) as resp:
                        data = json.loads(resp.read())
                    creative = data.get("creative", {})
                    # Promote asset_feed_spec copy into the top-level creative dict
                    # so the merge logic in export_all() can find it uniformly
                    if not creative.get("title") and not creative.get("body"):
                        afs = creative.get("asset_feed_spec") or {}
                        bodies = afs.get("bodies", [])
                        titles = afs.get("titles", [])
                        ctas = afs.get("call_to_action_types", [])
                        if bodies:
                            creative["body"] = bodies[0].get("text", "")
                        if titles:
                            creative["title"] = titles[0].get("text", "")
                        if ctas and not creative.get("call_to_action_type"):
                            creative["call_to_action_type"] = ctas[0]
                    ad["creative"] = creative
                except Exception as e:
                    print(f"[exporter] Could not fetch creative for {ad['id']}: {e}")
                    ad.setdefault("creative", {})

    def _paginate_raw(self, url: str, max_retries: int = 5) -> list[dict]:
        """Paginate using urllib (avoids requests re-encoding curly braces in field expansion syntax)."""
        import time as _time

        all_items: list[dict] = []
        while url:
            for attempt in range(max_retries):
                try:
                    with urllib.request.urlopen(url, timeout=60) as resp:
                        payload = json.loads(resp.read())

                    if "error" in payload:
                        code = payload["error"].get("code", 0)
                        if code == 17:  # rate limit
                            wait = min(60 * (attempt + 1), 300)
                            print(f"[exporter] Rate limited, waiting {wait}s (attempt {attempt + 1})...")
                            _time.sleep(wait)
                            continue
                        raise RuntimeError(f"Meta API error: {payload['error'].get('message', payload['error'])}")

                    all_items.extend(payload.get("data", []))
                    url = payload.get("paging", {}).get("next")
                    break

                except urllib.error.HTTPError as e:
                    if e.code == 400 and attempt < max_retries - 1:
                        body = e.read().decode()
                        if "request limit" in body.lower() or '"code":17' in body:
                            wait = min(60 * (attempt + 1), 300)
                            print(f"[exporter] Rate limited (HTTP 400), waiting {wait}s...")
                            _time.sleep(wait)
                            continue
                    raise
            else:
                raise RuntimeError("Max retries exceeded for Meta API")

        return all_items

    def _extract_conversions(
        self, actions: list, cost_per_actions: list
    ) -> tuple[int, Optional[float]]:
        conversions = 0
        cost_per = None
        target = "offsite_conversion.fb_pixel_custom"

        for a in actions:
            if a.get("action_type") == target:
                conversions = int(a.get("value", 0))
                break

        for c in cost_per_actions:
            if c.get("action_type") == target:
                cost_per = float(c.get("value", 0))
                break

        return conversions, cost_per

    def _determine_creative_type(self, creative_data: dict, ad_name: str) -> str:
        obj_type = (creative_data.get("object_type") or "").lower()
        name_lower = ad_name.lower()

        if "video" in obj_type or "video" in name_lower:
            return "video"
        if "carousel" in name_lower:
            return "carousel"
        return "image"


# ---------------------------------------------------------------------------
# Claude-powered creative analyzer
# ---------------------------------------------------------------------------

TAXONOMY_PROMPT = """\
You are analyzing paid ads for JotPsych, an AI documentation tool for behavioral health clinicians.

For each ad below, assign taxonomy tags using EXACTLY these categories:

message_type: one of [value_prop, pain_point, social_proof, urgency, education, comparison]
hook_type: one of [question, statistic, testimonial, provocative_claim, scenario, direct_benefit]
cta_type: one of [try_free, book_demo, learn_more, see_how, start_saving_time, watch_video]
tone: one of [clinical, warm, urgent, playful, authoritative, empathetic]
visual_style: one of [photography, illustration, screen_capture, text_heavy, mixed_media, abstract]
subject_matter: one of [clinician_at_work, patient_interaction, product_ui, workflow_comparison, conceptual, data_viz]
color_mood: one of [brand_primary, warm_earth, cool_clinical, high_contrast, muted_soft, bold_saturated]
text_density: one of [headline_only, headline_subhead, detailed_copy, minimal_overlay]
headline_word_count: integer (count words in the headline)
uses_number: boolean (does the copy contain a specific number like "2 hours" or "90%"?)
uses_question: boolean (does the copy ask a question?)
uses_first_person: boolean (does the copy use "I"/"my" vs "you"/"your"?)
uses_social_proof: boolean (does it mention other clinicians, stats, or testimonials?)
copy_reading_level: float (estimate Flesch-Kincaid grade level)

Here are the ads:
{ads_json}

Return a JSON array with one object per ad, in the same order. Each object should have:
{{"meta_ad_id": "...", "message_type": "...", "hook_type": "...", ...all taxonomy fields...}}
"""

PORTFOLIO_PROMPT = """\
You are a quantitative creative strategist for JotPsych, an AI documentation tool for behavioral health clinicians.

Below is a table of all tagged ads with their taxonomy tags and performance metrics.
Analyze the portfolio and identify patterns.

{ads_table}

Provide your analysis as a JSON object with these keys:
- "top_performing_patterns": list of objects, each with "description", "avg_cost_per_conversion", "example_ads" (list of ad names), "taxonomy_combo" (dict of the taxonomy fields that define this pattern)
- "worst_performing_patterns": same structure
- "untested_combinations": list of objects with "description" and "taxonomy_combo" — promising combos not yet tried
- "recommendations": list of specific actionable strings
- "statistical_notes": list of caveats about sample sizes, confidence, etc.
"""

PLAYBOOK_PROMPT = """\
You are writing a creative playbook for JotPsych's ad team based on regression-style analysis of their Meta ads.

Here is the structured analysis:
{analysis_json}

Here is the raw ad data:
{ads_summary}

Write a comprehensive markdown playbook with these sections:

# JotPsych Creative Playbook

## Executive Summary
What works, what doesn't, in 3-4 sentences.

## Top 5 Performing Patterns
For each: the taxonomy combination, average cost per conversion, example ads, and why it likely works.

## Bottom 5 Performing Patterns
Same structure — what to avoid and why.

## Untested Combinations to Try
Promising taxonomy combos we haven't explored yet, with rationale.

## Creative Briefs for Next Batch
3-5 specific ad concepts to produce next, each with: headline direction, body copy direction, visual direction, target taxonomy tags.

## Statistical Notes
Sample sizes, confidence levels, caveats about the data.

Return ONLY the markdown content, no code fences.
"""


class CreativeAnalyzer:
    def __init__(self, client: Anthropic = None):
        if client is None:
            s = get_settings()
            client = Anthropic(api_key=s.ANTHROPIC_API_KEY)
        self.client = client

    def tag_ads(
        self, ads: list[ExistingAd], store: Store, batch_size: int = 15
    ) -> list[ExistingAd]:
        """Tag every un-tagged ad with CreativeTaxonomy via Claude. Saves to store."""
        to_tag = [a for a in ads if a.taxonomy is None]
        already_tagged = [a for a in ads if a.taxonomy is not None]

        if not to_tag:
            print("[analyzer] All ads already tagged, nothing to do.")
            return ads

        total_batches = (len(to_tag) + batch_size - 1) // batch_size
        print(f"[analyzer] {len(to_tag)} ads to tag in {total_batches} batches")

        newly_tagged: list[ExistingAd] = []
        for i in range(0, len(to_tag), batch_size):
            batch = to_tag[i : i + batch_size]
            batch_num = i // batch_size + 1
            print(
                f"[analyzer] Tagging batch {batch_num}/{total_batches} "
                f"({len(batch)} ads)..."
            )
            try:
                tag_results = self._tag_batch(batch)
                tags_by_id = {t["meta_ad_id"]: t for t in tag_results}

                for ad in batch:
                        tag_data = tags_by_id.get(ad.meta_ad_id)
                        if not tag_data:
                            print(
                                f"[analyzer] No tags returned for ad {ad.meta_ad_id}, skipping"
                            )
                            newly_tagged.append(ad)
                            continue

                        fmt = self._ad_format_from_creative_type(ad.creative_type)
                        tag_data.pop("meta_ad_id", None)

                        # Provide defaults for any None fields Claude returns
                        # (happens for ads with no copy text — usually video/carousel with empty creative)
                        str_fields = ["message_type", "hook_type", "cta_type", "tone",
                                      "visual_style", "subject_matter", "color_mood", "text_density"]
                        str_defaults = {
                            "message_type": "value_prop",
                            "hook_type": "direct_benefit",
                            "cta_type": "learn_more",
                            "tone": "warm",
                            "visual_style": "photography",
                            "subject_matter": "clinician_at_work",
                            "color_mood": "brand_primary",
                            "text_density": "headline_subhead",
                        }
                        for field in str_fields:
                            if tag_data.get(field) is None:
                                tag_data[field] = str_defaults[field]
                        if tag_data.get("headline_word_count") is None:
                            tag_data["headline_word_count"] = 0
                        if tag_data.get("copy_reading_level") is None:
                            tag_data["copy_reading_level"] = 8.0
                        for bool_field in ["uses_number", "uses_question", "uses_first_person", "uses_social_proof"]:
                            if tag_data.get(bool_field) is None:
                                tag_data[bool_field] = False

                        ad.taxonomy = CreativeTaxonomy(
                            **tag_data,
                            format=fmt,
                            platform=Platform.META,
                            placement="feed",
                        )
                        ad.analyzed_at = datetime.utcnow()
                        store.save_existing_ad(ad)
                        newly_tagged.append(ad)

            except Exception as e:
                print(f"[analyzer] Batch {batch_num} failed: {e}")
                newly_tagged.extend(batch)

        return already_tagged + newly_tagged

    def analyze_portfolio(self, ads: list[ExistingAd]) -> dict:
        """Ask Claude to find winning/losing patterns across all tagged ads."""
        tagged = [a for a in ads if a.taxonomy is not None]
        if not tagged:
            print("[analyzer] No tagged ads to analyze.")
            return {}

        ads_table = self._build_ads_table(tagged)
        prompt = PORTFOLIO_PROMPT.format(ads_table=ads_table)

        print(f"[analyzer] Analyzing portfolio of {len(tagged)} tagged ads...")
        resp = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = resp.content[0].text
        return self._parse_json_response(raw)

    def generate_playbook(self, ads: list[ExistingAd], analysis: dict) -> str:
        """Generate a markdown playbook and save to data/existing_creative/playbook.md."""
        ads_summary = self._build_ads_table(
            [a for a in ads if a.taxonomy is not None]
        )
        prompt = PLAYBOOK_PROMPT.format(
            analysis_json=json.dumps(analysis, indent=2, default=str),
            ads_summary=ads_summary,
        )

        print("[analyzer] Generating creative playbook...")
        resp = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )

        playbook_md = resp.content[0].text
        out_path = Path("data/existing_creative/playbook.md")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(playbook_md)
        print(f"[analyzer] Playbook saved to {out_path}")
        return playbook_md

    # -- Internal helpers -----------------------------------------------------

    def _tag_batch(self, batch: list[ExistingAd]) -> list[dict]:
        ads_json = json.dumps(
            [
                {
                    "meta_ad_id": ad.meta_ad_id,
                    "ad_name": ad.ad_name,
                    "headline": ad.headline or "",
                    "body": ad.body or "",
                    "cta_type": ad.cta_type or "",
                    "creative_type": ad.creative_type,
                    "campaign_name": ad.campaign_name,
                    "spend": ad.spend,
                    "clicks": ad.clicks,
                    "conversions": ad.conversions,
                    "cost_per_conversion": ad.cost_per_conversion,
                }
                for ad in batch
            ],
            indent=2,
        )

        prompt = TAXONOMY_PROMPT.format(ads_json=ads_json)
        resp = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = resp.content[0].text
        return self._parse_json_response(raw)

    def _build_ads_table(self, ads: list[ExistingAd]) -> str:
        rows: list[str] = []
        for ad in ads:
            t = ad.taxonomy
            rows.append(
                f"- {ad.ad_name} | spend=${ad.spend:.2f} | conv={ad.conversions} "
                f"| cpconv=${ad.cost_per_conversion or 0:.2f} "
                f"| msg={t.message_type} | hook={t.hook_type} | cta={t.cta_type} "
                f"| tone={t.tone} | vis={t.visual_style} | subj={t.subject_matter} "
                f"| color={t.color_mood} | density={t.text_density}"
            )
        return "\n".join(rows)

    def extract_briefs_from_playbook(self, playbook_md: str = None) -> list:
        """
        Parse the Creative Briefs section from the playbook into CreativeBrief objects.
        Reads from data/existing_creative/playbook.md if no text provided.
        """
        if playbook_md is None:
            path = Path("data/existing_creative/playbook.md")
            if not path.exists():
                print("[analyzer] No playbook found. Run analyze first.")
                return []
            playbook_md = path.read_text()

        prompt = (
            "Extract the Creative Briefs from this playbook. For each brief, output a JSON object.\n\n"
            "Output a JSON array where each element has:\n"
            "{\n"
            '  "target_audience": "bh_clinicians" or "smb_clinic_owners",\n'
            '  "value_proposition": "the core promise in one sentence",\n'
            '  "pain_point": "the specific problem being addressed",\n'
            '  "desired_action": "what the viewer should do",\n'
            '  "tone_direction": "tone guidance from the brief",\n'
            '  "visual_direction": "visual direction from the brief",\n'
            '  "key_phrases": ["specific headlines or phrases to use"],\n'
            '  "num_variants": 6,\n'
            '  "formats_requested": ["single_image", "video"],\n'
            '  "platforms": ["meta"]\n'
            "}\n\n"
            "Playbook:\n"
            f"{playbook_md}"
        )

        print("[analyzer] Extracting creative briefs from playbook...")
        resp = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )

        from engine.models import CreativeBrief, AdFormat as AF, Platform as P

        raw = self._parse_json_response(resp.content[0].text)
        briefs = []
        for data in raw:
            try:
                brief = CreativeBrief(
                    raw_input=f"[auto-generated from playbook] {data.get('value_proposition', '')}",
                    source="playbook",
                    target_audience=data.get("target_audience", "bh_clinicians"),
                    value_proposition=data["value_proposition"],
                    pain_point=data.get("pain_point", ""),
                    desired_action=data.get("desired_action", "Learn more about JotPsych"),
                    tone_direction=data.get("tone_direction", "empathetic"),
                    visual_direction=data.get("visual_direction", ""),
                    key_phrases=data.get("key_phrases", []),
                    num_variants=data.get("num_variants", 6),
                    formats_requested=[AF(f) for f in data.get("formats_requested", ["single_image", "video"])],
                    platforms=[P(p) for p in data.get("platforms", ["meta"])],
                )
                briefs.append(brief)
            except Exception as e:
                print(f"[analyzer] Failed to parse brief: {e}")

        print(f"[analyzer] Extracted {len(briefs)} briefs from playbook")
        return briefs

    @staticmethod
    def _parse_json_response(text: str):
        cleaned = re.sub(r"```(?:json)?\s*", "", text)
        cleaned = cleaned.strip().rstrip("`")
        return json.loads(cleaned)

    @staticmethod
    def _ad_format_from_creative_type(creative_type: str) -> AdFormat:
        mapping = {
            "video": AdFormat.VIDEO,
            "carousel": AdFormat.CAROUSEL,
            "image": AdFormat.SINGLE_IMAGE,
        }
        return mapping.get(creative_type, AdFormat.SINGLE_IMAGE)
