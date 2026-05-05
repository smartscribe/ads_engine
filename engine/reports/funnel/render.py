"""Model JSON → HTML deliverable.

Every number in the output HTML traces back to model.json. The render function
serializes model data into JavaScript literals consumed by Chart.js. No
computation here — if it requires math, it belongs in compute.py.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from .config import (
    ARPU_MONTHLY, CHANNEL_COLORS, CHANNEL_LABELS, MODEL_PATH,
    PAID_CHANNELS, REST_LABEL, RENDER_PATH,
)


def _fmt_mrr(x: float) -> str:
    return f"${x:,.0f}"


def render(model: Dict[str, Any], out_path: Path = RENDER_PATH) -> Path:
    # ----- Precompute hero cards -----
    mature_weekly = [w for w in model["weekly"] if w["week"] < model["meta"]["incomplete_from"]]
    if mature_weekly:
        best = max(mature_weekly, key=lambda w: w["expected"])
        avg_expected = sum(w["expected"] for w in mature_weekly) / len(mature_weekly)
    else:
        best = {"week": "—", "expected": 0.0, "signups": 0, "mrr": 0.0}
        avg_expected = 0.0
    avg_mrr = avg_expected * ARPU_MONTHLY

    err = model.get("error_summary") or {}
    mae_conv = err.get("mae_conversions", 0.0)
    mae_mrr = err.get("mae_mrr", 0.0)
    mape = err.get("mape_pct")
    mape_str = f"{mape:.0f}%" if mape is not None else "—"
    bias_conv = err.get("bias_conversions", 0.0)
    bias_sign = "over" if bias_conv > 0 else ("under" if bias_conv < 0 else "neutral")

    # ----- Serialize model pieces into JS literals -----
    weekly_js = json.dumps(model["weekly"])
    weekly_chan_js = json.dumps(model["weekly_by_channel"])
    per_note_js = json.dumps(model["per_note"])
    biweekly_js = json.dumps(model["biweekly_discovery"])

    # Channel color / label maps for the paid split and full discovery map.
    paid_channels = model["meta"]["channel_order"]  # e.g. [google, facebook, linkedin, rest]
    paid_js = json.dumps([
        {"key": ch, "label": CHANNEL_LABELS.get(ch, ch), "color": CHANNEL_COLORS.get(ch, "#888")}
        for ch in paid_channels
    ])
    disc_channels = model["meta"]["discovery_channels_order"]
    disc_js = json.dumps([
        {"key": ch, "label": CHANNEL_LABELS.get(ch, ch), "color": CHANNEL_COLORS.get(ch, "#888")}
        for ch in disc_channels
    ])

    meta = model["meta"]
    cohort = model["cohort"]

    html = _TEMPLATE.format(
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        arpu=ARPU_MONTHLY,
        cohort_total=cohort["total"],
        cohort_active=cohort["active"],
        overall_base_pct=f"{model['overall_base_pct']:.1f}",
        best_week=best["week"],
        best_mrr=_fmt_mrr(best["expected"] * ARPU_MONTHLY),
        best_signups=best["signups"],
        best_expected=f"{best['expected']:.1f}",
        avg_mrr=_fmt_mrr(avg_mrr),
        avg_expected=f"{avg_expected:.1f}",
        mae_conv=f"{mae_conv:.1f}",
        mae_mrr=_fmt_mrr(mae_mrr),
        mape_str=mape_str,
        bias_conv=f"{abs(bias_conv):.1f}",
        bias_sign=bias_sign,
        n_mature=err.get("n_mature_weeks", 0),
        incomplete_from=meta["incomplete_from"],
        y_axis_max=meta["y_axis_max"],
        weekly_js=weekly_js,
        weekly_chan_js=weekly_chan_js,
        per_note_js=per_note_js,
        biweekly_js=biweekly_js,
        paid_js=paid_js,
        disc_js=disc_js,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return out_path


_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>Signup Funnel · Top of Funnel · L6M</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #e8e3d8;
    --ink: #1a1a1a;
    --purple: #6b5dd3;
    --purple-soft: #a89fdf;
    --green: #2d8a4e;
    --muted: #7a7568;
  }}
  html, body {{ background: var(--bg); color: var(--ink); margin: 0; }}
  body {{
    font-family: 'JetBrains Mono', 'SF Mono', Menlo, monospace;
    max-width: 1100px; margin: 0 auto; padding: 48px 56px 80px;
  }}
  header {{ border-bottom: 1px solid rgba(26,26,26,0.15); padding-bottom: 20px; margin-bottom: 32px; }}
  .eyebrow {{ font-size: 11px; letter-spacing: 2px; color: var(--purple); text-transform: uppercase; font-weight: 700; }}
  h1 {{ font-size: 28px; font-weight: 700; margin: 6px 0 4px; letter-spacing: -0.5px; }}
  h2 {{ font-size: 22px; font-weight: 700; margin: 6px 0 4px; letter-spacing: -0.3px; }}
  .sub {{ font-size: 13px; color: var(--muted); }}
  .frame {{ background: rgba(255,255,255,0.35); border-radius: 6px; padding: 28px 28px 20px; margin-bottom: 28px; }}
  .chart-box {{ position: relative; height: 460px; }}
  .takeaways {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin-top: 24px; margin-bottom: 40px; }}
  .card {{ background: rgba(255,255,255,0.45); border-radius: 4px; padding: 16px 18px; }}
  .card .label {{ font-size: 10px; letter-spacing: 1.5px; color: var(--purple); text-transform: uppercase; font-weight: 700; }}
  .card .val {{ font-size: 22px; font-weight: 700; margin-top: 4px; }}
  .card .note {{ font-size: 11px; color: var(--muted); margin-top: 4px; }}
  footer {{ font-size: 11px; color: var(--muted); margin-top: 8px; border-top: 1px solid rgba(26,26,26,0.12); padding-top: 14px; }}
  .evidence-header {{ margin-top: 60px; padding-top: 28px; border-top: 2px solid rgba(26,26,26,0.2); }}
  .evidence-header .eyebrow {{ color: var(--muted); }}
</style>
</head>
<body>

<header>
  <div class="eyebrow">Ads Engine · Top of Funnel · L6M</div>
  <h1>Forecast vs actual conversions · weekly</h1>
  <div class="sub">
    Weekly signups from public.users (L6M, n={cohort_total}) · Forecast = Σ (users × rolling rate at notes-during-trial) · Actual = users currently payment_status='active' · MRR = conversions × ${arpu} ARPU · generated {generated_at}
  </div>
</header>

<div class="frame">
  <div class="chart-box"><canvas id="chartWeekly"></canvas></div>
  <footer>
    Trial end = first <code>PAYMENT_STATUS_CHANGED</code> where <code>previous_status='trialing'</code>, else signup + 14d (capped 30d).
    Weeks on or after {incomplete_from} (shaded) have incomplete trial windows.
    ${arpu} ARPU is flat in config.py — swap in real blended ARPU when ready.
  </footer>
</div>

<div class="takeaways">
  <div class="card">
    <div class="label">Forecast MAE</div>
    <div class="val">± {mae_conv} convs · {mae_mrr}</div>
    <div class="note">Mean absolute error vs actual, across {n_mature} mature weeks · MAPE {mape_str}</div>
  </div>
  <div class="card">
    <div class="label">Model bias</div>
    <div class="val">{bias_conv} convs {bias_sign}</div>
    <div class="note">Positive = model over-forecasts vs actual. Systematic drift to watch.</div>
  </div>
  <div class="card">
    <div class="label">Average mature week</div>
    <div class="val">{avg_mrr} MRR</div>
    <div class="note">{avg_expected} forecast convs/wk · ${arpu} ARPU · base rate {overall_base_pct}%</div>
  </div>
</div>

<header style="margin-top: 48px;">
  <div class="eyebrow">CRITICAL · Channel Pipeline</div>
  <h1>Conversion-weighted pipeline by paid channel</h1>
  <div class="sub">
    Same expected-conversion math as the top chart, split by paid channel. Non-paid collapsed to "Rest". This shows which paid channel is actually contributing MRR each week, not just CPL.
  </div>
</header>

<div class="frame">
  <div class="chart-box" style="height: 480px;"><canvas id="chartChannel"></canvas></div>
  <footer>
    Stacked bars: each channel's contribution to expected conversions per week.
    Right axis shows the equivalent MRR at ${arpu}/user. Same shading rule for partial weeks.
  </footer>
</div>

<header style="margin-top: 48px;">
  <div class="eyebrow">Attribution Shift</div>
  <h1>Discovery channels over time · biweekly</h1>
  <div class="sub">
    Self-reported discovery channel of signups who created ≥1 note during trial, bucketed into 2-week cohorts. All channels including nulls.
  </div>
</header>

<div class="frame">
  <div class="chart-box" style="height: 480px;"><canvas id="chartArea"></canvas></div>
  <footer>
    The last biweek is partial. "Friend/colleague" and "part of group" still conflate organic + referral + group invites.
  </footer>
</div>

<header class="evidence-header">
  <div class="eyebrow">Evidence · Rate Model</div>
  <h2>Conversion rate by notes created during trial</h2>
  <div class="sub">
    How the rolling rate driving the charts above was computed. Matured L6M cohort. Each dot's size scales with bucket n.
  </div>
</header>

<div class="frame">
  <div class="chart-box"><canvas id="chartRate"></canvas></div>
  <footer>
    Source: <code>public.users</code> ⋈ <code>public.events</code> (Smartscribe Analytics Supabase).
    Notes counted only between signup and trial end. The smoothed line is a 5-pt rolling rate weighted by bucket n.
  </footer>
</div>

<script>
// ===== Model data (injected from compute.py output) =====
const WEEKLY           = {weekly_js};
const WEEKLY_BY_CHAN   = {weekly_chan_js};
const PER_NOTE         = {per_note_js};
const BIWEEKLY         = {biweekly_js};
const PAID_CHANNELS    = {paid_js};
const DISC_CHANNELS    = {disc_js};
const ARPU             = {arpu};
const INCOMPLETE_FROM  = "{incomplete_from}";
const OVERALL_BASE     = {overall_base_pct};
const Y_AXIS_MAX       = {y_axis_max};

Chart.defaults.font.family = "'JetBrains Mono', 'SF Mono', Menlo, monospace";
Chart.defaults.color = '#1a1a1a';

// ===== 1. Weekly signups + expected conversions =====
const wkLabels = WEEKLY.map(w => w.week.slice(5));

new Chart(document.getElementById('chartWeekly'), {{
  type: 'bar',
  data: {{
    labels: wkLabels,
    datasets: [
      {{
        type: 'bar',
        label: 'New signups',
        data: WEEKLY.map(w => w.signups),
        backgroundColor: WEEKLY.map(w =>
          w.week >= INCOMPLETE_FROM ? 'rgba(168,159,223,0.35)' : 'rgba(168,159,223,0.75)'),
        borderColor: 'rgba(107,93,211,0.4)',
        borderWidth: 1,
        yAxisID: 'y',
        order: 2,
      }},
      {{
        type: 'line',
        label: 'Forecast (weighted)',
        data: WEEKLY.map(w => w.expected),
        borderColor: '#6b5dd3',
        backgroundColor: '#6b5dd3',
        borderWidth: 2.5,
        pointRadius: WEEKLY.map(w => w.week >= INCOMPLETE_FROM ? 3 : 4.5),
        pointBackgroundColor: WEEKLY.map(w =>
          w.week >= INCOMPLETE_FROM ? 'rgba(107,93,211,0.4)' : '#6b5dd3'),
        pointBorderColor: '#6b5dd3',
        tension: 0.3,
        yAxisID: 'y1',
        order: 1,
      }},
      {{
        type: 'line',
        label: 'Actual (current active)',
        data: WEEKLY.map(w =>
          w.week >= INCOMPLETE_FROM ? null : w.actual),
        borderColor: '#2d8a4e',
        backgroundColor: '#2d8a4e',
        borderWidth: 2,
        borderDash: [6, 4],
        pointRadius: 4,
        pointStyle: 'rectRot',
        pointBackgroundColor: '#2d8a4e',
        pointBorderColor: '#2d8a4e',
        tension: 0.2,
        yAxisID: 'y1',
        order: 0,
        spanGaps: false,
      }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ boxWidth: 18, padding: 14, font: {{ size: 11 }} }} }},
      tooltip: {{
        backgroundColor: '#1a1a1a', titleColor:'#e8e3d8', bodyColor:'#e8e3d8', padding:12,
        callbacks: {{
          title: (items) => {{
            const w = WEEKLY[items[0].dataIndex];
            const tag = w.week >= INCOMPLETE_FROM ? '  (partial trial window)' : '';
            return `Week of ${{w.week}}${{tag}}`;
          }},
          label: (item) => {{
            const w = WEEKLY[item.dataIndex];
            if (item.datasetIndex === 0) return `Signups: ${{w.signups}}`;
            if (item.datasetIndex === 1) {{
              const rate = (w.expected/w.signups*100).toFixed(1);
              const mrr = w.mrr.toLocaleString('en-US',{{maximumFractionDigits:0}});
              return `Forecast: ${{w.expected.toFixed(1)}} convs (${{rate}}%) · $${{mrr}} MRR`;
            }}
            // actual
            if (w.week >= INCOMPLETE_FROM) return `Actual: pending`;
            const rate = (w.actual/w.signups*100).toFixed(1);
            const mrrA = w.mrr_actual.toLocaleString('en-US',{{maximumFractionDigits:0}});
            const err = (w.expected - w.actual);
            const errStr = (err >= 0 ? '+' : '') + err.toFixed(1);
            return [
              `Actual: ${{w.actual}} convs (${{rate}}%) · $${{mrrA}} MRR`,
              `Error: ${{errStr}} convs (forecast − actual)`
            ];
          }}
        }}
      }}
    }},
    scales: {{
      x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 9 }}, maxRotation: 60 }} }},
      y: {{
        position: 'left', beginAtZero: true,
        title: {{ display: true, text: 'New signups', font: {{ size: 11, weight: 600 }} }},
        grid: {{ color: 'rgba(26,26,26,0.06)' }},
        ticks: {{ font: {{ size: 10 }} }}
      }},
      y1: {{
        position: 'right', beginAtZero: true, max: Y_AXIS_MAX,
        title: {{ display: true, text: `Forecast vs Actual conversions  (× $${{ARPU}} = MRR)`, font: {{ size: 11, weight: 600 }}, color: '#6b5dd3' }},
        grid: {{ display: false }},
        ticks: {{
          font: {{ size: 10 }}, color: '#6b5dd3', stepSize: 5,
          callback: (v) => `${{v}}  ·  $${{(v*ARPU).toLocaleString()}}`
        }}
      }}
    }}
  }}
}});

// ===== 2. Channel-weighted pipeline (stacked) =====
const chanLabels = WEEKLY_BY_CHAN.map(w => w.week.slice(5));
const chanDatasets = PAID_CHANNELS.map(ch => ({{
  label: ch.label,
  data: WEEKLY_BY_CHAN.map(w => (w.channels[ch.key] || {{expected:0}}).expected),
  backgroundColor: WEEKLY_BY_CHAN.map(w =>
    w.week >= INCOMPLETE_FROM ? ch.color + '66' : ch.color + 'dd'),
  borderColor: ch.color,
  borderWidth: 0.5,
  stack: 'pipeline',
}}));

// Recompute the y-axis max from only the currently-visible stacked datasets.
// Called after every legend toggle so the bars grow when a channel is hidden.
function recomputeChannelYMax(chart) {{
  const n = chart.data.labels.length;
  let peak = 0;
  for (let i = 0; i < n; i++) {{
    let stack = 0;
    chart.data.datasets.forEach((ds, dsIdx) => {{
      if (chart.isDatasetVisible(dsIdx)) stack += (ds.data[i] || 0);
    }});
    if (stack > peak) peak = stack;
  }}
  // Round up to nearest "nice" tick. Pick the step that fits the range.
  const padded = peak * 1.12;
  const step = padded >= 20 ? 5 : (padded >= 10 ? 2 : (padded >= 4 ? 1 : 0.5));
  const newMax = Math.max(step, Math.ceil(padded / step) * step);
  chart.options.scales.y.max = newMax;
  chart.options.scales.y.ticks.stepSize = step;
}}

new Chart(document.getElementById('chartChannel'), {{
  type: 'bar',
  data: {{ labels: chanLabels, datasets: chanDatasets }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{
        position: 'bottom',
        labels: {{ boxWidth: 14, padding: 12, font: {{ size: 11 }} }},
        onClick: function(e, legendItem, legend) {{
          const chart = legend.chart;
          const idx = legendItem.datasetIndex;
          if (chart.isDatasetVisible(idx)) {{
            chart.hide(idx);
            legendItem.hidden = true;
          }} else {{
            chart.show(idx);
            legendItem.hidden = false;
          }}
          recomputeChannelYMax(chart);
          chart.update();
        }}
      }},
      tooltip: {{
        backgroundColor:'#1a1a1a', titleColor:'#e8e3d8', bodyColor:'#e8e3d8', padding:12,
        itemSort: (a,b) => b.raw - a.raw,
        callbacks: {{
          title: (items) => {{
            const i = items[0].dataIndex;
            const w = WEEKLY_BY_CHAN[i];
            const totalExp = PAID_CHANNELS.reduce((s, ch) =>
              s + ((w.channels[ch.key] || {{}}).expected || 0), 0);
            const totalMrr = (totalExp * ARPU).toLocaleString('en-US',{{maximumFractionDigits:0}});
            const tag = w.week >= INCOMPLETE_FROM ? '  (partial)' : '';
            return `Week of ${{w.week}}${{tag}}  ·  Σ ${{totalExp.toFixed(1)}} convs · $${{totalMrr}}`;
          }},
          label: (item) => {{
            const w = WEEKLY_BY_CHAN[item.dataIndex];
            const ch = PAID_CHANNELS[item.datasetIndex];
            const cell = w.channels[ch.key] || {{signups:0,expected:0,mrr:0}};
            const mrr = cell.mrr.toLocaleString('en-US',{{maximumFractionDigits:0}});
            return `${{ch.label}}: ${{cell.expected.toFixed(1)}} convs · $${{mrr}} · ${{cell.signups}} signups`;
          }}
        }}
      }}
    }},
    scales: {{
      x: {{ stacked: true, grid: {{ display: false }}, ticks: {{ font: {{ size: 9 }}, maxRotation: 60 }} }},
      y: {{
        stacked: true, beginAtZero: true, max: Y_AXIS_MAX,
        title: {{ display: true, text: `Expected conversions  (× $${{ARPU}} = MRR)`, font: {{ size: 11, weight: 600 }} }},
        grid: {{ color: 'rgba(26,26,26,0.06)' }},
        ticks: {{
          font: {{ size: 10 }}, stepSize: 5,
          callback: (v) => `${{v}}  ·  $${{(v*ARPU).toLocaleString()}}`
        }}
      }}
    }}
  }}
}});

// Recompute channel y-axis once after first render so the initial view
// uses its own tight fit (same logic as after a legend toggle).
(function() {{
  const chart = Chart.getChart(document.getElementById('chartChannel'));
  if (chart) {{
    recomputeChannelYMax(chart);
    chart.update();
  }}
}})();

// ===== 3. Biweekly discovery area =====
const bwLabels = BIWEEKLY.map(b => b.biweek.slice(5));
const bwLastIdx = BIWEEKLY.length - 1;

const areaDatasets = DISC_CHANNELS.map(ch => ({{
  label: ch.label,
  data: BIWEEKLY.map(b => b.channels[ch.key] || 0),
  borderColor: ch.color,
  backgroundColor: ch.color + 'cc',
  borderWidth: 0.75,
  fill: true,
  pointRadius: 0,
  tension: 0.3,
  stack: 'disc',
}}));

new Chart(document.getElementById('chartArea'), {{
  type: 'line',
  data: {{ labels: bwLabels, datasets: areaDatasets }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ boxWidth: 14, padding: 10, font: {{ size: 10 }} }} }},
      tooltip: {{
        backgroundColor:'#1a1a1a', titleColor:'#e8e3d8', bodyColor:'#e8e3d8', padding:12,
        itemSort: (a,b) => b.raw - a.raw,
        callbacks: {{
          title: (items) => {{
            const i = items[0].dataIndex;
            const bw = BIWEEKLY[i];
            const total = DISC_CHANNELS.reduce((s,ch) => s + (bw.channels[ch.key]||0), 0);
            const partial = i === bwLastIdx ? '  (partial)' : '';
            return `Biweek of ${{bw.biweek}}  ·  n=${{total}}${{partial}}`;
          }},
          label: (item) => {{
            const bw = BIWEEKLY[item.dataIndex];
            const total = DISC_CHANNELS.reduce((s,ch) => s + (bw.channels[ch.key]||0), 0);
            const pct = total ? (item.raw/total*100).toFixed(0) : '0';
            return `${{item.dataset.label}}: ${{item.raw}} (${{pct}}%)`;
          }}
        }}
      }}
    }},
    scales: {{
      x: {{ grid: {{ display: false }}, ticks: {{ font: {{ size: 10 }} }} }},
      y: {{
        stacked: true, beginAtZero: true,
        title: {{ display: true, text: 'First-note trialers', font: {{ size: 11, weight: 600 }} }},
        grid: {{ color: 'rgba(26,26,26,0.06)' }},
        ticks: {{ font: {{ size: 10 }} }}
      }}
    }}
  }}
}});

// ===== 4. Evidence: per-note rate =====
const labels = PER_NOTE.map(r => r.notes === 30 ? '30+' : r.notes);

new Chart(document.getElementById('chartRate'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{
        label: 'Raw conversion rate',
        data: PER_NOTE.map(r => r.raw_pct),
        borderColor: 'rgba(107,93,211,0.35)',
        backgroundColor: 'rgba(107,93,211,0.35)',
        borderWidth: 1.5,
        pointRadius: PER_NOTE.map(r => Math.max(3, Math.min(14, Math.sqrt(r.n)*0.9))),
        pointHoverRadius: PER_NOTE.map(r => Math.max(5, Math.min(16, Math.sqrt(r.n)*0.95))),
        pointBackgroundColor: 'rgba(107,93,211,0.55)',
        pointBorderColor: 'rgba(107,93,211,0.8)',
        pointBorderWidth: 1,
        tension: 0, borderDash: [4,4], order: 2,
      }},
      {{
        label: 'Smoothed (5-pt, weighted by n)',
        data: PER_NOTE.map(r => r.smooth_pct),
        borderColor: '#6b5dd3', backgroundColor: 'transparent',
        borderWidth: 3, pointRadius: 0, tension: 0.35, order: 1,
      }},
      {{
        label: `Overall base rate (${{OVERALL_BASE.toFixed(1)}}%)`,
        data: new Array(labels.length).fill(OVERALL_BASE),
        borderColor: '#2d8a4e',
        borderWidth: 1.5, borderDash: [2,3], pointRadius: 0, order: 3,
      }},
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    interaction: {{ mode: 'index', intersect: false }},
    plugins: {{
      legend: {{ position: 'bottom', labels: {{ boxWidth: 18, padding: 14, font: {{ size: 11 }} }} }},
      tooltip: {{
        backgroundColor: '#1a1a1a', titleColor: '#e8e3d8', bodyColor: '#e8e3d8', padding: 12,
        callbacks: {{
          title: (items) => `${{items[0].label}} notes during trial`,
          label: (item) => {{
            const row = PER_NOTE[item.dataIndex];
            if (item.datasetIndex === 0) return `Raw: ${{row.raw_pct}}% (${{row.active}}/${{row.n}})`;
            if (item.datasetIndex === 1) return `Smoothed: ${{row.smooth_pct}}%`;
            return `Base rate: ${{OVERALL_BASE.toFixed(1)}}%`;
          }}
        }}
      }}
    }},
    scales: {{
      x: {{
        title: {{ display: true, text: 'Notes created during trial', font: {{ size: 12, weight: 600 }}, padding: {{ top: 8 }} }},
        grid: {{ color: 'rgba(26,26,26,0.06)' }},
        ticks: {{ font: {{ size: 10 }} }}
      }},
      y: {{
        title: {{ display: true, text: 'Conversion rate (%)', font: {{ size: 12, weight: 600 }} }},
        beginAtZero: true, max: 65,
        grid: {{ color: 'rgba(26,26,26,0.08)' }},
        ticks: {{ callback: v => v + '%', font: {{ size: 10 }} }}
      }}
    }}
  }}
}});
</script>
</body>
</html>
"""


def main() -> Path:
    model = json.loads(Path(MODEL_PATH).read_text())
    path = render(model)
    print(f"HTML written → {path}")
    return path


if __name__ == "__main__":
    main()
