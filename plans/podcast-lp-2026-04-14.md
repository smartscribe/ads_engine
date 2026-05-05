# Nate Podcast landing page — Plan 2 of 3

**To the agent picking this up:** You are one of three parallel workstreams. Plan 1 is an audit-focused LP; Plan 3 is a site-wide LPV tracking fix. You do **not** need to coordinate with the other two — each plan is self-contained. Work this one to completion.

---

## TL;DR

Build a dedicated landing page inside `jotpsych.com` for traffic driven by the "Farm: Nate Podcast 4" Meta ad. This ad has the **highest link-click volume in the entire Farm+Scale account** over the last 10 days (533 link clicks, 5.52% link CTR) but converts those clicks into FirstNotes at **0.19% — 5x worse than the account baseline of 0.99%.** Podcast-warmed traffic expects content continuation, not a product pitch. We're losing an estimated 4 FirstNotes every 10 days on this single ad because the LP experience doesn't match the ad's emotional register. Build a podcast-matched LP that resolves curiosity into action without whiplash.

**Invoke `/landing-page-build` to execute.**

---

## Who Nate is / what JotPsych is / why this matters

- **Nate Peereboom** is the founder/CEO of JotPsych. He's the person IN the podcast ad. The podcast creative is literally "Farm: Nate Podcast 4 - ad" — episode 4 of a podcast featuring Nate. You'll need to pull the exact ad creative from Meta to see which podcast episode, which clip, which hook.
- **JotPsych** is agentic software for behavioral health clinicians. Target: solo NPs, small group practices, PHP/IOP clinics. Primary KPI is cost per first note (CpFN).
- **This project (ads_engine)** is Nate's ad-ops harness. The full 10-day performance briefing that produced this plan is at `data/ads-reports/briefing-10d-2026-04-14.html`.
- **Why this LP:** The podcast ad is pulling the most link-click volume in the account (3x what AJ: Audit Letter Arrives pulls) but converting those clicks at 5x below baseline. That's the single largest LP opportunity in the current ad portfolio by expected-FN-lift math. Podcast listeners are warm but exploratory — they clicked to learn more about the person/thesis, not to sign up. The current LP is a product pitch. That's the mismatch.

---

## Target state: what "done" looks like

1. A new page lives at `/Users/nathanpeereboom/jotpsych-harnesses/jotpsych_gtm/new_landing_page/site/{slug}.html` (slug decided during interrogation — likely `/podcast` or `/founder-story` or `/nate`) and ships to `jotpsych.com/{slug}`.
2. The page uses the existing site's design tokens, nav, and footer. Zero seam from the rest of the site.
3. All copy is real. No lorem ipsum.
4. The hero continues the podcast conversation — treats the visitor as if they just finished the episode and wants more, not as a cold prospect needing a product pitch. **The primary content is content, not conversion.**
5. CTA is earned — appears AFTER enough content to satisfy the podcast listener's curiosity. Not in the hero.
6. Meta OG, canonical, GTM, Meta Pixel, description all set per site convention.
7. Deployed via `/push-to-jotpsych-com` after Nate's explicit approval.

**Not done until:** Nate has reviewed the live preview, signed off on copy and sequencing, and approved deployment.

---

## Research already completed

### 1. Ad context — what you're building the LP for

**The ad:** `Farm: Nate Podcast 4 - ad` — currently running in `Farm: Testing - Apr 2026`. Static or video creative featuring Nate from Episode 4 of a podcast series.

**10-day performance (2026-04-04 → 2026-04-13):**

| Metric | Value |
|---|---|
| Impressions | 9,652 |
| Link clicks | **533** |
| Link CTR | **5.52%** (highest link-click volume in the non-LGF account; 2nd highest link CTR) |
| Landing page views | 23 |
| LPV per link click | **4.3%** (industry norm: 70–90% — same site-wide tracking problem Plan 3 is fixing, but also possible bounce signal) |
| FirstNotes | 1 |
| **Link→FN rate** | **0.19%** (vs account non-LGF baseline 0.99% → **5x below average**) |
| Spend | $237 |
| Raw CpFN | $237.40 |
| Post engagement | ~high (reactions/comments on the podcast clip) |
| Bayesian posterior median CpFN | $232 |
| Verdict from 10d briefing | HOLD — ambiguous signal, trending flat |

