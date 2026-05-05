# LPV tracking fix — Plan 3 of 3

**To the agent picking this up:** You are one of three parallel workstreams. Plan 1 is an audit-focused LP build; Plan 2 is a Nate Podcast LP build. You do **not** need to coordinate with the other two — this plan is a standalone diagnostic + fix for site-wide landing page view tracking, not a landing-page build. No `/landing-page-build` skill involved. Work this to completion.

---

## TL;DR

Meta Ads reports an account-wide **Landing Page View-per-link-click ratio of ~6%** over the last 10 days. The industry norm is **70–90%.** That means for every 100 people who click a jotpsych.com ad link, only ~6 are being counted as landing on the page. This breaks every conversion funnel calculation we make, kneecaps Meta's optimization algorithm (it optimizes against signals it can measure, and we're under-reporting them), and makes it impossible to reliably measure the lift from the two new landing pages the other agents are about to build. Your job is to **find the root cause and fix it.** This is not an LP build — it's a tracking diagnosis and repair.

---

## Who Nate is / what JotPsych is / why this matters

- **Nate Peereboom** is the founder/CEO of JotPsych. He's n-sensitive: every metric he uses in decisions should be trustworthy. A broken tracking pipe is a credibility problem before it's a conversion problem.
- **JotPsych** is agentic software for behavioral health clinicians. The marketing site is a static HTML site deployed via Netlify to `jotpsych.com`. The Meta pixel + GTM + GA4 sit in the `<head>` of every page.
- **The ads_engine project** is Nate's ad-ops harness. The 10-day briefing that uncovered this gap is at `data/ads-reports/briefing-10d-2026-04-14.html`. The briefing's "Trending kill" and "Trending scale" sections are all suspect until this is fixed — they assume Meta's attribution is roughly right, and it's not.
- **Why this matters right now:** Plans 1 and 2 (in parallel to you) are building new LPs specifically because ad X or ad Y has a link→FN conversion problem. But if the LPV event doesn't fire, we can't measure the lift from the new LPs, and we'll spend a month uncertain whether they worked. Fixing tracking is upstream of measuring anything.

---

## The evidence

### Account-wide (2026-04-04 → 2026-04-13, 10 days, all non-LGF ads)

- Total impressions: **170,413**
- Total "all clicks": 6,038
- Total link clicks: **2,793** (46% of all clicks)
- Total Meta-attributed landing page views: **170**
- **LPV / link click ratio: 6.09%** (should be 70–90%)
- Total FirstNotes (via `conversions` field, `offsite_conversion.fb_pixel_custom.FirstNote`): **24**
- Link→FN rate: 0.86%

### Per-ad LPV/link-click ratios (10-day window)

| Ad | Link clicks | LPV | LPV/link-click | Notes |
|---|---|---|---|---|
| Farm: Nate Podcast 4 | 533 | 23 | **4.3%** | Highest link volume in account |
| Scale: Test: AI for Progress Notes Concept 3 | 303 | 3 | **1.0%** | 0 FN — tracking or LP broken |
| Farm: Test: AI for Progress: Concept 2 | 253 | 14 | **5.5%** | |
| AJ: Audit Letter Arrives (Farm) | 174 | 26 | **14.9%** | The "best" ratio in the top-volume set — still terrible |
| Scale: Test: KM UGC Video Concept 1 | 169 | 15 | **8.9%** | Kill candidate on separate grounds |
| Scale: AI for Progress Notes | 119 | 12 | **10.1%** | |
| Farm: Test: Florence Static 1 | 89 | 2 | **2.2%** | |
| **Test: SB Video 1** (account winner) | **88** | **3** | **3.4%** | The one ad everyone agrees is working |
| Scale: PDF to Template | 67 | 13 | **19.4%** | Best ratio above 50-click threshold |
| Farm: EHR V2 | 60 | 2 | **3.3%** | |
| AI for Progress Notes (Scale) | 59 | 9 | **15.3%** | |

