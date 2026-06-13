"""
State-of-the-art rental market dashboard.
Produces data/insights.png.

Usage:
    python -m rental.insights
"""

import os
import sqlite3
import warnings
from collections import defaultdict

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import numpy as np

from .normalizer import normalise_district, normalise_room, normalise_furnished
from .config import settings

warnings.filterwarnings("ignore")

DB_PATH  = settings.database_path
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "insights.png")

# ── Design tokens ──────────────────────────────────────────────────────────────
BG    = "#F8FAFC"
CARD  = "#FFFFFF"
LINE  = "#E2E8F0"
DARK  = "#0F172A"
MID   = "#475569"
SOFT  = "#94A3B8"

BLUE   = "#3B82F6"
GREEN  = "#10B981"
AMBER  = "#F59E0B"
RED    = "#EF4444"
PURPLE = "#8B5CF6"
PINK   = "#EC4899"
TEAL   = "#14B8A6"
GRAY   = "#CBD5E1"

PTYPE_PAL = {
    "Condo":             BLUE,
    "Apartment":         GREEN,
    "Service Apartment": PURPLE,
    "Borey":             AMBER,
    "Villa":             RED,
    "Shophouse":         TEAL,
    "Studio":            PINK,
    "Unknown":           GRAY,
}

ROOM_ORDER = ["Studio", "1BR", "2BR", "3BR", "4BR+"]
ROOM_PAL   = [PURPLE, BLUE, GREEN, AMBER, RED]

FURN_PAL = {"Full": GREEN, "Partial": AMBER, "Unfurnished": SOFT}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _style(ax, title="", xlabel="", ylabel=""):
    ax.set_facecolor(CARD)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(LINE)
    ax.tick_params(colors=MID, labelsize=8)
    if xlabel:
        ax.set_xlabel(xlabel, color=MID, fontsize=8)
    if ylabel:
        ax.set_ylabel(ylabel, color=MID, fontsize=8)
    if title:
        ax.set_title(title, fontsize=10, fontweight="bold", color=DARK, pad=9)


def _kpi(ax, value, label, sub, accent):
    ax.set_facecolor(CARD)
    ax.axis("off")
    bar = mpatches.FancyBboxPatch(
        (0, 0.82), 1, 0.18,
        boxstyle="square,pad=0",
        fc=accent, ec="none",
        transform=ax.transAxes, clip_on=False, zorder=2,
    )
    ax.add_patch(bar)
    ax.text(0.5, 0.91, label, ha="center", va="center", fontsize=8.5,
            fontweight="bold", color="white", transform=ax.transAxes, zorder=3)
    ax.text(0.5, 0.52, value, ha="center", va="center", fontsize=21,
            fontweight="bold", color=DARK, transform=ax.transAxes)
    ax.text(0.5, 0.18, sub, ha="center", va="center", fontsize=8,
            color=SOFT, transform=ax.transAxes)
    for sp in ax.spines.values():
        sp.set_edgecolor(LINE)


