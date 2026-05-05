---
title: "Meta Ads State Snapshot — 24hr Roll-up (Apr 20-21)"
date: 2026-04-21
author: Nate + Claude
memory_target: Long-term memory
scope: Canonical state of the Meta Ads account after Apr 20 consolidation + Apr 21 script hardening
confidence: high
supersedes: Apr 16 structural assumptions (see meta-pixel-gtm-architecture-correction and meta-custom-conversions-values briefs for the two architectural corrections)
sources:
  - file: CHANGELOG.md (entries 2026-04-21, 2026-04-20 x3, 2026-04-16)
  - file: plans/plan-to-fix-2026-04-20.md
  - file: docs/facts-we-know-2026-04-20.md
  - file: docs/here-what-experts-say-2026-04-20.md
  - brief: docs/jot-briefs/meta-pixel-gtm-architecture-correction-2026-04-20.md
  - brief: docs/jot-briefs/meta-custom-conversions-values-2026-04-20.md
  - manifest: data/custom-conversions/valued-conversions-2026-04-20.json
  - file: ~/.claude/CLAUDE.md (Agency Rules section)
---

# Meta Ads State Snapshot — 24hr Roll-up (Apr 20-21)

**Date:** 2026-04-21
**Memory target:** Long-term memory
**Scope:** Canonical current state of Meta Ads so Jot can answer any ads question tomorrow without re-reading the conversation
**Status:** Canonical as of 2026-04-21. Ad set in 7-day no-touch window (re-eval 2026-04-27). Not action-required.

---

## TL;DR

Between 2026-04-20 and 2026-04-21 we corrected two architectural mistakes from the Apr 16 restructure, consolidated Farm: Testing - Q226 from 5 value-prop ad sets into a single ad set running Advantage+ audience, created 3 Meta Custom Conversions with dollar values so VALUE optimization has real signal without waiting on engineering, paused the LGF campaigns and the old OUTCOME_LEADS Scale campaign, and committed three durable operating rules to global CLAUDE.md (never-delete, engineering-last-resort, Nate-time-second-last-resort). The account is now in a defensible "hands off for 7 days" state with a single active ad set at $200/day optimizing on a FirstNote-bound Custom Conversion valued at $100. GDN-789 remains the outstanding engineering ask for match-quality uplift (EMQ 4→6) but is no longer blocking value optimization.

---

## What Jot Should Commit to Memory

1. **The only active Meta campaign right now is `Farm: Testing - Q226` (id `120245455503210548`, OUTCOME_SALES).** Inside it, the only active ad set is `Farm: All Value Props Q226` (id `120245455503860548`) at $200/day with `optimization_goal=VALUE`. Every other Farm ad set in that campaign is paused and empty or near-empty. Every other campaign is paused.

2. **VALUE optimization is bound to the `FirstNote (Valued)` Custom Conversion, not the raw FirstNote pixel event.** The ad set's `promoted_object.pixel_rule` references the rule `{"and": [{"event_type": {"eq": "FirstNote"}}]}`. Meta counts every FirstNote fire at $100 via the Custom Conversion's `default_conversion_value`. SignUpConfirm ($5) and CalendarScheduled ($15) fire with their own Custom Conversion default values.

3. **Three durable operating rules now live in global `~/.claude/CLAUDE.md` under Agency Rules.** (a) Never delete; always pause/disable/archive — rollback must be possible. (b) Engineering asks are last resort — exhaust APIs, scripts, configs, and platform-native capabilities first. (c) Nate's time is second-last resort — default to doing work via API/script, only involve Nate for approvals, product decisions, and human-only tasks.

4. **The Apr 16 match-quality PRD is architecturally superseded in two places but its business case still stands.** It proposed modifying `fbq('init')` / `fbq('track')` directly (wrong — app uses GTM-KL9RPN9V exclusively), and it asked engineering to ship value params on pixel events (wrong — Meta does this natively via Custom Conversions). The remaining valid ask is advanced matching via dataLayer enrichment → GTM Meta tag config — filed as Linear `GDN-789`, assigned to Jot.

