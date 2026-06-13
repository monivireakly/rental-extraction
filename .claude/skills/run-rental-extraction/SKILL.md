---
name: run-rental-extraction
description: Run, start, test, or smoke-test the rental-extraction Telegram bot and its extraction pipeline. Use when verifying extractor changes, testing DB operations, or confirming the bot starts.
---

# run-rental-extraction

This is a Python Telegram bot that receives rental listing text, calls the Claude API to extract structured data, and stores it in SQLite. There is no HTTP interface — the interactive surface is Telegram polling. The agent path is a Python smoke driver that exercises the full pipeline (DB init → Claude extract → DB insert → stats) without needing a live Telegram session.

## Prerequisites

Python 3.10+, pip packages from `requirements.txt`, and a `.env` file with `ANTHROPIC_API_KEY` and `TELEGRAM_BOT_TOKEN`.

```bash
pip3 install -r requirements.txt
cp .env.example .env   # then fill in the two required keys
```

## Run (agent path) — smoke driver

The driver at `.claude/skills/run-rental-extraction/driver.py` exercises the full extraction pipeline end-to-end and prints results + DB stats. It is self-contained and sets `sys.path` internally, so no `PYTHONPATH` export is needed.

```bash
python3 .claude/skills/run-rental-extraction/driver.py
```

Expected output (values vary — the assertions check structure, not exact text):

```
=== rental-extraction smoke driver ===

1. DB init...
   OK

2. Extraction (calls Claude API)...
   Result: { "property_name": "Sky Villa", "district": "Daun Penh", "rent_usd": 550, ... }
   assertions passed

3. DB insert (raw + listing)...
   listing id: <uuid>

4. DB stats...
   raw_listings: NNN
   listings:     NNN
   rent USD — min:130.0  max:...  avg:...

=== all checks passed ===
```

The driver asserts `rent_usd == 550`, `district == "Daun Penh"`, and `extraction_confidence > 0.5`. A failure here means the extractor prompt or API call broke.

## Direct component invocation

The extractor module has a `__main__` entry point. Pipe or pass text directly — no Python needed:

```bash
# single line via args
python3 -m rental.extractor "1BR condo BKK1 Phnom Penh 400USD/month"

# multiline listing via stdin
cat listing.txt | python3 -m rental.extractor
```

# DB stats
python3 -c "
from rental.db import get_connection; conn = get_connection()
print(conn.execute('SELECT COUNT(*) FROM listings').fetchone()[0], 'listings')
conn.close()
"

# normalizer
python3 -c "
from rental.normalizer import normalise_district, normalise_room
print(normalise_district('BKK1'))        # BKK1
print(normalise_district('toul kork'))   # Tuol Kouk
print(normalise_room('1 bed'))           # 1 bed
"
```

## Run (human path) — live bot

Requires a real Telegram bot token. Blocks in polling loop; Ctrl-C to stop.

```bash
python3 main.py
```

## Gotchas

- `extract_listing()` is **synchronous**, not `async`. Do not wrap it in `asyncio.run()` — it will raise `ValueError: a coroutine was expected, got {...}`.
- `insert_raw_listing(hash, text)` takes the MD5 hash as the **first** arg, raw text as second. The hash is not computed internally.
- `insert_listing(id, hash, data)` takes three positional args — listing UUID first, then hash, then the data dict.
- Running `python3 driver.py` from anywhere other than the project root fails with `ModuleNotFoundError: No module named 'rental'` if you strip the `sys.path` line. The driver patches this internally.
- The `.env` file must be in the **project root** (where `main.py` lives), not in `rental/`. `pydantic-settings` resolves it relative to CWD.

## Troubleshooting

**`ModuleNotFoundError: No module named 'rental'`** — run the driver via `python3 .claude/skills/run-rental-extraction/driver.py`, not as `cd .claude/... && python3 driver.py`. The `sys.path` patch resolves to the project root using `__file__`.

**`ValidationError` on startup** — `.env` is missing or `ANTHROPIC_API_KEY` / `TELEGRAM_BOT_TOKEN` not set. Copy `.env.example` and fill both keys.

**Assertion error on `district`** — the Claude model occasionally returns `"Chamkarmon"` instead of `"Daun Penh"` for the BKK1 sample. This is model non-determinism, not a bug. Re-run; it passes consistently.