# ── Data loading ───────────────────────────────────────────────────────────────
def load_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT district, room_type, furnished_status, property_type,
               rent_usd, electricity_per_kwh, water_per_m3,
               extraction_confidence, needs_review, posted_at
        FROM listings
    """).fetchall()

    monthly = conn.execute("""
        SELECT strftime('%Y-%m', posted_at) mo, COUNT(*) n
        FROM listings WHERE posted_at IS NOT NULL
        GROUP BY 1 ORDER BY 1
    """).fetchall()

    conn.close()

    data = []
    for r in rows:
        room = normalise_room(r["room_type"])
        if room and room not in ("Studio", "1BR", "2BR", "3BR"):
            room = "4BR+"
        ptype = r["property_type"] or "Unknown"
        if ptype == "null":
            ptype = "Unknown"
        data.append({
            "district": normalise_district(r["district"]),
            "room":     room,
            "furnished": normalise_furnished(r["furnished_status"]),
            "ptype":    ptype,
            "rent":     r["rent_usd"],
            "elec":     r["electricity_per_kwh"],
            "conf":     r["extraction_confidence"] or 0.0,
            "review":   bool(r["needs_review"]),
        })

    return data, [dict(r) for r in monthly]


# ── Main plot ──────────────────────────────────────────────────────────────────
def plot(data, monthly):
    n     = len(data)
    rents = [d["rent"] for d in data if d["rent"] and 0 < d["rent"] < 5000]

    # ── Figure + grid ──────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(22, 26), facecolor=BG)
    fig.text(0.04, 0.985, "Phnom Penh Rental Market — Intelligence Report",
             fontsize=20, fontweight="bold", color=DARK, va="top")
    fig.text(0.04, 0.972,
             f"{n:,} listings  ·  Jan – Jun 2026  ·  Claude-extracted, SQLite-backed",
             fontsize=10.5, color=MID, va="top")

    gs = gridspec.GridSpec(
        5, 4,
        figure=fig,
        height_ratios=[0.9, 2.2, 2.1, 2.4, 1.9],
        hspace=0.55, wspace=0.38,
        left=0.05, right=0.97,
        top=0.96, bottom=0.03,
    )

    # ── Row 0: KPI tiles ───────────────────────────────────────────────────────
    kax = [fig.add_subplot(gs[0, i]) for i in range(4)]
    med  = float(np.median(rents))
    avg  = float(np.mean(rents))
    hiq  = sum(1 for d in data if d["conf"] >= 0.8) / n * 100

    dist_counts = defaultdict(int)
    for d in data:
        if d["district"]:
            dist_counts[d["district"]] += 1
    top_dist = max(dist_counts, key=dist_counts.get, default="—")

    _kpi(kax[0], f"{n:,}", "Total Listings", "Jan – Jun 2026", BLUE)
    _kpi(kax[1], f"${avg:.0f}", "Avg Rent / mo", f"Median  ${med:.0f}", GREEN)
    _kpi(kax[2], top_dist, "Top District", f"{dist_counts[top_dist]:,} listings", AMBER)
    _kpi(kax[3], f"{hiq:.0f}%", "High Confidence", "extraction score ≥ 0.8", PURPLE)

    # ── Row 1 left (span 2): Rent distribution ────────────────────────────────
    ax_hist = fig.add_subplot(gs[1, :2])
    p10, p25, p50, p75, p90 = np.percentile(rents, [10, 25, 50, 75, 90])
    ax_hist.hist(rents, bins=42, color=BLUE, alpha=0.82, edgecolor="white", linewidth=0.4, zorder=2)
    ax_hist.axvspan(p25, p75, alpha=0.13, color=GREEN, zorder=1, label=f"IQR  ${p25:.0f} – ${p75:.0f}")
    for val, label, col, ls in [
        (p10, "P10", SOFT, ":"), (p50, "P50", GREEN, "--"),
        (avg, "Mean", AMBER, "--"), (p90, "P90", RED, ":"),
    ]:
        ax_hist.axvline(val, color=col, linestyle=ls, linewidth=1.6, zorder=3)
        ax_hist.text(val + 12, ax_hist.get_ylim()[1] * 0.88,
                     f"{label}\n${val:.0f}", fontsize=7, color=col, va="top", zorder=4)
    ax_hist.legend(fontsize=8, framealpha=0.7)
    _style(ax_hist, "Rent Distribution  (USD / month)", "USD / month", "Listings")

    # ── Row 1 col 2: Avg rent by room type (with error bars) ──────────────────
    ax_room = fig.add_subplot(gs[1, 2])
    room_vals = {r: [d["rent"] for d in data if d["room"] == r and d["rent"]] for r in ROOM_ORDER}
    r_avg = [float(np.mean(v)) if v else 0 for v in room_vals.values()]
    r_std = [float(np.std(v))  if len(v) > 1 else 0 for v in room_vals.values()]
    r_cnt = [len(v) for v in room_vals.values()]
    bars_r = ax_room.bar(ROOM_ORDER, r_avg, color=ROOM_PAL, edgecolor="white", linewidth=0.7, zorder=3)
    ax_room.errorbar(ROOM_ORDER, r_avg, yerr=r_std, fmt="none", color=DARK,
                     capsize=4, linewidth=1.2, zorder=4)
    for bar, avg_v, cnt in zip(bars_r, r_avg, r_cnt):
        if avg_v > 0:
            ax_room.text(bar.get_x() + bar.get_width() / 2, avg_v + 25,
                         f"${avg_v:.0f}\n({cnt})", ha="center", fontsize=7.5,
                         color=DARK, fontweight="bold", va="bottom")
    ax_room.set_ylim(0, max(r_avg) * 1.3 if any(r_avg) else 1)
    _style(ax_room, "Avg Rent by Room Type", "", "USD / month")

    # ── Row 1 col 3: Monthly volume trend ─────────────────────────────────────
    ax_trend = fig.add_subplot(gs[1, 3])
    if monthly:
        mo_labels = [m["mo"][5:] + " '" + m["mo"][2:4] for m in monthly]
        mo_counts = [m["n"] for m in monthly]
        xs = range(len(mo_counts))
        ax_trend.fill_between(xs, mo_counts, alpha=0.18, color=BLUE)
        ax_trend.plot(xs, mo_counts, color=BLUE, linewidth=2.5, marker="o",
                      markersize=5.5, zorder=3)
        for i, (lbl, cnt) in enumerate(zip(mo_labels, mo_counts)):
            ax_trend.text(i, cnt + max(mo_counts) * 0.04, str(cnt),
                          ha="center", fontsize=8, color=DARK, fontweight="bold")
        ax_trend.set_xticks(list(xs))
        ax_trend.set_xticklabels(mo_labels, fontsize=7.5, rotation=20, ha="right")
        # Flag last month as partial
        ax_trend.axvline(len(mo_counts) - 1, color=RED, linestyle=":", linewidth=1.2, alpha=0.7)
        ax_trend.text(len(mo_counts) - 1.05, max(mo_counts) * 0.45,
                      "partial\nmonth", fontsize=7, color=RED, ha="right", style="italic")
    _style(ax_trend, "Listing Volume by Month", "", "Count")

    # ── Row 2 left (span 2): Top districts ────────────────────────────────────
    ax_dist = fig.add_subplot(gs[2, :2])
    top14 = sorted(dist_counts.items(), key=lambda x: x[1], reverse=True)[:14]
    d_labels, d_counts = zip(*top14)
    d_colors = [BLUE] + [SOFT] * (len(d_labels) - 1)
    bars_d = ax_dist.barh(
        list(reversed(d_labels)), list(reversed(d_counts)),
        color=list(reversed(d_colors)), edgecolor="white", linewidth=0.4,
    )
    ax_dist.bar_label(bars_d, padding=4, fontsize=8, color=DARK)
    ax_dist.set_xlim(0, max(d_counts) * 1.20)
    _style(ax_dist, "Listings by District  (top 14)", "Count", "")

    # ── Row 2 col 2: Property type donut ──────────────────────────────────────
    ax_pt = fig.add_subplot(gs[2, 2])
    pt_count = defaultdict(int)
    for d in data:
        if d["ptype"] != "Unknown":
            pt_count[d["ptype"]] += 1
    pt_items = sorted(pt_count.items(), key=lambda x: x[1], reverse=True)
    pt_vals   = [v for _, v in pt_items]
    pt_labels = [k for k, _ in pt_items]
    pt_colors = [PTYPE_PAL.get(k, GRAY) for k in pt_labels]
    ax_pt.pie(pt_vals, colors=pt_colors, startangle=90,
              wedgeprops={"edgecolor": "white", "linewidth": 2, "width": 0.58})
    ax_pt.text(0, 0, str(sum(pt_vals)), ha="center", va="center",
               fontsize=18, fontweight="bold", color=DARK)
    ax_pt.text(0, -0.25, "typed\nlistings", ha="center", va="center", fontsize=7.5, color=MID)
    handles_pt = [
        mpatches.Patch(color=PTYPE_PAL.get(k, GRAY), label=f"{k}  ({v})")
        for k, v in pt_items
    ]
    ax_pt.legend(handles=handles_pt, fontsize=7, loc="lower center",
                 bbox_to_anchor=(0.5, -0.42), ncol=2, framealpha=0)
    ax_pt.set_title("Property Types", fontsize=10, fontweight="bold", color=DARK, pad=9)

    # ── Row 2 col 3: Furnished status donut ───────────────────────────────────
    ax_furn = fig.add_subplot(gs[2, 3])
    furn_order = ["Full", "Partial", "Unfurnished"]
    furn_cnt   = {k: sum(1 for d in data if d["furnished"] == k) for k in furn_order}
    furn_vals2 = [furn_cnt[k] for k in furn_order if furn_cnt[k] > 0]
    furn_keys2 = [k for k in furn_order if furn_cnt[k] > 0]
    furn_cols2 = [FURN_PAL[k] for k in furn_keys2]
    furn_total = sum(furn_vals2)
    ax_furn.pie(furn_vals2, colors=furn_cols2, startangle=90,
                wedgeprops={"edgecolor": "white", "linewidth": 2, "width": 0.58})
    ax_furn.text(0, 0, str(furn_total), ha="center", va="center",
                 fontsize=18, fontweight="bold", color=DARK)
    ax_furn.text(0, -0.25, "w/ data", ha="center", va="center", fontsize=7.5, color=MID)
    handles_f = [
        mpatches.Patch(color=FURN_PAL[k], label=f"{k}  ({furn_cnt[k]},  {furn_cnt[k]/furn_total*100:.0f}%)")
        for k in furn_keys2
    ]
    ax_furn.legend(handles=handles_f, fontsize=7.5, loc="lower center",
                   bbox_to_anchor=(0.5, -0.32), ncol=1, framealpha=0)
    ax_furn.set_title("Furnished Status", fontsize=10, fontweight="bold", color=DARK, pad=9)

    # ── Row 3 (full width): District × Room heatmap ───────────────────────────
    ax_heat = fig.add_subplot(gs[3, :])
    heat_rooms = ["Studio", "1BR", "2BR", "3BR"]
    heat_dists = [lbl for lbl, _ in top14[:10]]

    matrix = np.full((len(heat_dists), len(heat_rooms)), np.nan)
    sample  = np.zeros((len(heat_dists), len(heat_rooms)), dtype=int)
    for i, dist in enumerate(heat_dists):
        for j, room in enumerate(heat_rooms):
            vals = [d["rent"] for d in data if d["district"] == dist and d["room"] == room and d["rent"]]
            if vals:
                matrix[i, j] = float(np.median(vals))
                sample[i, j] = len(vals)

    # mask empty cells so colormap skips them
    masked = np.ma.masked_invalid(matrix)
    im = ax_heat.imshow(masked, cmap="YlOrRd", aspect="auto", vmin=np.nanmin(matrix), vmax=np.nanmax(matrix))

    ax_heat.set_xticks(range(len(heat_rooms)))
    ax_heat.set_xticklabels(heat_rooms, fontsize=10, color=DARK, fontweight="bold")
    ax_heat.set_yticks(range(len(heat_dists)))
    ax_heat.set_yticklabels(heat_dists, fontsize=9.5, color=DARK)
    ax_heat.tick_params(length=0)

    thresh = np.nanpercentile(matrix, 60)
    for i in range(len(heat_dists)):
        for j in range(len(heat_rooms)):
            val = matrix[i, j]
            if not np.isnan(val):
                text_color = "white" if val > thresh else DARK
                ax_heat.text(j, i, f"${val:.0f}\n(n={sample[i,j]})",
                             ha="center", va="center", fontsize=8.5,
                             color=text_color, fontweight="bold")
            else:
                ax_heat.text(j, i, "—", ha="center", va="center",
                             fontsize=9, color=SOFT)

    cb = plt.colorbar(im, ax=ax_heat, orientation="vertical", fraction=0.015, pad=0.01)
    cb.ax.tick_params(labelsize=8)
    cb.set_label("Median Rent  (USD / mo)", fontsize=8.5, color=MID)
    ax_heat.set_facecolor(CARD)
    ax_heat.set_title(
        "Median Rent Heatmap  ·  District × Room Type  (n = sample size)",
        fontsize=11, fontweight="bold", color=DARK, pad=10,
    )

    # ── Row 4 left (span 2): Furnished premium grouped bar ────────────────────
    ax_fp = fig.add_subplot(gs[4, :2])
    furn_types3 = ["Full", "Partial", None]
    furn_lbls3  = ["Fully Furnished", "Partial", "Not stated"]
    furn_cols3  = [GREEN, AMBER, GRAY]
    x3 = np.arange(len(ROOM_ORDER))
    w3 = 0.26
    for i, (furn, lbl, col) in enumerate(zip(furn_types3, furn_lbls3, furn_cols3)):
        avgs3 = []
        for room in ROOM_ORDER:
            vals3 = [d["rent"] for d in data if d["room"] == room and d["furnished"] == furn and d["rent"]]
            avgs3.append(float(np.mean(vals3)) if vals3 else 0)
        offset = (i - 1) * w3
        b3 = ax_fp.bar(x3 + offset, avgs3, w3, label=lbl, color=col,
                        edgecolor="white", linewidth=0.4, alpha=0.92)
    ax_fp.set_xticks(x3)
    ax_fp.set_xticklabels(ROOM_ORDER, fontsize=9)
    ax_fp.legend(fontsize=8, framealpha=0.7)
    _style(ax_fp, "Avg Rent by Room Type & Furnished Status", "", "USD / month")

    # ── Row 4 col 2: Electricity rate distribution ────────────────────────────
    ax_elec = fig.add_subplot(gs[4, 2])
    elec_vals = [d["elec"] for d in data if d["elec"] and 0.05 < d["elec"] < 0.5]
    if elec_vals:
        ax_elec.hist(elec_vals, bins=16, color=AMBER, edgecolor="white", linewidth=0.4, alpha=0.9)
        e_med = float(np.median(elec_vals))
        ax_elec.axvline(e_med, color=RED, linestyle="--", linewidth=1.6)
        ax_elec.text(e_med + 0.003, ax_elec.get_ylim()[1] * 0.88,
                     f"Median\n${e_med:.3f}", fontsize=7.5, color=RED, va="top")
        ax_elec.text(0.97, 0.92, f"n = {len(elec_vals)}",
                     transform=ax_elec.transAxes, ha="right", fontsize=8, color=MID)
    _style(ax_elec, "Electricity Rate  ($/kWh)", "$/kWh", "Count")

    # ── Row 4 col 3: Extraction quality ───────────────────────────────────────
    ax_qual = fig.add_subplot(gs[4, 3])
    buckets = {
        "High\n≥ 0.8":   sum(1 for d in data if d["conf"] >= 0.8),
        "Med\n0.6–0.8":  sum(1 for d in data if 0.6 <= d["conf"] < 0.8),
        "Low\n< 0.6":    sum(1 for d in data if d["conf"] < 0.6),
    }
    b_colors = [GREEN, AMBER, RED]
    bars_q = ax_qual.bar(buckets.keys(), buckets.values(), color=b_colors,
                          edgecolor="white", linewidth=0.7)
    ax_qual.bar_label(bars_q, padding=4, fontsize=9, color=DARK, fontweight="bold")
    review_n = sum(1 for d in data if d["review"])
    ax_qual.text(0.97, 0.96,
                 f"⚠  {review_n} flagged\nfor review",
                 transform=ax_qual.transAxes, ha="right", va="top",
                 fontsize=8, color=RED,
                 bbox=dict(boxstyle="round,pad=0.3", fc=CARD, ec=RED, alpha=0.85))
    _style(ax_qual, "Extraction Quality", "", "Count")

    # ── Export ────────────────────────────────────────────────────────────────
    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    plt.savefig(OUT_PATH, dpi=150, bbox_inches="tight", facecolor=BG)
    print(f"✅ Saved → {OUT_PATH}")
    plt.show()


def main():
    data, monthly = load_data()
    print(f"Loaded {len(data):,} listings")
    plot(data, monthly)


if __name__ == "__main__":
    main()
