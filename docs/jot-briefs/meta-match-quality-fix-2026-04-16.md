---
title: "Fix Meta Pixel Match Quality — 4/10 → 8/10"
date: 2026-04-16
author: Nate + Claude
memory_target: Mem0
scope: Engineering PRD — pass user data with Meta pixel events and CAPI to fix match quality
confidence: high
supersedes: none
sources:
  - screenshot: Meta Events Manager — FirstNote event quality tab (2026-04-16)
  - docs: https://developers.facebook.com/docs/marketing-api/conversions-api/parameters
  - code: ads_engine/engine/capi/sender.py
---

# Fix Meta Pixel Match Quality — 4/10 → 8/10

**Date:** 2026-04-16
**Memory target:** Mem0
**Scope:** Engineering changes to SmartScribe web app to pass user data with Meta conversion events
**Status:** Canonical as of 2026-04-16. Blocking effective ad optimization.

---

## TL;DR

Meta's match quality for our conversion events is 4.0/10. Meta needs at least 6.0/10 to effectively optimize ad delivery — below that, the algorithm can't reliably connect conversions back to the people who saw ads, so it can't learn who to target. We're spending $300/day on ads where the algorithm is half-blind. The fix is passing user data (email, IP, user agent, click ID, browser ID) with every conversion event, both client-side (advanced matching) and server-side (Conversions API). This is an engineering change in the SmartScribe web app, not the ads engine.

---

## The Problem

When a user completes a FirstNote, SignUpConfirm, or other conversion event, the Meta pixel fires — but it sends almost no identifying data. Meta receives the event but can't match it to the person who clicked the ad. Result:

- **Match quality: 4.0/10** (Meta recommends 6.0+, top advertisers hit 8-9)
- Meta's optimization algorithm can't learn which ad clicks lead to conversions
- Dollar-weighted optimization (FirstNote=$100, CalendarScheduled=$15, SignUpConfirm=$5) is neutered if Meta can't attribute the value back to the right user
- We're paying for signal that doesn't reach the algorithm

### What Meta Says Would Help

From the FirstNote event quality panel (screenshot 2026-04-16):

| Parameter | Potential Improvement | Hash Required | Currently Sent |
|-----------|----------------------|---------------|----------------|
| IP Address (`client_ip_address`) | **42%** | No | No |
| User Agent (`client_user_agent`) | **42%** | No | No |
| Click ID (`fbc`) | **42%** | No | No |
| Phone number (`ph`) | 32% | Yes (SHA256) | No |
| Browser ID (`fbp`) | 32% | No | No |
| External ID (`external_id`) | 32% | Recommended | No |
| ZIP code (`zp`) | 20% | Yes (SHA256) | No |
| City (`ct`) | 20% | Yes (SHA256) | No |
| State (`st`) | 20% | Yes (SHA256) | No |

The top three — IP, User Agent, Click ID — each offer 42% improvement and require no hashing. These are the highest-leverage, lowest-effort fixes.

---

## What Jot Should Commit to Memory

1. **Meta match quality is 4.0/10 as of 2026-04-16 — this is the single biggest bottleneck in ad performance.** More important than creative, audience, or budget. If Meta can't match conversions to ad viewers, none of the optimization works.

2. **Two parallel fixes are needed: client-side advanced matching AND server-side CAPI.** Client-side catches browser events in real-time. CAPI catches events even when ad blockers kill the pixel, and allows passing server-only data (IP, user agent). Both firing the same event with the same `event_id` enables Meta's deduplication — it keeps the best-matched version.

3. **The SmartScribe web app must pass user data with `fbq('init')` and with every `fbq('track')` call.** This is called "Advanced Matching" in Meta's docs. When a user is logged in (which they are for FirstNote and SignUpConfirm), the app knows their email, name, and phone — hash and pass them.

