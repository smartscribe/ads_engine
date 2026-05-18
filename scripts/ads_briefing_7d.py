"""Generate the printable 7-day HTML briefing from raw-7d-2026-05-11.json.

Scope: All 99 ads, single campaign "Nate figuring shit out" (NFSO).
Primary KPIs: CpPurchase (spend / canonical purchase count) and ROAS (attributed value / spend).
Decomposition (FN/SU/Cal) is context only, not the ranking metric.
"""
from __future__ import annotations

import json
from html import escape
from pathlib import Path

RAW = Path("data/ads-reports/raw-7d-2026-05-11.json")
OUT = Path("data/ads-reports/briefing-7d-2026-05-11.html")

PURCH_KEY = "offsite_conversion.custom.1604667127308749"
CAL_KEY = "offsite_conversion.custom.26939511482340303"

CSS = """
@page { size: Letter; margin: 0.5in; }
* { box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, sans-serif;
       color: #111; line-height: 1.45; max-width: 900px; margin: 0 auto; padding: 24px 32px 48px; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 24px 0 8px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
h3 { font-size: 13px; margin: 16px 0 6px; text-transform: uppercase; letter-spacing: 0.04em; color: #444; }
.sub { color: #666; font-size: 12px; margin-bottom: 16px; }
.governing { background: #fff4f0; border: 2px solid #c33; padding: 12px 16px; margin: 16px 0; }
.governing strong { color: #c33; }
.callout { background: #f0f6ff; border-left: 4px solid #06c; padding: 10px 14px; margin: 12px 0; font-size: 13px; }
.warning { background: #fff6d9; border-left: 4px solid #b07900; padding: 10px 14px; margin: 12px 0; font-size: 13px; }
table { width: 100%; border-collapse: collapse; font-size: 11px; margin: 8px 0; }
th, td { text-align: left; padding: 5px 7px; border-bottom: 1px solid #e5e5e5; vertical-align: top; }
th { background: #fafafa; font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: 0.03em; color: #555; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.row-good { background: #e8f7ea; }
.row-dead { background: #fde8e8; }
.lever { margin: 8px 0 8px 20px; }
.lever-title { font-weight: 600; }
.lever-why { color: #555; font-size: 12px; margin-left: 12px; margin-top: 2px; }
.footnote { font-size: 10px; color: #777; margin-top: 24px; }
.tag-kill { background: #fde8e8; color: #a21c1c; font-weight: 700; padding: 1px 6px; border-radius: 3px; font-size: 10px; }
.tag-watch { background: #fff6d9; color: #7a5000; font-weight: 600; padding: 1px 6px; border-radius: 3px; font-size: 10px; }
.tag-feed { background: #e8f7ea; color: #2a6b34; font-weight: 700; padding: 1px 6px; border-radius: 3px; font-size: 10px; }
.tag-inv { background: #f0f0ff; color: #3030aa; font-weight: 600; padding: 1px 6px; border-radius: 3px; font-size: 10px; }
@media print { h2 { page-break-after: avoid; } table { page-break-inside: auto; } tr { page-break-inside: avoid; } }
"""


def get_action(ad, key, field="actions"):
    items = ad.get(field) or []
    vals = [float(x["value"]) for x in items if x.get("action_type") == key]
    return max(vals) if vals else 0.0


def decompose(purch, val, z):
    """Return (fn, su, cal) given aggregate purchase count, value, and CalScheduled count."""
    if purch == 0 or val == 0:
        return 0, 0, int(z)
    cal_val = z * 5
    remaining_val = val - cal_val
    remaining_count = purch - z
    if remaining_count <= 0:
        return 0, 0, int(z)
    fn = max(0, round((remaining_val - 25 * remaining_count) / 125))
    su = int(remaining_count - fn)
    return fn, su, int(z)


def fmt_money(x, cents=False):
    if x is None:
        return "&#8212;"
    if cents or abs(x) < 10:
        return "$%.2f" % x
    return "$%s" % "{:,.0f}".format(x)


def fmt_roas(x):
    if x is None:
        return "&#8212;"
    return "%.2fx" % x


def fmt_pct(x, digits=1):
    if x is None:
        return "&#8212;"
    return ("%.{}f%%".format(digits)) % x


def e(s):
    return escape(str(s))


