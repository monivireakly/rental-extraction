"""
Normalisation agent — scans the listings table and fixes inconsistent
district names, room types, and furnished status directly in the database.

Usage:
    python normalizer.py           # dry-run: show what would change
    python normalizer.py --apply   # write changes to the database
"""

import argparse
import logging
import sqlite3

from .config import settings

logger = logging.getLogger(__name__)

# ── Canonical maps ────────────────────────────────────────────────────────────

DISTRICT_ALIASES = {
    "toul kok":          "Toul Kork",
    "toul kork":         "Toul Kork",
    "tk":                "Toul Kork",
    "bkk1":              "BKK1",
    "bkk":               "BKK1",
    "boeung keng kang":  "BKK2/3",
    "boung keng kang":   "BKK2/3",
    "bkk3":              "BKK2/3",
    "bkk2":              "BKK2/3",
    "sen sok":           "Sen Sok",
    "sensok":            "Sen Sok",
    "teok thla":         "Sen Sok",
    "tuek thla":         "Sen Sok",
    "toul tumpoung":     "Toul Tumpung",
    "toul tompong":      "Toul Tumpung",
    "toul tom pong":     "Toul Tumpung",
    "ttp":               "Toul Tumpung",
    "tonle bassac":      "Tonle Bassac",
    "chamkarmorn":       "Chamkar Mon",
    "chamkar mon":       "Chamkar Mon",
    "mean chey":         "Meanchey",
    "meanchey":          "Meanchey",
    "steung meanchey":   "Meanchey",
    "chroy changva":     "Chroy Changvar",
    "chroy changvar":    "Chroy Changvar",
    "chroy chongvar":    "Chroy Changvar",
    "daun penh":         "Daun Penh",
    "doun penh":         "Daun Penh",
    "boeng kok":         "Boeng Kok",
    "boeung trobek":     "Boeung Trobek",
    "7 makara":          "7 Makara",
}

ROOM_ALIASES = {
    "studio":    "Studio",
    "1br":       "1BR",
    "1 br":      "1BR",
    "1bedroom":  "1BR",
    "1 bedroom": "1BR",
    "2br":       "2BR",
    "2 br":      "2BR",
    "2br1ba":    "2BR",
    "2br2ba":    "2BR",
    "2br+1":     "2BR",
    "2bedroom":  "2BR",
    "2 bedroom": "2BR",
    "3br":       "3BR",
    "3 br":      "3BR",
    "3bedroom":  "3BR",
    "3 bedroom": "3BR",
    "4br":       "4BR",
    "4 br":      "4BR",
    "4bedroom":  "4BR",
    "4 bedroom": "4BR",
    "5br":       "5BR",
    "6br":       "6BR",
}

FURNISHED_ALIASES = {
    "fully furnished":   "Full",
    "full furnished":    "Full",
    "fully":             "Full",
    "full":              "Full",
    "partially":         "Partial",
    "semi-furnished":    "Partial",
    "semi furnished":    "Partial",
    "unfurnished":       "Unfurnished",
    "un-furnished":      "Unfurnished",
    "empty":             "Unfurnished",
}


def normalise_district(value):
    if not value:
        return None
    canonical = DISTRICT_ALIASES.get(value.strip().lower())
    return canonical if canonical else value.strip()


def normalise_room(value):
    if not value:
        return None
    canonical = ROOM_ALIASES.get(value.strip().lower())
    return canonical if canonical else value.strip()


def normalise_furnished(value):
    if not value:
        return None
    canonical = FURNISHED_ALIASES.get(value.strip().lower())
    return canonical if canonical else value.strip()


def run(apply=False):
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, district, room_type, furnished_status FROM listings"
    ).fetchall()

    changes = []

    for row in rows:
        updates = {}

        new_district = normalise_district(row["district"])
        if new_district != row["district"]:
            updates["district"] = (row["district"], new_district)

        new_room = normalise_room(row["room_type"])
        if new_room != row["room_type"]:
            updates["room_type"] = (row["room_type"], new_room)

        new_furnished = normalise_furnished(row["furnished_status"])
        if new_furnished != row["furnished_status"]:
            updates["furnished_status"] = (row["furnished_status"], new_furnished)

        if updates:
            changes.append({"id": row["id"], "updates": updates})

    if not changes:
        print("✅ Database is already clean — nothing to normalise.")
        conn.close()
        return

    print(f"{'APPLY' if apply else 'DRY RUN'} — {len(changes)} listing(s) need normalisation:\n")

    field_stats = {}
    for change in changes:
        for field, (old, new) in change["updates"].items():
            field_stats.setdefault(field, []).append((old, new))
            print(f"  [{field}]  {repr(old):30s} → {repr(new)}")

    print()
    print("── Summary ──────────────────────────────────")
    for field, pairs in field_stats.items():
        unique = {(o, n) for o, n in pairs}
        print(f"  {field}: {len(pairs)} row(s) across {len(unique)} unique mapping(s)")

    if not apply:
        print("\nRun with --apply to write these changes to the database.")
        conn.close()
        return

    cursor = conn.cursor()
    for change in changes:
        set_clause = ", ".join(f"{f} = ?" for f in change["updates"])
        values = [new for _, new in change["updates"].values()]
        values.append(change["id"])
        cursor.execute(f"UPDATE listings SET {set_clause} WHERE id = ?", values)

    conn.commit()
    conn.close()
    print(f"\n✅ Applied {len(changes)} update(s) to the database.")


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )
    parser = argparse.ArgumentParser(description="Normalise district, room type, and furnished status in the database.")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = parser.parse_args()
    run(apply=args.apply)
