"""Generate the printable HTML briefing from analysis-10d-*.json.

Scope: Farm + Scale campaigns only. LGF / Test / Retargeting / Q226 excluded
by project rule.
"""
from __future__ import annotations

import json
from datetime import date
from html import escape
from pathlib import Path

ANALYSIS = Path("data/ads-reports/analysis-10d-2026-04-14.json")
OUT = Path("data/ads-reports/briefing-10d-2026-04-14.html")

CSS = """
@page { size: Letter; margin: 0.5in; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, sans-serif;
       color: #111; line-height: 1.45; max-width: 900px; margin: 0 auto; padding: 24px 32px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 24px 0 8px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
h3 { font-size: 13px; margin: 16px 0 6px; text-transform: uppercase; letter-spacing: 0.04em; color: #444; }
.sub { color: #666; font-size: 12px; margin-bottom: 16px; }
.scope { background: #f4f4f4; border: 1px dashed #aaa; padding: 8px 12px; margin: 12px 0 16px; font-size: 11px; color: #555; }
.scope strong { color: #111; }
.governing { background: #fff4f0; border-left: 4px solid #c33; padding: 12px 16px; margin: 16px 0; }
.governing strong { color: #c33; }
.callout { background: #f0f6ff; border-left: 4px solid #06c; padding: 10px 14px; margin: 12px 0; font-size: 13px; }
.warning { background: #fff6d9; border-left: 4px solid #b07900; padding: 10px 14px; margin: 12px 0; font-size: 13px; }
table { width: 100%; border-collapse: collapse; font-size: 11px; margin: 8px 0; }
th, td { text-align: left; padding: 5px 7px; border-bottom: 1px solid #e5e5e5; vertical-align: top; }
th { background: #fafafa; font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.03em; color: #555; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.verdict-SCALE  { background: #e8f7ea; color: #2a6b34; font-weight: 700; padding: 1px 6px; border-radius: 3px; }
.verdict-KILL   { background: #fde8e8; color: #a21c1c; font-weight: 700; padding: 1px 6px; border-radius: 3px; }
.verdict-HOLD   { background: #f3f3f3; color: #555;   font-weight: 600; padding: 1px 6px; border-radius: 3px; }
.verdict-INSUFFICIENT_N { background: #f3f3f3; color: #888; font-weight: 500; padding: 1px 6px; border-radius: 3px; font-size: 9px; }
.lever { margin: 8px 0 8px 20px; }
.lever-title { font-weight: 600; }
.lever-why { color: #555; font-size: 12px; margin-left: 12px; margin-top: 2px; }
.footnote { font-size: 10px; color: #777; margin-top: 24px; }
@media print { h2 { page-break-after: avoid; } table { page-break-inside: auto; } tr { page-break-inside: avoid; } }
"""


def fmt_money(x, cents=False):
    if x is None: return "—"
    if cents or abs(x) < 10:
        return f"${x:,.2f}"
    return f"${x:,.0f}"


def fmt_pct(x, digits=2):
    if x is None: return "—"
    return f"{x:.{digits}f}%"


def verdict_badge(v):
    return f'<span class="verdict-{v}">{v.replace("_", " ")}</span>'


