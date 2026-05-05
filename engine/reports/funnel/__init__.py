"""Signup funnel reporting harness — all L6M cohorts, not channel-filtered.

Pull → Compute → QC → Render pipeline for weekly conversion-weighted pipeline,
forecast-vs-actual, paid channel split, and biweekly discovery attribution.
Sourced from Metabase (Smartscribe Analytics Supabase).

Entrypoint: ``python3 -m engine.reports.funnel.run``
"""