def build_row(r, row_class=""):
    cls = ' class="%s"' % row_class if row_class else ""
    cppurch = fmt_money(r["cppurch"])
    roas = fmt_roas(r["roas"])
    fn, su, cal = r["fn"], r["su"], r["cal"]
    decomp = "%d FN / %d SU / %d Cal" % (fn, su, cal) if r["purch"] > 0 else "no signal"
    return (
        "<tr%(cls)s>"
        "<td>%(name)s</td>"
        "<td class='num'>%(spend)s</td>"
        "<td class='num'>%(purch)s</td>"
        "<td class='num'>%(cppurch)s</td>"
        "<td class='num'>%(roas)s</td>"
        "<td class='num'>%(ctr)s</td>"
        "<td>%(decomp)s</td>"
        "</tr>"
    ) % {
        "cls": cls,
        "name": e(r["name"]),
        "spend": fmt_money(r["spend"]),
        "purch": "%d" % r["purch"] if r["purch"] > 0 else "0",
        "cppurch": cppurch,
        "roas": roas,
        "ctr": fmt_pct(r["ctr"]),
        "decomp": decomp,
    }


def main():
    data = json.loads(RAW.read_text())

    # Per-ad parse
    ad_results = []
    for ad in data:
        spend = float(ad.get("spend", 0) or 0)
        purch = get_action(ad, PURCH_KEY)
        val = get_action(ad, PURCH_KEY, "action_values")
        z = get_action(ad, CAL_KEY)
        fn, su, cal = decompose(purch, val, z)
        cppurch = spend / purch if purch > 0 else None
        roas = val / spend if (spend > 0 and val > 0) else None
        ad_results.append({
            "name": ad.get("ad_name", ""),
            "adset": ad.get("adset_name", ""),
            "spend": spend,
            "purch": int(purch),
            "val": val,
            "fn": fn,
            "su": su,
            "cal": cal,
            "cppurch": cppurch,
            "roas": roas,
            "ctr": float(ad.get("ctr", 0) or 0),
            "impressions": int(ad.get("impressions", 0) or 0),
        })

    ad_results.sort(key=lambda x: -x["spend"])

    # Account totals
    total_spend = sum(r["spend"] for r in ad_results)
    total_purch = sum(r["purch"] for r in ad_results)
    total_val = sum(r["val"] for r in ad_results)
    total_z = sum(r["cal"] for r in ad_results)
    fn_all, su_all, cal_all = decompose(total_purch, total_val, total_z)
    cppurch_all = total_spend / total_purch if total_purch > 0 else None
    roas_all = total_val / total_spend if total_spend > 0 else None

    # Main table (spend > $50)
    main_rows = []
    for r in ad_results:
        if r["spend"] < 50:
            continue
        if r["purch"] > 0 and r["cppurch"] and r["cppurch"] < 100:
            row_class = "row-good"
        elif r["purch"] == 0 and r["spend"] > 200:
            row_class = "row-dead"
        else:
            row_class = ""
        main_rows.append(build_row(r, row_class))

    all_rows = [build_row(r) for r in ad_results]

    # Governing: find the worst and best by ROAS among ads with signal
    with_signal = [r for r in ad_results if r["purch"] > 0 and r["roas"] is not None]
    best = sorted(with_signal, key=lambda x: x["roas"] or 0)[-1] if with_signal else None
    worst = sorted(with_signal, key=lambda x: x["roas"] or 999)[0] if with_signal else None

    html = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>JotPsych Meta Ads -- NFSO -- 7-day Briefing (May 4-10 2026)</title>
<style>{css}</style>
</head>
<body>

<h1>JotPsych Meta Ads -- NFSO Briefing</h1>
<div class="sub">Window: May 4-10, 2026 &middot; {spend} spend &middot; {purch} canonical purchases &middot; {roas} blended ROAS &middot; Generated 2026-05-11</div>

<div class="governing">
<strong>Governing finding:</strong> The account spent {spend} and returned {val} in tracked value this week, a blended ROAS of <strong>{roas}</strong> and CpPurchase of <strong>{cppurch}</strong>. One ad, <strong>{worst_name}</strong>, consumed {worst_spend} ({worst_pct}% of budget) and returned {worst_val} (ROAS {worst_roas}). The best performer, <strong>{best_name}</strong>, returned {best_val} on {best_spend} (ROAS {best_roas}, CpPurchase {best_cpp}). Reallocating the worst ad's budget to the best would more than double the account's effective ROAS. No formal kill/scale thresholds are set yet for the Purchase KPI; the structural lever below proposes them.
</div>

