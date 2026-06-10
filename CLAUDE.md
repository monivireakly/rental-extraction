# Claude Code Prompt — Phnom Penh Rental Listing Bot
 
## What to Build
 
A Telegram bot that receives raw rental listing text, extracts structured
data using the Claude API, and stores it in a local SQLite database.
Deployable to Railway as a single Python service.
 
---
 
## Project Structure to Generate
 
```
rental-bot/
├── bot.py                  # main entry point
├── db.py                   # SQLite setup and insert logic
├── extractor.py            # Claude API call and JSON parsing
├── prompts/
│   └── extraction.py       # extraction system prompt as a string constant
├── requirements.txt
├── railway.toml
├── .env.example
└── README.md
```
 
---
 
## Environment Variables
 
These must be read from environment, never hardcoded:
 
```
TELEGRAM_BOT_TOKEN=
ANTHROPIC_API_KEY=
DATABASE_PATH=./data/listings.db   # default if not set
```
 
---
 
## Database — SQLite, Two Tables
 
### Table 1: raw_listings
 
```sql
CREATE TABLE IF NOT EXISTS raw_listings (
    listing_hash      TEXT PRIMARY KEY,        -- MD5 of raw_text
    ingested_at       DATETIME DEFAULT (datetime('now')),
    source_platform   TEXT DEFAULT 'telegram',
    raw_text          TEXT NOT NULL,
    is_processed      INTEGER DEFAULT 0,       -- 0 = false, 1 = true
    processed_at      DATETIME,
    extraction_attempts INTEGER DEFAULT 0
);
```
 
### Table 2: listings
 
```sql
CREATE TABLE IF NOT EXISTS listings (
    id                    TEXT PRIMARY KEY,    -- UUID4
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
 
    amenities_included    TEXT,               -- JSON string
    amenities_excluded    TEXT,               -- JSON string
 
    extraction_confidence REAL,
    needs_review          INTEGER DEFAULT 0   -- 0 = false, 1 = true
);
```
 
---
 
## Bot Behavior
 
### On receiving any text message:
 
1. Compute MD5 hash of the message text
2. Check if `listing_hash` already exists in `raw_listings`
   - If yes: reply "⚠️ Duplicate listing — already in database." and stop
   - If no: insert into `raw_listings` with `is_processed = 0`
3. Call Claude API with the extraction prompt (see below)
4. Parse the returned JSON
5. On success:
   - Insert extracted row into `listings`
   - Update `raw_listings` set `is_processed = 1`, `processed_at = now()`
   - Reply with a confirmation summary (see format below)
6. On Claude API error or JSON parse failure:
   - Increment `extraction_attempts`
   - If `extraction_attempts >= 3`: set `needs_review = 1` in raw_listings
   - Reply "❌ Extraction failed. Saved raw. Will retry." and stop
### Confirmation reply format:
 
```
✅ Saved
 
🏠 {property_name or "Unknown"} {borey_name or ""}
📍 {district or landmark or "Location unknown"}
🛏 {room_type or "?"} | {furnished_status or "?"}
 
💵 Rent:        ${rent_usd}
⚡ Electric:    ${electricity_per_kwh}/kWh
💧 Water:       ${water_per_m3}/m³
🏢 Management:  ${management_fee_usd or "—"}
 
🎯 Confidence: {extraction_confidence}
{"⚠️ Flagged for review" if needs_review else ""}
```
 
---
 
## Claude API Call — extractor.py
 
Use the `anthropic` Python SDK.
Model: `claude-haiku-4-5`
Max tokens: `1024`
 
The system prompt is the full string defined in `prompts/extraction.py`.
The user message is:
 
```
<listing>
{raw_text}
</listing>
```
 
Parse the response as JSON. If JSON parsing fails, raise an exception
so the caller can handle retry logic.
 
---
 
## Extraction System Prompt — prompts/extraction.py
 
Store this exactly as a Python string constant named `EXTRACTION_PROMPT`:
 
