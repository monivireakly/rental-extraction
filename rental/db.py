import json
import logging
import os
import sqlite3
import uuid

from .config import settings
from .normalizer import (
    normalise_city,
    normalise_district,
    normalise_furnished,
    normalise_property_name,
    normalise_property_type,
    normalise_room,
)

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

    add_if_missing("raw_listings", "posted_at",      "DATETIME")
    add_if_missing("listings",     "posted_at",      "DATETIME")
    add_if_missing("listings",     "property_type",  "TEXT")
    add_if_missing("listings",     "listing_type",   "TEXT DEFAULT 'rent'")
    add_if_missing("channels",     "default_pages",  "INTEGER DEFAULT 3")
    conn.commit()


# ── Official Cambodia geo reference data (source: CambodiaProvinceList2025 / DistrictList2025) ──

_PROVINCES = [
    ("01", "បន្ទាយមានជ័យ", "Banteay Meanchey"),
    ("02", "បាត់ដំបង", "Battambang"),
    ("03", "កំពង់ចាម", "Kampong Cham"),
    ("04", "កំពង់ឆ្នាំង", "Kampong Chhnang"),
    ("05", "កំពង់ស្ពឺ", "Kampong Speu"),
    ("06", "កំពង់ធំ", "Kampong Thom"),
    ("07", "កំពត", "Kampot"),
    ("08", "កណ្ដាល", "Kandal"),
    ("09", "កោះកុង", "Koh Kong"),
    ("10", "ក្រចេះ", "Kratie"),
    ("11", "មណ្ឌលគិរី", "Mondul Kiri"),
    ("12", "រាជធានីភ្នំពេញ", "Phnom Penh"),
    ("13", "ព្រះវិហារ", "Preah Vihear"),
    ("14", "ព្រៃវែង", "Prey Veng"),
    ("15", "ពោធិ៍សាត់", "Pursat"),
    ("16", "រតនគិរី", "Ratanak Kiri"),
    ("17", "សៀមរាប", "Siem Reap"),
    ("18", "ព្រះសីហនុ", "Sihanoukville"),
    ("19", "ស្ទឹងត្រែង", "Stung Treng"),
    ("20", "ស្វាយរៀង", "Svay Rieng"),
    ("21", "តាកែវ", "Takeo"),
    ("22", "ឧត្ដរមានជ័យ", "Otdar Meanchey"),
    ("23", "កែប", "Kep"),
    ("24", "ប៉ៃលិន", "Pailin"),
    ("25", "ត្បូងឃ្មុំ", "Tboung Khmum"),
]

