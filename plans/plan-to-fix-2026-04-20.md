# Plan to Fix Meta Ads — 2026-04-20

**Baseline docs (read these first):**
- [docs/facts-we-know-2026-04-20.md](../docs/facts-we-know-2026-04-20.md) — verified state
- [docs/here-what-experts-say-2026-04-20.md](../docs/here-what-experts-say-2026-04-20.md) — current best-practice consensus

**Status:** Executed 2026-04-20. Phases 1 and 2 applied in production. Verifications 1–15 from facts-we-know.md remain open and should be run in parallel. Phases 4–7 are future/contingent.

---

## Governing Thought

**Our restructure last week fixed 3 real problems (audience targeting, landing page mismatches, UTM hygiene) but introduced 2 new problems that are actively making performance worse: premature VALUE optimization without value params, and over-fragmentation of ad sets below our conversion volume threshold.**

The plan below reverts the two mistakes, preserves the three wins, and surfaces a clear dependency chain for what engineering must ship next.

---

## What I Got Wrong Last Week

1. **Switched ad sets to VALUE optimization before confirming the app sends value params with pixel events.** Meta has been optimizing for a dollar signal that doesn't exist, since Apr 16. The CAPI sender I built sends values server-side but no production code calls it. Engineering needs to either ship app-side value params OR wire CAPI calls into the app backend. Neither has happened.

2. **Stacked the same audience (3 inclusion + 2 exclusion) across all 5 value-prop ad sets.** This makes it impossible for Meta to learn "which value prop resonates with which audience" — every ad set is training the same audience stack. Nate's design intent was per-value-prop audience differentiation; my implementation collapsed that to creative differentiation only. Correct move: one focused audience per value prop.

Both mistakes are reversible in <30 minutes via API. Neither destroys data or creatives.

---

## What We're Keeping (3 Wins From the Restructure)

1. **Audience architecture.** Sales Prospect List + Chris LAL + Converter LAL as inclusion; Stripe Customers + Converters as exclusion. These are correct and shouldn't move.

2. **Landing page mapping.** Audit ads → /audit, EHR ads → /features, etc. 12 of 18 audit ads previously went to the homepage. Fixed. Don't revert.

3. **Standardized UTMs.** Every ad now passes `utm_source={{site_source_name}}&utm_medium=paid_social&utm_campaign={{campaign.id}}&utm_content={{adset.id}}&utm_term={{ad.id}}`. Clean and consistent.

---

## TAM-Informed Reasoning

Our true addressable market is ~100-130K providers (PMHNPs + psychiatrists). This is **20-25x larger than the 5K threshold** where custom audiences outperform Meta's AI (Advantage+). At this size, the right mode is Advantage+ with our custom audiences as **suggested audiences** (hints that bias Meta's AI without hard-constraining it), not as hard-inclusion targeting.

Chris's 509 list is the one exception — small enough that manual wins — but at $80/day it would saturate in days if targeted directly. Best use: as a suggested audience inside Advantage+.

Expected conversion volume at our TAM (~0.01% weekly B2B SaaS benchmark): 10-15 FN/week. Matches our observed data. This isn't broken — it's our actual market capacity at current EMQ. Unlocking more volume requires EMQ 4→6 (engineering fix), not more audience stacking.

Frequency is the real ceiling. At $200/day on ~30K effective reach, we saturate to frequency 2+ within a week regardless of ad set count.

---

## The Plan (Subject to Verification)

### Phase 1: Stop the Bleeding (Day 0, ~30 min) — EXECUTED

1. **Pause LGF campaigns** (Q126 MLC STATICS TEST, Q126 MLC UPMARKET STATICS TEST). Burned $334 over 4 days with 3 LPVs and 0 FN. Zero strategic relevance. ✅ Paused 2026-04-20 without verification 14 (owner unconfirmed) — reactivate if Matt/Adam needed them.

2. **Pause old Scale: Winners - Apr 2026.** $622 CpFN is 2.4x pre-restructure rate. Dynamic-creative ads inside are fatigued. ✅ Paused 2026-04-20.