```
You are a data extraction agent for Cambodian real estate listings.
You receive raw listing text and return a single JSON object. Nothing else.
 
Extract structured rental data from the listing text provided in <listing> tags.
Return only the JSON object. No explanation. No commentary. No markdown fences.
 
Output schema:
{
  "property_name": string or null,
  "borey_name": string or null,
  "unit_code": string or null,
  "city": string or null,
  "district": string or null,
  "landmark": string or null,
  "room_type": string or null,
  "floor": integer or null,
  "furnished_status": "Full" or "Partial" or "Unfurnished" or null,
  "rent_usd": number or null,
  "management_fee_usd": number or null,
  "electricity_per_kwh": number or null,
  "water_per_m3": number or null,
  "car_parking_usd": number or null,
  "motor_parking_usd": number or null,
  "amenities_included": { "<name>": true } or null,
  "amenities_excluded": { "<name>": number or null } or null,
  "extraction_confidence": number,
  "needs_review": boolean
}
 
Rules:
- Numbers only for currency. Strip $, USD, ៛.
- free or included means 0, not null.
- null means not mentioned. Never guess.
- city defaults to "Phnom Penh" if not stated.
- floor is integer parsed from unit codes e.g. F2-09 → 2.
- amenities_excluded values are monthly costs. null if price not stated.
- extraction_confidence is 0.0 to 1.0 based on how complete core financials are.
- needs_review is true if rent_usd is null, values conflict, or text is mostly Khmer.
 
Example input:
<listing>
Beautiful L Residence Borey Keila For Rent
📍Location : Central of Phnom Penh City, Near Olympic Stadium
✅Price : 300$
✅Type : 1 Bedroom
✅Floor : F2-09
✅Fully Furnished
✅Management Fee : 24$
✅Service Includes :
👉Free Motor Park
✅Service Exclude :
👉Electric : $0.25/KW
👉Water : $0.75/M3
👉Car Parking : 40$
👉Gym | Pool | Steam | Sauna : 45$ per month
</listing>
 
Example output:
{"property_name":"L Residence","borey_name":"Borey Keila","unit_code":"F2-09","city":"Phnom Penh","district":null,"landmark":"Near Olympic Stadium","room_type":"1BR","floor":2,"furnished_status":"Full","rent_usd":300.00,"management_fee_usd":24.00,"electricity_per_kwh":0.25,"water_per_m3":0.75,"car_parking_usd":40.00,"motor_parking_usd":0,"amenities_included":{"motor_parking":true},"amenities_excluded":{"gym":45,"pool":45,"steam":45,"sauna":45,"car_parking":40},"extraction_confidence":0.95,"needs_review":false}
```
 
---
 
## requirements.txt
 
```
anthropic
python-telegram-bot==20.7
python-dotenv
```
 
No ORM. Use Python's built-in `sqlite3` module directly.
 
---
 
## railway.toml
 
```toml
[build]
builder = "nixpacks"
 
[deploy]
startCommand = "python bot.py"
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```
 
---
 
## .env.example
 
```
TELEGRAM_BOT_TOKEN=your_token_here
ANTHROPIC_API_KEY=your_key_here
DATABASE_PATH=./data/listings.db
```
 
---
 
## README.md — include these sections:
 
1. Overview (one paragraph)
2. Setup — clone, copy .env.example to .env, fill values
3. Run locally — `pip install -r requirements.txt && python bot.py`
4. Deploy to Railway — connect GitHub repo, set env vars in Railway dashboard
5. Usage — forward any rental listing text to the bot
6. Database — where the SQLite file lives, how to query it
---
 
## Additional Requirements
 
- Create the `data/` directory if it does not exist on startup
- Use `python-dotenv` to load `.env` in development
- All database operations in `db.py` as standalone functions, not a class
- `bot.py` only handles Telegram wiring — no business logic
- `extractor.py` only handles Claude API — no database logic
- Log to stdout: ingestion events, extraction results, errors
- No async database calls — sqlite3 is synchronous, keep it simple
- Bot should handle `/start` with a one-line welcome message only
 