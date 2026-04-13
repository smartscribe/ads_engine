# Ads Engine — System Diagram

How the JotPsych product, Stripe, Meta Ads, and this harness connect.

Last updated: 2026-04-06

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        JotPsych Product                                 │
│                                                                         │
│   User sees ad → Clicks → Signs up → Completes first note              │
│                                                                         │
│   ┌──────────┐     ┌──────────────┐     ┌───────────┐                  │
│   │  Website  │────▶│  App / Trial  │────▶│  Stripe   │                 │
│   │jotpsych.com│    │  (signup)    │     │ (billing) │                  │
│   └─────┬────┘     └──────┬───────┘     └─────┬─────┘                  │
│         │                 │                    │                         │
│    Meta Pixel          Meta Pixel         Customer DB                   │
│    fires:              fires:             (14K emails)                  │
│    PageView            FirstNote ★                                      │
└─────────┬─────────────────┬────────────────────┬───────────────────────┘
          │                 │                    │
          ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     Meta Ads Platform                                   │
│                                                                         │
│   Receives:                        Uses:                                │
│   • Pixel events (FirstNote)       • Optimize delivery toward           │
│   • Exclusion audiences              users likely to FirstNote          │
│   • Campaign/ad set/ad configs     • Auto-distribute budget             │
│   • Automated rules                • Enforce kill rules                 │
│                                                                         │
│   ┌────────────────┐  ┌────────────────┐  ┌────────────────────┐       │
│   │ Scale: Winners │  │ Farm: Testing  │  │ Q126 Lead Forms    │       │
│   │ $200/day       │  │ $150/day       │  │ (untouched)        │       │
│   │ 5 proven ads   │  │ 24 test ads    │  │                    │       │
│   │ CpFN $62-99    │  │ billing + early│  │                    │       │
│   └────────────────┘  └────────────────┘  └────────────────────┘       │
│                                                                         │
│   Exclusions:                                                           │
│   • CRM list (manual upload)                                            │
│   • Stripe customers (auto-synced daily) ◀──────────┐                  │
│                                                      │                  │
└──────────────────────────────▲───────────────────────┼──────────────────┘
                               │                       │
                    reads performance          pushes exclusions
                    creates campaigns          pulls customer emails
                    manages ad status          hashes + uploads
                               │                       │
┌──────────────────────────────┴───────────────────────┴──────────────────┐
│                      Ads Engine Harness                                  │
│                      /ads_engine repo                                    │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────┐       │
│   │  Meta Marketing API (read + write)                          │       │
│   │  • Pull ad-level insights filtered to FirstNote             │       │
│   │  • Rank ads by CpFN                                         │       │
│   │  • Create/pause/archive campaigns programmatically          │       │
│   │  • Set targeting, budgets, automated rules                  │       │
│   └─────────────────────────────────────────────────────────────┘       │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────┐       │
│   │  Stripe Exclusion Sync (daily cron)                         │       │
│   │  • Pulls all customer emails from Stripe API                │       │
│   │  • SHA256 hashes → uploads to Meta Custom Audience          │       │
│   │  • scripts/sync-stripe-exclusions.py                        │       │
│   └─────────────────────────────────────────────────────────────┘       │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────┐       │
│   │  Creative Intelligence Loop (METHODOLOGY.md)                │       │
│   │  Regress → Learn → Generate → Review → Deploy → Measure    │       │
│   │  (regression model not yet connected to live campaigns)     │       │
│   └─────────────────────────────────────────────────────────────┘       │
│                                                                         │
│   Credentials:                                                          │
│   • Meta: System User token (ads_management + ads_read)                 │
│   • Stripe: rk_live key from jotbill_crm/.env                          │
│   • Ad Account: act_1582817295627677                                    │
│   • Pixel: 1625233994894344                                             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘

Data flow:
  User completes first note
    → Pixel fires FirstNote event to Meta
    → Meta optimizes delivery toward similar users
    → Harness pulls performance data via API
    → Harness ranks ads, promotes winners, kills losers
    → Stripe sync excludes existing customers daily
    → Regression model (future) decomposes WHY ads win
```
