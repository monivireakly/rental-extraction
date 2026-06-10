import sqlite3
import os
import logging

logger = logging.getLogger(__name__)


def get_db_path():
    return os.getenv("DATABASE_PATH", "./data/listings.db")


def get_connection():
    db_path = get_db_path()
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    return sqlite3.connect(db_path)


def init_db():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS raw_listings (
                listing_hash        TEXT PRIMARY KEY,
                ingested_at         DATETIME DEFAULT (datetime('now')),
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
        """)
        conn.commit()
        logger.info("Database initialized.")
    finally:
        conn.close()


def listing_exists(listing_hash):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM raw_listings WHERE listing_hash = ?", (listing_hash,)
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def insert_raw_listing(listing_hash, raw_text):
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO raw_listings (listing_hash, raw_text) VALUES (?, ?)",
            (listing_hash, raw_text),
        )
        conn.commit()
        logger.info("Inserted raw listing %s", listing_hash)
    finally:
        conn.close()


def increment_extraction_attempts(listing_hash):
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE raw_listings
               SET extraction_attempts = extraction_attempts + 1
               WHERE listing_hash = ?""",
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


def insert_listing(listing_id, listing_hash, data):
    import json

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO listings (
                id, listing_hash,
                property_name, borey_name, unit_code, city, district, landmark,
                room_type, floor, furnished_status,
                rent_usd, management_fee_usd, electricity_per_kwh, water_per_m3,
                car_parking_usd, motor_parking_usd,
                amenities_included, amenities_excluded,
                extraction_confidence, needs_review
            ) VALUES (
                ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?
            )""",
            (
                listing_id,
                listing_hash,
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
                json.dumps(data.get("amenities_included")) if data.get("amenities_included") is not None else None,
                json.dumps(data.get("amenities_excluded")) if data.get("amenities_excluded") is not None else None,
                data.get("extraction_confidence"),
                1 if data.get("needs_review") else 0,
            ),
        )
        conn.execute(
            """UPDATE raw_listings
               SET is_processed = 1, processed_at = datetime('now')
               WHERE listing_hash = ?""",
            (listing_hash,),
        )
        conn.commit()
        logger.info("Inserted extracted listing %s (hash %s)", listing_id, listing_hash)
    finally:
        conn.close()
