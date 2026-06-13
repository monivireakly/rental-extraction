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

# ── Canonical district names follow official Cambodia District List 2025 ──────
# Khan (district) canonical names for Phnom Penh:
#   Chamkar Mon | Doun Penh | Prampir Meakkakra | Tuol Kouk | Dangkao
#   Mean Chey   | Russey Keo | Saen Sokh | Pou Saen Chey | Chbar Ampov
#   Chraoy Chongvar | Preaek Pnov | Boeng Keng Kang | Kamboul
# BKK1/BKK2/BKK3 and TTP are sangkats (sub-district), kept as identifiers.

DISTRICT_ALIASES = {
    # Tuol Kouk (official)
    "toul kork":             "Tuol Kouk",
    "toul kok":              "Tuol Kouk",
    "tuol kork":             "Tuol Kouk",
    "uk toul kork":          "Tuol Kouk",

    # BKK sangkats — practical sub-district identifiers
    "bkk1":                  "BKK1",
    "bkk 1":                 "BKK1",
    "bkk":                   "BKK1",
    "bkk area":              "BKK1",
    "boeng keng kang 1":     "BKK1",
    "boeung keng kang 1":    "BKK1",
    "bkk2":                  "BKK2",
    "bkk 2":                 "BKK2",
    "bkk2/3":                "BKK2",
    "bkk3":                  "BKK3",
    "bkk 3":                 "BKK3",
    "boeung keng kang 3":    "BKK3",
    "beung keng kang 3":     "BKK3",
    "beung keng kang 3":     "BKK3",

    # Saen Sokh (official)
    "sen sok":               "Saen Sokh",
    "sensok":                "Saen Sokh",
    "sen sokh":              "Saen Sokh",
    "sensokh":               "Saen Sokh",
    "saen sokh":             "Saen Sokh",
    "teok thla":             "Saen Sokh",
    "tuek thla":             "Saen Sokh",
    "tuek tla":              "Saen Sokh",
    "amory sen sok":         "Saen Sokh",
    "borei senchey":         "Saen Sokh",

    # Toul Tumpung — sangkat in Chamkar Mon
    "toul tumpung":          "Toul Tumpung",
    "toul tumpoung":         "Toul Tumpung",
    "toul tompong":          "Toul Tumpung",
    "toul tompuong":         "Toul Tumpung",
    "toul tompung":          "Toul Tumpung",
    "toul tom pong":         "Toul Tumpung",
    "toul tum poung":        "Toul Tumpung",
    "toul tom poung":        "Toul Tumpung",
    "toul pong":             "Toul Tumpung",
    "ttp":                   "Toul Tumpung",

    # Chamkar Mon (official)
    "chamkar mon":           "Chamkar Mon",
    "chamkarmorn":           "Chamkar Mon",
    "chamkar morn":          "Chamkar Mon",
    "chamkarmon":            "Chamkar Mon",
    "chamkamon":             "Chamkar Mon",

    # Tonle Bassac — sangkat in Chamkar Mon
    "tonle bassac":          "Tonle Bassac",
    "tonle basak":           "Tonle Bassac",
    "tonle bassak":          "Tonle Bassac",

    # Mean Chey (official)
    "meanchey":              "Mean Chey",
    "steung meanchey":       "Mean Chey",
    "stung mean chey":       "Mean Chey",
    "khan mean chey":        "Mean Chey",

    # Chraoy Chongvar (official)
    "chroy changva":         "Chraoy Chongvar",
    "chrouy changva":        "Chraoy Chongvar",
    "chroy changvar":        "Chraoy Chongvar",
    "chroy chongvar":        "Chraoy Chongvar",
    "chongva":               "Chraoy Chongvar",
    "chong var":             "Chraoy Chongvar",
    "chroy chongva":         "Chraoy Chongvar",
    "khan chrouy changva":   "Chraoy Chongvar",

    # Doun Penh (official)
    "daun penh":             "Doun Penh",
    "doun penh":             "Doun Penh",

    # Prampir Meakkakra (official; aka 7 Makara / 7th January)
    "7 makara":              "Prampir Meakkakra",
    "prampir meakkakra":     "Prampir Meakkakra",
    "7th january":           "Prampir Meakkakra",

    # Russey Keo (official)
    "russei keo":            "Russey Keo",

    # Chbar Ampov (official)
    "chbar ampve":           "Chbar Ampov",
    "chbar ompov":           "Chbar Ampov",

    # Pou Saen Chey (official; aka Por Sen Chey)
    "por sen chey":          "Pou Saen Chey",

    # Preaek Pnov (official)
    "preak pnow":            "Preaek Pnov",
    "preak pnov":            "Preaek Pnov",

    # Dangkao (official)
    "dangkor":               "Dangkao",

    # Boeng Keng Kang — the Khan itself (distinct from BKK1/2/3 sangkats)
    "boeng keng kang":       "Boeng Keng Kang",
    "boeung keng kang":      "Boeng Keng Kang",
    "boeng keng kong":       "Boeng Keng Kang",

    # Sangkats
    "boek kak 2":            "Boeng Kok",
    "boeung kak 2":          "Boeng Kok",
    "boeung kak 1":          "Boeng Kok",
    "beung kak 1":           "Boeng Kok",
    "boeng kak 1":           "Boeng Kok",
    "boeung trobek":         "Boeung Trobek",
    "boeng trobek":          "Boeung Trobek",
    "boeng trabaek":         "Boeung Trobek",
    "beong sneur":           "Boeung Snor",
    "beong snor":            "Boeung Snor",
    "boeng snor":            "Boeung Snor",
    "peng huot":             "Boeung Snor",
    "peng houth beurng snor":        "Boeung Snor",
    "borey peng huoth boeung snor":  "Boeung Snor",
    "boeung tumpun":         "Boeung Tumpun",
    "boeung tompun":         "Boeung Tumpun",
    "beong tompun":          "Boeung Tumpun",
    "niroth":                "Nirouth",
    "khos pich":             "Koh Pich",
    "chamkar dong":          "Chamkar Doung",
    "chak ongrae":           "Chak Angrae Leu",
    "chak angrae kroam":     "Chak Angrae Kraom",
    "daeum thkov":           "Phsar Daeum Thkov",
    "khmuonn":               "Khmuon",
    "boeng reang":           "Boeng Reang",
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

PROPERTY_TYPE_ALIASES = {
    # Apartment
    "apartment":             "Apartment",
    "flat":                  "Apartment",
    "unit":                  "Apartment",

    # Condo
    "condo":                 "Condo",
    "condominium":           "Condo",

    # Service Apartment
    "service apartment":     "Service Apartment",
    "serviced apartment":    "Service Apartment",
    "service":               "Service Apartment",

    # Borey
    "borey":                 "Borey",
    "borei":                 "Borey",

    # Villa
    "villa":                 "Villa",
    "house":                 "Villa",

    # Shophouse
    "shophouse":             "Shophouse",
    "shop house":            "Shophouse",

    # Studio
    "studio":                "Studio",
}

PROPERTY_ALIASES = {
    # Arakawa
    "arakawa":                       "Arakawa Residence",
    "arakawa condo":                 "Arakawa Residence",
    "arakawa residence condo":       "Arakawa Residence",

    # Urban Village (Phase 1 vs Phase 2 kept distinct)
    "urban village":                 "Urban Village Phase 1",
    "urban village p1":              "Urban Village Phase 1",
    "urban village phase2":          "Urban Village Phase 2",
    "urban village phase 2":         "Urban Village Phase 2",

    # Parkland / Parkland TK (two distinct buildings)
    "park land":                     "Parkland",
    "park land tk":                  "Parkland TK",

    # Morgan Enmaison
    "morgan":                        "Morgan Enmaison",

    # UK Condo 548
    "condo uk 548":                  "UK Condo 548",
    "condo uk548":                   "UK Condo 548",

    # Yuetai
    "condo yuetai":                  "Yuetai Condo",
    "yue tai":                       "Yuetai Condo",

    # Orient Ritz
    "orient ritz condo":             "Orient Ritz",

    # L Residence BTP
    "condo l btp":                   "L Residence BTP",
    "l btp":                         "L Residence BTP",
    "condo l":                       "L Residence",
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

# Landmark/district substrings that definitively place a listing in Siem Reap
SIEM_REAP_TERMS = [
    "pub street",
    "angkor market",
    "angkor supermarket",
    "sala kamreuk",
    "deum kralanh",
    "taphul",
    "bakheng",
    "heritage walk",
    "wat bo",        # Wat Bo temple, Siem Reap
    "svay dangkum",  # SR commune
    "slor kram",     # SR commune
]

# These contain a SR term as a substring but are in Phnom Penh — checked first
PHNOM_PENH_EXCLUSIONS = [
    "wat botum",   # Wat Botum Park, Phnom Penh (contains "wat bo")
    "chakto mukh", # Sangkat in Daun Penh, Phnom Penh
]


def _is_siem_reap(landmark, district):
    combined = f"{landmark or ''} {district or ''}".lower()
    for excl in PHNOM_PENH_EXCLUSIONS:
        if excl in combined:
            return False
    return any(term in combined for term in SIEM_REAP_TERMS)


def normalise_city(city, landmark, district):
    if city == "Phnom Penh" and _is_siem_reap(landmark, district):
        return "Siem Reap"
    return city


def normalise_property_type(value):
    if not value:
        return None
    canonical = PROPERTY_TYPE_ALIASES.get(value.strip().lower())
    return canonical if canonical else value.strip()


def normalise_property_name(value):
    if not value:
        return None
    canonical = PROPERTY_ALIASES.get(value.strip().lower())
    return canonical if canonical else value.strip()


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
        "SELECT id, city, property_type, property_name, district, landmark, room_type, furnished_status FROM listings"
    ).fetchall()

    changes = []

    for row in rows:
        updates = {}

        new_city = normalise_city(row["city"], row["landmark"], row["district"])
        if new_city != row["city"]:
            updates["city"] = (row["city"], new_city)

        new_ptype = normalise_property_type(row["property_type"])
        if new_ptype != row["property_type"]:
            updates["property_type"] = (row["property_type"], new_ptype)

        new_property = normalise_property_name(row["property_name"])
        if new_property != row["property_name"]:
            updates["property_name"] = (row["property_name"], new_property)

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


def fix_city(apply=False):
    """Standalone pass that only corrects city misclassifications."""
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, city, landmark, district FROM listings WHERE city = 'Phnom Penh'"
    ).fetchall()

    changes = [(row["id"], row["city"]) for row in rows
               if _is_siem_reap(row["landmark"], row["district"])]

    if not changes:
        print("✅ No city corrections needed.")
        conn.close()
        return 0

    print(f"{'APPLY' if apply else 'DRY RUN'} — {len(changes)} listing(s) city → Siem Reap")
    if apply:
        conn.executemany(
            "UPDATE listings SET city = 'Siem Reap' WHERE id = ?",
            [(id_,) for id_, _ in changes],
        )
        conn.commit()
        print(f"✅ Updated {len(changes)} row(s).")
    else:
        print("Run with --apply to write changes.")

    conn.close()
    return len(changes)


if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        level=logging.INFO,
    )
    parser = argparse.ArgumentParser(description="Normalise district, room type, and furnished status in the database.")
    parser.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = parser.parse_args()
    run(apply=args.apply)
