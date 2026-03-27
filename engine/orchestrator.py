"""
Orchestrator — runs the full daily cycle and one-off commands.

This is the main entry point. It wires all pipeline stages together.

Daily cycle (scheduled):
1. Pull performance data from Meta + Google
2. Run decision engine (scale/kill/wait)
3. Execute decisions (pause/scale budget on platforms)
4. Run regression model
5. Post Slack digest

On-demand:
- Submit idea → generate variants
- Review variants → deploy approved
"""

from __future__ import annotations

import json
from datetime import date
from typing import Optional

from engine.store import Store
from engine.intake.parser import IntakeParser
from engine.generation.generator import CreativeGenerator
from engine.review.reviewer import ReviewPipeline
from engine.deployment.deployer import AdDeployer
from engine.tracking.tracker import PerformanceTracker
from engine.decisions.engine import DecisionEngine
from engine.regression.model import CreativeRegressionModel
from engine.notifications import SlackNotifier
from engine.models import AdStatus, DecisionVerdict
from engine.analysis.analyzer import MetaAdsExporter, CreativeAnalyzer
from engine.memory.creative_memory import CreativeMemoryManager
from engine.memory.playbook_translator import PlaybookTranslator
from engine.memory.builder import MemoryBuilder
from engine.memory.models import GenerationContext


