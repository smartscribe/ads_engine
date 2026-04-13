# UTM Capture Investigation and Fix — jotpsych.com Marketing Cutover Bug

**Date:** 2026-04-13
**Author:** Nate + Claude
**Affected surface:** jotpsych.com marketing site → app.jotpsych.com handoff
**Severity:** High — 100% of UTMs dropped on marketing→app click since Mar 28; ads_engine CpFN attribution fully blocked for the entire period
**File changed:** `jotpsych_gtm/new_landing_page/site/assets/js/main.js`
**Deployment status:** Shipped 2026-04-13 ~12:58 PM via `/push-to-jotpsych.com`. Commit `6fcbf6c` on master, live at `www.jotpsych.com`.

---

## TL;DR

UTM-based attribution to JotPsych's `ACCOUNT_CREATED` event stopped working on **Mar 28, 2026** — the exact date the marketing site was cut over from Wix to a new static site. The old Wix site had a "signup bridge" page that captured URL params on landing and forwarded them to `app.jotpsych.com` on CTA click. The new static site didn't replicate that logic: all **175 "Try for free" CTAs across 34 HTML pages** were hardcoded as `https://app.jotpsych.com` with no query string. Every Meta ad click that hit jotpsych.com had its UTMs stripped the moment the user clicked any CTA. The web-app's `UTMTracker` code was working exactly as it had for a year; it just never received any UTMs to capture. The backend event pipeline was equally fine. The whole attribution chain was intact except for one missing link: the marketing→app handoff. Fix is a ~40-line JS snippet in `assets/js/main.js` (the shared script every page loads) that captures `utm_*` + click IDs (gclid, fbclid, etc.) to sessionStorage on first arrival and appends them to every `app.jotpsych.com` anchor on every page. Verified live with Playwright.

---

## Symptom That Kicked This Off

Today's ads_engine analysis for the last 7 days showed $2,312 of Farm/Scale spend producing 2 Facebook-attributed first-note signups via discovery-survey attribution. Even accounting for the 86% survey-skip rate, that was catastrophically off the historical $189–354 CpFN band and invited the wrong conclusion that the ads were broken.

A deeper check revealed it wasn't an ads problem at all — the downstream UTM-based attribution was returning 0 across the board. A daily rollup made the break obvious:

| Period | UTM-populated % of ACCOUNT_CREATED events |
|---|---|
| Feb 27 – Mar 27 | 20–50% (with normal day-to-day variation) |
| Mar 28 – Apr 13 | **0%** across 175 signups (one spurious 1 on Mar 30) |

A discrete cliff, not a gradual decay. That pattern almost always points at a deploy.

---

## Diagnostic Steps Taken

### Step 1: Rule out the backend

