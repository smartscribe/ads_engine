---
title: "Meta Pixel Architecture Correction — GTM, Not Direct fbq()"
date: 2026-04-20
author: Nate + Claude
memory_target: Long-term memory
scope: Correct the Meta pixel match-quality PRD and commit the true app→pixel architecture to memory
confidence: high
supersedes: docs/jot-briefs/meta-match-quality-fix-2026-04-16.md (architecturally; urgency + rationale still stand)
sources:
  - slack_thread: #ads-engine (approx) 2026-04-20, Nate/Jackson/Marcus/Jot, re GDN-789 filing
  - file: docs/jot-briefs/meta-match-quality-fix-2026-04-16.md
  - file: docs/facts-we-know-2026-04-20.md
  - linear: GDN-789
  - repo: smartscribe-companion-apps (index.html, analytics_utils.tsx, useEncounterSubmission.ts)
  - repo: smartscribe-server (grepped clean for CAPI/graph.facebook.com — nothing exists)
---

# Meta Pixel Architecture Correction — GTM, Not Direct fbq()

**Date:** 2026-04-20
**Memory target:** Long-term memory
**Scope:** Correct the Apr 16 match-quality PRD's architectural assumption and establish the actual pixel architecture as canonical
**Status:** Canonical as of 2026-04-20. Supersedes the Apr 16 PRD's "5 lines of JS" implementation framing. Business case for shipping (EMQ 4→6, unblock VALUE optimization) remains valid and urgent.

---

## TL;DR

The Apr 16 match-quality PRD asked engineering to modify `fbq('init')` and `fbq('track')` calls directly. Jot's code investigation confirmed that assumption is wrong: the smartscribe-companion-apps web app has zero direct `fbq()` calls. Google Tag Manager (GTM-KL9RPN9V) owns the Meta pixel tag; app code only pushes events to `window.dataLayer`. The corrected implementation path is dataLayer enrichment plus a GTM Meta Pixel tag config change — more GTM work than JS. Linear issue GDN-789 has been filed with this corrected framing for the frontend-only enrichment (hashed email, `_fbc`/`_fbp` cookies, `external_id`, `eventID` into dataLayer, then GTM tag advanced-matching config). The paired FE+BE CAPI issue is held pending resolution of a) where CAPI lives (Jackson flagged FE vs BE uncertainty) and b) the `meta_event_id`/`meta_fbc`/`meta_fbp` contract between frontend and backend for dedup. Until GDN-789 ships, Meta is running VALUE optimization blind: $200/day spend, $0 attributed conversion value over 7 days, EMQ stuck at 4.0/10.

---

## What Jot Should Commit to Memory

1. **The smartscribe-companion-apps web app does not call `fbq()` directly.** All pixel events flow: app code → `window.dataLayer.push(...)` → GTM container `GTM-KL9RPN9V` → Meta pixel tag (ID `1625233994894344`). Any future PRD, recommendation, or architectural reasoning about Meta pixel behavior must start from this premise.

2. **GTM is where Meta pixel advanced matching gets configured, not the app code.** To improve Event Match Quality, advanced matching fields (hashed email, `_fbc`, `_fbp`, `external_id`, `eventID`) must be (a) pushed into dataLayer by the app, and (b) mapped into the Meta Pixel tag's Advanced Matching slots inside the GTM container. Both halves are required; neither alone is sufficient.

3. **Reading `_fbc` / `_fbp` cookies carries zero risk and is purely additive.** First-party cookies on our domain, readable via `document.cookie`, no CSP implication (CSP gates network, not DOM). Same applies to adding fields to dataLayer — existing `trackEvent()` calls stay untouched.

4. **The one real risk in the Meta match-quality work is GTM tag misconfiguration.** If the Meta Pixel tag is edited incorrectly, the pixel can stop firing entirely until fixed. Mitigation: GTM preview mode before publish, and GTM version rollback if a published version breaks delivery.

5. **CAPI (server-side conversions) does not exist in smartscribe-server as of 2026-04-20.** Grepped clean for `graph.facebook.com`, `META_ADS_ACCESS_TOKEN`, `capi`, `conversions.api` — nothing. The reference implementation at `ads_engine/engine/capi/sender.py` lives in a different repo outside the smartscribe-server allowlist. When CAPI gets built, it gets built in-repo; the ads_engine module is a reference, not a dependency.

