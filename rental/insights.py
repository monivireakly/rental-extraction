"""
Generate a visual insights dashboard from the listings database.
Saves to data/insights.png and opens it automatically.

Usage:
    python -m rental.insights
"""

import os
import sqlite3
import warnings

import matplotlib.pyplot as plt
import numpy as np

from .normalizer import normalise_district, normalise_room, normalise_furnished
from .config import settings

warnings.filterwarnings("ignore")

DB_PATH = settings.database_path
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "insights.png")

ROOM_ORDER = ["Studio", "1BR", "2BR", "3BR", "4BR"]

COLORS = {
    "Studio": "#6C9BD2",
    "1BR":    "#5BAD8F",
    "2BR":    "#F0A500",
    "3BR":    "#E05C5C",
    "4BR":    "#9B6BB5",
    "other":  "#AAAAAA",
}

BG = "#F7F7F7"
ACCENT = "#2C3E50"


def load_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT district, room_type, furnished_status,
               rent_usd, management_fee_usd,
               electricity_per_kwh, water_per_m3,
               extraction_confidence, needs_review
        FROM listings
    """).fetchall()
    conn.close()

    data = []
    for r in rows:
        room = normalise_room(r["room_type"]) or "Other"
        data.append({
            "district":    normalise_district(r["district"]),
            "room_type":   room if room in ROOM_ORDER else "Other",
            "furnished":   normalise_furnished(r["furnished_status"]),
            "rent":        r["rent_usd"],
            "mgmt":        r["management_fee_usd"],
            "elec":        r["electricity_per_kwh"],
            "water":       r["water_per_m3"],
            "confidence":  r["extraction_confidence"],
            "needs_review": r["needs_review"],
        })
    return data


def plot(data):
    fig = plt.figure(figsize=(18, 14), facecolor=BG)
    fig.suptitle("Phnom Penh Rental Listings — Dashboard", fontsize=18,
                 fontweight="bold", color=ACCENT, y=0.98)

    gs = fig.add_gridspec(3, 3, hspace=0.45, wspace=0.35,
                          left=0.07, right=0.97, top=0.93, bottom=0.06)

    ax1 = fig.add_subplot(gs[0, 0])
    rooms = [d["room_type"] for d in data]
    room_counts = {r: rooms.count(r) for r in ROOM_ORDER + ["Other"] if rooms.count(r) > 0}
    bars = ax1.bar(room_counts.keys(), room_counts.values(),
                   color=[COLORS.get(k, COLORS["other"]) for k in room_counts],
                   edgecolor="white", linewidth=0.8)
    ax1.bar_label(bars, padding=3, fontsize=9, color=ACCENT)
    ax1.set_title("Listings by Room Type", fontweight="bold", color=ACCENT)
    ax1.set_ylabel("Count")
    ax1.set_facecolor(BG)
    ax1.spines[["top", "right"]].set_visible(False)

    ax2 = fig.add_subplot(gs[0, 1])
    rents = [d["rent"] for d in data if d["rent"] and d["rent"] <= 3000]
    ax2.hist(rents, bins=24, color="#6C9BD2", edgecolor="white", linewidth=0.6)
    ax2.axvline(np.mean(rents), color="#E05C5C", linestyle="--", linewidth=1.5,
                label=f"Avg ${np.mean(rents):.0f}")
    ax2.axvline(np.median(rents), color="#5BAD8F", linestyle="--", linewidth=1.5,
                label=f"Median ${np.median(rents):.0f}")
    ax2.set_title("Rent Distribution (USD/mo)", fontweight="bold", color=ACCENT)
    ax2.set_xlabel("USD")
    ax2.set_ylabel("Count")
    ax2.legend(fontsize=8)
    ax2.set_facecolor(BG)
    ax2.spines[["top", "right"]].set_visible(False)

    ax3 = fig.add_subplot(gs[0, 2])
    avg_rents = {r: np.mean([d["rent"] for d in data if d["room_type"] == r and d["rent"]])
                 for r in ROOM_ORDER if any(d["room_type"] == r and d["rent"] for d in data)}
    bars3 = ax3.bar(avg_rents.keys(), avg_rents.values(),
                    color=[COLORS.get(k) for k in avg_rents],
                    edgecolor="white", linewidth=0.8)
    ax3.bar_label(bars3, fmt="$%.0f", padding=3, fontsize=9, color=ACCENT)
    ax3.set_title("Avg Rent by Room Type", fontweight="bold", color=ACCENT)
    ax3.set_ylabel("USD / month")
    ax3.set_facecolor(BG)
    ax3.spines[["top", "right"]].set_visible(False)

    ax4 = fig.add_subplot(gs[1, :2])
    dist_counts = {}
    for d in data:
        if d["district"]:
            dist_counts[d["district"]] = dist_counts.get(d["district"], 0) + 1
    top10 = sorted(dist_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    labels, counts = zip(*top10)
    bars4 = ax4.barh(list(reversed(labels)), list(reversed(counts)),
                     color="#6C9BD2", edgecolor="white", linewidth=0.8)
    ax4.bar_label(bars4, padding=3, fontsize=9, color=ACCENT)
    ax4.set_title("Listings by District (top 10)", fontweight="bold", color=ACCENT)
    ax4.set_xlabel("Count")
    ax4.set_facecolor(BG)
    ax4.spines[["top", "right"]].set_visible(False)

    ax5 = fig.add_subplot(gs[1, 2])
    top_districts = [l for l, _ in top10[:6]]
    box_data = [(d, [r["rent"] for r in data if r["district"] == d and r["rent"]])
                for d in top_districts]
    box_data = [(d, v) for d, v in box_data if v]
    if box_data:
        bp = ax5.boxplot([v for _, v in box_data], vert=True, patch_artist=True,
                         medianprops={"color": "#E05C5C", "linewidth": 2})
        for patch in bp["boxes"]:
            patch.set_facecolor("#6C9BD2")
            patch.set_alpha(0.7)
        ax5.set_xticks(range(1, len(box_data) + 1))
        ax5.set_xticklabels([d for d, _ in box_data], rotation=30, ha="right", fontsize=8)
    ax5.set_title("Rent Range by District", fontweight="bold", color=ACCENT)
    ax5.set_ylabel("USD / month")
    ax5.set_facecolor(BG)
    ax5.spines[["top", "right"]].set_visible(False)

    ax6 = fig.add_subplot(gs[2, 0])
    furn_counts = {}
    for d in data:
        key = d["furnished"] or "Unknown"
        furn_counts[key] = furn_counts.get(key, 0) + 1
    ax6.pie(furn_counts.values(), labels=furn_counts.keys(), autopct="%1.0f%%",
            colors=["#5BAD8F", "#F0A500", "#AAAAAA"],
            startangle=140, wedgeprops={"edgecolor": "white", "linewidth": 1.5})
    ax6.set_title("Furnished Status", fontweight="bold", color=ACCENT)

    ax7 = fig.add_subplot(gs[2, 1])
    elec_vals = [d["elec"] for d in data if d["elec"] and 0 < d["elec"] < 1]
    water_vals = [d["water"] for d in data if d["water"] and 0 < d["water"] < 5]
    ax7.hist(elec_vals, bins=12, alpha=0.75, color="#F0A500",
             label=f"Electricity (n={len(elec_vals)})", edgecolor="white")
    ax7_twin = ax7.twinx()
    ax7_twin.hist(water_vals, bins=10, alpha=0.55, color="#6C9BD2",
                  label=f"Water (n={len(water_vals)})", edgecolor="white")
    ax7.set_xlabel("Rate")
    ax7.set_ylabel("Count (electricity)", color="#F0A500")
    ax7_twin.set_ylabel("Count (water)", color="#6C9BD2")
    ax7.set_title("Utility Rates Distribution", fontweight="bold", color=ACCENT)
    lines1, labels1 = ax7.get_legend_handles_labels()
    lines2, labels2 = ax7_twin.get_legend_handles_labels()
    ax7.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper right")
    ax7.set_facecolor(BG)
    ax7.spines[["top"]].set_visible(False)

    ax8 = fig.add_subplot(gs[2, 2])
    conf_vals = [d["confidence"] for d in data if d["confidence"] is not None]
    counts = [
        sum(1 for c in conf_vals if c >= 0.9),
        sum(1 for c in conf_vals if 0.7 <= c < 0.9),
        sum(1 for c in conf_vals if c < 0.7),
    ]
    bars8 = ax8.bar(["High\n(≥0.9)", "Medium\n(0.7–0.9)", "Low\n(<0.7)"], counts,
                    color=["#5BAD8F", "#F0A500", "#E05C5C"],
                    edgecolor="white", linewidth=0.8)
    ax8.bar_label(bars8, padding=3, fontsize=9, color=ACCENT)
    ax8.set_title("Extraction Confidence", fontweight="bold", color=ACCENT)
    ax8.set_ylabel("Count")
    ax8.set_facecolor(BG)
    ax8.spines[["top", "right"]].set_visible(False)

    os.makedirs(os.path.dirname(os.path.abspath(OUT_PATH)), exist_ok=True)
    plt.savefig(OUT_PATH, dpi=150, bbox_inches="tight", facecolor=BG)
    print(f"Saved → {OUT_PATH}")
    plt.show()


def main():
    data = load_data()
    print(f"Loaded {len(data)} listings")
    plot(data)


if __name__ == "__main__":
    main()