Cloned `smartscribe/smartscribe-server` and traced the `/user/updateUserInfo` route handler. [user_routes.py:889](../../../jotpsych_product/smartscribe-server/services/ehr_api/lib/modules/users/routes/v1/user_routes.py#L889) accepts `utm` from the request body, writes it to `user_info["signup_utm"]`, and passes it to `UserSignupService.handle_new_user_signup()`. Both `ACCOUNT_CREATED` emission sites in [user_signup_service.py](../../../jotpsych_product/smartscribe-server/services/ehr_api/lib/modules/users/services/user_signup_service.py) — the v2 createUser path at line 187 and the legacy path at line 908 — explicitly include `"utm": utm` in the event payload. Backend is clean.

### Step 2: Rule out the web-app frontend

`UTMTracker.ts` in the web-app captures from `window.location.search` on initialization and stores to `sessionStorage['utm_session']`. `UserInfoForm.tsx:544` calls `UTMTracker.getUTMsForAPI()` and forwards the result in the `updateUserInfo` mutation body. Frontend is clean. Both the backend and the web-app frontend have been unchanged in substance for the duration of the break.

### Step 3: Rule out Meta-side config

Pulled creative config for every active ad in the Farm and Scale campaigns via the Meta Marketing API. Of 29 active ads:

- **20 Farm ads** had UTM templates at the creative `url_tags` level (`utm_source={{site_source_name}}&utm_medium=paid_social&utm_campaign={{campaign.id}}&utm_content={{adset.id}}&utm_term={{ad.id}}`).
- **4 Scale ads** had UTM templates inline in the destination URL (`asset_feed_spec.link_urls[0].website_url`) with the pattern `?utm_source={{site_source_name}}&utm_medium={{placement}}&utm_campaign={{campaign.name}}&utm_content={{adset.name}}`.
- **1 Farm ad** (`Farm: Nate Podcast 4 - ad`) had no UTMs in either location — the only genuinely misconfigured ad on the account.
- **1 Farm ad** used legacy HubSpot `hsa_*` params instead of `utm_` — functional but off-template.

Meta was sending users into `jotpsych.com` with UTMs correctly set. The landing URL in the user's browser had them. Something was stripping them after arrival but before the app saw them.

### Step 4: Ask Jot + Jackson's memory pinpoints the cause

Posted the symptom summary to Slack and tagged Jot. Jot's response identified the most suspicious commit as `55b6a99e4` (Mar 26, Alfred) — shared Auth0 callback logic for PR preview deployments — and noted cross-domain handoff as the top hypothesis for UTM loss. Jot's quoted paragraph:

> The Auth0 redirect itself is fine — app.jotpsych.com → auth0 → app.jotpsych.com/callback keeps the same origin so sessionStorage survives. But the pipeline has a single point of failure: UTMs must be present in `window.location.search` when the SPA loads on app.jotpsych.com. If anything upstream strips query params before the page loads, they're gone forever. Given the branding/marketing site work happening in that same window (Mar 26–30), my top hypothesis: the marketing site (jotpsych.com) redirect to app.jotpsych.com stopped forwarding query params. That would produce exactly the cliff you're seeing — discrete, 100% drop, nothing wrong in backend or frontend code.

Jackson's reply in the same thread was the confirming tell:

> I think the wix website had a special page that it went to after clicking signup that inserted some stuff to the utm. did you replicate that in the new site?

Nate's reply: "Nope — I didn't."

### Step 5: Audit the new landing page's CTA handoff

Located the new marketing site at `jotpsych_gtm/new_landing_page/site/`. Grepped for every instance of `app.jotpsych.com`:

```
Found 175 total occurrences across 34 files.
```

Spot-checked `index.html:251`:

```html
<a href="https://app.jotpsych.com" class="btn btn-primary">Try for free &rarr;</a>
```

Every CTA was a plain anchor with no query-string handling. When a user landed on `jotpsych.com/?utm_source=facebook&utm_campaign=Scale` and clicked any CTA, they arrived at `app.jotpsych.com` with zero query params. The web-app's `UTMTracker` then captured nothing because nothing arrived. Every Meta and Google ad UTM was lost on click.

---

## Root Cause

**The static landing site that replaced Wix on Mar 27–28 omitted the Wix signup-bridge page's UTM-forwarding logic.** The old Wix site had a dedicated intermediate page that caught URL params and injected them into the signup CTA before redirecting to the app. When the site was rebuilt from scratch as static HTML, that behavior wasn't documented anywhere and wasn't replicated.

Every other link in the attribution chain was still intact: Meta ads had UTM templates in their click URLs, the web-app's `UTMTracker` was waiting on the other side exactly as it had for a year, the backend event pipeline passed `utm` through cleanly, and Metabase was reading the right columns. But the one invisible link — the jotpsych.com → app.jotpsych.com handoff — was silently removed with the site rebuild, and nothing in code review or test coverage caught it because the old behavior lived in a Wix page that didn't exist in the new repo.

This is a classic vendor-migration failure mode: functionality that was implicit in the old vendor's offering gets lost when you rebuild elsewhere. No tests catch it because it was never your code in the first place.

---

## Fix Applied

### Approach

A ~40-line JS snippet added to `assets/js/main.js` — the shared script that every one of the 34 HTML pages already loads via `<script src="assets/js/main.js"></script>` near the end of `<body>`. The snippet:

1. On page load, reads any persisted params from `sessionStorage['jp_attrib_params']`.
2. Reads the current URL's query params, extracts any known attribution keys, and merges into the persisted object (URL params win).
3. Writes the merged object back to sessionStorage if anything changed.
4. If the stored object has any keys, appends them as a query string to every `<a>` element whose href contains `app.jotpsych.com`.

Keys forwarded: `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, `utm_term`, `utm_id`, `utm_source_platform`, `utm_creative_format`, `utm_marketing_tactic`, `gclid`, `gbraid`, `wbraid`, `fbclid`, `msclkid`.

The click IDs (`gclid`, `fbclid`, etc.) are a small upgrade over the old Wix setup — they enable cross-platform conversion linking and enhanced conversions independent of UTMs, which is useful for Google Ads' offline conversion imports and Meta's CAPI.

### Why one shared snippet instead of per-page edits

Edit scope: 1 file vs. 34. Zero chance of drift between pages. Any new CTA added anywhere in the future is automatically forwarded. No per-page templating system needed (the site is plain HTML). The snippet also handles cross-page persistence: a user who lands on `/` with UTMs, navigates to `/pricing.html` (which has no params in its URL), then clicks "Try for free" still gets the original UTMs attached — because `sessionStorage` survives same-origin navigation.

### Diff

```javascript
// ---- UTM Forwarding to App CTAs ----
// Replaces the old Wix "signup bridge" page that captured marketing-site URL
// params and forwarded them to app.jotpsych.com. Lost in the Mar 2026 cutover;
// ACCOUNT_CREATED events have landed with utm = null since Mar 28. Without
// this, Meta + Google ad UTMs are stripped on click and CpFN attribution
// breaks for the entire ads_engine. See investigation 2026-04-13.
(function forwardAttribParams() {
  var STORAGE_KEY = 'jp_attrib_params';
  var FORWARD_KEYS = [
    'utm_source','utm_medium','utm_campaign','utm_content','utm_term','utm_id',
    'utm_source_platform','utm_creative_format','utm_marketing_tactic',
    'gclid','gbraid','wbraid','fbclid','msclkid'
  ];

  var stored = {};
  try { stored = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '{}'); } catch (e) {}

  var current = new URLSearchParams(window.location.search);
  var changed = false;
  FORWARD_KEYS.forEach(function (k) {
    var v = current.get(k);
    if (v) { stored[k] = v; changed = true; }
  });
  if (changed) {
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(stored)); } catch (e) {}
  }

  var keys = Object.keys(stored);
  if (!keys.length) return;
  var qs = keys.map(function (k) {
    return encodeURIComponent(k) + '=' + encodeURIComponent(stored[k]);
  }).join('&');

  document.querySelectorAll('a[href*="app.jotpsych.com"]').forEach(function (a) {
    var href = a.getAttribute('href');
    var sep = href.indexOf('?') === -1 ? '?' : '&';
    a.setAttribute('href', href + sep + qs);
  });
})();
```

### Safety properties

- **Strictly additive.** No existing UI, styles, behavior, or other code in `main.js` changed. The snippet sits at the top of the existing IIFE, runs once, and returns.
- **No backend or web-app changes.** The web-app's `UTMTracker` and the backend event pipeline were already correct — they just had no data to process. This fix is scoped entirely to the marketing site.
- **Reversible.** One commit, one file. Revert + redeploy = back to the broken state in ~2 minutes.
- **Graceful degradation.** `try`/`catch` around sessionStorage means quota-exceeded, disabled storage, or Safari's ITP restrictions won't throw — CTAs just stop forwarding, which is the current state anyway.
- **No XSS surface.** The snippet only reads/writes its own params and only modifies `href` attributes on anchors it finds by substring match against a fixed host. User-controlled input (URL params) is URL-encoded before insertion.

---

## Deployment and Verification

### Deployed via `/push-to-jotpsych.com`

Commit `6fcbf6c` on master in `smartscribe/jotpsych.com`, deployed to Netlify production at 2026-04-13 ~12:58 PM. Asset-only change (no HTML / sitemap / redirect work), so phases 2–5 of the deploy waterfall were skipped per the skill's edge case handling.

### Playwright verification on live prod (not staging)

**Test 1 — Direct landing with UTMs in URL:**

Navigated to:
```
https://www.jotpsych.com/?utm_source=test_2026_04_13&utm_medium=test&utm_campaign=test_repro&utm_content=playwright_verify&fbclid=test_fbclid_value
```

Result:
- 15 of 15 `app.jotpsych.com` CTAs rewritten with all 5 params
- `sessionStorage['jp_attrib_params']` = `{"utm_source":"test_2026_04_13","utm_medium":"test","utm_campaign":"test_repro","utm_content":"playwright_verify","fbclid":"test_fbclid_value"}`
- Sample href: `https://app.jotpsych.com?utm_source=test_2026_04_13&utm_medium=test&utm_campaign=test_repro&utm_content=playwright_verify&fbclid=test_fbclid_value`