_DISTRICTS = [
    ("01","0102","មង្គលបូរី","Mangkul Bourei"),
    ("01","0103","ភ្នំស្រុក","Phnum Srok"),
    ("01","0104","ព្រះនេត្រព្រះ","Preah Net Preah"),
    ("01","0105","អូរជ្រៅ","Ou Chrov"),
    ("01","0106","សិរីសោភ័ណ","Serei Saophoan"),
    ("01","0107","ថ្មពួក","Thma Puok"),
    ("01","0108","ស្វាយចេក","Svay Chek"),
    ("01","0109","ម៉ាឡៃ","Malai"),
    ("01","0110","ប៉ោយប៉ែត","Paoy Paet"),
    ("02","0201","បាណន់","Banan"),
    ("02","0202","ថ្មគោល","Thma Koul"),
    ("02","0203","បាត់ដំបង","Battambang"),
    ("02","0204","បវេល","Bavel"),
    ("02","0205","ឯកភ្នំ","Aek Phnum"),
    ("02","0206","មោងឫស្សី","Moung Ruessei"),
    ("02","0207","រតនមណ្ឌល","Rotaknak Mundul"),
    ("02","0208","សង្កែ","Sangkae"),
    ("02","0209","សំឡូត","Samlout"),
    ("02","0210","សំពៅលូន","Sampov Lun"),
    ("02","0211","ភ្នំព្រឹក","Phnum Proek"),
    ("02","0212","កំរៀង","Kamrieng"),
    ("02","0213","គាស់ក្រឡ","Koas Krala"),
    ("02","0214","រុក្ខគិរី","Rukh Kiri"),
    ("03","0301","បាធាយ","Batheay"),
    ("03","0302","ចំការលើ","Chamkar Leu"),
    ("03","0303","ជើងព្រៃ","Cheung Prey"),
    ("03","0305","កំពង់ចាម","Kampong Cham"),
    ("03","0306","កំពង់សៀម","Kampong Siem"),
    ("03","0307","កងមាស","Kang Meas"),
    ("03","0308","កោះសូទិន","Kaoh Soutin"),
    ("03","0313","ព្រៃឈរ","Prey Chhor"),
    ("03","0314","ស្រីសន្ធរ","Srei Santhor"),
    ("03","0315","ស្ទឹងត្រង់","Stueng Trang"),
    ("04","0401","បរិបូណ៌","Baribour"),
    ("04","0402","ជលគីរី","Chul Kiri"),
    ("04","0403","កំពង់ឆ្នាំង","Kampong Chhnang"),
    ("04","0404","កំពង់លែង","Kampong Leaeng"),
    ("04","0405","កំពង់ត្រឡាច","Kampong Tralach"),
    ("04","0406","រលាប្អៀរ","Rolea B'ier"),
    ("04","0407","សាមគ្គីមានជ័យ","Sammeakki Mean Chey"),
    ("04","0408","ទឹកផុស","Tuek Phos"),
    ("05","0501","បរសេដ្ឋ","Basaed"),
    ("05","0502","ច្បារមន","Chbar Mon"),
    ("05","0503","គងពិសី","Kong Pisei"),
    ("05","0504","ឱរ៉ាល់","Aoral"),
    ("05","0506","ភ្នំស្រួច","Phnum Sruoch"),
    ("05","0507","សំរោងទង","Samraong Tong"),
    ("05","0508","ថ្ពង","Thpong"),
    ("05","0509","ឧដុង្គម៉ែជ័យ","Odong Mae Chey"),
    ("05","0510","សាមគ្គីមុនីជ័យ","Sammeakki Muni Chey"),
    ("06","0601","បារាយណ៍","Baray"),
    ("06","0602","កំពង់ស្វាយ","Kampong Svay"),
    ("06","0603","ស្ទឹងសែន","Stueng Saen"),
    ("06","0604","ប្រាសាទបល្ល័ង្គ","Prasat Ballang"),
    ("06","0605","ប្រាសាទសំបូរ","Prasat Sambour"),
    ("06","0606","សណ្ដាន់","Sandan"),
    ("06","0607","សន្ទុក","Santuk"),
    ("06","0608","ស្ទោង","Stoung"),
    ("06","0609","តាំងគោក","Tang Kouk"),
    ("07","0701","អង្គរជ័យ","Angkor Chey"),
    ("07","0702","បន្ទាយមាស","Banteay Meas"),
    ("07","0703","ឈូក","Chhuk"),
    ("07","0704","ជុំគិរី","Chum Kiri"),
    ("07","0705","ដងទង់","Dang Tung"),
    ("07","0706","កំពង់ត្រាច","Kampong Trach"),
    ("07","0707","ទឹកឈូ","Tuek Chhu"),
    ("07","0708","កំពត","Kampot"),
    ("07","0709","បូកគោ","Bouk Kou"),
    ("08","0801","កណ្ដាលស្ទឹង","Kandal Stueng"),
    ("08","0802","កៀនស្វាយ","Kien Svay"),
    ("08","0803","ខ្សាច់កណ្ដាល","Khsach Kandal"),
    ("08","0804","កោះធំ","Kaoh Thum"),
    ("08","0805","លើកដែក","Leuk Daek"),
    ("08","0806","ល្វាឯម","Lvea Aem"),
    ("08","0807","មុខកំពូល","Mukh Kampul"),
    ("08","0808","អង្គស្នួល","Angk Snuol"),
    ("08","0809","ពញាឮ","Ponhea Lueu"),
    ("08","0810","ស្អាង","S'ang"),
    ("08","0811","តាខ្មៅ","Ta Khmau"),
    ("08","0812","សំពៅពូន","Sampov Pun"),
    ("08","0813","អរិយក្សត្រ","Akrey Ksat"),
    ("09","0901","បុទុមសាគរ","Botum Sakor"),
    ("09","0902","គិរីសាគរ","Kiri Sakor"),
    ("09","0903","កោះកុង","Kaoh Kong"),
    ("09","0904","ខេមរភូមិន្ទ","Khemmeakrakphumin"),
    ("09","0905","មណ្ឌលសីមា","Mundul Seima"),
    ("09","0906","ស្រែ អំបិល","Srae Ambel"),
    ("09","0907","ថ្មបាំង","Thma Bang"),
    ("10","1001","ឆ្លូង","Chhloung"),
    ("10","1002","ក្រចេះ","Kracheh"),
    ("10","1003","ព្រែកប្រសព្វ","Preaek Prasab"),
    ("10","1004","សំបូរ","Sambour"),
    ("10","1005","ស្នួល","Snuol"),
    ("10","1006","ចិត្របុរី","Chet Borei"),
    ("10","1007","អូរគ្រៀងសែនជ័យ","Ou Krieng Saen Chey"),
    ("11","1101","កែវសីមា","Kaev Seima"),
    ("11","1102","កោះញែក","Kaoh Nheaek"),
    ("11","1103","អូររាំង","Ou Reang"),
    ("11","1104","ពេជ្រាដា","Pechreada"),
    ("11","1105","សែនមនោរម្យ","Saen Meaknourum"),
    ("12","1201","ចំការមន","Chamkar Mon"),
    ("12","1202","ដូនពេញ","Doun Penh"),
    ("12","1203","៧មករា","Prampir Meakkakra"),
    ("12","1204","ទួលគោក","Tuol Kouk"),
    ("12","1205","ដង្កោ","Dangkao"),
    ("12","1206","មានជ័យ","Mean Chey"),
    ("12","1207","ឫស្សីកែវ","Russey Keo"),
    ("12","1208","សែនសុខ","Saen Sokh"),
    ("12","1209","ពោធិ៍សែនជ័យ","Pou Saen Chey"),
    ("12","1210","ច្បារអំពៅ","Chbar Ampov"),
    ("12","1211","ជ្រោយចង្វារ","Chraoy Chongvar"),
    ("12","1212","ព្រែកព្នៅ","Preaek Pnov"),
    ("12","1213","បឹងកេងកង","Boeng Keng Kang"),
    ("12","1214","កំបូល","Kamboul"),
    ("13","1301","ជ័យសែន","Chey Saen"),
    ("13","1302","ឆែប","Chhaeb"),
    ("13","1303","ជាំក្សាន្ដ","Choam Ksan"),
    ("13","1304","គូលែន","Kuleaen"),
    ("13","1305","រវៀង","Rovieng"),
    ("13","1306","សង្គមថ្មី","Sangkum Thmei"),
    ("13","1307","ត្បែងមានជ័យ","Tbaeng Mean Chey"),
    ("13","1308","ព្រះវិហារ","Preah Vihear"),
    ("14","1401","បាភ្នំ","Ba Phnum"),
    ("14","1402","កំចាយមារ","Kamchay Mear"),
    ("14","1403","កំពង់ត្របែក","Kampong Trabaek"),
    ("14","1404","កញ្ជ្រៀច","Kanhchriech"),
    ("14","1405","មេសាង","Me Sang"),
    ("14","1406","ពាមជរ","Peam Chor"),
    ("14","1407","ពាមរក៍","Peam Ro"),
    ("14","1408","ពារាំង","Pea Reang"),
    ("14","1409","ព្រះស្ដេច","Preah Sdach"),
    ("14","1410","ព្រៃវែង","Prey Veng"),
    ("14","1411","ពោធិ៍រៀង","Pur Rieng"),
    ("14","1412","ស៊ីធរកណ្ដាល","Sithor Kandal"),
    ("14","1413","ស្វាយអន្ទរ","Svay Antor"),
    ("15","1501","បាកាន","Bakan"),
    ("15","1502","កណ្ដៀង","Kandieng"),
    ("15","1503","ក្រគរ","Krakor"),
    ("15","1504","ភ្នំក្រវ៉ាញ","Phnum Kravanh"),
    ("15","1505","ពោធិ៍សាត់","Pousat"),
    ("15","1506","វាលវែង","Veal Veaeng"),
    ("15","1507","តាលោសែនជ័យ","Ta Lou Soen Chey"),
    ("16","1601","អណ្ដូងមាស","Andoung Meas"),
    ("16","1602","បានលុង","Ban Lung"),
    ("16","1603","បរកែវ","Bar Kaev"),
    ("16","1604","កូនមុំ","Koun Mom"),
    ("16","1605","លំផាត់","Lumphat"),
    ("16","1606","អូរជុំ","Ou Chum"),
    ("16","1607","អូរយ៉ាដាវ","Ou Ya Dav"),
    ("16","1608","តាវែង","Ta Veaeng"),
    ("16","1609","វើនសៃ","Veun Sai"),
    ("17","1701","អង្គរជុំ","Angkor Chum"),
    ("17","1702","អង្គរធំ","Angkor Thum"),
    ("17","1703","បន្ទាយស្រី","Banteay Srei"),
    ("17","1704","ជីក្រែង","Chi Kraeng"),
    ("17","1706","ក្រឡាញ់","Kralanh"),
    ("17","1707","ពួក","Puok"),
    ("17","1709","ប្រាសាទបាគង","Prasat Bakong"),
    ("17","1710","សៀមរាប","Siem Reab"),
    ("17","1711","សូទ្រនិគម","Sout Nikum"),
    ("17","1712","ស្រីស្នំ","Srei Snam"),
    ("17","1713","ស្វាយលើ","Svay Leu"),
    ("17","1714","វ៉ារិន","Varin"),
    ("17","1715","រុនតាឯកតេជោសែន","Run Ta Aek Techou Saen"),
    ("18","1801","ព្រះសីហនុ","Preah Sihanouk"),
    ("18","1802","ព្រៃនប់","Prey Nub"),
    ("18","1803","ស្ទឹងហាវ","Stueng Hav"),
    ("18","1804","កំពង់សីលា","Kampong Seila"),
    ("18","1805","កោះរ៉ុង","Kaoh Rung"),
    ("18","1806","កំពង់សោម","Kampong Saom"),
    ("19","1901","សេសាន","Sesan"),
    ("19","1902","សៀមបូក","Siem Bouk"),
    ("19","1903","សៀមប៉ាង","Siem Pang"),
    ("19","1904","ស្ទឹងត្រែង","Stueng Traeng"),
    ("19","1905","ថាឡាបរិវ៉ាត់","Thala Barivat"),
    ("19","1906","បុរីអូរស្វាយសែនជ័យ","Borei Ou Svay Senchey"),
    ("20","2001","ចន្ទ្រា","Chantrea"),
    ("20","2002","កំពង់រោទិ៍","Kampong Rou"),
    ("20","2003","រំដួល","Rumduol"),
    ("20","2004","រមាសហែក","Romeas Haek"),
    ("20","2005","ស្វាយជ្រំ","Svay Chrum"),
    ("20","2006","ស្វាយរៀង","Svay Rieng"),
    ("20","2007","ស្វាយទាប","Svay Teab"),
    ("20","2008","បាវិត","Bavet"),
    ("21","2101","អង្គរបូរី","Angkor Borei"),
    ("21","2102","បាទី","Bati"),
    ("21","2103","បូរីជលសារ","Bourei Chulsar"),
    ("21","2104","គីរីវង់","Kiri Vung"),
    ("21","2105","កោះអណ្ដែត","Kaoh Andaet"),
    ("21","2106","ព្រៃកប្បាស","Prey Kabbas"),
    ("21","2107","សំរោង","Samraong"),
    ("21","2108","ដូនកែវ","Doun Kaev"),
    ("21","2109","ត្រាំកក់","Tram Kak"),
    ("21","2110","ទ្រាំង","Treang"),
    ("22","2201","អន្លង់វែង","Anlung Veaeng"),
    ("22","2202","បន្ទាយអំពិល","Banteay Ampil"),
    ("22","2203","ចុងកាល់","Chong Kal"),
    ("22","2204","សំរោង","Samraong"),
    ("22","2205","ត្រពាំងប្រាសាទ","Trapeang Prasat"),
    ("23","2301","ដំណាក់ចង្អើរ","Damnak Chang'aeu"),
    ("23","2302","កែប","Kaeb"),
    ("24","2401","ប៉ៃលិន","Pailin"),
    ("24","2402","សាលាក្រៅ","Sala Krau"),
    ("25","2501","តំបែរ","Dambae"),
    ("25","2502","ក្រូចឆ្មារ","Krouch Chhmar"),
    ("25","2503","មេមត់","Memut"),
    ("25","2504","អូររាំងឪ","Ou Reang Ov"),
    ("25","2505","ពញាក្រែក","Ponhea Kraek"),
    ("25","2506","សួង","Suong"),
    ("25","2507","ត្បូងឃ្មុំ","Tboung Khmum"),
]


