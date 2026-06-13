#!/usr/bin/env python3
"""
Smoke driver for rental-extraction.
Exercises the full extraction pipeline: DB init → Claude extract → DB insert → stats.
Run from the repo root with: python3 .claude/skills/run-rental-extraction/driver.py
Requires .env with ANTHROPIC_API_KEY set.
"""

import hashlib
import json
import os
import sys
import uuid

# ensure `rental` package is importable regardless of CWD
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

SAMPLE_LISTING = """Sky Villa Condo BKK1 For Rent
Location: BKK1, Daun Penh, Phnom Penh
Price: 550USD/month
Type: 2 Bedrooms
Floor: F5-12
Fully Furnished
Management Fee: 30USD
Electric: 0.25/KW
Water: 0.8/M3
Car Parking: Free"""


def run_smoke():
    from rental.db import init_db, insert_raw_listing, listing_exists, insert_listing, get_connection
    from rental.extractor import extract_listing

    print("=== rental-extraction smoke driver ===\n")

    print("1. DB init...")
    init_db()
    print("   OK\n")

    print("2. Extraction (calls Claude API)...")
    result = extract_listing(SAMPLE_LISTING)
    print("   Result:", json.dumps(result, indent=4))
    assert result.get("rent_usd") == 550, f"unexpected rent_usd: {result.get('rent_usd')}"
    assert result.get("district") == "Daun Penh", f"unexpected district: {result.get('district')}"
    assert result.get("extraction_confidence", 0) > 0.5, "confidence too low"
    print("   assertions passed\n")

    print("3. DB insert (raw + listing)...")
    h = hashlib.md5(SAMPLE_LISTING.encode()).hexdigest()
    if not listing_exists(h):
        insert_raw_listing(h, SAMPLE_LISTING)
    lid = str(uuid.uuid4())
    insert_listing(lid, h, result)
    print(f"   listing id: {lid}\n")

    print("4. DB stats...")
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
    raw = conn.execute("SELECT COUNT(*) FROM raw_listings").fetchone()[0]
    rent_stats = conn.execute(
        "SELECT MIN(rent_usd), MAX(rent_usd), ROUND(AVG(rent_usd),0) FROM listings WHERE rent_usd IS NOT NULL"
    ).fetchone()
    conn.close()
    print(f"   raw_listings: {raw}")
    print(f"   listings:     {total}")
    print(f"   rent USD — min:{rent_stats[0]}  max:{rent_stats[1]}  avg:{rent_stats[2]}\n")

    print("5. extractor CLI (python3 -m rental.extractor)...")
    import subprocess
    proc = subprocess.run(
        [sys.executable, "-m", "rental.extractor", "1BR condo BKK1 Phnom Penh 400USD/month"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"extractor CLI failed:\n{proc.stderr}"
    cli_result = json.loads(proc.stdout)
    assert cli_result.get("rent_usd") == 400, f"CLI unexpected rent_usd: {cli_result.get('rent_usd')}"
    print("   CLI output:", json.dumps(cli_result, indent=4))
    print("   assertions passed\n")

    print("=== all checks passed ===")


if __name__ == "__main__":
    run_smoke()
