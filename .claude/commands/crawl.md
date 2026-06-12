Crawl one or all Telegram rental channels and extract listings into the database.

Usage:
  /crawl                         — crawl all channels from .env, 5 pages each
  /crawl condoapartmentincambodia — crawl one channel, 5 pages
  /crawl condoapartmentincambodia 10 — crawl one channel, 10 pages

Arguments: $ARGUMENTS

Steps:
1. Parse $ARGUMENTS:
   - If empty: channel = all from TELEGRAM_CHANNELS env, pages = 5
   - If one arg and not a number: that is the channel name, pages = 5
   - If one arg and a number: all channels, that many pages
   - If two args: first is channel, second is pages
2. Strip any leading @ from the channel name
3. Run the crawler with the Bash tool:
   - Single channel: `python3 -m rental.crawler --channel <channel> --pages <pages>`
   - All channels:   `python3 -m rental.crawler --pages <pages>`
4. Stream the output and report a summary:
   - How many listings extracted, skipped (duplicates), failed
   - Any errors encountered
5. If extractions succeeded, suggest running /normalize then /insights to clean and visualise the new data.
