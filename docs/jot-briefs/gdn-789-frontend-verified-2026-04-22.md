---
title: "GDN-789 Frontend Enrichment Verified: PR #1712 Safe to Merge"
date: 2026-04-22
author: Nate + Claude
memory_target: Long-term memory
scope: Runtime verification of GDN-789's frontend dataLayer enrichment on preview deploy, attribution baseline for post-publish comparison, two follow-up issues found during testing
confidence: high
supersedes: none
sources:
  - conversation: Nate's dev console session on preview deploy 1712, 2026-04-22 ~4:15-4:45 PM ET
  - meta_api: Account-level and ad-level insights pulls 2026-04-22
  - meta_api: Pixel /stats event-aggregation pulls 2026-04-22
  - slack_thread: #sales-and-marketing (or adjacent) 2026-04-22 ~4:09 PM with Marcus, Jackson, Alfred
  - pr: https://github.com/smartscribe/smartscribe-companion-apps/pull/1712
---

# GDN-789 Frontend Enrichment Verified: PR #1712 Safe to Merge

**Date:** 2026-04-22
**Memory target:** Long-term memory
**Scope:** Runtime verification of GDN-789's frontend dataLayer enrichment, attribution baseline to compare against post-publish, two follow-up issues to file
**Status:** Canonical as of 2026-04-22. Frontend verified. GTM tag config + container publish are the remaining gates before EMQ moves.

---

## TL;DR

GDN-789's frontend dataLayer enrichment was verified end-to-end on preview deploy 1712 by signing up a fresh account in incognito and inspecting the dataLayer in DevTools. The `user_identified` event carries all five populatable Advanced Matching fields (`em`, `fn`, `ln`, `external_id`, `fbp`; `fbc` only fires when the session was initiated by an fbclid or real ad click) and fires before any conversion event. The privacy cleanup is confirmed: `signupConfirm` and `generatedFirstNote` payloads no longer carry raw email. PR #1712 is safe to merge. The GTM container still needs to be updated to map those dataLayer variables into the Meta Pixel tag's Advanced Matching slots; until that publishes, Meta sees the enriched dataLayer but doesn't consume it, so EMQ stays at 4.0 and attribution stays at ~14%. Two cheap follow-ups surfaced during the test and should be filed as their own issues.

---

## What Jot Should Commit to Memory

1. **PR #1712 (GDN-789) is runtime-verified as of 2026-04-22 and safe to merge.** Frontend dataLayer enrichment works end-to-end in the preview build. Marcus's Slack question from the same afternoon ("test it / merge / delete / unneeded?") resolves to: merge.

2. **Verified `user_identified` payload shape in incognito fresh-signup flow:** `em` is 64-char lowercase SHA-256 of trimmed+lowercased email, `fn` and `ln` are SHA-256 of name parts, `external_id` is the raw Auth0 user ID (e.g. `google-oauth2|117548102980604083318`, intentionally unhashed so it byte-matches future CAPI), `fbp` is the Meta first-party cookie (`fb.2.<ts>.<rand>`), `fbc` is absent unless the session started with `?fbclid=...` or an ad click.

3. **Firing order is correct: `user_identified` lands in dataLayer before any conversion event.** On a fresh signup flow, the push fires ~7 times before `signupConfirm` at index 28. The reviewer's concern about ordering on mid-session flows is not borne out here. Identity is populated well ahead of the conversion.

4. **Privacy cleanup verified at runtime.** `signupConfirm` payload = `{timestamp, event, platform, gtm.uniqueEventId}` with no `email`. `generatedFirstNote` payload = `{timestamp, event, gtm.uniqueEventId}` with no `email`. The one-line removal in `useEncounterSubmission.ts:50` (dropping `email: userState?.user_info?.email,`) is proven to have taken effect.

5. **GTM container update is the one remaining engineering gate before EMQ moves.** The Meta Pixel tag in GTM-KL9RPN9V must be configured to read `em`, `fn`, `ln`, `external_id`, `fbp`, `fbc` from dataLayer and map them into the tag's Advanced Matching slots. Validate in GTM preview mode via Meta Events Manager → Test Events, then publish. Until that happens, Meta receives events but cannot match them; enriched dataLayer is invisible to the pixel.