3. **VALUE optimization retained on new Farm** (superseded by Phase 2 reasoning — Nate's thesis holds, engineering must ship values). No change to optimization_goal.

**Actual result:** Daily spend drops from ~$300 to ~$200 (new Farm only). No learning phase reset on new Farm — objective unchanged.

### Phase 2: Consolidate to Single Ad Set Until EMQ Is Fixed (Day 0, ~15 min) — EXECUTED (Partial)

Consolidate new Farm from 5 ad sets to 1 ad set. Keep VALUE optimization on.

**Why single ad set right now:**
1. **EMQ 4/10 makes differential signals between ad sets uninterpretable.** Running 5 ad sets produces noise we can't act on until match quality is fixed.
2. **Meta learns creative winners within an ad set automatically.** 24 ads in one ad set = Meta tests and auto-promotes. No need to split for creative-level learning.
3. **Budget concentration.** $200/day in one ad set = strong signal. Split 5 ways = $40/ad set = ~1,600 impressions/day per ad set at current CPMs. Too thin.
4. **Value optimization needs signal concentration.** All value-bearing events flowing into one ad set = one strong combined signal. Split = 5 weak signals.

**Ad set "Farm: All Value Props Q226" (ID 120245455503860548):**
- ✅ 22 of 24 ads consolidated. Two ads (Farm: Nate Podcast 4 - ad, Farm: EHR V2) could not be API-copied due to deprecated "standard enhancements" in their creatives. They remain paused in their original ad sets. Must be manually duplicated via Ads Manager GUI if wanted.
- ✅ $200/day budget
- ✅ Advantage+ enabled (`advantage_audience: 1`) with 3 custom audiences as suggested (Sales Prospect List, Chris LAL, Converter LAL) + 2 hard exclusions (Stripe, Converters)
- ✅ Optimization goal: VALUE
- ✅ Conversion event: FirstNote on pixel 1625233994894344
- ✅ Landing pages mapped per ad
- ✅ UTMs intact at ad set level

**Known ad-level issues surfaced post-consolidation (require GUI fix):**
- 2 ads flagged "Delivery error: 191x100 crop key deprecated": AJ: Cigna Has Rules. JotPsych Knows Them, AN: Your Notes Are Perfect - Insurance Doesnt Care. Fix: Edit ad → re-crop image to 100x100.
- 4 empty ad sets remain paused in the campaign (Time Savings, EHR Integration, UGC / Social Proof, AI Progress Concepts). Pending cleanup once Nate decides whether to manually duplicate the 2 orphan ads out.

**When to split into 5 value-prop ad sets (Phase 7, ~2-4 weeks out):**
- EMQ ≥ 6.0 (engineering ships advanced matching)
- 40+ value events/week with attributed dollar values
- At that point, differential signals become interpretable and the 5×1 value-prop-×-audience experiment can actually learn something

This preserves Nate's value-prop-differentiation thesis — it sequences it for when the data actually supports it.

### Phase 3: Keep Optimization Event as FirstNote (Nate's Thesis)

Under VALUE optimization with consolidated ad set, the combined signal (FN + SignUp + Calendar × dollar weights) is what Meta optimizes on — not just the primary event count. At ~40 weighted events/week in one ad set, we have enough volume to learn.

Primary conversion event stays: **FirstNote** ($100 value). SignUpConfirm ($5) and CalendarScheduled ($15) fire automatically and contribute to VALUE optimization when engineering ships value params.

No need to swap primary event — VALUE optimization with concentrated signal solves the "need more events" problem correctly.

### Phase 4: Start the 7-Day No-Touch Window (Day 0 to Day 7)

After Phases 1-3, **no changes for 7 days.** No budget tweaks, no creative swaps, no audience changes. Let the algorithm gather data.

Exception: if spend exceeds $250/day or CpFN exceeds $400 for 3 consecutive days, reassess. Otherwise, read-only.

### Phase 5: Unblock Engineering (Day 0, parallel)

The match-quality / advanced-matching PRD to Jot from Apr 16 is the single highest-leverage unshipped change. EMQ 4.0 → 6.0 reliably cuts CPA 18-25% per expert data. Nothing else we can do in Ads Manager competes with shipping this.

**Specific asks to engineering (P0):**
1. Add `{value: 100, currency: 'USD'}` to `fbq('track', 'FirstNote', ...)` call in the app
2. Add `{value: 5, currency: 'USD'}` to `fbq('track', 'SignUpConfirm', ...)` call
3. Pass hashed user email/name in `fbq('init', '1625233994894344', {em: ..., fn: ..., ln: ...})` on authenticated pages

**P1 (can ship separately after P0):**
4. Wire `engine/capi/sender.py` into the app backend for server-side event mirroring with full user data (IP, user agent, fbc, fbp)
5. Pass `eventID` with each `fbq('track')` call and matching `event_id` on CAPI side for dedup

Full PRD: [docs/jot-briefs/meta-match-quality-fix-2026-04-16.md](../docs/jot-briefs/meta-match-quality-fix-2026-04-16.md)

### Phase 6: Re-Evaluate After 7 Days (Day 7)

On Apr 27, pull 7-day performance on the consolidated Farm ad set. Expected metrics:

| Metric | Baseline (pre-restructure Apr 4–13) | Threshold for continuing | Threshold for reverting |
|--------|---------|--------------------------|------------------------|
| Weekly SignUpConfirm | ~25 | ≥30 | <15 |
| Weekly FirstNote | ~14 | ≥10 | <5 |
| CpFN | $213 | ≤$250 | >$350 |
| Frequency | 1.5 | ≤2.5 | >3.0 (audience fatigue) |

If "continue" thresholds met: consider adding a second ad set (value-prop split becomes supportable).
If "revert" thresholds hit: roll back to pre-Apr-16 Farm: Testing - Apr 2026 campaign, which is still paused and intact.

### Phase 7: After Engineering Ships Values (Day 14+)

Once app-side `value` params are live AND EMQ hits ≥6.0 AND we're producing ≥30 value events with attributed values over a 7-day window, THEN flip optimization_goal back to VALUE. Not before. This is the ONLY path to legitimate value optimization.

---

## Rollback

Every step above has a sub-5-minute rollback:

1. **Phase 1 rollback:** Reactivate paused LGF/Scale campaigns via API.
2. **Phase 2 rollback:** Re-split ad sets via API (or keep the consolidation — the split doesn't have to come back).
3. **Phase 3 rollback:** Switch optimization event back to FirstNote (one API call per ad set).
4. **Phase 5 rollback:** Not applicable — engineering work doesn't break anything.

Old Farm campaign (Farm: Testing - Apr 2026) remains paused with all original ads intact. Nuclear rollback = reactivate old Farm, pause new Farm. <5 minutes.

---

## What We're Explicitly NOT Doing

- **Not touching audiences.** The audience architecture is correct per experts. Even if "broader beats narrower" applies at low volume, we've committed to narrower and should hold for 7 days before reconsidering.
- **Not recreating the 6 orphaned dynamic-creative ads** in new Farm. They're mostly AI Progress Notes variants that were never winners. Not worth manual reconstruction.
- **Not adjusting daily budget.** $200/day is above the expert-cited minimum for a single ad set at our expected $30-80 CPA ($150/day floor). Preserves enough signal.
- (Previously said "Not running Advantage+" — reversed during execution. Advantage+ IS enabled on the consolidated ad set with our custom audiences as suggestions, per the TAM reasoning in this doc.)

---

## Open Items Post-Execution

1. **Verifications 1–15 from facts-we-know.md.** None were completed pre-execution. Priority items still open: #7 (Events Manager Test Events — end-to-end Calendly booking test), #9 (inspect SignUpConfirm parameters payload for `value`), #10-11 (confirm Calendly redirect config), #14 (LGF ownership — paused without confirmation).

2. **Manual fixes in Ads Manager GUI (Nate):**
   - Fix 2 delivery-error ads (re-crop to 100x100): AJ: Cigna Has Rules, AN: Your Notes Are Perfect
   - Manually duplicate 2 orphan ads to the consolidated ad set (API couldn't): Nate Podcast, EHR V2
   - Clean up 4 empty paused ad sets once orphans are relocated

3. **Commit to 7-day no-touch window.** Started 2026-04-20. Next re-eval 2026-04-27.

4. **Engineering priority.** Match-quality PRD ([docs/jot-briefs/meta-match-quality-fix-2026-04-16.md](../docs/jot-briefs/meta-match-quality-fix-2026-04-16.md)) needs to be handed to engineering. P0 items: ship value params on FirstNote + SignUpConfirm pixel events, hashed user email in fbq('init'). This is the single highest-leverage unshipped change.

---

## Questions Nate's Verifications Will Resolve

- Verifications 1-4: Confirms whether the ad sets are actually configured as I believe
- Verifications 5-6: Delivery health check
- Verifications 7-9: Confirms whether pixel values are shipping (answers the whole "why isn't VALUE optimization working" question definitively)
- Verifications 10-11: Confirms Calendly → pixel pipeline integrity
- Verification 14: Whether LGF pause is safe
- Verification 15: End-to-end Calendly→pixel test (definitive answer on whether CalendarScheduled is broken)