5. **The Advantage+ audience mode is on.** The three custom audiences (Sales Prospect List - BH Clinics, Lookalike - BH Clinic Prospects 1%, Lookalike - First Note Converters 1%) are configured as **suggested audiences** — Meta treats them as hints and explores beyond them. Exclusions (Stripe Customers Auto-Exclusion, Converters - First Note Completers) are hard and remain respected.

6. **Two orphan ads remain paused in old ad sets, per never-delete rule.** `Farm: EHR V2` and `Farm: Nate Podcast 4 - ad` couldn't be copied to the consolidated ad set because their creatives had a deprecated `standard_enhancements` field that Meta's copy endpoint rejects. They exist in paused ad sets and will not spend. Manually duplicating them via GUI is a low-priority option.

7. **The NPPES audience builder is now resumable.** `scripts/build-nppes-audience.py` writes per-(query,state) results to `data/audiences/nppes-checkpoint.json` after every state, honors a 1000-skip NPPES API cap, and retries transient failures with exponential backoff. Re-running the script resumes from the checkpoint rather than restarting. The NPPES audience upload to Meta has NOT been confirmed complete — the upload portion may still need a successful full run.

8. **The 7-day no-touch window started 2026-04-20.** Next re-evaluation is 2026-04-27. During the window: no budget changes, no creative swaps, no audience changes, no optimization flips. Any edit re-triggers Meta's learning phase from scratch. Exception threshold: spend > $250/day OR CpFN > $400 for 3 straight days.

9. **The three Custom Conversions verify automatically as matching events fire.** FirstNote (Valued) and SignUpConfirm (Valued) should verify within hours given existing event volume (6 FN and 11 SignUp in the last 7 days account-wide). CalendarScheduled (Valued) may verify slower because production bookings have been near-zero — but the end-to-end pixel pipe was verified working on 2026-04-20 via Playwright and an Events Manager Test Events run.

10. **Audience saturation risk is real but not yet imminent.** At $200/day against ~100-130K TAM of PMHNPs + psychiatrists, frequency is expected to reach ~2+ within a week. Broader-beats-narrower guidance from experts already accommodated via Advantage+ mode. If frequency >3.0 appears at the Apr 27 re-eval, broaden further or rotate creatives.

---

## Why (Reasoning + Evidence)

### The two architectural corrections

**Correction 1 — GTM, not direct fbq().** Jot's own code investigation on 2026-04-20 found zero `fbq()` calls in the smartscribe-companion-apps web app. All events flow app → `window.dataLayer` → GTM container `GTM-KL9RPN9V` → Meta Pixel tag. The Apr 16 PRD's "5 lines of JS" framing would have pointed the implementation agent at the wrong file. Fix path: dataLayer enrichment + GTM Meta tag config change (GDN-789). Full detail: [meta-pixel-gtm-architecture-correction-2026-04-20.md](meta-pixel-gtm-architecture-correction-2026-04-20.md).

**Correction 2 — Meta assigns values natively.** Meta's Custom Conversions API accepts `default_conversion_value` at creation time. When a matching pixel event fires, Meta automatically counts the Custom Conversion at the default value. Zero engineering work, zero pixel changes. The Apr 16 PRD's "engineering must ship value params on pixel events" framing was asking engineering to do something the platform does server-side. Full detail: [meta-custom-conversions-values-2026-04-20.md](meta-custom-conversions-values-2026-04-20.md).

Both corrections followed the same anti-pattern: the original brief assumed an engineering fix without first exhausting platform-native capabilities. The global `Engineering asks are last resort` rule added today is the generalized defense.

### Why single ad set

At ~14 FirstNotes/week account-wide and Meta's learning-phase threshold of ~50 conversions per ad set per 7 days[^1], 5 ad sets splits the signal into structurally un-exitable fragments. Consolidation to 1 ad set restores Meta's ability to learn. Under VALUE optimization the combined signal (FN + SignUp + Calendar weighted by value) is what the algorithm optimizes against, so "losing" 4 value-prop splits costs less than it sounds — Meta still learns which creatives work via in-ad-set auction dynamics.