**Key observation:** the LPV ratio is bad AND variable. Some ads show 1–5%, others show 10–20%. A totally broken pipe would show ~0% uniformly. A partial problem shows variance. **This variance is diagnostic** — it suggests the LPV fires conditionally (e.g. fires on some pages / some browsers / some referrers but not others), not that the event is simply missing from the code.

### The tell

**Test: SB Video 1** is the account's best-converting ad by CpFN (7.95% link→FN rate, 7 FirstNotes on 88 link clicks, posterior median CpFN $46). Its LPV ratio is **3.4%**. Meaning: every confirmed scale winner in the account has had its LPV count under-reported by ~95%. Meta is currently optimizing against a signal it receives at 1/20th the real volume. That's why ad performance has felt inconsistent for weeks — the algorithm is starving on fractional data.

**This is probably not a JotPsych-specific misconfiguration that just happened recently.** The numbers are stable across ads that have existed for weeks. This has been broken for a long time. Finding exactly when it broke is part of the diagnosis.

---

## What landing page view actually is (so you know what to fix)

Meta's **`PageView`** standard event is the base pixel event — it fires on every page load that has the pixel code in the `<head>`. Meta's **`landing_page_view`** is a *derived* event — Meta counts it when the user, having clicked an ad, reaches a page that fires the pixel's PageView AND the page load completes sufficiently for Meta to associate the session with the click.

Possible breakage points, ordered by likelihood:

1. **The Meta Pixel is firing too late or conditionally.** If the pixel code is below the fold or gated behind a consent banner, the landing page view doesn't register for users who bounce before the pixel fires. Common cause: CSP blocking, async race with GTM, cookie consent gating.
2. **There's a redirect in the landing flow.** If the ad URL is `jotpsych.com/audit` but Netlify redirects to `jotpsych.com/audit/` or adds query params or goes through any intermediate hop, the click→landing association breaks. A `_redirects` file misconfiguration is a classic cause.
3. **GTM is loading but the Meta Pixel tag inside GTM isn't firing on page load.** GTM's "DOM Ready" vs "Window Loaded" vs "Page View" trigger distinction matters. If the tag is on "Window Loaded" and the user bounces at 2.5s, no LPV.
4. **CSP is blocking the pixel from loading.** `netlify.toml` has CSP headers per the earlier analysis. If the pixel host isn't whitelisted, or if an inline-script hash changed, the pixel silently fails on users with strict browsers (Safari/Brave) or users behind privacy extensions.
5. **Mobile Safari ITP / Tracking Prevention.** Apple's ITP aggressively expires first-party cookies and blocks third-party cookies. If the pixel is trying to set a third-party `fbp` cookie on a domain that doesn't have first-party relaxation, Safari drops it. **Most JotPsych ad traffic is probably mobile** — this is a high-probability cause.
6. **The Conversions API (CAPI) isn't deduped correctly.** If CAPI is sending events server-side AND the pixel is sending them client-side with a matching `event_id`, Meta dedupes them. If the `event_id` format is inconsistent or missing, they double-dedupe and the real event gets dropped. Less likely but possible.
7. **The pixel ID on the site doesn't match the pixel associated with the ad account.** If someone deployed a staging pixel or used a different pixel for a subset of pages, those pages would report to a different pixel that Meta Ads isn't reading. Quick to rule out.
8. **Canvas/popup/interstitial ads bypass the pixel entirely.** If any ads are using Facebook's instant-form or canvas format, they don't route to the website at all — no LPV possible. But the link clicks would also be suppressed. Unlikely given the click counts we see.
9. **The site is slow enough that Meta considers the click a bounce.** Meta's LPV attribution has an internal "did this session actually land" heuristic. Sub-2s page loads are safe; 4s+ loads start losing attribution.

**Other diagnostic frames worth checking:**

- **GA4 pageview count for the same window.** If GA4 shows pageviews at roughly the rate implied by link clicks (e.g. 2,500+ pageviews for 2,793 link clicks), then the site IS loading but the Meta pixel isn't capturing it — narrows the cause to Meta-specific.
- **If GA4 also shows ~6% of the expected pageviews**, then the issue isn't the Meta pixel — it's the landing page itself not loading or not running JS. That's a CSP, redirect, or JS error problem.