4. **The CAPI sender module already exists at `ads_engine/engine/capi/sender.py`.** It handles hashing, formatting, and posting to Meta's server-side endpoint. The app backend needs to call it (or replicate its logic) when FirstNote and SignUpConfirm events fire server-side.

5. **The `fbc` (click ID) and `fbp` (browser ID) cookies are the easiest wins.** `_fbc` is set by Meta when someone clicks an ad. `_fbp` is set by the pixel on first visit. Both are first-party cookies readable by the app. Passing them with events is the single fastest path to higher match quality.

---

## Implementation Plan

### Fix 1: Client-Side Advanced Matching (Frontend)

**Where:** SmartScribe web app frontend, wherever the Meta pixel initializes.

**Current state:** The pixel initializes with just the pixel ID:
```javascript
fbq('init', '1625233994894344');
```

**Target state:** Initialize with user data when logged in:
```javascript
// On pages where user is authenticated
fbq('init', '1625233994894344', {
  em: 'sha256_hashed_email',        // user's email, lowercased, SHA256
  fn: 'sha256_hashed_first_name',   // first name, lowercased, SHA256
  ln: 'sha256_hashed_last_name',    // last name, lowercased, SHA256
  ph: 'sha256_hashed_phone',        // phone (digits only, with country code), SHA256
  external_id: 'user_uuid',         // your internal user ID (hash recommended)
});
```

**Also pass data with each track call:**
```javascript
fbq('track', 'FirstNote', {
  value: 100.00,
  currency: 'USD',
}, {
  eventID: 'fn_<unique_event_uuid>'  // for CAPI deduplication
});
```

**Hashing rules (Meta spec):**
- Email: lowercase, trim whitespace, SHA256
- Phone: digits only, include country code (e.g., `15551234567`), SHA256
- First/last name: lowercase, trim, SHA256
- External ID: SHA256 recommended but not required
- `fbc`, `fbp`: read from cookies `_fbc` and `_fbp`, pass as-is (no hash)

**Reading fbc/fbp from cookies:**
```javascript
function getCookie(name) {
  var match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return match ? match[2] : null;
}

var fbp = getCookie('_fbp');
var fbc = getCookie('_fbc');

// Pass to init if available
fbq('init', '1625233994894344', {
  em: hashedEmail,
  fbp: fbp,
  fbc: fbc,
  external_id: hashedUserId,
});
```

### Fix 2: Server-Side CAPI (Backend)

**Where:** SmartScribe backend, at the point where FirstNote and SignUpConfirm events are recorded.

**What to send:** When the app records a FirstNote completion or signup confirmation, also POST to Meta's Conversions API:

```
POST https://graph.facebook.com/v21.0/1625233994894344/events
```

**Payload structure:**
```json
{
  "data": [{
    "event_name": "FirstNote",
    "event_time": 1713200000,
    "event_source_url": "https://app.jotpsych.com/notes",
    "action_source": "website",
    "event_id": "fn_<same_uuid_as_client_side>",
    "user_data": {
      "em": ["<sha256_email>"],
      "ph": ["<sha256_phone>"],
      "fn": ["<sha256_first_name>"],
      "ln": ["<sha256_last_name>"],
      "external_id": ["<sha256_user_id>"],
      "client_ip_address": "<from_request_headers>",
      "client_user_agent": "<from_request_headers>",
      "fbc": "<from_cookie_or_url_param>",
      "fbp": "<from_cookie>",
      "zp": ["<sha256_zip>"],
      "st": ["<sha256_state>"],
      "ct": ["<sha256_city>"]
    },
    "custom_data": {
      "value": 100.00,
      "currency": "USD"
    }
  }],
  "access_token": "<META_ADS_ACCESS_TOKEN>"
}
```

**Critical: Event deduplication.** Both the client-side pixel and CAPI will fire the same event. Meta deduplicates using `event_id` + `event_name`. The client-side `fbq('track', 'FirstNote', ..., {eventID: 'fn_xxx'})` and the CAPI payload `event_id: 'fn_xxx'` must use the **same UUID**. This means:

1. Frontend generates a UUID when the event fires
2. Frontend sends UUID to backend (e.g., in the API call that records the note)
3. Backend includes that UUID in the CAPI `event_id` field
4. Meta keeps whichever copy has better match quality, discards the other

### Fix 3: Dollar Values on All Events

**Where:** Both client-side and CAPI.

With value optimization now enabled on all ad sets, every conversion event should include:

| Event | `value` | `currency` |
|-------|---------|------------|
| FirstNote | 100.00 | USD |
| CalendarScheduled | 15.00 | USD |
| SignUpConfirm | 5.00 | USD |

The client-side pixel calls should include `{value: 100.00, currency: 'USD'}` in the custom data. The CAPI calls already support this via the `custom_data` field.

---

## How to Apply

| Situation | Response |
|---|---|
| Engineering asks what to prioritize | Fix 1 (advanced matching init) + reading fbc/fbp cookies. Highest impact, lowest effort. |
| Backend doesn't have user's phone/address | Send what you have. Email + IP + user agent + fbc + fbp alone should push to 7+/10. Don't block on optional fields. |
| Concern about PII/HIPAA | All PII is SHA256-hashed before transmission. Meta never sees raw email/phone. IP address and user agent are standard web request data, not PHI. The hashing is one-way — Meta matches hashed values against their own hashed user database. |
| How to test | Meta Events Manager → Test Events tab. Fire a conversion with the new params, check that match quality improves on the test event. |
| Which events need this | FirstNote (primary), SignUpConfirm (secondary), CalendarScheduled (already handled via confirmation page pixel). |

---

## What This Brief Does NOT Cover

- Creative strategy or ad copy changes
- Audience targeting configuration (handled separately, already deployed)
- Google Analytics / GA4 integration
- The CalendarScheduled event (already fires with value from jotpsych.com/scheduled-confirmed — match quality there depends on the user having fbc/fbp cookies from a prior Meta ad click)

---

## Priority and Sequencing

1. **P0 — Read fbc/fbp cookies and pass with fbq('init').** 5 lines of JS. Unlocks 42% + 32% match quality improvement.
2. **P0 — Pass hashed email with fbq('init') on authenticated pages.** User is logged in, email is known. Another 32%+ improvement.
3. **P1 — Add value params to client-side fbq('track') calls.** Ensures dollar-weighted optimization works end-to-end.
4. **P1 — Implement CAPI for FirstNote and SignUpConfirm.** Server-side redundancy, catches ad-blocked browsers, allows passing IP + user agent.
5. **P2 — Add event_id deduplication between pixel and CAPI.** Required once CAPI is live to prevent double-counting.
6. **P2 — Pass phone, zip, city, state if available in user profile.** Incremental improvement.

---

## Canonical Identifiers

| Thing | Value |
|---|---|
| Meta Pixel ID (canonical) | `1625233994894344` |
| CAPI Endpoint | `POST https://graph.facebook.com/v21.0/1625233994894344/events` |
| Access Token Env Var | `META_ADS_ACCESS_TOKEN` |
| CAPI Sender Module | `ads_engine/engine/capi/sender.py` |
| fbc Cookie Name | `_fbc` |
| fbp Cookie Name | `_fbp` |
| Current Match Quality | 4.0/10 (FirstNote, as of 2026-04-16) |
| Target Match Quality | 8.0/10 |
| Meta Docs — CAPI Parameters | developers.facebook.com/docs/marketing-api/conversions-api/parameters |
| Meta Docs — Advanced Matching | developers.facebook.com/docs/meta-pixel/advanced/advanced-matching |

---

## Sources

[^1]: Meta Events Manager screenshot, FirstNote event quality tab, 2026-04-16. Match quality 4.0/10, parameter improvement estimates from Meta's own recommendations.
[^2]: Meta Conversions API parameter documentation: developers.facebook.com/docs/marketing-api/conversions-api/parameters