**The math on LP opportunity:**
- 533 link clicks / 10 days = 53/day
- Current rate: 0.19% → 1 FN on 533 clicks
- If an LP match lifted to account baseline (0.99%): +4 FN / 10 days
- If it lifted to the top-performer tier (Test: SB Video 1 converts at 7.95%): +40 FN / 10 days
- Even the pessimistic scenario (baseline lift) exceeds the audit LP's expected lift. The aggressive scenario dwarfs everything else in the portfolio.

**You MUST pull the actual ad creative from Meta before designing.** Use the Meta Marketing API:

```
GET /{ad_id}?fields=creative{id,title,body,object_story_spec,image_url,thumbnail_url,video_id,effective_object_story_id}
```

Ad IDs are in `data/ads-reports/raw-10d-2026-04-14.json` — search for `ad_name` containing "Nate Podcast 4". The credentials are in `~/.claude/.env` (`META_ADS_ACCESS_TOKEN`). The scope is `ads_management`, which includes read on creative objects.

**Specifically capture:**
- The video URL or thumbnail (the hero of the LP needs to echo this visual)
- The ad primary text (what Nate said in the caption)
- The headline
- The destination URL currently in use (where does the 533-click traffic currently land? probably homepage or features — note which it is, because that's what we're displacing)
- Any CTA button text (Meta shows "Learn More" / "Sign Up" / etc. — match or improve)

### 2. Podcast context — what you need to find out before building

**Known:** The ad is titled "Nate Podcast 4" which strongly implies this is the 4th episode of a podcast series featuring Nate. You need to figure out:

- Which podcast is this? Is it the JotPsych podcast, or an external interview?
- If internal: where are the episodes hosted? (Spotify? YouTube? Libsyn? Simplecast?)
- If external: who interviewed Nate? What's the show name? What was the topic?
- What's the actual episode title?
- What's the runtime?
- Are episodes 1, 2, 3 also ads? Is this a sequence we should link to?

**Where to look:**
1. Grep the Grain transcript cache (`data/grain/audit-research/*.txt`) for "podcast" — even though that cache is scoped to audit research, you might find podcast references in meeting chatter.
2. Look in `/Users/nathanpeereboom/Library/CloudStorage/GoogleDrive-nate@smartscribe.health/Shared drives/jotpsych_shared_workspace/` for any `podcast/` or `media/` or `content/` subfolder. There's likely a shared drive folder for marketing content.
3. Look in `new_landing_page/site/` for any existing page that mentions "podcast" — grep for it. If there's already a podcast mention on `about.html` or `index.html`, it'll tell you which show and platform.
4. Check `ads_engine/data/existing_creative/` if it has any naming that correlates with podcast episodes.
5. Ask Nate directly during the interrogation phase if none of the above pans out — this is a legit "I can't proceed without this" question.

**Why this matters:** A landing page that purports to continue the podcast conversation but has no actual link back to the podcast, no episode player, and no "listen to the other episodes" CTA is a worse experience than the generic homepage. The entire premise of this LP is that it's a content-first page that happens to lead to conversion.

### 3. What the current LP situation looks like (what you're displacing)

The 533 link clicks from this ad in 10 days currently land on whatever the ad's destination URL is set to (confirm when you pull creative). Almost certainly this is `jotpsych.com` (homepage) or `jotpsych.com/features`. Neither of those is the right experience for a podcast listener who clicked to hear more from Nate.

The conversion rate on whatever they currently land on is 0.19% link→FN. That's the floor. Any new LP that does not actively make things worse will outperform it.

### 4. Site structure (confirmed — same context as the other two plans)