6. **Attribution baseline for post-publish comparison (Apr 15-21 2026):** Account spent $3,350 across all active and tail-spending campaigns. Pixel fired 37 FirstNote events but Meta attributed only 5 of them to ads, a 13.5% attribution rate. SignUpConfirm shows the same pattern (50 fires, 13 attributed = 26%). `conversion_value` and `action_value` = $0 across the entire window because value params aren't on pixel events yet (shipped in the same PR as dataLayer enrichment; GTM tag still needs to forward them). Target post-publish + 48h: attribution > 70% and `conversion_value` > $0.

7. **Follow-up issue to file #1: `useUser()` over-firing.** The hydration effect in `features/user/store/hooks.ts` re-runs on every re-render instead of once per mount. On a single fresh-signup + first-note session, `user_identified` pushed 21+ times before `signupConfirm` fired, and `gtm.uniqueEventId` hit 582 by the end. This is the root cause of the 1.1M `userID` pixel fires observed in 7 days. Not a GDN-789 correctness bug (Meta dedupes identical Advanced Matching payloads), but it adds massive pixel noise. Cheap fix: ref guard or tighten the effect's dep array to fire once per real identity change.

8. **Follow-up issue to file #2: `platform` undefined on `generatedFirstNote`.** The `trackEvent` call site passes `{event, platform, email}` (per the PR diff, minus the removed `email` line). The serialized payload shows `{timestamp, event, gtm.uniqueEventId}`, no `platform`. Since `JSON.stringify` strips `undefined` values, `platform` is undefined at fire time. Pre-existing (not introduced by this PR), but means every first-note conversion is missing platform context. Investigate whether the platform detection hook resolves after the event fires.

9. **Test methodology for future pixel enrichment verification (reusable).** (a) Open preview build in incognito. (b) Append `?fbclid=test123` to the URL on first load to force `_fbc` cookie to populate. (c) Sign up a fresh test account. (d) DevTools console: `window.dataLayer.filter(e => e.event === 'user_identified')` to verify identity enrichment, then run the same filter for each conversion event. (e) `JSON.stringify(window.dataLayer.find(e => e.event === '<name>'), null, 2)` to dump a full payload. (f) `window.dataLayer.map((e,i)=>({i,event:e.event})).filter(x=>x.event)` to see firing order. Works on the preview-deploy URL pattern `https://smartscribe.github.io/smartscribe-companion-apps/web-app/<PR#>/`.

10. **Preview-deploy testing with a normal account works against dev data.** Alfred Souza confirmed on 2026-04-22 that using the real user's own account on the preview-deploy URL points at dev data, not prod. This means runtime verification of Meta pixel / dataLayer changes can be done by the user without provisioning a throwaway. For events that only fire once per user (like `generatedFirstNote`), use incognito + fresh signup regardless.

---

## Why (Reasoning + Evidence)

### The verification session

Nate ran the test on preview-deploy 1712 after Marcus pinged him in Slack asking whether the PR (filed 6 days earlier by jotreviewer bot) should be merged, deleted, or was unneeded. Alfred provided the preview URL and confirmed dev-data routing.

The session proceeded in two phases:

**Phase A: Nate's own logged-in account.** Confirmed `user_identified` fires with valid SHA-256 hashed email, name parts, raw `external_id`, and `fbp` cookie. `fbc` was absent because the session wasn't initiated from an ad. `generatedFirstNote` did NOT fire on Nate's account because he had already generated his first note in June 2025 (visible in his Notes list as "First JotPsych Encounter 6/17/25").

**Phase B: Fresh incognito signup.** Bypassed the "first note only fires once per user" constraint. Both `signupConfirm` and `generatedFirstNote` fired cleanly, both with no raw email in the payload.

### Evidence table

| Check | Evidence | Result |
|---|---|---|
| `user_identified` fires | 10 pushes observed in initial session, 21+ in fresh signup flow | ✓ |
| `em` is SHA-256 | `5f255bffe549ad0254a8c409d65a9647eca0cf6c175357d7d6213813aa1218d0` (64-char hex) | ✓ |
| `fn` / `ln` are SHA-256 | `d2653ff7cbb2d8ff...` / `e5c38f8cc4c05e1a...` (both 64-char hex) | ✓ |
| `external_id` raw (unhashed) | `google-oauth2\|117548102980604083318` (Auth0 raw user ID, not hashed) | ✓ (intentional per PR decision to byte-match CAPI) |
| `fbp` cookie present | `fb.2.1774625176009.820603250229806545` | ✓ |
| `fbc` cookie present | Absent without `?fbclid=...` | ✓ expected |
| Firing order | `user_identified` at index 7, `signupConfirm` at index 28 | ✓ identity before conversion |
| `signupConfirm` no raw email | `{timestamp, event: "signupConfirm", platform: "desktop", gtm.uniqueEventId: 237}` | ✓ |
| `generatedFirstNote` no raw email | `{timestamp, event: "generatedFirstNote", gtm.uniqueEventId: 582}` | ✓ |