**Test 2 — Cross-page persistence (the harder case):**

Navigated to `https://www.jotpsych.com/pricing.html` — a URL with **no UTMs**. The snippet should still load the persisted params from sessionStorage and rewrite every CTA.

Result:
- 10 of 10 `app.jotpsych.com` CTAs rewritten from sessionStorage
- Every CTA carried the original landing UTMs, proving that cross-page navigation within the marketing site preserves attribution

This is the behavior that matters in production: most users don't click the first CTA they see. They browse to Pricing or Features first, then click. Without sessionStorage persistence, internal navigation would lose the UTMs even if the landing fix worked.

### Remaining verification (deferred to 2026-04-14+)

Once at least 24 hours of live Meta/Google ad traffic has flowed through the fix, run:

```sql
SELECT event_timestamp::date as d,
       COUNT(*) FILTER (WHERE event_data->'utm' IS NOT NULL
                          AND event_data->'utm'::text NOT IN ('null','{}')) as with_utm,
       COUNT(*) as total,
       ROUND(100.0 * COUNT(*) FILTER (WHERE event_data->'utm' IS NOT NULL
                          AND event_data->'utm'::text NOT IN ('null','{}')) / COUNT(*), 1) as pct
FROM public.events_with_user
WHERE event_type='ACCOUNT_CREATED'
  AND event_timestamp >= NOW() - INTERVAL '10 days'
GROUP BY 1 ORDER BY 1 DESC
```

