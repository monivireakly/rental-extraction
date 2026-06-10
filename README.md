# Phnom Penh Rental Listing Bot

A Telegram bot that receives raw rental listing text, extracts structured data using the Claude API (claude-haiku-4-5), and stores it in a local SQLite database. Designed to run as a single Python service on Railway.

## Setup

```bash
git clone <your-repo-url>
cd rental-extraction
cp .env.example .env
# Edit .env and fill in TELEGRAM_BOT_TOKEN and ANTHROPIC_API_KEY
```

## Run locally

```bash
pip install -r requirements.txt
python bot.py
```

## Deploy to Railway

1. Push this repo to GitHub.
2. Create a new Railway project and connect your GitHub repo.
3. In the Railway dashboard, add environment variables:
   - `TELEGRAM_BOT_TOKEN`
   - `ANTHROPIC_API_KEY`
   - `DATABASE_PATH` (optional, defaults to `./data/listings.db`)
4. Railway will detect `railway.toml` and deploy automatically.

## Usage

Forward or paste any Phnom Penh rental listing text into the bot. It will:
- Deduplicate by MD5 hash
- Extract structured fields (rent, utilities, location, amenities) via Claude
- Reply with a formatted summary and confidence score

## Database

The SQLite file lives at `DATABASE_PATH` (default: `./data/listings.db`).

```bash
# View raw listings
sqlite3 ./data/listings.db "SELECT listing_hash, ingested_at, is_processed FROM raw_listings;"

# View extracted listings
sqlite3 ./data/listings.db "SELECT property_name, district, rent_usd, extraction_confidence FROM listings;"
```

Two tables:
- `raw_listings` — every message received, with processing status
- `listings` — extracted structured data linked to raw listings