### Attribution baseline from Meta API

Pulled from the Ads Insights API (account level, `last_7d` = 2026-04-15 → 2026-04-21) against account `act_1582817295627677`:

| Metric | Value |
|---|---|
| Spend | $3,350.03 |
| Impressions | 106,691 |
| Clicks | 4,327 |
| Reach | 44,885 |
| Frequency | 2.38 |
| FirstNote attributed to ads | 5 |
| SignUpConfirm attributed to ads | 13 |
| `conversion_value` | $0.00 |
| `action_value` | $0.00 |

Pulled from the Pixel Graph API (`/1625233994894344/stats?aggregation=event`) for the same window:

| Event | Pixel fires | Meta attributed | Attribution rate |
|---|---|---|---|
| FirstNote | 37 | 5 | 13.5% |
| SignUpConfirm | 50 | 13 | 26.0% |
| CalendarScheduled | 14 | 0 | 0% |
| userID | 1,124,128 | n/a (not a standard event) | n/a |
| UserID | 585,197 | n/a | n/a |
| PageView | 766,657 | n/a | n/a |

Daily FN breakdown shows the gap persists across the window, not concentrated on any one day:

| Date | Pixel FN | Attributed FN |
|---|---|---|
| Apr 15 | 8 | 1 |
| Apr 16 | 8 | 0 |
| Apr 17 | 7 | 2 |
| Apr 18 | 1 | 0 |
| Apr 19 | 0 | 0 |
| Apr 20 | 6 | 1 |
| Apr 21 | 7 | 1 |

The pattern: ~86% of real FirstNote conversions are dark to Meta's attribution engine because the events arrive without matchable identity fields. This is exactly what GDN-789 is designed to fix and what makes the frontend verification business-critical.

### Why over-firing matters even though Meta dedupes

Meta's Advanced Matching dedup happens server-side after receipt. The over-firing still costs on the pixel-fire side:
- Each `userID`/`user_identified` push can trigger a pixel event in GTM depending on tag triggers
- 1.1M `userID` fires in 7 days at ~$0 per fire is free but inflates any per-event rate-limit calculations
- Event volume crowds out signal-relevant events in Events Manager Test Events / debugging

The fix (ref guard on the hydration effect) is small and should ship separately from GDN-789.

---

## How to Apply

| Situation | Response |
|---|---|
| Someone asks "is PR #1712 ready?" | Yes, merged-safe as of 2026-04-22. Frontend runtime-verified. |
| Someone asks "why didn't merging fix EMQ?" | Merging ships frontend dataLayer enrichment. The GTM Meta Pixel tag must also be updated to read those variables and map them into Advanced Matching slots. Until GTM publishes, Meta doesn't see the enrichment. |
| Someone asks "how do we know the PR works?" | Point to this brief's evidence table. Fresh incognito signup + first note on preview-deploy 1712, all payloads verified clean in DevTools console. |
| Someone asks "when will EMQ move?" | 24-48h after GTM container publishes. Current baseline is 4.0/10; target is 6+. |
| Someone asks "why is attribution so low right now?" | 37 pixel FN fires vs 5 Meta-attributed = 86% of conversions are invisible to Meta because events arrive without matchable identity fields. GDN-789 fixes this. |
| Someone wants to verify a future pixel/enrichment change | Use the test methodology in memory item #9. Don't skip the incognito + fresh-signup step for any event that only fires once per user. |
| Someone proposes splitting the active ad set or increasing budget before EMQ moves | Push back. The current $200/day is being burned against attribution that sees only 14% of conversions. Scaling compounds the waste. Let GDN-789 + GTM publish land, wait 48h, re-pull attribution, then decide. |
| Someone asks about the `useUser()` over-firing | File as a separate cleanup issue. Not a GDN-789 blocker. Cheap fix (ref guard or tightened deps array). Root cause of the 1.1M `userID` pixel fires. |
| Someone asks why `platform` is missing from a `generatedFirstNote` event | Pre-existing bug, not introduced by GDN-789. `platform` is `undefined` at fire time and `JSON.stringify` strips it. File separately. |