The value-prop separation thesis is not dead. It's **sequenced** for after EMQ crosses 6.0 (engineering ships GDN-789) and the account produces 40+ value events/week with attributable dollar values. At that point differential signals between ad sets become interpretable and splitting re-enables meaningful learning.

### Why Advantage+ suggested audiences, not hard include

TAM at 100-130K is 20-25x larger than the ~5K threshold where manually-curated custom audiences outperform Meta's AI-driven targeting[^2]. At our scale, Meta's Advantage+ audience mode with our lists as hints yields better delivery than hard-locking to the lists. Chris's 509-person Sales Prospect List in particular would saturate within days if used as a hard include at $80/day of previous budget — using it as a suggested audience lets Meta explore similar profiles without burning the original list.

### The data that forced the consolidation

Over Apr 17-20 (4 days after the Apr 16 restructure):

| Campaign | Spend | Impr | LPVs | FirstNotes | CpFN |
|---|---|---|---|---|---|
| Farm: Testing - Q226 (new) | $585 | 20,575 | 179 (61% LPV rate) | 0 | — |
| Scale: Winners - Apr 2026 (old) | $622 | 14,502 | 144 (84%) | 1 | $622 |
| Q126 LGF campaigns (2) | $334 | 5,546 | 3 (4%) | 0 | — |
| Total | $1,541 | | | 1 | $1,541 |

At account level for the same 7-day window the attributed `action_values` and `conversion_values` fields were both empty. This is the definitive evidence that VALUE optimization had no dollar signal before Custom Conversions were created. With Custom Conversions now live, the same data check should show real values once events have accrued.

---

## How to Apply

| Situation | Response |
|---|---|
| Someone asks "what's the current Meta setup?" | Single active ad set `Farm: All Value Props Q226` ($200/day, VALUE optimization, Advantage+ audience, FirstNote (Valued) Custom Conversion). 7-day no-touch window until Apr 27. |
| Someone proposes pixel / CAPI / advanced-matching work | Point them at GDN-789 (frontend dataLayer + GTM tag config, assigned to Jot). CAPI paired issue is held pending Jackson+Marcus FE/BE decision. |
| Someone asks "why is CpFN so high?" or "why are we in learning phase?" | EMQ is 4.0/10, Meta can't match events reliably, and the Custom Conversions just went live — algorithm needs 24-48hr to start incorporating dollar signals. Next re-eval Apr 27 before any remediation is warranted. |
| Someone wants to add ad sets or split the current ad set | Defer until EMQ ≥ 6 AND 40+ value events/week with attributable dollars. Early split re-fragments signal and re-triggers learning. |
| Someone wants to add more audiences | Inclusion audiences beyond the current 3 suggested risks muddying the Advantage+ signal. Prefer letting Advantage+ explore with existing hints unless a discrete new segment is being tested. |
| Someone asks about LGF (`Q126 MLC STATICS`, `Q126 MLC UPMARKET`) | Paused 2026-04-20. Burning ~$82/day with 0 in-scope FirstNotes. Per never-delete rule, not archived — just paused. Unpause only with explicit rationale. |
| Someone asks about the old Scale campaign (OUTCOME_LEADS) | Paused 2026-04-20. The 6 dynamic-creative ads that couldn't migrate to OUTCOME_SALES (AI Progress Notes, Concepts 3/4, PDF to Template, Florence Static, AI Progress Concept 2) live there. Not deleted. |
| Someone proposes deleting anything | Stop. Global CLAUDE.md rule: never delete, always pause/disable/archive. Ask Nate for explicit "delete" permission first. |
| Someone asks about NPPES audience status | Script hardened with checkpoint 2026-04-21. Upload to Meta not yet confirmed complete — rerun resumes from `data/audiences/nppes-checkpoint.json`. Future NPPES lookalike will auto-attach via `scripts/attach-audiences-to-adsets.py` when present. |

---

## What This Brief Does NOT Cover