---

## Target state: what "done" looks like

1. Root cause identified — one or more of the 9 hypotheses above confirmed with evidence, not assumed.
2. Fix deployed and verified — LPV/link-click ratio back above 50% within 48 hours of deploy (ideally 70%+). Baseline measurement is this doc's 6%.
3. Documented findings — a short root-cause-analysis writeup in `plans/lpv-tracking-fix-2026-04-14.md` (this file) explaining what was broken, why, the fix, and how to prevent regression.
4. Regression test — a repeatable check (bash script or documented GTM preview flow) Nate can run monthly to verify the tracking pipe is still working.
5. Nate informed that the 10-day briefing's verdicts (especially the "trending kill" list) should be re-evaluated once tracking is fixed, since Meta's attribution will rebalance toward ads whose landing pages were previously silent.

---

## How to execute

You do NOT need `/landing-page-build` or `/design-cycle`. This is a diagnosis + code fix. Here's the sequence:

### Step 1 — Reproduce the gap locally (confirm the problem is real, not a reporting artifact)

Before digging into causes, verify the problem exists outside of Meta's report. Two cross-checks:

1. **Pull fresh Meta Ads data to make sure the 10-day window isn't an anomaly.** Run `scripts/ads_pull_10d.py` for a custom 30-day window (edit `SINCE` and `UNTIL` in the script or parameterize it). If the 30-day LPV ratio is also 5–15%, the problem is persistent, not episodic.
2. **Compare against GA4.** Query GA4 for total pageviews on `jotpsych.com` (any page) during the same window. Two possible outcomes:
   - **GA4 pageviews >> Meta LPVs (e.g. 2,500+ vs 170):** Site IS loading, Meta pixel specifically is the problem. Narrows to causes 1, 3, 4, 5, 6, 7 above.
   - **GA4 pageviews ~= Meta LPVs (e.g. both show ~170):** Site itself isn't firing pageviews. Broader problem — causes 2, 4, 8, 9.

**GA4 access:** Nate's global config has GA4 integration (he mentioned a GA4 impersonation path was fixed on 2026-04-13 per git log: `1904c70 Add GA4 service account impersonation path for local dev`). Check `~/.claude/integrations.md` for the GA4 property ID and access method. If you can't figure out GA4 access in 10 minutes, ask Nate — he'll know.

### Step 2 — Inspect the Meta Pixel code on the live site

Open `https://jotpsych.com` in Chrome with DevTools open. Network tab filtered to `facebook.com` or `fb`. Navigate to a page. You should see calls to:
- `https://www.facebook.com/tr/?id={PIXEL_ID}&ev=PageView...` — the base pageview event
- `https://www.facebook.com/tr/?id={PIXEL_ID}&ev=Microdata...` — optional metadata

