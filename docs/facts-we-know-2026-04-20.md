# Facts We Know For 100% — Meta Ads State, 2026-04-20

**Purpose:** First-principles baseline. Everything we reason from below this line must be verifiable. Anything unverified is flagged.

---

## 1. Account Structure (Verified via API, 2026-04-20 11:04 PT)

| Campaign | Status | Objective | Notes |
|----------|--------|-----------|-------|
| Farm: Testing - Q226 | ACTIVE | OUTCOME_SALES | Created 2026-04-16. 5 ad sets. 24 ads. |
| Scale: Winners - Q226 | PAUSED | OUTCOME_SALES | Created 2026-04-16. Empty — no ad sets, no ads. |
| Farm: Testing - Apr 2026 | PAUSED | OUTCOME_LEADS | Pre-restructure Farm. All ads present but paused. |
| Scale: Winners - Apr 2026 | ACTIVE | OUTCOME_LEADS | Reactivated 2026-04-16 because 6 dynamic-creative ads couldn't be API-migrated. |
| Q126 MLC STATICS TEST LGF | ACTIVE | OUTCOME_LEADS | Not touched by restructure. Burning ~$40/day. |
| Q126 MLC UPMARKET STATICS TEST LGF | ACTIVE | OUTCOME_LEADS | Not touched by restructure. Burning ~$42/day. |
| Q126 000 CREATIVE LIBRARY DO NOT TOUCH | PAUSED | OUTCOME_LEADS | Asset library only, not delivering. |

---

## 2. New Farm Ad Sets (Verified via API)

All 5 ad sets are ACTIVE with optimization_goal=VALUE:

| Ad Set | Daily Budget | Ads | Audiences |
|--------|-------------|-----|-----------|
| Billing & Audit | $80 | 20 | 3 inclusion / 2 exclusion |
| Time Savings | $30 | 1 | 3 inclusion / 2 exclusion |
| EHR Integration | $30 | 1 | 3 inclusion / 2 exclusion |
| UGC / Social Proof | $30 | 2 | 3 inclusion / 2 exclusion |
| AI Progress Concepts | $30 | 0 | 3 inclusion / 2 exclusion |

**AI Progress Concepts has ZERO ads.** Both ads that should be in it (Concept 3, Concept 4) couldn't be API-migrated — they live in old Scale.

**Time Savings and EHR Integration each have 1 ad.** Each should have 3 — the missing 2 in each are dynamic-creative ads stuck in old Scale.

---

## 3. Attributed Conversion Events, Apr 14–20 (Verified via API)

Account-wide, all campaigns combined:

| Event | Count | Value Sent With Event? |
|-------|-------|----------------------|
| SignUpConfirm | 11 | **NO** — pixel fires without `{value: 5, currency: 'USD'}` |
| FirstNote | 6 | **NO** — pixel fires without `{value: 100, currency: 'USD'}` |
| CalendarScheduled | 0 | Page IS configured to fire with `{value: 15}` but no events attributed |
| lead (LGF form) | 13 | N/A (separate funnel) |

**Total spend Apr 14–20: $3,574.18**

---

## 4. Apr 17–20 Performance (Verified via API — 4 days since restructure)

| Campaign | Spend | Impr | Link Clicks | LPVs | FN | CpFN |
|----------|-------|------|-------------|------|-----|------|
| Farm: Testing - Q226 (NEW) | $585 | 20,575 | 292 | 179 (61%) | 0 | — |
| Scale: Winners - Apr 2026 (OLD) | $622 | 14,502 | 171 | 144 (84%) | 1 | $622 |
| Q126 MLC UPMARKET LGF | $169 | 2,800 | 67 | 3 (4%) | 0 | — |
| Q126 MLC STATICS LGF | $165 | 2,746 | 40 | 0 | 0 | — |

**4-day total: $1,541 spent, 1 FirstNote.**

LPV rates on Farm (61%) and Scale (84%) are dramatically better than pre-Apr-14 rates (<10%), suggesting the CSP fix and /audit page deploy improved tracking.

---

## 5. What We Built Last Week (2026-04-16) — Status Check

| Artifact | Built? | Working in Production? |
|----------|--------|------------------------|
| Stripe exclusion audience sync (14,130 emails) | Yes | Yes — attached to all new Farm ad sets |
| Chris's sales prospect list audience (509 contacts) | Yes | Yes — attached to all new Farm ad sets |
| Chris's list 1% Lookalike | Yes | Yes — attached |
| Metabase converter audience (2,000 users) | Yes | Yes — exclusion, attached |
| Converter 1% Lookalike | Yes | Yes — inclusion, attached |
| NPPES PMHNPs + Psychiatrists audience | Partially — script written, ran 20min+ via state-by-state method | **UNVERIFIED** — did the upload complete? Is the audience attached? |
| /scheduled-confirmed page on jotpsych.com | Yes | Yes — pixel fires `CalendarScheduled` with `{value: 15, currency: USD}`, verified via Playwright 2026-04-20 |
| CAPI sender module (`engine/capi/sender.py`) | Yes | **NO** — library exists, one test event sent, but no production code calls it |
| Campaign restructure (Farm Q226 + Scale Q226) | Yes | Yes — new Farm is ACTIVE |
| Audience-attach script | Yes | Ran successfully on new Farm ad sets |
| Match-quality engineering brief (PRD to Jot) | Yes | **NO** — engineering hasn't shipped app-side value params or advanced matching |

---

## 6. What's Broken (Known)

1. **VALUE optimization on new Farm is operating on a null dollar signal.** Meta is trying to maximize value but pixel events don't carry values. This is objectively worse than OFFSITE_CONVERSIONS optimization for count because Meta spent $585 chasing phantom dollars.

