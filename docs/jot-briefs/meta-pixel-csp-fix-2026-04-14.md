---
title: Meta Pixel LPV Tracking Fix — jotpsych.com CSP + Pixel ID Swap
date: 2026-04-14
author: Nate + Claude
memory_target: Mem0
scope: When any tag/pixel on jotpsych.com reports anomalously low event volume, CSP is the first diagnostic check. Plus canonical Meta Pixel ID and the 2026-04-14 fix details.
confidence: high
supersedes: none
sources:
  - doc: jotpsych_gtm/ads_engine/plans/lpv-tracking-fix-2026-04-14.md
  - doc: jotpsych_gtm/ads_engine/docs/jot-briefs/ga4-csp-fix-2026-04-13.md
  - commit: smartscribe/jotpsych.com@8664313
  - commit: smartscribe/jotpsych.com@62df031
  - data: jotpsych_gtm/ads_engine/data/ads-reports/briefing-10d-2026-04-14.html
---

# Meta Pixel LPV Tracking Fix — jotpsych.com CSP + Pixel ID Swap

**Date:** 2026-04-14
**Memory target:** Mem0
**Scope:** Durable diagnostic principle for any tracking gap on jotpsych.com, plus the canonical Meta Pixel ID going forward and the 2026-04-14 fix record.
**Status:** canonical as of 2026-04-14

---

## TL;DR

The Meta Pixel on jotpsych.com has been effectively dead for weeks. CSP in `site/_headers` was missing two Facebook hosts — `connect.facebook.net` (where `fbevents.js` lives) and `www.facebook.com` (where the pixel sends its tracking XHRs) — so `fbq()` calls on every page queued into a stub that never executed. Meta Ads reporting showed a landing-page-view-per-link-click ratio of 6% over the 2026-04-04 → 2026-04-13 window against an industry norm of 70–90%, which kneecapped Meta's optimizer (it was starving on fractional signal). The 6% that did get counted was the `<noscript>` img fallback firing for bots, prefetchers, and link crawlers — not real users. Fixed 2026-04-14 by adding both Facebook hosts to the CSP allowlist and swapping the site-wide pixel ID from `340582149007668` (JotPsych Actions, orphaned) to `1625233994894344` (WebApp Actions, canonical). This is the exact same class of bug as the GA4/Google Ads CSP fix from 2026-04-13 (`ga4-csp-fix-2026-04-13.md`); the prior commit that fixed GA4 was a half-fix that never added Facebook. **The durable principle: when any tag/pixel on jotpsych.com reports anomalously low event volume, CSP is the first place to look — not GTM, not the pixel code itself, not the ad account.**

---

## What Jot Should Commit to Memory

1. **When any third-party tag on jotpsych.com reports anomalously low event volume, check the CSP header first.** Context: jotpsych.com's CSP in `site/_headers` has already caused two tracking outages in April 2026 (GA4 on 2026-04-13, Meta Pixel on 2026-04-14). The pattern: tag libraries load fine (scripts are usually allowed), but actual telemetry XHRs get silently killed at the browser CSP layer because the target host isn't in `connect-src`. Tag helpers and in-platform dashboards will show "installed" while the real event count is near zero.

2. **The canonical Meta Pixel for jotpsych.com paid media is `1625233994894344` (WebApp Actions).** Context: the old pixel `340582149007668` (JotPsych Actions) is orphaned from the site as of 2026-04-14 and should not be cited when reading or comparing pixel data. If someone references the old ID, flag it — they're probably looking at stale dashboards.

3. **"CSP fix" in jotpsych.com history always means `site/_headers`, not `netlify.toml`.** Context: `netlify.toml` only configures `pretty_urls`. The CSP is served via the `_headers` file. Anyone asking where CSP lives should be pointed at `jotpsych_gtm/new_landing_page/site/_headers`.

4. **Meta's "Landing Page View" is a derived event, not a raw pixel event.** Context: Meta counts an LPV when a click's destination page fires a PageView pixel event that Meta can associate with the click. If the PageView never fires, Meta credits the link click but not the landing, which tanks the LPV/link-click ratio. Industry norm is 70–90%; anything below 30% is broken tracking, not bad creative.

5. **The LPV ratio for the 2026-04-04 → 2026-04-13 window was 6%, meaning Meta's optimizer was starving on ~14x under-reported signal.** Context: this breaks every "kill/scale" verdict that was made from that window. Specifically, the 10-day ads briefing at `data/ads-reports/briefing-10d-2026-04-14.html` has "trending kill" and "trending scale" sections that should NOT be acted on until post-fix data stabilizes (~2026-04-17). Ads that looked weak may have been starving; ads that looked strong may have been getting noisy credit.

