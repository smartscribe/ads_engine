---
title: Google Ads API Setup
date: 2026-05-05
status: in_progress
owner: Nate (browser steps) + Claude (config + scripts)
---

# Google Ads API Setup

## Why

Ads engine has Google Ads scaffolding (`engine/deployment/deployer.py`, `engine/tracking/tracker.py`) but no live API. Every Google Ads decision since the Apr 6 Meta restructure has been made blind: the only data is what Jenna (Google rep) sends in audit decks and what Metabase shows via UTM. Two weeks of unactioned recommendations are sitting in inbox (4/29 audit, 4/20 reschedule, three disapproved PMax asset groups, $1.8K billing failure resolved 5/4 but worth verifying via API).

The orientation briefing Nate originally asked for is reading tea leaves without API access. With API access, every future briefing pulls clean account-level data: spend by campaign, conversions by event, search-term reports, asset-disapproval reasons, GAQL-driven analysis at the level of the existing Meta tracker.

## Account Facts (verified)

- **Customer ID:** 944-822-1568 (no dashes: `9448221568`)
- **Account owner:** nate@jotpsych.com (Administrative since at least 2023-12-10)
- **Other admins on account:** nate@smartscribe.health, chris@smartscribe.health (Chris Hume), aharrison@smartscribe.health (Adam Harrison, transitioning out), Matt Lovett (read-only, added 2026-02-17)
- **MCC status:** None. CID 944-822-1568 is standalone. Adam was a regular admin user, not a manager-link relationship.
- **Google account team:** Jenna Stafford (Account Strategist, Lead Generation), Morgan Pacheco (CC), Hyun Kim (AGT), all reachable at @google.com

## Required Artifacts

| Artifact | Source | Long pole? |
|---|---|---|
| Developer token | MCC API Center (Basic tier) | **Yes — 1-3 business days approval** |
| OAuth2 Client ID + Secret | GCP Console (Desktop client) | No, ~5 min |
| Refresh token | OAuth flow (one consent click) | No, ~2 min |
| Customer ID | Already known: 9448221568 | Done |
| Login Customer ID | New MCC's CID (TBD after MCC creation) | Same step as MCC creation |

## Sequence

### Today (parallelizable)

**Nate's browser sequence (single session, signed in as nate@jotpsych.com):**

1. **Verify no MCC** — visit https://ads.google.com/aw/accounts/manager/managed
   - Confirm no manager accounts listed
   - If any exist, capture their CIDs and update this doc
2. **Create JotPsych Manager MCC** — visit https://ads.google.com/aw/signup/manager
   - Name: "JotPsych Manager"
   - Country: United States
   - Currency: USD
   - Timezone: America/New_York
3. **Link CID 944-822-1568 under MCC**
   - From MCC: Tools → Setup → Sub-account settings → "+" → "Link existing account" → enter `944-822-1568` → request link
   - From CID 944-822-1568: Tools → Setup → Access and security → Managers → accept the pending link request
4. **Apply for developer token** — from the new MCC: Tools → Setup → API Center
   - Tier: Basic Access (15K ops/day)
   - Use-case narrative: see Appendix A in this doc (Claude drafts; Nate pastes)
   - Submit
5. **`gcloud auth login`** in terminal (signed in as nate@jotpsych.com) — refreshes the stale token

**Claude's parallel work:**

6. Identify GCP project (likely `ads-engin` based on existing service account name) or create `jotpsych-ads-engine`
7. Enable Google Ads API on that project
8. Configure OAuth consent screen (Internal user type, scope: `https://www.googleapis.com/auth/adwords`)
9. Create Desktop OAuth2 client → save `credentials.json` to `~/.claude/integrations/google_ads_oauth.json`
10. Write `scripts/google_ads_oauth.py` — uses `google-ads` SDK's installed-app flow to mint the refresh token
11. Write `scripts/test_google_ads.py` — `customer.list` smoke test
12. Add `google-ads>=24.0.0` to `requirements.txt`
13. Wire env vars into `~/.claude/.env` (placeholders) and `config/settings.py`:
    - `GOOGLE_ADS_DEVELOPER_TOKEN`
    - `GOOGLE_ADS_CLIENT_ID`
    - `GOOGLE_ADS_CLIENT_SECRET`
    - `GOOGLE_ADS_REFRESH_TOKEN`
    - `GOOGLE_ADS_CUSTOMER_ID=9448221568`
    - `GOOGLE_ADS_LOGIN_CUSTOMER_ID=<MCC CID, set after step 2>`