**Expected:** Apr 14 and onward climb back into the historical 20–50% band, matching the pre-Mar-28 baseline.

**If still 0%:** something else is broken — possibilities in order of likelihood: Netlify edge cache serving stale main.js, main.js not actually included on the specific landing pages being hit, CSP on the web-app side rejecting cross-origin sessionStorage (unlikely — same app origin), Safari ITP silently clearing sessionStorage on cross-site navigation (plausible — monitor Safari-specific user segments).

Project memory saved at `memory/project_utm_fix_follow_up.md` with the query and the expected outcome, so next session's first check is to verify recovery.

---

## What This Does Not Fix

- **Historical data recovery.** All signups between Mar 28 and the Apr 13 fix have `event_data.utm = null` and cannot be backfilled. Any attribution analysis for that 16-day window has to be done via secondary signals: Klaviyo's `multiFbc` localStorage key (captures `fbclid`), Google Click Linker's `_gcl_ls` localStorage (captures `gclid`), or reconciliation against Meta Ads' click-through reports and conversion API data. None of those reconstruct Farm vs Scale splits perfectly.
- **Discovery-survey undercount.** 86% of signups in the last 30 days skipped the "how did you hear about us?" survey. That's a separate attribution gap and the UTM fix does not address survey completion rates. Consider a follow-up on why the survey skip rate is so high — it's the single biggest source of unattributed signups after this fix lands.
- **The 2FA SMS-verification break in conversion tracking.** Separate known issue on the Meta pixel and Google tag side from the ads_engine CLAUDE.md's Known Issues #1. Distinct bug, distinct fix.
- **Web-app direct traffic.** Users who go directly to `app.jotpsych.com` (e.g. bookmarks, direct URLs from internal Slack) rather than through jotpsych.com still depend on the web-app's `UTMTracker` to capture any UTMs present on the app's own URL. This fix doesn't touch that path, but it's been working fine and isn't suspected as a source of drop.
- **Cross-domain session continuity in GA4.** GTM container's cross-domain linker is still unverified (see `ga4-csp-fix-2026-04-13.md` open question #1). UTM forwarding solves the ads_engine's CpFN attribution problem; the GTM linker is a separate concern for GA4 session continuity and won't be visible in the `events_with_user` table either way.

