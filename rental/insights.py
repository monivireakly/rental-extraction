"""
Generate a self-contained HTML market intelligence dashboard.
Outputs data/insights.html — open in any browser, screenshot for social media.

Usage:
    python -m rental.insights
"""

import json
import os
import sqlite3
import webbrowser
from collections import defaultdict
from datetime import date

import numpy as np

from .config import settings
from .normalizer import normalise_district, normalise_room, normalise_furnished

DB_PATH  = settings.database_path
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "insights.html")

ROOM_ORDER = ["Studio", "1BR", "2BR", "3BR", "4BR+"]

PTYPE_COLORS = {
    "Condo":             "#3B82F6",
    "Apartment":         "#10B981",
    "Service Apartment": "#8B5CF6",
    "Borey":             "#F59E0B",
    "Villa":             "#EF4444",
    "Shophouse":         "#14B8A6",
    "Studio":            "#EC4899",
}


def _extract():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT district, room_type, furnished_status, property_type,
               rent_usd, electricity_per_kwh, extraction_confidence,
               needs_review, posted_at
        FROM listings
    """).fetchall()
    monthly = conn.execute("""
        SELECT strftime('%Y-%m', posted_at) mo, COUNT(*) n
        FROM listings WHERE posted_at IS NOT NULL GROUP BY 1 ORDER BY 1
    """).fetchall()
    conn.close()

    records = []
    for r in rows:
        room = normalise_room(r["room_type"])
        if room and room not in ("Studio", "1BR", "2BR", "3BR"):
            room = "4BR+"
        ptype = r["property_type"] or "Unknown"
        if ptype == "null":
            ptype = "Unknown"
        records.append({
            "district": normalise_district(r["district"]),
            "room":     room,
            "furnished": normalise_furnished(r["furnished_status"]),
            "ptype":    ptype,
            "rent":     r["rent_usd"],
            "elec":     r["electricity_per_kwh"],
            "conf":     float(r["extraction_confidence"] or 0),
            "review":   bool(r["needs_review"]),
        })

    n     = len(records)
    rents = [r["rent"] for r in records if r["rent"] and 0 < r["rent"] < 5000]

    # Districts
    dist_counts = defaultdict(int)
    for r in records:
        if r["district"]:
            dist_counts[r["district"]] += 1
    top_dist  = max(dist_counts, key=dist_counts.get, default="—")
    top14     = sorted(dist_counts.items(), key=lambda x: x[1], reverse=True)[:14]
    top10_keys = [k for k, _ in sorted(dist_counts.items(), key=lambda x: x[1], reverse=True)[:10]]

    # Rent histogram
    hc, he = np.histogram(rents, bins=40, range=(100, 4500))
    h_bins  = [round((he[i] + he[i+1]) / 2) for i in range(len(hc))]

    # Percentiles
    pcts = {k: int(np.percentile(rents, v)) for k, v in
            [("p10",10),("p25",25),("p50",50),("p75",75),("p90",90)]} if rents else {}

    # Room type averages + std
    rv = {r: [d["rent"] for d in records if d["room"] == r and d["rent"]] for r in ROOM_ORDER}

    # Heatmap
    heat_rooms = ["Studio", "1BR", "2BR", "3BR"]
    hm_data = []
    for i, dist in enumerate(top10_keys):
        for j, room in enumerate(heat_rooms):
            vals = [d["rent"] for d in records
                    if d["district"] == dist and d["room"] == room and d["rent"]]
            if vals:
                hm_data.append([j, i, int(np.median(vals)), len(vals)])

    hm_vals = [x[2] for x in hm_data]

    # Furnished premium (grouped bar)
    fp_full    = [int(np.mean([d["rent"] for d in records if d["room"]==r and d["furnished"]=="Full"    and d["rent"]]) or 0)
                  if any(d["room"]==r and d["furnished"]=="Full"    and d["rent"] for d in records) else None
                  for r in ROOM_ORDER]
    fp_partial = [int(np.mean([d["rent"] for d in records if d["room"]==r and d["furnished"]=="Partial" and d["rent"]]) or 0)
                  if any(d["room"]==r and d["furnished"]=="Partial" and d["rent"] for d in records) else None
                  for r in ROOM_ORDER]
    fp_none    = [int(np.mean([d["rent"] for d in records if d["room"]==r and d["furnished"] is None    and d["rent"]]) or 0)
                  if any(d["room"]==r and d["furnished"] is None    and d["rent"] for d in records) else None
                  for r in ROOM_ORDER]

    # Electricity histogram
    ev = [r["elec"] for r in records if r["elec"] and 0.05 < r["elec"] < 0.5]
    ec2, ee2 = (np.histogram(ev, bins=16), ev) if ev else ((np.array([]), np.array([])), ev)
    if ev:
        ec_counts, ee2 = np.histogram(ev, bins=16)
        ec_bins = [round((ee2[i] + ee2[i+1]) / 2, 3) for i in range(len(ec_counts))]
    else:
        ec_counts, ec_bins = [], []

    # Property types + furnished
    ptc = defaultdict(int)
    for r in records:
        if r["ptype"] != "Unknown":
            ptc[r["ptype"]] += 1
    pt_sorted = sorted(ptc.items(), key=lambda x: x[1], reverse=True)
    furn_cnt = {k: sum(1 for r in records if r["furnished"] == k)
                for k in ["Full", "Partial", "Unfurnished"]}

    return {
        "meta": {"generated_at": date.today().strftime("%B %d, %Y"), "total": n},
        "kpis": {
            "total":               n,
            "avg_rent":            int(np.mean(rents)) if rents else 0,
            "median_rent":         int(np.median(rents)) if rents else 0,
            "top_district":        top_dist,
            "top_district_count":  dist_counts[top_dist],
            "high_conf_pct":       round(sum(1 for r in records if r["conf"] >= 0.8) / n * 100),
            "needs_review":        sum(1 for r in records if r["review"]),
        },
        "percentiles": pcts,
        "rent_hist":   {"bins": h_bins, "counts": hc.tolist()},
        "room_avg": {
            "labels": ROOM_ORDER,
            "avgs":   [int(np.mean(rv[r])) if rv[r] else None for r in ROOM_ORDER],
            "counts": [len(rv[r]) for r in ROOM_ORDER],
            "stds":   [int(np.std(rv[r])) if len(rv[r]) > 1 else 0 for r in ROOM_ORDER],
        },
        "monthly": {
            "labels": [m["mo"][5:] + "/" + m["mo"][2:4] for m in monthly],
            "counts": [m["n"] for m in monthly],
        },
        "districts": {
            "labels": [k for k, _ in top14],
            "counts": [v for _, v in top14],
        },
        "property_types": [
            {"name": k, "value": v, "itemStyle": {"color": PTYPE_COLORS.get(k, "#94A3B8")}}
            for k, v in pt_sorted
        ],
        "furnished": [
            {"name": k, "value": v,
             "itemStyle": {"color": {"Full": "#10B981", "Partial": "#F59E0B",
                                     "Unfurnished": "#94A3B8"}.get(k, "#94A3B8")}}
            for k, v in furn_cnt.items() if v > 0
        ],
        "heatmap": {
            "districts": top10_keys,
            "rooms":     heat_rooms,
            "data":      hm_data,
            "min":       min(hm_vals) if hm_vals else 0,
            "max":       max(hm_vals) if hm_vals else 0,
        },
        "furnished_premium": {
            "rooms":   ROOM_ORDER,
            "full":    fp_full,
            "partial": fp_partial,
            "none":    fp_none,
        },
        "elec": {
            "bins":   ec_bins,
            "counts": ec_counts.tolist() if hasattr(ec_counts, "tolist") else list(ec_counts),
            "median": round(float(np.median(ev)), 3) if ev else None,
            "n":      len(ev),
        },
        "quality": {
            "high":    sum(1 for r in records if r["conf"] >= 0.8),
            "med":     sum(1 for r in records if 0.6 <= r["conf"] < 0.8),
            "low":     sum(1 for r in records if r["conf"] < 0.6),
            "flagged": sum(1 for r in records if r["review"]),
        },
    }


# ── HTML template ──────────────────────────────────────────────────────────────
_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta property="og:title" content="Phnom Penh Rental Market — Intelligence Report">
<meta property="og:description" content="Deep analysis of rental listings across Phnom Penh. Prices, districts, trends.">
<title>Phnom Penh Rental Market Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --blue:#2563EB;--blue-l:#EFF6FF;--green:#059669;--amber:#D97706;
  --red:#DC2626;--purple:#7C3AED;--teal:#0D9488;--pink:#DB2777;
  --bg:#EEF2FF;--card:#fff;--border:#E2E8F0;
  --text:#0F172A;--mid:#475569;--soft:#94A3B8;
  --font:'Inter',system-ui,-apple-system,sans-serif;
  --shadow:0 1px 3px rgba(0,0,0,.05),0 4px 16px rgba(0,0,0,.06);
  --r:14px;
}
body{font-family:var(--font);background:var(--bg);color:var(--text);font-size:14px;line-height:1.6}

/* ── Header ── */
.hdr{
  background:linear-gradient(140deg,#0F0C29 0%,#1E1B4B 45%,#1D4ED8 100%);
  padding:52px 48px 44px;position:relative;overflow:hidden;
}
.hdr::before{
  content:'';position:absolute;inset:0;
  background:radial-gradient(ellipse at 80% 50%,rgba(99,102,241,.18) 0%,transparent 65%);
  pointer-events:none;
}
.hdr-inner{max-width:1360px;margin:0 auto;position:relative;z-index:1}
.hdr-badge{
  display:inline-flex;align-items:center;gap:6px;
  background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.18);
  color:rgba(255,255,255,.8);font-size:10.5px;font-weight:700;
  letter-spacing:.1em;text-transform:uppercase;
  padding:5px 14px;border-radius:100px;margin-bottom:22px;
}
.hdr h1{
  font-size:clamp(28px,3.2vw,46px);font-weight:900;color:#fff;
  letter-spacing:-.03em;line-height:1.05;margin-bottom:10px;
}
.hdr-sub{font-size:16px;color:rgba(255,255,255,.55);font-weight:400;margin-bottom:34px}
.hdr-pills{display:flex;gap:14px;flex-wrap:wrap}
.hdr-pill{
  background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14);
  border-radius:10px;padding:12px 20px;
}
.hdr-pill .v{font-size:20px;font-weight:800;color:#fff;letter-spacing:-.01em}
.hdr-pill .l{font-size:10px;font-weight:600;color:rgba(255,255,255,.45);
             text-transform:uppercase;letter-spacing:.08em;margin-top:2px}
.hdr-date{
  position:absolute;top:52px;right:0;
  font-size:11px;color:rgba(255,255,255,.3);text-align:right;
}

/* ── Main ── */
.main{max-width:1360px;margin:0 auto;padding:36px 48px 56px}

/* ── Section headers ── */
.sec{display:flex;align-items:center;gap:12px;margin:40px 0 18px}
.sec:first-of-type{margin-top:0}
.sec-lbl{
  font-size:10.5px;font-weight:800;letter-spacing:.12em;
  text-transform:uppercase;color:var(--mid);white-space:nowrap;
}
.sec-line{flex:1;height:1px;background:var(--border)}

/* ── KPI grid ── */
.kpi-row{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
.kpi{
  background:var(--card);border-radius:var(--r);
  box-shadow:var(--shadow);padding:22px 20px 18px;
  border-top:4px solid var(--ac,var(--blue));
  position:relative;overflow:hidden;
}
.kpi::after{
  content:'';position:absolute;bottom:-20px;right:-20px;
  width:80px;height:80px;border-radius:50%;
  background:var(--ac,var(--blue));opacity:.06;
}
.kpi-v{font-size:30px;font-weight:900;color:var(--text);letter-spacing:-.025em;line-height:1}
.kpi-l{font-size:11px;font-weight:700;color:var(--mid);text-transform:uppercase;
        letter-spacing:.07em;margin-top:8px}
.kpi-s{font-size:11px;color:var(--soft);margin-top:3px}

/* ── Chart cards ── */
.card{background:var(--card);border-radius:var(--r);box-shadow:var(--shadow);padding:22px 20px 16px;overflow:hidden}
.card-t{font-size:14px;font-weight:700;color:var(--text)}
.card-s{font-size:11px;color:var(--soft);margin-top:3px;margin-bottom:14px}

/* ── Grids ── */
.g21  {display:grid;grid-template-columns:2fr 1fr;gap:16px}
.g211 {display:grid;grid-template-columns:2fr 1fr 1fr;gap:16px}
.g3   {display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px}

/* ── Insight callout ── */
.callout{
  background:linear-gradient(90deg,#EFF6FF,#F5F3FF);
  border:1px solid #DBEAFE;border-radius:10px;
  padding:13px 18px;font-size:12px;color:#1E40AF;font-weight:500;
  display:flex;gap:6px;align-items:flex-start;margin-bottom:16px;
}
.callout-icon{font-size:14px;margin-top:1px}

/* ── Footer ── */
.ftr{
  text-align:center;padding:22px 48px;
  font-size:11px;color:var(--soft);
  border-top:1px solid var(--border);background:var(--card);
  margin-top:0;
}
.ftr strong{color:var(--mid)}

@media(max-width:960px){
  .kpi-row{grid-template-columns:repeat(2,1fr)}
  .g21,.g211,.g3{grid-template-columns:1fr}
  .main,.hdr{padding-left:20px;padding-right:20px}
}
</style>
</head>
<body>

<!-- ── HEADER ─────────────────────────────────────────────────────────────── -->
<header class="hdr">
  <div class="hdr-inner">
    <div class="hdr-badge">🏙 Market Intelligence Report</div>
    <h1>Phnom Penh<br>Rental Market</h1>
    <p class="hdr-sub">Data-driven insights from Telegram listing channels — prices, districts, trends</p>
    <div class="hdr-pills" id="hdr-pills"></div>
    <div class="hdr-date" id="hdr-date"></div>
  </div>
</header>

<main class="main">

<!-- ── KPIs ─────────────────────────────────────────────────────────────────── -->
<div class="sec"><span class="sec-lbl">Key Metrics</span><div class="sec-line"></div></div>
<div class="kpi-row">
  <div class="kpi" style="--ac:#3B82F6">
    <div class="kpi-v" id="kv-total">—</div>
    <div class="kpi-l">Total Listings</div>
    <div class="kpi-s">Jan – Jun 2026</div>
  </div>
  <div class="kpi" style="--ac:#10B981">
    <div class="kpi-v" id="kv-avg">—</div>
    <div class="kpi-l">Avg Rent / Month</div>
    <div class="kpi-s" id="kv-med-s">Median —</div>
  </div>
  <div class="kpi" style="--ac:#F59E0B">
    <div class="kpi-v" id="kv-dist">—</div>
    <div class="kpi-l">Top District</div>
    <div class="kpi-s" id="kv-dist-s">— listings</div>
  </div>
  <div class="kpi" style="--ac:#8B5CF6">
    <div class="kpi-v" id="kv-conf">—</div>
    <div class="kpi-l">High Confidence</div>
    <div class="kpi-s">extraction score ≥ 0.8</div>
  </div>
</div>

<!-- ── MARKET OVERVIEW ────────────────────────────────────────────────────── -->
<div class="sec"><span class="sec-lbl">📊 Market Overview</span><div class="sec-line"></div></div>
<div class="g21">
  <div class="card">
    <div class="card-t">Rent Distribution</div>
    <div class="card-s">USD / month &nbsp;·&nbsp; listings under $4,500 &nbsp;·&nbsp; dashed lines = key percentiles</div>
    <div id="c-hist" style="height:280px"></div>
  </div>
  <div class="card">
    <div class="card-t">Listing Volume by Month</div>
    <div class="card-s">Jan – Jun 2026 &nbsp;·&nbsp; Jun is a partial month</div>
    <div id="c-trend" style="height:280px"></div>
  </div>
</div>

<!-- ── LOCATION ──────────────────────────────────────────────────────────── -->
<div class="sec"><span class="sec-lbl">📍 Location & Supply</span><div class="sec-line"></div></div>
<div class="g211">
  <div class="card">
    <div class="card-t">Listings by District</div>
    <div class="card-s">Top 14 districts ranked by listing count</div>
    <div id="c-dist" style="height:340px"></div>
  </div>
  <div class="card">
    <div class="card-t">Property Type Mix</div>
    <div class="card-s">% share of classified listings</div>
    <div id="c-ptype" style="height:340px"></div>
  </div>
  <div class="card">
    <div class="card-t">Furnished Status</div>
    <div class="card-s">% of listings with stated furnishing</div>
    <div id="c-furn" style="height:340px"></div>
  </div>
</div>

<!-- ── PRICING HEATMAP ────────────────────────────────────────────────────── -->
<div class="sec"><span class="sec-lbl">💰 Pricing Intelligence</span><div class="sec-line"></div></div>
<div class="card">
  <div class="card-t">Median Rent Heatmap — District × Room Type</div>
  <div class="card-s">USD / month &nbsp;·&nbsp; each cell shows median rent and sample size (n)</div>
  <div id="c-heat" style="height:400px"></div>
</div>

<!-- ── DEEPER ANALYSIS ────────────────────────────────────────────────────── -->
<div class="sec"><span class="sec-lbl">🔍 Deeper Analysis</span><div class="sec-line"></div></div>
<div class="g211">
  <div class="card">
    <div class="card-t">Avg Rent by Room Type &amp; Furnished Status</div>
    <div class="card-s">Mean rent across furnishing tiers — shows the furnished premium</div>
    <div id="c-fprm" style="height:280px"></div>
  </div>
  <div class="card">
    <div class="card-t">Electricity Rate Distribution</div>
    <div class="card-s">$/kWh across listings where stated</div>
    <div id="c-elec" style="height:280px"></div>
  </div>
  <div class="card">
    <div class="card-t">Extraction Quality</div>
    <div class="card-s">Claude confidence score distribution</div>
    <div id="c-qual" style="height:280px"></div>
  </div>
</div>

</main>

<footer class="ftr">
  <strong>Phnom Penh Rental Market Intelligence</strong> &nbsp;·&nbsp;
  Data extracted via Claude AI &nbsp;·&nbsp;
  Source: public Telegram rental channels &nbsp;·&nbsp;
  Generated <span id="f-date"></span>
</footer>

<script>
const D = __DATA__;

// ── Hydrate KPIs & header ─────────────────────────────────────────────────
document.getElementById('kv-total').textContent   = D.kpis.total.toLocaleString();
document.getElementById('kv-avg').textContent     = '$' + D.kpis.avg_rent.toLocaleString();
document.getElementById('kv-med-s').textContent   = 'Median  $' + D.kpis.median_rent.toLocaleString();
document.getElementById('kv-dist').textContent    = D.kpis.top_district;
document.getElementById('kv-dist-s').textContent  = D.kpis.top_district_count + ' listings';
document.getElementById('kv-conf').textContent    = D.kpis.high_conf_pct + '%';
document.getElementById('hdr-date').textContent   = 'Generated ' + D.meta.generated_at;
document.getElementById('f-date').textContent     = D.meta.generated_at;

const pills = [
  { v: D.kpis.total.toLocaleString(),           l: 'Listings' },
  { v: '$' + D.percentiles.p50,                 l: 'Median Rent' },
  { v: '$' + D.percentiles.p25 + '–$' + D.percentiles.p75, l: 'IQR Range' },
  { v: D.kpis.top_district,                     l: 'Top District' },
];
document.getElementById('hdr-pills').innerHTML = pills.map(p =>
  `<div class="hdr-pill"><div class="v">${p.v}</div><div class="l">${p.l}</div></div>`
).join('');

// ── Shared ECharts config ──────────────────────────────────────────────────
const C = {
  B:'#3B82F6', G:'#10B981', A:'#F59E0B', R:'#EF4444',
  P:'#8B5CF6', T:'#14B8A6', K:'#EC4899', S:'#94A3B8',
  DARK:'#0F172A', MID:'#475569', SOFT:'#94A3B8', BORDER:'#F1F5F9',
};
const tip = {
  backgroundColor:'#1E293B', borderColor:'transparent',
  textStyle:{color:'#F1F5F9',fontSize:12},
  extraCssText:'border-radius:8px;padding:10px 14px;box-shadow:0 8px 30px rgba(0,0,0,.3)',
};
const axY = (name='') => ({
  type:'value', name, nameTextStyle:{color:C.MID,fontSize:10},
  axisLine:{lineStyle:{color:C.BORDER}}, axisTick:{show:false},
  axisLabel:{color:C.MID,fontSize:10},
  splitLine:{lineStyle:{color:'#F8FAFC',type:'dashed'}},
});
const axX = (data, rotate=0) => ({
  type:'category', data,
  axisLine:{lineStyle:{color:C.BORDER}}, axisTick:{show:false},
  axisLabel:{color:C.MID,fontSize:10,rotate},
});
const axXV = () => ({
  type:'value',
  axisLine:{lineStyle:{color:C.BORDER}}, axisTick:{show:false},
  axisLabel:{color:C.MID,fontSize:10},
  splitLine:{lineStyle:{color:'#F8FAFC',type:'dashed'}},
});
const grid = (t=16,r=16,b=36,l=48) => ({top:t,right:r,bottom:b,left:l,containLabel:true});
function ec(id){ return echarts.init(document.getElementById(id),null,{renderer:'svg'}); }

// ── 1. Rent histogram ─────────────────────────────────────────────────────
(function(){
  const ch = ec('c-hist');
  const P  = D.percentiles;
  const mx = Math.max(...D.rent_hist.counts);
  const ml = (val, lbl, col) => ({
    xAxis: val+'', yAxis:0,
    lineStyle:{color:col,width:1.8,type:'dashed'},
    label:{show:true,position:'insideEndTop',formatter:lbl,color:col,fontSize:10,fontWeight:'600'},
    symbol:'none',
  });
  ch.setOption({
    grid: grid(36,20,32,20),
    tooltip: {...tip, trigger:'axis',
      formatter:p=>`$${p[0].name}<br/><b>${p[0].value} listings</b>`},
    xAxis: axX(D.rent_hist.bins),
    yAxis: axY('Listings'),
    visualMap:{show:false,min:0,max:mx,inRange:{color:[C.B+'55',C.B]}},
    series:[{
      type:'bar', data:D.rent_hist.counts, barWidth:'90%',
      itemStyle:{borderRadius:[3,3,0,0]},
      markLine:{silent:true, animation:false, data:[
        ml(P.p25,'P25',C.S), ml(P.p50,'P50\n$'+P.p50,C.G),
        ml(P.p75,'P75',C.A), ml(P.p90,'P90',C.R),
      ]},
    }],
  });
})();

// ── 2. Monthly trend ──────────────────────────────────────────────────────
(function(){
  const ch = ec('c-trend');
  const mx = Math.max(...D.monthly.counts);
  ch.setOption({
    grid: grid(32,16,32,20),
    tooltip: {...tip, trigger:'axis',
      formatter:p=>`${p[0].name} 2026<br/><b>${p[0].value} listings</b>`},
    xAxis: axX(D.monthly.labels),
    yAxis: axY(),
    series:[{
      type:'line', data:D.monthly.counts, smooth:0.3,
      symbol:'circle', symbolSize:7, lineWidth:2.5,
      color:C.B,
      areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,
        colorStops:[{offset:0,color:C.B+'44'},{offset:1,color:C.B+'05'}]}},
      markPoint:{
        data:[{type:'max',name:'Peak',label:{formatter:'Peak\n{c}',fontSize:10}}],
        symbol:'circle',symbolSize:42,
        itemStyle:{color:C.R+'22',borderColor:C.R,borderWidth:1.5},
        label:{color:C.R,fontWeight:'700'},
      },
    }],
  });
})();

// ── 3. Districts horizontal bar ───────────────────────────────────────────
(function(){
  const ch = ec('c-dist');
  const rev = (a) => [...a].reverse();
  ch.setOption({
    grid: grid(8,60,8,8),
    tooltip: {...tip, trigger:'axis', formatter:p=>`${p[0].name}<br/><b>${p[0].value} listings</b>`},
    xAxis: axXV(),
    yAxis: {type:'category', data:rev(D.districts.labels),
      axisLine:{show:false}, axisTick:{show:false},
      axisLabel:{color:C.MID,fontSize:10.5}},
    series:[{
      type:'bar', data:rev(D.districts.counts), barWidth:'60%',
      itemStyle:{borderRadius:[0,4,4,0],
        color:{type:'linear',x:0,y:0,x2:1,y2:0,
          colorStops:[{offset:0,color:C.B+'aa'},{offset:1,color:C.B}]}},
      label:{show:true,position:'right',color:C.MID,fontSize:10,
        formatter:'{c}'},
    }],
  });
})();

// ── 4. Property type donut ────────────────────────────────────────────────
(function(){
  const ch = ec('c-ptype');
  const total = D.property_types.reduce((s,d)=>s+d.value,0);
  ch.setOption({
    tooltip:{...tip, trigger:'item',
      formatter:p=>`${p.name}<br/><b>${p.value} listings (${p.percent}%)</b>`},
    legend:{bottom:0,left:'center',textStyle:{color:C.MID,fontSize:10},itemWidth:10,itemHeight:10},
    series:[{
      type:'pie', radius:['42%','70%'],
      center:['50%','44%'],
      data: D.property_types,
      label:{show:false},
      emphasis:{scaleSize:4},
      itemStyle:{borderRadius:4,borderColor:'#fff',borderWidth:2},
    }],
    graphic:[{type:'text',left:'center',top:'38%',style:{
      text:total.toLocaleString(),fill:C.DARK,
      font:'bold 20px Inter,sans-serif',
    }},{type:'text',left:'center',top:'47%',style:{
      text:'listings',fill:C.SOFT,font:'11px Inter,sans-serif',
    }}],
  });
})();

// ── 5. Furnished donut ────────────────────────────────────────────────────
(function(){
  const ch = ec('c-furn');
  const total = D.furnished.reduce((s,d)=>s+d.value,0);
  ch.setOption({
    tooltip:{...tip, trigger:'item',
      formatter:p=>`${p.name}<br/><b>${p.value} listings (${p.percent}%)</b>`},
    legend:{bottom:0,left:'center',textStyle:{color:C.MID,fontSize:10},itemWidth:10,itemHeight:10},
    series:[{
      type:'pie', radius:['42%','70%'],
      center:['50%','44%'],
      data: D.furnished,
      label:{show:false},
      emphasis:{scaleSize:4},
      itemStyle:{borderRadius:4,borderColor:'#fff',borderWidth:2},
    }],
    graphic:[{type:'text',left:'center',top:'38%',style:{
      text:total.toLocaleString(),fill:C.DARK,
      font:'bold 20px Inter,sans-serif',
    }},{type:'text',left:'center',top:'47%',style:{
      text:'with data',fill:C.SOFT,font:'11px Inter,sans-serif',
    }}],
  });
})();

// ── 6. Heatmap ────────────────────────────────────────────────────────────
(function(){
  const ch = ec('c-heat');
  const rooms = D.heatmap.rooms;
  const dists = D.heatmap.districts;
  // build full matrix (fill nulls)
  const full = [];
  for(let i=0;i<dists.length;i++)
    for(let j=0;j<rooms.length;j++){
      const pt = D.heatmap.data.find(d=>d[0]===j&&d[1]===i);
      full.push(pt ? [j,i,pt[2],pt[3]] : [j,i,null,0]);
    }
  ch.setOption({
    grid: grid(14,100,12,12),
    tooltip:{...tip, formatter:p=>{
      if(!p.data[2]) return `${dists[p.data[1]]} / ${rooms[p.data[0]]}<br/>No data`;
      return `${dists[p.data[1]]} &amp; ${rooms[p.data[0]]}<br/><b>Median $${p.data[2]}</b><br/>n = ${p.data[3]} listings`;
    }},
    visualMap:{
      min:D.heatmap.min, max:D.heatmap.max,
      calculable:true, orient:'vertical',
      right:8, top:'middle',
      inRange:{color:['#EFF6FF','#BFDBFE','#3B82F6','#1D4ED8','#1E3A8A']},
      textStyle:{color:C.MID,fontSize:10},
      formatter:v=>'$'+Math.round(v),
    },
    xAxis:{type:'category',data:rooms,
      axisLine:{show:false},axisTick:{show:false},
      axisLabel:{color:C.DARK,fontWeight:'600',fontSize:12},
      position:'top',
    },
    yAxis:{type:'category',data:dists,
      axisLine:{show:false},axisTick:{show:false},
      axisLabel:{color:C.MID,fontSize:10.5},
    },
    series:[{
      type:'heatmap',
      data: full.filter(d=>d[2]!==null),
      label:{show:true,
        formatter:p=>`$${p.data[2]}\nn=${p.data[3]}`,
        color:null, // overridden below
        fontSize:11, fontWeight:'600',
      },
      emphasis:{itemStyle:{shadowBlur:8,shadowColor:'rgba(0,0,0,.2)'}},
      itemStyle:{borderRadius:4,borderColor:'#EEF2FF',borderWidth:2},
    }],
  });
  // white label on dark cells
  const opt = ch.getOption();
  opt.series[0].label.color = (params)=>{
    const v = params.data[2];
    return v > D.heatmap.max*0.55 ? '#fff' : C.DARK;
  };
  ch.setOption(opt);
})();

// ── 7. Furnished premium grouped bar ──────────────────────────────────────
(function(){
  const ch = ec('c-fprm');
  const mk = (name, data, color) => ({
    type:'bar', name, data, barGap:'6%', barCategoryGap:'35%',
    itemStyle:{borderRadius:[3,3,0,0],color},
    label:{show:false},
  });
  ch.setOption({
    grid: grid(32,16,36,20),
    tooltip:{...tip, trigger:'axis',
      formatter:params=>{
        let s=`<b>${params[0].axisValueLabel}</b><br/>`;
        params.forEach(p=>{if(p.value)s+=`${p.marker}${p.seriesName}: <b>$${p.value}</b><br/>`;});
        return s;
      }},
    legend:{top:4,right:8,textStyle:{color:C.MID,fontSize:10},itemWidth:10,itemHeight:10},
    xAxis: axX(D.furnished_premium.rooms),
    yAxis: axY('USD/mo'),
    series:[
      mk('Fully Furnished', D.furnished_premium.full,    C.G),
      mk('Partial',         D.furnished_premium.partial, C.A),
      mk('Not stated',      D.furnished_premium.none,    C.S),
    ],
  });
})();

// ── 8. Electricity histogram ──────────────────────────────────────────────
(function(){
  const ch = ec('c-elec');
  if(!D.elec.bins.length){ch.setOption({title:{text:'No data',left:'center',top:'middle',textStyle:{color:C.SOFT}}});return;}
  ch.setOption({
    grid: grid(28,16,36,20),
    tooltip:{...tip, trigger:'axis',
      formatter:p=>`$${p[0].name}/kWh<br/><b>${p[0].value} listings</b>`},
    xAxis: axX(D.elec.bins, 30),
    yAxis: axY('Count'),
    series:[{
      type:'bar', data:D.elec.counts, barWidth:'80%',
      itemStyle:{color:C.A, borderRadius:[3,3,0,0]},
      markLine:{silent:true,animation:false,data:[{
        xAxis:D.elec.median+'',
        lineStyle:{color:C.R,width:2,type:'dashed'},
        label:{formatter:'Median\n$'+D.elec.median,color:C.R,fontSize:10,fontWeight:'600'},
        symbol:'none',
      }]},
    }],
  });
})();

// ── 9. Quality bar ────────────────────────────────────────────────────────
(function(){
  const ch = ec('c-qual');
  const Q = D.quality;
  ch.setOption({
    grid: grid(28,16,36,20),
    tooltip:{...tip, trigger:'axis',formatter:p=>`${p[0].name}<br/><b>${p[0].value} listings</b>`},
    xAxis: axX(['High\n≥0.8','Med\n0.6–0.8','Low\n<0.6']),
    yAxis: axY('Count'),
    series:[{
      type:'bar', data:[
        {value:Q.high, itemStyle:{color:C.G,borderRadius:[4,4,0,0]}},
        {value:Q.med,  itemStyle:{color:C.A,borderRadius:[4,4,0,0]}},
        {value:Q.low,  itemStyle:{color:C.R,borderRadius:[4,4,0,0]}},
      ],
      label:{show:true,position:'top',color:C.MID,fontSize:10,fontWeight:'600'},
    }],
    graphic:[{type:'text',right:12,top:8,style:{
      text:'⚠ '+Q.flagged+' flagged',fill:C.R,
      font:'600 11px Inter,sans-serif',
    }}],
  });
})();
</script>
</body>
</html>
"""


def generate():
    print("Extracting data from database…")
    data = _extract()
    html = _HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Saved → {OUT_PATH}")
    webbrowser.open(f"file://{OUT_PATH}")


def main():
    generate()


if __name__ == "__main__":
    main()