def main():
    d = json.loads(ANALYSIS.read_text())
    acct = d["account"]
    ads = d["ads"]
    camps = d["campaigns"]
    th = d["thresholds"]
    scope = d["scope"]

    scales = [a for a in ads if a["verdict"] == "SCALE"]
    kills = [a for a in ads if a["verdict"] == "KILL"]
    holds = [a for a in ads if a["verdict"] == "HOLD"]

    # Trending scale: ≥2 FN, raw CpFN < $150 (clearly beating blended), HOLD
    trend_scale = sorted(
        [a for a in holds if a["first_notes"] >= 2 and (a["raw_cpfn"] or 999) < 150],
        key=lambda x: x["raw_cpfn"] or 999,
    )
    # Trending kill: 0 FN, spend ≥ $150, p_above_kill ≥ 0.55
    trend_kill = sorted(
        [a for a in holds if a["first_notes"] == 0 and a["spend"] >= 150 and a["p_above_kill"] >= 0.55],
        key=lambda x: -x["p_above_kill"],
    )
    # High-CTR candidates not yet confirmed (Farm ads trending interesting)
    high_ctr = sorted(
        [a for a in ads if a["ctr_pct"] >= 5.0 and a["spend"] >= 50 and a["verdict"] == "HOLD"],
        key=lambda x: -x["ctr_pct"],
    )

    def row(a, cols):
        out = [f"<td>{escape(a['ad_name'])}</td>"]
        if "campaign" in cols:
            out.append(f"<td>{escape(a['campaign_name'])}</td>")
        if "spend" in cols:
            out.append(f"<td class='num'>{fmt_money(a['spend'])}</td>")
        if "ctr" in cols:
            out.append(f"<td class='num'>{fmt_pct(a['ctr_pct'])}</td>")
        if "freq" in cols:
            out.append(f"<td class='num'>{a['frequency']:.2f}</td>")
        if "fn" in cols:
            out.append(f"<td class='num'>{a['first_notes']}</td>")
        if "raw" in cols:
            out.append(f"<td class='num'>{fmt_money(a['raw_cpfn'], cents=True)}</td>")
        if "median" in cols:
            out.append(f"<td class='num'>{fmt_money(a.get('cost_median'))}</td>")
        if "ci" in cols:
            out.append(f"<td class='num'>{fmt_money(a.get('cost_ci90_lo'))}–{fmt_money(a.get('cost_ci90_hi'))}</td>")
        if "p_scale" in cols:
            out.append(f"<td class='num'>{a.get('p_below_scale', 0):.2f}</td>")
        if "p_kill" in cols:
            out.append(f"<td class='num'>{a.get('p_above_kill', 0):.2f}</td>")
        if "verdict" in cols:
            out.append(f"<td>{verdict_badge(a['verdict'])}</td>")
        return f"<tr>{''.join(out)}</tr>"

    def rows(lst, cols):
        return "".join(row(a, cols) for a in lst)

    kill_rows = rows(kills, ["campaign", "spend", "fn", "median", "ci", "p_kill"])
    trend_scale_rows = rows(trend_scale, ["campaign", "spend", "fn", "raw", "median", "ci", "p_scale"])
    trend_kill_rows = rows(trend_kill, ["campaign", "spend", "fn", "median", "ci", "p_kill"])
    high_ctr_rows = rows(high_ctr, ["campaign", "spend", "ctr", "fn", "median"])
    all_rows = rows(sorted(ads, key=lambda x: -x["spend"]), ["campaign", "spend", "fn", "raw", "median", "ci", "verdict"])

    rows_camp = "".join(
        f"<tr><td>{escape(c['campaign_name'])}</td>"
        f"<td class='num'>{c['ads']}</td>"
        f"<td class='num'>{fmt_money(c['spend'])}</td>"
        f"<td class='num'>{c['impressions']:,}</td>"
        f"<td class='num'>{fmt_pct(c['ctr_pct'])}</td>"
        f"<td class='num'>{fmt_money(c['cpm'], cents=True)}</td>"
        f"<td class='num'>{c['first_notes']}</td>"
        f"<td class='num'>{fmt_money(c.get('cpfn'))}</td></tr>"
        for c in camps
    )

    kill_count = len(kills)
    scale_count = len(scales)

    # Governing thought
    if kill_count and not scale_count:
        governing = (
            f"<strong>Governing finding:</strong> One high-confidence kill call, zero scale calls. "
            f"<strong>Scale: Test: KM UGC - Video Concept 1</strong> has spent $334 with zero FirstNotes — posterior median "
            f"CpFN {fmt_money(kills[0]['cost_median'])}, 90% CI {fmt_money(kills[0]['cost_ci90_lo'])}–{fmt_money(kills[0]['cost_ci90_hi'])}, "
            f"P(CpFN&gt;$250)&nbsp;=&nbsp;<strong>{kills[0]['p_above_kill']:.2f}</strong>. Kill it today. "
            f"No ads cleared the 0.8 scale bar — not because creative isn't working, but because the strongest "
            f"candidates only have 2–3 FirstNotes each and the posteriors are still wide. "
            f"The best trending-scale candidate is <strong>AJ: Audit Letter Arrives. You're Ready</strong> "
            f"(3 FN, 12.5% CTR — highest in scope — raw CpFN $96, posterior median $153). "
            f"Another 5–7 days of spend on the top trending ads will likely produce 2–3 confirmed scale calls."
        )
    else:
        governing = "Governing finding: see tables below."

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>JotPsych Meta Ads — Farm + Scale — 10-day Briefing</title>
<style>{CSS}</style>
</head>
<body>

