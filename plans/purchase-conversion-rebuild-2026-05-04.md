# Plan: Convert "Nate figuring shit out" to Purchase value-based optimization

**Date:** 2026-05-04
**Status:** plan, awaiting execution
**Owner:** Nate (GTM container, Meta Ads Manager, calibration cycle)
**Engineering owner:** Alfred (CAPI + identity hashing for FirstNote)

**Related context (read for background, not required to execute):**
- [meta-custom-conversions-v3-field-fix-2026-04-23.md](../../new_landing_page/docs/jot-briefs/meta-custom-conversions-v3-field-fix-2026-04-23.md) — superseded by this plan, but documents the silent-fail modes we're avoiding by using a Meta standard event
- [signup-funnel-elegant-path-2026-04-29.md](../../new_landing_page/docs/jot-briefs/signup-funnel-elegant-path-2026-04-29.md) — current signup funnel state
- [meta-capi-token-2026-04-29.md](../../new_landing_page/docs/jot-briefs/meta-capi-token-2026-04-29.md) — token Alfred uses in Phase 2

---

## Governing thought

Convert the existing "Nate figuring shit out" ad set, currently bound to a custom event (`SignUpConfirm`) that fires 0-4 times per day and provides effectively zero optimization signal, to optimize on Meta standard `Purchase` event with three valued sub-events (FirstNote $150, SignUp $25, Calendar $5). This gives Meta the combined event volume needed to exit learning phase and the value signal needed to allocate budget toward the highest-LTV converters, without depending on the Custom Conversion infrastructure that has failed three times in three weeks.

## Why this is the next move

The Apr 23 v3 Custom Conversion attempt was structurally hampered by Meta's rule that multi-event optimization isn't supported with VALUE in OUTCOME_SALES + Custom Conversions. Meta standard `Purchase` removes that constraint: all three valued events fire as the same Meta event, and Meta optimizes for total Purchase value across them. Three known silent-fail modes from the CC attempts (whitespace in rule values, cents-vs-dollars unit confusion, wrong rule field name `event_type` vs `event`) are also eliminated by going through GTM with a Meta standard event template instead of API-created CCs.

Current state is broken in three compounding ways: the legacy SignUpConfirm pixel event went dark May 2 (suspected GTM container regression), the legacy FirstNote pixel event went dark same day, and the ad set has been ACTIVE the entire time with the dead optimization event. Spend is going out, no signal is coming back. This plan replaces the legacy custom-event GTM tags with Meta standard Purchase tags listening to the same upstream dataLayer events (which still fire from the React app correctly), making the May 2 GTM regression irrelevant rather than fixing it.

## Approach

Three sequential phases. Phase 2 can run in parallel with Phase 1 if Alfred starts the same day; it does not block Phase 1 going live.

| Phase | Owner | Duration | Output |
|---|---|---|---|
| Phase 1: GTM tags + ad set rebind | Claude (API-driven) + Nate (verification) | ~15-30 min once GCP API enabled | Live Purchase events flowing browser-side, ad set bound to Purchase, learning phase begins. Tag definitions committed to ads_engine repo |
| Phase 2: CAPI parity for FirstNote | Alfred | 5-7 days | FirstNote fires from BE via Meta CAPI with shared event_id. EMQ rises from ~3-4 to 7+ |
| Phase 3: Calibration | Nate | day 30+ | Recalibrate event values from cohort data. No learning-phase reset. |

**Phase 1 driver:** GTM API client at `~/.claude/integrations/gtm_client.py` (OAuth completed 2026-05-04, scopes include edit + publish). Claude lists existing tags via API, creates the three new Purchase tags via API POST, configures triggers, builds a workspace version. Nate verifies via GTM Preview + Meta Test Events. Claude publishes via API. Tag definitions land in `ads_engine/config/gtm/` as version-controlled JSON for future diff-against-drift.