6. **CpFN totals for pre-fix windows are still correct as totals; per-ad attribution is what rebalances.** Context: FirstNote is an event-level measurement that doesn't depend on LPV. Total spend ÷ total FNs = true CpFN. What changes post-fix is how Meta distributes credit across ads within a window. Do not re-compute pre-fix CpFN as if it was "wrong" — it wasn't.

7. **Post-fix Meta reporting from 2026-04-14 forward will show lower apparent CpFN than prior weeks.** Context: this is a tracking correction, NOT a performance improvement. Do not interpret it as a regime change. Budget decisions should wait ~7 days for the new baseline to stabilize.

8. **`scripts/lpv_tracking_check.sh` in the ads_engine project verifies tracking is healthy in under a second.** Context: run it monthly or after any marketing-site deploy. It checks CSP allows both Facebook hosts and that the canonical pixel ID is present on top landing pages. 7/7 pass is green.

---

## Why (Reasoning + Evidence)

### How the gap was detected

The 10-day Meta Ads briefing (`briefing-10d-2026-04-14.html`) surfaced a striking number: across 170,413 impressions and 2,793 link clicks over 2026-04-04 → 2026-04-13, only **170 landing-page-views were recorded by Meta**. That's a 6.09% LPV-per-link-click ratio. The industry norm for a correctly-instrumented landing page is 70–90%. [^1]

Per-ad breakdown (excerpt, 10-day window):

| Ad | Link clicks | LPV | LPV/LC |
|---|---|---|---|
| Farm: Nate Podcast 4 | 533 | 23 | 4.3% |
| Scale: Test: AI for Progress Notes Concept 3 | 303 | 3 | 1.0% |
| Test: SB Video 1 (account winner) | 88 | 3 | 3.4% |
| Scale: PDF to Template (best ratio in set) | 67 | 13 | 19.4% |

The variance — some ads at 1–5%, others at 10–20% — was diagnostic. A fully blocked pipe would show ~0% uniformly. Partial and variable suggests conditional firing (noscript fallback hitting bots + prefetchers, not consistent across ad surfaces).

### The smoking gun — in the first file opened

The diagnostic plan listed 9 candidate causes in likelihood order. CSP was ranked #4. The evidence was in the first file I read:

`jotpsych_gtm/new_landing_page/site/_headers` (line 5, pre-fix): [^2]

```
script-src 'self' 'unsafe-inline' https://*.googletagmanager.com https://api.hsforms.com;
connect-src 'self' https://api.hsforms.com https://*.google-analytics.com
            https://*.analytics.google.com https://*.googletagmanager.com
            https://www.google.com https://*.g.doubleclick.net
            https://server-side-tagging-z4zkeg2xnq-uc.a.run.app;
```

No `https://connect.facebook.net` in `script-src`. No `https://www.facebook.com` in `connect-src`. The Meta Pixel snippet on every page of the site attempts exactly those two calls:

```html
<!-- From site/index.html (pre-fix), line 12 -->
<script>!function(...){...}
(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');
fbq('init','340582149007668');fbq('track','PageView');</script>
<noscript><img height="1" width="1" style="display:none"
  src="https://www.facebook.com/tr?id=340582149007668&ev=PageView&noscript=1"/></noscript>
```

CSP `script-src` blocks `fbevents.js`, so `fbq` is defined only as a queue-pushing stub — the real library never arrives to flush the queue. `fbq('init',...)` and `fbq('track','PageView')` just push to an array that nobody reads. The `<noscript>` `<img>` fallback does work because `img-src 'self' https: data:` is wildcard-permissive, but `<noscript>` only renders when JavaScript is disabled — which covers bots, link previewers, and Meta's own crawlers, but not real users. That's the entire 6%. [^3]

### Why this went unnoticed — the half-fix that set it up

Commit `62df031` on 2026-04-13 was titled *"Site update: fix CSP to unblock GA4 and Google Ads tracking."* It added Google hosts to the CSP. It did not add Facebook hosts. [^4] The same class of bug, same file, same root cause — but fixed for only one vendor. Whoever wrote that commit was responding to the GA4 CSP incident documented in `ga4-csp-fix-2026-04-13.md` and either didn't know Meta had the same problem or didn't think to audit for it.