<h1>JotPsych Meta Ads — Farm + Scale Briefing</h1>
<div class="sub">Window: {d['window']['since']} → {d['window']['until']} · Generated {date.today().isoformat()}</div>

<div class="scope">
<strong>Scope:</strong> Farm and Scale campaigns only ({scope['in_scope_ads']} ads, {fmt_money(acct['total_spend'])} spend, {acct['total_first_notes']} FirstNotes).
<strong>Excluded:</strong> {scope['excluded_ads']} ads across {", ".join(scope['excluded_campaigns'])} ({fmt_money(scope['excluded_spend'])} spend excluded, including both LGF winners from the full-account view). These campaigns are out of scope for this analysis by project rule.
</div>

<div class="governing">
{governing}
</div>

<h2>In-scope snapshot</h2>
<table>
<tr><th>Metric</th><th class="num">Value</th></tr>
<tr><td>Ads in scope</td><td class="num">{scope['in_scope_ads']}</td></tr>
<tr><td>Total spend</td><td class="num">{fmt_money(acct['total_spend'])}</td></tr>
<tr><td>Daily pace</td><td class="num">{fmt_money(acct['daily_spend'])}/day</td></tr>
<tr><td>Impressions</td><td class="num">{acct['total_impressions']:,}</td></tr>
<tr><td>CTR</td><td class="num">{fmt_pct(acct['account_ctr_pct'])}</td></tr>
<tr><td>CPM</td><td class="num">{fmt_money(acct['account_cpm'], cents=True)}</td></tr>
<tr><td>FirstNotes</td><td class="num"><strong>{acct['total_first_notes']}</strong></td></tr>
<tr><td>SignUpConfirms</td><td class="num">{acct['total_signups']}</td></tr>
<tr><td>Blended CpFN</td><td class="num"><strong>{fmt_money(acct['account_cpfn'])}</strong></td></tr>
</table>

<div class="callout">
Blended in-scope CpFN {fmt_money(acct['account_cpfn'])} sits inside the project's historical weekly band of $189–$354 (per CLAUDE.md Feb–Mar table). That means the engine is running at the middle of its recent range — not crashing, not breaking out. The leverage is in creative variance: the worst 5 ads in scope spent ~$1,350 and produced 2 FirstNotes combined (~$675/FN), while the best trending ads are doing sub-$120 raw. Kill the bad, feed the good, and the blended number compresses.
</div>

<h2>Campaign rollup</h2>
<table>
<tr><th>Campaign</th><th class="num">Ads</th><th class="num">Spend</th><th class="num">Impr</th><th class="num">CTR</th><th class="num">CPM</th><th class="num">FN</th><th class="num">CpFN</th></tr>
{rows_camp}
</table>

<div class="warning">
<strong>Scale: Winners is still sicker than Farm.</strong> Scale: Winners CpFN $263 vs Farm CpFN $220. That's the second 10-day window running where the promoted "winners" are performing worse than the average Farm ad. Two plausible causes: (1) promotion criteria are eyeballed, not gated on CpFN, and bad promotions slip through, OR (2) Scale audiences are saturating where Farm audiences are fresh. Worth an hour with Adam this week to diagnose. See structural lever below.
</div>

