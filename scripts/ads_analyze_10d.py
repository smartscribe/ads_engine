"""
Analyze the raw 10d Meta pull and produce a structured analysis JSON.

Primary KPI: FirstNote custom event (category OTHER on WebApp Actions dataset).
Meta returns it in the `conversions` field as
  action_type='offsite_conversion.fb_pixel_custom.FirstNote'
NOT in the `actions` field. This was the subtle miss in the first run.

Bayesian model: Gamma-Poisson on λ=FN/$. Prior calibrated on account-wide
10d blended CpFN with weak weight (α=2). Decision rules:
  - KILL  if P(CpFN > $250) > 0.8
  - SCALE if P(CpFN < $100) > 0.8
  - HOLD  otherwise
  - INSUFFICIENT_N if spend < $50 AND fn == 0 (pre-empts noise)

Secondary signal: lead-form leads (lead_grouped in `actions` field), used as
diagnostic and for ads in LGF campaigns that don't have FN fires.
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from statistics import mean

from scipy import stats  # type: ignore

RAW = Path("data/ads-reports/raw-10d-2026-04-14.json")
OUT_JSON = Path("data/ads-reports/analysis-10d-2026-04-14.json")

SINCE = "2026-04-04"
UNTIL = "2026-04-13"

# Hard scope: only Farm and Scale campaigns. Everything else (LGF, Test,
# Retargeting, Q226) is excluded by explicit decision — Nate doesn't want
# lead-form or one-off test campaigns in this analysis.
SCOPE_PREFIXES = ("Farm", "Scale")

KILL_CPFN = 250.0
SCALE_CPFN = 100.0

# LGF ads drive to Meta's lead form, not to the website — FirstNote cannot fire
# on them by design. Evaluate them on cost-per-lead with a CPL threshold derived
# from the Mar 11 lead-form experiment baseline (~$63/lead).
KILL_CPL = 150.0
SCALE_CPL = 70.0

FN_ACTION_TYPE = "offsite_conversion.fb_pixel_custom.FirstNote"
SIGNUP_ACTION_TYPE = "offsite_conversion.fb_pixel_custom.SignUpConfirm"


def is_lgf(ad: dict) -> bool:
    return "LGF" in (ad.get("campaign_name") or "")


def parse_row(row: dict) -> dict:
    spend = float(row.get("spend", 0) or 0)
    impressions = int(row.get("impressions", 0) or 0)
    reach = int(row.get("reach", 0) or 0)
    clicks = int(row.get("clicks", 0) or 0)
    freq = float(row.get("frequency", 0) or 0)
    cpm = float(row.get("cpm", 0) or 0)
    ctr = float(row.get("ctr", 0) or 0)

    # FirstNote from the `conversions` field (NOT `actions`)
    first_notes = 0
    signups = 0
    for conv in row.get("conversions") or []:
        at = conv.get("action_type", "")
        v = int(float(conv.get("value", 0) or 0))
        if at == FN_ACTION_TYPE:
            first_notes += v
        elif at == SIGNUP_ACTION_TYPE:
            signups += v

    # Lead-form leads from `actions` field
    leads = 0
    lpv = 0
    link_clicks = 0
    for a in row.get("actions") or []:
        t = a.get("action_type", "")
        v = int(float(a.get("value", 0) or 0))
        if t == "onsite_conversion.lead_grouped":
            leads = max(leads, v)
        elif t in ("landing_page_view", "omni_landing_page_view"):
            lpv = max(lpv, v)
        elif t == "link_click":
            link_clicks = max(link_clicks, v)

    return {
        "ad_id": row.get("ad_id"),
        "ad_name": row.get("ad_name"),
        "campaign_name": row.get("campaign_name"),
        "adset_name": row.get("adset_name"),
        "spend": round(spend, 2),
        "impressions": impressions,
        "reach": reach,
        "frequency": round(freq, 2),
        "clicks": clicks,
        "link_clicks": link_clicks,
        "lpv": lpv,
        "leads": leads,
        "first_notes": first_notes,
        "signups": signups,
        "ctr_pct": round(ctr, 3),
        "cpm": round(cpm, 2),
        "cpc": round((spend / clicks) if clicks else 0, 2),
        "raw_cpfn": round(spend / first_notes, 2) if first_notes else None,
        "raw_cpl": round(spend / leads, 2) if leads else None,
        "lpv_rate_pct": round(lpv / link_clicks * 100, 2) if link_clicks else None,
    }


def gamma_poisson(conversions: int, spend: float, prior_c: float, prior_spend: float,
                  kill: float, scale: float) -> dict:
    """Gamma-Poisson posterior on λ=conversions/$. Returns cost/conv median, 90% CI, p(kill), p(scale)."""
    a = prior_c + conversions
    b = prior_spend + spend
    rv = stats.gamma(a=a, scale=1 / b)
    lam_lo, lam_med, lam_hi = rv.ppf([0.05, 0.5, 0.95])
    cost_median = 1 / lam_med if lam_med else None
    cost_lo = 1 / lam_hi if lam_hi else None
    cost_hi = 1 / lam_lo if lam_lo else None
    p_kill = float(rv.cdf(1 / kill))
    p_scale = float(rv.sf(1 / scale))
    return {
        "cost_median": round(cost_median, 2) if cost_median else None,
        "cost_ci90_lo": round(cost_lo, 2) if cost_lo else None,
        "cost_ci90_hi": round(cost_hi, 2) if cost_hi else None,
        "p_above_kill": round(p_kill, 3),
        "p_below_scale": round(p_scale, 3),
    }


def classify(ad: dict) -> str:
    lgf = is_lgf(ad)
    conv = ad["leads"] if lgf else ad["first_notes"]
    spend = ad["spend"]

    # INSUFFICIENT_N: spend too low to trust any verdict
    if spend < 50 and conv == 0:
        return "INSUFFICIENT_N"

    p_kill = ad.get("p_above_kill", 0)
    p_scale = ad.get("p_below_scale", 0)

    # SCALE: high posterior confidence AND at least 2 conversions (no tiny-n scale)
    if p_scale > 0.8 and conv >= 2:
        return "SCALE"

    # KILL: high posterior confidence AND (≥3 conversions OR ≥$200 spent)
    # This protects against the "0 conversions, small spend" false-positive trap
    # while still flagging serious burn.
    if p_kill > 0.8 and (conv >= 3 or spend >= 200):
        return "KILL"

    return "HOLD"


def in_scope(ad: dict) -> bool:
    cn = ad.get("campaign_name") or ""
    return any(cn.startswith(p) for p in SCOPE_PREFIXES)


def main():
    raw = json.loads(RAW.read_text())
    all_ads = [parse_row(r) for r in raw]
    excluded = [a for a in all_ads if not in_scope(a)]
    ads = [a for a in all_ads if in_scope(a)]

    total_spend = sum(a["spend"] for a in ads)
    total_fn = sum(a["first_notes"] for a in ads)
    total_signups = sum(a["signups"] for a in ads)
    total_leads = sum(a["leads"] for a in ads)
    total_lpv = sum(a["lpv"] for a in ads)
    total_clicks = sum(a["clicks"] for a in ads)
    total_impressions = sum(a["impressions"] for a in ads)

    account_cpfn = (total_spend / total_fn) if total_fn else None
    account_cpl = (total_spend / total_leads) if total_leads else None

    # Bayesian prior (CpFN): weak, centered on in-scope Farm+Scale CpFN
    cpfn_prior_center = (total_spend / total_fn) if total_fn else 200.0
    prior_fn = 2.0
    prior_spend_fn = 2.0 * cpfn_prior_center

    for ad in ads:
        b = gamma_poisson(
            ad["first_notes"], ad["spend"], prior_fn, prior_spend_fn,
            kill=KILL_CPFN, scale=SCALE_CPFN,
        )
        ad["signal"] = "cpfn"
        ad["threshold_kill"] = KILL_CPFN
        ad["threshold_scale"] = SCALE_CPFN
        ad.update(b)
        ad["verdict"] = classify(ad)

    # Campaign rollup
    camp_rollup: dict[str, dict] = {}
    for a in ads:
        c = camp_rollup.setdefault(a["campaign_name"], {
            "campaign_name": a["campaign_name"],
            "ads": 0, "spend": 0.0, "impressions": 0, "clicks": 0,
            "first_notes": 0, "signups": 0, "leads": 0, "lpv": 0,
        })
        c["ads"] += 1
        c["spend"] += a["spend"]
        c["impressions"] += a["impressions"]
        c["clicks"] += a["clicks"]
        c["first_notes"] += a["first_notes"]
        c["signups"] += a["signups"]
        c["leads"] += a["leads"]
        c["lpv"] += a["lpv"]
    for c in camp_rollup.values():
        c["ctr_pct"] = round(c["clicks"] / c["impressions"] * 100, 2) if c["impressions"] else 0
        c["cpm"] = round(c["spend"] / c["impressions"] * 1000, 2) if c["impressions"] else 0
        c["cpfn"] = round(c["spend"] / c["first_notes"], 2) if c["first_notes"] else None
        c["cpl"] = round(c["spend"] / c["leads"], 2) if c["leads"] else None
        c["spend"] = round(c["spend"], 2)

    # Promotion candidates: high CTR Farm ads with few/no FN (moving them to a
    # FirstNote-optimized ad set is a leverage bet, not a guaranteed win).
    promotes = [a for a in ads
                if a["ctr_pct"] >= 5.0 and a["spend"] >= 50
                and a["verdict"] not in ("SCALE", "KILL")]
    promotes.sort(key=lambda a: -a["ctr_pct"])

    # LPV/click tracking anomalies: unchanged
    anomaly = [a for a in ads if a["link_clicks"] >= 200 and
               a.get("lpv_rate_pct") is not None and a["lpv_rate_pct"] < 15]

    analysis = {
        "window": {"since": SINCE, "until": UNTIL, "days": 10},
        "scope": {
            "prefixes": list(SCOPE_PREFIXES),
            "in_scope_ads": len(ads),
            "excluded_ads": len(excluded),
            "excluded_campaigns": sorted(set(a["campaign_name"] for a in excluded)),
            "excluded_spend": round(sum(a["spend"] for a in excluded), 2),
        },
        "account": {
            "total_spend": round(total_spend, 2),
            "total_impressions": total_impressions,
            "total_clicks": total_clicks,
            "total_lpv": total_lpv,
            "total_leads": total_leads,
            "total_first_notes": total_fn,
            "total_signups": total_signups,
            "account_ctr_pct": round(total_clicks / total_impressions * 100, 3) if total_impressions else 0,
            "account_cpm": round(total_spend / total_impressions * 1000, 2) if total_impressions else 0,
            "account_cpfn": round(account_cpfn, 2) if account_cpfn else None,
            "account_cpl": round(account_cpl, 2) if account_cpl else None,
            "daily_spend": round(total_spend / 10, 2),
        },
        "thresholds": {
            "kill_cpfn": KILL_CPFN,
            "scale_cpfn": SCALE_CPFN,
            "cpfn_prior_center": round(cpfn_prior_center, 2),
            "rule": (
                "KILL if P(CpFN>$250)>0.8 AND (fn>=3 OR spend>=$200); "
                "SCALE if P(CpFN<$100)>0.8 AND fn>=2. "
                "INSUFFICIENT_N if spend<$50 AND fn==0."
            ),
        },
        "campaigns": sorted(list(camp_rollup.values()), key=lambda x: -x["spend"]),
        "ads": sorted(ads, key=lambda x: -x["spend"]),
        "promotes": promotes,
        "anomalies": anomaly,
    }
    OUT_JSON.write_text(json.dumps(analysis, indent=2))
    print(f"Wrote {OUT_JSON}")
    return analysis


if __name__ == "__main__":
    main()