**Pattern to internalize: when a CSP fix ships for one tracking vendor, audit every other tracking vendor on the site the same day.** The vendors are orthogonal, the CSP changes are additive, and the cost of checking is trivial compared to another week of broken tracking.

### The pixel ID swap (separate sub-fix)

While the CSP gap was the main cause, there was also a pixel dataset question. The ad account has two Meta Pixel datasets:

| Dataset ID | Label | Status |
|---|---|---|
| `1625233994894344` | WebApp Actions | **Canonical** — wired to the ad account's event configuration |
| `340582149007668` | JotPsych Actions | Orphaned — was firing site-wide but not aligned to the account's event setup |

All 38 HTML files on the site (36 tracked + `audit.html` + `making-time-for-presence.html` untracked at fix time) were using the orphaned ID `340582149007668`. Even if the CSP had been correct, Meta Ads wouldn't have been reading that dataset for optimization. The fix commit swaps all occurrences to `1625233994894344` in both the `fbq('init', ...)` call and the `<noscript>` image beacon. [^5]

### Live verification

Post-deploy smoke test against `https://jotpsych.com` (commit `8664313`, Netlify deploy `69deae2cc8fee026819436ee`): [^6]

```
LPV tracking check — https://jotpsych.com

  PASS  CSP script-src allows connect.facebook.net
  PASS  CSP connect-src allows www.facebook.com
  PASS  / fires pixel 1625233994894344
  PASS  /features fires pixel 1625233994894344
  PASS  /audit fires pixel 1625233994894344
  PASS  /pricing fires pixel 1625233994894344
  PASS  /for-clinics fires pixel 1625233994894344

passed: 7  failed: 0
```

The definitive business-signal verification is the 24h Meta Ads re-pull. Expect LPV/link-click ratio to climb from 6% to 50%+ (ideally 70%+) within 24–48 hours of deploy. If not, CSP passed but there's a secondary blocker (GTM consent gating, event_id dedup, etc.) and the plan file has a 9-hypothesis backup list.

---

## How to Apply

| Situation | Response |
|---|---|
| "Why are my GA4 / Meta / LinkedIn / TikTok / any other pixel numbers suspiciously low on jotpsych.com?" | First diagnostic: `curl -sI https://jotpsych.com/` and check the `content-security-policy` header for the tracking vendor's domains. If missing, that's the bug. Second step: read `site/_headers` in the new_landing_page repo to confirm. |
| "Should I look at GTM first?" | No. GTM is a common suspect but on this site it's been wrong twice in a row. Check CSP first, GTM second. |
| "What's the Meta Pixel ID for the marketing site?" | `1625233994894344` (WebApp Actions). If anyone cites `340582149007668`, they're reading stale data. |
| "Where does the CSP live?" | `jotpsych_gtm/new_landing_page/site/_headers`. NOT `netlify.toml` — that only handles `pretty_urls`. |
| "Can I trust the 2026-04-04 → 2026-04-13 ads briefing's kill/scale verdicts?" | No. LPV signal was 6% real during that window. Wait until ~2026-04-17 for three days of clean post-fix data before acting on those verdicts. The CpFN totals are accurate; the per-ad attribution will rebalance. |
| "Why did Meta's CpFN drop this week compared to last week?" | Tracking correction, not performance change. Do not re-budget on it. Wait ~7 days for the new baseline to stabilize. |
| "How do I verify tracking is still working before a deploy?" | Run `scripts/lpv_tracking_check.sh` in the ads_engine project. 7/7 pass = green. |
| "A new tracking vendor is being added to the site — what's the CSP checklist?" | Add the vendor's script host to `script-src`, tracking XHR host to `connect-src`. Check `img-src` is wildcard (it is — `'self' https: data:`). Commit to `site/_headers`. Redeploy via `/push-to-jotpsych-com`. |
| "Someone wants to swap or retire the `340582149007668` dataset in Meta Events Manager." | It's orphaned from the site as of 2026-04-14. Retiring is safe. Decide with Nate whether to keep for historical continuity. |

---

## What This Brief Does NOT Cover

- **The GTM container configuration.** This brief does not audit GTM tags, triggers, or consent gating. GTM was not the cause of this specific outage but could be a contributor to other tracking questions.
- **The Conversions API (CAPI) migration.** Server-side Meta event delivery is a viable future project but out of scope — this fix is the browser-side pixel.
- **Historical data recovery.** The weeks of under-counted LPV data cannot be backfilled. Meta's reporting API does not expose "uncounted events."
- **The 2FA signup tracking break.** A separate bug noted in the ads_engine project — SMS verification disrupts the conversion tag fire at signup. Different bug, different fix.
- **LinkedIn / TikTok / other pixels.** jotpsych.com does not currently fire them. If they're added later, the CSP checklist above applies.
- **App-side tracking (`app.jotpsych.com`).** Different CSP, different domain, different GTM behavior. Audit separately.