<h2>KILL — {kill_count} ad{"s" if kill_count != 1 else ""}</h2>
<div class="sub">Rule: P(CpFN&gt;$250)&nbsp;&gt;&nbsp;0.8 AND (≥3 FirstNotes OR ≥$200 spent). Data-volume guard is the second clause — protects against 0-FN false positives on small spend.</div>
<table>
<tr><th>Ad</th><th>Campaign</th><th class="num">Spend</th><th class="num">FN</th><th class="num">Median</th><th class="num">90% CI</th><th class="num">P(&gt;$250)</th></tr>
{kill_rows}
</table>

<h2>SCALE — {scale_count} ads</h2>
<div class="sub">Rule: P(CpFN&lt;$100)&nbsp;&gt;&nbsp;0.8 AND ≥2 FirstNotes. No ads cleared the bar this window; see trending scale below for the next most likely promotions.</div>

<h2>Levers — prioritized</h2>

<h3>1. Act now — kill the one confident loser</h3>
<div class="lever"><span class="lever-title">KILL: Scale: Test: KM UGC - Video Concept 1 — save ~$33/day.</span>
<div class="lever-why">Zero FirstNotes on $334 spent at a daily pace of ~$33. Posterior says 80.7% probability CpFN exceeds $250. Even with n-sensitivity guards (≥$200 spent clause), this crosses the kill threshold. 10-day forward save at current pace is ~$330. <strong>Action:</strong> pause the ad today.</div></div>

<h3>2. Watch closely — trending scale ({len(trend_scale)} ads, 3–5 more days)</h3>

<table>
<tr><th>Ad</th><th>Campaign</th><th class="num">Spend</th><th class="num">FN</th><th class="num">Raw CpFN</th><th class="num">Median</th><th class="num">90% CI</th><th class="num">P(&lt;$100)</th></tr>
{trend_scale_rows}
</table>

<div class="lever"><span class="lever-title">Priority: AJ: Audit Letter Arrives. You're Ready.</span>
<div class="lever-why">Strongest combination of data-volume and engagement in the trending set: $287 spent, 3 FirstNotes (raw $96), 12.5% CTR (3x account mean). Bayesian posterior median is $153 — still outside the scale bar because the 90% CI stretches to $340 on small n. Another 5 days of spend should tighten the CI dramatically. <strong>Action:</strong> do not touch; let it accrue data. Revisit in 3 days. This is the most likely next scale call.</div></div>

<div class="lever"><span class="lever-title">Second priority: AI for Progress Notes (the bare "Scale" campaign version).</span>
<div class="lever-why">$71 spent, 2 FirstNotes, raw CpFN $36 — the best raw efficiency in the scope — but only $71 of spend means the posterior is still centered at $135 with wide uncertainty. <strong>Action:</strong> raise this ad set's budget modestly (2x) and revisit in 5 days. If it converts 2–3 more FirstNotes at sub-$80 raw, it's a clear scale.</div></div>

<h3>3. Watch closely — trending kill ({len(trend_kill)} ads, 3–5 more days)</h3>

<table>
<tr><th>Ad</th><th>Campaign</th><th class="num">Spend</th><th class="num">FN</th><th class="num">Median</th><th class="num">90% CI</th><th class="num">P(&gt;$250)</th></tr>
{trend_kill_rows}
</table>

<div class="lever"><span class="lever-title">Set a lifetime cap on AN: 847 Ways payers reject claims and Farm: EHR V2.</span>
<div class="lever-why">Both are at 0 FN with $280 and $182 spent respectively. Bayesian P(CpFN&gt;$250) is 0.78 and 0.70 — under the 0.80 kill bar, but trending. <strong>Action:</strong> cap each at $400 lifetime spend. If they hit that with still 0 FN, kill them in the next review. This preempts another ~$200 of exposure without risking a false-positive kill right now.</div></div>

