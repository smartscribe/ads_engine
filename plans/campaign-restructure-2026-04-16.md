# Campaign Restructure: OUTCOME_SALES + Value Prop Ad Sets

## What We're Doing

Replace the existing Farm and Scale campaigns (OUTCOME_LEADS) with new campaigns (OUTCOME_SALES) that enable true value optimization. Reorganize ad sets by value proposition so Meta's algorithm learns which audiences respond to which message, not just which ad happened to be in which bucket.

## Rollback Plan

**Old campaigns are PAUSED, not deleted.** At any point:
1. Pause new campaigns
2. Reactivate old campaigns
3. Everything is back to previous state in <5 minutes

No ads are deleted. No creatives are destroyed. Old campaigns retain all history.

---

## New Structure

### Farm: Testing - Q226 (OUTCOME_SALES)

| Ad Set | Ads | Daily Budget |
|--------|-----|-------------|
| **Billing & Audit** | 16 ads (all AN/AJ audit ads) | $80 |
| **Time Savings** | AI for Progress Notes, Florence Static, Nate Podcast | $30 |
| **EHR Integration** | EHR V2, PDF to Template, AI Progress Concept 2 | $30 |
| **UGC / Social Proof** | KM Video Concept 2 | $30 |
| **AI Progress Concepts** | Concept 3, Concept 4 | $30 |

Total Farm daily budget: **$200/day**

### Scale: Winners - Q226 (OUTCOME_SALES)

Empty at launch. Ads get promoted here when they prove out in Farm. Same 5 ad set structure, budget allocated as winners emerge.

---

## Ad Set Configuration (All Ad Sets)

| Setting | Value |
|---------|-------|
| Objective | OUTCOME_SALES |
| Optimization goal | VALUE |
| Conversion event | FirstNote (primary) |
| Value optimization | Enabled |
| Billing event | IMPRESSIONS |
| Pixel | 1625233994894344 (WebApp Actions) |
| Attribution | 7-day click, 1-day view |

### Audiences (All Ad Sets)

**Inclusion:**
- Sales Prospect List - BH Clinics (`120245449291240548`)
- Lookalike - BH Clinic Prospects 1% (`120245449291800548`)
- Lookalike - First Note Converters 1% (`120245449282540548`)
- NPPES PMHNPs + Psychiatrists (pending — will attach when ready)

**Exclusion:**
- Stripe Customers - Auto Exclusion (`120245449143920548`)
- Converters - First Note Completers (`120245449282160548`)

---

## Execution Sequence

### Step 1: Create new campaigns via API
- Farm: Testing - Q226 → objective=OUTCOME_SALES
- Scale: Winners - Q226 → objective=OUTCOME_SALES

### Step 2: Create 5 ad sets in Farm campaign
- Each with audiences, budgets, and value optimization configured
- All ad sets start PAUSED

### Step 3: Duplicate ads into new ad sets
- Copy each ad's creative (image/video + copy) from old campaign into new ad set
- Preserve ad names for tracking continuity

### Step 4: Verify in Ads Manager GUI
- Confirm OUTCOME_SALES objective
- Confirm value optimization enabled
- Confirm audiences attached
- Confirm conversion event = FirstNote with value

### Step 5: Cutover
- Pause old Farm campaign ("Farm: Testing - Apr 2026")
- Pause old Scale campaign ("Scale: Winners - Apr 2026")
- Activate new Farm campaign
- Verify ads are delivering

### Step 6: Cleanup (after 7 days of stable performance)
- Old campaigns remain paused (rollback insurance)
- Delete empty duplicate audiences from failed earlier runs (`120245449281870548`)

---

## Ad → Ad Set Mapping