14. Run `python3 scripts/google_ads_oauth.py` — Nate clicks Allow, refresh token captured to env
15. Confirm `python3 scripts/test_google_ads.py` fails with "developer token required" (expected) — pipe is wired

### T+1-3 days

16. Token approval email arrives → Nate pastes into `~/.claude/.env`
17. Run `python3 scripts/test_google_ads.py` → expect: customer 9448221568 visible
18. Implement `GoogleTracker.pull_ad_metrics()` with GAQL:
    - 90-day window: campaign, ad_group, ad, spend, impressions, clicks, conversions (FirstNote, SignUp), CpA per conversion, search_term_view
19. First analysis: 90-day spend/conversions/CpFN by campaign + branded vs non-brand split + search-term review
20. Use that data to power the orientation briefing Nate originally asked for

### Later (separate workstreams, not gating)

- `GoogleDeployer.create_ad()` — write access to deploy ads programmatically (only when generation pipeline is ready)
- Enhanced Conversions for Leads via HubSpot (Jenna's recurring ask) — separate plan
- Demand Gen campaign launch (Jenna's recurring ask) — separate plan
- Fix 3 disapproved PMax asset groups (likely tied to website redirect / CSP fallout) — separate plan

## Risk + Notes

- **Developer token approval can be denied or delayed** if the use-case narrative is vague. Appendix A drafts a narrative grounded in our actual stack (analysis + read-only first, write later) to maximize first-pass approval.
- **Sub-account link from MCC requires the CID's admin to accept.** Nate is the admin on both, so this is two clicks in two tabs.
- **OAuth refresh token doesn't expire** unless revoked or unused for 6 months. Single-use generation.
- **Login Customer ID** must be set in API headers when calling on behalf of a sub-account. The MCC's CID acts as the "logged-in" account; the customer ID is the target sub-account (944-822-1568).
- **Account suspensions** have happened before (2024-05-29 thread). API access is independent of UI access — if account suspended, API still requires resolution at account level first.
- **GA4 service account `ads-engine-ga-reader@ads-engin.iam.gserviceaccount.com` is unrelated** to Google Ads API. Different service, different OAuth path. We're adding to the same GCP project for tidiness, not reusing the SA.

## Appendix A: Developer Token Application Narrative (draft)

> JotPsych is a SaaS clinical documentation platform serving behavioral health clinicians. We operate Google Ads campaigns (search + PMax + branded) at ~$15-20K/month spend, currently advised by Jenna Stafford on the Google Engage / Lead Generation team.
>
> We are building an internal ads operations harness ("ads_engine") that integrates Meta Ads and Google Ads performance data to drive a Bayesian creative-decision pipeline (kill/scale/hold per ad based on cost-per-first-note). Production code lives in a private repo.
>
> **Initial use cases (read-only):**
> 1. Daily pull of campaign, ad_group, and ad-level performance (impressions, clicks, conversions, cost) via GAQL into our analytics warehouse for cross-channel attribution analysis
> 2. Search-term reporting for ongoing keyword-list hygiene
> 3. Asset disapproval monitoring for fast remediation on PMax asset groups
>
> **Subsequent use cases (write):**
> 4. Programmatic creation of responsive search ads from our internal creative-generation pipeline (variants reviewed by humans before deployment)
> 5. Bid adjustment automation tied to our internal Bayesian decision engine
> 6. Conversion upload (Enhanced Conversions for Leads via HubSpot integration)
>
> All operations target a single Google Ads account (CID 944-822-1568, our own JotPsych account) under our own MCC. We are not a third-party tool builder. Estimated daily ops well below the 15,000 ceiling.

## Appendix B: Env var contract

```bash
# ~/.claude/.env additions (placeholders today, real values when token arrives)
GOOGLE_ADS_DEVELOPER_TOKEN=          # paste from approval email
GOOGLE_ADS_CLIENT_ID=                # from OAuth Desktop client
GOOGLE_ADS_CLIENT_SECRET=            # from OAuth Desktop client
GOOGLE_ADS_REFRESH_TOKEN=            # from scripts/google_ads_oauth.py
GOOGLE_ADS_CUSTOMER_ID=9448221568    # CID 944-822-1568, dashes stripped
GOOGLE_ADS_LOGIN_CUSTOMER_ID=        # MCC's CID, set after step 2
```

`config/settings.py` reads these via `os.environ["KEY"]` per global secret-handling rule (fail loud if missing, no fallbacks).