<h3>4. High-CTR Farm ads with small spend — feed or discontinue?</h3>

<table>
<tr><th>Ad</th><th>Campaign</th><th class="num">Spend</th><th class="num">CTR</th><th class="num">FN</th><th class="num">Median</th></tr>
{high_ctr_rows}
</table>

<div class="lever"><span class="lever-title">Raise budgets on the 5%+ CTR ads that have seen {'<'}$100 spend.</span>
<div class="lever-why">These are screening as engagement winners but haven't seen enough spend to tell whether engagement converts to FirstNotes. Bumping their ad-set budgets by 2x each is a cheap experiment — you spend another ~$200 total across them and buy several more data points per ad. The one to watch is any 5%+ CTR ad with raw CpFN signal; "AJ: Audit Letter Arrives" (above) is the pattern — high CTR that did cash out.</div></div>

<h3>5. Structural — fix the Scale: Winners promotion pipe</h3>

<div class="lever"><span class="lever-title">Gate promotions to Scale with a hard rule: ≥2 FN at raw CpFN ≤ $150 in Farm before promotion.</span>
<div class="lever-why">Current Scale: Winners CpFN is $263 — worse than the Farm's $220. Something in the promotion workflow is letting ads through that shouldn't be there. Under the proposed gate, only two ads in the current Scale: Winners would have qualified (Scale: PDF to Template and Scale: AI for Progress Notes Concept 3), and the other three would still be in Farm collecting more data. Worth a 30-minute conversation with Adam / Matt this week.</div></div>

<div class="lever"><span class="lever-title">Consolidate the "Scale" and "Scale: Winners - Apr 2026" campaigns.</span>
<div class="lever-why">You have both a bare "Scale" campaign (4 ads, $167, CpFN $84) and a "Scale: Winners - Apr 2026" campaign (5 ads, $1,054, CpFN $263). The bare Scale is outperforming the named one on the same KPI. Either retire the bare Scale into a single Scale campaign or repurpose it explicitly. Two Scale campaigns split the learning signal for Meta's auction.</div></div>

<h2>Appendix — all in-scope ads by spend</h2>
<table>
<tr><th>Ad</th><th>Campaign</th><th class="num">Spend</th><th class="num">FN</th><th class="num">Raw CpFN</th><th class="num">Median</th><th class="num">90% CI</th><th>Verdict</th></tr>
{all_rows}
</table>

<div class="footnote">
<strong>Source:</strong> Meta Marketing API ad-level insights for {d['window']['since']}..{d['window']['until']}, queried with <code>fields=[...,actions,conversions,cost_per_conversion]</code>. FirstNote read from <code>conversions</code> field as <code>offsite_conversion.fb_pixel_custom.FirstNote</code>.
<br/><br/>
<strong>Statistical model:</strong> Gamma-Poisson on λ=FN/$. Prior Gamma(α=2, β=2·{fmt_money(th['cpfn_prior_center'])}) calibrated on in-scope (Farm+Scale) blended CpFN.
<br/><br/>
<strong>Decision rules:</strong> {escape(th['rule'])}
<br/><br/>
<strong>Scope:</strong> Farm and Scale campaigns only. {scope['excluded_ads']} ads in {len(scope['excluded_campaigns'])} other campaigns ({fmt_money(scope['excluded_spend'])} spend) were excluded, including the LGF lead-form winners and the "Test: SB Video 1" outlier from the Test campaign. Those are not evaluated here.
<br/><br/>
<strong>False-positive posture:</strong> Data-volume guards (≥3 FN or ≥$200 for KILL, ≥2 FN for SCALE) are calibrated toward false-negative tolerance — better to miss a verdict by a week than burn credibility with a wrong call.
</div>

</body>
</html>
"""
    OUT.write_text(html)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