2. **Match quality is 4.0/10 on FirstNote.** Meta can't reliably attribute conversions to ad clicks. Every optimization decision Meta makes is built on weak matching.

3. **CalendarScheduled has 0 attributed events over 7 days despite the page being wired correctly.** Either genuinely no bookings (plausible at low volume), or Calendly redirect isn't configured. **Requires Nate verification.**

4. **Old Scale is decaying.** $622 CpFN vs $263 pre-restructure on same ads. Dynamic creative fatigue.

5. **LGF campaigns are burning $80+/day with near-zero signal.** Not in any scope. Not being worked on.

6. **6 dynamic-creative ads are orphaned in old Scale.** AI for Progress Notes, Florence Static, PDF to Template, AI Progress Concept 2, Concepts 3 and 4. API can't migrate `asset_feed_spec` ads to a different objective.

---

## 7. Things Nate Must Verify In-Account (Before We Plan Anything)

These I cannot verify via API alone or by reasoning. Nate must open Ads Manager / Calendly and confirm:

### Meta Ads Manager

1. **Open Farm: Testing - Q226 campaign. Confirm the campaign objective shown in the UI is "Sales" (OUTCOME_SALES).** If it says anything else, the API state and UI state are out of sync.

2. **Click into the "Billing & Audit" ad set. Go to the Conversion tab. Confirm:** 
   - Performance goal says something like "Maximize value of conversions" (not "number of conversions")
   - Conversion event is "FirstNote" on WebApp Actions dataset
   - Value rules are either Enabled OR the dataset is flagged "value sent with events: yes"

3. **On the same ad set, Audience tab. Confirm the list of Custom Audiences includes:**
   - Sales Prospect List - BH Clinics
   - Lookalike - BH Clinic Prospects 1%
   - Lookalike - First Note Converters 1%
   - Exclusions: Stripe Customers - Auto Exclusion, Converters - First Note Completers
   - (Confirm whether "NPPES PMHNPs + Psychiatrists" is listed — tells us if NPPES sync completed)

4. **Open each of the other 4 ad sets. Confirm they have the same audiences.** Especially confirm AI Progress Concepts has audiences attached despite having 0 ads.

5. **Check delivery status of the 22 ads showing "ACTIVE" in Farm Q226.** Are any flagged as "Not Delivering" or "In Review" after 4 days? Ads that are ACTIVE but not delivering burn budget at $0 effective rate.

6. **Check the 2 ads flagged WITH_ISSUES (deprecated 191x100 crop):** "AN: Your Notes Are Perfect - Insurance Doesnt Care - Copy" and "AJ: Cigna Has Rules. JotPsych Knows Them - Copy". Confirm whether they're actually delivering or stuck in review.

7. **Go to Events Manager → WebApp Actions pixel (ID 1625233994894344) → Test Events tab.** Wait 60 seconds. Book a test Calendly meeting from your personal account. Confirm you see a `CalendarScheduled` event appear with `value: 15, currency: USD` in the test events stream.

8. **Events Manager → FirstNote event → Event Quality tab.** Confirm what the current match quality score is and what parameters Meta says would improve it most.

9. **Events Manager → SignUpConfirm event → click on a recent fired event → look at the parameters payload.** Does it contain `value`? Does it contain `currency`? (This tells us definitively whether the app-side value params are shipped or not.)

### Calendly

10. **Open calendly.com/event_types. Click into "Is JotPsych Right for You and Your Clinic".** In Booking page options → After booking, confirm the setting is:
    - "Redirect to an external site" (NOT "Display confirmation page")
    - URL: `https://www.jotpsych.com/scheduled-confirmed`
    - "Pass event details to your redirected page" is CHECKED

11. **Open "JotStart: An Introduction" event type. Same check — confirm the redirect is configured identically.**

### Budget & Billing

12. **Meta Ads Manager → Billing. Confirm:**
    - What's the daily account-level spend cap (if any)?
    - How much has been spent today (Apr 20) so far?
    - Is there any alert/issue on the billing section?

13. **Look at Ads Manager → Account Overview for the last 7 days.** Confirm:
    - Total spend figure matches what we see via API ($3,574)
    - No fraud flags, policy violations, or account warnings

### Context

14. **Who created the LGF campaigns (Q126 MLC STATICS / MLC UPMARKET)?** Matt or Adam? Are they testing something independent of our workstream, and should we leave them alone? Or are they orphaned and we should pause them?

15. **Can Nate / anyone on the team book a Calendly meeting from their phone right now as an end-to-end test** — click a LinkedIn ad or type the URL, go through the Calendly flow, land on /scheduled-confirmed, and then check Events Manager to see if the event attributed?

---

## 8. Unverified Claims That Must Be Resolved Before Planning

- "The CSP fix deployed on Apr 14 is working on mobile" — we haven't tested mobile specifically
- "Calendly redirects are configured" — Nate said done 2026-04-16, no end-to-end test exists
- "NPPES audience upload completed" — the script was started but final status not confirmed
- "The 24 ads in new Farm are delivering (not in review/rejected)" — API shows ACTIVE but that's not the same as delivering

---

## 9. Questions We Cannot Answer Without Verification

- Is the 0 CalendarScheduled / 0 FirstNote on new Farm because of VALUE-opt misfiring, Calendly config gap, low volume, or attribution failure? Answer depends on verifications 7, 10, 11, 15.
- Should we kill the LGF campaigns? Answer depends on verification 14.
- Should we manually duplicate the 6 orphaned dynamic-creative ads or kill them? Answer depends on recent performance of those specific ads (verification 5) and whether Nate wants them.