### Billing & Audit (Farm, $80/day)
1. AJ: Audit Letter Arrives. You're Ready ← **best performer, $96 CpFN**
2. AJ: Audit Ready. Home On Time
3. AJ: How Much Did You Underbill?
4. AJ: Cigna Has Rules. JotPsych Knows Them - Copy
5. AN: 4 Different Logins
6. AN: 47 Different Payer Rules
7. AN: 847 Ways payers reject claims
8. AN: Audit Anxiety vs. Confidence
9. AN: Cigna vs. Aetna Rules
10. AN: Doing 99214, Billing 99213
11. AN: E-prescribe from scribe
12. AN: JotAudit Catches What Others Miss
13. AN: Missing $460?
14. AN: Most Stop at the Note
15. AN: Scribe that Thinks Like an Auditor
16. AN: Stop leaving your practice exposed to audit risk
17. AN: The Work. The Bill
18. AN: Your Notes Are Perfect - Insurance Doesnt Care - Copy

### Time Savings (Farm, $30/day)
1. Scale: AI for Progress Notes
2. Farm: Test: Florence Static 1 - Notes Complete
3. Farm: Nate Podcast 4 - ad

### EHR Integration (Farm, $30/day)
1. Farm: EHR V2
2. Scale: PDF to Template
3. Farm: Test: AI for Progress: Concept 2

### UGC / Social Proof (Farm, $30/day)
1. Farm: Test: KM UGC - Video Concept 2

### AI Progress Concepts (Farm, $30/day)
1. Scale: Test: AI for Progress Notes Concept 3
2. Scale: Test: AI for Progress Notes: Concept 4

---

## Landing Pages & UTMs

### Current Problems
1. **12 of 18 audit ads point at the homepage** instead of `/audit`. Conversion killer.
2. **Three different UTM formats** across ads — some have source/medium reversed, some have URL-encoded `%7B%7B` braces that Meta can't resolve.
3. **`http://` instead of `https://`** on many ads — causes redirect hop that may drop UTM params and `_fbc` cookie.

### Correct Mapping

| Value Prop | Landing Page |
|-----------|-------------|
| Billing & Audit | `https://www.jotpsych.com/audit` |
| Time Savings | `https://www.jotpsych.com/` |
| Time Savings (Podcast) | `https://www.jotpsych.com/making-time-for-presence` |
| EHR Integration | `https://www.jotpsych.com/features` |
| UGC / Social Proof | `https://www.jotpsych.com/` |
| AI Progress Concepts | `https://www.jotpsych.com/` |

### Standardized UTM Template (All Ads)

```
utm_source={{site_source_name}}&utm_medium=paid_social&utm_campaign={{campaign.id}}&utm_content={{adset.id}}&utm_term={{ad.id}}
```

Applied via `url_tags` at the ad set level so every ad in the set inherits it. No per-ad UTM configuration needed.

### Rules
- Always `https://www.jotpsych.com/` — never `http://`, never bare `jotpsych.com`
- UTMs in `url_tags` (ad set level), not baked into the URL
- `utm_source` = `{{site_source_name}}` (resolves to `fb` or `ig`)
- `utm_medium` = `paid_social` (literal, not a macro)
- `utm_campaign` = `{{campaign.id}}` (numeric ID for clean joins)
- `utm_content` = `{{adset.id}}` (ties to value prop ad set)
- `utm_term` = `{{ad.id}}` (ties to specific creative)

---

## What Could Go Wrong

| Risk | Mitigation |
|------|-----------|
| New campaigns enter learning phase, CpFN spikes for 1 week | Expected. Old campaigns are paused not deleted — reactivate if spike exceeds $400 CpFN after 5 days |
| OUTCOME_SALES doesn't support FirstNote as conversion event | Test with one ad set first before creating all 5. If blocked, fall back to OUTCOME_CONVERSIONS with value rules. |
| Budget too thin on $30/day ad sets (1 ad in UGC) | Monitor. If UGC ad set can't exit learning, merge it into Time Savings. |
| Audience overlap between inclusion audiences causes delivery issues | Meta handles overlap with auction-level dedup. Monitor frequency — if >2.0 in first week, narrow. |
