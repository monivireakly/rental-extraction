# Phnom Penh Rental Listing Bot

A Telegram bot that ingests raw rental listings from public Telegram channels, extracts structured data using the Claude API, and stores everything in a local SQLite database. Includes a channel crawler, a data normalisation agent, a property research agent, and a matplotlib insights dashboard.

---

## Project Structure

```
rental-extraction/
├── rental/                    # core package
│   ├── bot.py                 # Telegram bot + scheduled auto-crawl
│   ├── crawler.py             # public channel scraper (no API key needed)
│   ├── db.py                  # SQLite data layer
│   ├── extractor.py           # Claude extraction (listing → structured JSON)
│   ├── normalizer.py          # district / room type cleaning agent
│   ├── researcher.py          # property enrichment agent (profiles + descriptions)
│   ├── insights.py            # matplotlib dashboard
│   ├── config.py              # Pydantic settings (single source of truth)
│   └── prompts/
│       ├── extraction.py      # extraction system prompt
│       └── research.py        # property research system prompt
├── .claude/commands/          # Claude Code slash commands
│   ├── bot.md                 # /bot
│   ├── crawl.md               # /crawl
│   ├── normalize.md           # /normalize
│   ├── research.md            # /research
│   ├── insights.md            # /insights
│   └── db.md                  # /db
├── data/                      # SQLite db + chart output (gitignored)
├── main.py                    # entry point
├── requirements.txt
├── railway.toml
└── .env.example
```

---

## Setup

```bash
git clone https://github.com/monivireakly/rental-extraction.git
cd rental-extraction
cp .env.example .env
# Fill in TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, and TELEGRAM_CHANNELS
pip install -r requirements.txt
```

### Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | — | From [@BotFather](https://t.me/BotFather) |
| `ANTHROPIC_API_KEY` | Yes | — | From [console.anthropic.com](https://console.anthropic.com) |
| `TELEGRAM_CHANNELS` | Yes | — | Comma-separated channel names e.g. `condoapartmentincambodia,channel2` |
| `DATABASE_PATH` | No | `./data/listings.db` | Path to SQLite file |
| `CRAWL_INTERVAL_HOURS` | No | `6` | How often the bot auto-crawls channels |
| `CRAWL_PAGES_PER_RUN` | No | `3` | Pages per channel per scheduled run |

---

## Run locally

```bash
python3 main.py
```

The bot starts polling and schedules an automatic crawl 30 seconds after launch, then every `CRAWL_INTERVAL_HOURS` hours.

---

## Bot commands (in Telegram)

| Command | Description |
|---|---|
| `/start` | Welcome message |
| `/crawl` | Crawl all channels, 1 page each |
| `/crawl 5` | Crawl all channels, 5 pages each |
| `/crawl condoapartmentincambodia` | Crawl one channel, 1 page |
| `/crawl condoapartmentincambodia 10` | Crawl one channel, 10 pages |

You can also paste any listing text directly into the bot — it extracts and saves it on the spot.

---

## CLI commands

```bash
# Crawl channels
python3 -m rental.crawler --pages 10
python3 -m rental.crawler --channel condoapartmentincambodia --pages 5

# Normalise dirty data (dry-run first, then apply)
python3 -m rental.normalizer
python3 -m rental.normalizer --apply

# Enrich buildings with profiles and descriptions
python3 -m rental.researcher --dry-run     # preview pending buildings
python3 -m rental.researcher --limit 20    # research up to 20 buildings
python3 -m rental.researcher               # research all pending

# Generate insights dashboard → saved to data/insights.png
python3 -m rental.insights
```

---

## Claude Code skills

If you're developing with [Claude Code](https://claude.ai/code), slash commands are available for every operation:

| Skill | Description |
|---|---|
| `/crawl [channel] [pages]` | Crawl channels and report stats |
| `/normalize [apply]` | Preview and apply data cleaning |
| `/research [limit\|dry-run]` | Enrich buildings with AI-generated profiles |
| `/insights` | Generate and display the dashboard |
| `/bot` | Validate env and start the bot |
| `/db [district\|rent\|review]` | Database health check |

---

## Data pipeline

```
Telegram channel
      ↓
  crawler.py      — scrapes t.me/s/<channel>, deduplicates by MD5
      ↓
  extractor.py    — Claude haiku returns structured JSON per listing
      ↓
  raw_listings    — every message stored with processing status
  listings        — extracted fields with confidence score
  price_history   — rent changes tracked per property over time
      ↓
  normalizer.py   — fixes district typos and room type variants in-place
      ↓
  researcher.py   — Claude agent enriches each unique building with
                    year built, developer, building type, and a
                    distinct description → property_profiles table
      ↓
  insights.py     — matplotlib dashboard from clean data
```

---

## Database

SQLite at `DATABASE_PATH` (default `./data/listings.db`). Four tables:

| Table | Description |
|---|---|
| `raw_listings` | Every ingested message, MD5 hash, processing status, retry count |
| `listings` | Extracted fields: property, location, room type, rent, utilities, amenities, confidence |
| `price_history` | Rent changes over time per property, keyed by `property_name\|unit_code\|district\|room_type` |
| `property_profiles` | One row per unique building — year built, developer, type, amenities summary, AI description |

```bash
# Spot check listings
sqlite3 ./data/listings.db "SELECT district, room_type, rent_usd, extraction_confidence FROM listings LIMIT 10;"

# Price history for a property
sqlite3 ./data/listings.db "SELECT property_key, rent_usd, recorded_at FROM price_history ORDER BY recorded_at DESC LIMIT 10;"

# Building profiles
sqlite3 ./data/listings.db "SELECT building_key, building_type, year_built, developer FROM property_profiles LIMIT 10;"

# Flagged for review
sqlite3 ./data/listings.db "SELECT id, extraction_confidence FROM listings WHERE needs_review = 1;"
```

---

## Deploy to Railway

1. Push to GitHub.
2. Create a new Railway project → connect the repo.
3. Set environment variables in the Railway dashboard (`TELEGRAM_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `TELEGRAM_CHANNELS`).
4. Railway detects `railway.toml` and deploys with `python main.py`.

Free alternatives: [Fly.io](https://fly.io), [Koyeb](https://koyeb.com), [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/).