- **Framework:** Plain static HTML. No React, no build step. Files in `new_landing_page/site/` ship directly to Netlify. `site/{slug}.html` becomes `jotpsych.com/{slug}` (Netlify `pretty_urls` strips the .html).
- **Deploy mechanism:** Push to `https://github.com/smartscribe/jotpsych.com` → Netlify auto-deploy → CNAME to jotpsych.com. Smoke-test via `/push-to-jotpsych-com` skill after build.
- **Shared components:** Nav/header injected via `<div id="site-header"></div>` + `<script src="assets/js/header.js"></script>`. Footer is copied from any existing page.
- **Design tokens (CSS vars in `assets/css/style.css`):**
  - Colors: `--midnight #1C1E85`, `--deep #1E125E`, `--warm #FFF2F5`, `--sunset #FD96C9`, `--afterglow #813FE8`, `--daylight #FFF3C4`, plus text/border tokens
  - Typography: **Archivo** for headings, **Inter** for body. `clamp()` for responsive heading sizes.
  - Spacing: 4px grid. Every padding/margin divisible by 4.
  - Buttons: `.btn.btn-primary`, `.btn.btn-outline`, `.btn.btn-white`, `.btn.btn-ghost`, `.btn.btn-sm`
  - Layout: `.container` (1200px max-width + padding). Section padding `80px 0` desktop / `56px 0` mobile. Hero padding `140px 0 80px`.
  - Animations: `class="anim-target"` for scroll fade-in.
- **Reference pages:**
  - `site/about.html` — small campaign / narrative page (closest match for a story-forward LP)
  - `site/index.html` — homepage hero structure
  - `site/jotstart.html` — single-focus conversion LP reference
- **CSS class prefix rule:** use `.np-` for this page (Nate Podcast) to prevent collisions with global styles.

### 5. What we know about Nate's podcast voice from Grain

These are excerpts from internal/sales calls that capture how Nate talks when he's being himself (not doing a product pitch). These are the tonal baseline for the LP's voice — if the LP doesn't sound like this, it's wrong.

> *"The best way to build trust with a clinician is to demonstrate that you understand their day. Not tell them you do — show them."* — Nathan Peereboom, internal 2026-02-11

> *"We're not trying to be an EHR with AI bolted on. We're building the thing that EHR companies will try to copy in five years and can't, because they have twenty years of technical debt and we have twenty months."* — Nathan Peereboom, JotBill Analysis Presentation 2026-03-11

> *"AI is going to be the way that insurance companies crush small practices. When you have the ability to litigate and audit every single note, insurance companies will very soon have that ability. If you don't have a similarly sophisticated billing company, it's going to be a pretty rocky few years."* — Nathan Peereboom, JotBill Analysis Presentation 2026-03-11

> *"Some people look and they say, hey, I'm billing, this is great. I'm just submitting claims. And then they get audited and 30% of their revenue gets clawed back. And it's really, really tragic."* — Nathan Peereboom, JotPsych & JotBill Discussion 2026-01-23

**Voice characteristics:** Direct. Slightly oppositional (against the conventional wisdom). Strong on the "them vs. us" frame where "them" is big-vendor incumbents and "us" is small practices. Uses absolute statements confidently. Acknowledges real pain before proposing solutions. Never apologizes. No hedging.

These should inform how the LP talks to the listener. The podcast listener chose to hear Nate's voice — the LP should sound like Nate, not like JotPsych marketing.

### 6. CRITICAL: How NOT to write this LP

Most landing pages built from this research brief would fail because they'd over-convert. Here's what NOT to do:

- **Don't lead with "Start your free trial."** The listener clicked to hear more, not to sign up. A trial CTA in the hero is whiplash.
- **Don't lead with JotPsych product features.** They already know what JotPsych does from the podcast — if they didn't they wouldn't have clicked.
- **Don't treat the page as a sales page.** Treat it as an extension of the podcast episode.
- **Don't use the standard "hero → features → pricing → CTA" template.** That's product-page convention. This is a content page that ends in a CTA.
- **Don't skip the podcast episode itself.** The first section should give the listener a way to finish the episode or listen to others. If they haven't listened yet (got the ad while scrolling), they should be able to listen on-page.

---

## How to execute: invoke `/landing-page-build`

### Step 0 — BEFORE invoking the skill, do these fact-gathers

Unlike Plan 1 (audit LP) which has all its research pre-loaded, this plan has two known-unknowns that need resolving before the question round will be useful:

1. **Pull the actual Meta ad creative.** See the instructions in Section 1 above. Cache the JSON response at `ads_engine/data/ads-reports/ad-creative-cache/nate-podcast-4.json` for future reference. From the response, extract and document in this file: the video URL or thumbnail, the primary text, the headline, the destination URL currently in use, and the CTA button text.