6. **Event dedup requires a client-generated UUID passed to both sides.** Frontend generates `crypto.randomUUID()` at conversion time, pushes it into dataLayer (GTM's Meta tag forwards it as `eventID`) AND sends it to backend on the API call that records the event. Backend includes the same UUID as `event_id` in its CAPI payload. Meta dedupes by `event_name + event_id`, keeps the better-matched copy.

7. **Linear issue GDN-789 is filed and assigned to Jot (as the Jot Worker agent).** Scope: frontend dataLayer enrichment + GTM tag config change. Size S. Team "The Garden." Medium priority. Can ship independently of CAPI work and is expected to move the EMQ needle on its own.

8. **The paired FE+BE CAPI issue is not filed yet.** Blocked on two open questions: (a) does CAPI live in the frontend client or the backend server — Jackson flagged uncertainty on 2026-04-20, (b) the API contract between frontend and backend for forwarding `meta_event_id` / `meta_fbc` / `meta_fbp` needs design before the issue is scoped.

9. **The app already pushes raw email to dataLayer (useEncounterSubmission.ts:52).** This is a pre-existing PII-exposure concern. The GDN-789 work — moving to SHA-256 hashed email — is strictly better on privacy and should include cleaning up the raw-email push in the same change.

10. **Value params (`value`, `currency`) on FirstNote and SignUpConfirm events are part of the same frontend enrichment work.** FirstNote = `{value: 100, currency: 'USD'}`, SignUpConfirm = `{value: 5, currency: 'USD'}`. These get pushed into dataLayer alongside `eventID` and mapped in the GTM Meta tag's event parameters. Without them, Meta VALUE optimization has no dollar signal to maximize — which is the current state of Farm: Testing - Q226.

---

## Why (Reasoning + Evidence)

### The Apr 16 PRD was wrong about "5 lines of JS"

The original brief proposed:

```javascript
fbq('init', '1625233994894344', {
  em: 'sha256_hashed_email',
  fbp: fbp,
  fbc: fbc,
  external_id: hashedUserId,
});
```

Jot's code investigation on 2026-04-20[^1] found:

> "Big finding that changes the plan. We don't call `fbq()` anywhere in the web app. The Meta pixel is loaded and managed entirely by Google Tag Manager (GTM-KL9RPN9V, in index.html). Our code just pushes events to window.dataLayer via trackEvent() — GTM is what actually fires the pixel."

The `fbq()`-based PRD would have pointed the coding agent at the wrong file. Any future Meta pixel recommendation must begin from the GTM-mediated architecture, not assume direct pixel access.

### The corrected implementation path

Per Jot's revised design[^2]:

| Field | Source | How it gets to Meta |
|---|---|---|
| `_fbc` cookie | `document.cookie` | dataLayer push → GTM Meta tag advanced matching |
| `_fbp` cookie | `document.cookie` | Same |
| Hashed email | `userState.user_info.email` → SHA-256 via `crypto.subtle.digest` | Same |
| Hashed first/last name | user state | Same |
| `external_id` | user ID from user state | Same |
| `eventID` (per-event UUID) | `crypto.randomUUID()` | dataLayer push → GTM Meta tag `eventID` advanced param |
| `client_ip_address` | HTTP request headers | CAPI (backend) — frontend cannot access this cleanly |
| `client_user_agent` | HTTP request headers | CAPI (backend) |

The P0 tier (cookies + hashed email + external_id + eventID) is entirely additive and non-breaking. The one thing that requires care is the GTM tag config change — that's the "real risk" to mitigate with preview mode.

### Why urgency matters — specific numbers

Facts as of 2026-04-20[^3]:

- Meta Ads account-level spend, Apr 14–20: **$3,574.18**
- Attributed `action_values` across all events: **$0.00**
- Attributed `conversion_values`: **$0.00**
- Event Match Quality (FirstNote): **4.0/10** per Meta's Events Manager
- Current Farm: Testing - Q226 daily budget: **$200/day**
- Optimization goal: VALUE (set 2026-04-16)

Expert data[^4]:

- Meta's own EMQ benchmark: **6.0 or higher**
- Expected CPA impact of EMQ 4.0 → 6.0: **18–25% reduction**
- Value optimization threshold to function: **30 attributed value events in 7 days** — we have zero

Every day GDN-789 doesn't ship is a day Meta continues to optimize for a dollar signal that doesn't exist, on a $200/day burn rate. The frontend work (cookies + hashed email into dataLayer + GTM tag map) alone is expected to unlock the 42%+42% match-quality uplift Meta attributes to IP/UA and cookie forwarding, even before the backend CAPI work lands.

### Where Jackson's FE/BE uncertainty sits

From the thread (2026-04-20 2:44 PM):

> "I don't think the backend is the one that sends these events. I think the frontend does…"

Jot's investigation[^5] stated the backend *could* host CAPI (it has access to IP/UA from headers, it can emit async fire-and-forget HTTP calls), and nothing in smartscribe-server exists there today. But the question of whether that's the right architecture — vs. having the frontend forward IP/UA to a serverless edge function or similar — hasn't been resolved. This is the gating question on the paired CAPI issue.

---

## How to Apply

| Situation | Response |
|---|---|
| Someone proposes "just add a line to fbq()" | Correct them. App uses GTM, not direct fbq(). Work happens in dataLayer + GTM tag config. |
| Someone asks "why is EMQ so low?" | App pushes raw email to dataLayer (useEncounterSubmission.ts:52) with no other matching fields. GDN-789 is the fix. |
| Someone asks "why isn't VALUE optimization working?" | Pixel events from app don't carry `value` params. Meta has zero dollar signal to optimize on. Ships in the same GDN-789 enrichment work. |
| Someone asks about CAPI — is it live? | No. Not in smartscribe-server. Reference impl exists at ads_engine/engine/capi/sender.py but that's outside allowlisted repos. Gets built in-repo when the paired issue is filed. |
| Someone asks about event dedup between pixel and CAPI | Frontend generates UUID via `crypto.randomUUID()`, pushes to dataLayer AND forwards to backend API. Backend uses same UUID as CAPI `event_id`. Meta dedupes on `event_name + event_id`. |
| Someone proposes modifying GTM tags without preview | Push back. GTM preview mode is the mitigation for the one real risk in this workstream. Don't publish GTM versions blind. |

---

## What This Brief Does NOT Cover

- The actual GTM tag config steps (which slots to map in Meta's Advanced Matching UI). That lives in GDN-789's implementation notes.
- Whether phone numbers get collected in user profile today. Jot flagged as "unclear" — needs verification before phone becomes part of enrichment.
- Address fields (zip/city/state). P2 in original PRD, skip v1.
- Value-rule configuration in Meta Ads Manager itself (different system; pixel values are upstream).

---

## Open Questions

- **Where does CAPI live — frontend or backend?** Jackson (2026-04-20) and Jot both flagged this as unresolved. Needs decision before paired FE+BE issue is scoped. Owner: Marcus + Jackson. No deadline set.
- **Is phone number collected in user state today?** Blocks including `ph` in the enrichment. Owner: engineering during GDN-789 implementation.
- **API contract for `meta_event_id` / `meta_fbc` / `meta_fbp` forwarding between FE and BE.** Feature flag for paired ship vs sequenced FE-then-BE? Owner: Jackson, resolvable in issue scoping.

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| GTM container | `GTM-KL9RPN9V` |
| Meta pixel ID (canonical) | `1625233994894344` (WebApp Actions dataset) |
| Meta Ad Account | `act_1582817295627677` |
| Access Token env var | `META_ADS_ACCESS_TOKEN` |
| Linear — frontend enrichment issue | `GDN-789` |
| Linear — paired FE+BE CAPI issue | **Not filed yet** — held pending FE/BE decision |
| Original PRD (architecturally superseded) | `docs/jot-briefs/meta-match-quality-fix-2026-04-16.md` |
| CAPI reference implementation | `ads_engine/engine/capi/sender.py` (outside smartscribe-server allowlist) |
| Existing dataLayer PII exposure | `useEncounterSubmission.ts:52` (raw email push) |
| Current EMQ | 4.0/10 (FirstNote, as of 2026-04-20) |
| Target EMQ | 6.0+ |
| Farm: Testing - Q226 budget | $200/day |
| Account spend 2026-04-14 → 2026-04-20 | $3,574.18 |
| Attributed conversion value same period | $0.00 |

---

## Sources

[^1]: Jot's code investigation, Slack thread 2026-04-20 2:36 PM. Quoted verbatim.
[^2]: Jot's revised implementation table, Slack thread 2026-04-20 2:41 PM.
[^3]: Meta Ads API pull 2026-04-20; [docs/facts-we-know-2026-04-20.md](../facts-we-know-2026-04-20.md). `action_values` and `conversion_values` both empty across account.
[^4]: [docs/here-what-experts-say-2026-04-20.md](../here-what-experts-say-2026-04-20.md), citing Triple Whale, Madgicx, CustomerLabs benchmarks.
[^5]: Jot's smartscribe-server grep + CAPI module explanation, Slack thread 2026-04-20 2:42 PM.