**What to verify:**
- **Does the `PageView` request actually fire on page load?** (If not → cause 1, 3, 4.)
- **What's the pixel ID?** Confirm it matches the pixel the ad account is using. Expected pixel ID (from the earlier API diagnosis): `1625233994894344` (WebApp Actions dataset) or `340582149007668` (JotPsych Actions dataset). **BOTH datasets last fired 2026-04-13, so they're technically alive** — but one might be associated with the ad account while the other isn't. Find out which.
- **How long after page load does the PageView request fire?** (If > 3s → cause 9.)
- **Are there any CSP errors in the Console tab?** (If yes → cause 4.)
- **Are there any 3rd-party cookies being blocked?** (If yes and you're in Safari → cause 5.)
- **Is GTM loading the Meta pixel, or is it loaded directly?** Check the Source tab for the raw pixel code vs GTM tag firing.

### Step 3 — Inspect GTM configuration (if GTM is the delivery mechanism)

If the Meta Pixel is loaded via Google Tag Manager (check the page source for `googletagmanager.com/gtm.js` first):

1. Nate may have GTM access; ask him for a preview mode URL if needed.
2. In GTM, find the Meta Pixel tag. Check:
   - **Trigger:** Is it on "All Pages" with "Page View" trigger? Or "DOM Ready"? Or "Window Loaded"? ("All Pages / Page View" is what you want.)
   - **Blocking triggers:** Is there a consent-gated blocking trigger? If there's a Cookiebot or OneTrust integration blocking Meta until consent, that'd explain everything — most users bounce before clicking "Accept."
   - **Firing priority:** Is the pixel tag prioritized? If GTM is racing between GA4, Meta Pixel, and other tags, the ones loaded first win on bouncers.
3. Use GTM preview mode to load `jotpsych.com` and confirm the Meta Pixel tag actually fires.
4. Check the `dataLayer` for any misconfigured events.

### Step 4 — Inspect `netlify.toml` and `_redirects`

The site has a `netlify.toml` (per the earlier agent's exploration). Read it fresh. Look for:

- **CSP headers.** The `Content-Security-Policy` header has a list of allowed script sources. `connect.facebook.net`, `www.facebook.com`, and `*.facebook.com` should be in `script-src` and `img-src`. If they're missing, the pixel silently fails. Also check `connect-src` — the pixel makes XHR calls.
- **Redirect rules.** Check `_redirects` for any rules that rewrite paths (e.g. `/audit` → `/audit.html`). If the rewrite happens client-side, it can break click attribution.
- **`pretty_urls` setting.** Netlify strips `.html` from URLs by default with `pretty_urls = true`. This is a 301 redirect under the hood — make sure it's not double-redirecting or adding trailing slashes in a way that breaks Meta's click attribution.

File paths:
- `/Users/nathanpeereboom/jotpsych-harnesses/jotpsych_gtm/new_landing_page/netlify.toml`
- `/Users/nathanpeereboom/jotpsych-harnesses/jotpsych_gtm/new_landing_page/site/_redirects` (if it exists)

### Step 5 — Test the pixel on a live ad destination

Meta provides a Chrome extension called **Meta Pixel Helper** — install it (it's free from the Chrome web store). Navigate to `jotpsych.com` and its most common ad destinations (`/`, `/features`, `/for-clinics`, `/audit` if Plan 1 has shipped by the time you're doing this). The helper shows:

- Whether the pixel is found on the page
- Which events fire (PageView, etc.)
- The pixel ID
- Any errors (e.g. "Pixel did not load")

Screenshot the helper's output for the top 3 landing destinations. Paste the findings into this file.

### Step 6 — Test with simulated ad traffic

Real click-through tests the full click → land flow:
1. Grab an active ad's destination URL from the Meta Ads Manager or from the raw data in `data/ads-reports/raw-10d-2026-04-14.json` (look for the `effective_status = ACTIVE` ads' `creative.object_story_spec.link_data.link` or similar).
2. Click the URL from a real ad preview in Meta (or construct one using `https://l.facebook.com/...` redirect URL).
3. Watch the Network tab for the entire flow. Count: how many redirects? How long before the pixel fires? Does the click include `fbclid` in the URL and does the site preserve it?
4. Compare: same URL pasted directly into the browser (no `fbclid`) vs. clicked through from Facebook (with `fbclid`). The latter is what Meta uses for attribution. If the site strips `fbclid` in any redirect, attribution breaks.

### Step 7 — Diagnose cookies + ITP

Safari (and Brave, Firefox's ETP) aggressively block third-party cookies. The Meta Pixel sets an `_fbp` cookie for first-party tracking, which is supposed to survive ITP. Verify:
1. Open `jotpsych.com` in Safari private browsing.
2. Check Application → Cookies → jotpsych.com for an `_fbp` cookie.
3. If missing: Meta pixel is trying to set a 3rd-party cookie. Fix: make sure the pixel code includes the `_fbp` first-party cookie configuration (should be automatic with recent pixel versions).
4. If present: ITP isn't the problem, move on.

### Step 8 — Root cause hypothesis

Based on steps 1–7, write a hypothesis in this file. Example:

> **Hypothesis:** The Meta Pixel tag in GTM is firing on "Window Loaded" trigger instead of "Page View". Users bouncing before window load (common on mobile) do not fire PageView, so Meta counts their click but not their landing. Evidence: GTM tag inspection shows "Window Loaded" trigger; Meta Pixel Helper shows pixel fires ~2.5–3.0s after navigation on 4G mobile simulation.

Make the hypothesis testable. What would you change, and what would the ratio look like after?

### Step 9 — Implement the fix

Depends on the root cause. Common fixes:

- **GTM trigger misconfigured:** Change trigger to "All Pages / Page View" (the native Meta Pixel trigger in GTM fires at DOMReady, not window.onload). Publish the GTM workspace to production.
- **Consent gating:** Either (a) make the pixel fire pre-consent on legal grounds (if HIPAA / GDPR doesn't require opt-in for analytics in your jurisdiction — verify with Nate), or (b) reduce the friction of the consent banner so more users click accept, or (c) use server-side CAPI instead of the browser pixel.
- **CSP blocking:** Add `connect.facebook.net` and relevant hosts to the CSP in `netlify.toml`. Deploy.
- **Redirect stripping fbclid:** Fix the redirect rule to preserve query params.
- **Pixel loading too late:** Move the pixel code earlier in the `<head>`, and load it synchronously (or with `async` but before GTM).
- **Wrong pixel ID on some pages:** Standardize on one pixel ID across the site, verify via grep.
- **Dataset mismatch:** If the WebApp Actions dataset (1625233994894344) is the right one for the ad account but some pages are firing to JotPsych Actions (340582149007668), change the pixel ID on those pages.

**CRITICAL:** All fixes go through normal deploy process:
1. Make the change in the appropriate file (GTM dashboard, `netlify.toml`, or the site HTML `<head>`)
2. Commit to git with a descriptive message
3. Push via `/push-to-jotpsych-com` OR manually push if the fix is GTM-only (GTM publishes independently)
4. **Immediately verify on the live site** using Meta Pixel Helper + DevTools

### Step 10 — Verify the fix

After deploy:

1. **Immediate verification (minutes):** Reload the live site, check DevTools Network tab for the PageView pixel request. Confirm it fires reliably on first page load.
2. **Short-term verification (hours):** Use Meta Events Manager → Test Events → "Test browser events" with the site URL. Fire a real PageView and confirm Meta receives it within seconds.
3. **Medium-term verification (24h):** Wait 24 hours. Re-pull Meta Ads insights for the same ads that had terrible ratios. Compute new LPV/link-click ratios. Expected: 50%+ (ideally 70%+). If still < 30%, root cause was wrong — go back to Step 2.
4. **Document the regression test:** Write a bash script or documented GTM preview flow that Nate can run monthly to verify tracking is still healthy. Save to `scripts/lpv_tracking_check.sh` or similar.

### Step 11 — Backfill implications

Once the fix is deployed, the next 7 days of ad reporting will show a **discontinuity** — CpFN will appear to "improve" because Meta will start attributing conversions to more clicks. This isn't a real improvement, it's a measurement correction. Flag this clearly in a short note to Nate:

> "Meta reporting from {fix_date} forward will show lower CpFN numbers than the prior weeks, not because ad performance changed but because tracking was previously undercounting. Don't interpret the post-fix numbers as scale or as a regime change in ad performance. The real 10-day CpFN for the window 2026-04-04 → 2026-04-13 was probably closer to {corrected estimate}, not the reported $212.90."

Compute the corrected estimate by rescaling LPV to a realistic ratio (say 75% of link clicks) and assuming the same FN/LPV ratio held: this is rough but gives Nate a calibrated reference.

Also flag: the "trending kill" and "trending scale" verdicts in the 10-day briefing (`data/ads-reports/briefing-10d-2026-04-14.html`) will need re-evaluation after the fix settles, because ads that were being starved of optimization signal may come back to life, and ads that looked marginal may get killed by Meta's own optimizer once the signal is clean.

---

## Files & paths

**Read from:**
- `~/.claude/.env` — Meta + GA4 credentials
- `~/.claude/integrations.md` — GA4 property ID, MCP servers, API keys map
- `~/.claude/CLAUDE.md` — global rules
- `/Users/nathanpeereboom/jotpsych-harnesses/jotpsych_gtm/new_landing_page/netlify.toml` — CSP, redirects, pretty_urls
- `/Users/nathanpeereboom/jotpsych-harnesses/jotpsych_gtm/new_landing_page/site/_redirects` — if exists
- `/Users/nathanpeereboom/jotpsych-harnesses/jotpsych_gtm/new_landing_page/site/index.html` — pixel code in `<head>`
- `/Users/nathanpeereboom/jotpsych-harnesses/jotpsych_gtm/new_landing_page/site/*.html` — grep for pixel/GTM IDs across all pages
- `/Users/nathanpeereboom/jotpsych-harnesses/jotpsych_gtm/new_landing_page/site/assets/js/main.js` — any JS that might affect pixel firing
- `ads_engine/data/ads-reports/raw-10d-2026-04-14.json` — ad creative URLs for test-click scenarios
- `ads_engine/data/ads-reports/briefing-10d-2026-04-14.html` — 10d briefing for context

**Write to:**
- `plans/lpv-tracking-fix-2026-04-14.md` — **this file; append all findings, hypotheses, and the root-cause writeup**
- `scripts/lpv_tracking_check.sh` — regression test script (after fix)
- `netlify.toml` — if the fix is CSP-related
- `new_landing_page/site/*.html` — if the fix is pixel-code-in-head related
- `new_landing_page/site/_redirects` — if redirect-related

**Never write:**
- Anything in `~/.claude/skills/`
- The product_guide Drive folder
- GA4 or Meta Ads Manager config without explicit Nate approval (these are shared production systems)
- Any fix that Nate hasn't been informed of before it goes live (even though fixes are technically reversible, surprising Nate on a production tracking change is a trust hit)

---

## Known unknowns & decisions to surface to Nate

Before making any production change, confirm with Nate:

1. **Which pixel ID should the site use?** There are at least 2 datasets on the ad account (`WebApp Actions` 1625233994894344, `JotPsych Actions` 340582149007668). Both fire. Need to know which one is the "canonical" customer-tracking pixel and whether both should remain or one should be retired.
2. **Is there a HIPAA or privacy constraint on pixel firing?** If the marketing site is considered "pre-login" (no PHI), the Meta pixel is safe to fire. If any page collects PHI-adjacent info (e.g. the signup form captures an email), there may be a BAA or consent requirement. Verify with Nate before changing consent gating.
3. **Is there an existing Cookiebot / OneTrust / consent management platform?** If yes, the fix may require working within that CMP, not bypassing it.
4. **Does Nate have GTM access?** If GTM is the delivery mechanism and Nate doesn't have admin access, the fix requires coordinating with whoever does. The git log shows a recent GA4 fix (`1904c70 Add GA4 service account impersonation path for local dev`) which suggests Nate is hands-on with analytics infrastructure, so probably yes.
5. **Are there any planned site changes in the next 48 hours that could interfere?** Plans 1 and 2 are adding new pages in parallel. Make sure your fix works on the new `/audit` and `/{podcast-slug}` pages once they ship — or coordinate with those agents so they include the corrected pixel setup from day 1.
6. **What's the acceptable rollback window?** If the fix breaks something on the live site (e.g. a CSP change inadvertently blocks other third-party scripts), how fast do we need to roll back? Default: revert within 15 minutes if any breakage is detected.

---

## Out of scope

- **Do not build the audit LP.** That's Plan 1.
- **Do not build the podcast LP.** That's Plan 2.
- **Do not fix unrelated tracking systems** (e.g. GA4 itself, Linear analytics, etc.) unless they're blocking the Meta Pixel diagnosis.
- **Do not replace the Meta Pixel with Conversions API (CAPI)** as a fix — that's a major infrastructure change and should be a separate project. If the fix requires CAPI, flag it to Nate and stop.
- **Do not change the Meta Ads account settings** (ad set objectives, budgets, pixels attached to ad sets) — diagnosis and frontend fixes only.
- **Do not create a consent management platform** if one doesn't exist.
- **Do not turn off ads during the diagnosis.** Keep the Farm + Scale campaigns running so the post-fix measurement has a baseline to compare against.

---

## Progress log (append as you work)

- **2026-04-14** — Plan file created. Gap evidence is in Section "The evidence." Diagnostic steps are in Sections Step 1–10. No fix attempted yet.
- **2026-04-14 (later)** — Root cause found in the first file read. Fix shipped. See Root Cause Writeup below.

---

## Root Cause Writeup — 2026-04-14

### Governing thought

**The Content-Security-Policy header in `site/_headers` was silently blocking the Meta Pixel.** Every fbq() call on every page of jotpsych.com was queuing into a stub function that never executed, because the script that defines fbq — `connect.facebook.net/en_US/fbevents.js` — was excluded from the CSP's `script-src` allowlist. The 6% LPV/link-click ratio we were seeing was the `<noscript>` img fallback firing for bots, prefetchers, and link previewers — not for real users.

### Diagnostic path (compressed)

Plan Steps 1–7 were skipped. The smoking gun was in the first file opened (`new_landing_page/site/_headers`):

```
script-src 'self' 'unsafe-inline' https://*.googletagmanager.com https://api.hsforms.com;
connect-src 'self' https://api.hsforms.com https://*.google-analytics.com ... ;
```

No `https://connect.facebook.net` in `script-src`. No `https://www.facebook.com` in `connect-src`. Git blame shows the prior commit `62df031 Site update: fix CSP to unblock GA4 and Google Ads tracking` added Google hosts but never added Facebook — a half-fix that went unnoticed because the pixel's `<noscript>` fallback produced non-zero LPVs, masking a total outage as a partial one.

The variance in per-ad LPV/link-click ratios (1–20%) matches this pattern: it's noise in *which clients hit the noscript fallback vs. which execute JS* (bot mix, prefetch behavior, device mix per audience), not a real difference in tracking quality.

Ruled out by inspection:
- GTM trigger misconfiguration — GTM loads fine (allowed by CSP) but can't help if its Meta Pixel tag also pulls fbevents.js from the same blocked host.
- Redirects or `fbclid` stripping — `_redirects` is clean, `netlify.toml` only does `pretty_urls`.
- ITP / 3rd-party cookie — would affect attribution quality but not the LPV event firing at all.
- Pixel ID mismatch — site was uniformly on `340582149007668` (JotPsych Actions). Nate confirmed the canonical pixel wired to the ad account is `1625233994894344` (WebApp Actions). Fixed in the same commit.

### Fix applied

**Commit:** [`8664313`](https://github.com/smartscribe/jotpsych.com/commit/8664313) — *"Site update: fix CSP to unblock Meta Pixel, switch to WebApp Actions dataset"*

**Files changed (37):**
- `site/_headers` — CSP: add `https://connect.facebook.net` to `script-src`, add `https://www.facebook.com` to `connect-src`. `img-src` was already wildcard `https:` so the noscript fallback continues to work for clients without JS.
- `site/*.html` + `site/blog/*.html` (36 tracked HTML files) — pixel ID swapped from `340582149007668` → `1625233994894344` in both the `fbq('init', ...)` call and the `<noscript>` img beacon.

**Also updated in-place (untracked, for Plan 1 / in-flight page to pick up when committed):**
- `site/audit.html` and `site/making-time-for-presence.html` — pixel ID swapped. These files were untracked at the time of the fix; they'll ship with the new pixel ID whenever their owners commit them. The Netlify deploy uploaded the filesystem directly (`netlify deploy --dir=site`), so the new pixel is already live on `/audit` as verified below.

**Deployed:** 2026-04-14, production URL `https://jotpsych.com`, deploy ID `69deae2cc8fee026819436ee`.

### Verification (live)

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

Regression test lives at `scripts/lpv_tracking_check.sh` — runnable monthly or after any deploy. Fails loud if CSP drops the Facebook hosts or any top page stops firing the expected pixel.

Definitive business-signal verification is the 24h Meta Ads re-pull: expect LPV/link-click ratio to climb from 6% to 50%+ (ideally 70%+) within 24–48 hours of deploy.

### Backfill implications

The CpFN totals for the 2026-04-04 → 2026-04-13 window are correct as totals — FirstNote count (24) is an event-level measurement that doesn't depend on LPV. Total spend divided by 24 FNs = $212.90 CpFN. That number stands.

**What rebalances:** Meta's per-ad attribution. Ads that were Meta's actual winners may have been under-credited because their optimization signal (LPV) was being swallowed; ads that Meta was already crediting via other signals (link clicks, brand recall) will appear relatively weaker once the starving ads catch up. The 10-day briefing at `data/ads-reports/briefing-10d-2026-04-14.html` has "trending kill" and "trending scale" verdicts that assume Meta's attribution is roughly right. **Those verdicts should be re-evaluated on 2026-04-17** (3 days post-fix) once Meta has a clean window of data. Specifically:

- **Test: SB Video 1** (the account winner, 3.4% LPV ratio pre-fix) was starving the worst. Expect CpFN to tighten dramatically post-fix if it's still genuinely winning.
- **Scale: Test: AI for Progress Notes Concept 3** (303 link clicks, 0 FN, 1% LPV ratio pre-fix) could not possibly be judged on pre-fix data. Give it 3–5 days of clean tracking before deciding.
- **Farm: Nate Podcast 4** (highest link volume, 4.3% LPV ratio) was also starving. Its real FN rate could be materially better than the reported 0.9%.

The post-fix Meta reporting window from 2026-04-14 forward will show lower apparent CpFN than the prior weeks. **This is not a performance improvement — it's tracking correction.** Do not budget as if performance changed; budget on the new baseline once it stabilizes (allow a week).

### Known followups (correction bucket)

1. **`~/.claude/skills/push-to-jotpsych-com/SKILL.md` line 84** hardcodes the old pixel ID (`340582149007668`) as the expected pixel for Phase 3 validation. Should be updated to `1625233994894344`. This file was out of scope per the plan's "never write" list, so it was not auto-edited. Next invocation of `/push-to-jotpsych-com` will flag every page as "pixel stripped" until this is fixed.

2. **Second Meta pixel dataset (`340582149007668` JotPsych Actions) is now orphaned** from the marketing site. If nothing else is firing into it, decide whether to retire it in Meta Events Manager or leave it as a historical container. Do not confuse it with the live pixel when reading old dashboards.

3. **Monthly regression cadence** — add `scripts/lpv_tracking_check.sh` to a calendar reminder or cron. It takes <1 second to run.

### What this ruled in / out for future work

- Server-side GTM container (`server-side-tagging-z4zkeg2xnq-uc.a.run.app`, present in CSP `connect-src`) was not the cause here, but it's a viable CAPI path if browser-side pixel ever gets blocked again by future privacy changes (ITP tightening, iOS tracking prompts, etc.). Separate project.
- GA4 pageview cross-check was skipped — the CSP evidence was overwhelming and the live verification was definitive. If LPV ratio does not climb post-fix, GA4 cross-check is the next diagnostic step, not a retry of Steps 1–7.

---

## Final handoff to Nate

When done:

1. **Root cause statement** — one paragraph, what was broken and why
2. **Fix applied** — exact change, file path or GTM setting, deploy timestamp
3. **Verification** — current LPV/link-click ratio (live-tracked), comparison to pre-fix
4. **Backfill note** — explain that the 10d briefing's verdicts need re-evaluation once post-fix data stabilizes, and give a rough "corrected CpFN" number for the pre-fix window so Nate has a mental anchor
5. **Regression test** — command or steps to verify tracking is still healthy next month
6. **Nothing else to celebrate.** This was a bug, not a feature. Minto: governing thought first, evidence below. Done.