def seed_geo_tables():
    conn = get_connection()
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO provinces (province_code, province_kh, province_en) VALUES (?,?,?)",
            _PROVINCES,
        )
        conn.executemany(
            "INSERT OR IGNORE INTO geo_districts (province_code, district_code, district_kh, district_en) VALUES (?,?,?,?)",
            _DISTRICTS,
        )
        conn.commit()
        logger.info("Geo tables seeded: %d provinces, %d districts", len(_PROVINCES), len(_DISTRICTS))
    finally:
        conn.close()


def init_db():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS raw_listings (
                listing_hash        TEXT PRIMARY KEY,
                ingested_at         DATETIME DEFAULT (datetime('now', '+7 hours')),
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
                extracted_at          DATETIME DEFAULT (datetime('now', '+7 hours')),
                posted_at             DATETIME,

                property_type         TEXT,
                property_name         TEXT,
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
                needs_review          INTEGER DEFAULT 0,
                listing_type          TEXT DEFAULT 'rent'
            );

            CREATE TABLE IF NOT EXISTS price_history (
                id              TEXT PRIMARY KEY,
                property_key    TEXT NOT NULL,
                listing_id      TEXT REFERENCES listings(id),
                listing_hash    TEXT REFERENCES raw_listings(listing_hash),
                rent_usd        REAL NOT NULL,
                recorded_at     DATETIME DEFAULT (datetime('now', '+7 hours'))
            );

            CREATE INDEX IF NOT EXISTS idx_price_history_property_key
                ON price_history (property_key, recorded_at);

            CREATE TABLE IF NOT EXISTS channels (
                username        TEXT PRIMARY KEY,
                added_at        DATETIME DEFAULT (datetime('now', '+7 hours')),
                last_crawled_at DATETIME,
                total_crawls    INTEGER DEFAULT 0,
                total_extracted INTEGER DEFAULT 0,
                total_skipped   INTEGER DEFAULT 0,
                total_failed    INTEGER DEFAULT 0,
                is_active       INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS provinces (
                province_code TEXT PRIMARY KEY,
                province_kh   TEXT,
                province_en   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS geo_districts (
                district_code TEXT PRIMARY KEY,
                province_code TEXT REFERENCES provinces(province_code),
                district_kh   TEXT,
                district_en   TEXT NOT NULL
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

                researched_at       DATETIME DEFAULT (datetime('now', '+7 hours')),
                research_confidence REAL,
                needs_review        INTEGER DEFAULT 0
            );
        """)
        conn.commit()
        _migrate(conn)
        logger.info("Database initialised.")
    finally:
        conn.close()
    seed_geo_tables()


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
    # normalise before insert — district first, city depends on it
    _district  = normalise_district(data.get("district"))
    _city      = normalise_city(data.get("city", "Phnom Penh"), data.get("landmark"), _district)
    _room      = normalise_room(data.get("room_type"))
    _furnished = normalise_furnished(data.get("furnished_status"))
    _ptype     = normalise_property_type(data.get("property_type"))
    _pname     = normalise_property_name(data.get("property_name"))

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO listings (
                id, listing_hash, posted_at,
                property_type, property_name, unit_code,
                city, district, landmark,
                room_type, floor, furnished_status,
                rent_usd, management_fee_usd, electricity_per_kwh, water_per_m3,
                car_parking_usd, motor_parking_usd,
                amenities_included, amenities_excluded,
                extraction_confidence, needs_review, listing_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                listing_id, listing_hash, posted_at,
                _ptype,
                _pname,
                data.get("unit_code"),
                _city,
                _district,
                data.get("landmark"),
                _room,
                data.get("floor"),
                _furnished,
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
                data.get("listing_type", "rent"),
            ),
        )
        conn.execute(
            "UPDATE raw_listings SET is_processed = 1, processed_at = datetime('now', '+7 hours') WHERE listing_hash = ?",
            (listing_hash,),
        )
        conn.commit()
        logger.info("Inserted listing %s (hash %s)", listing_id, listing_hash)
    finally:
        conn.close()

    _record_price_if_changed(listing_id, listing_hash, {
        **data,
        "property_name": _pname,
        "district": _district,
        "room_type": _room,
    })


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
    if not (data.get("property_name") or "").strip():
        return  # property_name required — keys like |||1br conflate unrelated listings

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


def get_properties_missing_type():
    """Return distinct (property_name, district, building_type_from_profile) where property_type IS NULL."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT
                l.property_name,
                l.district,
                pp.building_type,
                COUNT(*) AS listing_count
            FROM listings l
            LEFT JOIN property_profiles pp
                ON pp.building_key =
                   LOWER(TRIM(COALESCE(l.property_name,''))) || '|' ||
                   LOWER(TRIM(COALESCE(l.district,'')))
            WHERE l.property_type IS NULL
              AND l.property_name IS NOT NULL
              AND TRIM(l.property_name) != ''
            GROUP BY l.property_name, l.district, pp.building_type
            ORDER BY listing_count DESC
        """).fetchall()
        return [
            {
                "property_name":  r[0],
                "district":       r[1],
                "building_type":  r[2],
                "listing_count":  r[3],
            }
            for r in rows
        ]
    finally:
        conn.close()


def bulk_update_property_type(property_name, property_type):
    """Set property_type on all listings with the given property_name."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "UPDATE listings SET property_type = ? WHERE property_name = ? AND property_type IS NULL",
            (property_type, property_name),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def upsert_profile_building_type(building_key, building_type):
    """Insert a minimal property_profiles row or update building_type if the key already exists."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO property_profiles (id, building_key, building_type)
            VALUES (lower(hex(randomblob(16))), ?, ?)
            ON CONFLICT(building_key) DO UPDATE SET building_type = excluded.building_type
            """,
            (building_key, building_type),
        )
        conn.commit()
    finally:
        conn.close()


def sync_property_type_to_profiles():
    """
    For every distinct (property_name, district) in listings that has a property_type
    but no property_profiles row, insert a minimal profile row so future researcher
    runs can skip the Claude classify step.
    Returns the number of rows inserted/updated.
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            """
            INSERT INTO property_profiles (id, building_key, building_type)
            SELECT
                lower(hex(randomblob(16))),
                building_key,
                property_type
            FROM (
                SELECT
                    LOWER(TRIM(COALESCE(property_name,''))) || '|' ||
                    LOWER(TRIM(COALESCE(district,'')))    AS building_key,
                    property_type,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            LOWER(TRIM(COALESCE(property_name,''))),
                            LOWER(TRIM(COALESCE(district,'')))
                        ORDER BY extracted_at DESC
                    ) AS rn
                FROM listings
                WHERE property_type IS NOT NULL
                  AND property_name IS NOT NULL
                  AND TRIM(property_name) != ''
            ) t
            WHERE rn = 1
            ON CONFLICT(building_key) DO UPDATE SET building_type = excluded.building_type
            """
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


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
                researched_at       = datetime('now', '+7 hours'),
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
               VALUES (?, datetime('now', '+7 hours'), 1, ?, ?, ?, COALESCE(?, 3))
               ON CONFLICT(username) DO UPDATE SET
                   last_crawled_at = datetime('now', '+7 hours'),
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