---

## Open Questions

1. **24h LPV ratio verification.** Owner: Nate. Due: 2026-04-15 (one day post-deploy). Expected: LPV/link-click ratio > 50%. If < 30%, fix failed and secondary diagnosis needed.
2. **Retire `340582149007668` (JotPsych Actions) dataset in Meta Events Manager?** Owner: Nate / Adam Harrison. Due: 2026-04-21. Not urgent. Orphaned from the site, safe to retire.
3. **Update `~/.claude/skills/push-to-jotpsych-com/SKILL.md` line 84.** Owner: Nate. Due: before next `/push-to-jotpsych-com` invocation. The skill's Phase 3 validation still expects the old pixel ID and will flag every page as "stripped" until updated to `1625233994894344`.
4. **Re-evaluate 10-day briefing kill/scale verdicts.** Owner: Nate. Due: 2026-04-17 (3 days post-deploy, once Meta has clean signal). Specifically re-check Test: SB Video 1, Farm: Nate Podcast 4, Scale: Test: AI for Progress Notes Concept 3 — all were starving worst.
5. **Cross-vendor CSP audit policy.** Open question for the team: when one tracking vendor's CSP is fixed, should it be policy to audit all other vendors the same day? This would have caught the Meta gap two weeks earlier.

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| Meta Pixel ID — canonical (WebApp Actions) | `1625233994894344` |
| Meta Pixel ID — orphaned (JotPsych Actions) | `340582149007668` |
| GTM container ID (shared with app) | `GTM-KL9RPN9V` |
| Fix commit | `8664313` in `smartscribe/jotpsych.com` |
| Prior half-fix (GA4 only) commit | `62df031` in `smartscribe/jotpsych.com` |
| Netlify deploy ID | `69deae2cc8fee026819436ee` |
| Marketing site repo | `jotpsych_gtm/new_landing_page` |
| Netlify headers file | `jotpsych_gtm/new_landing_page/site/_headers` |
| Regression test script | `jotpsych_gtm/ads_engine/scripts/lpv_tracking_check.sh` |
| Plan + writeup | `jotpsych_gtm/ads_engine/plans/lpv-tracking-fix-2026-04-14.md` |
| Related brief (GA4/Google Ads CSP fix) | `jotpsych_gtm/ads_engine/docs/jot-briefs/ga4-csp-fix-2026-04-13.md` |
| 10-day ads briefing (context for kill/scale verdicts that need re-eval) | `jotpsych_gtm/ads_engine/data/ads-reports/briefing-10d-2026-04-14.html` |
| Netlify site name | `jotpsych-landing` |
| Production domain | `www.jotpsych.com` |

---

## Sources

[^1]: Meta Ads Insights pull for `act_{JotPsych ad account}` 2026-04-04 → 2026-04-13, summarized in `jotpsych_gtm/ads_engine/plans/lpv-tracking-fix-2026-04-14.md` ("The evidence" section). 170,413 impressions, 2,793 link clicks, 170 LPVs, 24 FirstNote conversions.
[^2]: `jotpsych_gtm/new_landing_page/site/_headers` pre-fix state (prior to commit `8664313`). Also visible in commit `62df031` from 2026-04-13 which added Google hosts but not Facebook.
[^3]: `jotpsych_gtm/new_landing_page/site/index.html` line 12–13 (pre-fix). Same pattern on all 38 site HTML files.
[^4]: `git log --oneline -20` in `jotpsych_gtm/new_landing_page` on 2026-04-14. Commit `62df031` message: *"Site update: fix CSP to unblock GA4 and Google Ads tracking."*
[^5]: Commit `8664313` in `smartscribe/jotpsych.com` on 2026-04-14. 37 files changed (36 tracked HTML + `_headers`), 75 insertions / 75 deletions. Additional in-place swaps on untracked `audit.html` + `making-time-for-presence.html` rode the Netlify deploy but were not committed.
[^6]: `jotpsych_gtm/ads_engine/scripts/lpv_tracking_check.sh` run against `https://jotpsych.com` on 2026-04-14 at deploy time. Output captured in the commit's verification step.
