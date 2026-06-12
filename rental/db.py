import json
import logging
import os
import sqlite3
import uuid

from .config import settings

logger = logging.getLogger(__name__)


def get_connection():
    path = settings.database_path
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return sqlite3.connect(path)


def _migrate(conn):
    """Add columns introduced after the initial schema without recreating tables."""
    def add_if_missing(table, column, definition):
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            logger.info("Migrated: added %s.%s", table, column)

    add_if_missing("raw_listings", "posted_at",     "DATETIME")
    add_if_missing("listings",     "posted_at",     "DATETIME")
    add_if_missing("channels",     "default_pages", "INTEGER DEFAULT 3")
    conn.commit()


def init_db():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS raw_listings (
                listing_hash        TEXT PRIMARY KEY,
                ingested_at         DATETIME DEFAULT (datetime('now')),
                posted_at           DATETIME,
                source_platform     TEXT DEFAULT 'telegram',
                raw_text            TEXT NOT NULL,
                is_processed        INTEGER DEFAULT 0,
                processed_at        DATETIME,
                extraction_attempts INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS listings (
                id                    TEXT PRIMARY KEY,
                listing_hash          TEXT REFERENCES raw_listings(listing_hash),
                extracted_at          DATETIME DEFAULT (datetime('now')),
                posted_at             DATETIME,

                property_name         TEXT,
                borey_name            TEXT,
                unit_code             TEXT,
                city                  TEXT DEFAULT 'Phnom Penh',
                district              TEXT,
                landmark              TEXT,
                room_type             TEXT,
                floor                 INTEGER,
                furnished_status      TEXT,

                rent_usd              REAL,
                management_fee_usd    REAL,
                electricity_per_kwh   REAL,
                water_per_m3          REAL,
                car_parking_usd       REAL,
                motor_parking_usd     REAL,

                amenities_included    TEXT,
                amenities_excluded    TEXT,

                extraction_confidence REAL,
                needs_review          INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id              TEXT PRIMARY KEY,
                property_key    TEXT NOT NULL,
                listing_id      TEXT REFERENCES listings(id),
                listing_hash    TEXT REFERENCES raw_listings(listing_hash),
                rent_usd        REAL NOT NULL,
                recorded_at     DATETIME DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_price_history_property_key
                ON price_history (property_key, recorded_at);

            CREATE TABLE IF NOT EXISTS channels (
                username        TEXT PRIMARY KEY,
                added_at        DATETIME DEFAULT (datetime('now')),
                last_crawled_at DATETIME,
                total_crawls    INTEGER DEFAULT 0,
                total_extracted INTEGER DEFAULT 0,
                total_skipped   INTEGER DEFAULT 0,
                total_failed    INTEGER DEFAULT 0,
                is_active       INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS property_profiles (
                id                  TEXT PRIMARY KEY,
                building_key        TEXT UNIQUE NOT NULL,   -- lower(property_name)|lower(district)
                canonical_listing_id TEXT REFERENCES listings(id),

                year_built          INTEGER,
                developer           TEXT,
                total_floors        INTEGER,
                total_units         INTEGER,
                building_type       TEXT,
                amenities_summary   TEXT,
                description         TEXT,

                researched_at       DATETIME DEFAULT (datetime('now')),
                research_confidence REAL,
                needs_review        INTEGER DEFAULT 0
            );
        """)
        conn.commit()
        _migrate(conn)
        logger.info("Database initialised.")
    finally:
        conn.close()


# ── Raw listings ──────────────────────────────────────────────────────────────

def listing_exists(listing_hash):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM raw_listings WHERE listing_hash = ?", (listing_hash,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def insert_raw_listing(listing_hash, raw_text, posted_at=None):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO raw_listings (listing_hash, raw_text, posted_at) VALUES (?, ?, ?)",
            (listing_hash, raw_text, posted_at),
        )
        conn.commit()
        logger.info("Inserted raw listing %s (posted_at=%s)", listing_hash, posted_at)
    finally:
        conn.close()


def increment_extraction_attempts(listing_hash):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE raw_listings SET extraction_attempts = extraction_attempts + 1 WHERE listing_hash = ?",
            (listing_hash,),
        )
        conn.commit()
    finally:
        conn.close()


def get_extraction_attempts(listing_hash):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT extraction_attempts FROM raw_listings WHERE listing_hash = ?",
            (listing_hash,),
        ).fetchone()
        return row[0] if row else 0
    finally:
        conn.close()


def mark_needs_review(listing_hash):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE raw_listings SET needs_review = 1 WHERE listing_hash = ?",
            (listing_hash,),
        )
        conn.commit()
    finally:
        conn.close()


# ── Listings ──────────────────────────────────────────────────────────────────

def insert_listing(listing_id, listing_hash, data, posted_at=None):
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO listings (
                id, listing_hash, posted_at,
                property_name, borey_name, unit_code, city, district, landmark,
                room_type, floor, furnished_status,
                rent_usd, management_fee_usd, electricity_per_kwh, water_per_m3,
                car_parking_usd, motor_parking_usd,
                amenities_included, amenities_excluded,
                extraction_confidence, needs_review
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                listing_id, listing_hash, posted_at,
                data.get("property_name"),
                data.get("borey_name"),
                data.get("unit_code"),
                data.get("city", "Phnom Penh"),
                data.get("district"),
                data.get("landmark"),
                data.get("room_type"),
                data.get("floor"),
                data.get("furnished_status"),
                data.get("rent_usd"),
                data.get("management_fee_usd"),
                data.get("electricity_per_kwh"),
                data.get("water_per_m3"),
                data.get("car_parking_usd"),
                data.get("motor_parking_usd"),
                json.dumps(data["amenities_included"]) if data.get("amenities_included") is not None else None,
                json.dumps(data["amenities_excluded"]) if data.get("amenities_excluded") is not None else None,
                data.get("extraction_confidence"),
                1 if data.get("needs_review") else 0,
            ),
        )
        conn.execute(
            "UPDATE raw_listings SET is_processed = 1, processed_at = datetime('now') WHERE listing_hash = ?",
            (listing_hash,),
        )
        conn.commit()
        logger.info("Inserted listing %s (hash %s)", listing_id, listing_hash)
    finally:
        conn.close()

    _record_price_if_changed(listing_id, listing_hash, data)


# ── Price history ─────────────────────────────────────────────────────────────

def _make_property_key(data):
    parts = [
        (data.get("property_name") or "").strip().lower(),
        (data.get("unit_code") or "").strip().lower(),
        (data.get("district") or "").strip().lower(),
        (data.get("room_type") or "").strip().lower(),
    ]
    return "|".join(parts)


def _record_price_if_changed(listing_id, listing_hash, data):
    rent = data.get("rent_usd")
    if rent is None:
        return

    property_key = _make_property_key(data)
    if not property_key.replace("|", "").strip():
        return  # not enough info to identify the property

    conn = get_connection()
    try:
        last = conn.execute(
            "SELECT rent_usd FROM price_history WHERE property_key = ? ORDER BY recorded_at DESC LIMIT 1",
            (property_key,),
        ).fetchone()

        if last and last[0] == rent:
            return  # price unchanged

        conn.execute(
            "INSERT INTO price_history (id, property_key, listing_id, listing_hash, rent_usd) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), property_key, listing_id, listing_hash, rent),
        )
        conn.commit()

        if last:
            logger.info("Price change: %s  $%.0f → $%.0f", property_key, last[0], rent)
        else:
            logger.info("Price first seen: %s  $%.0f", property_key, rent)
    finally:
        conn.close()


# ── Property profiles ─────────────────────────────────────────────────────────

def make_building_key(property_name, district):
    name = (property_name or "").strip().lower()
    dist = (district or "").strip().lower()
    return f"{name}|{dist}"


def get_unresearched_buildings():
    """Return buildings that have listings but no profile yet."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT
                LOWER(TRIM(COALESCE(property_name, ''))) || '|' || LOWER(TRIM(COALESCE(district, ''))) AS building_key,
                property_name,
                district,
                COUNT(*) AS listing_count,
                MAX(id) AS canonical_listing_id
            FROM listings
            WHERE property_name IS NOT NULL AND TRIM(property_name) != ''
            GROUP BY building_key
            HAVING building_key NOT IN (SELECT building_key FROM property_profiles)
            ORDER BY listing_count DESC
        """).fetchall()
        return [
            {
                "building_key": r[0],
                "property_name": r[1],
                "district": r[2],
                "listing_count": r[3],
                "canonical_listing_id": r[4],
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_listing_samples(property_name, district, limit=5):
    """Fetch raw listing texts for a building to give the research agent context."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT r.raw_text
            FROM listings l
            JOIN raw_listings r ON l.listing_hash = r.listing_hash
            WHERE LOWER(TRIM(COALESCE(l.property_name, ''))) = LOWER(TRIM(?))
              AND LOWER(TRIM(COALESCE(l.district, '')))  = LOWER(TRIM(?))
            ORDER BY l.extraction_confidence DESC
            LIMIT ?
            """,
            (property_name or "", district or "", limit),
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def insert_property_profile(building_key, canonical_listing_id, data):
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO property_profiles (
                id, building_key, canonical_listing_id,
                year_built, developer, total_floors, total_units,
                building_type, amenities_summary, description,
                research_confidence, needs_review
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(building_key) DO UPDATE SET
                year_built          = excluded.year_built,
                developer           = excluded.developer,
                total_floors        = excluded.total_floors,
                total_units         = excluded.total_units,
                building_type       = excluded.building_type,
                amenities_summary   = excluded.amenities_summary,
                description         = excluded.description,
                researched_at       = datetime('now'),
                research_confidence = excluded.research_confidence,
                needs_review        = excluded.needs_review
            """,
            (
                str(uuid.uuid4()),
                building_key,
                canonical_listing_id,
                data.get("year_built"),
                data.get("developer"),
                data.get("total_floors"),
                data.get("total_units"),
                data.get("building_type"),
                data.get("amenities_summary"),
                data.get("description"),
                data.get("research_confidence"),
                1 if data.get("needs_review") else 0,
            ),
        )
        conn.commit()
        logger.info("Upserted profile for %s", building_key)
    finally:
        conn.close()


# ── Price history ─────────────────────────────────────────────────────────────

# ── Channels ─────────────────────────────────────────────────────────────────

def register_channel(username):
    """Insert channel if not already known. Safe to call repeatedly."""
    username = username.lstrip("@").strip()
    conn = get_connection()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO channels (username) VALUES (?)",
            (username,),
        )
        conn.commit()
    finally:
        conn.close()


def update_channel_stats(username, extracted, skipped, failed, pages=None):
    username = username.lstrip("@").strip()
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO channels (username, last_crawled_at, total_crawls, total_extracted, total_skipped, total_failed, default_pages)
               VALUES (?, datetime('now'), 1, ?, ?, ?, COALESCE(?, 3))
               ON CONFLICT(username) DO UPDATE SET
                   last_crawled_at = datetime('now'),
                   total_crawls    = total_crawls + 1,
                   total_extracted = total_extracted + excluded.total_extracted,
                   total_skipped   = total_skipped  + excluded.total_skipped,
                   total_failed    = total_failed   + excluded.total_failed,
                   default_pages   = COALESCE(excluded.default_pages, default_pages)""",
            (username, extracted, skipped, failed, pages),
        )
        conn.commit()
        logger.info("Channel stats updated: @%s +%d extracted (pages=%s)", username, extracted, pages)
    finally:
        conn.close()


def get_active_channels():
    """Return active channels with their stored page depth."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT username, COALESCE(default_pages, 3)
               FROM channels WHERE is_active = 1
               ORDER BY last_crawled_at ASC NULLS FIRST"""
        ).fetchall()
        return [{"username": r[0], "pages": r[1]} for r in rows]
    finally:
        conn.close()


def list_channels():
    """Return full channel rows for display."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT username, added_at, last_crawled_at,
                      total_crawls, total_extracted, total_skipped, total_failed,
                      is_active, COALESCE(default_pages, 3)
               FROM channels ORDER BY total_extracted DESC"""
        ).fetchall()
        return [
            {
                "username":        r[0],
                "added_at":        r[1],
                "last_crawled_at": r[2],
                "total_crawls":    r[3],
                "total_extracted": r[4],
                "total_skipped":   r[5],
                "total_failed":    r[6],
                "is_active":       bool(r[7]),
                "default_pages":   r[8],
            }
            for r in rows
        ]
    finally:
        conn.close()


def set_channel_active(username, active):
    username = username.lstrip("@").strip()
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE channels SET is_active = ? WHERE username = ?",
            (1 if active else 0, username),
        )
        conn.commit()
    finally:
        conn.close()


def get_price_history(property_key):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT rent_usd, recorded_at FROM price_history WHERE property_key = ? ORDER BY recorded_at",
            (property_key,),
        ).fetchall()
        return [{"rent_usd": r[0], "recorded_at": r[1]} for r in rows]
    finally:
        conn.close()