<div class="callout">
<strong>Campaign structure:</strong> All 99 active ads run inside one campaign, "Nate figuring shit out" (NFSO, id 120245858870520548). The old Farm / Scale routing is gone. Ad names carry a prefix that encodes creative type (NFSo:, AJ:, AN:, etc.).
</div>

<h2>Account snapshot (May 4-10)</h2>
<table>
<tr><th>Metric</th><th class="num">Value</th></tr>
<tr><td>Total spend</td><td class="num"><strong>{spend}</strong></td></tr>
<tr><td>Canonical purchases (bundled)</td><td class="num"><strong>{purch}</strong></td></tr>
<tr><td>Attributed value (canonical CC)</td><td class="num">{val}</td></tr>
<tr><td>Blended ROAS</td><td class="num"><strong>{roas}</strong></td></tr>
<tr><td>CpPurchase (blended)</td><td class="num"><strong>{cppurch}</strong></td></tr>
<tr><td>Decomposed: FirstNote est.</td><td class="num">{fn} &nbsp;<span style="color:#888;font-size:10px">(context only)</span></td></tr>
<tr><td>Decomposed: SignUpConfirm est.</td><td class="num">{su}</td></tr>
<tr><td>Decomposed: CalendarScheduled</td><td class="num">{cal}</td></tr>
</table>

<div class="callout">
<strong>How purchases are counted:</strong> The canonical Purchase CC (id 1604667127308749) bundles three events into a single pixel signal: FirstNote ($150), SignUpConfirm ($25), CalendarScheduled ($5). CpPurchase and ROAS are computed directly from that CC's count and value fields. The decomposition (FN/SU/Cal column) is derived via the ATTRIBUTION.md method and shown as context only.
</div>

<h2>Ad performance (spend above $50)</h2>
<div class="sub">Green: CpPurchase below $100. Red: zero purchases and spend above $200.</div>
<table>
<tr>
  <th>Ad Name</th>
  <th class="num">Spend</th>
  <th class="num">Purchases</th>
  <th class="num">CpPurchase</th>
  <th class="num">ROAS</th>
  <th class="num">CTR</th>
  <th>Decomp (FN/SU/Cal)</th>
</tr>
{main_table}
</table>

<h2>Levers (prioritized)</h2>

<h3>1. Kill</h3>
<div class="lever">
  <span class="lever-title"><span class="tag-kill">KILL</span> NFSo: jotstart-first-payer-approved-feed ($2,912 spend, ROAS 0.04x, CpPurchase $243).</span>
  <div class="lever-why">42% of the week's budget. $120 in tracked value on $2,912 spent. Every dollar in produced 4 cents out. Pausing this one ad and redeploying its budget to the top two performers would increase account ROAS by roughly 3x. This is the highest-leverage action available right now.</div>
</div>

<h3>2. Feed</h3>
<div class="lever">
  <span class="lever-title"><span class="tag-feed">FEED</span> NFSo: WILDCARD_SPEED_DATING_V1 ($846, ROAS 0.80x, CpPurchase $70).</span>
  <div class="lever-why">Best performer in the account on both CpPurchase and ROAS. $675 of attributed value on $846 spent. Raise daily budget 1.5-2x and review in 5 days. This is the clear scale candidate.</div>
</div>
<div class="lever">
  <span class="lever-title"><span class="tag-feed">FEED</span> AJ: Audit Letter Arrives. You're Ready ($626, ROAS 0.68x, CpPurchase $89).</span>
  <div class="lever-why">Second-best ROAS, and 6.8% CTR. $405 of attributed value on $626 spent. Small purchase count (7) means the ROAS estimate will stabilize as it accrues more signal. Let it run; do not cap it.</div>
</div>

<h3>3. Watch</h3>
<div class="lever">
  <span class="lever-title"><span class="tag-watch">WATCH</span> NFSo: salt-68-notes-behind-feed ($425 spend, 5.7% CTR, 0 purchases).</span>
  <div class="lever-why">No purchase signal yet, but 5.7% CTR is high relative to account baseline. Run to $600 total spend before any verdict. The click-to-purchase gap may be a landing page or post-click issue rather than a creative failure.</div>
</div>

<h3>4. Investigate</h3>
<div class="lever">
  <span class="lever-title"><span class="tag-inv">INVESTIGATE</span> NFSo: AJ: Audit Letter Arrives. You're Ready - Copy ($187, 10.2% CTR, 0 purchases).</span>
  <div class="lever-why">Highest CTR in the account. Copy variant of a proven creative with only $187 of spend. Needs more runway before a verdict. Watch for first purchase signal around $300 spend.</div>