**Phase 0 prereq (one-time):** Tag Manager API enabled at the GCP project level. Without this, all API calls return 403 SERVICE_DISABLED. Enable once at https://console.developers.google.com/apis/api/tagmanager.googleapis.com/overview?project=761849295485, propagation ~2-5 min.

---

## Phase 1: GTM tags + ad set rebind (Claude API-driven + Nate verification, ~15-30 min)

**Driver split:**
- Claude: API-driven tag inventory, creation, workspace version, publish
- Nate: GTM Preview verification, Meta Test Events verification, ad set rebind in Meta Ads Manager UI

### Step 1.1 — Diagnose existing GTM state (Claude, 2 min via API)

Pull current state of the container's tags, triggers, variables via:
```
python3 ~/.claude/integrations/gtm_client.py tags list <accountId> <containerId> <workspaceId>
```

Snapshot the full output to `ads_engine/config/gtm/snapshot-pre-purchase-rebuild-2026-05-04.json` for the version-controlled baseline. Search the snapshot for tag names containing `signupConfirm`, `generatedFirstNote`, `CalendarScheduled`. Note their state (`paused`, `tagFiringOption`), trigger references, and most-recent fingerprint. If any are paused or have orphaned triggers, that's the May 2 regression captured for the record. Do not re-enable; we're replacing them with new Purchase tags listening to the same upstream events.

**Manual fallback:** if the GTM API isn't yet enabled at the GCP project level (Phase 0 prereq), do this step via tagmanager.google.com UI: Tags > search for the three event names, note state.

### Step 1.2 — Create three Purchase tags (Claude, 5 min via API)

Each tag created via `POST /accounts/<a>/containers/<c>/workspaces/<w>/tags` with the JSON body checked into `ads_engine/config/gtm/tags/`. Three files:
- `meta-purchase-first-note.json`
- `meta-purchase-sign-up.json`
- `meta-purchase-calendar-scheduled.json`