class Orchestrator:
    def __init__(
        self,
        store: Optional[Store] = None,
        notifier: Optional[SlackNotifier] = None,
    ):
        self.store = store or Store()
        self.notifier = notifier or SlackNotifier()

        # Pipeline stages
        self.parser = IntakeParser()
        self.generator = CreativeGenerator()
        self.reviewer = ReviewPipeline(self.store)
        self.deployer = AdDeployer(self.store)
        self.tracker = PerformanceTracker(self.store)
        self.decisions = DecisionEngine(self.store)
        self.regression = CreativeRegressionModel(self.store)
        self.exporter = MetaAdsExporter()
        self.analyzer = CreativeAnalyzer()
        
        # Memory system (v2 with three-layer architecture)
        self.memory_builder = MemoryBuilder(self.store)
        self.memory_manager = CreativeMemoryManager(self.store)  # Legacy
        self.playbook_translator = PlaybookTranslator(self.store)

    # ------------------------------------------------------------------
    # Analysis: Export → Tag → Analyze → Playbook
    # ------------------------------------------------------------------

    def export_meta_ads(self) -> dict:
        """Export all existing Meta ads with creative + performance data."""
        ads = self.exporter.export_all(self.store)
        return {
            "exported": len(ads),
            "with_conversions": len([a for a in ads if a.conversions > 0]),
            "total_spend": sum(a.spend for a in ads),
        }

    def analyze_existing_ads(self) -> dict:
        """Full analysis pipeline: tag → analyze → playbook → regression."""
        ads = self.store.get_all_existing_ads()
        if not ads:
            return {"error": "No ads exported yet. Run 'export' first."}

        tagged = self.analyzer.tag_ads(ads, self.store)
        analysis = self.analyzer.analyze_portfolio(tagged)
        playbook = self.analyzer.generate_playbook(tagged, analysis)

        reg_result = self.regression.run()
        if reg_result:
            self.store.save_regression(reg_result)

        return {
            "ads_tagged": len([a for a in tagged if a.taxonomy is not None]),
            "analysis_keys": list(analysis.keys()) if isinstance(analysis, dict) else [],
            "playbook_length": len(playbook),
            "regression": {
                "r_squared": reg_result.r_squared,
                "observations": reg_result.n_observations,
            } if reg_result else {"status": "insufficient_data"},
        }

    # ------------------------------------------------------------------
    # On-demand: Idea → Variants
    # ------------------------------------------------------------------

    def submit_idea(self, raw_text: str, source: str = "manual") -> dict:
        """Full pipeline: parse idea → generate variants → notify.

        Always uses the v2 multi-agent copy pipeline (HeadlineAgent + BodyCopyAgent +
        CTAAgent) with Playwright HTML template rendering for images.
        """
        brief = self.parser.parse(raw_text, source)
        self.store.save_brief(brief)

        context, rejection_feedback, approval_feedback = self._get_generation_context()
        variants = self.generator.generate_with_templates(
            brief,
            use_v2=True,
            store=self.store,
            rejection_feedback=rejection_feedback,
            approval_feedback=approval_feedback,
            generation_context=context,
        )

        for v in variants:
            self.store.save_variant(v)

        self.notifier.notify_variants_generated(brief.id, variants)

        return {
            "brief_id": brief.id,
            "variants_generated": len(variants),
            "brief": brief.model_dump(),
        }

    def submit_idea_templates(
        self,
        raw_text: str,
        source: str = "manual",
        use_selector: bool = True,
    ) -> dict:
        """
        Full pipeline using Playwright template rendering instead of AI image gen.

        parse idea → generate copy (v2) → select templates per variant → render
        pixel-perfect PNGs/MP4s → notify.
        """
        brief = self.parser.parse(raw_text, source)
        self.store.save_brief(brief)

        context, rejection_feedback, approval_feedback = self._get_generation_context()

        variants = self.generator.generate_with_templates(
            brief,
            use_v2=True,
            store=self.store,
            rejection_feedback=rejection_feedback,
            approval_feedback=approval_feedback,
            generation_context=context,
            use_selector=use_selector,
        )

        for v in variants:
            self.store.save_variant(v)

        self.notifier.notify_variants_generated(brief.id, variants)

        return {
            "brief_id": brief.id,
            "variants_generated": len(variants),
            "asset_types": {
                "image": len([v for v in variants if v.asset_type == "image"]),
                "video": len([v for v in variants if v.asset_type == "video"]),
            },
            "templates_used": list({v.asset_path.split("/")[-1].rsplit("_", 1)[0] for v in variants}),
            "brief": brief.model_dump(),
        }

    def _get_generation_context(self) -> tuple[GenerationContext, list, list]:
        """
        Build structured GenerationContext from the three-layer creative memory.
        Returns context object plus raw feedback lists for backwards compatibility.
        """
        memory = self.memory_builder.build()
        self.store.save_memory(memory)
        
        context = self.memory_builder.build_generation_context(memory)
        
        rejection_feedback = self.memory_manager.get_rejection_feedback(
            self.memory_manager.load_or_create(), limit=10
        )
        approval_feedback = self.memory_manager.get_approval_feedback(
            self.memory_manager.load_or_create(), limit=10
        )
        
        return context, rejection_feedback, approval_feedback

    def _get_legacy_generation_context(self) -> tuple:
        """Legacy method for backwards compatibility."""
        top_patterns = None
        regression = self.store.get_latest_regression()
        if regression:
            top_patterns = regression.top_positive_features[:5]

        rejection_feedback = None
        rejections = self.reviewer.get_rejection_feedback()
        if rejections:
            rejection_feedback = rejections[-10:]

        approval_feedback = None
        approvals = self.reviewer.get_approval_feedback()
        if approvals:
            approval_feedback = approvals[-10:]

        return top_patterns, rejection_feedback, approval_feedback

    def generate_from_playbook(self) -> dict:
        """
        Automated loop closure: read playbook → extract briefs → generate ads.
        No human intervention required. Uses v2 pipeline with three-layer
        creative memory and regression insights.
        """
        briefs = self.analyzer.extract_briefs_from_playbook()
        if not briefs:
            return {"error": "No briefs extracted from playbook."}

        context, rejection_feedback, approval_feedback = self._get_generation_context()

        all_variants = []
        for i, brief in enumerate(briefs):
            print(f"[orchestrator] Generating ads for brief {i + 1}/{len(briefs)}: {brief.value_proposition[:60]}...")
            self.store.save_brief(brief)

            variants = self.generator.generate_with_templates(
                brief,
                use_v2=True,
                store=self.store,
                rejection_feedback=rejection_feedback,
                approval_feedback=approval_feedback,
                generation_context=context,
            )

            for v in variants:
                self.store.save_variant(v)

            all_variants.extend(variants)
            self.notifier.notify_variants_generated(brief.id, variants)

        print(f"[orchestrator] Generated {len(all_variants)} total variants from {len(briefs)} briefs")
        return {
            "briefs_processed": len(briefs),
            "total_variants_generated": len(all_variants),
            "variants_per_brief": [
                {"brief_value_prop": b.value_proposition[:60], "variants": len([v for v in all_variants if v.brief_id == b.id])}
                for b in briefs
            ],
        }

    def regenerate_assets(self, brief_id: Optional[str] = None) -> dict:
        """
        Regenerate missing or corrupt assets for existing variants.
        
        If brief_id is provided, only regenerate for that brief.
        Otherwise, regenerate for all briefs with missing assets.
        """
        from pathlib import Path
        
        briefs = self.store.get_all_briefs()
        if brief_id:
            briefs = [b for b in briefs if b.id == brief_id]
            if not briefs:
                return {"error": f"Brief {brief_id} not found"}
        
        regenerated = []
        skipped = []
        
        for brief in briefs:
            # Get variants for this brief
            variants = [v for v in self.store.get_all_variants() if v.brief_id == brief.id]
            if not variants:
                continue
            
            # Check which assets are missing or corrupt
            missing_assets = []
            for v in variants:
                asset_path = Path(v.asset_path)
                if not asset_path.exists():
                    missing_assets.append(v)
                elif asset_path.suffix in ['.png', '.jpg', '.jpeg'] and asset_path.stat().st_size < 10240:
                    missing_assets.append(v)
                elif asset_path.suffix == '.mp4' and asset_path.stat().st_size < 102400:
                    missing_assets.append(v)
            
            if not missing_assets:
                skipped.append(brief.id)
                continue
            
            print(f"[orchestrator] Regenerating {len(missing_assets)} assets for brief {brief.id[:8]}...")
            
            # Build copy_variants dict from existing variants
            copy_variants = []
            for v in missing_assets:
                copy_variants.append({
                    "headline": v.headline,
                    "primary_text": v.primary_text,
                    "taxonomy": v.taxonomy.model_dump() if v.taxonomy else {},
                })
            
            # Regenerate with force_regenerate=True
            new_paths = self.generator.generate_assets(
                brief, 
                copy_variants,
                force_regenerate=True,
            )
            
            # Update variant asset paths if changed
            for i, v in enumerate(missing_assets):
                if i < len(new_paths):
                    v.asset_path = new_paths[i]
                    self.store.save_variant(v)
            
            regenerated.append({
                "brief_id": brief.id,
                "variants_regenerated": len(missing_assets),
            })
        
        return {
            "regenerated": regenerated,
            "skipped": len(skipped),
            "total_regenerated": sum(r["variants_regenerated"] for r in regenerated),
        }

    # ------------------------------------------------------------------
    # On-demand: Deploy approved variants
    # ------------------------------------------------------------------

    def deploy_approved(self, campaign_id: str, adset_or_adgroup_id: str) -> list:
        """Deploy all approved variants to platforms."""
        approved = self.store.get_variants_by_status(AdStatus.APPROVED)
        if not approved:
            print("No approved variants to deploy.")
            return []

        deployed = []
        for variant in approved:
            try:
                result = self.deployer.deploy_variant(variant, campaign_id, adset_or_adgroup_id)
                deployed.append(result)
            except Exception as e:
                print(f"Failed to deploy {variant.id}: {e}")

        if deployed:
            platform = deployed[0].taxonomy.platform.value
            self.notifier.notify_deployment(deployed, platform)

        return deployed

    # ------------------------------------------------------------------
    # Scheduled: Daily cycle
    # ------------------------------------------------------------------

    def run_daily_cycle(self, report_date: Optional[date] = None) -> dict:
        """
        Full daily cycle. Call this from a scheduler (cron, Airflow, etc.).

        1. Pull performance data
        2. Make scale/kill/wait decisions
        3. Execute kill decisions automatically
        4. Run regression
        5. Send Slack digest
        """
        if report_date is None:
            report_date = date.today()

        results = {"date": report_date.isoformat()}

        # 1. Pull performance
        print(f"[{report_date}] Pulling performance data...")
        try:
            snapshots = self.tracker.pull_daily(report_date)
            results["snapshots_pulled"] = len(snapshots)
        except Exception as e:
            print(f"Performance pull failed: {e}")
            results["snapshots_pulled"] = 0

        # 2. Make decisions
        print(f"[{report_date}] Running decision engine...")
        decisions = self.decisions.run_daily(report_date)
        results["decisions"] = {
            "scale": len([d for d in decisions if d.verdict == DecisionVerdict.SCALE]),
            "kill": len([d for d in decisions if d.verdict == DecisionVerdict.KILL]),
            "wait": len([d for d in decisions if d.verdict == DecisionVerdict.WAIT]),
        }

        # 3. Auto-execute kills (scales require manual confirmation)
        kills = [d for d in decisions if d.verdict == DecisionVerdict.KILL]
        for decision in kills:
            try:
                variant = self.store.get_variant(decision.ad_variant_id)
                self.deployer.kill_variant(variant)
                decision.executed = True
                self.store.save_decision(decision)
            except Exception as e:
                print(f"Failed to kill {decision.ad_variant_id}: {e}")

        results["auto_killed"] = len([d for d in kills if d.executed])

        # 4. Run regression (all-time with decay + rolling window)
        print(f"[{report_date}] Running regression models...")
        try:
            reg_result = self.regression.run(use_weights=True)
            rolling_result = self.regression.run_rolling(window_days=30)
            
            if reg_result:
                self.store.save_regression(reg_result)
                self.notifier.notify_regression_update(reg_result)
                results["regression"] = {
                    "r_squared": reg_result.r_squared,
                    "observations": reg_result.n_observations,
                    "weighted": reg_result.sample_weights_used,
                }
                
                memory = self.memory_builder.build()
                self.store.save_memory(memory)
                
                results["memory"] = {
                    "winning_patterns": len(memory.statistical.winning_patterns),
                    "approval_clusters": len(memory.editorial.approval_clusters),
                    "fatigue_alerts": len(memory.statistical.fatiguing_patterns),
                    "data_quality": memory.data_quality_score,
                }
            else:
                results["regression"] = {"status": "insufficient_data"}
                
            if rolling_result:
                results["rolling_regression"] = {
                    "r_squared": rolling_result.r_squared,
                    "observations": rolling_result.n_observations,
                    "window_days": rolling_result.window_days,
                }
        except Exception as e:
            print(f"Regression failed: {e}")
            results["regression"] = {"status": "error", "message": str(e)}

        # 5. Send Slack digest
        if decisions:
            self.notifier.notify_daily_decisions(decisions)

        print(f"[{report_date}] Daily cycle complete.")
        return results