---

## What This Brief Does NOT Cover

- The CAPI (server-side) paired workstream. Blocked on FE/BE decision between Jackson and Marcus. Separate issue when scoped.
- Value parameters on pixel events (`value`, `currency`). Already handled via Meta Custom Conversions with `default_conversion_value`; the frontend-side value push was scoped out of GDN-789 because Custom Conversions cover it natively.
- Landing page conversion rate. Independent funnel issue; LP redirect to /audit is a separate plan.
- Campaign structure / ad set consolidation. Covered in the Apr 21 snapshot brief.
- Match quality from unattributed traffic beyond Meta (Google, organic). Out of scope.

---

## Open Questions

- **When does the GTM container get updated and published?** Owner: Jackson or whoever holds the GTM-KL9RPN9V admin. No ETA committed. Watching for this.
- **When is the `useUser()` over-firing follow-up filed?** Owner: Jackson post-merge. Should include a ref guard or dep-array tightening.
- **When is the `platform: undefined` follow-up filed?** Owner: Jackson or whoever ships first-note telemetry fixes. Lower urgency.
- **Should Aryan's 6 UGC/wildcard videos go live before or after GDN-789 publish?** Before accelerates learning but against bad attribution; after delays the test but gives Meta clean signal. Default: wait until EMQ crosses 5.

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| PR | https://github.com/smartscribe/smartscribe-companion-apps/pull/1712 |
| Linear issue | GDN-789 |
| Preview deploy URL | https://smartscribe.github.io/smartscribe-companion-apps/web-app/1712/ |
| Meta Ad Account | `act_1582817295627677` |
| Meta Pixel (canonical) | `1625233994894344` (WebApp Actions dataset) |
| GTM container | `GTM-KL9RPN9V` |
| Active campaign | `120245455503210548` (Farm: Testing - Q226) |
| Active ad set | `120245455503860548` (Farm: All Value Props Q226) |
| Bound Custom Conversion | `3914250848710226` (FirstNote (Valued), $100) |
| File with removed raw-email push | `src/web-app/src/features/encounters/components/v1/hooks/useEncounterSubmission.ts:50` |
| File with new enrichment hook | `src/web-app/src/features/user/store/hooks.ts` |
| File with Advanced Matching helper | `src/web-app/src/utils/meta_match.ts` |
| Test account used | `google-oauth2|117548102980604083318` (Nate's Google account) + fresh incognito throwaway |
| Attribution baseline window | 2026-04-15 → 2026-04-21 (7 days) |
| Attribution baseline spend | $3,350.03 |
| Attribution baseline FN | 5 attributed / 37 pixel-fired (13.5%) |
| Current EMQ | 4.0/10 |
| Target EMQ | 6+/10 |
| Slack thread prompting this verification | #sales-and-marketing 2026-04-22 ~4:09 PM ET, participants Nate, Marcus, Jackson, Alfred |

---

## Sources

[^1]: DevTools console session on preview-deploy 1712, captured in conversation transcript 2026-04-22 ~4:15-4:45 PM ET. Raw dataLayer payloads, firing-order output, and stringified conversion-event payloads.

[^2]: Meta Ads Insights API pull, 2026-04-22, account `act_1582817295627677`, `date_preset=last_7d`, `level=account` and `level=campaign`. Both `conversion_value` and `action_value` = $0; FirstNote = 5 attributed, SignUpConfirm = 13.

[^3]: Meta Pixel Graph API pull, 2026-04-22, pixel `1625233994894344`, `/stats?aggregation=event&start_time=2026-04-15&end_time=2026-04-22`. Raw event-fire counts by event type across the window.

[^4]: PR #1712 diff, specifically `useEncounterSubmission.ts` removing the single `email:` line on what was previously line 51. Verified via `gh pr diff 1712`.

[^5]: Slack thread 2026-04-22 ~4:09 PM ET (channel approx #sales-and-marketing), Marcus asking Nate about PR #1712 status, Alfred sharing the preview URL and confirming dev-data routing. Pasted verbatim into the verification conversation.