- Specific creative performance at the ad level — no change in this window, still resting on the Apr 16 migration + Aryan's 6 UGC/wildcard videos staged separately.
- GDN-789 implementation details — lives in the Linear issue, not here.
- CAPI paired issue scope — blocked on FE/BE decision from Jackson + Marcus.
- Apr 27 re-evaluation methodology — will come back around as a new brief then.
- Reporting stack (GA4 / Metabase) — unchanged in this window.

---

## Open Questions

- **Does NPPES audience upload need another run?** Check `data/audiences/` for a `nppes-upload-*.json` summary; if absent, rerun `build-nppes-audience.py`. Owner: Claude, within the week.
- **When will FirstNote (Valued) and SignUpConfirm (Valued) Custom Conversions hit `first_fired_time`?** Expected within 24hr given event volume. Worth verifying in Events Manager > Custom Conversions. Owner: Nate, passive monitoring.
- **Does GDN-789 ship before the Apr 27 re-eval?** Unclear — depends on engineering bandwidth. If it ships early, match quality should start visibly improving within 48hr.
- **Are the 2 delivery-error ads (AJ: Cigna Has Rules, AN: Your Notes Are Perfect) back in active delivery after the 191x100 crop fix?** User re-cropped in the Ads Manager GUI on 2026-04-20; Meta revalidation was pending. Owner: Nate, visual check in Ads Manager.

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| Meta Ad Account | `act_1582817295627677` |
| Meta Pixel (canonical) | `1625233994894344` (WebApp Actions dataset) |
| Active Campaign | `120245455503210548` (Farm: Testing - Q226) |
| Empty Scale Campaign (future winners) | `120245455503370548` (Scale: Winners - Q226) |
| Active Ad Set | `120245455503860548` (Farm: All Value Props Q226) |
| Daily Budget | $200/day |
| Optimization Goal | VALUE |
| Bound Custom Conversion | `3914250848710226` (FirstNote (Valued), $100) |
| Other Custom Conversions | `1960979881475090` (SignUpConfirm (Valued), $5); `1270312578633364` (CalendarScheduled (Valued), $15) |
| Audience: Sales Prospect List | `120245449291240548` (509 contacts, suggested) |
| Audience: BH Clinic Prospects 1% LAL | `120245449291800548` (suggested) |
| Audience: First Note Converters 1% LAL | `120245449282540548` (suggested) |
| Audience: Stripe Customers Auto-Exclusion | `120244895647380548` (excluded, 14,130 emails) |
| Audience: Converters Exclusion | `120245449282160548` (excluded, 2,000 users) |
| Calendly confirmation page | https://www.jotpsych.com/scheduled-confirmed |
| GTM container | `GTM-KL9RPN9V` |
| Linear — filed, assigned to Jot | `GDN-789` |
| Linear — paired FE+BE CAPI issue | Not yet filed (blocked on FE/BE decision) |
| CAPI reference implementation | `engine/capi/sender.py` (outside smartscribe-server allowlist) |
| Paused: Old Farm (rollback insurance) | `Farm: Testing - Apr 2026` |
| Paused: Old Scale (holds 6 orphaned dynamic-creative ads) | `Scale: Winners - Apr 2026` |
| Paused: LGF campaigns | `Q126 MLC STATICS TEST`, `Q126 MLC UPMARKET STATICS TEST` |
| Orphaned paused ads in consolidated Farm | `Farm: EHR V2`, `Farm: Nate Podcast 4 - ad` (deprecated standard_enhancements blocked API copy) |
| 7-day no-touch window | 2026-04-20 → 2026-04-27 |
| Global CLAUDE.md | `~/.claude/CLAUDE.md` (Agency Rules section) |

---

## Sources

[^1]: [Modern Marketing Institute — Exit Meta Ads Learning Phase 2026](https://www.modernmarketinginstitute.com/blog/how-to-exit-the-meta-ads-learning-phase-fast-and-start-scaling-profitably-in-2026); cited in `docs/here-what-experts-say-2026-04-20.md`.
[^2]: [Alex Neiman — Advantage+ Audience: When to Use It vs Override It (2026)](https://alexneiman.com/meta-advantage-plus-audience-targeting-2026/); cited in `docs/here-what-experts-say-2026-04-20.md`.