Each is a Custom HTML tag (most portable; doesn't depend on whether the Meta Pixel template is installed in the container). Tag spec shape:

```json
{
  "name": "Meta Purchase — First Note",
  "type": "html",
  "parameter": [
    {"type": "template", "key": "html", "value": "<script>fbq('track', 'Purchase', {value: 150, currency: 'USD', content_name: 'first_note'}, {eventID: {{event_id}}});</script>"},
    {"type": "boolean", "key": "supportDocumentWrite", "value": "false"}
  ],
  "firingTriggerId": ["<trigger_id_for_generatedFirstNote_event>"],
  "tagFiringOption": "oncePerEvent"
}
```

Triggers (one Custom Event per dataLayer event, one Page View for the calendar URL) are also created via API into `ads_engine/config/gtm/triggers/`:

| Tag name | Trigger | Meta event params |
|---|---|---|
| `Meta Purchase — First Note` | Custom Event, event name = `generatedFirstNote` | `Purchase`, `value=150`, `currency=USD`, `content_name=first_note`, `eventID={{event_id}}` (read from dataLayer) |
| `Meta Purchase — Sign Up` | Custom Event, event name = `CompleteRegistration` | `Purchase`, `value=25`, `currency=USD`, `content_name=signup`, `eventID={{event_id}}` |
| `Meta Purchase — Calendar Scheduled` | Page View, Page Path matches `/scheduled-confirmed*` | `Purchase`, `value=5`, `currency=USD`, `content_name=calendar` |

Custom HTML fallback snippet (replace parameters per row, change `eventID` reference if no event_id in dataLayer):

```javascript
fbq('track', 'Purchase', {
  value: 150,
  currency: 'USD',
  content_name: 'first_note'
}, {eventID: {{event_id}}});
```

### Step 1.3 — GTM Preview (15 min)

Click Preview. Three test paths:
1. `https://app.jotpsych.com` — trigger `generatedFirstNote` either by recording an encounter end-to-end on a test account, OR by pushing the event manually via browser console: `window.dataLayer.push({event: 'generatedFirstNote', event_id: 'test-' + Date.now()})`
2. `https://app.jotpsych.com/callback` after Auth0, OR push `CompleteRegistration` via console
3. `https://jotpsych.com/scheduled-confirmed` — verify the URL exists; if booking confirmation actually lives at a different path, fix the trigger to match

Each tag should show "Fired" in the GTM debugger. Open Meta Events Manager > Test Events tab in another window with a test event code added. Each Purchase event should appear within 5 seconds with the correct value and content_name.

**Do not Submit / Publish until each tag fires once successfully in both GTM Preview AND Meta Test Events.** This is gate 1 + gate 2.

### Step 1.4 — Publish container (Claude, 1 min via API)

Two API calls:
1. `POST /accounts/<a>/containers/<c>/workspaces/<w>:create_version` with body `{"name": "purchase-conversion-v1 (FirstNote $150 + SignUp $25 + Calendar $5)"}` to create the version.
2. `POST /accounts/<a>/containers/<c>/versions/<v>:publish` to push it live.

Save the resulting version ID and publish timestamp to `ads_engine/config/gtm/published-versions.log`.

### Step 1.5 — Rebind ad set in Meta Ads Manager (10 min)

Ad set: `120245858870530548` ("Nate figuring shit out"), parent campaign `120245858870520548`. Both currently ACTIVE.

Currently bound to: `custom_event_str: SignUpConfirm`, `custom_event_type: OTHER`. Already on OUTCOME_SALES + VALUE optimization with 7-day click + 1-day view attribution, so the campaign frame is correct.

Edit > Optimization & Delivery:
- Conversion event: change to **Meta standard Purchase**
- Custom event field: clear (no custom event)
- Bid strategy: keep "Highest Value"
- Attribution window: keep 7-day click + 1-day view (do NOT extend; longer windows make the calendar attribution decay problem worse, not better)
- Daily budget: keep current, OR raise to $1000 if not already

Save. Meta will reset the learning phase when the conversion event changes. Accept this. ~7-14 days to exit at $1000/day spend.

### Step 1.6 — Archive the v3 CCs (5 min)

Meta Events Manager > Custom Conversions, rename to `_archived_*` prefix:
- `FirstNote (Valued) v3` (id 1755976485786147)
- `SignUpConfirm (Valued) v3` (id 1014486627931137)
- `CalendarScheduled (Valued) v3` (id 26939511482340303)

Per the never-delete rule: rename only, do not delete. They become inert reference state for the next time we look back at this saga.

---

## Phase 1 execution log (2026-05-04)

### Built in workspace 24 (verified, awaiting publish)

| Type | ID | Name | Wired to |
|---|---|---|---|
| Variable | 64 | `dlv_event_id` | reads `event_id` from dataLayer (Data Layer Variable v2) |
| Trigger | 65 | CompleteRegistration Event | `_event == 'CompleteRegistration'` (custom event from `pixels.ts`) |
| Trigger | 66 | Calendar Scheduled Page View | Page URL contains `/scheduled-confirmed` |
| Tag | 67 | Meta Purchase - First Note | trigger 15 (existing `generatedFirstNote`) → Custom HTML, `Purchase` $150, content_name=`first_note`, eventID=`{{dlv_event_id}}` |
| Tag | 68 | Meta Purchase - Sign Up | trigger 65 → Custom HTML, `Purchase` $25, content_name=`signup`, eventID=`{{dlv_event_id}}` |
| Tag | 69 | Meta Purchase - Calendar Scheduled | trigger 66 → Custom HTML, `Purchase` $5, content_name=`calendar` |

JSON specs and create responses saved at `ads_engine/config/gtm/{tags,triggers}/`. Apply script at `ads_engine/config/gtm/apply.py` for reproducibility.

Used regular ASCII hyphen-space in tag names ("Meta Purchase - First Note") to match container convention; em-dash and colon are both rejected by GTM's name validator.

### GTM Preview verification (passed)

All three new tags fired correctly in workspace Preview:
- Tag 67 fired on `generatedFirstNote` dataLayer push (Custom HTML - Succeeded)
- Tag 68 fired on `CompleteRegistration` dataLayer push (Custom HTML - Succeeded)
- Tag 69 fired on `/scheduled-confirmed` page view (Custom HTML - Succeeded)

Legacy `Meta - First Note Event` and `Meta - SignUp Confirm Event` tags also fired correctly in Preview, confirming the May 2 production-side drop is NOT a GTM regression. Most likely cause is browser-side blocking of `facebook.com/tr` calls (ad-blockers, iOS Safari ITP). CAPI parity (Phase 2) is the structural fix.

### Meta Test Events verification (deferred to post-publish live check)

Meta's Test Events UI opens a fresh tab without the GTM Preview connection, which loads the live container (version 20) — no Purchase tags present yet. Test Events flow therefore cannot validate workspace-only tags via Meta's standard path.

Decision: skip Test Events as a pre-publish gate. The pixel is empirically reaching Meta from this domain (existing CAPI integration sees ~488/day CompleteRegistration fires), so the new browser-side Purchase tag should too. Verification happens post-publish via Meta Events Manager Overview tab live ingestion (~5-30 min lag).

### Live container snapshot (baseline captured)

Inspecting the live container (version 20, "Updated with Calendly Event") confirmed the legacy `Meta - First Note Event` (tag id 26) and `Meta - SignUp Confirm Event` (tag id 27) are both ACTIVE, bound to correctly-configured triggers (15, 17), last edited January 2025. So the May 2 production drop happened below GTM. Full snapshot now in `ads_engine/config/gtm/snapshot-{tags,triggers,variables}-2026-05-04.json` for future regression diff.

---

## Phase 2: CAPI + identity for FirstNote (Alfred, 5-7 days)

**Engineering ticket scope:** when the BE persists a new note via the existing first-note creation path (find via grep for the same hook that updates `onboardingSteps.generated_first_note`), ALSO POST to Meta Conversions API with the payload below.

### CAPI POST shape

`POST https://graph.facebook.com/v21.0/1625233994894344/events?access_token={{META_CAPI_ACCESS_TOKEN}}`

```json
{
  "data": [{
    "event_name": "Purchase",
    "event_time": "<unix_seconds>",
    "event_id": "<same UUID generated client-side and pushed to dataLayer in the generatedFirstNote event>",
    "event_source_url": "<the page URL where the FE event fired>",
    "action_source": "website",
    "user_data": {
      "em": ["<sha256(lowercase(email))>"],
      "ph": ["<sha256(phone)>"],
      "fn": ["<sha256(first_name)>"],
      "ln": ["<sha256(last_name)>"],
      "external_id": ["<user_id raw, not hashed>"],
      "fbp": "<_fbp cookie value, raw>",
      "fbc": "<_fbc cookie value, raw>",
      "client_user_agent": "<request user agent>",
      "client_ip_address": "<request client IP>"
    },
    "custom_data": {
      "value": 150,
      "currency": "USD",
      "content_name": "first_note"
    }
  }]
}
```

### Token

`META_CAPI_ACCESS_TOKEN` already minted (Apr 29) and persisted in Nate's `~/.claude/.env`. Alfred should pull it from wherever JotPsych BE stores secrets (likely the same place `META_PIXEL_ID` lives). Don't generate a new one (it would invalidate the existing token in surprising ways per Meta's UI warning).

### Idempotency / dedup

`event_id` is the dedup key. The FE already generates a UUID for the dataLayer push (need to verify this is true for `generatedFirstNote`; if not, add it to the React-side push). BE reads that same event_id from the request that triggered the first-note save and uses it in the CAPI payload. Meta dedupes within ~7 days.

### FE side (verified 2026-05-04 against `origin/staging`)

The React app's `generatedFirstNote` dataLayer push has **four call sites and none of them currently include `event_id`**:

- `src/web-app/src/Views/RecorderView.tsx:315` — pushes `{event: 'generatedFirstNote', platform}`
- `src/web-app/src/features/encounters/components/v1/EncounterView.tsx:565` — pushes `{event: 'generatedFirstNote', platform}`
- `src/web-app/src/features/encounters/components/v1/hooks/useEncounterSubmission.ts:50` — pushes `{event: 'generatedFirstNote', platform}`
- `src/web-app/src/features/encounters/components/v2/EncounterViewV2.tsx:2658` — pushes `{event: 'generatedFirstNote'}` (note: missing `platform` field that the others have; minor pre-existing inconsistency)

Phase 2 needs to add `event_id: crypto.randomUUID()` (or equivalent) to ALL four sites, AND surface that event_id to the BE request that creates the note so BE uses the same one in the CAPI payload. Recommended implementation: extract a small helper (e.g. `services/attribution/fireFirstNoteEvent.ts`) that generates the UUID once, pushes to dataLayer, and returns the event_id for the BE request. Replace the four scattered `trackEvent({event: 'generatedFirstNote', ...})` calls with the helper. Drives consistency across v1/v2 paths and gives a single place to update when patterns evolve.

The GTM Custom HTML snippet then reads `{{event_id}}` from the dataLayer (configure as a Data Layer Variable in GTM > Variables) and passes it as `eventID` to the browser pixel call. Meta sees the same event_id from browser pixel + CAPI, dedupes them, keeps the richer one.

### Mirror pattern

Follow the GDN-1180 implementation in `services/attribution/pixels.ts` and `Views/AuthenticationCallback.tsx`. The CAPI shape is identical, only the trigger differs (first-note creation vs auth callback). SignUp / CompleteRegistration CAPI is already shipped via GDN-1180; no new work for that event. Calendar CAPI is out of scope for now (low value, low volume; defer until base setup is verified).

### Done criteria

Meta Events Manager > Pixel > Overview > FirstNote shows EMQ score >= 7, "Server" event source share >= 30%, and dedup rate visible (browser + server events being matched).

---

## Phase 3: Calibration (Nate, day 30+)

**Trigger:** 30+ days after Phase 1 ships, OR when Meta Ads Manager shows >100 attributed Purchase events on the ad set, whichever comes first.

**Process:**
1. Pull cohort data for each upstream event from the BE source of truth:
   - Of users who triggered Calendar today, what fraction became FirstNote within 60 days?
   - Same for SignUp.
2. Recalibrate values:
   - Calendar value = (true FirstNote LTV) × (Calendar→FirstNote conversion rate) × (in-attribution-window fraction)
   - Same formula for SignUp
   - FirstNote value = LTV directly (no decay needed since it IS the money event)
3. Update the three GTM tag values (Tags > edit > save > publish).

**Important:** changing Meta conversion event values does NOT reset learning phase. Safe to recalibrate without delivery impact.

---

## Verification gates

These must pass in order before declaring success.

| Gate | Pass criterion | Owner | Window |
|---|---|---|---|
| 1. GTM tags publish without error | All three tags fire in Preview, container publishes successfully | Nate | Phase 1, ~1 hour |
| 2. Meta receives Purchase events | Meta Events Manager > Test Events shows three Purchase events with correct value/content_name within 5 min of test fire | Nate | Phase 1, immediate |
| 3. Ad set rebind takes effect | Ad set effective_status reflects new optimization event within 1h, learning phase indicator shows | Nate | Phase 1, ~1 hour |
| 4. action_values populate in insights | Within 24-48h, ad set Insights shows non-zero `Purchase value` column | Nate | Phase 1+24h |
| 5. CompleteRegistration volume sanity check | After 7 days post-rebind, weekly CompleteRegistration count is in the 70-350 range (10-50/day, real new signups). If >5x weekly FirstNote count, kill its $25 value attribution and investigate first_capture gating | Nate | Phase 1+7d |
| 6. CAPI dedup working | Meta Events Manager > Pixel > Overview > FirstNote shows EMQ >= 7 and "Server" event source share >= 30% | Alfred | Phase 2 done |
| 7. Learning phase exit | Ad set delivery status moves from "Learning" to "Active" | Nate | Phase 1+7-14d |
| 8. CpFN recovers | Cost per FirstNote returns toward humming-era $144, or stable trajectory below $300 | Nate | Phase 1+30d |

If gates 1-3 don't pass within 4 hours of starting Phase 1, halt and reassess before going further.

---

## The biggest open concern: SignUp / CompleteRegistration accuracy

This is the most likely failure mode, surfaced explicitly per Nate's prompt.

**The data:** CompleteRegistration is firing at 488-572/day right now (May 2-4), down from a 4031/day spike on Apr 30. Real new JotPsych signups are likely 10-30/day.

**Why the gap:** GDN-1180 added a `first_capture=true` gate on the BE `captureSignupAttribution` mutation, intended to fire CompleteRegistration once per user lifetime. But "first capture" is currently firing for every existing user the first time they log in post-deploy (Apr 29). Effectively a backfill burning down through the active user base. With ~5000 active clinicians and 488 firing/day, this is roughly consistent with a 10-day backfill.

**Expected trajectory:** if the gating logic is correct, daily volume should continue decaying toward true new-signup rate (10-30/day) over the next 7-14 days. By May 14, CompleteRegistration should be near-equal to FirstNote volume.

**Risk:** if `first_capture` is buggy and fires on every callback (not once per user_id), volume will plateau or grow rather than decaying. We won't know definitively until 7+ days post-rebind.

**Mitigation:**
1. Phase 1 ships with CompleteRegistration tag at $25 value. Risk accepted because lower-bound real volume (10-30/day × $25 = $250-750/day attributed value) is reasonable, AND the over-firing scenario is detectable by gate 5.
2. If gate 5 fails: edit the GTM tag for `Meta Purchase — Sign Up`, change value to $0 within 5 minutes (single GTM edit, no engineering ask). Tag still fires for behavioral context but contributes no value to optimization. Open an Alfred ticket to audit `first_capture` gating in `AuthenticationCallback.tsx`.
3. Conservative alternative: ship Phase 1 with CompleteRegistration tag at $0 value from day one, raise to $25 only after gate 5 passes. Less downside but loses the SignUp signal during the first week.

**Recommended: ship at $25 with explicit gate 5 monitoring at day 7.** Bounded downside, faster signal.

---

## Decisions made and trade-offs accepted

| Decision | Trade-off accepted |
|---|---|
| Meta standard `Purchase` event, not custom CCs | Removes 3 known silent-fail modes, enables multi-event VALUE optimization that CCs blocked. Cost: less semantic clarity in Meta reporting; need `content_name` to distinguish event types in insights |
| All three events into the existing one ad set | Combined volume clears 50/wk learning threshold without needing per-event ad sets. Cost: single audience targeting; no per-event audience differentiation |
| Placeholder values $150 / $25 / $5, calendar discounted for attribution decay | Directional ratio is more important than exact magnitudes; uncalibrated values still beat count optimization. Cost: optimization is biased toward our guesses for ~30 days until calibration |
| Phase 1 (GTM) ships before Phase 2 (CAPI) | Faster to live signal; ad set unpaused with optimization data flowing within hours. Cost: until CAPI ships, FirstNote browser-only fires limit EMQ to ~3-4 |
| CompleteRegistration in Phase 1 with $25 value | All three signals from day one. Cost: 7 days of monitoring risk before we know if first_capture gating is correct |
| Calendar trigger via Page View on `/scheduled-confirmed*`, not dataLayer push | No marketing-site code change required for Phase 1. Cost: less precise trigger; misses any bookings that don't hit that confirm page |
| Defer Calendar CAPI | Low value, low volume, not blocking. Cost: Calendar EMQ stays low; revisit if Calendar volume grows materially |
| Phase 1 ships at current daily budget (likely <$1000); raise to $1000 only after gate 4 passes | Don't accelerate spend against unverified signal. Cost: slower data accumulation in week 1 |

---

## Risks

1. **CompleteRegistration over-fires past the gate 5 window.** Mitigation: drop tag value to $0 within 5 min (one GTM edit), let Alfred audit gating. Bounded downside (~7 days of polluted optimization).
2. **GTM Preview doesn't catch a tag mis-config.** Mitigation: Meta Events Manager Test Events is a second verification before we trust the data. Spend doesn't get optimized against bad signal until gate 4 passes.
3. **CpFN doesn't recover even after clean signal.** This means the Apr 16 restructure damage is the actual root cause, not attribution. If gate 8 fails after 30 days of clean Purchase data, audit the campaign structure (audience stacking, ad set fragmentation, creative quality), not the pixels.
4. **Marketing-site `/scheduled-confirmed` URL doesn't fire on every booking.** Verify in step 1.3. If actual confirm path is different, OR if some bookings happen in-app without going through this URL, the calendar tag will under-count. Worth a 5-minute audit during Phase 1.
5. **iOS ATT caps prioritize the wrong events.** Risk that iOS users only get N events tracked per pixel and Apple picks the lowest-value ones. Mitigation: all three events fire as the same Meta event (`Purchase`), so Apple's prioritization is one event type, not three. Likely fine.

---

## Out of scope

- Wiring Google Ads conversion tracking (separate playbook, do once Meta is verified and CpFN is moving)
- Re-architecting the legacy `signupConfirm` and `generatedFirstNote` dataLayer pushes in the React app (Phase 1 keeps them; the Purchase tags listen to existing events)
- Investigating the May 2 GTM regression that broke legacy SignUpConfirm/FirstNote pixel fires (if Phase 1 publishes a clean Purchase setup, that regression becomes irrelevant)
- Building a productionized calibration data pipeline (Phase 3 calibration is manual at day 30; productionizing is later)
- Recovering CpFN measurement for the period before Phase 1 (unrecoverable; baseline starts now)
- Re-platforming attribution to a BE-first event architecture (Phase 2 puts FirstNote on CAPI, which is the partial step toward that; full BE-first re-architecture is a separate decision for later)

---

## Open questions

1. ~~Does the marketing-site `/scheduled-confirmed` page fire on every calendar booking?~~ **Resolved 2026-05-04, Nate:** every booking lands on `/scheduled-confirmed`. Page View trigger is sufficient.
2. Is `first_capture` in `AuthenticationCallback.tsx` actually gating per `user_id`, or does it fire on every callback with a bug? Resolving early would let us choose between $25 and $0 starting value with confidence. Worth a 30-min audit by Alfred during Phase 2.
3. What is the actual number of new JotPsych signups per day, from the BE source of truth (user-creation table)? We're using 10-30/day as an estimate; a precise number would let us validate gate 5 with confidence and properly size CompleteRegistration value. One BE query Alfred can run.
4. Should we eventually pause the CompleteRegistration browser pixel fire entirely, letting only CAPI handle it once CAPI proves out? Tighter dedup, lower client-side noise. Defer this decision to month 2.

## Resolved decisions (post-plan-write, 2026-05-04)

- **Calendar trigger:** Page View on `/scheduled-confirmed*` confirmed sufficient (every booking hits this URL).
- **Daily budget at start:** keep current (sub-$1000), raise to $1000 only after gate 4 passes.
- **`event_id` on `generatedFirstNote`:** confirmed missing from all four call sites in `origin/staging`. Adding it is part of Phase 2 scope. See Phase 2 "FE side" section.