2. **Find the podcast itself.** Per Section 2 above, locate the actual podcast episode (show name, episode title, platform, URL, runtime). If you cannot find this without asking Nate, that's fine — flag it as an interrogation-phase question and proceed.

Append both findings to the "Progress log" section at the bottom of this file when done.

### Step 1 — Invoke `/landing-page-build`

Tell the skill: "All Phase 0 context is in `plans/podcast-lp-2026-04-14.md`; the ad creative has been pulled and is cached at `ad-creative-cache/nate-podcast-4.json`. Proceed to Phase 1."

### Step 2 — Phase 1 Question Round (question bank)

Cover these during Phase 1 via AskUserQuestion (batches of 3–4):

1. **Primary audience framing.** The podcast listener who clicked. Is that a (a) prospective clinician customer considering JotPsych, (b) an already-curious industry person (operator/VC/founder) who listens to Nate for thought leadership, or (c) an existing customer advocating internally? The current ad is running in the Farm campaign so the assumption is (a) — confirm.

2. **Podcast episode linking.** Should the LP (i) embed the episode inline so listeners can finish it on the LP, (ii) link out to the platform (Spotify/Apple/etc.), (iii) both — embed + "listen on your platform" secondary link, or (iv) just reference it textually without playback? (Recommendation: both, with embed as primary.)

3. **Page sequence.** Possible sections, in order:
   a. Hero: "You just heard episode 4. Here's the rest."
   b. Inline episode player / "listen on your platform" grid
   c. Episode show notes or extracted quotes
   d. "About Nate" / "About JotPsych" one-liner
   e. "What you can do next" — options that range from "subscribe to the podcast" (low friction) to "start a free trial" (high friction)
   f. Social proof — testimonials that echo the podcast's thesis
   g. CTA footer
   Which ordering? Are any sections cut?

4. **Primary CTA.** Given the content-first thesis, the primary CTA is deliberately lower-intent than a product page. Options:
   - Subscribe to the podcast on Apple/Spotify (content continuation)
   - Join the JotPsych newsletter (medium commitment)
   - Start a free trial (direct conversion — but risks whiplash)
   - Book a demo with Nate (extremely high commitment but the listener has pre-trusted him)
   - Download a free resource like "The Audit Defense Playbook" (lead magnet)
   Which is primary? Can we have a stacked "low + medium + high commitment" CTA sequence rather than one dominant button?

5. **Tone calibration.** The podcast listener has already heard Nate's voice. The LP should sound like that voice — not like the rest of jotpsych.com marketing. Is Nate OK with a materially different voice on this specific page? (i.e., first-person, direct, oppositional — more like his Grain quotes than the current `index.html` copy.)

6. **Show the ads engine findings?** There's an interesting meta-move here: the podcast is about how Nate thinks about building JotPsych, and the LP could briefly surface "here's what we learned from the last 10 days of ads — this page exists because of a data finding" as a proof-of-thinking. That's very on-brand for Nate but very unusual for a marketing LP. Discuss.

7. **Slug.** `/podcast`, `/founder-story`, `/nate`, `/from-the-founder`, `/episode-4`? Different slugs set different reader expectations.

8. **Nav behavior.** Standard site nav, or stripped-down for content focus? Content pages usually benefit from full nav to encourage exploration; conversion pages usually benefit from stripped nav to reduce friction. Which is this?

9. **Discoverability.** Should this page be linked from the main nav (/podcast as a top-level link)? Linked from the footer? Indexed by search engines? Only reachable via the ad?

10. **Re-use.** If we build this well, is the pattern reusable for future podcast episodes (episode 5, 6, etc.)? If yes, the page should be built as a template-able structure with episode-specific content that can be swapped out. If no, build it as a one-off.

11. **Other content on the page.** Should we include show notes, transcript excerpt, guest bios (if episode 4 has a guest), or just Nate + the episode? A full show-notes page is content-rich but slow to build; a Nate-only page is simpler and faster.

12. **Social proof angle.** What proof statements match the podcast's thesis? The podcast is Nate's voice so the LP proofs should be "here's who's listening to Nate and acting on it" — customer quotes that reference founder trust, not just product efficacy. Check the Grain corpus for "I trust Nate" / "I heard Nate on the podcast" type quotes.