---

## Remaining Open Questions

1. **Audit for other signup endpoints.** The snippet's selector is `a[href*="app.jotpsych.com"]`, so any hypothetical links to e.g. `signup.jotpsych.com`, `forms.jotpsych.com`, or `auth.jotpsych.com` would not get forwarded. Quick grep of the new landing site confirms `app.jotpsych.com` is the only signup destination today, but worth re-checking before any new marketing-site change.
2. **Should this logic eventually move to build time?** Right now it's runtime JS. If the site ever moves to Next.js / Astro / another framework, the same logic can be implemented at SSR or build time with slight reliability and SEO improvements. Not worth migrating today.
3. **`META_ADS_ACCESS_TOKEN` expiration.** The token is a user token ("ads_2_nate") with `ads_management` scope, expiring ~2026-06-06. Flag for calendar reminder to regenerate via business.facebook.com → System Users before the window closes, or the ads_engine read + write path breaks.
4. **Documentation of implicit Wix behavior.** The only reason this bug existed is that the Wix signup-bridge page wasn't documented anywhere before the migration. Audit of whatever-else-Wix-used-to-do-silently is probably worth a half-day — what other implicit behavior might still be missing from the new static site? Checkout redirects? Form submissions? Tracking pixels? Worth a spring-cleaning pass.
5. **Survey skip rate.** 86% of signups in the last 30 days skipped the discovery survey entirely. The UTM fix solves ad attribution, but the discovery survey is still the canonical human-reported channel source, and if it's being skipped that often, any analysis depending on `discovery_channel` is itself suspect. Separate investigation.

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| Investigation date | 2026-04-13 |
| Break start date | 2026-03-28 |
| Fix deploy date | 2026-04-13 |
| Break duration | 16 days |
| Marketing site repo (GitHub) | `smartscribe/jotpsych.com` (private) |
| Marketing site local path | `jotpsych_gtm/new_landing_page/` |
| Shared JS file edited | `site/assets/js/main.js` |
| Fix commit SHA | `6fcbf6c` on master |
| Netlify site name | `jotpsych-landing` |
| Production domain | `www.jotpsych.com` |
| App domain | `app.jotpsych.com` |
| Web-app UTM tracker file | `smartscribe-companion-apps/src/web-app/src/services/utm/UTMTracker.ts` |
| Web-app signup form | `smartscribe-companion-apps/src/web-app/src/components/UserInfoForm.tsx:544` |
| Backend repo | `smartscribe/smartscribe-server` |
| Backend signup route (legacy) | `services/ehr_api/lib/modules/users/routes/v1/user_routes.py:889` |
| Backend `ACCOUNT_CREATED` emission (legacy path) | `services/ehr_api/lib/modules/users/services/user_signup_service.py:908` |
| Backend `ACCOUNT_CREATED` emission (v2 createUser path) | `services/ehr_api/lib/modules/users/services/user_signup_service.py:187` |
| `ACCOUNT_CREATED` event model | `lib/jotpsych/product_events/event_data_models.py:38` |
| Analytics DB | SmartScribe Analytics Supabase (Metabase database_id = 2) |
| Events table | `public.events_with_user` |
| Session storage key added | `jp_attrib_params` |
| Slack thread where Jot + Jackson diagnosed | ads thread, 2026-04-13 ~12:45 PM |
| Suspicious commit Jot flagged (ruled out) | `55b6a99e4` (Mar 26, Alfred) — shared Auth0 callback redirect |
| Meta ad account token | `META_ADS_ACCESS_TOKEN` (user token "ads_2_nate", `ads_management` scope, expires ~2026-06-06) |
| Follow-up memory file | `memory/project_utm_fix_follow_up.md` |