# CLI entry point
if __name__ == "__main__":
    import sys

    orchestrator = Orchestrator()

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "daily":
            result = orchestrator.run_daily_cycle()
            print(result)

        elif command == "idea":
            if len(sys.argv) < 3:
                print("Usage: python -m engine.orchestrator idea 'your idea here'")
                sys.exit(1)
            idea = " ".join(sys.argv[2:])
            result = orchestrator.submit_idea(idea)
            print(f"Brief: {result['brief_id']}")
            print(f"Variants generated: {result['variants_generated']}")

        elif command == "review":
            pending = orchestrator.reviewer.get_pending_review()
            print(f"{len(pending)} variants pending review")
            for v in pending:
                print(f"  {v.id[:8]} | {v.headline[:60]}")

        elif command == "regression":
            playbook = orchestrator.regression.get_creative_playbook()
            print(json.dumps(playbook, indent=2, default=str))

        elif command == "export":
            print("Exporting Meta ads...")
            result = orchestrator.export_meta_ads()
            print(json.dumps(result, indent=2))

        elif command == "analyze":
            print("Running full analysis pipeline...")
            result = orchestrator.analyze_existing_ads()
            print(json.dumps(result, indent=2, default=str))

        elif command == "generate":
            print("Generating ads from playbook...")
            result = orchestrator.generate_from_playbook()
            print(json.dumps(result, indent=2, default=str))

        elif command == "full-cycle":
            print("=== FULL CYCLE: export → analyze → generate ===")
            print("\n--- Step 1: Export Meta ads ---")
            export_result = orchestrator.export_meta_ads()
            print(json.dumps(export_result, indent=2))

            print("\n--- Step 2: Analyze + Playbook + Regression ---")
            analysis_result = orchestrator.analyze_existing_ads()
            print(json.dumps(analysis_result, indent=2, default=str))

            print("\n--- Step 3: Generate ads from playbook ---")
            gen_result = orchestrator.generate_from_playbook()
            print(json.dumps(gen_result, indent=2, default=str))

            print("\n=== FULL CYCLE COMPLETE ===")

        elif command == "regenerate-assets":
            brief_id = sys.argv[2] if len(sys.argv) > 2 else None
            print("Regenerating missing/corrupt assets...")
            result = orchestrator.regenerate_assets(brief_id)
            print(json.dumps(result, indent=2, default=str))

        elif command == "idea-templates":
            if len(sys.argv) < 3:
                print("Usage: python -m engine.orchestrator idea-templates 'your idea here'")
                sys.exit(1)
            idea = " ".join(sys.argv[2:])
            result = orchestrator.submit_idea_templates(idea, use_selector=True)
            print(f"Brief: {result['brief_id']}")
            print(f"Variants generated: {result['variants_generated']}")
            print(f"Asset types: {result['asset_types']}")

        else:
            print(f"Unknown command: {command}")
            print("Commands: daily, idea, idea-templates, review, regression, export, analyze, generate, full-cycle, regenerate-assets")
    else:
        print("JotPsych Ads Engine Orchestrator")
        print("Commands: daily, idea '<text>', idea-templates '<text>', review, regression, export, analyze, generate, full-cycle, regenerate-assets [brief_id]")