13. **Newsletter integration.** Is there an existing JotPsych newsletter? If yes, newsletter signup is a strong medium-commitment CTA for content-warmed traffic. If no, this might be the moment to create one (out of scope for this build, but flag it).

14. **Episode 5+ pipeline.** Is there a plan for future podcast episodes? If yes, the LP becomes evergreen ("I'm on a podcast about building healthcare software — here are all the episodes"). If no, this is an episode-4-specific moment.

### Step 3 — Phase 2 `/this-or-that` calibration (3–6 pairs)

Mandatory pairs:

1. **Hero sequencing** — "Hero with big player embed" vs "Hero with text-first continuation framing, player below the fold"
2. **Tone** — "Marketing-polished" vs "Unpolished, first-person, like the podcast itself"
3. **CTA placement** — Single prominent CTA above the fold vs Low-friction content links first, high-intent CTA at the end
4. **Visual style** — Photographic (Nate's face) vs Abstract/typographic (the podcast's wordmark or episode art)
5. *(optional)* Episode linking — Inline player vs Platform-link grid (Apple / Spotify / YouTube / etc.)

### Step 4 — Build rules (same as the other LPs)

1. Native subpage integration — same nav, same footer, same design tokens
2. All page-specific styles inline in `<style>`, prefix with `.np-`
3. 4px spacing grid, no `!important`, no stock-photo vibes
4. No screenshots of real JotPsych UI (you don't need any for this LP anyway)
5. The episode player embed: use the platform's official embed markup (Spotify iframe, Apple podcast widget, YouTube iframe, whatever). Do NOT rebuild a custom player.
6. If using Nate's photo, confirm with Nate first — make sure the photo has been approved for marketing use. Don't grab from social without permission.

### Step 5 — QC checklist before presenting to Nate

- [ ] Every section has a purpose. Cut any filler.
- [ ] The hero does NOT demand conversion. It welcomes content continuation.
- [ ] The episode is playable on the page OR reachable within one click.
- [ ] The voice sounds like Nate in his Grain quotes, not like marketing-Nate.
- [ ] All CTAs are appropriate for content-warmed traffic. No whiplash.
- [ ] Mobile at 768px and 480px — embed player resizes, CTAs stay tappable.
- [ ] Head tags: title, meta description, canonical, OG, Twitter card, GTM, Meta Pixel.
- [ ] No lorem ipsum, no TBD.
- [ ] `.np-` prefix on every page-specific class.
- [ ] No spacing values off the 4px grid.

### Step 6 — Deploy (ONLY after Nate signs off)

Use `/push-to-jotpsych-com`. Confirm the URL loads at `jotpsych.com/{slug}` and the player embed actually works in production (some embeds require specific CSP rules — if CSP blocks the embed, fix via `netlify.toml` updates).

---

## Files & paths

**Read from:**
- `~/.claude/.env` — Meta API credentials
- `~/.claude/CLAUDE.md` — global rules
- `~/.claude/skills/landing-page-build/SKILL.md` — the skill
- `~/.claude/skills/this-or-that/SKILL.md` — calibration skill
- `new_landing_page/site/about.html` — narrative page reference
- `new_landing_page/site/index.html` — homepage hero structure
- `new_landing_page/site/jotstart.html` — single-focus page reference
- `new_landing_page/site/assets/css/style.css` — design tokens
- `new_landing_page/site/assets/js/header.js`, `main.js` — shared JS
- `/Users/nathanpeereboom/Library/CloudStorage/GoogleDrive-nate@smartscribe.health/Shared drives/jotpsych_shared_workspace/` — look for podcast/media/content folders
- `ads_engine/data/grain/audit-research/*.txt` — grep for "podcast" references
- `ads_engine/data/ads-reports/raw-10d-2026-04-14.json` — find Nate Podcast 4 ad IDs
- `ads_engine/data/ads-reports/briefing-10d-2026-04-14.html` — full 10-day briefing for broader context

**Write to:**
- `new_landing_page/site/{slug}.html` — the new page (slug decided in interrogation)
- `new_landing_page/site/assets/images/` — any new imagery (confirm permission first)
- `plans/podcast-lp-2026-04-14.md` — **this file; append progress notes**
- `ads_engine/data/ads-reports/ad-creative-cache/nate-podcast-4.json` — cached Meta creative response

**Never write:**
- Global `style.css`
- Anything in the product_guide Drive folder
- Anything in `~/.claude/skills/` unless adding legitimate new skill infra

---

## Known unknowns & decisions to surface

- **What IS the podcast?** Highest-priority unknown. See Section 2 for how to figure it out.
- **Does Nate want a photo of himself on the page?** The LP works better with a face; confirm photo permission.
- **Is the podcast a one-off or a series?** Affects whether the LP is evergreen or episode-specific.
- **Is there a newsletter?** Affects CTA options.
- **Who owns the podcast hosting?** If it's on a 3rd-party platform (Apple/Spotify), we need embed codes and may need to respect platform branding.
- **Is episode 4 the latest? Will episode 5 render this LP stale?** If yes, build for reusability.
- **The LPV tracking anomaly is still in play.** Plan 3 is fixing it in parallel. The podcast ad currently shows 4.3% LPV/link ratio — meaning we probably can't trust the LPV count even today. Measuring the lift from this new LP will be hard until Plan 3 ships. Note this in the post-deploy handoff to Nate.

---

## Out of scope (do not do these)

- **Do not build the audit LP.** That's Plan 1.
- **Do not fix LPV tracking.** That's Plan 3.
- **Do not deploy without Nate's approval.**
- **Do not modify global `style.css`.**
- **Do not create a newsletter system** if one doesn't exist. Flag it and move on.
- **Do not rebuild a custom audio/video player.** Use platform embeds.
- **Do not grab Nate's photo from LinkedIn or Twitter without permission.**
- **Do not pretend to know the podcast name if you can't find it.** Ask Nate.
- **Do not A/B test** — build one page, ship one page. Future iteration is a separate cycle.

---

## Progress log (append as you work)

- **2026-04-14** — Plan file created. Research complete on ad performance (Section 1) and tone baseline (Section 5). Two known-unknowns: (a) actual ad creative needs to be pulled from Meta, (b) actual podcast show/episode/platform needs to be identified. Both are Step 0 fact-gathers before invoking the skill.
- **2026-04-14** — Phase 0 fact-gathers complete (via `/landing-page-build`):
  - **Meta creative pulled** for ad_id `120244893449570548` → `data/ads-reports/ad-creative-cache/nate-podcast-4.json`. Key findings:
    - `object_type`: VIDEO. `video_id`: `1036710121854220` (active spec; top-level also shows `1393258451826490`).
    - **Ad copy is generic product-pitch, NOT podcast content.** Title: "AI Notes, Built for Behavioral Health". Body: "Psychiatrists spend 1–2 hours a day finishing notes." CTA: `LEARN_MORE`.
    - Destination URL: `http://www.jotpsych.com/` (homepage — no UTM specificity beyond dynamic placeholders).
    - `asset_feed_spec` shows Meta is rotating 3 bodies + 3 titles — one title variant is "Trusted by Psychiatrists & PMHNPs".
    - **Implication for plan thesis:** the ad *copy* isn't content-first — but the *video asset* is podcast-sourced (name "Nate Podcast 4" refers to the 4th podcast Nate appeared on). The mismatch theory still holds: clinicians see Nate speaking authentically in podcast footage, click expecting more of that voice, and land on a generic product homepage. The LP needs to continue the podcast-voice experience.
  - **Podcast candidates found** on `site/news.html` — JotPsych's existing press page already lists 4 Nate podcast appearances:
    1. Practice of the Practice — *How AI is Changing Behavioral Healthcare with Nate Peereboom* — Sep 2025 — Spotify `3L9AiModV663969kbcqo9R`
    2. The Modern Therapist's Survival Guide — Apr 2025 — Spotify `1snPxaGR0tW0dSta0SIa5s`
    3. The Trauma Therapist — Mar 2025 — Spotify `7ocrWYb3ArJ7gEnkx1oSXH`
    4. Future of Psychiatry — *AI-Based Smart Documenting with JotPsych* — Mar 2024 — Spotify `3N5UYm2tbBKdROlFcYcVlg`
    - "Podcast 4" in the ad name could mean the 4th one Nate filmed a cut from, or the 4th in listed order. **Confirmation needed from Nate in interrogation.**
  - **Reference pages read:** `about.html` (narrative hero pattern), `jotstart.html` (`.js-` prefix convention, inline styles, split hero grid, photo + floating card). CSS prefix for this build: `.np-`. Design tokens confirmed in `assets/css/style.css`.
- **2026-04-14 (build complete, not deployed)** — Phases 1–4 complete. Nate stood down the deploy mid-waterfall and said the push would be handled in another thread (Plan 1's audit.html is also pending, doesn't want to couple the two). State:
  - **Built:** `new_landing_page/site/making-time-for-presence.html` (~540 lines, single file, inline `.np-` styles, uses global `.final-cta` + footer classes). Pixel ID matches the new canonical WebApp Actions dataset `1625233994894344` (commit `8664313` swapped all site pages to it earlier on 2026-04-14).
  - **Slug decided:** `/making-time-for-presence` (derived from the real episode title "JotPsych: Making Time for Presence and Creativity For Behavioral Health Clinicians with Nathan Peereboom").
  - **Episode confirmed:** Nate confirmed the "Nate Podcast 4" ad footage is sourced from **The Trauma Therapist** with Guy MacPherson, published 2025-03-17, 26 min, Spotify id `7ocrWYb3ArJ7gEnkx1oSXH`. Cover art served directly from `image-cdn-fa.spotifycdn.com`.
  - **Page sections:** hero (split: first-person letter + cover art) → Spotify embed + platform link row → 3 large italic pulled quotes (reusing approved Grain quotes from Section 5, framed as "What I keep coming back to" rather than falsely attributed to the episode) → one-paragraph JotPsych about → dark-gradient `.final-cta` with Book-a-demo primary + Try-for-free ghost.
  - **Deliberate skill deviation:** no CTA above the fold — the skill default is "primary action visible without scrolling," but Plan 2's thesis is content continuation, so the hero has zero conversion surface. Nate confirmed this framing during Phase 1.
  - **Visual QC passed** at 1280 / 768 / 480. Screenshots in `new_landing_page/.playwright-mcp/`. Two harmless console warnings (iframe `allow`/`allowfullscreen` precedence; Meta Pixel duplicate init from shared `header.js` — not page-specific).
  - **Side edits:**
    - `site/sitemap.xml` — added `/making-time-for-presence` at priority 0.6 (and a linter/other thread also added `/audit` at 0.7 from Plan 1).
    - `site/news.html` — Trauma Therapist card already points at `/making-time-for-presence` in HEAD (commit `8664313` folded that edit in alongside the pixel swap).
  - **Untouched / still TODO:**
    - Meta ad `120244893449570548` destination URL is still `http://www.jotpsych.com/?utm_source=...` — needs to flip to `https://jotpsych.com/making-time-for-presence?utm_source={{site_source_name}}&...` via Marketing API POST after deploy. Scope on the user token includes `ads_management`, so `POST /{creative_id}` (creative `728612216169042`) or a new creative + ad update is feasible.
    - Deploy: `/push-to-jotpsych-com` not run. `site/making-time-for-presence.html` is still untracked. `site/audit.html` also untracked (Plan 1 — not my scope to stage).
    - Measurement caveat: CSP fix for Meta Pixel (commit `8664313`) just shipped — it probably resolved the 6% LPV-tracking anomaly, so lift measurement on this LP should be cleaner than the plan originally assumed. Still, the first 3–5 days of post-deploy data will have mixed attribution state.

---

## Final handoff to Nate

When done:
1. Live preview URL
2. One-page summary: what's on the page, key decisions made, how the page differs from the rest of the site, open questions
3. Absolute path of the new page
4. **Critical note:** this LP is built on the theory that podcast-warmed clicks want content continuation, not product pitching. The current link→FN rate is 0.19%; if the new LP lifts it to baseline (0.99%) that's +4 FN/10 days, if it lifts to top-tier (7.95%) that's +40 FN/10 days. Measuring the lift will be distorted until Plan 3 (LPV tracking fix) ships.
5. Request for explicit deploy approval

Do not self-deploy. Minto the summary.