</div>
<div class="lever">
  <span class="lever-title"><span class="tag-inv">INVESTIGATE</span> NFSo: UGC_LISTENING_V1 ($98, 9.6% CTR, 0 purchases) and NFSo: Farm: Nate Podcast 4 ($60, 7.4% CTR, 0 purchases).</span>
  <div class="lever-why">Both have strong CTR with minimal spend. Neither has enough data to call. Let each reach $250 before evaluating.</div>
</div>

<h3>5. Structural: set kill and scale thresholds for CpPurchase</h3>
<div class="lever">
  <span class="lever-title">Proposed thresholds:</span>
  <div class="lever-why">
    KILL: CpPurchase above $200 after at least 5 purchases OR at least $500 spend with 0 purchases.<br>
    SCALE: CpPurchase below $100 after at least 3 purchases.<br>
    HOLD: everything else.<br>
    These would have killed jotstart-first-payer-approved-feed (12 purchases at $243) and scaled WILDCARD_SPEED_DATING_V1 (12 purchases at $70) this week. Nate to confirm before the next run.
  </div>
</div>

<h2>Signal quality</h2>
<div class="callout">
The canonical Purchase CC is firing cleanly: 47 purchases, $1,485 attributed value across the account. The CalendarScheduled probe CC (26939511482340303) returned 22 events, enabling per-ad decomposition. ROAS and CpPurchase are read directly from the API and are not derived. The decomposition (FN/SU/Cal) is approximate: fractional FN estimates are rounded, which can shift individual-ad decomps by 1 unit. Account-level decomposition (6 FN, 19 SU, 22 Cal) is more reliable since rounding errors partially cancel.
</div>

<h2>Appendix: all ads by spend</h2>
<table>
<tr>
  <th>Ad Name</th>
  <th class="num">Spend</th>
  <th class="num">Purchases</th>
  <th class="num">CpPurchase</th>
  <th class="num">ROAS</th>
  <th class="num">CTR</th>
  <th>Decomp (FN/SU/Cal)</th>
</tr>
{all_table}
</table>

<div class="footnote">
<strong>Source:</strong> Meta Marketing API ad-level insights for 2026-05-04 to 2026-05-10. Raw data: data/ads-reports/raw-7d-2026-05-11.json.<br><br>
<strong>KPI method:</strong> CpPurchase = spend / canonical CC count (offsite_conversion.custom.1604667127308749). ROAS = canonical CC value / spend. Both read directly from the API (actions and action_values fields), not derived from decomposition. max() used per action_type to avoid double-counting duplicate rows.<br><br>
<strong>Decomposition method:</strong> ATTRIBUTION.md. CalendarScheduled probe CC 26939511482340303 provides Z count. FN = round((value - 5Z - 25*(n-Z)) / 125). Shown as context; not used for ranking or verdicts.<br><br>
<strong>Thresholds:</strong> Not yet confirmed for the NFSO / Purchase KPI. Proposed: KILL at CpPurchase above $200 (5+ purchases or $500+ spend with 0), SCALE at CpPurchase below $100 (3+ purchases).
</div>

</body>
</html>
""".format(
        css=CSS,
        spend=fmt_money(total_spend),
        purch="%d" % int(total_purch),
        val=fmt_money(total_val),
        roas=fmt_roas(roas_all),
        cppurch=fmt_money(cppurch_all),
        fn=fn_all,
        su=su_all,
        cal=cal_all,
        main_table="\n".join(main_rows),
        all_table="\n".join(all_rows),
        worst_name=worst["name"] if worst else "N/A",
        worst_spend=fmt_money(worst["spend"]) if worst else "N/A",
        worst_pct="%d" % int(100 * worst["spend"] / total_spend) if worst else "0",
        worst_val=fmt_money(worst["val"]) if worst else "N/A",
        worst_roas=fmt_roas(worst["roas"]) if worst else "N/A",
        best_name=best["name"] if best else "N/A",
        best_spend=fmt_money(best["spend"]) if best else "N/A",
        best_val=fmt_money(best["val"]) if best else "N/A",
        best_roas=fmt_roas(best["roas"]) if best else "N/A",
        best_cpp=fmt_money(best["cppurch"]) if best else "N/A",
    )

    OUT.write_text(html)
    print("Wrote %s" % OUT)


if __name__ == "__main__":
    main()
